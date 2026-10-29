import base64
import hashlib
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from jevdecision import Noul
from jevdecision.answers import NoulAnswer, RefusalAnswer
from jevdecision.calibration import apply_map, fit, fit_isotonic, fit_platt, load
from jevdecision.errors import DatasetError
from jevdecision.evaluation import Case, main as eval_main, score_answers
from jevdecision.verify import main as verify_main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
QUESTIONS_FILE = EXAMPLES / "support-ticket.json"
REFUND = Noul("refund", "Is the customer asking for a refund?")
PRODUCER = {"name": "jevdecision", "version": "test"}
BASIS = {"cases_sha256": "0" * 64, "responses_sha256": "1" * 64, "case_ids": ["f1"]}


def run(main, *args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def noul_set(rows, prefix):
    """Cases and answers for REFUND from (probability or None for a refusal, label) rows."""
    cases = [Case(f"{prefix}{i}", "state", {"refund": label}) for i, (_, label) in enumerate(rows)]
    answers = {case.id: {"refund": RefusalAnswer("refund") if p is None else NoulAnswer("refund", p)}
               for case, (p, _) in zip(cases, rows)}
    return cases, answers


class FittingTests(unittest.TestCase):
    def test_isotonic_pools_violators_into_a_monotone_map(self):
        # Rates by probability: 0.1 -> 1/2, 0.4 -> 0/2 (violates), 0.7 -> 1/2, 0.9 -> 2/2.
        pairs = [(0.1, True), (0.1, False), (0.4, False), (0.4, False), (0.7, True), (0.7, False),
                 (0.9, True), (0.9, True)]
        mapping = fit_isotonic(pairs)
        self.assertEqual(mapping, {"x": [0.1, 0.4, 0.7, 0.9], "y": [0.25, 0.25, 0.5, 1.0]})
        self.assertEqual(apply_map("isotonic", mapping, 0.0), 0.25)  # constant beyond the ends
        self.assertEqual(apply_map("isotonic", mapping, 1.0), 1.0)
        self.assertAlmostEqual(apply_map("isotonic", mapping, 0.8), 0.75)  # linear between blocks

    def test_platt_shrinks_an_overconfident_model_toward_its_hit_rate(self):
        # Says 0.9 but is right 30 of 50 times; says 0.1 and is wrong 20 of 50 times.
        pairs = [(0.9, i < 30) for i in range(50)] + [(0.1, i < 20) for i in range(50)]
        mapping = fit_platt(pairs)
        self.assertAlmostEqual(apply_map("platt", mapping, 0.9), 0.6, delta=0.01)
        self.assertAlmostEqual(apply_map("platt", mapping, 0.1), 0.4, delta=0.01)

    def test_platt_reaches_the_optimum_from_a_far_start(self):
        # Confidently wrong both ways: the smoothed targets are 11/12 at 0.02 and 1/12 at 0.98.
        pairs = [(0.02, True)] * 10 + [(0.98, False)] * 10
        mapping = fit_platt(pairs)
        self.assertAlmostEqual(apply_map("platt", mapping, 0.02), 11 / 12, places=9)
        self.assertAlmostEqual(apply_map("platt", mapping, 0.98), 1 / 12, places=9)

    def test_platt_on_one_distinct_probability_is_the_constant_target(self):
        # a and b are not identifiable from one probability; the map is the smoothed hit rate everywhere.
        mapping = fit_platt([(0.02, True)] * 12)
        self.assertEqual(mapping["a"], 0.0)
        for probability in (0.02, 0.5, 0.99):
            self.assertAlmostEqual(apply_map("platt", mapping, probability), 13 / 14, places=12)
        # Probabilities spanning less than 1e-4 fix no reproducible slope either.
        self.assertEqual(fit_platt([(0.9, True)] * 5 + [(0.90005, False)] * 5)["a"], 0.0)

    def test_refusals_are_left_out_of_the_fit(self):
        cases, answers = noul_set([(0.2, False), (None, True), (0.8, True)], "f")
        document = fit("isotonic", [REFUND], cases, answers, BASIS, PRODUCER)
        self.assertEqual(document["questions"]["refund"]["n"], 2)
        self.assertEqual(document["questions"]["refund"]["positives"], 1)

    def test_fitting_without_any_answered_label_is_an_input_error(self):
        cases, answers = noul_set([(None, True)], "f")
        with self.assertRaises(DatasetError):
            fit("platt", [REFUND], cases, answers, BASIS, PRODUCER)

    def test_a_decreasing_isotonic_map_is_rejected(self):
        cases, answers = noul_set([(0.2, False), (0.8, True)], "f")
        document = fit("isotonic", [REFUND], cases, answers, BASIS, PRODUCER)
        document["questions"]["refund"]["map"]["y"] = [1.0, 0.0]
        with self.assertRaises(DatasetError):
            load(json.dumps(document).encode())

    def test_held_out_refusal_leaves_calibrated_metrics_unmeasured(self):
        fit_cases, fit_answers = noul_set([(0.2, False), (0.8, True)], "f")
        calibration = load(json.dumps(fit("isotonic", [REFUND], fit_cases, fit_answers, BASIS, PRODUCER)).encode())
        cases, answers = noul_set([(0.3, False), (None, True)], "h")
        metrics = score_answers([REFUND], cases, answers, calibration)["refund"]
        self.assertEqual([metrics[k] for k in ("calibrated_brier", "calibrated_log_loss", "calibrated_ece")],
                         [None, None, None])


class CommandTests(unittest.TestCase):
    """Fit on example cases t01-t06, apply to t07-t12, and verify both directories."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for name, rows in (("fit", slice(0, 6)), ("held", slice(6, 12))):
            for kind in ("cases", "responses"):
                lines = (EXAMPLES / f"support-ticket-{kind}.jsonl").read_text().splitlines(True)[rows]
                (self.root / f"{name}-{kind}.jsonl").write_text("".join(lines))

    def evaluate(self, half, out, *extra):
        return run(eval_main, "--questions", QUESTIONS_FILE, "--cases", self.root / f"{half}-cases.jsonl",
                   "--responses", self.root / f"{half}-responses.jsonl", "--out", self.root / out, *extra)

    def require(self, bound):
        path = self.root / f"require-{bound}.json"
        path.write_text(json.dumps({"questions": {"refund": {"calibrated_ece": {"max": bound}}}}))
        return path

    def test_platt_fit_and_held_out_application_verify(self):
        self.assertEqual(self.evaluate("fit", "fitted", "--fit-calibration", "platt")[0], 3)
        calibration = self.root / "fitted" / "calibration.json"
        self.assertEqual(self.evaluate("held", "applied", "--calibration", calibration)[0], 3)
        for name in ("fitted", "applied"):
            code, out, err = run(verify_main, "--evaluation", self.root / name)
            self.assertEqual((code, err), (0, ""), out)
        report = json.loads((self.root / "applied" / "evaluation.json").read_text())
        self.assertEqual(report["schema_version"], 3)
        self.assertIsNotNone(report["questions"]["refund"]["calibrated_ece"])

    def test_a_calibrated_bound_gates_the_held_out_run(self):
        self.evaluate("fit", "fitted", "--fit-calibration", "isotonic")
        calibration = self.root / "fitted" / "calibration.json"
        self.assertEqual(self.evaluate("held", "loose", "--calibration", calibration,
                                       "--require", self.require(0.5))[0], 0)
        self.assertEqual(self.evaluate("held", "tight", "--calibration", calibration,
                                       "--require", self.require(0.01))[0], 1)
        # Without a calibration the calibrated metric is unmeasured, so its bound fails.
        self.assertEqual(self.evaluate("held", "none", "--require", self.require(0.5))[0], 1)

    def test_applying_to_cases_it_was_fitted_on_is_refused(self):
        self.evaluate("fit", "fitted", "--fit-calibration", "platt")
        code, _, err = self.evaluate("fit", "in-sample", "--calibration", self.root / "fitted" / "calibration.json")
        self.assertEqual(code, 2)
        self.assertIn("held-out", err)
        self.assertFalse((self.root / "in-sample").exists())

    def test_malformed_calibration_file_is_invalid_input(self):
        self.evaluate("fit", "fitted", "--fit-calibration", "isotonic")
        document = json.loads((self.root / "fitted" / "calibration.json").read_text())
        document["questions"]["refund"]["type"] = ["noul"]
        bad = self.root / "bad-calibration.json"
        bad.write_text(json.dumps(document))
        code, _, err = self.evaluate("held", "bad", "--calibration", bad)
        self.assertEqual(code, 2)
        self.assertIn("invalid type", err)

    def reseal_calibration(self, directory, edit):
        """Edit calibration.json, then rewrite every hash that covers it, as a forger would."""
        document = json.loads((directory / "calibration.json").read_text())
        edit(document["questions"]["refund"]["map"])
        data = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        (directory / "calibration.json").write_bytes(data)
        report = json.loads((directory / "evaluation.json").read_text())
        report["calibration"]["sha256"] = hashlib.sha256(data).hexdigest()
        (directory / "evaluation.json").write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
        provenance = json.loads((directory / "provenance.json").read_text())
        for name in ("calibration.json", "evaluation.json"):
            provenance["outputs"][name]["sha256"] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        (directory / "provenance.json").write_text(json.dumps(provenance, sort_keys=True, separators=(",", ":")))
        return run(verify_main, "--evaluation", directory)

    def test_edited_platt_parameter_fails_the_refit(self):
        self.evaluate("fit", "fitted", "--fit-calibration", "platt")
        code, out, _ = self.reseal_calibration(self.root / "fitted",
                                               lambda mapping: mapping.update(a=mapping["a"] + 1e-6))
        self.assertEqual(code, 1)
        self.assertIn("calibration.json", out)

    def test_slope_added_to_a_one_probability_platt_fit_fails_the_refit(self):
        # One case: the fit is the constant map. A slope through the same point keeps the value there
        # but changes every other probability's calibrated value, so it must not verify.
        (self.root / "one-cases.jsonl").write_text((self.root / "fit-cases.jsonl").read_text().splitlines(True)[0])
        (self.root / "one-responses.jsonl").write_text(
            (self.root / "fit-responses.jsonl").read_text().splitlines(True)[0])
        self.assertEqual(self.evaluate("one", "fitted", "--fit-calibration", "platt")[0], 3)
        raw = 0.08  # t01's raw refund probability in the example responses
        logit = math.log(raw / (1 - raw))
        code, out, _ = self.reseal_calibration(
            self.root / "fitted", lambda mapping: mapping.update(a=1.0, b=mapping["b"] - logit))
        self.assertEqual(code, 1)
        self.assertIn("calibration.json", out)

    def test_signed_calibrated_run_verifies_with_the_schema_3_predicate(self):
        key = self.root / "key"
        key.write_text("ab" * 32)
        self.assertEqual(self.evaluate("fit", "signed", "--fit-calibration", "isotonic", "--sign-key", key)[0], 3)
        envelope = json.loads((self.root / "signed" / "provenance.json.dsse.json").read_text())
        statement = json.loads(base64.b64decode(envelope["payload"]))
        self.assertTrue(statement["predicateType"].endswith("/provenance/v3"))
        code, out, err = run(verify_main, "--evaluation", self.root / "signed", "--require-signature", "--key", key)
        self.assertEqual((code, err), (0, ""), out)


if __name__ == "__main__":
    unittest.main()
