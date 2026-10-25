"""Notebook cleanup: CLI checks, retained content, layout, and tracked paths."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "notebooks.py"


class NotebookTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "example.ipynb"
        self.clean = {
            "cells": [
                {"cell_type": "code", "execution_count": None, "metadata": {},
                 "outputs": [], "source": ["print('café')\n"]},
                {"cell_type": "markdown", "metadata": {}, "source": ["# Notes\n"]},
                {"cell_type": "raw", "metadata": {}, "source": "raw text"},
            ],
            "metadata": {"kernelspec": {"name": "python3"},
                         "language_info": {"name": "python"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        self.dirty = copy.deepcopy(self.clean)
        self.dirty["cells"][0].update(
            execution_count=2,
            outputs=[{"output_type": "stream", "name": "stdout", "text": ["café\n"]}],
        )

    def run_cli(self, command, *paths, script=SCRIPT):
        return subprocess.run([sys.executable, str(script), command, *map(str, paths)],
                              cwd=self.root, capture_output=True, text=True)

    def write_notebook(self, notebook, indent=1, newline="\n", prefix=""):
        text = json.dumps(notebook, indent=indent, ensure_ascii=False,
                          **({"separators": (",", ":")} if indent is None else {}))
        line_ending = "\r\n" if newline == "\r\n" else "\n"
        text = text.replace("\n", line_ending + prefix) + newline
        self.path.write_bytes(text.encode("utf-8"))

    def test_check_lists_dirty_notebooks_and_passes_clean_ones(self):
        self.write_notebook(self.dirty)
        original = self.path.read_bytes()
        result = self.run_cli("check", self.path)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(str(self.path), result.stdout)
        self.assertEqual(self.path.read_bytes(), original)
        self.write_notebook(self.clean)
        self.assertEqual(self.run_cli("check", self.path).returncode, 0)

    def test_volatile_metadata_alone_is_dirty_and_is_removed(self):
        notebook = copy.deepcopy(self.clean)
        notebook["metadata"]["widgets"] = {"state": {"some-widget": {}}}
        notebook["cells"][0]["metadata"] = {
            "execution": {}, "collapsed": False, "scrolled": True, "ExecuteTime": {},
        }
        self.write_notebook(notebook)
        self.assertEqual(self.run_cli("check", self.path).returncode, 1)
        result = self.run_cli("strip", self.path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.path.read_bytes()), self.clean)
        self.assertEqual(self.run_cli("check", self.path).returncode, 0)

    def test_strip_preserves_sources_layout_and_is_idempotent(self):
        for indent, newline, prefix in [(1, "\n", ""), (2, "", ""), (4, "\n", ""),
                                       ("\t", "", ""), (None, "\n", ""), (1, "", "   "),
                                       (1, "\r\n", "")]:
            with self.subTest(indent=indent, newline=newline, prefix=prefix):
                self.write_notebook(self.clean, indent, newline, prefix)
                expected = self.path.read_bytes()
                self.write_notebook(self.dirty, indent, newline, prefix)
                result = self.run_cli("strip", self.path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.path.read_bytes(), expected)
                self.assertEqual(self.run_cli("check", self.path).returncode, 0)
                self.assertEqual(self.run_cli("strip", self.path).returncode, 0)
                self.assertEqual(self.path.read_bytes(), expected)

    def test_default_paths_include_only_tracked_notebooks_with_odd_names(self):
        (self.root / "scripts").mkdir()
        script = self.root / "scripts/notebooks.py"
        shutil.copyfile(SCRIPT, script)
        self.path = self.root / "odd \"name\"\n_é_.ipynb"
        self.write_notebook(self.dirty)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "add", "--", self.path.name], cwd=self.root, check=True)
        untracked = self.root / "untracked.ipynb"
        untracked.write_bytes(self.path.read_bytes())
        self.assertEqual(self.run_cli("check", script=script).returncode, 1)
        result = self.run_cli("strip", script=script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.path.read_bytes()), self.clean)
        self.assertEqual(json.loads(untracked.read_bytes()), self.dirty)
        self.assertEqual(self.run_cli("check", script=script).returncode, 0)


if __name__ == "__main__":
    unittest.main()
