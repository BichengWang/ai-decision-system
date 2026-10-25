#!/usr/bin/env python3
"""Keep committed notebooks free of outputs and volatile execution metadata.

strip rewrites notebooks in place; check lists notebooks that need stripping.
Paths default to every tracked *.ipynb in the repository. Standard library only,
Python 3.11+. Exit codes: 0 clean/stripped, 1 check found dirty notebooks, 2 error.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_VOLATILE_KEYS = ("widgets",)
CELL_VOLATILE_KEYS = ("execution", "collapsed", "scrolled", "ExecuteTime")


def tracked_notebooks():
    """Return tracked paths without splitting whitespace or Git-quoted names."""
    result = subprocess.run(["git", "ls-files", "-z", "*.ipynb"], cwd=ROOT,
                            check=True, capture_output=True)
    return [ROOT / os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def clean_notebook(notebook):
    """Remove volatile fields in place and return whether anything changed."""
    changed = False
    metadata = notebook.get("metadata", {})
    for key in NOTEBOOK_VOLATILE_KEYS:
        if key in metadata:
            del metadata[key]
            changed = True
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") == "code":
            for key, value in (("outputs", []), ("execution_count", None)):
                if key not in cell or cell[key] != value:
                    cell[key] = value
                    changed = True
        metadata = cell.get("metadata", {})
        for key in CELL_VOLATILE_KEYS:
            if key in metadata:
                del metadata[key]
                changed = True
    return changed


def serialize(notebook, original):
    """Retain indentation, compact layout, line endings, and final newline."""
    lines = original.splitlines()
    # Some notebooks have an extra margin on every line after the opening brace.
    prefixes = [re.match(r"[ \t]*", line)[0] for line in lines[1:] if line.strip()]
    margin = min(prefixes, key=len, default="")
    while any(not prefix.startswith(margin) for prefix in prefixes):
        margin = margin[:-1]
    match = re.search(r"^([ \t]+)\S", "\n".join(line[len(margin):] for line in lines[1:]),
                      re.MULTILINE)
    indent = match[1] if match else None
    options = {"indent": indent, "ensure_ascii": False}
    if indent is None:
        options["separators"] = (",", ":")
    text = json.dumps(notebook, **options)
    text = text.replace("\n", "\n" + margin)
    newline = "\r\n" if "\r\n" in original else "\n"
    text = text.replace("\n", newline)
    if original.endswith("\n"):
        text += newline
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("strip", "strip outputs in place"),
                            ("check", "list notebooks that are not clean")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("paths", metavar="PATH", nargs="*", type=Path,
                             help="notebook files (default: all tracked notebooks)")
    args = parser.parse_args(argv)
    dirty = False
    try:
        paths = args.paths or tracked_notebooks()
        for path in paths:
            original = path.read_bytes().decode("utf-8")
            notebook = json.loads(original)
            if clean_notebook(notebook):
                dirty = True
                if args.command == "strip":
                    path.write_bytes(serialize(notebook, original).encode("utf-8"))
                print(path)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if args.command == "check" and dirty else 0


if __name__ == "__main__":
    sys.exit(main())
