#!/usr/bin/env python3
"""Export the first RELIA candidate without publishing or importing monorepo history."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile


PROJECT = "projects/ai-decision-reliability-framework"
BRANCH = "relia-release"
GENERATED_DIRS = {".venv", ".pytest_cache", "review-run", "repro-a", "repro-b"}


def git(repo, *args, data=None):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "Git command failed")
    return result.stdout


def git_text(repo, *args):
    return git(repo, *args).decode().strip()


def require_clean_project(source, commit):
    # Check index and worktree separately so staged and unstaged changes cannot cancel.
    for args in (("diff", "--cached", "--name-only", commit), ("diff", "--name-only")):
        if git(source, *args, "--", PROJECT):
            raise ValueError("Candidate project has staged or unstaged changes")
    status = git(source, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                 "--ignored=matching", "--", PROJECT)
    for entry in status.split(b"\0"):
        if not entry:
            continue
        state, path = entry[:2], entry[3:].decode()
        relative = PurePosixPath(path).relative_to(PROJECT)
        generated = (relative.parts[0] in GENERATED_DIRS
                     or "__pycache__" in relative.parts or relative.suffix == ".pyc")
        if state != b"!!" or not generated:
            raise ValueError("Uncommitted candidate file or directory: " + path)


def export(source, source_ref, output):
    source = Path(git_text(source, "rev-parse", "--show-toplevel")).resolve()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new, nonexistent directory")
    if output.resolve().is_relative_to(source):
        raise ValueError("Output must be outside the source repository")
    if not output.parent.is_dir():
        raise ValueError("Output parent directory must already exist")
    branches = git_text(source, "for-each-ref", "--format=%(refname)",
                        "refs/heads", "refs/remotes").splitlines()
    tags = git_text(source, "for-each-ref", "--format=%(refname)", "refs/tags/relia/")
    if tags or any(ref.rsplit("/", 1)[-1] == BRANCH for ref in branches):
        raise ValueError("First-release export only: an existing RELIA release ref was found")
    commit = git_text(source, "rev-parse", "--verify", source_ref + "^{commit}")
    tree = git_text(source, "rev-parse", "--verify", commit + ":" + PROJECT)
    if git_text(source, "cat-file", "-t", tree) != "tree":
        raise ValueError("The project path must be a committed directory")
    require_clean_project(source, commit)
    try:
        name = git_text(source, "config", "--get", "user.name")
        email = git_text(source, "config", "--get", "user.email")
    except ValueError:
        raise ValueError("Configure your Git user.name and user.email before exporting") from None
    if not name or not email:
        raise ValueError("Configure your Git user.name and user.email before exporting")
    object_format = git_text(source, "rev-parse", "--show-object-format")
    entries = []
    for entry in git(source, "ls-tree", "-r", "-z", tree).split(b"\0"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        path = raw_path.decode()
        parts = PurePosixPath(path).parts
        if (mode not in {"100644", "100755"} or kind != "blob"
                or not parts or path.startswith("/") or any(p in {"..", ".git"} for p in parts)):
            raise ValueError("Only regular project files are supported; rejected: " + path)
        entries.append({"path": path, "mode": mode, "object_id": oid})
    if not entries:
        raise ValueError("The committed project is empty")

    with tempfile.TemporaryDirectory(prefix=".relia-export-", dir=output.parent) as temporary:
        workspace = Path(temporary)
        candidate = workspace / "candidate"
        candidate.mkdir()
        git(candidate, "init", "--quiet", "--initial-branch=" + BRANCH,
            "--object-format=" + object_format)
        # Start from a tree object: this pack contains no source commits or parent history.
        objects = git(source, "rev-list", "--objects", "--no-object-names", tree)
        packed = git(source, "pack-objects", "--stdout", data=objects)
        git(candidate, "index-pack", "--stdin", data=packed)
        for entry in entries:
            blob = git(candidate, "cat-file", "blob", entry["object_id"])
            target = candidate / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            target.chmod(0o755 if entry["mode"] == "100755" else 0o644)
            entry["sha256"] = hashlib.sha256(blob).hexdigest()
        git(candidate, "read-tree", tree)
        metadata = (candidate / "pyproject.toml").read_text()
        project_section = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", metadata)
        version_match = re.search(r"(?m)^version\s*=\s*[\"']([^\"']+)[\"']\s*$",
                                  project_section[1] if project_section else "")
        if not version_match:
            raise ValueError("pyproject.toml must declare a literal project version")
        version = version_match[1]
        manifest = json.loads((candidate / "results/MANIFEST.json").read_text())
        if manifest["package_version"] != version:
            raise ValueError("Stored manifest and package versions differ")
        git(candidate, "check-ref-format", "refs/tags/relia/v" + version)
        # Use the maintainer's configured identity and Git's current timestamp.
        env = os.environ.copy()
        for key in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
            env.pop(key, None)
        env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                   GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
        exported = subprocess.run(
            ["git", "-C", str(candidate), "commit-tree", tree, "-m", "RELIA candidate " + version],
            env=env, check=True, capture_output=True, text=True,
        ).stdout.strip()
        git(candidate, "update-ref", "refs/heads/" + BRANCH, exported)
        if git_text(candidate, "rev-parse", "HEAD^{tree}") != tree:
            raise ValueError("Export tree identity mismatch")
        if git_text(candidate, "rev-list", "--count", "HEAD") != "1":
            raise ValueError("First export must have exactly one root commit")
        bundle = workspace / "relia.bundle"
        git(candidate, "bundle", "create", str(bundle), "refs/heads/" + BRANCH)
        git(candidate, "bundle", "verify", str(bundle))
        if git_text(candidate, "bundle", "list-heads", str(bundle)) != exported + " refs/heads/" + BRANCH:
            raise ValueError("Bundle contains unexpected refs")
        check_clone = workspace / "verify-clone"
        git(workspace, "clone", "--quiet", "--branch", BRANCH, str(bundle), str(check_clone))
        if (git_text(check_clone, "rev-parse", "HEAD") != exported
                or git_text(check_clone, "rev-parse", "HEAD^{tree}") != tree):
            raise ValueError("Fresh bundle clone identity mismatch")
        identity = {
            "status": "local export; acceptance and publication pending",
            "source_commit": commit, "project_path": PROJECT, "project_tree": tree,
            "export_commit": exported, "export_parent": None, "object_format": object_format,
            "branch": BRANCH, "intended_annotated_tag": "relia/v" + version,
            "package_version": version, "spec_version": manifest["spec_version"],
            "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
            "file_inventory": entries,
        }
        # Claim a fresh destination atomically; never replace an existing directory.
        output.mkdir()
        shutil.move(str(candidate), str(output / "candidate"))
        shutil.move(str(bundle), str(output / "relia.bundle"))
        (output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-ref", default="HEAD", help="Committed monorepo candidate (default: HEAD)")
    parser.add_argument("--output", required=True, type=Path, help="New directory outside the source repository")
    args = parser.parse_args()
    try:
        identity = export(args.source_repo, args.source_ref, args.output)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, "Export failed: " + str(error) + "\n")
    print(json.dumps({key: value for key, value in identity.items() if key != "file_inventory"}, indent=2))


if __name__ == "__main__":
    main()
