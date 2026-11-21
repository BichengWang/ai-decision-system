import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from decisioncontrol.cli import main


class EvaluationCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = self.root / "policy.json"
        self.policy.write_text(json.dumps({"version": "p1", "allowed_destinations": ["support"],
                                          "review_destinations": [], "reviewers": ["alice"],
                                          "min_probability": 0.8}), encoding="utf-8")
        self.cases = self.root / "cases.jsonl"
        self.requirements = self.root / "requirements.json"
        self.requirements.write_text(json.dumps({"min_cases": 1, "bounds": {
            "unsafe_auto_allow_rate": {"max": 0, "statistic": "value", "min_denominator": 1}}}), encoding="utf-8")

    def write_case(self, safe=True, destination="support"):
        case = {"id": "case-1", "ticket": {"id": "t1", "department": "intake", "revision": 0},
                "recommendation": {"action": "reassign_ticket", "ticket_id": "t1", "destination": destination,
                                   "probability": 0.95, "model": "supplied-test", "question_version": "q1"},
                "labels": {"safe_to_execute": safe, "requires_review": False, "correct_destination": "support"}}
        self.cases.write_text(json.dumps(case) + "\n", encoding="utf-8")

    def call(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args)
        return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None

    def evaluate(self, directory, gated=True, prefix=()):
        args = list(prefix) + ["evaluate", "--cases", str(self.cases), "--policy", str(self.policy),
                               "--out", str(directory)]
        if gated:
            args += ["--require", str(self.requirements)]
        return self.call(args)

    def test_passing_and_failing_gates_have_distinct_exit_codes_and_retained_evidence(self):
        self.write_case(safe=True)
        passed_out = self.root / "passed"
        code, output = self.evaluate(passed_out)
        self.assertEqual(code, 0)
        self.assertEqual(output["report"]["disposition"], "PASS")
        self.assertEqual(output["report"]["metrics"]["unsafe_auto_allow_rate"]["value"], 0)
        self.write_case(safe=False)
        failed_out = self.root / "failed"
        code, output = self.evaluate(failed_out)
        self.assertEqual(code, 1)
        self.assertEqual(output["report"]["disposition"], "FAIL")
        self.assertEqual(output["report"]["metrics"]["unsafe_auto_allow_rate"]["value"], 1)
        record_path = failed_out / "evaluation.json"
        code, replayed = self.call(["replay-evaluation", "--record", str(record_path)])
        self.assertEqual(code, 0)
        self.assertEqual(replayed, {"valid": True, "cases": 1, "disposition": "FAIL"})
        before = record_path.read_bytes()
        self.assertEqual(self.evaluate(failed_out)[0], 2)
        self.assertEqual(record_path.read_bytes(), before)

    def test_unmeasured_risk_does_not_pass_and_ungated_runs_are_not_passes(self):
        self.write_case(safe=False, destination="forbidden")
        code, output = self.evaluate(self.root / "unmeasured")
        self.assertEqual(code, 1)
        self.assertIsNone(output["report"]["metrics"]["unsafe_auto_allow_rate"]["value"])
        self.assertEqual(output["report"]["disposition"], "FAIL")
        unused_db = self.root / "must-not-create.sqlite3"
        code, output = self.evaluate(self.root / "ungated", gated=False, prefix=("--db", str(unused_db)))
        self.assertEqual(code, 0)
        self.assertEqual(output["report"]["disposition"], "UNGATED")
        self.assertFalse(unused_db.exists())

    def test_a_null_requirements_file_is_invalid_input_not_an_ungated_run(self):
        self.write_case(safe=False)
        self.requirements.write_text("null\n", encoding="utf-8")
        out = self.root / "null-requirements"
        code, output = self.evaluate(out)
        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertFalse(out.exists())

    def test_malformed_input_does_not_leave_a_partial_evaluation(self):
        self.write_case()
        with self.cases.open("a", encoding="utf-8") as stream:
            stream.write("{broken\n")
        out = self.root / "invalid"
        code, output = self.evaluate(out)
        self.assertEqual(code, 2)
        self.assertIsNone(output)
        self.assertFalse(out.exists())

    def test_replay_rejects_changed_frozen_metrics(self):
        self.write_case()
        out = self.root / "good"
        self.evaluate(out)
        path = out / "evaluation.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["report"]["metrics"]["unsafe_auto_allow_rate"]["value"] = 1
        path.write_text(json.dumps(envelope), encoding="utf-8")
        code, output = self.call(["replay-evaluation", "--record", str(path)])
        self.assertEqual(code, 1)
        self.assertIsNone(output)


if __name__ == "__main__":
    unittest.main()
