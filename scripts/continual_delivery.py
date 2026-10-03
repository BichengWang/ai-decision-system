#!/usr/bin/env python3
"""Fail-closed GitHub gate and queue snapshot for the local delivery task.

The scheduled Codex task performs implementation and starts an independent review.
This tool only reads GitHub state, records a review result, and merges a verified SHA.
"""

import argparse
import fcntl
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MANAGED = "continual-managed"
READY = "continual-ready"
REVIEW_PREFIX = "<!-- continual-review "
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ATTRIBUTION_RE = re.compile(r"codex", re.IGNORECASE)
IMPLEMENTATION_RE = re.compile(r"^Implementation run: ([A-Za-z0-9._/-]+)$", re.M)
CHECK_WORKFLOWS = {
    "Delivery policy": "Delivery policy",
    "RELIA required": "RELIA CI",
    "src baseline": "Research baseline",
    "test (3.11)": "Experiment gate CI",
    "test (3.13)": "Experiment gate CI",
}
RELEASE_PATHS = (
    "docs/RELIA_RELEASE.md",
    ".github/workflows/relia-release-verify.yml",
    "ai-workflows/ai-decision-reliability/LICENSE",
    "ai-workflows/ai-decision-reliability/templates/release-record.md",
)


class Blocked(RuntimeError):
    pass


def run(*args, input_text=None):
    result = subprocess.run(
        args, input=input_text, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise Blocked(f"{' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def gh_json(*args):
    return json.loads(run("gh", *args))


def gh_pages(path):
    pages = gh_json("api", path, "--paginate", "--slurp")
    return [item for page in pages for item in page]


def repo_name():
    return gh_json("repo", "view", "--json", "nameWithOwner")["nameWithOwner"]


def labels(item):
    return {label["name"] for label in item.get("labels", [])}


def local_day(timestamp):
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(
        ZoneInfo("America/Los_Angeles")
    ).date()


def day_counts(merged, now):
    today = now.astimezone(ZoneInfo("America/Los_Angeles")).date()
    return sum(
        MANAGED in labels(pr)
        and pr.get("mergedAt")
        and local_day(pr["mergedAt"]) == today
        for pr in merged
    )


def snapshot():
    run("gh", "auth", "status")
    repo = repo_name()
    open_prs = gh_json(
        "pr", "list", "--state", "open", "--limit", "1000",
        "--json", "number,title,headRefName,labels,url",
    )
    merged_prs = gh_json(
        "pr", "list", "--state", "merged", "--limit", "1000",
        "--json", "number,mergedAt,labels",
    )
    issues = gh_json(
        "issue", "list", "--state", "open", "--label", READY,
        "--limit", "1000", "--json", "number,title,createdAt,labels,url",
    )
    if any(len(items) >= 1000 for items in (open_prs, merged_prs, issues)):
        raise Blocked("GitHub listing reached its limit; refusing an incomplete snapshot")
    managed = [pr for pr in open_prs if MANAGED in labels(pr)]
    active_ids = {
        int(match.group(1))
        for pr in managed
        for match in [re.search(r"^automation/issue-(\d+)(?:-|$)", pr["headRefName"])]
        if match
    }
    queue = sorted(
        (issue for issue in issues if issue["number"] not in active_ids),
        key=lambda issue: issue["createdAt"],
    )
    count = day_counts(merged_prs, datetime.now(ZoneInfo("America/Los_Angeles")))
    return {
        "repo": repo,
        "date": str(datetime.now(ZoneInfo("America/Los_Angeles")).date()),
        "merged_today": count,
        "daily_target": [15, 20],
        "open_managed_prs": managed,
        "next_issue": queue[0] if queue and count < 20 and len(managed) < 3 else None,
        "blocker": "daily cap" if count >= 20 else "three PRs open" if len(managed) >= 3 else None,
    }


def required_checks(paths):
    required = {"Delivery policy"}
    if any(
        path.startswith("ai-workflows/ai-decision-reliability/")
        or path.startswith("scripts/export-relia")
        or path.startswith(".github/workflows/relia-")
        or path in {"Makefile", ".gitignore"}
        for path in paths
    ):
        required.add("RELIA required")
    if any(
        path.startswith("ai-workflows/experiment-gate/")
        or path == ".github/workflows/expgate-ci.yml"
        for path in paths
    ):
        required.update({"test (3.11)", "test (3.13)"})
    # Keep this aligned with the path filters in src-baseline.yml. Root setup
    # changes affect the research environment even when no src/ file changes.
    if any(
        path.startswith(("src/", "tests/"))
        or path in {
            "pyproject.toml", "requirements.txt", "setup.cfg", "Makefile",
            ".github/workflows/src-baseline.yml",
        }
        for path in paths
    ):
        required.add("src baseline")
    return required


def review_result(comments, sha, implementation_run, trusted_login):
    verdict = None
    for comment in comments:
        if (comment.get("user") or {}).get("login") != trusted_login:
            continue
        body = comment.get("body", "")
        for line in body.splitlines():
            if line.startswith(REVIEW_PREFIX) and line.endswith(" -->"):
                try:
                    record = json.loads(line[len(REVIEW_PREFIX):-4])
                except json.JSONDecodeError:
                    continue
                if (record.get("head_sha") == sha
                        and record.get("reviewer_run")
                        and record["reviewer_run"] != implementation_run):
                    if record.get("verdict") == "BLOCK" or record.get("blocking_findings") != 0:
                        return record
                    verdict = record
    return verdict


def evaluate(pr, comments, commits, trusted_login="BichengWang"):
    failures = []
    sha = pr.get("headRefOid", "")
    paths = {item["path"] for item in pr.get("files", [])}
    if not SHA_RE.fullmatch(sha):
        failures.append("missing exact head SHA")
    if pr.get("state") != "OPEN" or pr.get("isDraft"):
        failures.append("PR is closed or draft")
    if pr.get("baseRefName") != "main" or pr.get("headRefName") == "relia-release":
        failures.append("wrong base or release branch")
    if ATTRIBUTION_RE.search(pr.get("headRefName") or ""):
        failures.append("branch name contains forbidden attribution")
    if ATTRIBUTION_RE.search(pr.get("title") or ""):
        failures.append("PR title contains forbidden attribution")
    if MANAGED not in labels(pr):
        failures.append("PR is not managed")
    if pr.get("mergeStateStatus") != "CLEAN":
        failures.append("branch is not current and clean")
    if not paths or any(path in RELEASE_PATHS for path in paths):
        failures.append("empty or release-related diff")
    if ATTRIBUTION_RE.search(pr.get("body") or ""):
        failures.append("PR description contains forbidden attribution")
    implementation = IMPLEMENTATION_RE.search(pr.get("body") or "")
    if not implementation:
        failures.append("PR must identify its implementation run")
    for commit in commits:
        author = commit.get("commit", {}).get("author") or {}
        committer = commit.get("commit", {}).get("committer") or {}
        message = commit.get("commit", {}).get("message", "")
        if any(ATTRIBUTION_RE.search(author.get(key) or "") for key in ("name", "email")):
            failures.append("commit author contains forbidden attribution")
        if any(ATTRIBUTION_RE.search(committer.get(key) or "") for key in ("name", "email")):
            failures.append("commit committer contains forbidden attribution")
        if ATTRIBUTION_RE.search(message):
            failures.append("commit message contains forbidden attribution")
    checks = {}
    for check in pr.get("statusCheckRollup") or []:
        name = check.get("name") or check.get("context")
        if name:
            checks.setdefault(name, []).append(check)
    for name in sorted(required_checks(paths)):
        matching = checks.get(name, [])
        if not matching or any(
            (check.get("conclusion") or check.get("state")) != "SUCCESS"
            or check.get("workflowName") != CHECK_WORKFLOWS[name]
            for check in matching
        ):
            failures.append(f"required check {name} is missing, failing, or from the wrong workflow")
    review = review_result(comments, sha, implementation.group(1) if implementation else "", trusted_login)
    if not review or review.get("verdict") != "PASS" or review.get("blocking_findings") != 0:
        failures.append("independent review has no passing receipt for head SHA")
    return failures


def pr_data(repo, number):
    pr = gh_json(
        "pr", "view", str(number), "--json",
        "number,title,body,state,isDraft,headRefOid,headRefName,baseRefName,mergeStateStatus,files,statusCheckRollup,labels",
    )
    comments = gh_pages(f"repos/{repo}/issues/{number}/comments?per_page=100")
    commits = gh_pages(f"repos/{repo}/pulls/{number}/commits?per_page=100")
    return pr, comments, commits


def branch_rules(repo):
    protection = gh_json("api", f"repos/{repo}/branches/main/protection")
    checks = protection.get("required_status_checks") or {}
    names = set(checks.get("contexts") or []) | {
        check.get("context") for check in checks.get("checks") or []
    }
    if not {"Delivery policy", "RELIA required"} <= names:
        raise Blocked("main must require Delivery policy and RELIA required")
    if not checks.get("strict"):
        raise Blocked("main must require branches to be up to date")
    if not (protection.get("enforce_admins") or {}).get("enabled"):
        raise Blocked("main must apply protection to administrators")


def gate(repo, number):
    pr, comments, commits = pr_data(repo, number)
    failures = evaluate(pr, comments, commits, repo.split("/", 1)[0])
    if failures:
        raise Blocked("; ".join(failures))
    branch_rules(repo)
    return pr["headRefOid"]


@contextmanager
def merge_lock(repo):
    name = hashlib.sha256(repo.encode()).hexdigest()[:16]
    path = Path(tempfile.gettempdir()) / f"continual-delivery-{name}.lock"
    with open(path, "a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Blocked("another local merge is already running") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def merge(repo, number):
    with merge_lock(repo):
        return _merge_locked(repo, number)


def _merge_locked(repo, number):
    state = snapshot()
    if state["merged_today"] >= 20:
        raise Blocked("20 managed PRs already merged today")
    identity = run("git", "config", "user.name") + " " + run("git", "config", "user.email")
    if ATTRIBUTION_RE.search(identity):
        raise Blocked("configured Git identity violates attribution rule")
    sha = gate(repo, number)
    # Refresh the review and checks immediately before the conditional merge.
    if gate(repo, number) != sha:
        raise Blocked("PR head changed before merge")
    # The GitHub merge API rejects a changed head; the branch rules protect CI.
    response = json.loads(run(
        "gh", "api", "--method", "PUT", f"repos/{repo}/pulls/{number}/merge",
        "--input", "-", input_text=json.dumps({"sha": sha, "merge_method": "squash"}),
    ))
    if not response.get("merged"):
        raise Blocked("GitHub did not confirm the merge")
    merged_pr = gh_json("api", f"repos/{repo}/pulls/{number}")
    if not merged_pr.get("merged") or not merged_pr.get("merge_commit_sha"):
        raise Blocked("merged PR could not be verified")
    merge_sha = merged_pr["merge_commit_sha"]
    comparison = gh_json("api", f"repos/{repo}/compare/{merge_sha}...main")
    if comparison.get("status") not in {"identical", "ahead"}:
        raise Blocked("merged commit is not on main")
    return {"number": number, "head_sha": sha, "merge_commit_sha": merge_sha}


def record_review(repo, number, report_path):
    with open(report_path, encoding="utf-8") as report_file:
        report = json.load(report_file)
    sha = gh_json("pr", "view", str(number), "--json", "headRefOid")["headRefOid"]
    if report.get("head_sha") != sha or not SHA_RE.fullmatch(sha):
        raise Blocked("review is stale or missing an exact head SHA")
    if report.get("verdict") not in {"PASS", "BLOCK"}:
        raise Blocked("review verdict must be PASS or BLOCK")
    if not isinstance(report.get("blocking_findings"), int) or report["blocking_findings"] < 0:
        raise Blocked("review must count blocking findings")
    if not report.get("reviewer_run"):
        raise Blocked("reviewer_run is required")
    payload = {key: report[key] for key in ("head_sha", "verdict", "blocking_findings", "reviewer_run")}
    body = f"{REVIEW_PREFIX}{json.dumps(payload, sort_keys=True)} -->\n\n{report.get('summary', '')}"
    run("gh", "api", "--method", "POST", f"repos/{repo}/issues/{number}/comments",
        "--input", "-", input_text=json.dumps({"body": body}))
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot")
    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("number", type=int)
    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("number", type=int)
    review_parser = sub.add_parser("record-review")
    review_parser.add_argument("number", type=int)
    review_parser.add_argument("report")
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            result = snapshot()
        else:
            run("gh", "auth", "status")
            repo = repo_name()
            if args.command == "gate":
                result = {"head_sha": gate(repo, args.number), "ready": True}
            elif args.command == "merge":
                result = merge(repo, args.number)
            else:
                result = record_review(repo, args.number, args.report)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (Blocked, KeyError, ValueError, OSError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
