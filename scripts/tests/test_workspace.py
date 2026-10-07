import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "workspace.py"
SPEC = importlib.util.spec_from_file_location("workspace", MODULE_PATH)
workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace)

ROOT = Path(__file__).resolve().parents[2]


# The components and checks the controller routed by hand before workspace.json.
ORIGINAL_COMPONENTS = ("relia", "experiment-gate", "research-workbench", "workspace-tooling")
ORIGINAL_CHECK_WORKFLOWS = {
    "Delivery policy": "Delivery policy",
    "RELIA required": "RELIA CI",
    "src baseline": "Research baseline",
    "test (3.11)": "Experiment gate CI",
    "test (3.13)": "Experiment gate CI",
}


def legacy_required_checks(paths):
    """The controller's hardcoded routing before workspace.json, kept as a parity reference."""
    required = {"Delivery policy"}
    if any(path.startswith(("ai-workflows/ai-decision-reliability/", "scripts/export-relia",
                            ".github/workflows/relia-")) or path in {"Makefile", ".gitignore"}
           for path in paths):
        required.add("RELIA required")
    if any(path.startswith("ai-workflows/experiment-gate/") or path == ".github/workflows/expgate-ci.yml"
           for path in paths):
        required.update({"test (3.11)", "test (3.13)"})
    if any(path.startswith(("src/", "tests/")) or path in {
            "pyproject.toml", "requirements.txt", "setup.cfg", "Makefile", ".github/workflows/src-baseline.yml"}
           for path in paths):
        required.add("src baseline")
    return required


def clean_git_env():
    """Git environment isolated from user, system, and injected configuration."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("GIT_CONFIG", "GIT_AUTHOR_", "GIT_COMMITTER_"))}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    return env


def component(**changes):
    result = {
        "kind": "project",
        "path": "ai-workflows/demo",
        "summary": "Demo project",
        "sources": ["ai-workflows/demo/**"],
        "packages": ["demo"],
        "third_party_imports": [],
        "paths": ["ai-workflows/demo/**", ".github/workflows/demo-ci.yml"],
        "ci": {"workflow": ".github/workflows/demo-ci.yml", "trigger": "paths"},
        "checks": [{"name": "demo test", "workflow": "Demo CI"}],
        "test": [{"run": "python3 -m unittest discover -s tests"}],
    }
    result.update(changes)
    return result


def manifest(**components):
    return {
        "schema_version": 1,
        "description": "fixture",
        "global_paths": ["workspace.json"],
        "always_required_checks": [{"name": "Policy", "workflow": "Policy"}],
        "components": components or {"demo": component()},
    }


DEMO_WORKFLOW = """name: Demo CI
on:
  pull_request:
    branches: [main]
    paths:
      - "ai-workflows/demo/**"
      - ".github/workflows/demo-ci.yml"
      - "workspace.json"
  push:
    branches: [main]
    paths:
      - "ai-workflows/demo/**"
      - ".github/workflows/demo-ci.yml"
      - "workspace.json"
jobs:
  test:
    name: demo test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@cccccccccccccccccccccccccccccccccccccccc # v9
      - uses: actions/setup-python@5555555555555555555555555555555555555555 # v8
      - run: |
          echo "paths:"  # a block scalar must not be read as a trigger
"""

POLICY_WORKFLOW = """name: Policy
on:
  pull_request:
    branches: [main]
jobs:
  policy:
    name: Policy
    runs-on: ubuntu-latest
    steps:
      - run: true
"""


class FixtureRepo:
    """A tiny monorepo with one stdlib project and an always-on tooling component."""

    def __init__(self, folder):
        self.root = Path(folder)
        self.manifest = manifest(
            demo=component(),
            tooling=component(
                kind="tooling", path="tools", summary="Tooling", sources=["tools/**"], packages=["tool"],
                paths=["tools/**", ".github/workflows/policy.yml"],
                ci={"workflow": ".github/workflows/policy.yml", "trigger": "always"},
                checks=[{"name": "Policy", "workflow": "Policy"}],
                test=[{"run": "python3 -c pass"}],
            ),
        )
        self.write("workspace.json", json.dumps(self.manifest, indent=2))
        self.write("README.md", "| Project | Scope |\n| --- | --- |\n| [Demo](ai-workflows/demo/README.md) | Demo |\n")
        self.write("ai-workflows/README.md", "| Project | Purpose | Run from |\n| --- | --- | --- |\n"
                   "| [`demo`](demo/README.md) | Demo | `ai-workflows/demo/` |\n\nMore text.\n")
        self.write("ai-workflows/demo/README.md", "Demo\n")
        self.write("ai-workflows/demo/pyproject.toml", "[project]\nname = 'demo'\n")
        self.write("ai-workflows/demo/demo/__init__.py", "import json\nfrom . import core\n")
        self.write("ai-workflows/demo/demo/core.py", "import os.path\n")
        self.write("ai-workflows/demo/tests/test_demo.py", "import unittest\nimport demo\n")
        self.write("tools/tool.py", "import sys\n")
        self.write(".github/workflows/demo-ci.yml", DEMO_WORKFLOW)
        self.write(".github/workflows/policy.yml", POLICY_WORKFLOW)
        self.git("init", "--quiet", "--initial-branch=main")
        self.git("add", "--all")
        self.git("commit", "--quiet", "--no-gpg-sign", "-m", "Fixture")

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], env=clean_git_env(), check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()

    def commit_all(self, message):
        self.git("add", "--all")
        self.git("commit", "--quiet", "--no-gpg-sign", "-m", message)
        return self.git("rev-parse", "HEAD")

    def problems(self):
        self.git("add", "--all")
        return workspace.check_workspace(self.root, workspace.load_manifest(self.root))


class RepositoryManifestTests(unittest.TestCase):
    def test_repository_workspace_is_consistent(self):
        self.assertEqual(workspace.check_workspace(ROOT), [])

    def test_manifest_routing_matches_previous_controller_rules(self):
        loaded = workspace.load_manifest(ROOT)
        intentional = {
            # RELIA CI already validated these; the controller now agrees with it.
            "scripts/tests/test_export_relia.py": {"Delivery policy", "RELIA required"},
            # The manifest routes every component, so a change to it runs every check.
            "workspace.json": set(workspace.check_workflows(loaded)),
        }
        # Components registered after the hardcoded rules add only their own checks.
        later = [component for name, component in loaded["components"].items()
                 if name not in ORIGINAL_COMPONENTS]
        paths = sorted(set(workspace.tracked_files(ROOT)) | set(intentional) | {
            "src/new.py", "tests/new.py", "docs/new.md", "new-root-file", "scripts/workspace.py"})
        for path in paths:
            with self.subTest(path=path):
                expected = intentional.get(path)
                if expected is None:
                    expected = legacy_required_checks([path])
                    for component in later:
                        if workspace.matches_any(component["paths"], path):
                            expected = expected | {check["name"] for check in component["checks"]}
                self.assertEqual(workspace.required_checks(loaded, [path]), expected)

    def test_original_check_names_map_to_their_workflows(self):
        mapping = workspace.check_workflows(workspace.load_manifest(ROOT))
        self.assertLessEqual(ORIGINAL_CHECK_WORKFLOWS.items(), mapping.items())


class PatternTests(unittest.TestCase):
    def test_matching_follows_github_path_filters(self):
        cases = [
            ("src/**", "src/a/b.py", True),
            ("src/**", "src/a.py", True),
            ("src/**", "srcx/a.py", False),
            ("src/**", "src", False),
            ("scripts/export-relia*", "scripts/export-relia.py", True),
            ("scripts/export-relia*", "scripts/export-relia/x.py", False),
            (".github/workflows/relia-*", ".github/workflows/relia-ci.yml", True),
            (".github/workflows/relia-*", ".github/workflows/expgate-ci.yml", False),
            ("Makefile", "Makefile", True),
            ("Makefile", "docs/Makefile", False),
            ("a.b", "aXb", False),
        ]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertIs(workspace.matches(pattern, path), expected)

    def test_unsupported_patterns_are_rejected(self):
        for pattern in ("", "/src/**", "src/../x", "**/x.py", "src/**/x.py", "src/**x", "a?b",
                        "[ab]", "!src/**", "src//x", "**"):
            with self.subTest(pattern=pattern):
                self.assertIsNotNone(workspace.pattern_problem(pattern))
        for pattern in ("src/**", "Makefile", ".github/workflows/relia-*", "a/*/b"):
            with self.subTest(pattern=pattern):
                self.assertIsNone(workspace.pattern_problem(pattern))


class ManifestValidationTests(unittest.TestCase):
    def test_valid_fixture(self):
        self.assertEqual(workspace.validate(manifest()), [])

    def test_structural_errors_are_reported(self):
        broken = {
            "unknown key": manifest(demo={**component(), "extra": 1}),
            "missing key": manifest(demo={k: v for k, v in component().items() if k != "checks"}),
            "kind": manifest(demo=component(kind="service")),
            "trigger": manifest(demo=component(ci={"workflow": ".github/workflows/x.yml", "trigger": "cron"})),
            "workflow location": manifest(demo=component(ci={"workflow": "ci.yml", "trigger": "paths"})),
            "name": manifest(Demo=component()),
            "package": manifest(demo=component(packages=["not-an-identifier"])),
            "empty paths": manifest(demo=component(paths=[])),
            "duplicate path": manifest(demo=component(paths=["a/**", "a/**"])),
            "glob": manifest(demo=component(paths=["a/**/b"])),
            "test cwd": manifest(demo=component(test=[{"run": "true", "cwd": "../x"}])),
            "test command": manifest(demo=component(test=[{"run": "echo 'unterminated"}])),
            "env": manifest(demo=component(test_env={"A": 1})),
            "path": manifest(demo=component(path="ai-workflows/demo/")),
            "shared package": manifest(a=component(), b=component()),
            "check workflow": manifest(a=component(), b=component(
                packages=["other"], checks=[{"name": "demo test", "workflow": "Other CI"}])),
        }
        for label, value in broken.items():
            with self.subTest(label=label):
                self.assertTrue(workspace.validate(value))

    def test_load_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "workspace.json"
            path.write_text("{not json")
            with self.assertRaises(workspace.ManifestError):
                workspace.load_manifest(folder)
            path.write_text(json.dumps(manifest(demo=component(kind="service"))))
            with self.assertRaises(workspace.ManifestError):
                workspace.load_manifest(folder)
            path.unlink()
            with self.assertRaises(OSError):
                workspace.load_manifest(folder)


class AffectedTests(unittest.TestCase):
    def setUp(self):
        self.manifest = manifest(
            demo=component(),
            other=component(path="ai-workflows/other", sources=["ai-workflows/other/**"], packages=["other"],
                            paths=["ai-workflows/other/**", "Makefile"],
                            checks=[{"name": "other test", "workflow": "Other CI"}]),
        )

    def test_components_and_checks_follow_changed_paths(self):
        self.assertEqual(workspace.affected_components(self.manifest, ["ai-workflows/demo/x.py"]), ["demo"])
        self.assertEqual(workspace.affected_components(self.manifest, ["Makefile", "docs/a.md"]), ["other"])
        self.assertEqual(workspace.affected_components(self.manifest, ["docs/a.md", ""]), [])
        self.assertEqual(workspace.required_checks(self.manifest, ["docs/a.md"]), {"Policy"})
        self.assertEqual(workspace.required_checks(self.manifest, ["ai-workflows/demo/x.py"]),
                         {"Policy", "demo test"})

    def test_global_path_affects_every_component(self):
        self.assertEqual(workspace.affected_components(self.manifest, ["workspace.json"]), ["demo", "other"])
        self.assertEqual(workspace.required_checks(self.manifest, ["workspace.json"]),
                         {"Policy", "demo test", "other test"})


class WorkflowReaderTests(unittest.TestCase):
    def test_reads_name_events_and_path_filters(self):
        result = workspace.read_workflow(DEMO_WORKFLOW)
        self.assertEqual(result["name"], "Demo CI")
        self.assertEqual(result["events"]["pull_request"]["paths"],
                         ["ai-workflows/demo/**", ".github/workflows/demo-ci.yml", "workspace.json"])
        self.assertEqual(set(result["events"]), {"pull_request", "push"})

    def test_reads_flow_style_comments_and_ignore_filters(self):
        result = workspace.read_workflow(
            "# leading comment\nname: 'Quoted # name'  # trailing\non: [push, pull_request]\njobs: {}\n")
        self.assertEqual(result, {"name": "Quoted # name", "events": {"push": {}, "pull_request": {}}})
        result = workspace.read_workflow(
            "name: X\non:\n  pull_request:\n    paths-ignore: ['docs/**', \"*.md\"]\n  workflow_dispatch:\n")
        self.assertEqual(result["events"], {
            "pull_request": {"paths-ignore": ["docs/**", "*.md"]}, "workflow_dispatch": {}})

    def test_repository_workflows_are_readable(self):
        for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
            with self.subTest(path=path.name):
                result = workspace.read_workflow(path.read_text(encoding="utf-8"))
                self.assertTrue(result["name"])
                self.assertTrue(result["events"])

    def test_missing_triggers_are_an_error(self):
        with self.assertRaises(workspace.WorkspaceError):
            workspace.read_workflow("name: X\njobs: {}\n")
        with self.assertRaises(workspace.WorkspaceError):
            workspace.read_workflow("name: X\non:\njobs: {}\n")


class ImportBoundaryTests(unittest.TestCase):
    def check(self, files, loaded=None, stdlib=frozenset({"json", "os", "sys", "unittest"})):
        loaded = loaded or manifest(
            demo=component(third_party_imports=["numpy"]),
            other=component(path="ai-workflows/other", sources=["ai-workflows/other/**"], packages=["other"],
                            paths=["ai-workflows/other/**"], third_party_imports=None),
        )
        with tempfile.TemporaryDirectory() as folder:
            for path, text in files.items():
                (Path(folder) / path).parent.mkdir(parents=True, exist_ok=True)
                (Path(folder) / path).write_text(text, encoding="utf-8")
            return workspace.import_problems(folder, loaded, list(files), stdlib=stdlib)

    def test_allowed_imports_pass(self):
        self.assertEqual(self.check({
            "ai-workflows/demo/demo/a.py": "import json, os.path\nfrom . import b\nfrom demo.b import c\nimport numpy\n",
            "ai-workflows/other/x.py": "import pandas\nimport other\n",
            "ai-workflows/demo/README.md": "import other\n",
        }), [])

    def test_cross_component_and_undeclared_imports_fail(self):
        problems = self.check({
            "ai-workflows/demo/demo/a.py": "import json\n\nfrom other.core import x\nimport requests\n",
            "ai-workflows/other/x.py": "import demo\n",
        })
        self.assertEqual(problems, [
            "ai-workflows/demo/demo/a.py:3: imports 'other' from component 'other'; "
            "components must not import each other's sources",
            "ai-workflows/demo/demo/a.py:4: imports 'requests', which component 'demo' does not declare "
            "in third_party_imports",
            "ai-workflows/other/x.py:1: imports 'demo' from component 'demo'; "
            "components must not import each other's sources",
        ])

    def test_unparseable_legacy_source_is_still_scanned(self):
        problems = self.check({"ai-workflows/other/old.py": "print 'python 2'\nfrom demo import x\n"})
        self.assertEqual(len(problems), 1)
        self.assertIn("old.py:2: imports 'demo'", problems[0])

    def test_source_must_have_exactly_one_owner(self):
        problems = self.check({"orphan.py": "import os\n"})
        self.assertEqual(problems, ["orphan.py: Python source must belong to exactly one component, found []"])

    def test_without_stdlib_list_only_boundaries_are_checked(self):
        files = {"ai-workflows/demo/demo/a.py": "import requests\nimport other\n"}
        with patch.object(workspace.sys, "stdlib_module_names", None, create=True):
            problems = self.check(files, stdlib=None)
        self.assertEqual(len(problems), 1)
        self.assertIn("from component 'other'", problems[0])


class WorkspaceCheckTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repo = FixtureRepo(self.folder.name)

    def test_fixture_passes(self):
        self.assertEqual(self.repo.problems(), [])

    def test_unregistered_project_directory_fails(self):
        self.repo.write("ai-workflows/stray/README.md", "Stray\n")
        self.assertIn(
            "ai-workflows/stray: directory under ai-workflows/ is not registered as a project in workspace.json",
            self.repo.problems())

    def test_project_layout_and_links_are_required(self):
        self.repo.write("README.md", "No links\n")
        self.repo.git("rm", "--quiet", "ai-workflows/demo/pyproject.toml")
        problems = self.repo.problems()
        self.assertIn("component 'demo': missing ai-workflows/demo/pyproject.toml", problems)
        self.assertIn("component 'demo': README.md must link ai-workflows/demo/README.md", problems)

    def test_workflow_filters_must_match_manifest(self):
        self.repo.write(".github/workflows/demo-ci.yml",
                        DEMO_WORKFLOW.replace('      - "workspace.json"\n', "", 1))
        problems = self.repo.problems()
        self.assertEqual(len(problems), 1)
        self.assertIn("on.pull_request.paths must be exactly", problems[0])

    def test_always_on_workflow_must_not_filter_paths(self):
        self.repo.write(".github/workflows/policy.yml", POLICY_WORKFLOW.replace(
            "    branches: [main]\n", "    branches: [main]\n    paths: ['tools/**']\n"))
        self.assertTrue(any("must not filter pull_request by path" in item for item in self.repo.problems()))

    def test_check_workflow_name_must_match(self):
        self.repo.write(".github/workflows/demo-ci.yml", DEMO_WORKFLOW.replace("name: Demo CI", "name: Renamed"))
        self.assertTrue(any("expects workflow 'Demo CI'" in item for item in self.repo.problems()))

    def test_workspace_trigger_requires_the_relevance_command(self):
        loaded = json.loads((self.repo.root / "workspace.json").read_text())
        loaded["components"]["tooling"]["ci"]["trigger"] = "workspace"
        self.repo.write("workspace.json", json.dumps(loaded))
        self.assertTrue(any("scripts/workspace.py github-changes --component tooling" in item
                            for item in self.repo.problems()))

    def test_declared_checks_must_be_reported_by_a_job(self):
        loaded = json.loads((self.repo.root / "workspace.json").read_text())
        loaded["components"]["demo"]["checks"] = [{"name": "demo tests", "workflow": "Demo CI"}]
        self.repo.write("workspace.json", json.dumps(loaded))
        self.assertEqual(self.repo.problems(), [
            "component 'demo': no job in .github/workflows/demo-ci.yml reports check 'demo tests' "
            "(jobs report ['demo test'])",
        ])

    def test_untracked_files_count_and_ignored_or_deleted_files_do_not(self):
        self.repo.write(".gitignore", "scratch/\n")
        self.repo.write("scratch/notes.py", "import requests\n")
        self.repo.write("stray.py", "import os\n")
        (self.repo.root / "tools/tool.py").unlink()
        files = workspace.workspace_files(self.repo.root)
        self.assertIn("stray.py", files)
        self.assertNotIn("scratch/notes.py", files)
        self.assertNotIn("tools/tool.py", files)
        problems = workspace.check_workspace(self.repo.root)
        self.assertIn("stray.py: Python source must belong to exactly one component, found []", problems)

    def test_missing_package_and_test_directory_fail(self):
        loaded = json.loads((self.repo.root / "workspace.json").read_text())
        loaded["components"]["demo"]["packages"] = ["missing"]
        loaded["components"]["demo"]["test"] = [{"run": "true", "cwd": "nowhere"}]
        self.repo.write("workspace.json", json.dumps(loaded))
        problems = self.repo.problems()
        self.assertIn("component 'demo': package 'missing' not found in ai-workflows/demo", problems)
        self.assertIn("component 'demo': test directory nowhere does not exist", problems)


class WorkflowCheckNameTests(unittest.TestCase):
    def names(self, jobs):
        return workspace.workflow_check_names("name: X\non: push\njobs:\n" + jobs)

    def test_job_names_and_single_key_matrices(self):
        self.assertEqual(self.names(
            "  plain:\n    runs-on: x\n    steps:\n      - name: Not a job name\n"
            "  named:\n    name: \"Named job\"\n"
            "  test:\n    strategy:\n      fail-fast: false\n      matrix:\n        python: [\"3.11\", \"3.13\"]\n"
            "  templated:\n    name: lint (${{ matrix.tool }})\n    strategy:\n      matrix:\n        tool:\n"
            "          - ruff\n          - mypy\n"), ({
                "plain", "Named job", "test (3.11)", "test (3.13)", "lint (ruff)", "lint (mypy)"}, []))

    def test_unmodelled_jobs_are_reported(self):
        cases = {
            "expression matrix": "  a:\n    strategy:\n      matrix: ${{ fromJSON(x) }}\n",
            "include": "  a:\n    strategy:\n      matrix:\n        include:\n          - v: 1\n",
            "two keys": "  a:\n    strategy:\n      matrix:\n        x: [1]\n        y: [2]\n",
            "name expression": "  a:\n    name: ${{ github.ref }}\n",
            "name without matrix key": "  a:\n    name: fixed\n    strategy:\n      matrix:\n        x: [1, 2]\n",
        }
        for label, jobs in cases.items():
            with self.subTest(label=label):
                names, problems = self.names(jobs + "  ok:\n    name: fine\n")
                self.assertEqual(names, {"fine"})
                self.assertEqual(len(problems), 1)
        self.assertEqual(workspace.workflow_check_names("name: X\non: push\n"), (set(), ["workflow has no jobs"]))

    def test_repository_workflows_report_their_declared_checks(self):
        loaded = workspace.load_manifest(ROOT)
        for name, component in loaded["components"].items():
            with self.subTest(component=name):
                text = (ROOT / component["ci"]["workflow"]).read_text(encoding="utf-8")
                names, problems = workspace.workflow_check_names(text)
                self.assertEqual(problems, [])
                self.assertLessEqual({check["name"] for check in component["checks"]}, names)


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repo = FixtureRepo(self.folder.name)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = workspace.main(["--root", str(self.repo.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_scaffolded_project_passes_check_and_tests(self):
        code, out, _ = self.run_main("new", "risk-score", "--summary", 'Risk "score" — ünïcode @NAME@')
        self.assertEqual(code, 0, out)
        self.assertIn("create .github/workflows/risk-score-ci.yml", out)
        self.assertEqual(self.repo.problems(), [])
        loaded = workspace.load_manifest(self.repo.root)
        self.assertEqual(list(loaded["components"]), ["demo", "risk-score", "tooling"])
        self.assertEqual(loaded["components"]["risk-score"]["packages"], ["risk_score"])
        self.assertEqual(workspace.required_checks(loaded, ["ai-workflows/risk-score/risk_score/__init__.py"]),
                         {"Policy", "risk-score (3.11)", "risk-score (3.13)"})
        workflow = (self.repo.root / ".github/workflows/risk-score-ci.yml").read_text()
        self.assertIn(f"actions/checkout@{'c' * 40} # v9", workflow)
        self.assertIn(f"actions/setup-python@{'5' * 40} # v8", workflow)
        self.assertIn("| [risk-score](ai-workflows/risk-score/README.md) |",
                      (self.repo.root / "README.md").read_text())
        self.assertTrue((self.repo.root / "ai-workflows/README.md").read_text().endswith(
            "| [`risk-score`](risk-score/README.md) | Risk \"score\" — ünïcode @NAME@ | `ai-workflows/risk-score/` |"
            "\n\nMore text.\n"))
        self.assertIn("\nRisk \"score\" — ünïcode @NAME@\n", (self.repo.root / "ai-workflows/risk-score/README.md").read_text())
        self.assertEqual(workspace.run_tests(self.repo.root, loaded, ["risk-score"], out=io.StringIO()), 0)

    def test_dry_run_and_rejected_requests_write_nothing(self):
        cases = [
            ("new", "risk-score", "--summary", "Risk", "--dry-run"),
            ("new", "Risk_Score", "--summary", "Risk"),
            ("new", "demo", "--summary", "Demo again"),
            ("new", "risk-score", "--summary", "Risk", "--package", "demo"),
            ("new", "risk-score", "--summary", "Risk", "--package", "risk-score"),
            ("new", "risk-score", "--summary", "Risk | score"),
            ("new", "risk-score", "--summary", "  "),
        ]
        if getattr(sys, "stdlib_module_names", None):
            cases.append(("new", "json-tools", "--summary", "JSON", "--package", "json"))
        for args in cases:
            with self.subTest(args=args):
                code, out, err = self.run_main(*args)
                self.assertEqual(code, 0 if "--dry-run" in args else 2, err)
                self.assertEqual(self.repo.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_failed_write_restores_the_previous_state(self):
        real_write = Path.write_text

        def failing_write(path, *args, **kwargs):
            if path.name == "risk-score-ci.yml":
                raise OSError("disk full")
            return real_write(path, *args, **kwargs)

        with patch.object(Path, "write_text", failing_write):
            code, _, err = self.run_main("new", "risk-score", "--summary", "Risk")
        self.assertEqual(code, 2)
        self.assertIn("disk full", err)
        self.assertEqual(self.repo.git("status", "--porcelain", "--untracked-files=all"), "")
        self.assertFalse((self.repo.root / "ai-workflows/risk-score").exists())

    def test_existing_paths_and_missing_tables_are_refused(self):
        self.repo.write("ai-workflows/risk-score/notes.md", "draft\n")
        code, _, err = self.run_main("new", "risk-score", "--summary", "Risk")
        self.assertEqual(code, 2)
        self.assertIn("ai-workflows/risk-score already exists", err)
        self.repo.write("README.md", "No project table; [Demo](ai-workflows/demo/README.md)\n")
        code, _, err = self.run_main("new", "pricing", "--summary", "Pricing")
        self.assertEqual(code, 2)
        self.assertIn("cannot find the project table in README.md", err)
        self.assertFalse((self.repo.root / "ai-workflows/pricing").exists())


class ChangeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repo = FixtureRepo(self.folder.name)
        self.base = self.repo.git("rev-parse", "HEAD")

    def test_committed_and_working_tree_changes(self):
        self.repo.git("mv", "tools/tool.py", "ai-workflows/demo/demo/tool.py")
        head = self.repo.commit_all("Move tool")
        self.assertEqual(workspace.changed_paths(self.repo.root, self.base, head),
                         ["ai-workflows/demo/demo/tool.py", "tools/tool.py"])
        self.repo.write("docs/new.md", "untracked\n")
        self.repo.write("ai-workflows/demo/README.md", "edited\n")
        self.assertEqual(workspace.changed_paths(self.repo.root, self.base), [
            "ai-workflows/demo/README.md", "ai-workflows/demo/demo/tool.py", "docs/new.md", "tools/tool.py"])

    def test_github_events(self):
        self.repo.write("ai-workflows/demo/demo/core.py", "import sys\n")
        head = self.repo.commit_all("Change demo")
        root = self.repo.root
        pull = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}
        self.assertEqual(workspace.github_changed_paths(root, "pull_request", pull),
                         ["ai-workflows/demo/demo/core.py"])
        self.assertEqual(workspace.github_changed_paths(root, "push", {"before": self.base, "after": head}),
                         ["ai-workflows/demo/demo/core.py"])
        self.assertIsNone(workspace.github_changed_paths(root, "push", {"before": "0" * 40, "after": head}))
        self.assertIsNone(workspace.github_changed_paths(root, "workflow_dispatch", {}))
        self.assertIsNone(workspace.github_changed_paths(root, "schedule", {}))
        with self.assertRaises(workspace.WorkspaceError):
            workspace.github_changed_paths(root, "push", {"before": "f" * 40, "after": head})

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = workspace.main(["--root", str(self.repo.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_github_changes_command_writes_job_output(self):
        self.repo.write("tools/tool.py", "import os\n")
        head = self.repo.commit_all("Change tooling")
        event = Path(self.folder.name) / "event.json"
        event.write_text(json.dumps({"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}))
        for name, expected in (("demo", "false"), ("tooling", "true")):
            with self.subTest(component=name):
                code, out, err = self.run_main("github-changes", "--component", name,
                                               "--event-name", "pull_request", "--event-path", str(event))
                self.assertEqual((code, out), (0, f"relevant={expected}\n"))
                self.assertIn(f"{name} validation required: {expected}", err)
        code, out, err = self.run_main("github-changes", "--component", "demo", "--event-name", "workflow_dispatch",
                                       "--event-path", "")
        self.assertEqual((code, out), (0, "relevant=true\n"))
        code, out, err = self.run_main("github-changes", "--component", "missing",
                                       "--event-name", "workflow_dispatch")
        self.assertEqual(code, 2)
        bad_event = Path(self.folder.name) / "bad.json"
        bad_event.write_text("{}")
        code, out, err = self.run_main("github-changes", "--component", "demo",
                                       "--event-name", "pull_request", "--event-path", str(bad_event))
        self.assertEqual((code, out), (2, ""))

    def test_affected_command_formats(self):
        self.repo.write("ai-workflows/demo/demo/core.py", "import sys\n")
        code, out, _ = self.run_main("affected", "--base", self.base, "--format", "json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {
            "paths": ["ai-workflows/demo/demo/core.py"], "components": ["demo"],
            "required_checks": ["Policy", "demo test"]})
        code, out, _ = self.run_main("affected", "--base", self.base, "--component", "tooling")
        self.assertEqual((code, out), (0, "false\n"))
        code, out, _ = self.run_main("affected", "--base", self.base, "--format", "markdown")
        self.assertIn("| `demo` | project | `ai-workflows/demo` | `demo test` |", out)
        listing = Path(self.folder.name) / "paths.txt"
        listing.write_text("tools/tool.py\0workspace.json\0")
        code, out, _ = self.run_main("affected", "--paths-from", str(listing))
        self.assertIn("Affected components: demo, tooling", out)


class TestCommandTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "a").mkdir()
        (self.root / "b").mkdir()
        self.manifest = manifest(
            passing=component(path="a", test=[
                {"run": "python3 -c \"import os, sys; sys.exit(os.environ['MODE'] != 'outer')\""},
                {"run": "python3 -c \"import os; open('ran', 'w').write(os.getcwd())\""},
            ], test_env={"MODE": "default"}),
            failing=component(path="b", packages=["b"], test=[
                {"run": "python3 -c \"raise SystemExit(3)\""},
                {"run": "python3 -c \"open('never', 'w')\""},
            ]),
        )

    def test_runs_steps_in_component_directories_and_reports_failures(self):
        out = io.StringIO()
        with patch.dict(os.environ, {"MODE": "outer"}):
            code = workspace.run_tests(self.root, self.manifest, ["passing", "failing"], out=out)
        self.assertEqual(code, 1)
        self.assertEqual(Path((self.root / "a/ran").read_text()).resolve(), (self.root / "a").resolve())
        self.assertFalse((self.root / "b/never").exists())
        self.assertIn("PASS passing", out.getvalue())
        self.assertIn("FAIL failing: 'python3 -c \"raise SystemExit(3)\"' exited 3", out.getvalue())

    def test_dry_run_and_missing_programs(self):
        out = io.StringIO()
        self.assertEqual(workspace.run_tests(self.root, self.manifest, ["failing"], dry_run=True, out=out), 0)
        self.assertIn("[failing] (b) $ python3 -c", out.getvalue())
        broken = manifest(missing=component(path="a", test=[{"run": "definitely-not-a-program-xyz"}]))
        out = io.StringIO()
        self.assertEqual(workspace.run_tests(self.root, broken, ["missing"], out=out), 1)
        self.assertIn("could not start", out.getvalue())

    def test_python3_runs_under_the_current_interpreter(self):
        plan = workspace.test_plan(self.root, self.manifest, ["passing"])
        self.assertEqual(plan[0][2][0], sys.executable)
        self.assertEqual(plan[0][1], self.root / "a")


if __name__ == "__main__":
    unittest.main()
