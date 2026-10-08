import copy
import io
import json
import math
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
                "regression": "ROLLBACK", "srm": "INVALID", "cuped": "HOLD",
                "early-regression": "ROLLBACK"}

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
    "power of 1": _set(["policy", "power"], 1.0),
    "string power": _set(["policy", "power"], "0.8"),
    "misspelled alpha": _set(["policy", "alpah"], 0.01),
    "misspelled sequential plan": _set(["policy", "sequential"], {"planned_units": 200000, "planed_units": 1}),
    "misspelled share": _set(["assignment", "expected_share"], 0.2),
    "misspelled covariate": _set(["arms", "control", "metrics", "latency_ms", "covarite"],
                                 {"mean": 40.0, "sd": 12.0, "corr": 0.5}),
    "covariate with an extra field": lambda s: [
        arm["metrics"]["latency_ms"].__setitem__("covariate", {"mean": 40.0, "sd": 12.0, "corr": 0.5, "rho": 0.5})
        for arm in s["arms"].values()] and s,
    "mean field on a proportion": _set(["arms", "control", "metrics", "conversion", "mean"], 0.1),
    "non-string experiment name": _set(["experiment"], 7),
    "blank experiment name": _set(["experiment"], " "),
}


class MalformedInputTest(unittest.TestCase):
    def test_misspelled_setting_is_named(self):
        summary = example()
        summary["policy"]["alpah"] = 0.01
        with self.assertRaisesRegex(ValueError, r"'policy' has unknown keys \['alpah'\]"):
            evaluate(summary)

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


def sequential_summary(planned, n, control_mean, treatment_mean, sd=10.0):
    """Primary-only mean-metric summary with ``n`` units per arm, monitored toward ``planned`` units."""
    return {"metrics": {"y": {"type": "mean", "role": "primary", "direction": "increase"}},
            "policy": {"sequential": {"planned_units": planned}},
            "arms": {"control": {"units": n, "metrics": {"y": {"mean": control_mean, "sd": sd}}},
                     "treatment": {"units": n, "metrics": {"y": {"mean": treatment_mean, "sd": sd}}}}}


class SequentialTest(unittest.TestCase):
    def test_multiplier_is_wider_than_fixed_horizon_and_narrowest_at_the_plan(self):
        for alpha in (0.05, 0.025, 0.01):
            with self.subTest(alpha=alpha):
                at_plan = stats.sequential_multiplier(alpha, 1.0)
                self.assertGreater(at_plan, stats.z_for(alpha))
                self.assertLess(at_plan, stats.sequential_multiplier(alpha, 4.0))   # a quarter of the way in
                self.assertLess(at_plan, stats.sequential_multiplier(alpha, 0.25))  # four times past the plan
                self.assertLess(stats.sequential_multiplier(alpha, 4.0), stats.sequential_multiplier(alpha, 100.0))
        self.assertLess(stats.sequential_multiplier(0.05, 1.0), stats.sequential_multiplier(0.01, 1.0))

    def test_multiplier_reaches_the_mixture_boundary(self):
        """At the returned value the one-sided mixture likelihood ratio equals 1 / alpha."""
        for alpha, info in ((0.05, 1.0), (0.0125, 3.0)):
            ratio = stats.mixture_ratio(alpha) / info
            z = stats.sequential_multiplier(alpha, info)
            mixture = 2 / (1 + ratio) ** 0.5 * math.exp(z * z * ratio / (2 * (1 + ratio))) * \
                statistics.NormalDist().cdf(z * (ratio / (1 + ratio)) ** 0.5)
            self.assertAlmostEqual(mixture * alpha, 1.0, places=9)

    def test_rejects_invalid_arguments(self):
        with self.assertRaises(ValueError):
            stats.sequential_multiplier(0.05, 0.0)
        with self.assertRaises(ValueError):
            stats.mixture_ratio(1.0)

    def test_repeated_looks_keep_the_false_ship_rate_below_alpha(self):
        """A/A experiments checked at 20 interim looks. Re-applying the fixed-horizon bound at every
        look ships far more often than alpha; the always-valid bound stays below it."""
        rng, reps, looks, block, sd = random.Random(11), 400, 20, 500, 10.0
        ships = {"sequential": 0, "fixed": 0}
        for _ in range(reps):
            totals, shipped = [0.0, 0.0], {"sequential": False, "fixed": False}
            for k in range(1, looks + 1):
                totals = [t + rng.gauss(0.0, sd / block ** 0.5) * block for t in totals]
                summary = sequential_summary(2 * looks * block, k * block, totals[0] / (k * block),
                                             totals[1] / (k * block), sd)
                shipped["sequential"] |= evaluate(summary)["decision"] == "SHIP"
                del summary["policy"]
                shipped["fixed"] |= evaluate(summary)["decision"] == "SHIP"
            for key in ships:
                ships[key] += shipped[key]
        self.assertLess(ships["sequential"] / reps, 0.05)
        self.assertGreater(ships["fixed"] / reps, 0.10)

    def test_interim_look_can_stop_for_a_large_regression(self):
        report = evaluate(generate("early-regression"))
        self.assertEqual(report["decision"], "ROLLBACK")
        self.assertEqual(report["sequential"], {"planned_units": 60_000, "units": 15_000, "information_fraction": 0.25})
        primary = report["metrics"][0]
        self.assertAlmostEqual(primary["z"], stats.sequential_multiplier(0.05, 4.0))
        guard = status_of(report, "latency_ms")
        self.assertAlmostEqual(guard["z"], stats.sequential_multiplier(0.025, 4.0))

    def test_same_data_can_ship_fixed_horizon_but_hold_sequentially(self):
        summary = sequential_summary(20_000, 10_000, 50.0, 50.3)  # z = 2.12
        self.assertEqual(evaluate(summary)["decision"], "HOLD")
        self.assertIn("planned sample size reached without a decision", evaluate(summary)["reasons"])
        del summary["policy"]
        self.assertEqual(evaluate(summary)["decision"], "SHIP")

    def test_hold_before_the_plan_does_not_claim_the_horizon(self):
        report = evaluate(sequential_summary(40_000, 10_000, 50.0, 50.0))
        self.assertEqual(report["decision"], "HOLD")
        self.assertEqual(len(report["reasons"]), 1)
        self.assertTrue(report["reasons"][0].startswith("primary metric is inconclusive (detectable improvement"))

    def test_fixed_horizon_records_are_unchanged(self):
        for name in sorted(set(SCENARIOS) - {"early-regression"}):
            with self.subTest(name):
                self.assertNotIn("sequential", evaluate(generate(name)))
        self.assertNotIn("sequential", evaluate(example()))

    def test_malformed_sequential_policy_is_rejected(self):
        for label, value in {
            "not an object": 60_000,
            "missing planned_units": {},
            "float planned_units": {"planned_units": 60_000.0},
            "boolean planned_units": {"planned_units": True},
            "too small": {"planned_units": 1},
        }.items():
            with self.subTest(label), self.assertRaises(ValueError):
                summary = example()
                summary["policy"]["sequential"] = value
                evaluate(summary)

    def test_cli_reports_the_monitoring_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = run_cli("--scenario", "early-regression", "--out", tmp, "--require-ship")
            self.assertEqual(code, 1)
            self.assertIn("Sequential monitoring: 15000 of 60000 planned units (25%)",
                          Path(tmp, "DECISION.md").read_text())
            record = json.loads(Path(tmp, "decision.json").read_text())
            self.assertEqual(record["policy"]["sequential"], {"planned_units": 60_000})


def ratio_stat(num_mean, num_sd, den_mean, den_sd, corr):
    return {"numerator": {"mean": num_mean, "sd": num_sd}, "denominator": {"mean": den_mean, "sd": den_sd},
            "corr": corr}


def with_ratio_guardrail(summary, control, treatment, margin=0.5):
    summary["metrics"]["revenue_per_session"] = {"type": "ratio", "role": "guardrail", "direction": "increase",
                                                 "margin": margin}
    summary["arms"]["control"]["metrics"]["revenue_per_session"] = control
    summary["arms"]["treatment"]["metrics"]["revenue_per_session"] = treatment
    return summary


class RatioTest(unittest.TestCase):
    def test_delta_method_by_hand(self):
        arm = stats.RatioArm(100, 12.0, 6.0, 3.0, 1.5, 0.5)
        ratio, var = arm.ratio_and_variance()
        self.assertAlmostEqual(ratio, 4.0)
        # (36 - 2*4*(0.5*6*1.5) + 16*2.25) / (9*100) = (36 - 36 + 36) / 900
        self.assertAlmostEqual(var, 0.04)
        effect = stats.ratio_effect(arm, stats.RatioArm(400, 13.0, 6.0, 3.0, 1.5, 0.5))
        self.assertAlmostEqual(effect.diff, 13.0 / 3.0 - 4.0)
        r = 13.0 / 3.0
        self.assertAlmostEqual(effect.se ** 2, 0.04 + (36 - 2 * r * 4.5 + r * r * 2.25) / (9 * 400))

    def test_constant_denominator_reduces_to_a_mean(self):
        effect = stats.ratio_effect(stats.RatioArm(100, 10.0, 2.0, 1.0, 0.0, 0.0),
                                    stats.RatioArm(400, 11.0, 4.0, 1.0, 0.0, 0.0))
        mean = stats.mean_effect(10.0, 2.0, 100, 11.0, 4.0, 400)
        self.assertAlmostEqual(effect.diff, mean.diff)
        self.assertAlmostEqual(effect.se, mean.se)

    def test_rejects_unusable_arms(self):
        for arm in (stats.RatioArm(1, 1.0, 1.0, 1.0, 1.0, 0.0), stats.RatioArm(10, 1.0, 1.0, 0.0, 1.0, 0.0),
                    stats.RatioArm(10, 1.0, -1.0, 1.0, 1.0, 0.0), stats.RatioArm(10, 1.0, 1.0, 1.0, 1.0, 1.5)):
            with self.subTest(arm=arm), self.assertRaises(ValueError):
                arm.ratio_and_variance()

    def test_simulation_matches_the_delta_method(self):
        """Randomize users with a varying number of correlated sessions: the reported SE must match
        the spread of the A/A differences, which the session-level SE understates."""
        rng, n, reps = random.Random(3), 400, 300
        diffs, reported, naive = [], [], []

        def arm():
            sessions, revenue, flat = [], [], []
            for _ in range(n):
                k, propensity = 1 + int(rng.expovariate(0.5)), rng.lognormvariate(0, 0.6)
                spend = [propensity * rng.expovariate(1.0) * 5 for _ in range(k)]
                sessions.append(k)
                revenue.append(sum(spend))
                flat += spend
            summary = stats.RatioArm(n, statistics.fmean(revenue), statistics.stdev(revenue),
                                     statistics.fmean(sessions), statistics.stdev(sessions),
                                     statistics.correlation(revenue, sessions))
            return summary, statistics.variance(flat) / len(flat)

        for _ in range(reps):
            (c, naive_c), (t, naive_t) = arm(), arm()
            effect = stats.ratio_effect(c, t)
            diffs.append(effect.diff)
            reported.append(effect.se)
            naive.append(math.sqrt(naive_c + naive_t))
        empirical = statistics.stdev(diffs)
        self.assertAlmostEqual(statistics.fmean(reported) / empirical, 1.0, delta=0.12)
        self.assertLess(statistics.fmean(naive) / empirical, 0.85)

    def test_ratio_guardrail_in_a_decision(self):
        control, treatment = ratio_stat(31.0, 40.0, 3.1, 2.4, 0.6), ratio_stat(31.2, 40.0, 3.1, 2.4, 0.6)
        report = evaluate(with_ratio_guardrail(example(), control, treatment, margin=0.5))
        row = status_of(report, "revenue_per_session")
        self.assertAlmostEqual(row["control"], 31.0 / 3.1)
        self.assertAlmostEqual(row["treatment"], 31.2 / 3.1)
        self.assertEqual(row["status"], "NON_INFERIOR")
        self.assertEqual(report["decision"], "SHIP")
        harmful = ratio_stat(26.0, 40.0, 3.1, 2.4, 0.6)
        report = evaluate(with_ratio_guardrail(example(), control, harmful, margin=0.5))
        self.assertEqual(status_of(report, "revenue_per_session")["status"], "BREACH")
        self.assertEqual(report["decision"], "ROLLBACK")

    def test_ratio_primary_with_sequential_monitoring(self):
        summary = example()
        summary["metrics"] = {"revenue_per_session": {"type": "ratio", "role": "primary", "direction": "increase"}}
        summary["policy"] = {"sequential": {"planned_units": 200000}}
        summary["arms"]["control"]["metrics"] = {"revenue_per_session": ratio_stat(31.0, 40.0, 3.1, 2.4, 0.6)}
        summary["arms"]["treatment"]["metrics"] = {"revenue_per_session": ratio_stat(32.5, 40.0, 3.1, 2.4, 0.6)}
        report = evaluate(summary)
        self.assertEqual(report["decision"], "SHIP")
        self.assertGreater(report["metrics"][0]["z"], stats.z_for(0.05))

    def test_malformed_ratio_metrics_exit_2(self):
        good = ratio_stat(31.0, 40.0, 3.1, 2.4, 0.6)
        bad = {
            "zero denominator": ratio_stat(31.0, 40.0, 0.0, 2.4, 0.6),
            "negative sd": ratio_stat(31.0, -1.0, 3.1, 2.4, 0.6),
            "correlation above 1": ratio_stat(31.0, 40.0, 3.1, 2.4, 1.1),
            "missing denominator": {"numerator": {"mean": 31.0, "sd": 40.0}, "corr": 0.6},
            "missing corr": {"numerator": {"mean": 31.0, "sd": 40.0}, "denominator": {"mean": 3.1, "sd": 2.4}},
            "flat mean instead": {"mean": 10.0, "sd": 4.0},
            "covariate": {**good, "covariate": {"mean": 1.0, "sd": 1.0, "corr": 0.5}},
            "unknown part key": {**good, "numerator": {"mean": 31.0, "sd": 40.0, "n": 5}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            for i, (label, stat) in enumerate(bad.items()):
                with self.subTest(label):
                    summary = with_ratio_guardrail(example(), good, stat)
                    with self.assertRaises(ValueError):
                        evaluate(summary)
                    path = Path(tmp, f"{i}.json")
                    path.write_text(json.dumps(summary))
                    code, _, err = run_cli("--input", str(path), "--out", str(Path(tmp, f"out-{i}")))
                    self.assertEqual(code, 2)
                    self.assertIn("invalid experiment summary", err)


class MinimumDetectableEffectTest(unittest.TestCase):
    def test_every_row_reports_its_mde(self):
        report = evaluate(example())
        self.assertEqual(report["policy"]["power"], 0.8)
        for row in report["metrics"]:
            with self.subTest(row["metric"]):
                self.assertAlmostEqual(row["mde"], (row["z"] + 0.8416212335729143) * row["se"])

    def test_power_and_bounds_widen_the_mde(self):
        base = status_of(evaluate(example()), "conversion")["mde"]
        summary = example()
        summary["policy"]["power"] = 0.95
        self.assertGreater(status_of(evaluate(summary), "conversion")["mde"], base)
        summary = example()
        summary["policy"]["sequential"] = {"planned_units": 200_000}
        self.assertGreater(status_of(evaluate(summary), "conversion")["mde"], base)
        # Guardrails share alpha, so their bounds and MDEs are wider than at the full alpha.
        latency = status_of(evaluate(example()), "latency_ms")
        self.assertAlmostEqual(latency["mde"], stats.minimum_detectable_effect(latency["se"], stats.z_for(0.025), 0.8))

    def test_a_true_effect_equal_to_the_mde_ships_at_the_stated_power(self):
        rng, n, sd, reps = random.Random(5), 5_000, 10.0, 1_000
        mde = stats.minimum_detectable_effect(stats.mean_effect(50.0, sd, n, 50.0, sd, n).se, stats.z_for(0.05), 0.8)
        shipped = 0
        for _ in range(reps):
            summary = sequential_summary(2 * n, n, rng.gauss(50.0, sd / math.sqrt(n)),
                                         rng.gauss(50.0 + mde, sd / math.sqrt(n)), sd)
            del summary["policy"]
            shipped += evaluate(summary)["decision"] == "SHIP"
        self.assertAlmostEqual(shipped / reps, 0.8, delta=0.04)

    def test_hold_reason_and_record_name_the_mde(self):
        summary = generate("flat")
        report = evaluate(summary)
        self.assertEqual(report["decision"], "HOLD")
        mde = status_of(report, "conversion")["mde"]
        self.assertIn(f"detectable improvement at 80% power: {mde:.4g}", report["reasons"][0])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli("--scenario", "flat", "--out", tmp)[0], 0)
            text = Path(tmp, "DECISION.md").read_text()
        self.assertIn("| Margin | MDE | Status |", text)
        self.assertIn("power 0.8", text)

    def test_rejects_invalid_power(self):
        for power in (0.0, 1.0, -0.5):
            with self.subTest(power=power), self.assertRaises(ValueError):
                stats.minimum_detectable_effect(1.0, 1.64, power)


class BatchInputTest(unittest.TestCase):
    def write(self, folder, name, **changes):
        summary = example()
        summary.update(changes)
        path = Path(folder, f"{name}.json")
        path.write_text(json.dumps(summary))
        return path

    def test_several_summaries_get_one_record_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self.write(tmp, "a", experiment="ranker-a")
            b = self.write(tmp, "b", experiment="ranker-b")
            out = Path(tmp, "out")
            code, stdout, _ = run_cli("--input", str(a), str(b), "--out", str(out), "--require-ship")
            self.assertEqual(code, 0)
            self.assertEqual([line.split(":")[0] for line in stdout.splitlines()], ["ranker-a", "ranker-b"])
            single = Path(tmp, "single")
            run_cli("--input", str(a), "--out", str(single))
            self.assertEqual((out / "ranker-a" / "decision.json").read_bytes(), (single / "decision.json").read_bytes())
            self.assertTrue((out / "ranker-b" / "DECISION.md").is_file())

    def test_require_ship_covers_the_whole_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            ship = self.write(tmp, "a", experiment="ships")
            hold = Path(tmp, "hold.json")
            hold.write_text(json.dumps(generate("flat")))
            code, stdout, _ = run_cli("--input", str(ship), str(hold), "--out", str(Path(tmp, "out")), "--require-ship")
            self.assertEqual(code, 1)
            self.assertIn("flat: HOLD", stdout)

    def test_invalid_batches_exit_2_and_write_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = self.write(tmp, "good", experiment="good")
            batches = {
                "invalid second summary": [good, self.write(tmp, "bad", experiment="bad", metrics={})],
                "unreadable second file": [good, Path(tmp, "missing.json")],
                "duplicate names": [good, self.write(tmp, "dup", experiment="good")],
                "names differing only in case": [good, self.write(tmp, "case", experiment="GOOD")],
                "path in the name": [good, self.write(tmp, "path", experiment="../escape")],
                "dot name": [good, self.write(tmp, "dot", experiment="..")],
                "hidden name": [good, self.write(tmp, "hidden", experiment=".git")],
                "missing name": [good, self.write(tmp, "unnamed")],
            }
            batches["missing name"][1].write_text(json.dumps({k: v for k, v in example().items() if k != "experiment"}))
            for i, (label, paths) in enumerate(batches.items()):
                with self.subTest(label):
                    out = Path(tmp, f"out-{i}")
                    code, stdout, err = run_cli("--input", *map(str, paths), "--out", str(out), "--require-ship")
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("error:", err)
                    self.assertFalse(out.exists())
            self.assertFalse(Path(tmp, "escape").exists())


if __name__ == "__main__":
    unittest.main()
