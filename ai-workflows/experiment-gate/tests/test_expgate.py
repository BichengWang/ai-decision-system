import copy
import io
import json
import random
import statistics
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
                "regression": "ROLLBACK", "srm": "INVALID", "cuped": "HOLD"}

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


def example():
    return json.loads(EXAMPLE.read_text())


def status_of(report, metric):
    return next(m for m in report["metrics"] if m["metric"] == metric)


class BoundaryTest(unittest.TestCase):
    """Pin the edges of the decision rules without changing any threshold."""

    def test_sample_ratio_p_value_equal_to_alpha_passes(self):
        summary = example()  # 50210 / 49874 units: p is about 0.29
        p = stats.sample_ratio_p_value(summary["arms"]["control"]["units"],
                                       summary["arms"]["treatment"]["units"], 0.5)
        summary["policy"] = {"srm_alpha": p}
        self.assertTrue(evaluate(summary)["sample_ratio"]["pass"])
        summary["policy"] = {"srm_alpha": p * 1.000001}
        self.assertEqual(evaluate(summary)["decision"], "INVALID")

    def test_guardrail_bound_equal_to_margin_is_inconclusive(self):
        summary = generate("win")
        lo = status_of(evaluate(summary), "latency_ms")["improvement_bounds"][0]
        summary["metrics"] = copy.deepcopy(summary["metrics"])
        summary["metrics"]["latency_ms"]["margin"] = -lo  # upper degradation bound
        report = evaluate(summary)
        self.assertEqual(status_of(report, "latency_ms")["status"], "INCONCLUSIVE")
        self.assertEqual(report["decision"], "HOLD")
        summary["metrics"]["latency_ms"]["margin"] = -lo * 1.000001
        self.assertEqual(evaluate(summary)["decision"], "SHIP")

    def test_significant_harm_within_margin_is_not_a_breach(self):
        summary = generate("guardrail-breach")
        summary["metrics"] = copy.deepcopy(summary["metrics"])
        summary["metrics"]["latency_ms"]["margin"] = 20.0
        report = evaluate(summary)
        latency = status_of(report, "latency_ms")
        self.assertLess(latency["improvement_bounds"][1], 0)  # significantly worse
        self.assertEqual(latency["status"], "NON_INFERIOR")
        self.assertNotEqual(report["decision"], "ROLLBACK")

    def test_primary_only_experiment(self):
        summary = generate("win")
        summary["metrics"] = {"conversion": summary["metrics"]["conversion"]}
        report = evaluate(summary)
        self.assertEqual(report["decision"], "SHIP")
        self.assertAlmostEqual(report["metrics"][0]["z"], stats.z_for(0.05))

    def test_zero_variance_holds_instead_of_failing(self):
        summary = example()
        for arm in summary["arms"].values():
            arm["metrics"]["conversion"]["successes"] = 0
        report = evaluate(summary)
        self.assertEqual(status_of(report, "conversion")["status"], "INCONCLUSIVE")
        self.assertEqual(report["decision"], "HOLD")

    def test_policy_and_share_limits_are_accepted(self):
        summary = example()
        summary["policy"] = {"alpha": 0.999, "srm_alpha": 1e-12}
        summary["assignment"] = {"expected_treatment_share": 0.5}
        self.assertIn(evaluate(summary)["decision"], {"SHIP", "HOLD", "ROLLBACK"})


def _set(path, value):
    def mutate(summary):
        target = summary
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return summary
    return mutate


MALFORMED = {
    "top-level list": lambda s: [s],
    "metrics not an object": _set(["metrics"], ["conversion"]),
    "metric spec not an object": _set(["metrics", "latency_ms"], "mean"),
    "unknown metric type": _set(["metrics", "latency_ms", "type"], "ratio"),
    "infinite margin": _set(["metrics", "latency_ms", "margin"], float("inf")),
    "string margin": _set(["metrics", "latency_ms", "margin"], "2"),
    "arms not an object": _set(["arms"], []),
    "missing treatment arm": lambda s: s["arms"].pop("treatment") and s,
    "boolean units": _set(["arms", "control", "units"], True),
    "fractional units": _set(["arms", "control", "units"], 50210.5),
    "zero units": _set(["arms", "control", "units"], 0),
    "fractional successes": _set(["arms", "control", "metrics", "conversion", "successes"], 5121.5),
    "successes above units": _set(["arms", "control", "metrics", "conversion", "successes"], 60000),
    "negative successes": _set(["arms", "control", "metrics", "conversion", "successes"], -1),
    "NaN mean": _set(["arms", "treatment", "metrics", "latency_ms", "mean"], float("nan")),
    "infinite sd": _set(["arms", "control", "metrics", "latency_ms", "sd"], float("inf")),
    "negative sd": _set(["arms", "control", "metrics", "latency_ms", "sd"], -1.0),
    "string mean": _set(["arms", "control", "metrics", "latency_ms", "mean"], "41.8"),
    "metric stat not an object": _set(["arms", "control", "metrics", "latency_ms"], 41.8),
    "alpha out of range": _set(["policy", "alpha"], 1.0),
    "srm_alpha out of range": _set(["policy", "srm_alpha"], 5),
    "policy not an object": _set(["policy"], 0.05),
    "share out of range": _set(["assignment", "expected_treatment_share"], 0.0),
}


class MalformedInputTest(unittest.TestCase):
    def test_evaluate_raises_value_error(self):
        for label, mutate in MALFORMED.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    evaluate(mutate(example()))

    def test_cli_exits_2_not_1(self):
        # Exit 1 means "evaluated but did not ship"; bad input must never look like that.
        with tempfile.TemporaryDirectory() as tmp:
            for i, (label, mutate) in enumerate(MALFORMED.items()):
                with self.subTest(label):
                    path = Path(tmp, f"{i}.json")
                    path.write_text(json.dumps(mutate(example())))
                    code, _, err = run_cli("--input", str(path), "--out", str(Path(tmp, f"out-{i}")),
                                           "--require-ship")
                    self.assertEqual(code, 2)
                    self.assertIn("invalid experiment summary", err)
                    self.assertFalse(Path(tmp, f"out-{i}").exists())

    def test_unreadable_input_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.json")
            bad.write_text("{")
            for source in (bad, Path(tmp, "missing.json")):
                with self.subTest(str(source.name)):
                    code, _, err = run_cli("--input", str(source), "--out", str(Path(tmp, "out")))
                    self.assertEqual(code, 2)
                    self.assertIn("cannot read experiment summary", err)


def without_covariates(summary):
    summary = copy.deepcopy(summary)
    for arm in summary["arms"].values():
        for stat in arm["metrics"].values():
            stat.pop("covariate", None)
    return summary


class CupedTest(unittest.TestCase):
    EQUAL = stats.Covariate(10.0, 3.0, 0.8)

    def test_zero_correlation_reduces_to_the_unadjusted_estimators(self):
        flat = stats.Covariate(10.0, 3.0, 0.0)
        effect, info = stats.cuped_effect(5.0, 4.0, 100, flat, 5.5, 9.0, 150, stats.Covariate(10.4, 2.0, 0.0))
        welch = stats.mean_effect(5.0, 2.0, 100, 5.5, 3.0, 150)
        self.assertAlmostEqual(effect.diff, welch.diff)
        self.assertAlmostEqual(effect.se, welch.se)
        self.assertEqual(info["theta"], 0.0)
        self.assertAlmostEqual(info["variance_reduction"], 0.0)

    def test_variance_reduction_is_rho_squared_for_matching_arms(self):
        for rho in (0.3, 0.8, -0.6):
            with self.subTest(rho=rho):
                cov = stats.Covariate(10.0, 3.0, rho)
                _, info = stats.cuped_effect(5.0, 4.0, 1000, cov, 5.5, 4.0, 1000, cov)
                self.assertAlmostEqual(info["variance_reduction"], rho ** 2)
                self.assertAlmostEqual(info["theta"], rho * 2.0 / 3.0)

    def test_adjusted_difference_removes_the_covariate_gap(self):
        control, treatment = stats.Covariate(10.0, 3.0, 0.8), stats.Covariate(10.6, 3.0, 0.8)
        effect, info = stats.cuped_effect(5.0, 4.0, 1000, control, 5.9, 4.0, 1000, treatment)
        self.assertAlmostEqual(info["raw_diff"], 0.9)
        self.assertAlmostEqual(effect.diff, 0.9 - info["theta"] * 0.6)
        self.assertEqual((effect.control, effect.treatment), (5.0, 5.9))  # arm means stay raw

    def test_proportion_uses_the_wald_variance(self):
        flat = stats.Covariate(0.0, 1.0, 0.0)
        effect, _ = stats.cuped_effect(0.10, stats.proportion_variance(100, 1000), 1000, flat,
                                       0.12, stats.proportion_variance(120, 1000), 1000, flat)
        wald = stats.proportion_effect(100, 1000, 120, 1000)
        self.assertAlmostEqual(effect.se, wald.se)
        self.assertAlmostEqual(effect.diff, wald.diff)

    def test_rejects_unusable_summaries(self):
        ok = self.EQUAL
        for label, args in {
            "correlation above 1": (stats.Covariate(10.0, 3.0, 1.2), ok),
            "zero covariate sd": (stats.Covariate(10.0, 0.0, 0.5), ok),
            "negative covariate sd": (ok, stats.Covariate(10.0, -1.0, 0.5)),
        }.items():
            with self.subTest(label), self.assertRaises(ValueError):
                stats.cuped_effect(5.0, 4.0, 100, args[0], 5.0, 4.0, 100, args[1])
        with self.assertRaises(ValueError):
            stats.cuped_effect(5.0, 4.0, 1, ok, 5.0, 4.0, 100, ok)
        with self.assertRaises(ValueError):
            stats.cuped_effect(5.0, -4.0, 100, ok, 5.0, 4.0, 100, ok)

    def test_simulation_matches_the_formulas(self):
        """Run many A/A experiments at the unit level: the reported SE must match the spread of the
        adjusted differences, the adjustment must not move their mean, and the spread must shrink by
        sqrt(1 - rho**2) relative to the unadjusted difference."""
        rng, rho, n, reps = random.Random(7), 0.7, 300, 500
        adjusted, raw, reported = [], [], []

        def arm():
            xs = [rng.gauss(50.0, 10.0) for _ in range(n)]
            ys = [30.0 + rho * (x - 50.0) + (1 - rho ** 2) ** 0.5 * 10.0 * rng.gauss(0, 1) for x in xs]
            return (statistics.fmean(ys), statistics.variance(ys), stats.Covariate(
                statistics.fmean(xs), statistics.stdev(xs), statistics.correlation(xs, ys)))

        for _ in range(reps):
            (cm, cv, cc), (tm, tv, tc) = arm(), arm()
            effect, info = stats.cuped_effect(cm, cv, n, cc, tm, tv, n, tc)
            adjusted.append(effect.diff)
            raw.append(info["raw_diff"])
            reported.append(effect.se)
        spread = statistics.stdev(adjusted)
        self.assertAlmostEqual(statistics.fmean(reported) / spread, 1.0, delta=0.12)
        self.assertLess(abs(statistics.fmean(adjusted)), 3 * spread / reps ** 0.5)
        self.assertAlmostEqual(spread / statistics.stdev(raw), (1 - rho ** 2) ** 0.5, delta=0.08)

    def test_scenario_decision_depends_on_the_adjustment(self):
        summary = generate("cuped")
        adjusted, plain = evaluate(summary), evaluate(without_covariates(summary))
        self.assertEqual(adjusted["decision"], "HOLD")
        self.assertEqual(plain["decision"], "SHIP")  # the unadjusted lift is inflated by the covariate gap
        row = adjusted["metrics"][0]
        self.assertEqual(row["adjustment"]["method"], "cuped")
        self.assertLess(row["se"], row["adjustment"]["raw_se"])
        self.assertLess(row["diff"], row["adjustment"]["raw_diff"])
        self.assertNotIn("adjustment", plain["metrics"][0])

    def test_summaries_without_covariates_are_unchanged(self):
        for name in ("win", "flat", "guardrail-breach", "regression", "srm"):
            with self.subTest(name):
                self.assertFalse(any("adjustment" in m for m in evaluate(generate(name))["metrics"]))
        self.assertFalse(any("adjustment" in m for m in evaluate(example())["metrics"]))

    def test_covariate_must_be_in_both_arms_or_neither(self):
        summary = generate("cuped")
        del summary["arms"]["treatment"]["metrics"]["revenue_per_user"]["covariate"]
        with self.assertRaisesRegex(ValueError, "both arms or in neither"):
            evaluate(summary)

    def test_malformed_covariates_are_rejected(self):
        path = ["arms", "control", "metrics", "revenue_per_user", "covariate"]
        for label, mutate in {
            "not an object": _set(path, 0.8),
            "correlation above 1": _set(path + ["corr"], 1.5),
            "correlation below -1": _set(path + ["corr"], -1.01),
            "string correlation": _set(path + ["corr"], "0.8"),
            "zero sd": _set(path + ["sd"], 0),
            "negative sd": _set(path + ["sd"], -2.0),
            "NaN mean": _set(path + ["mean"], float("nan")),
            "missing sd": lambda s: s["arms"]["control"]["metrics"]["revenue_per_user"]["covariate"].pop("sd") and s,
        }.items():
            with self.subTest(label), self.assertRaises(ValueError):
                evaluate(mutate(generate("cuped")))

    def test_proportion_metrics_accept_a_covariate(self):
        summary = example()
        for arm, gap in (("control", 0.0), ("treatment", 0.05)):
            summary["arms"][arm]["metrics"]["conversion"]["covariate"] = {"mean": 0.10 + gap, "sd": 0.30, "corr": 0.5}
        row = status_of(evaluate(summary), "conversion")
        self.assertGreater(row["adjustment"]["variance_reduction"], 0.0)

    def test_cli_reports_the_adjustment(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = run_cli("--scenario", "cuped", "--out", tmp)
            self.assertEqual(code, 0)
            self.assertIn("CUPED on `revenue_per_user`", Path(tmp, "DECISION.md").read_text())
            record = json.loads(Path(tmp, "decision.json").read_text())
            self.assertIn("adjustment", record["metrics"][0])


if __name__ == "__main__":
    unittest.main()
