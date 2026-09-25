import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from expgate import stats
from expgate.decision import evaluate
from expgate.generator import SCENARIOS, generate
from expgate.run import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "offer-ranker-v2.json"


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class StatsTest(unittest.TestCase):
    def test_proportion_effect(self):
        e = stats.proportion_effect(100, 1000, 150, 1000)
        self.assertAlmostEqual(e.diff, 0.05)
        self.assertAlmostEqual(e.se, (0.1 * 0.9 / 1000 + 0.15 * 0.85 / 1000) ** 0.5)

    def test_mean_effect_uses_welch_standard_error(self):
        e = stats.mean_effect(10.0, 2.0, 100, 11.0, 4.0, 400)
        self.assertAlmostEqual(e.diff, 1.0)
        self.assertAlmostEqual(e.se, (4 / 100 + 16 / 400) ** 0.5)

    def test_sample_ratio(self):
        self.assertAlmostEqual(stats.sample_ratio_p_value(5000, 5000, 0.5), 1.0)
        self.assertLess(stats.sample_ratio_p_value(4700, 5300, 0.5), 1e-8)
        self.assertAlmostEqual(stats.sample_ratio_p_value(2000, 8000, 0.8), 1.0)

    def test_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            stats.proportion_effect(11, 10, 1, 10)
        with self.assertRaises(ValueError):
            stats.sample_ratio_p_value(1, 1, 1.0)
        with self.assertRaises(ValueError):
            stats.z_for(0.0)


class DecisionTest(unittest.TestCase):
    EXPECTED = {"win": "SHIP", "flat": "HOLD", "guardrail-breach": "ROLLBACK",
                "regression": "ROLLBACK", "srm": "INVALID"}

    def test_every_scenario_has_an_expectation(self):
        self.assertEqual(set(SCENARIOS), set(self.EXPECTED))

    def test_scenario_decisions(self):
        for name, expected in self.EXPECTED.items():
            with self.subTest(scenario=name):
                self.assertEqual(evaluate(generate(name))["decision"], expected)

    def test_breach_names_the_guardrail(self):
        report = evaluate(generate("guardrail-breach"))
        status = {m["metric"]: m["status"] for m in report["metrics"]}
        self.assertEqual(status["latency_ms"], "BREACH")
        self.assertEqual(status["conversion"], "IMPROVED")
        self.assertIn("guardrail latency_ms breached its margin", report["reasons"])

    def test_sample_ratio_mismatch_takes_precedence(self):
        summary = generate("srm")
        summary["arms"]["treatment"]["metrics"]["latency_ms"]["mean"] += 20
        self.assertEqual(evaluate(summary)["decision"], "INVALID")

    def test_bonferroni_widens_guardrail_bounds(self):
        report = evaluate(generate("win"))
        z = {m["role"]: m["z"] for m in report["metrics"]}
        self.assertAlmostEqual(z["primary"], stats.z_for(0.05))
        self.assertAlmostEqual(z["guardrail"], stats.z_for(0.025))

    def test_generation_is_deterministic(self):
        self.assertEqual(generate("win"), generate("win"))
        self.assertNotEqual(generate("win", seed=1), generate("win"))

    def test_validation(self):
        base = generate("win")
        cases = {
            "no primary": lambda s: s["metrics"]["conversion"].update(role="guardrail", margin=0.01),
            "missing margin": lambda s: s["metrics"]["latency_ms"].pop("margin"),
            "bad direction": lambda s: s["metrics"]["latency_ms"].update(direction="down"),
            "missing arm metric": lambda s: s["arms"]["control"]["metrics"].pop("refund_rate"),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                summary = copy.deepcopy(base)
                summary["metrics"] = copy.deepcopy(summary["metrics"])
                mutate(summary)
                with self.assertRaises(ValueError):
                    evaluate(summary)


class CliTest(unittest.TestCase):
    def test_example_ships_and_records_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp, "a"), Path(tmp, "b")
            self.assertEqual(run_cli("--input", str(EXAMPLE), "--out", str(a), "--require-ship")[0], 0)
            self.assertEqual(run_cli("--input", str(EXAMPLE), "--out", str(b))[0], 0)
            self.assertEqual((a / "decision.json").read_bytes(), (b / "decision.json").read_bytes())
            self.assertIn("**Decision: SHIP**", (a / "DECISION.md").read_text())
            self.assertEqual(json.loads((a / "decision.json").read_text())["decision"], "SHIP")

    def test_all_scenarios_and_require_ship(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli("--all-scenarios", "--out", tmp, "--require-ship")
            self.assertEqual(code, 1)
            self.assertEqual(len(out.splitlines()), len(SCENARIOS))
            for name in SCENARIOS:
                self.assertTrue(Path(tmp, name, "decision.json").is_file())

    def test_refuses_non_empty_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "keep").write_text("x")
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                main(["--scenario", "win", "--out", tmp])

    def test_invalid_summary_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.json")
            bad.write_text(json.dumps({"arms": {}, "metrics": {}}))
            code, _, err = run_cli("--input", str(bad), "--out", str(Path(tmp, "out")))
            self.assertEqual(code, 2)
            self.assertIn("invalid experiment summary", err)


if __name__ == "__main__":
    unittest.main()
