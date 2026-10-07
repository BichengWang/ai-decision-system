#!/usr/bin/env python3
"""Monorepo workspace tool: components, affected changes, tests, and boundaries.

workspace.json at the repository root registers every component: where its
sources live, which changed paths affect it, which CI checks it needs, and how
to run its tests. This tool reads that manifest so the delivery controller, CI
routing, and local commands share one definition of each component.

Commands:
  list            Show registered components.
  affected        Show the components and CI checks a change affects.
  test            Run component test commands from their own directories.
  check           Verify the manifest, CI routing, project layout, and import boundaries.
  github-changes  Print `relevant=true|false` for one component in a GitHub Actions job.

Standard library only; Python 3.9 or newer. `check` needs Python 3.10+ for the
standard-library module list and skips the undeclared-import rule without it.
"""

import argparse
import ast
import json
import os
import re
import shlex
import subprocess
import sys
from functools import lru_cache
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "workspace.json"
PROJECTS_DIR = "ai-workflows"
KINDS = {"project", "legacy", "tooling"}
TRIGGERS = {"paths", "workspace", "always"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# GitHub path-filter syntax that this matcher does not model. Rejecting it keeps
# local matching identical to the workflow filters it is compared with.
UNSUPPORTED_GLOB = set("?[]!+{}\\")
COMPONENT_KEYS = {
    "kind", "path", "summary", "sources", "packages", "third_party_imports",
    "paths", "ci", "checks", "test", "test_env",
}
REQUIRED_COMPONENT_KEYS = COMPONENT_KEYS - {"test_env"}


class WorkspaceError(RuntimeError):
    pass


class ManifestError(ValueError):
    pass


# Manifest ------------------------------------------------------------------

def load_manifest(root=ROOT):
    """Read and structurally validate workspace.json; raise ManifestError if invalid."""
    path = Path(root) / MANIFEST
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except json.JSONDecodeError as error:
        raise ManifestError(f"{MANIFEST} is not valid JSON: {error}") from error
    problems = validate(manifest)
    if problems:
        raise ManifestError(f"{MANIFEST} is invalid: " + "; ".join(problems))
    return manifest


def pattern_problem(pattern):
    if not isinstance(pattern, str) or not pattern:
        return "must be a non-empty string"
    if pattern.startswith("/") or "//" in pattern or ".." in pattern.split("/"):
        return "must be a normalized repository-relative path"
    if UNSUPPORTED_GLOB & set(pattern):
        return "may use only '*' and a trailing '/**'"
    if "**" in pattern.replace("/**", "", 1) or ("/**" in pattern and not pattern.endswith("/**")):
        return "may use '**' only as its final '/**' segment"
    return None


def _relative_dir_problem(value):
    if not isinstance(value, str) or not value:
        return "must be a non-empty string"
    if value == ".":
        return None
    if value.startswith("/") or value.endswith("/") or "//" in value or {".", ".."} & set(value.split("/")):
        return "must be a normalized repository-relative directory"
    return None


def _check_list(problems, where, value, item_problem, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        problems.append(f"{where} must be a {'' if allow_empty else 'non-empty '}list")
        return
    if len(set(map(json.dumps, value))) != len(value):
        problems.append(f"{where} has duplicate entries")
    for item in value:
        problem = item_problem(item)
        if problem:
            problems.append(f"{where} entry {item!r} {problem}")


def _identifier_problem(value):
    if not isinstance(value, str) or not IDENTIFIER_RE.match(value):
        return "must be a Python identifier"
    return None


def _check_problem(value):
    if (not isinstance(value, dict) or set(value) != {"name", "workflow"}
            or not all(isinstance(value[key], str) and value[key] for key in value)):
        return "must be an object with non-empty 'name' and 'workflow'"
    return None


def _test_problem(value):
    if not isinstance(value, dict) or not set(value) <= {"run", "cwd"} or "run" not in value:
        return "must be an object with 'run' and optional 'cwd'"
    if not isinstance(value["run"], str) or not value["run"].strip():
        return "must have a non-empty 'run' command"
    try:
        shlex.split(value["run"])
    except ValueError as error:
        return f"has an unparseable command: {error}"
    if "cwd" in value:
        problem = _relative_dir_problem(value["cwd"])
        if problem:
            return f"'cwd' {problem}"
    return None


def validate(manifest):
    """Return structural problems in a manifest without touching the filesystem."""
    problems = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    expected = {"schema_version", "description", "global_paths", "always_required_checks", "components"}
    if set(manifest) != expected:
        return [f"top-level keys must be exactly {sorted(expected)}"]
    if manifest["schema_version"] != 1:
        problems.append("schema_version must be 1")
    _check_list(problems, "global_paths", manifest["global_paths"], pattern_problem)
    _check_list(problems, "always_required_checks", manifest["always_required_checks"], _check_problem)
    components = manifest["components"]
    if not isinstance(components, dict) or not components:
        return problems + ["components must be a non-empty object"]
    workflows_by_check = {}
    owners_by_package = {}
    for check in manifest["always_required_checks"]:
        if not _check_problem(check):
            workflows_by_check.setdefault(check["name"], set()).add(check["workflow"])
    for name, component in components.items():
        where = f"component {name!r}"
        if not NAME_RE.match(name):
            problems.append(f"{where} name must use lowercase letters, digits, and hyphens")
        if not isinstance(component, dict):
            problems.append(f"{where} must be an object")
            continue
        missing = REQUIRED_COMPONENT_KEYS - set(component)
        unknown = set(component) - COMPONENT_KEYS
        if missing or unknown:
            problems.append(f"{where} is missing {sorted(missing)} or has unknown keys {sorted(unknown)}")
            continue
        if component["kind"] not in KINDS:
            problems.append(f"{where} kind must be one of {sorted(KINDS)}")
        problem = _relative_dir_problem(component["path"])
        if problem:
            problems.append(f"{where} path {problem}")
        if not isinstance(component["summary"], str) or not component["summary"].strip():
            problems.append(f"{where} summary must be a non-empty string")
        _check_list(problems, f"{where} sources", component["sources"], pattern_problem)
        _check_list(problems, f"{where} paths", component["paths"], pattern_problem)
        _check_list(problems, f"{where} packages", component["packages"], _identifier_problem, allow_empty=True)
        if component["third_party_imports"] is not None:
            _check_list(problems, f"{where} third_party_imports", component["third_party_imports"],
                        _identifier_problem, allow_empty=True)
        ci = component["ci"]
        if (not isinstance(ci, dict) or set(ci) != {"workflow", "trigger"}
                or ci.get("trigger") not in TRIGGERS or pattern_problem(ci.get("workflow"))
                or not str(ci.get("workflow")).startswith(".github/workflows/")):
            problems.append(f"{where} ci must name a .github/workflows file and a trigger in {sorted(TRIGGERS)}")
        _check_list(problems, f"{where} checks", component["checks"], _check_problem)
        _check_list(problems, f"{where} test", component["test"], _test_problem)
        env = component.get("test_env", {})
        if not isinstance(env, dict) or not all(
                isinstance(key, str) and key and isinstance(value, str) for key, value in env.items()):
            problems.append(f"{where} test_env must map variable names to strings")
        if isinstance(component["checks"], list):
            for check in component["checks"]:
                if not _check_problem(check):
                    workflows_by_check.setdefault(check["name"], set()).add(check["workflow"])
        if isinstance(component["packages"], list):
            for package in component["packages"]:
                owners_by_package.setdefault(package, []).append(name)
    for check, workflows in sorted(workflows_by_check.items()):
        if len(workflows) > 1:
            problems.append(f"check {check!r} is attributed to several workflows: {sorted(workflows)}")
    for package, owners in sorted(owners_by_package.items()):
        if len(owners) > 1:
            problems.append(f"package {package!r} is claimed by several components: {owners}")
    return problems


# Path matching and affected components -------------------------------------

@lru_cache(maxsize=None)
def _pattern_regex(pattern):
    body, tail = (pattern[:-3], "/.*") if pattern.endswith("/**") else (pattern, "")
    regex = "".join("[^/]*" if char == "*" else re.escape(char) for char in body)
    return re.compile(regex + tail + r"\Z", re.S)


def matches(pattern, path):
    """Match like a GitHub path filter restricted to '*' and a trailing '/**'."""
    return _pattern_regex(pattern).match(path) is not None


def matches_any(patterns, path):
    return any(matches(pattern, path) for pattern in patterns)


def affected_components(manifest, paths):
    """Return component names, in manifest order, that the changed paths affect.

    A change to a global path (the manifest itself) affects every component.
    """
    paths = [path for path in paths if path]
    components = manifest["components"]
    if any(matches_any(manifest["global_paths"], path) for path in paths):
        return list(components)
    return [
        name for name, component in components.items()
        if any(matches_any(component["paths"], path) for path in paths)
    ]


def required_checks(manifest, paths):
    """Return CI check names a change must pass before merging."""
    checks = {check["name"] for check in manifest["always_required_checks"]}
    for name in affected_components(manifest, paths):
        checks.update(check["name"] for check in manifest["components"][name]["checks"])
    return checks


def check_workflows(manifest):
    """Map each declared check name to the workflow that must report it."""
    mapping = {check["name"]: check["workflow"] for check in manifest["always_required_checks"]}
    for component in manifest["components"].values():
        mapping.update({check["name"]: check["workflow"] for check in component["checks"]})
    return mapping


# Git -----------------------------------------------------------------------

def git(root, *args):
    result = subprocess.run(
        ["git", "-C", str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise WorkspaceError(f"git {' '.join(args[:2])} failed: {message}")
    return result.stdout.decode()


def _split_z(output):
    return [item for item in output.split("\0") if item]


def tracked_files(root):
    return _split_z(git(root, "ls-files", "-z"))


def changed_paths(root, base, head=None):
    """Paths changed since the merge base of `base`.

    With `head`, compare committed history (`base...head`). Without it, compare the
    merge base with the working tree and include untracked, non-ignored files.
    Renames are listed as a deletion and an addition so both sides count.
    """
    if head:
        return sorted(set(_split_z(git(root, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}"))))
    merge_base = git(root, "merge-base", base, "HEAD").strip()
    changed = _split_z(git(root, "diff", "--name-only", "--no-renames", "-z", merge_base))
    untracked = _split_z(git(root, "ls-files", "-z", "--others", "--exclude-standard"))
    return sorted(set(changed) | set(untracked))


def github_changed_paths(root, event_name, event):
    """Return paths a GitHub event changed, or None when every component must run.

    Pull requests compare the merge base with the head; pushes compare the previous
    and new tip. Manual runs, new branches, and other events validate everything.
    """
    if event_name not in {"pull_request", "push"}:
        return None
    pull_request = event.get("pull_request")
    base = pull_request["base"]["sha"] if pull_request else event["before"]
    head = pull_request["head"]["sha"] if pull_request else event["after"]
    if not base.strip("0"):
        return None
    revision = f"{base}...{head}" if pull_request else f"{base}..{head}"
    return _split_z(git(root, "diff", "--name-only", "--no-renames", "-z", revision))


# Minimal workflow reading ---------------------------------------------------

def _strip_comment(line):
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index].rstrip()
    return line.rstrip()


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _yaml_lines(text):
    lines = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if line.strip():
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    return lines


def _mapping_entry(lines, key):
    """Find `key` among the shallowest entries of a block; return (value, body) or None."""
    if not lines:
        return None
    base = min(indent for indent, _ in lines)
    for index, (indent, content) in enumerate(lines):
        if indent == base and (content == f"{key}:" or content.startswith(f"{key}: ")):
            body = []
            for child_indent, child in lines[index + 1:]:
                if child_indent <= base:
                    break
                body.append((child_indent, child))
            return content[len(key) + 1:].strip(), body
    return None


def _sequence(value, body):
    if value.startswith("[") and value.endswith("]"):
        return [_unquote(item) for item in value[1:-1].split(",") if item.strip()]
    if value:
        raise WorkspaceError(f"unsupported YAML sequence value {value!r}")
    items = []
    for _, content in body:
        if not content.startswith("- "):
            raise WorkspaceError(f"unsupported YAML sequence entry {content!r}")
        items.append(_unquote(content[2:]))
    return items


def read_workflow(text):
    """Return a workflow's name and, per event, its `paths`/`paths-ignore` filters.

    This reads only the block-style YAML subset used by this repository's workflows.
    """
    lines = _yaml_lines(text)
    top = [(indent, content) for indent, content in lines if indent == 0]
    name_entry = _mapping_entry(top, "name")
    name = _unquote(name_entry[0]) if name_entry else None
    on_entry = _mapping_entry(lines, "on")
    if on_entry is None:
        raise WorkspaceError("workflow has no 'on' triggers")
    value, body = on_entry
    events = {}
    if value:
        for event in _sequence(value, []) if value.startswith("[") else [value]:
            events[_unquote(event)] = {}
        return {"name": name, "events": events}
    if not body:
        raise WorkspaceError("workflow has an empty 'on' block")
    base = min(indent for indent, _ in body)
    for indent, content in body:
        if indent == base:
            event = content.split(":", 1)[0].strip()
            entry = _mapping_entry(body, event)
            filters = {}
            for key in ("paths", "paths-ignore"):
                found = _mapping_entry(entry[1], key) if entry and entry[1] else None
                if found:
                    filters[key] = _sequence(*found)
            events[event] = filters
    return {"name": name, "events": events}


# Import boundaries ---------------------------------------------------------

def import_roots(source, filename="<source>"):
    """Yield (line, top-level module) for absolute imports in Python source.

    Files that do not parse (legacy material) fall back to a line scan.
    """
    try:
        tree = ast.parse(source, filename)
    except SyntaxError:
        pattern = re.compile(r"^\s*(?:from\s+([A-Za-z_]\w*)[\w.]*\s+import\b|import\s+([A-Za-z_]\w*))")
        for number, line in enumerate(source.splitlines(), 1):
            match = pattern.match(line)
            if match:
                yield number, match.group(1) or match.group(2)
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.split(".")[0]


def source_owners(manifest, path):
    return [name for name, component in manifest["components"].items()
            if matches_any(component["sources"], path)]


def import_problems(root, manifest, files, stdlib=None):
    """Check that each Python file belongs to one component and respects its boundaries."""
    if stdlib is None:
        stdlib = getattr(sys, "stdlib_module_names", None)
    components = manifest["components"]
    package_owner = {
        package: name for name, component in components.items() for package in component["packages"]
    }
    problems = []
    for path in files:
        if not path.endswith(".py"):
            continue
        owners = source_owners(manifest, path)
        if len(owners) != 1:
            problems.append(f"{path}: Python source must belong to exactly one component, found {owners}")
            continue
        owner = owners[0]
        component = components[owner]
        allowed = component["third_party_imports"]
        try:
            source = (Path(root) / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            problems.append(f"{path}: cannot read source: {error}")
            continue
        for line, module in import_roots(source, path):
            other = package_owner.get(module)
            if other and other != owner:
                problems.append(
                    f"{path}:{line}: imports {module!r} from component {other!r}; "
                    "components must not import each other's sources"
                )
            elif (other is None and allowed is not None and stdlib is not None
                  and module not in stdlib and module not in allowed):
                problems.append(
                    f"{path}:{line}: imports {module!r}, which component {owner!r} does not declare "
                    "in third_party_imports"
                )
    return problems


# Workspace check -----------------------------------------------------------

def _workflow_problems(root, name, component, global_paths):
    workflow_path = component["ci"]["workflow"]
    try:
        text = (Path(root) / workflow_path).read_text(encoding="utf-8")
        workflow = read_workflow(text)
    except (OSError, WorkspaceError) as error:
        return [f"component {name!r}: cannot read {workflow_path}: {error}"]
    problems = []
    for check in component["checks"]:
        if workflow["name"] != check["workflow"]:
            problems.append(
                f"component {name!r}: check {check['name']!r} expects workflow {check['workflow']!r}, "
                f"but {workflow_path} is named {workflow['name']!r}"
            )
    trigger = component["ci"]["trigger"]
    events = workflow["events"]
    if "pull_request" not in events:
        problems.append(f"component {name!r}: {workflow_path} must run on pull_request")
    if trigger == "paths":
        expected = sorted(component["paths"] + global_paths)
        for event in ("pull_request", "push"):
            filters = events.get(event, {})
            if "paths-ignore" in filters or sorted(filters.get("paths", [])) != expected:
                problems.append(
                    f"component {name!r}: {workflow_path} on.{event}.paths must be exactly the "
                    f"component paths plus global paths: {expected}"
                )
    else:
        for event in ("pull_request", "push"):
            if events.get(event):
                problems.append(
                    f"component {name!r}: {workflow_path} must not filter {event} by path "
                    f"(trigger {trigger!r} runs on every change)"
                )
        command = f"scripts/workspace.py github-changes --component {name}"
        if trigger == "workspace" and command not in text:
            problems.append(f"component {name!r}: {workflow_path} must decide relevance with `{command}`")
    return problems


def check_workspace(root=ROOT, manifest=None):
    """Return every problem with the manifest, layout, CI routing, and imports."""
    root = Path(root)
    manifest = manifest if manifest is not None else load_manifest(root)
    files = tracked_files(root)
    tracked = set(files)
    problems = []
    components = manifest["components"]
    readme = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").exists() else ""
    workspace_readme_path = root / PROJECTS_DIR / "README.md"
    workspace_readme = workspace_readme_path.read_text(encoding="utf-8") if workspace_readme_path.exists() else ""

    project_dirs = {
        "/".join(path.split("/")[:2]) for path in files
        if path.startswith(f"{PROJECTS_DIR}/") and path.count("/") >= 2
    }
    registered = {component["path"] for component in components.values() if component["kind"] == "project"}
    for directory in sorted(project_dirs - registered):
        problems.append(f"{directory}: directory under {PROJECTS_DIR}/ is not registered as a project in {MANIFEST}")

    for name, component in components.items():
        path = component["path"]
        if not (root / path).is_dir():
            problems.append(f"component {name!r}: path {path} does not exist")
            continue
        if not any(matches_any(component["sources"], file) for file in files):
            problems.append(f"component {name!r}: sources match no tracked file")
        for package in component["packages"]:
            if not ((root / path / package / "__init__.py").is_file() or (root / path / f"{package}.py").is_file()):
                problems.append(f"component {name!r}: package {package!r} not found in {path}")
        for step in component["test"]:
            if not (root / step.get("cwd", path)).is_dir():
                problems.append(f"component {name!r}: test directory {step.get('cwd', path)} does not exist")
        if component["kind"] == "project":
            parts = PurePosixPath(path).parts
            if len(parts) != 2 or parts[0] != PROJECTS_DIR:
                problems.append(f"component {name!r}: projects must live directly under {PROJECTS_DIR}/")
                continue
            own = f"{path}/**"
            for key in ("paths", "sources"):
                if own not in component[key]:
                    problems.append(f"component {name!r}: {key} must include {own!r}")
            for required in ("README.md", "pyproject.toml"):
                if f"{path}/{required}" not in tracked:
                    problems.append(f"component {name!r}: missing tracked {path}/{required}")
            if not any(file.startswith(f"{path}/tests/") for file in files):
                problems.append(f"component {name!r}: missing tracked tests under {path}/tests/")
            if f"]({path}/README.md)" not in readme:
                problems.append(f"component {name!r}: README.md must link {path}/README.md")
            if f"]({parts[1]}/README.md)" not in workspace_readme:
                problems.append(f"component {name!r}: {PROJECTS_DIR}/README.md must link {parts[1]}/README.md")
        problems.extend(_workflow_problems(root, name, component, manifest["global_paths"]))

    declared = {check["name"] for component in components.values() for check in component["checks"]}
    for check in manifest["always_required_checks"]:
        if check["name"] not in declared:
            problems.append(f"always-required check {check['name']!r} is not reported by any component's workflow")

    problems.extend(import_problems(root, manifest, files))
    return problems


# Tests ---------------------------------------------------------------------

def test_plan(root, manifest, names):
    """Return (component, cwd, argv, env overrides, command text) for each test step."""
    plan = []
    for name in names:
        component = manifest["components"][name]
        for step in component["test"]:
            argv = shlex.split(step["run"])
            if argv[0] == "python3":
                argv[0] = sys.executable
            cwd = Path(root) / step.get("cwd", component["path"])
            plan.append((name, cwd, argv, component.get("test_env", {}), step["run"]))
    return plan


def run_tests(root, manifest, names, dry_run=False, out=sys.stdout):
    results = {}
    for name, cwd, argv, env_defaults, command in test_plan(root, manifest, names):
        if results.get(name):
            continue
        relative = os.path.relpath(cwd, root)
        print(f"[{name}] ({relative}) $ {command}", file=out, flush=True)
        if dry_run:
            continue
        env = dict(env_defaults)
        env.update(os.environ)
        try:
            code = subprocess.call(argv, cwd=cwd, env=env)
        except OSError as error:
            results[name] = f"{command!r} could not start: {error}"
            continue
        if code:
            results[name] = f"{command!r} exited {code}"
    if not dry_run:
        print(file=out)
        for name in names:
            print(f"{'FAIL' if results.get(name) else 'PASS'} {name}"
                  + (f": {results[name]}" if results.get(name) else ""), file=out)
    return 1 if any(results.values()) else 0


# CLI -----------------------------------------------------------------------

def _paths_from(source):
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    separator = "\0" if "\0" in text else "\n"
    return [item.strip() for item in text.split(separator) if item.strip()]


def _resolve_paths(args, root):
    if args.paths_from:
        label = "stdin" if args.paths_from == "-" else args.paths_from
        return _paths_from(args.paths_from), f"paths from {label}"
    if args.head:
        return changed_paths(root, args.base, args.head), f"{args.base}...{args.head}"
    return changed_paths(root, args.base), f"merge base with {args.base} vs. working tree"


def command_list(args, root, manifest):
    components = manifest["components"]
    if args.format == "json":
        print(json.dumps(components, indent=2))
        return 0
    rows = [("NAME", "KIND", "PATH", "CHECKS")] + [
        (name, component["kind"], component["path"], ", ".join(check["name"] for check in component["checks"]))
        for name, component in components.items()
    ]
    widths = [max(len(row[index]) for row in rows) for index in range(3)]
    for row in rows:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row[:3])) + "  " + row[3])
    return 0


def command_affected(args, root, manifest):
    paths, source = _resolve_paths(args, root)
    names = affected_components(manifest, paths)
    checks = sorted(required_checks(manifest, paths))
    if args.component:
        if args.component not in manifest["components"]:
            raise WorkspaceError(f"unknown component {args.component!r}")
        print(str(args.component in names).lower())
    elif args.format == "json":
        print(json.dumps({"paths": paths, "components": names, "required_checks": checks}, indent=2))
    elif args.format == "markdown":
        print("### Affected workspace components\n")
        print(f"{len(paths)} changed path(s) ({source}).\n")
        print("| Component | Kind | Path | Required checks |\n| --- | --- | --- | --- |")
        for name in names:
            component = manifest["components"][name]
            listed = ", ".join(f"`{check['name']}`" for check in component["checks"])
            print(f"| `{name}` | {component['kind']} | `{component['path']}` | {listed} |")
        if not names:
            print("| _none_ | | | |")
        always = ", ".join(f"`{check['name']}`" for check in manifest["always_required_checks"])
        print(f"\nAlways required: {always}")
    else:
        print(f"Changed paths: {len(paths)} ({source})")
        print(f"Affected components: {', '.join(names) or 'none'}")
        print(f"Required checks: {', '.join(checks)}")
    return 0


def command_test(args, root, manifest):
    components = manifest["components"]
    if args.all:
        names = list(components)
    elif args.affected:
        paths, _ = _resolve_paths(args, root)
        names = affected_components(manifest, paths)
        if not names:
            print("No component is affected; nothing to test.")
            return 0
    else:
        names = args.components
        if not names:
            raise WorkspaceError("name components to test, or pass --all or --affected")
    unknown = [name for name in names if name not in components]
    if unknown:
        raise WorkspaceError(f"unknown component(s): {', '.join(unknown)}")
    return run_tests(root, manifest, names, dry_run=args.dry_run)


def command_check(args, root, manifest):
    problems = check_workspace(root, manifest)
    if getattr(sys, "stdlib_module_names", None) is None:
        print("note: Python 3.10+ is needed to check undeclared third-party imports; skipped", file=sys.stderr)
    if problems:
        print(f"Workspace check found {len(problems)} problem(s):")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Workspace check passed: {len(manifest['components'])} components.")
    return 0


def command_github_changes(args, root, manifest):
    if args.component not in manifest["components"]:
        raise WorkspaceError(f"unknown component {args.component!r}")
    event_name = args.event_name or os.environ.get("GITHUB_EVENT_NAME", "")
    event_path = args.event_path or os.environ.get("GITHUB_EVENT_PATH", "")
    event = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
    paths = github_changed_paths(root, event_name, event)
    relevant = paths is None or args.component in affected_components(manifest, paths)
    print(f"{args.component} validation required: {str(relevant).lower()}", file=sys.stderr)
    print(f"relevant={str(relevant).lower()}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="show registered components")
    listing.add_argument("--format", choices=("text", "json"), default="text")

    def add_change_source(command):
        command.add_argument("--base", default="origin/main", help="base revision (default: origin/main)")
        command.add_argument("--head", help="compare base...HEAD-REVISION instead of the working tree")
        command.add_argument("--paths-from", metavar="FILE",
                             help="read changed paths (newline or NUL separated) from FILE, or '-' for stdin")

    affected = sub.add_parser("affected", help="show components and checks a change affects")
    add_change_source(affected)
    affected.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    affected.add_argument("--component", help="print only true or false for this component")

    test = sub.add_parser("test", help="run component tests from their own directories")
    test.add_argument("components", nargs="*")
    test.add_argument("--all", action="store_true", help="test every component")
    test.add_argument("--affected", action="store_true", help="test components affected by a change")
    test.add_argument("--dry-run", action="store_true", help="print commands without running them")
    add_change_source(test)

    sub.add_parser("check", help="verify the manifest, CI routing, layout, and import boundaries")

    github = sub.add_parser("github-changes", help="print relevant=true|false for a GitHub Actions job")
    github.add_argument("--component", required=True)
    github.add_argument("--event-name", help="default: $GITHUB_EVENT_NAME")
    github.add_argument("--event-path", help="default: $GITHUB_EVENT_PATH")
    return parser


COMMANDS = {
    "list": command_list,
    "affected": command_affected,
    "test": command_test,
    "check": command_check,
    "github-changes": command_github_changes,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        manifest = load_manifest(root)
        return COMMANDS[args.command](args, root, manifest)
    except (ManifestError, WorkspaceError, OSError, KeyError, ValueError) as error:
        print(f"workspace: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
