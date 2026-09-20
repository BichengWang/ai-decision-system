"""Exercise local export using disposable repositories and synthetic test identity."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "export-relia.py"
PROJECT = "projects/ai-decision-reliability-framework"


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.env = os.environ.copy()
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        for key in tuple(self.env):
            if key.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_")):
                del self.env[key]
        self.git(self.source, "init", "--quiet", "--initial-branch=main")
        self.git(self.source, "config", "user.name", "Fixture Maintainer")
        self.git(self.source, "config", "user.email", "maintainer@example.invalid")
        (self.source / "private-parent.txt").write_text("private historical content\n")
        self.commit("Private parent")
        self.private_commit = self.git(self.source, "rev-parse", "HEAD")
        self.private_blob = self.git(self.source, "rev-parse", "HEAD:private-parent.txt")
        (self.source / "private-parent.txt").unlink()
        self.project = self.source / PROJECT
        self.project.mkdir(parents=True)
        (self.project / "pyproject.toml").write_text('[project]\nname = "relia"\nversion = "0.1.5"\n')
        (self.project / "README.md").write_bytes(b"Candidate\r\nPreserve bytes.\n")
        (self.project / ".gitattributes").write_text("README.md export-ignore\n")
        (self.project / ".gitignore").write_text(".venv/\nrepro-a/\n__pycache__/\n.pytest_cache/\n*.pyc\nhidden.py\n")
        (self.project / "uv.lock").write_text("fixture lock\n")
        (self.project / "run.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.project / "run.sh").chmod(0o755)
        (self.project / "results").mkdir()
        (self.project / "results/MANIFEST.json").write_text(json.dumps({"package_version": "0.1.5", "spec_version": "0.1.3"}))
        self.commit("Candidate")
        self.output = self.root / "export"

    def git(self, repo, *args, check=True):
        result = subprocess.run(["git", "-C", str(repo), *args], env=self.env, check=check,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode().strip()

    def commit(self, message):
        self.git(self.source, "add", "--all")
        self.git(self.source, "commit", "--quiet", "-m", message)

    def run_export(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "--source-repo", str(self.source),
                               "--output", str(self.output), *extra], env=self.env,
                              capture_output=True, text=True)

    def assert_rejected(self, expected):
        result = self.run_export()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)

    def test_export_tree_bundle_and_source_history_isolation(self):
        before = self.git(self.source, "rev-parse", "HEAD")
        result = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.output / "identity.json").read_text())
        candidate = self.output / "candidate"
        tree = self.git(self.source, "rev-parse", "HEAD:" + PROJECT)
        self.assertEqual(tree, self.git(candidate, "rev-parse", "HEAD^{tree}"))
        self.assertEqual(tree, record["project_tree"])
        self.assertEqual("1", self.git(candidate, "rev-list", "--count", "HEAD"))
        self.assertEqual("Fixture Maintainer <maintainer@example.invalid>",
                         self.git(candidate, "show", "-s", "--format=%an <%ae>", "HEAD"))
        self.assertEqual((candidate / "README.md").read_bytes(), (self.project / "README.md").read_bytes())
        self.assertTrue((candidate / "run.sh").stat().st_mode & 0o111)
        self.assertFalse((candidate / "identity.json").exists())
        self.assertEqual("", self.git(candidate, "remote"))
        self.assertEqual(before, self.git(self.source, "rev-parse", "HEAD"))
        self.assertEqual("", self.git(self.source, "status", "--porcelain"))
        bundle = self.output / "relia.bundle"
        self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(), record["bundle_sha256"])
        clone = self.root / "fresh-clone"
        self.git(self.root, "clone", "--quiet", "--branch", "relia-release", str(bundle), str(clone))
        self.assertEqual(record["export_commit"], self.git(clone, "rev-parse", "HEAD"))
        self.assertEqual(tree, self.git(clone, "rev-parse", "HEAD^{tree}"))
        for repository in (candidate, clone):
            for oid in (before, self.private_commit, self.private_blob):
                probe = subprocess.run(["git", "-C", str(repository), "cat-file", "-e", oid],
                                       env=self.env, capture_output=True)
                self.assertNotEqual(probe.returncode, 0, "Source history leaked into export")

    def test_staged_and_unstaged_changes_rejected(self):
        for staged in (False, True):
            with self.subTest(staged=staged):
                (self.project / "README.md").write_text("Changed\n")
                if staged:
                    self.git(self.source, "add", PROJECT)
                self.assert_rejected("staged or unstaged changes")
        self.assertFalse(self.output.exists())

    def test_untracked_and_ignored_source_rejected(self):
        for name in ("new.py", "hidden.py"):
            with self.subTest(name=name):
                path = self.project / name
                path.write_text("source\n")
                self.assert_rejected("Uncommitted candidate")
                path.unlink()

    def test_normal_ignored_environment_and_run_output_allowed(self):
        for name in (".venv", "repro-a", "__pycache__", ".pytest_cache"):
            directory = self.project / name
            directory.mkdir()
            (directory / "local.txt").write_text("local generated content\n")
        result = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.output / "candidate/.venv").exists())
        self.assertFalse((self.output / "candidate/repro-a").exists())

    def test_existing_output_even_empty_is_preserved(self):
        self.output.mkdir()
        self.assert_rejected("new, nonexistent directory")
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep\n")
        self.assert_rejected("new, nonexistent directory")
        self.assertEqual("keep\n", sentinel.read_text())

    def test_symlink_and_gitlink_rejected(self):
        (self.project / "external-link").symlink_to("../../private-parent.txt")
        self.commit("Link")
        self.assert_rejected("Only regular project files")
        (self.project / "external-link").unlink()
        self.commit("Remove link")
        self.git(self.source, "update-index", "--add", "--cacheinfo", "160000," + self.private_commit + "," + PROJECT + "/submodule")
        self.git(self.source, "commit", "--quiet", "-m", "Gitlink")
        (self.project / "submodule").mkdir()
        self.assert_rejected("Only regular project files")

    def test_existing_release_refs_reject_another_orphan(self):
        for ref in ("refs/heads/relia-release", "refs/remotes/origin/relia-release", "refs/tags/relia/v0.1.4"):
            with self.subTest(ref=ref):
                self.git(self.source, "update-ref", ref, "HEAD")
                self.assert_rejected("First-release export only")
                self.git(self.source, "update-ref", "-d", ref)

    def test_output_inside_source_rejected(self):
        self.output = self.source / "candidate-output"
        self.assert_rejected("outside the source repository")

    def test_manifest_version_mismatch_rejected(self):
        (self.project / "results/MANIFEST.json").write_text(json.dumps({"package_version": "0.1.4", "spec_version": "0.1.3"}))
        self.commit("Mismatched manifest")
        self.assert_rejected("manifest and package versions differ")
        self.assertFalse(self.output.exists())

    def test_unrelated_root_changes_do_not_block_project_export(self):
        (self.source / "unrelated.txt").write_text("Unrelated local work\n")
        result = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
