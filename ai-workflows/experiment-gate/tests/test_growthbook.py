"""``experiment-gate --from growthbook``: conversion of GrowthBook results exports.

The three ``ranker-v*.results.json`` files are the unmodified bodies of
``GET /api/v1/experiments/{id}/results`` from a throwaway self-hosted GrowthBook 5.1.0 whose warehouse held
synthetic events (see tests/fixtures/growthbook/README.md). They show that the importer reads the real
export shape; they are not evidence about any real experiment, user or model.
"""
import copy
import hashlib
import importlib.util
import io
import json
import math
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from expgate.decision import evaluate
from expgate.importers import growthbook
from expgate.run import main as run_main
from expgate.verify import main as verify_main

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "growthbook"

# name -> (GrowthBook's own reading, expgate's decision)
CASES = {"ranker-v2": ("SHIP", "SHIP"), "ranker-v3": ("SHIP", "HOLD"), "ranker-v4": ("HOLD", "SHIP")}


def export_bytes(name):
    return (FIXTURES / f"{name}.results.json").read_bytes()


def mapping():
    return json.loads((FIXTURES / "mapping.json").read_text(encoding="utf-8"))


def run_cli(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = run_main(args)
        except SystemExit as exc:  # argparse usage errors
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def verify_cli(path):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = verify_main([str(path)])
    return code, out.getvalue() + err.getvalue()


class Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name, content):
        path = self.tmp / name
        path.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode("utf-8"))
        return path

    def convert(self, export, mapping_doc=None):
        """Run the CLI on ``export`` (a dict or bytes); returns (code, stderr, record or None)."""
        out = self.tmp / "out"
        shutil.rmtree(out, ignore_errors=True)
        results = self.write("results.json", export)
        mapping_path = self.write("mapping.json", mapping() if mapping_doc is None else mapping_doc)
        code, _, err = run_cli(["--from", "growthbook", str(results), "--mapping", str(mapping_path),
                                "--out", str(out)])
        record = json.loads((out / "decision.json").read_text(encoding="utf-8")) if code == 0 else None
        if out.exists() and record is None:
            self.fail("a failed import left an output directory behind")
        return code, err, record


class FixtureConversionTest(Workspace):
    def test_each_captured_export_converts_into_a_record_that_verifies(self):
        for name, (_, decision) in CASES.items():
            with self.subTest(export=name):
                out = self.tmp / name
                code, stdout, err = run_cli(["--from", "growthbook", str(FIXTURES / f"{name}.results.json"),
                                             "--mapping", str(FIXTURES / "mapping.json"), "--out", str(out)])
                self.assertEqual(code, 0, err)
                self.assertTrue(stdout.startswith(f"{name}: {decision} "))
                record = json.loads((out / "decision.json").read_text(encoding="utf-8"))
                self.assertEqual(record["schema_version"], 3)
                self.assertEqual(record["decision"], decision)
                self.assertEqual(verify_cli(out / "decision.json"), (0, f"{out / 'decision.json'}: verified\n"))

    def test_record_keeps_the_sha256_of_the_exact_export_bytes(self):
        for name in CASES:
            with self.subTest(export=name):
                code, err, record = self.convert(export_bytes(name))
                self.assertEqual(code, 0, err)
                source = record["input"]["source"]
                self.assertEqual(source["format"], "growthbook")
                self.assertEqual(source["export_sha256"], hashlib.sha256(export_bytes(name)).hexdigest())
                self.assertIn(source["export_sha256"], (self.tmp / "out" / "DECISION.md").read_text(encoding="utf-8"))

    def test_the_digest_covers_bytes_not_meaning(self):
        original = export_bytes("ranker-v2")
        reformatted = json.dumps(json.loads(original), indent=4).encode("utf-8")
        self.assertNotEqual(original, reformatted)
        first = self.convert(original)[2]
        second = self.convert(reformatted)[2]
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertNotEqual(first["input"]["source"]["export_sha256"], second["input"]["source"]["export_sha256"])
        self.assertNotEqual(first["input_sha256"], second["input_sha256"])

    def test_field_mapping(self):
        export = json.loads(export_bytes("ranker-v2"))
        by_id = {m["metricId"]: m for m in export["result"]["results"][0]["metrics"]}
        record = self.convert(export_bytes("ranker-v2"))[2]
        summary = record["input"]
        self.assertEqual(summary["experiment"], "ranker-v2")
        self.assertEqual(summary["assignment"], {"expected_treatment_share": 0.5})
        self.assertEqual(set(summary["metrics"]), {"purchase_rate", "refund_rate", "page_load_ms", "average_order_value"})
        self.assertEqual({n: s["role"] for n, s in summary["metrics"].items()},
                         {"purchase_rate": "primary", "refund_rate": "guardrail",
                          "page_load_ms": "guardrail", "average_order_value": "guardrail"})
        self.assertEqual(summary["metrics"]["refund_rate"]["margin"], 0.005)
        ids = {name: metric_id for metric_id, entry in mapping()["metrics"].items() for name in [entry["name"]]}
        for arm, index in (("control", 0), ("treatment", 1)):
            exported = {name: by_id[metric_id]["variations"][index] for name, metric_id in ids.items()}
            stats = summary["arms"][arm]["metrics"]
            self.assertEqual(summary["arms"][arm]["units"], exported["purchase_rate"]["users"])
            self.assertEqual(stats["purchase_rate"]["successes"], exported["purchase_rate"]["analyses"][0]["numerator"])
            self.assertEqual(stats["page_load_ms"]["mean"], exported["page_load_ms"]["analyses"][0]["mean"])
            self.assertEqual(stats["page_load_ms"]["sd"], exported["page_load_ms"]["analyses"][0]["stddev"])
            ratio = stats["average_order_value"]
            analysis = exported["average_order_value"]["analyses"][0]
            users = summary["arms"][arm]["units"]
            self.assertAlmostEqual(ratio["numerator"]["mean"], analysis["numerator"] / users, places=9)
            self.assertAlmostEqual(ratio["denominator"]["mean"], analysis["denominator"] / users, places=9)

    def test_ratio_metric_keeps_growthbooks_per_unit_standard_deviation(self):
        record = self.convert(export_bytes("ranker-v3"))[2]
        export = json.loads(export_bytes("ranker-v3"))
        metric = next(m for m in export["result"]["results"][0]["metrics"] if m["metricName"] == "Average order value")
        sd = [v["analyses"][0]["stddev"] for v in metric["variations"]]
        users = record["input"]["arms"]["control"]["units"]
        row = next(r for r in record["metrics"] if r["metric"] == "average_order_value")
        self.assertAlmostEqual(row["se"], math.hypot(*sd) / math.sqrt(users), places=9)
        self.assertAlmostEqual(row["control"], metric["variations"][0]["analyses"][0]["mean"], places=9)
        self.assertAlmostEqual(row["treatment"], metric["variations"][1]["analyses"][0]["mean"], places=9)

    def test_secondary_metrics_are_not_imported(self):
        record = self.convert(export_bytes("ranker-v2"))[2]
        self.assertNotIn("revenue_per_user", record["input"]["metrics"])
        self.assertNotIn("Revenue per user", record["input"]["metrics"])

    def test_require_ship_follows_expgate_not_growthbook(self):
        args = ["--from", "growthbook", None, "--mapping", str(FIXTURES / "mapping.json"), "--require-ship"]
        for name, (_, decision) in CASES.items():
            with self.subTest(export=name):
                args[2] = str(FIXTURES / f"{name}.results.json")
                code, _, err = run_cli([*args, "--out", str(self.tmp / name)])
                self.assertEqual(code, 0 if decision == "SHIP" else 1, err)


class PolicyDifferenceTest(Workspace):
    """Where GrowthBook's own statistics and expgate's frozen policy disagree, the record says why."""

    def reasons(self, name):
        code, err, record = self.convert(export_bytes(name))
        self.assertEqual(code, 0, err)
        return record, record["reasons"]

    def test_growthbook_reading_is_recorded_for_every_import(self):
        for name, (reading, _) in CASES.items():
            with self.subTest(export=name):
                record = self.reasons(name)[0]
                self.assertEqual(record["input"]["source"]["reading"]["decision"], reading)
                self.assertTrue(record["input"]["source"]["reading"]["basis"])

    def test_agreement_adds_no_reason(self):
        _, reasons = self.reasons("ranker-v2")
        self.assertEqual(reasons, ["primary metric improved and all guardrails are non-inferior"])

    def test_growthbook_ships_but_a_guardrail_is_not_shown_non_inferior(self):
        record, reasons = self.reasons("ranker-v3")
        self.assertEqual(record["decision"], "HOLD")
        self.assertIn("GrowthBook's own statistics read as SHIP; expgate decided HOLD", reasons)
        difference = next(r for r in reasons if r.startswith("policy difference: guardrail page_load_ms"))
        self.assertIn("GrowthBook reports no significant degradation (two-sided p 0.1456 >= 0.05)", difference)
        self.assertIn("non-inferior", difference)
        self.assertIn("margin 4", difference)
        row = next(r for r in record["metrics"] if r["metric"] == "page_load_ms")
        self.assertEqual(row["status"], "INCONCLUSIVE")
        # GrowthBook sees the primary metric as a clear win, so it is not what separates the two.
        self.assertEqual(next(r for r in record["metrics"] if r["metric"] == "purchase_rate")["status"], "IMPROVED")

    def test_growthbook_sees_no_significant_effect_but_expgate_tests_one_sided(self):
        record, reasons = self.reasons("ranker-v4")
        self.assertEqual(record["decision"], "SHIP")
        self.assertIn("GrowthBook's own statistics read as HOLD; expgate decided SHIP", reasons)
        difference = next(r for r in reasons if r.startswith("policy difference: primary purchase_rate"))
        self.assertIn("two-sided p 0.09086 >= 0.05", difference)
        self.assertIn("one-sided at alpha 0.05", difference)
        # Not "GrowthBook's p / 2": half of 0.0909 is 0.0454, expgate's one-sided p is 0.0413 (a different
        # estimator). What matters is that the two-sided p is above alpha and the one-sided reading is below it.
        export = json.loads(export_bytes("ranker-v4"))
        p_two_sided = export["result"]["results"][0]["metrics"][0]["variations"][1]["analyses"][0]["pValue"]
        self.assertGreater(p_two_sided, 0.05)
        self.assertLess(p_two_sided / 2, 0.05)

    def test_replay_reproduces_the_policy_difference_reasons(self):
        for name in ("ranker-v3", "ranker-v4"):
            with self.subTest(export=name):
                record = self.reasons(name)[0]
                self.assertEqual(evaluate(record["input"])["reasons"], record["reasons"])

    def test_decision_does_not_depend_on_growthbooks_statistics(self):
        export = json.loads(export_bytes("ranker-v4"))
        for variation in export["result"]["results"][0]["metrics"][0]["variations"]:
            for analysis in variation["analyses"]:
                analysis.update(pValue=1e-9, ciLow=0.5, ciHigh=0.6, percentChange=0.55)
        record = self.convert(export)[2]
        self.assertEqual(record["decision"], "SHIP")
        self.assertEqual(record["input"]["source"]["reading"]["decision"], "SHIP")
        self.assertEqual(record["reasons"], ["primary metric improved and all guardrails are non-inferior"])

    def test_sample_ratio_comes_from_the_asserted_allocation(self):
        export = json.loads(export_bytes("ranker-v2"))
        control, treatment = export["experiment"]["phases"][0]["trafficSplit"]
        control["weight"], treatment["weight"] = 0.8, 0.2
        doc = mapping()
        doc["snapshot"]["expected_treatment_share"] = 0.2
        record = self.convert(export, doc)[2]  # an edited export: this exercises the code path only
        self.assertEqual(record["decision"], "INVALID")
        self.assertEqual(record["input"]["assignment"]["expected_treatment_share"], 0.2)

    def test_bayesian_export_reads_chance_to_beat_control(self):
        record = self.reasons("ranker-v2")[0]
        basis = record["input"]["source"]["reading"]["basis"]
        self.assertEqual(record["input"]["source"]["stats_engine"], "bayesian")
        self.assertTrue(any("chance to beat control" in line for line in basis))
        export = json.loads(export_bytes("ranker-v2"))
        export["result"]["results"][0]["metrics"][0]["variations"][1]["analyses"][0]["chanceToBeatControl"] = 0.7
        edited = self.convert(export, None)
        self.assertEqual(edited[0], 0)  # decisions never read the Bayesian numbers
        self.assertEqual(edited[2]["decision"], "SHIP")
        self.assertEqual(edited[2]["input"]["source"]["reading"]["decision"], "HOLD")
        self.assertTrue(any("expgate does not" in r or "GrowthBook's own statistic is not used" in r
                            for r in edited[2]["reasons"]))


class RecordIntegrityTest(Workspace):
    def record(self, name="ranker-v3"):
        return self.convert(export_bytes(name))[2]

    def verify_text(self, record):
        path = self.write("edited.json", record)
        return verify_cli(path)[0]

    def test_editing_the_recorded_digest_or_reading_exits_1(self):
        record = self.record()
        digest = copy.deepcopy(record)
        digest["input"]["source"]["export_sha256"] = "0" * 64
        reading = copy.deepcopy(record)
        reading["input"]["source"]["reading"]["differences"][0] += " (edited)"
        for label, edited in (("digest", digest), ("reading", reading)):
            with self.subTest(edit=label):
                self.assertEqual(self.verify_text(edited), 1)
        self.assertEqual(self.verify_text(record), 0)

    def test_source_needs_schema_3(self):
        summary = self.record()["input"]
        with self.assertRaisesRegex(ValueError, "schema_version 3"):
            evaluate(summary, schema_version=2)

    def test_source_is_validated(self):
        base = self.record("ranker-v2")["input"]
        bad = {
            "unknown key": lambda s: s.update(extra=1),
            "format": lambda s: s.update(format="optimizely"),
            "digest": lambda s: s.update(export_sha256="ABC"),
            "engine": lambda s: s.update(stats_engine="bandit"),
            "reading decision": lambda s: s["reading"].update(decision="MAYBE"),
            "reading differences": lambda s: s["reading"].update(differences="no"),
            "reading key": lambda s: s["reading"].update(chance=1),
            "asserted share": lambda s: s["asserted"].update(expected_treatment_share=0),
            "asserted adjustment": lambda s: s["asserted"].update(regression_adjustment=True),
            "asserted key": lambda s: s["asserted"].update(extra=1),
            "asserted type": lambda s: s.update(asserted=[]),
        }
        for label, edit in bad.items():
            with self.subTest(case=label):
                summary = copy.deepcopy(base)
                edit(summary["source"])
                with self.assertRaises(ValueError):
                    evaluate(summary)

    def test_importing_does_not_change_the_decision_of_the_converted_summary(self):
        for name, (_, decision) in CASES.items():
            summary = self.record(name)["input"]
            without = {key: value for key, value in summary.items() if key != "source"}
            self.assertEqual(evaluate(without)["decision"], decision)


class MalformedExportTest(Workspace):
    def fixture(self, name="ranker-v3"):
        return json.loads(export_bytes(name))

    def assert_rejected(self, export, message, mapping_doc=None):
        code, err, record = self.convert(export, mapping_doc)
        self.assertEqual(code, 2, err)
        self.assertIsNone(record)
        self.assertIn(message, err)
        self.assertIn("cannot import GrowthBook export", err)

    def test_not_json_or_not_an_export(self):
        good = export_bytes("ranker-v3")
        cases = {
            "": "not valid JSON",
            b"": "not valid JSON",
            good[: len(good) // 2]: "not valid JSON",
            b"\xff\xfe": "not UTF-8",
            b"[]": "must be a JSON object",
            b'{"result": {}}': "GET /api/v1/experiments/{id}/results",
            b'{"experiment": {}, "result": {"results": []}}': "result.dimension must be a JSON object",
            b'{"a": 1, "a": 2}': "duplicate object key",
            b'{"a": NaN}': "non-finite number NaN",
        }
        for content, message in cases.items():
            with self.subTest(content=content[:30]):
                self.assert_rejected(content if isinstance(content, bytes) else content.encode(), message)

    def test_unsupported_experiments(self):
        def three_variations(d):
            d["experiment"]["variations"].append({"variationId": "var_x", "key": "2", "name": "Third"})
        def bandit(d):
            d["experiment"]["type"] = "multi-armed-bandit"
        def dimension(d):
            d["result"]["dimension"] = {"type": "experiment", "id": "country"}
        def cuped(d):
            d["experiment"]["settings"]["regressionAdjustmentEnabled"] = True
        def cuped_in_result(d):
            d["result"]["settings"]["regressionAdjustmentEnabled"] = True
        def sequential(d):
            d["result"]["settings"]["sequentialTestingEnabled"] = True
        def metric_override(d):
            d["experiment"]["settings"]["metricOverrides"] = [
                {"id": "x", "regressionAdjustmentOverride": True, "regressionAdjustmentEnabled": True}]
        def metric_cuped(d):
            d["result"]["settings"]["goals"][0]["overrides"]["regressionAdjustmentEnabled"] = True
        def two_rows(d):
            d["result"]["results"].append(copy.deepcopy(d["result"]["results"][0]))
        def no_engine(d):
            del d["result"]["settings"]["statsEngine"]
        cases = [(three_variations, "only two-variation"), (bandit, "not supported"),
                 (dimension, "broken down by dimension"), (cuped, "regressionAdjustmentEnabled"),
                 (cuped_in_result, "regressionAdjustmentEnabled"), (sequential, "sequentialTestingEnabled"),
                 (metric_override, "regression adjustment override"), (metric_cuped, "regression adjustment"),
                 (two_rows, "expected exactly one overall row"), (no_engine, "statsEngine")]
        for edit, message in cases:
            with self.subTest(case=edit.__name__):
                export = self.fixture()
                edit(export)
                self.assert_rejected(export, message)

    def test_inconsistent_metric_data(self):
        def metric(d, name="Purchase rate"):
            return next(m for m in d["result"]["results"][0]["metrics"] if m["metricName"] == name)
        def fractional_successes(d):
            metric(d)["variations"][0]["analyses"][0]["numerator"] = 1986.5
        def too_many_successes(d):
            metric(d)["variations"][0]["analyses"][0]["numerator"] = 99999
        def wrong_mean(d):
            metric(d)["variations"][0]["analyses"][0]["mean"] = 0.5
        def wrong_sd(d):
            metric(d)["variations"][0]["analyses"][0]["stddev"] = 7
        def ratio_without_denominator(d):
            metric(d, "Average order value")["variations"][0]["analyses"][0]["denominator"] = 0
        def metric_error(d):
            metric(d)["variations"][1]["analyses"][0]["errorMessage"] = "query failed"
        def missing_variation(d):
            metric(d)["variations"].pop()
        def user_counts_differ(d):
            metric(d, "Page load ms")["variations"][0]["users"] = 19999
        def missing_stat(d):
            del metric(d)["variations"][0]["analyses"][0]["stddev"]
        def non_finite(d):
            metric(d)["variations"][0]["analyses"][0]["mean"] = "NaN"
        def no_analysis(d):
            metric(d)["variations"][0]["analyses"] = []
        def unknown_variation(d):
            metric(d)["variations"][0]["variationId"] = "var_other"
        def no_traffic_split(d):
            del d["experiment"]["phases"][0]["trafficSplit"]
        def bad_phase(d):
            d["result"]["phase"] = "7"
        def overflowing_sd(d):
            metric(d, "Page load ms")["variations"][0]["analyses"][0]["stddev"] = 1e200
        cases = [(overflowing_sd, "not valid input"), (fractional_successes, "whole number"), (too_many_successes, "exceed"),
                 (wrong_mean, "is not successes/users"), (wrong_sd, "not that of a proportion"),
                 (ratio_without_denominator, "positive exported denominator"), (metric_error, "query failed"),
                 (missing_variation, "has results for variations"), (user_counts_differ, "differs from"),
                 (missing_stat, "stddev must be a finite number"), (non_finite, "mean must be a finite number"),
                 (no_analysis, "has no analyses"), (unknown_variation, "has results for variations"),
                 (no_traffic_split, "trafficSplit must be a JSON array"), (bad_phase, "result.phase")]
        for edit, message in cases:
            with self.subTest(case=edit.__name__):
                export = self.fixture()
                edit(export)
                self.assert_rejected(export, message)

    def test_a_metric_mapped_to_the_wrong_type_is_caught(self):
        for name, wrong, message in (("page_load_ms", "proportion", "numerator"),
                                     ("average_order_value", "mean", "only a ratio metric has"),
                                     ("page_load_ms", "ratio", "positive exported denominator"),
                                     ("purchase_rate", "ratio", "positive exported denominator")):
            with self.subTest(metric=name, mapped_as=wrong):
                doc = mapping()
                entry = next(e for e in doc["metrics"].values() if e["name"] == name)
                entry["type"] = wrong
                self.assert_rejected(self.fixture(), message, doc)

    def test_mean_metric_mapped_as_proportion_with_integral_sum_is_still_caught(self):
        export = self.fixture()
        load = next(m for m in export["result"]["results"][0]["metrics"] if m["metricName"] == "Page load ms")
        for variation in load["variations"]:
            variation["analyses"][0]["numerator"] = 100.0
            variation["analyses"][0]["mean"] = 100.0 / variation["users"]
        doc = mapping()
        next(e for e in doc["metrics"].values() if e["name"] == "page_load_ms")["type"] = "proportion"
        self.assert_rejected(export, "not that of a proportion", doc)


class MappingTest(Workspace):
    def assert_rejected(self, mapping_doc, message):
        code, err, record = self.convert(export_bytes("ranker-v3"), mapping_doc)
        self.assertEqual(code, 2, err)
        self.assertIsNone(record)
        self.assertIn(message, err)

    def test_invalid_mapping_files(self):
        def edit(change):
            doc = mapping()
            change(doc)
            return doc
        by_name = lambda doc, name: next(e for e in doc["metrics"].values() if e["name"] == name)
        cases = [
            (edit(lambda d: d.update(metrics={})), "at least one metric"),
            (edit(lambda d: d.pop("snapshot")), "mapping 'snapshot'"),
            (edit(lambda d: d.update(extra=1)), "unknown keys"),
            (edit(lambda d: by_name(d, "purchase_rate").update(type="count")), "type must be"),
            (edit(lambda d: by_name(d, "purchase_rate").pop("direction")), "direction must be"),
            (edit(lambda d: by_name(d, "refund_rate").pop("margin")), "needs a 'margin'"),
            (edit(lambda d: by_name(d, "refund_rate").update(margin=-1)), "margin must be non-negative"),
            (edit(lambda d: by_name(d, "purchase_rate").update(margin=0.1)), "takes no margin"),
            (edit(lambda d: by_name(d, "purchase_rate").update(extra=1)), "unknown keys"),
            (edit(lambda d: d.update(policy={"alpah": 0.1})), "unknown keys"),
            (edit(lambda d: d.update(growthbook={"alpha": 2})), "must be in (0, 1)"),
            (edit(lambda d: d.update(policy={"alpha": 2})), "alpha must be in (0, 1)"),
            (edit(lambda d: d.update(policy={"sequential": {"planned_units": 5}})), "unknown keys"),
            (edit(lambda d: d["metrics"].pop(next(i for i, e in d["metrics"].items() if e["name"] == "refund_rate"))),
             "needs an entry under 'metrics'"),
            (edit(lambda d: d["metrics"].update({"fact__unknown": {"type": "mean", "direction": "increase"}})),
             "does not use"),
            (edit(lambda d: d.update(primary="fact__nope")), "not one of the export's goal metrics"),
            (edit(lambda d: by_name(d, "page_load_ms").update(name="purchase_rate")), "distinct 'name' values"),
        ]
        for doc, message in cases:
            with self.subTest(message=message):
                self.assert_rejected(doc, message)

    def test_unreadable_or_invalid_mapping_file(self):
        results = self.write("results.json", export_bytes("ranker-v3"))
        for content, message in ((b"not json", "not valid JSON"), (b"[]", "must be a JSON object")):
            with self.subTest(content=content):
                mapping_path = self.write("mapping.json", content)
                code, _, err = run_cli(["--from", "growthbook", str(results), "--mapping", str(mapping_path),
                                        "--out", str(self.tmp / "out")])
                self.assertEqual(code, 2)
                self.assertIn(message, err)
        code, _, err = run_cli(["--from", "growthbook", str(results), "--mapping", str(self.tmp / "missing.json"),
                                "--out", str(self.tmp / "out")])
        self.assertEqual(code, 2)
        self.assertIn("missing.json", err)
        code, _, err = run_cli(["--from", "growthbook", str(self.tmp / "missing.json"),
                                "--mapping", str(FIXTURES / "mapping.json"), "--out", str(self.tmp / "out")])
        self.assertEqual(code, 2)
        self.assertIn("missing.json", err)
        self.assertFalse((self.tmp / "out").exists())

    def test_several_goal_metrics_need_an_explicit_primary(self):
        export = json.loads(export_bytes("ranker-v3"))
        goals = export["result"]["settings"]["goals"]
        secondary = export["result"]["settings"]["secondaryMetrics"][0]
        goals.append(copy.deepcopy(secondary))
        code, err, _ = self.convert(export)
        self.assertEqual(code, 2)
        self.assertIn("set 'primary' in the mapping", err)
        doc = mapping()
        doc["primary"] = goals[0]["metricId"]
        code, err, record = self.convert(export, doc)
        self.assertEqual(code, 0, err)
        self.assertEqual(record["decision"], "HOLD")

    def test_no_goal_metric(self):
        export = json.loads(export_bytes("ranker-v3"))
        export["result"]["settings"]["goals"] = []
        code, err, _ = self.convert(export)
        self.assertEqual(code, 2)
        self.assertIn("no goal metric", err)

    def test_policy_settings_flow_into_the_record(self):
        doc = mapping()
        doc["policy"] = {"alpha": 0.1, "power": 0.9}
        doc["growthbook"] = {"alpha": 0.1}
        record = self.convert(export_bytes("ranker-v4"), doc)[2]
        self.assertEqual(record["policy"]["alpha"], 0.1)
        self.assertEqual(record["policy"]["power"], 0.9)
        self.assertEqual(record["input"]["source"]["reading"]["alpha"], 0.1)
        # At 0.1 GrowthBook's two-sided p 0.0909 is significant too, so the readings now agree.
        self.assertEqual(record["input"]["source"]["reading"]["decision"], "SHIP")

    def test_usage_errors_exit_2(self):
        results = str(FIXTURES / "ranker-v2.results.json")
        mapping_path = str(FIXTURES / "mapping.json")
        cases = [
            (["--from", "growthbook", results, "--out", str(self.tmp / "a")], "--from needs --mapping"),
            (["--scenario", "win", "--mapping", mapping_path, "--out", str(self.tmp / "b")], "only used with --from"),
            (["--from", "optimizely", results, "--mapping", mapping_path, "--out", str(self.tmp / "c")],
             "unsupported --from format"),
            (["--from", "growthbook", "--mapping", mapping_path, "--out", str(self.tmp / "d")], "error:"),
            (["--from", "growthbook", results, "--input", results, "--mapping", mapping_path,
              "--out", str(self.tmp / "e")], "not allowed with"),
        ]
        for args, message in cases:
            with self.subTest(args=args[:3]):
                code, _, err = run_cli(args)
                self.assertEqual(code, 2)
                self.assertIn(message, err)


class SnapshotProvenanceTest(Workspace):
    """GrowthBook pairs the latest successful snapshot with the experiment's CURRENT settings (growthbook
    7cbc85d1: getExperimentResults.ts, services/experiments.ts toSnapshotApiInterface), so the export cannot
    show how the snapshot was computed. The mapping asserts it and the importer refuses contradictions."""

    def rejected(self, export, message, mapping_doc=None):
        code, err, record = self.convert(export, mapping_doc)
        self.assertEqual(code, 2, err)
        self.assertIsNone(record)
        self.assertIn(message, err)

    def test_assertions_are_recorded_as_asserted(self):
        record = self.convert(export_bytes("ranker-v2"))[2]
        self.assertEqual(record["input"]["source"]["asserted"],
                         {"expected_treatment_share": 0.5, "regression_adjustment": False})
        self.assertEqual(record["input"]["assignment"]["expected_treatment_share"], 0.5)

    def test_the_mapping_must_make_both_assertions(self):
        for label, edit, message in (
            ("no snapshot block", lambda d: d.pop("snapshot"), "mapping 'snapshot'"),
            ("no share", lambda d: d["snapshot"].pop("expected_treatment_share"), "expected_treatment_share is required"),
            ("share 1", lambda d: d["snapshot"].update(expected_treatment_share=1), "must be in (0, 1)"),
            ("share text", lambda d: d["snapshot"].update(expected_treatment_share="0.5"), "finite number"),
            ("no adjustment", lambda d: d["snapshot"].pop("regression_adjustment"), "regression_adjustment must be false"),
            ("adjusted", lambda d: d["snapshot"].update(regression_adjustment=True), "regression_adjustment must be false"),
            ("typo", lambda d: d["snapshot"].update(regresion_adjustment=False), "unknown keys"),
        ):
            with self.subTest(case=label):
                doc = mapping()
                edit(doc)
                self.rejected(export_bytes("ranker-v3"), message, doc)

    def test_weights_edited_after_the_snapshot_are_refused_not_turned_into_invalid(self):
        # A within-phase weight edit leaves the snapshot's counts alone but changes trafficSplit.
        export = json.loads(export_bytes("ranker-v2"))
        control, treatment = export["experiment"]["phases"][0]["trafficSplit"]
        control["weight"], treatment["weight"] = 0.8, 0.2
        self.rejected(export, "contradicts the experiment's current allocation weights")
        code, err, _ = self.convert(export)
        self.assertIn("refresh the analysis", err)

    def test_a_real_allocation_change_is_imported_when_the_operator_asserts_it(self):
        export = json.loads(export_bytes("ranker-v2"))
        control, treatment = export["experiment"]["phases"][0]["trafficSplit"]
        control["weight"], treatment["weight"] = 0.8, 0.2
        doc = mapping()
        doc["snapshot"]["expected_treatment_share"] = 0.2
        record = self.convert(export, doc)[2]  # edited export: exercises the sample-ratio path only
        self.assertEqual(record["decision"], "INVALID")
        self.assertEqual(record["input"]["assignment"]["expected_treatment_share"], 0.2)
        self.assertIn("GrowthBook's own statistics read as SHIP; expgate decided INVALID", record["reasons"])
        self.assertTrue(any(r.startswith("policy difference: sample ratio") for r in record["reasons"]))

    def test_adjustment_switched_on_after_the_snapshot_is_refused(self):
        for where in ("experiment", "result"):
            with self.subTest(where=where):
                export = json.loads(export_bytes("ranker-v3"))
                export[where]["settings"]["regressionAdjustmentEnabled"] = True
                self.rejected(export, "refresh the analysis")

    def test_metric_level_adjustment_override_is_refused(self):
        export = json.loads(export_bytes("ranker-v3"))
        export["experiment"]["settings"]["metricOverrides"] = [
            {"id": "fact__x", "regressionAdjustmentOverride": True, "regressionAdjustmentEnabled": True}]
        self.rejected(export, "regression adjustment override")

    def test_post_stratification_is_not_refused(self):
        # It is on by default in GrowthBook and affects only GrowthBook's own effect estimate, not the arm aggregates.
        for value in (True, False, None):
            with self.subTest(value=value):
                export = json.loads(export_bytes("ranker-v3"))
                export["experiment"]["settings"]["postStratificationEnabled"] = value
                self.assertEqual(self.convert(export)[0], 0)


class StrictFieldTest(Workspace):
    def rejected(self, export, message):
        code, err, record = self.convert(export)
        self.assertEqual(code, 2, err)
        self.assertIsNone(record)
        self.assertIn(message, err)

    def metric(self, export, name="Purchase rate"):
        return next(m for m in export["result"]["results"][0]["metrics"] if m["metricName"] == name)

    def test_a_repeated_variation_entry_is_not_silently_overwritten(self):
        export = json.loads(export_bytes("ranker-v4"))
        variations = self.metric(export)["variations"]
        extra = copy.deepcopy(variations[1])
        extra["analyses"][0]["numerator"] = 200  # contradictory 1% conversion for the same variation id
        extra["analyses"][0]["mean"] = 0.01
        extra["analyses"][0]["stddev"] = math.sqrt(0.01 * 0.99)
        variations.append(extra)
        self.rejected(export, "more than one result for variation")

    def test_a_third_variation_entry_is_refused(self):
        export = json.loads(export_bytes("ranker-v4"))
        variations = self.metric(export)["variations"]
        third = copy.deepcopy(variations[1])
        third["variationId"] = "var_other"
        variations.append(third)
        self.rejected(export, "expected exactly")

    def test_phase_must_be_a_valid_index_string(self):
        for phase, message in (("-1", "result.phase"), (0.5, "result.phase"), (True, "result.phase"),
                               (0, "result.phase"), ("0.5", "result.phase"), ("00", "result.phase"),
                               (" 0", "result.phase"), ("1", "1 entries"), ("", "result.phase"), (None, "result.phase")):
            with self.subTest(phase=phase):
                export = json.loads(export_bytes("ranker-v4"))
                export["result"]["phase"] = phase
                self.rejected(export, message)

    def test_phase_selects_the_named_phase_not_the_last(self):
        export = json.loads(export_bytes("ranker-v4"))
        first = export["experiment"]["phases"][0]
        second = copy.deepcopy(first)
        second["trafficSplit"][0]["weight"], second["trafficSplit"][1]["weight"] = 0.8, 0.2
        export["experiment"]["phases"].append(second)
        export["result"]["phase"] = "0"
        self.assertEqual(self.convert(export)[0], 0)  # phase 0 keeps the asserted 0.5
        export["result"]["phase"] = "1"
        self.rejected(export, "contradicts the experiment's current allocation weights")

    def test_probabilities_must_lie_in_zero_one(self):
        def treatment(export):
            return self.metric(export)["variations"][1]["analyses"][0]
        cases = (("p below 0", "ranker-v4", lambda d: treatment(d).update(pValue=-0.5), "pValue"),
                 ("p above 1", "ranker-v4", lambda d: treatment(d).update(pValue=1.5), "pValue"),
                 ("srm below 0", "ranker-v4", lambda d: d["result"]["results"][0]["checks"].update(srm=-0.5), "checks.srm"),
                 ("srm above 1", "ranker-v4", lambda d: d["result"]["results"][0]["checks"].update(srm=2), "checks.srm"),
                 ("chance below 0", "ranker-v2", lambda d: treatment(d).update(chanceToBeatControl=-0.1), "chanceToBeatControl"),
                 ("chance above 1", "ranker-v2", lambda d: treatment(d).update(chanceToBeatControl=1.0001), "chanceToBeatControl"))
        for label, name, edit, message in cases:
            with self.subTest(case=label):
                export = json.loads(export_bytes(name))
                edit(export)
                self.rejected(export, message)

    def test_probability_bounds_are_inclusive(self):
        export = json.loads(export_bytes("ranker-v4"))
        export["result"]["results"][0]["checks"]["srm"] = 1
        self.metric(export)["variations"][1]["analyses"][0]["pValue"] = 0
        self.assertEqual(self.convert(export)[0], 0)


def _load_schema_validation():
    """The dev-only validator helper; None when jsonschema is not installed."""
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return None
    spec = importlib.util.spec_from_file_location("expgate_schema_validation", Path(__file__).with_name("schema_validation.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema_validation = _load_schema_validation()


@unittest.skipIf(schema_validation is None, "jsonschema is not installed (dev and CI only)")
class ImportedRecordSchemaTest(Workspace):
    def test_imported_records_validate_against_the_v3_schema(self):
        for name in CASES:
            with self.subTest(export=name):
                record = self.convert(export_bytes(name))[2]
                self.assertEqual(schema_validation.errors(record, 3), [])

    def test_a_malformed_source_does_not_validate(self):
        record = self.convert(export_bytes("ranker-v3"))[2]
        edits = {
            "digest": lambda s: s.update(export_sha256="xyz"),
            "format": lambda s: s.update(format="other"),
            "extra": lambda s: s.update(extra=1),
            "reading": lambda s: s["reading"].update(decision="MAYBE"),
            "asserted share": lambda s: s["asserted"].update(expected_treatment_share=1),
            "asserted adjustment": lambda s: s["asserted"].update(regression_adjustment=True),
            "asserted missing": lambda s: s["asserted"].pop("regression_adjustment"),
        }
        for label, edit in edits.items():
            with self.subTest(edit=label):
                edited = copy.deepcopy(record)
                edit(edited["input"]["source"])
                self.assertNotEqual(schema_validation.errors(edited, 3), [])


class ImporterApiTest(unittest.TestCase):
    def test_convert_returns_a_summary_that_evaluate_accepts(self):
        summary = growthbook.convert(export_bytes("ranker-v2"), growthbook.load_mapping(json.dumps(mapping()).encode()))
        self.assertEqual(evaluate(summary)["decision"], "SHIP")

    def test_import_errors_are_value_errors(self):
        self.assertTrue(issubclass(growthbook.GrowthBookImportError, ValueError))


if __name__ == "__main__":
    unittest.main()
