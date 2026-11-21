"""Schema 2 (python-json-v1) and schema 3 (RFC 8785) record behaviour."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from expgate import verify_record
from expgate.decision import evaluate
from expgate.jcs import canonicalize
from expgate.records import input_digest
from expgate.run import main as run_main
from expgate.verify import load_record, main as verify_main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def summary(name="offer-ranker-v2.json"):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def verify_text(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "decision.json")
        path.write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = verify_main([str(path)])
        return code, out.getvalue() + err.getvalue()


class SchemaThreeTest(unittest.TestCase):
    def test_new_records_use_jcs_digest(self):
        value = summary()
        # Integral floats and non-ASCII keys are where RFC 8785 and python-json-v1 differ.
        value["metrics"]["latency_ms"]["margin"] = 2.0
        value["description"] = "\U0001f600 <&> \u2028"
        record = evaluate(value)
        self.assertEqual(record["schema_version"], 3)
        self.assertEqual(record["input_sha256"], hashlib.sha256(canonicalize(value)).hexdigest())
        self.assertNotEqual(record["input_sha256"], evaluate(value, schema_version=2)["input_sha256"])
        self.assertEqual(verify_record(record), [])

    def test_float_and_integer_spellings_are_one_input(self):
        a, b = summary(), summary()
        a["metrics"]["latency_ms"]["margin"] = 2.0
        b["metrics"]["latency_ms"]["margin"] = 2
        self.assertEqual(evaluate(a)["input_sha256"], evaluate(b)["input_sha256"])

    def test_run_writes_schema_3_that_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_main(["--scenario", "win", "--out", tmp]), 0)
            text = Path(tmp, "decision.json").read_text(encoding="utf-8")
            self.assertEqual(json.loads(text)["schema_version"], 3)
            self.assertEqual(verify_text(text)[0], 0)

    def test_replay_comparison_ignores_number_spelling(self):
        record = evaluate(summary())
        text = json.dumps(record).replace('"alpha": 0.05', '"alpha": 0.050')
        self.assertEqual(verify_text(text)[0], 0)

    def test_edits_exit_1(self):
        record = evaluate(summary())
        stale = copy.deepcopy(record)
        stale["input"]["arms"]["control"]["metrics"]["conversion"]["successes"] += 1
        redigested = copy.deepcopy(stale)
        redigested["input_sha256"] = hashlib.sha256(canonicalize(redigested["input"])).hexdigest()
        decision = {**record, "decision": "ROLLBACK"}
        for name, case in (("stale", stale), ("redigested", redigested), ("decision", decision)):
            with self.subTest(case=name):
                code, message = verify_text(json.dumps(case))
                self.assertEqual(code, 1, message)
        self.assertIn("input_sha256", verify_text(json.dumps(stale))[1])
        self.assertNotIn("input_sha256", verify_text(json.dumps(redigested))[1])

    def test_duplicate_keys_exit_2_for_schema_3_only(self):
        text = json.dumps(evaluate(summary()), indent=2)
        duplicated = text.replace('"decision": "', '"decision": "HOLD",\n  "decision": "', 1)
        self.assertNotEqual(text, duplicated)
        code, message = verify_text(duplicated)
        self.assertEqual(code, 2)
        self.assertIn("duplicate object key", message)
        nested = text.replace('"units": ', '"units": 1,\n "units": ', 1)
        self.assertEqual(verify_text(nested)[0], 2)
        with self.assertRaises(ValueError):
            load_record(duplicated)
        # Schema 2 keeps the lenient last-key-wins reading of the original release.
        legacy = json.dumps(evaluate(summary(), schema_version=2), indent=2)
        legacy = legacy.replace('"decision": "', '"decision": "HOLD",\n  "decision": "', 1)
        self.assertEqual(verify_text(legacy)[0], 0)

    def test_non_finite_numbers_exit_2(self):
        record = evaluate(summary())
        text = json.dumps(record)
        for literal in ("NaN", "Infinity", "-Infinity", "1e999"):
            for target in ('"alpha": 0.05', '"units": 50210'):
                if target not in text:
                    continue
                with self.subTest(literal=literal, target=target):
                    changed = text.replace(target, target.split(":")[0] + ": " + literal, 1)
                    code, message = verify_text(changed)
                    self.assertEqual(code, 2, message)

    def test_schema_3_requires_exact_integer_version(self):
        record = evaluate(summary())
        for version in (True, 3.0, "3", None):
            with self.subTest(version=version):
                self.assertEqual(verify_text(json.dumps({**record, "schema_version": version}))[0], 2)

    def test_integers_beyond_the_safe_range_are_invalid_input(self):
        value = summary()
        value["arms"]["control"]["units"] = 2 ** 60
        with self.assertRaises(ValueError):
            evaluate(value)

    def test_unsupported_schema_to_evaluate_is_rejected(self):
        for version in (1, 4):
            with self.assertRaises(ValueError):
                evaluate(summary(), schema_version=version)


class SchemaThreeReplayTest(unittest.TestCase):
    def test_srm_record_carries_the_accurate_tail_and_verifies(self):
        from expgate.generator import generate
        record = evaluate(generate("srm"))
        self.assertEqual(record["schema_version"], 3)
        self.assertEqual(record["decision"], "INVALID")
        self.assertGreater(record["sample_ratio"]["p_value"], 0.0)
        self.assertLess(record["sample_ratio"]["p_value"], 1e-40)
        self.assertEqual(verify_text(json.dumps(record))[0], 0)
        old = evaluate(generate("srm"), schema_version=2)
        self.assertEqual(old["sample_ratio"]["p_value"], 0.0)
        self.assertEqual(verify_text(json.dumps(old))[0], 0)

    def test_schema_3_uses_exact_tails_and_schema_2_the_0_1_0_formulas(self):
        from expgate import stats
        from expgate.records import EXACT_TAIL
        self.assertEqual(EXACT_TAIL, {2: False, 3: True})
        value = summary()
        three, two = evaluate(value), evaluate(value, schema_version=2)
        self.assertEqual(three["metrics"][1]["z"], stats.z_for(0.025, exact_tail=True))
        self.assertEqual(two["metrics"][1]["z"], stats.z_for(0.025))

    def test_derived_floats_agree_within_a_relative_1e_9(self):
        record = evaluate(summary())
        for factor, code in ((1 + 1e-10, 0), (1 + 1e-7, 1)):
            changed = json.loads(json.dumps(record))
            changed["metrics"][0]["se"] *= factor
            changed["metrics"][0]["improvement_bounds"][0] *= factor
            changed["sample_ratio"]["p_value"] *= factor
            with self.subTest(factor=factor):
                self.assertEqual(verify_text(json.dumps(changed))[0], code)

    def test_exact_values_stay_exact(self):
        record = evaluate(summary())
        cases = {
            "integer": lambda r: r["sample_ratio"].update(control_units=r["sample_ratio"]["control_units"] + 1),
            "string": lambda r: r["metrics"][0].update(status="IMPROVED" if r["metrics"][0]["status"] != "IMPROVED" else "DEGRADED"),
            "boolean": lambda r: r["sample_ratio"].update(**{"pass": not r["sample_ratio"]["pass"]}),
            "structure": lambda r: r["metrics"][0].update(extra=1),
            "reason": lambda r: r.update(reasons=r["reasons"] + ["x"]),
            "type": lambda r: r["metrics"][0].update(se=str(r["metrics"][0]["se"])),
        }
        for name, edit in cases.items():
            changed = json.loads(json.dumps(record))
            edit(changed)
            with self.subTest(case=name):
                self.assertEqual(verify_text(json.dumps(changed))[0], 1)

    def test_zero_uses_an_absolute_floor(self):
        value = summary()
        for arm in value["arms"].values():
            arm["metrics"]["conversion"]["successes"] = 0
        record = evaluate(value)
        self.assertEqual(record["metrics"][0]["se"], 0.0)
        for noise, code in ((1e-13, 0), (1e-9, 1)):
            changed = json.loads(json.dumps(record))
            changed["metrics"][0]["se"] = noise
            with self.subTest(noise=noise):
                self.assertEqual(verify_text(json.dumps(changed))[0], code)


def overflowing_summary():
    value = summary()
    for arm, mean in (("control", -1e308), ("treatment", 1e308)):
        value["arms"][arm]["metrics"]["latency_ms"].update(mean=mean, sd=1.0)
    return value


class ReviewProbeTest(unittest.TestCase):
    """Each case below is a probe from the review of the first tolerance implementation."""

    def edited(self, schema, edit):
        record = json.loads(json.dumps(evaluate(summary(), schema_version=schema)))
        edit(record)
        return verify_text(json.dumps(record))[0]

    def test_counts_compare_exactly_whatever_their_spelling(self):
        for schema in (2, 3):
            for value in (lambda n: float(n + 1), lambda n: n + 0.4, lambda n: float(n) * (1 + 1e-10)):
                with self.subTest(schema=schema):
                    def edit(r, value=value):
                        r["sample_ratio"]["control_units"] = value(r["sample_ratio"]["control_units"])
                    self.assertEqual(self.edited(schema, edit), 1)
            # the same count spelled as a float is the same count
            def respell(r):
                r["sample_ratio"]["control_units"] = float(r["sample_ratio"]["control_units"])
            self.assertEqual(self.edited(schema, respell), 0)
        big = summary()
        big["arms"]["control"]["units"] = 2_000_000_000
        record = json.loads(json.dumps(evaluate(big)))
        record["sample_ratio"]["control_units"] = 2_000_000_001.0
        self.assertEqual(verify_text(json.dumps(record))[0], 1)

    def test_copied_input_and_policy_values_are_exact(self):
        def alpha(r):
            r["policy"]["alpha"] *= 1 + 1e-10
        def margin(r):
            for row in r["metrics"]:
                if "margin" in row:
                    row["margin"] *= 1 + 1e-10
        def share(r):
            r["sample_ratio"]["expected_treatment_share"] *= 1 + 1e-10
        def control(r):
            r["metrics"][0]["control"] *= 1 + 1e-10
        for schema in (2, 3):
            for name, edit in (("alpha", alpha), ("margin", margin), ("share", share), ("control", control)):
                with self.subTest(schema=schema, field=name):
                    self.assertEqual(self.edited(schema, edit), 1)

    def test_computed_statistics_keep_the_tolerance_in_both_schemas(self):
        def edit(r):
            r["metrics"][0]["z"] *= 1 + 1e-10
            r["metrics"][0]["mde"] *= 1 - 1e-10
            r["sample_ratio"]["p_value"] *= 1 + 1e-10
        for schema in (2, 3):
            with self.subTest(schema=schema):
                self.assertEqual(self.edited(schema, edit), 0)

    def test_non_finite_values_must_be_identical(self):
        record = evaluate(overflowing_summary(), schema_version=2)
        row = next(m for m in record["metrics"] if m["metric"] == "latency_ms")
        self.assertEqual((row["diff"], row["improvement"]), (float("inf"), float("-inf")))
        text = json.dumps(record)  # Python writes the Infinity literal, as 0.1.0 did
        self.assertEqual(verify_text(text)[0], 0, "an untouched record from the old producer verifies")
        for field, replacement in (("diff", 0), ("improvement", 0), ("se", 0)):
            changed = json.loads(text)
            target = next(m for m in changed["metrics"] if m["metric"] == "latency_ms")
            target[field] = replacement
            with self.subTest(field=field):
                self.assertEqual(verify_text(json.dumps(changed))[0], 1)
        flipped = json.loads(text)
        next(m for m in flipped["metrics"] if m["metric"] == "latency_ms")["diff"] = float("-inf")
        self.assertEqual(verify_text(json.dumps(flipped))[0], 1)
        nan = json.loads(text)
        next(m for m in nan["metrics"] if m["metric"] == "latency_ms")["diff"] = float("nan")
        self.assertEqual(verify_text(json.dumps(nan))[0], 1)

    def test_schema_3_does_not_produce_non_finite_records(self):
        with self.assertRaises(ValueError):
            evaluate(overflowing_summary())

    def test_schema_3_strictness_covers_ignored_members(self):
        text = json.dumps(evaluate(summary()), indent=2)
        for member in ('9007199254740992', '1e999', '"\\ud800"', '-9007199254740993', '[1e999]', '{"k": 1e999}'):
            changed = text.replace("{\n", "{\n  \"note\": " + member + ",\n", 1)
            with self.subTest(member=member):
                code, message = verify_text(changed)
                self.assertEqual(code, 2, message)
        for member in ('"free text"', "9007199254740991", "1.5", "[1, 2]", '{"k": null}'):
            changed = text.replace("{\n", "{\n  \"note\": " + member + ",\n", 1)
            with self.subTest(member=member):
                self.assertEqual(verify_text(changed)[0], 0)
        # schema 2 keeps its lenient reading of ignored members
        legacy = json.dumps(evaluate(summary(), schema_version=2), indent=2)
        self.assertEqual(verify_text(legacy.replace("{\n", '{\n  "note": 9007199254740992,\n', 1))[0], 0)

    def test_verify_record_api_applies_the_same_strictness(self):
        record = evaluate(summary())
        record["note"] = 2 ** 60
        with self.assertRaises(ValueError):
            verify_record(record)


class UnreplayableRecordTest(unittest.TestCase):
    """A record the running version cannot evaluate or parse is invalid (exit 2), never a traceback."""

    def test_replay_that_divides_by_an_underflowed_zero_exits_2(self):
        value = summary()
        for arm in value["arms"].values():  # covariate sd squared underflows to 0.0
            arm["metrics"]["latency_ms"]["covariate"] = {"mean": 1.0, "sd": 1e-200, "corr": 0.5}
        for schema in (2, 3):
            with self.subTest(schema=schema):
                record = json.loads(json.dumps(evaluate(summary(), schema_version=schema)))
                record["input"] = value  # the digest is still that of the original input
                self.assertEqual(verify_record(record), ["input_sha256", "input (cannot replay)"])
                record["input_sha256"] = input_digest(value, schema)
                with self.assertRaises(ValueError):
                    verify_record(record)
                code, message = verify_text(json.dumps(record))
                self.assertEqual(code, 2, message)
                self.assertIn("invalid embedded input", message)

    def test_deeply_nested_records_exit_2_and_later_records_are_still_checked(self):
        text = json.dumps(evaluate(summary()), indent=2)
        # 5,000 levels parse but exceed the canonicalizer's recursion; 200,000 exceed the parser's.
        for depth in (5_000, 200_000):
            with self.subTest(depth=depth), tempfile.TemporaryDirectory() as tmp:
                deep = Path(tmp, "deep.json")
                deep.write_text(text.replace("{\n", '{\n  "note": ' + "[" * depth + "]" * depth + ",\n", 1))
                good = Path(tmp, "good.json")
                good.write_text(text)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = verify_main([str(deep), str(good)])
                self.assertEqual(code, 2)
                self.assertIn("deep.json: cannot verify", err.getvalue())
                self.assertIn("good.json: verified", out.getvalue())


class SchemaTwoTest(unittest.TestCase):
    def test_schema_2_replay_uses_the_same_tolerance_as_schema_3(self):
        record = evaluate(summary(), schema_version=2)
        for factor, code in ((1 + 1e-12, 0), (1 + 1e-7, 1)):
            changed = json.loads(json.dumps(record))
            changed["metrics"][0]["se"] *= factor
            with self.subTest(factor=factor):
                self.assertEqual(verify_text(json.dumps(changed))[0], code)

    def test_schema_2_keeps_exact_inputs_strings_and_the_0_1_0_tail(self):
        record = evaluate(summary(), schema_version=2)
        changed = json.loads(json.dumps(record))
        changed["sample_ratio"]["control_units"] += 1
        self.assertEqual(verify_text(json.dumps(changed))[0], 1)
        changed = json.loads(json.dumps(record))
        changed["input_sha256"] = evaluate(summary())["input_sha256"]
        self.assertEqual(verify_text(json.dumps(changed))[0], 1)
        from expgate.generator import generate
        self.assertEqual(evaluate(generate("srm"), schema_version=2)["sample_ratio"]["p_value"], 0.0)

    def test_python_json_v1_records_still_verify(self):
        value = summary()
        value["description"] = "例子"
        value["metrics"]["latency_ms"]["margin"] = 2.0
        record = evaluate(value, schema_version=2)
        expected = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                             ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["input_sha256"], expected)
        self.assertEqual(verify_text(json.dumps(record))[0], 0)
        self.assertEqual(verify_text(json.dumps({**record, "decision": "HOLD"}))[0], 1)

    def test_schema_2_digest_is_not_accepted_under_schema_3(self):
        value = summary()
        value["metrics"]["latency_ms"]["margin"] = 2.0
        record = evaluate(value, schema_version=2)
        code, message = verify_text(json.dumps({**record, "schema_version": 3}))
        self.assertEqual(code, 1)
        self.assertIn("input_sha256", message)

    def test_schema_1_is_unverifiable(self):
        code, message = verify_text(json.dumps({"decision": "SHIP", "expgate_version": "0.0.9"}))
        self.assertEqual(code, 2)
        self.assertIn("schema 1 cannot be verified", message)


if __name__ == "__main__":
    unittest.main()
