#!/usr/bin/env python3
"""Milestone outreach trigger (P-036).

A milestone in docs/launch/milestones.json is reached when every listed PyPI
version and GitHub Release exists, none is yanked or a draft, and every PyPI file
carries a provenance whose publisher matches the manifest's. `start` then re-runs
the milestone's demo in an empty directory and opens one tracking issue holding
the facts, the transcript, a checklist per channel and the announcement text.
While the demo fails, each later `start` re-runs it and replaces that issue's body.
`announce` posts the announcement, as edited in the issue, to GitHub Discussions.
Nothing here posts outside this repository; docs/launch/README.md says who posts
where. Python 3.11+ and an authenticated `gh`.
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from continual_delivery import Blocked, gh_pages, repo_name, run  # noqa: E402

ROOT = SCRIPTS.parent
MANIFEST = "docs/launch/milestones.json"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
MARKER_RE = re.compile(r"<!-- outreach-milestone: ([a-z0-9][a-z0-9.-]*) -->")
POST_RE = re.compile(r"^## Post\n\n````text\n(.*?)\n````$", re.M | re.S)
PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
PLACEHOLDERS = {"releases", "demo", "demo_note"}
BLOCKED = "<!-- outreach-blocked -->"
BEGIN = "<!-- announcement:begin -->"
END = "<!-- announcement:end -->"
CATEGORY = "Announcements"
INTEGRITY = "application/vnd.pypi.integrity.v1+json"
DEMO_TIMEOUT = 600
# The demo installs and runs published code; it gets no token from the environment.
DEMO_ENV = ("HOME", "LANG", "LC_ALL", "TMPDIR", "LD_LIBRARY_PATH", "SSL_CERT_FILE",
            "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")
DISCUSSIONS = """query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    id
    discussionCategories(first: 25) { nodes { id name } }
    discussions(first: 100, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { title url }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""
CREATE_DISCUSSION = """mutation($repo: ID!, $category: ID!, $title: String!, $body: String!) {
  createDiscussion(input: {repositoryId: $repo, categoryId: $category, title: $title, body: $body}) {
    discussion { url }
  }
}"""


def marker(name):
    return f"<!-- outreach-milestone: {name} -->"


def load(root=ROOT):
    """Read the manifest and raise Blocked listing every problem in it."""
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    problems = []
    if manifest.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    if not isinstance(manifest.get("publisher"), dict) or not manifest["publisher"]:
        problems.append("publisher must be a non-empty object")
    milestones = manifest.get("milestones")
    if not isinstance(milestones, dict) or not milestones:
        problems.append("milestones must be a non-empty object")
        milestones = {}
    for name, milestone in milestones.items():
        where = f"milestone {name!r}"
        if not ID_RE.match(name):
            problems.append(f"{where}: id must match {ID_RE.pattern}")
        if not milestone.get("title"):
            problems.append(f"{where}: title is required")
        if not milestone.get("requires"):
            problems.append(f"{where}: requires must list at least one requirement")
        for item in milestone.get("requires", []):
            if set(item) not in ({"pypi", "version"}, {"github_release"}):
                problems.append(f"{where}: requirement {item} must have pypi and version, or github_release")
        for step in milestone.get("demo", []):
            if not isinstance(step.get("run"), str) or set(step) - {"run", "expect"}:
                problems.append(f"{where}: demo step {step} must have run and may have expect")
        if not milestone.get("channels"):
            problems.append(f"{where}: channels must list at least one venue")
        drafts = []
        for channel in milestone.get("channels", []):
            if not channel.get("venue") or not channel.get("by") or set(channel) - {"venue", "by", "draft"}:
                problems.append(f"{where}: channel {channel} must have venue and by and may have draft")
            if channel.get("draft"):
                drafts.append(channel["draft"])
        announcement = milestone.get("announcement")
        if announcement is not None:
            if set(announcement) != {"title", "draft"}:
                problems.append(f"{where}: announcement must have exactly title and draft")
            elif (root / announcement["draft"]).is_file():
                post = POST_RE.search((root / announcement["draft"]).read_text(encoding="utf-8"))
                if post is None:
                    problems.append(f"{where}: {announcement['draft']} has no '## Post' block fenced with ````text")
                elif set(PLACEHOLDER_RE.findall(post.group(1))) - PLACEHOLDERS:
                    unknown = sorted(set(PLACEHOLDER_RE.findall(post.group(1))) - PLACEHOLDERS)
                    problems.append(f"{where}: {announcement['draft']} uses unknown placeholders {unknown}")
            else:
                drafts.append(announcement["draft"])
        problems += [f"{where}: draft {draft} does not exist" for draft in drafts if not (root / draft).is_file()]
    if problems:
        raise Blocked(f"invalid {MANIFEST}:\n  " + "\n  ".join(problems))
    return manifest


def fetch_json(url, accept="application/json"):
    """GET a JSON document; None on 404, Blocked on any other failure."""
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "ai-decision-system-outreach"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise Blocked(f"GET {url}: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise Blocked(f"GET {url}: {error}") from error


def pypi_release(dist, version):
    """A PyPI release's page and files with their provenance publishers, or None if it is absent."""
    release = fetch_json(f"https://pypi.org/pypi/{dist}/{version}/json")
    if release is None:
        return None
    files = []
    for item in release["urls"]:
        url = f"https://pypi.org/integrity/{dist}/{version}/{item['filename']}/provenance"
        provenance = fetch_json(url, INTEGRITY) or {}
        files.append({
            "filename": item["filename"],
            "yanked": bool(item["yanked"] or release["info"]["yanked"]),
            "publishers": [bundle.get("publisher") or {} for bundle in provenance.get("attestation_bundles", [])],
        })
    return {"url": release["info"]["release_url"], "files": files}


def check(milestone, publisher, pypi, releases):
    """Return (facts, missing): a (label, state, url) row per requirement that holds, a reason per one that does not.

    `pypi(dist, version)` returns what `pypi_release` returns; `releases` maps a tag to its GitHub Release.
    """
    facts, missing = [], []
    for item in milestone["requires"]:
        if "pypi" in item:
            label = f"{item['pypi']} {item['version']} on PyPI"
            release = pypi(item["pypi"], item["version"])
            if release is None:
                missing.append(f"{label}: not published")
                continue
            problems = [] if release["files"] else ["no files"]
            for file in release["files"]:
                if file["yanked"]:
                    problems.append(f"{file['filename']} is yanked")
                if not any(all(found.get(key) == value for key, value in publisher.items())
                           for found in file["publishers"]):
                    problems.append(f"{file['filename']} has no provenance from the manifest publisher")
            if problems:
                missing.append(f"{label}: {'; '.join(problems)}")
            else:
                facts.append((label, f"{len(release['files'])} files, each with provenance from "
                              f"{publisher.get('repository')} {publisher.get('workflow')}", release["url"]))
        else:
            label = f"GitHub Release {item['github_release']}"
            release = releases.get(item["github_release"])
            if release is None or release.get("draft"):
                missing.append(f"{label}: {'draft' if release else 'not published'}")
            else:
                facts.append((label, f"published {release['published_at'][:10]}", release["html_url"]))
    return facts, missing


def run_demo(steps, workdir):
    """Run each step with bash in `workdir`, `.venv/bin` first on PATH; return (transcript, problem or None)."""
    env = {key: os.environ[key] for key in DEMO_ENV if key in os.environ}
    env["PATH"] = f"{Path(workdir) / '.venv' / 'bin'}{os.pathsep}{os.environ.get('PATH', os.defpath)}"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    lines = []
    for step in steps:
        lines.append(f"$ {step['run']}")
        try:
            result = subprocess.run(["bash", "-c", step["run"]], cwd=workdir, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=DEMO_TIMEOUT)
        except subprocess.TimeoutExpired:
            return "\n".join(lines), f"`{step['run']}` ran longer than {DEMO_TIMEOUT} seconds"
        if result.stdout:
            lines.append(result.stdout.rstrip("\n"))
        if result.returncode:
            return "\n".join(lines), f"`{step['run']}` exited {result.returncode}"
        absent = [text for text in step.get("expect", []) if text not in result.stdout]
        if absent:
            return "\n".join(lines), f"`{step['run']}` did not print {absent}"
    return "\n".join(lines), None


def announcement_text(root, milestone, facts, transcript, note):
    post = POST_RE.search((root / milestone["announcement"]["draft"]).read_text(encoding="utf-8")).group(1)
    values = {"releases": "\n".join(f"- [{label}]({url})" for label, _, url in facts),
              "demo": transcript or "", "demo_note": note}
    # One pass, so placeholder-like text inside a value is left alone.
    return PLACEHOLDER_RE.sub(lambda match: values[match.group(1)], post)


def issue_body(name, milestone, repo, facts, demo, announcement, origin):
    blob = f"https://github.com/{repo}/blob/main"
    transcript, problem = demo
    lines = [marker(name)] + ([BLOCKED] if problem else []) + [
        "",
        f"Milestone `{name}` is reached: {milestone['title']}. Plan IDs: {', '.join(milestone.get('plan', [])) or 'none'}.",
        "",
        f"Started by {origin}. Nothing outside this repository has been posted; the channels below say who posts where.",
        "",
        "## Facts checked",
        "",
        "| Requirement | State | Link |",
        "| --- | --- | --- |",
        *(f"| {label} | {state} | {url} |" for label, state, url in facts),
    ]
    if transcript is not None:
        lines += ["", "## Demo", "", (
            f"**Blocker:** {problem}. Post nothing yet. The next run of the trigger re-runs the demo and "
            "replaces this body; edits made here before then are lost." if problem else
            "Reproduced: every step exited 0 and printed what the milestone expects. Paste this output, "
            "unedited, over the demo in each draft."), "", "```text", transcript, "```"]
    lines += ["", "## Channels", "",
              f"Do the [owner checklist]({blob}/docs/launch/README.md#before-posting-owner-checklist) first, "
              f"and log each post in the [outreach log]({blob}/docs/launch/README.md#outreach-log) the same day.", ""]
    lines += [f"- [ ] **{channel['venue']}**: {channel['by']}"
              + (f" ([draft]({blob}/{channel['draft']}))" if channel.get("draft") else "")
              for channel in milestone["channels"]]
    if announcement is not None:
        lines += ["", "## Announcement", "",
                  f"The announce job posts the text between the markers to GitHub Discussions ({CATEGORY}) "
                  "when the `outreach` deployment is approved. Edit it here first; the job posts what is here then.",
                  "", BEGIN, announcement, END]
    return "\n".join(lines) + "\n"


def extract_announcement(body):
    body = body.replace("\r\n", "\n")
    begin, end = body.find(BEGIN), body.find(END)
    if begin < 0 or end < begin:
        return None
    return body[begin + len(BEGIN):end].strip() or None


class GitHub:
    """The GitHub reads and writes outreach makes, through `gh`. With dry_run, writes are printed instead."""

    def __init__(self, dry_run=False):
        self.repo = repo_name()
        self.dry_run = dry_run

    def _write(self, description, preview, method, path, payload):
        if self.dry_run:
            print(f"[dry run] {description}\n{preview}")
            return {"number": 0, "html_url": "(dry run)", "data": {"createDiscussion": {"discussion": {"url": "(dry run)"}}}}
        return json.loads(run("gh", "api", "--method", method, path, "--input", "-", input_text=json.dumps(payload)))

    def releases(self):
        return {release["tag_name"]: release for release in gh_pages(f"repos/{self.repo}/releases?per_page=100")}

    def issues(self):
        """Map each milestone name to its tracking issue."""
        found = {}
        for issue in gh_pages(f"repos/{self.repo}/issues?state=all&per_page=100"):
            match = MARKER_RE.search(issue.get("body") or "")
            if match and "pull_request" not in issue:
                found.setdefault(match.group(1), issue)
        return found

    def create_issue(self, title, body):
        return self._write(f"create issue {title!r}", body, "POST", f"repos/{self.repo}/issues",
                           {"title": title, "body": body})

    def edit_issue(self, number, body):
        return self._write(f"replace the body of #{number}", body, "PATCH", f"repos/{self.repo}/issues/{number}",
                           {"body": body})

    def comment(self, number, body):
        return self._write(f"comment on #{number}", body, "POST", f"repos/{self.repo}/issues/{number}/comments",
                           {"body": body})

    def discussions(self):
        owner, name = self.repo.split("/")
        payload = {"query": DISCUSSIONS, "variables": {"owner": owner, "name": name, "after": None}}
        nodes = []
        while True:
            repository = json.loads(run("gh", "api", "graphql", "--input", "-",
                                        input_text=json.dumps(payload)))["data"]["repository"]
            discussions = repository["discussions"]
            nodes.extend(discussions["nodes"])
            if not discussions["pageInfo"]["hasNextPage"]:
                discussions["nodes"] = nodes
                return repository
            payload["variables"]["after"] = discussions["pageInfo"]["endCursor"]

    def create_discussion(self, repository_id, category_id, title, body):
        variables = {"repo": repository_id, "category": category_id, "title": title, "body": body}
        response = self._write(f"create discussion {title!r} in {CATEGORY}", body, "POST", "graphql",
                               {"query": CREATE_DISCUSSION, "variables": variables})
        return response["data"]["createDiscussion"]["discussion"]["url"]


def origin_and_note(today):
    run_id = os.environ.get("GITHUB_RUN_ID")
    if run_id:
        url = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}"
        origin = f"[workflow run {run_id}]({url}) on {today} UTC"
    else:
        origin = f"`scripts/outreach.py` on {today} UTC"
    return origin, f"Run on {today} UTC in an empty directory on {platform.system()} {platform.machine()}; output unedited."


def start(root, github, pypi, today):
    """Open or refresh the tracking issue of every reached milestone; return those ready to announce."""
    manifest = load(root)
    issues, releases = github.issues(), github.releases()
    origin, note = origin_and_note(today)
    ready = []
    posted_titles = None
    for name, milestone in manifest["milestones"].items():
        issue = issues.get(name)
        facts, missing = check(milestone, manifest["publisher"], pypi, releases)
        if missing:
            print(f"{name}: not reached: {'; '.join(missing)}")
            continue
        if issue and BLOCKED not in (issue.get("body") or ""):
            print(f"{name}: already started in #{issue['number']}")
            if milestone.get("announcement"):
                if posted_titles is None:
                    posted_titles = {item["title"] for item in github.discussions()["discussions"]["nodes"]}
                if milestone["announcement"]["title"] not in posted_titles:
                    ready.append(name)
            continue
        demo = (None, None)
        if milestone.get("demo"):
            with tempfile.TemporaryDirectory(prefix="outreach-demo-") as workdir:
                demo = run_demo(milestone["demo"], workdir)
        announcement = None
        if demo[1] is None and milestone.get("announcement"):
            announcement = announcement_text(root, milestone, facts, demo[0], note)
        body = issue_body(name, milestone, github.repo, facts, demo, announcement, origin)
        if issue:
            github.edit_issue(issue["number"], body)
            action = f"refreshed #{issue['number']}"
        else:
            created = github.create_issue("Outreach: " + milestone["title"], body)
            action = f"opened {created['html_url']}"
        print(f"{name}: reached; {action}" + (f"; blocked: {demo[1]}" if demo[1] else ""))
        if announcement is not None:
            ready.append(name)
    return ready


def announce(root, github, names):
    """Post each named milestone's announcement from its tracking issue, once."""
    manifest = load(root)
    issues = github.issues()
    repository = github.discussions()
    category = next((item["id"] for item in repository["discussionCategories"]["nodes"] if item["name"] == CATEGORY), None)
    if category is None:
        raise Blocked(f"the repository has no {CATEGORY!r} discussion category")
    posted = {item["title"]: item["url"] for item in repository["discussions"]["nodes"]}
    for name in names:
        milestone = manifest["milestones"].get(name)
        if milestone is None or not milestone.get("announcement"):
            raise Blocked(f"{name}: no such milestone with an announcement in {MANIFEST}")
        issue = issues.get(name)
        if issue is None:
            raise Blocked(f"{name}: not started; run `start` first")
        if BLOCKED in (issue.get("body") or ""):
            raise Blocked(f"{name}: the demo has not reproduced (#{issue['number']})")
        text = extract_announcement(issue.get("body") or "")
        if text is None:
            raise Blocked(f"{name}: #{issue['number']} has no text between the announcement markers")
        title = milestone["announcement"]["title"]
        if title in posted:
            print(f"{name}: already announced at {posted[title]}")
            continue
        url = github.create_discussion(repository["id"], category, title, text)
        github.comment(issue["number"], f"Announced in GitHub Discussions: {url}")
        print(f"{name}: announced at {url}")


def status(root, github):
    manifest = load(root)
    issues, releases = github.issues(), github.releases()
    for name, milestone in manifest["milestones"].items():
        issue = issues.get(name)
        if issue:
            print(f"{name}: started in #{issue['number']}" + (" (demo blocked)" if BLOCKED in (issue.get("body") or "") else ""))
            continue
        _, missing = check(milestone, manifest["publisher"], pypi_release, releases)
        print(f"{name}: " + (f"not reached: {'; '.join(missing)}" if missing else "reached; the next `start` opens its issue"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="print whether each milestone is started, reached or not reached, and why")
    demo_parser = sub.add_parser("demo", help="run a milestone's demo in an empty directory and print the transcript")
    demo_parser.add_argument("milestone")
    start_parser = sub.add_parser("start", help="open or refresh the tracking issue of every reached milestone")
    start_parser.add_argument("--dry-run", action="store_true", help="print the issue instead of writing it")
    start_parser.add_argument("--github-output", type=Path, help="append announce=<milestones> to this file")
    announce_parser = sub.add_parser("announce", help="post the announcement of started milestones to GitHub Discussions")
    announce_parser.add_argument("milestones", nargs="+")
    announce_parser.add_argument("--dry-run", action="store_true", help="print the discussion instead of posting it")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            milestone = load(args.root)["milestones"].get(args.milestone)
            if not milestone or not milestone.get("demo"):
                raise Blocked(f"{args.milestone}: no such milestone with a demo in {MANIFEST}")
            with tempfile.TemporaryDirectory(prefix="outreach-demo-") as workdir:
                transcript, problem = run_demo(milestone["demo"], workdir)
            print(transcript)
            if problem:
                raise Blocked(problem)
        elif args.command == "status":
            status(args.root, GitHub())
        elif args.command == "start":
            today = datetime.now(timezone.utc).date().isoformat()
            ready = start(args.root, GitHub(args.dry_run), pypi_release, today)
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as output:
                    output.write(f"announce={' '.join(ready)}\n")
        else:
            announce(args.root, GitHub(args.dry_run), args.milestones)
    except (Blocked, KeyError, ValueError, OSError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
