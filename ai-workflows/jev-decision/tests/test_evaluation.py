import io
import json
import math
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from jevdecision import APIError, Choice, JevBackend, Noul, OpenAIDecisionsBackend, Score
from jevdecision.answers import parse_answers
from jevdecision.errors import DatasetError
from jevdecision.evaluation import (
    Case,
    case_results,
    evaluate,
    expected_calibration_error,
    load_cases,
    load_requirements,
    load_responses,
    main,
    render_markdown,
    replay,
    run_live,
    score_answers,
    wilson_interval,
    write_records,
)

REFUND = Noul("refund", "Is the customer asking for a refund?")
DEPARTMENT = Choice("department", "Which team should handle this?", {
    "billing": "Payments, invoicing, refunds",
    "technical": "Bugs, outages, integrations",
    "sales": "Pricing, upgrades, new accounts",
})
FRUSTRATION = Score("frustration", "How frustrated is the customer?", ["Calm", "Frustrated", "Very angry"])
QUESTIONS = [REFUND, DEPARTMENT, FRUSTRATION]

JEV_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "refund": {"type": "noul", "noul": 0.12},
        "department": {"type": "choice", "choice": "technical",
                       "probabilities": {"billing": 0.08, "technical": 0.85, "sales": 0.07}},
        "frustration": {"type": "score", "score": 1.05, "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}},
    },
}
OPENAI_RESPONSE = {
    "model": "gpt-6-luna",
    "answers": [
        {"type": "predicate", "name": "refund", "probability": 0.12},
        {"type": "choice", "name": "department", "value": "technical",
         "probabilities": [{"value": "billing", "probability": 0.08}, {"value": "technical", "probability": 0.85},
                           {"value": "sales", "probability": 0.07}]},
        {"type": "score", "name": "frustration", "score": 1.05,
         "probabilities": [{"label": "Calm", "probability": 0.0}, {"label": "Frustrated", "probability": 0.95},
                           {"label": "Very angry", "probability": 0.05}]},
    ],
}


class FakeTransport:
    """Returns (or raises) the given responses in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, url, headers, body, timeout):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def jev(*responses):
    transport = FakeTransport(*responses)
    return JevBackend(api_key="k", transport=transport, sleep=lambda _: None, env={}), transport

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
QUESTIONS_FILE = EXAMPLES / "support-ticket.json"
CASES_FILE = EXAMPLES / "support-ticket-cases.jsonl"
RESPONSES_FILE = EXAMPLES / "support-ticket-responses.jsonl"
REQUIRE_FILE = EXAMPLES / "support-ticket-requirements.json"


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def jev_answers(refund, department, frustration):
    """Parse a Jev response with the given refund probability, department probabilities, and score probabilities."""
    choice = max(department, key=department.get)
    raw = {
        "refund": {"type": "noul", "noul": refund},
        "department": {"type": "choice", "choice": choice, "probabilities": department},
        "frustration": {"type": "score", "probabilities": list(frustration)},
    }
    return parse_answers(raw, QUESTIONS)


def jsonl(rows):
    return "".join(json.dumps(row) + "\n" for row in rows)


class MetricTest(unittest.TestCase):
    def setUp(self):
        self.cases = [
            Case("a", "x", {"refund": True, "department": "billing", "frustration": 2}),
            Case("b", "y", {"refund": False, "department": "technical", "frustration": 0}),
            Case("c", "z", {"refund": True, "department": "sales"}),
        ]
        self.answers = {
            "a": jev_answers(0.9, {"billing": 0.7, "technical": 0.2, "sales": 0.1}, (0.0, 0.5, 0.5)),
            "b": jev_answers(0.2, {"billing": 0.1, "technical": 0.8, "sales": 0.1}, (1.0, 0.0, 0.0)),
            "c": jev_answers(0.4, {"billing": 0.6, "technical": 0.0, "sales": 0.4}, (0.0, 1.0, 0.0)),
        }
        self.report = score_answers(QUESTIONS, self.cases, self.answers)

    def test_noul_metrics(self):
        m = self.report["refund"]
        self.assertEqual(m["n"], 3)
        self.assertAlmostEqual(m["accuracy"], 2 / 3)  # 0.4 for a yes counts as no
        self.assertAlmostEqual(m["brier"], (0.1 ** 2 + 0.2 ** 2 + 0.6 ** 2) / 3)
        self.assertAlmostEqual(m["log_loss"], -(math.log(0.9) + math.log(0.8) + math.log(0.4)) / 3)
        self.assertAlmostEqual(m["base_rate"], 2 / 3)
        self.assertAlmostEqual(m["mean_probability"], 0.5)
        # Bins: 0.2 -> no (|0 - 0.2|), 0.4 -> yes (|1 - 0.4|), 0.9 -> yes (|1 - 0.9|).
        self.assertAlmostEqual(m["ece"], (0.2 + 0.6 + 0.1) / 3)

    def test_choice_metrics(self):
        m = self.report["department"]
        self.assertAlmostEqual(m["accuracy"], 2 / 3)
        brier_a = 0.3 ** 2 + 0.2 ** 2 + 0.1 ** 2
        brier_b = 0.1 ** 2 + 0.2 ** 2 + 0.1 ** 2
        brier_c = 0.6 ** 2 + 0.0 ** 2 + 0.6 ** 2
        self.assertAlmostEqual(m["brier"], (brier_a + brier_b + brier_c) / 3)
        self.assertAlmostEqual(m["log_loss"], -(math.log(0.7) + math.log(0.8) + math.log(0.4)) / 3)
        self.assertEqual(m["confusion"], {"billing": {"billing": 1}, "technical": {"technical": 1},
                                          "sales": {"billing": 1}})
        # Chosen-label probabilities 0.7 (right), 0.8 (right), 0.6 (wrong) fall in three bins.
        self.assertAlmostEqual(m["ece"], (0.3 + 0.2 + 0.6) / 3)

    def test_score_metrics_skip_unlabeled_cases(self):
        m = self.report["frustration"]
        self.assertEqual(m["n"], 2)  # case c has no frustration label
        self.assertAlmostEqual(m["accuracy"], 1.0)  # a scores 1.5, which rounds to the top level
        self.assertAlmostEqual(m["within_one"], 1.0)
        self.assertAlmostEqual(m["mae"], (0.5 + 0.0) / 2)

    def test_accuracy_carries_a_wilson_interval(self):
        for name, correct, n in (("refund", 2, 3), ("department", 2, 3), ("frustration", 2, 2)):
            with self.subTest(name):
                m = self.report[name]
                lower, upper = wilson_interval(correct, n)
                self.assertEqual((m["accuracy_lower"], m["accuracy_upper"]), (lower, upper))
                self.assertLessEqual(m["accuracy_lower"], m["accuracy"])
                self.assertGreaterEqual(m["accuracy_upper"], m["accuracy"])

    def test_wilson_interval(self):
        # Reference values for the 95% Wilson score interval.
        for (successes, n), (lower, upper) in {(11, 12): (0.6461, 0.9851), (50, 100): (0.4038, 0.5962),
                                               (12, 12): (0.7575, 1.0), (0, 5): (0.0, 0.4345)}.items():
            with self.subTest(successes=successes, n=n):
                got = wilson_interval(successes, n)
                self.assertAlmostEqual(got[0], lower, places=4)
                self.assertAlmostEqual(got[1], upper, places=4)
        self.assertEqual(wilson_interval(0, 0), (None, None))
        narrow, wide = wilson_interval(90, 100, confidence=0.8), wilson_interval(90, 100, confidence=0.99)
        self.assertLess(wide[0], narrow[0])
        self.assertGreater(wide[1], narrow[1])

    def test_requirement_on_the_accuracy_lower_bound(self):
        cases = [Case(str(i), "x", {"refund": True}) for i in range(12)]
        answers = {case.id: {"refund": parse_answers({"refund": {"noul": 0.9 if i else 0.1}}, [REFUND])["refund"]}
                   for i, case in enumerate(cases)}
        loose = evaluate([REFUND], cases, answers, [], {"questions": {"refund": {"accuracy": {"min": 0.9}}}})
        strict = evaluate([REFUND], cases, answers, [], {"questions": {"refund": {"accuracy_lower": {"min": 0.9}}}})
        self.assertTrue(loose["pass"])  # 11 of 12 correct
        self.assertFalse(strict["pass"])  # but the interval reaches down to 0.65
        self.assertAlmostEqual(strict["requirements"][1]["value"], 0.6461, places=4)

    def test_log_loss_is_clipped(self):
        cases = [Case("a", "x", {"refund": True})]
        report = score_answers([REFUND], cases, {"a": parse_answers({"refund": {"noul": 0.0}}, [REFUND])})
        self.assertAlmostEqual(report["refund"]["log_loss"], -math.log(1e-6))

    def test_empty_question_has_no_metrics(self):
        report = score_answers(QUESTIONS, [Case("a", "x", {"refund": True})],
                               {"a": jev_answers(0.9, {"billing": 1.0}, (1, 0, 0))})
        self.assertEqual(report["department"]["n"], 0)
        self.assertIsNone(report["department"]["accuracy"])

    def test_ece(self):
        self.assertIsNone(expected_calibration_error([]))
        self.assertAlmostEqual(expected_calibration_error([(0.25, True), (0.25, False)]), 0.25)
        self.assertAlmostEqual(expected_calibration_error([(1.0, True), (0.95, True)]), 0.025)  # 1.0 joins the top bin


class LoadTest(unittest.TestCase):
    def case(self, **overrides):
        row = {"id": "a", "state": "text", "labels": {"refund": True}}
        row.update(overrides)
        return row

    def test_labels_are_normalized(self):
        cases = load_cases(jsonl([
            self.case(labels={"refund": False, "department": "sales", "frustration": "Very angry"}),
            self.case(id="b", state={"ticket": 1}, labels={"frustration": 0}),
        ]), QUESTIONS)
        self.assertEqual(cases[0].labels, {"refund": False, "department": "sales", "frustration": 2})
        self.assertEqual(cases[1].labels, {"frustration": 0})
        self.assertEqual(cases[1].state, {"ticket": 1})

    def test_invalid_cases(self):
        bad = {
            "not JSON": "{",
            "not an object": "[1]\n",
            "no cases": "\n",
            "missing id": jsonl([self.case(id="")]),
            "duplicate id": jsonl([self.case(), self.case()]),
            "empty state": jsonl([self.case(state=" ")]),
            "no labels": jsonl([self.case(labels={})]),
            "unknown question": jsonl([self.case(labels={"other": True})]),
            "noul label not boolean": jsonl([self.case(labels={"refund": 1})]),
            "unknown choice": jsonl([self.case(labels={"department": "legal"})]),
            "unknown level": jsonl([self.case(labels={"frustration": "Livid"})]),
            "level index out of range": jsonl([self.case(labels={"frustration": 3})]),
            "boolean level index": jsonl([self.case(labels={"frustration": True})]),
        }
        for label, text in bad.items():
            with self.subTest(label), self.assertRaises(DatasetError):
                load_cases(text, QUESTIONS)

    def test_invalid_responses(self):
        for label, text in {
            "missing response": jsonl([{"id": "a"}]),
            "numeric id": jsonl([{"id": 1, "response": {}}]),
            "duplicate id": jsonl([{"id": "a", "response": {}}] * 2),
        }.items():
            with self.subTest(label), self.assertRaises(DatasetError):
                load_responses(text)

    def test_requirements(self):
        rate, checks = load_requirements({"max_error_rate": 0.1, "questions": {
            "refund": {"brier": {"max": 0.2}, "n": {"min": 5}},
            "frustration": {"mae": {"min": 0, "max": 1}}}}, QUESTIONS)
        self.assertEqual(rate, 0.1)
        self.assertEqual(checks, [("refund", "brier", "max", 0.2), ("refund", "n", "min", 5),
                                  ("frustration", "mae", "max", 1), ("frustration", "mae", "min", 0)])
        self.assertEqual(load_requirements({}, QUESTIONS), (0.0, []))

    def test_invalid_requirements(self):
        for label, spec in {
            "not an object": [],
            "unknown key": {"min_cases": 3},
            "error rate above 1": {"max_error_rate": 2},
            "boolean error rate": {"max_error_rate": True},
            "unknown question": {"questions": {"other": {"n": {"min": 1}}}},
            "metric of another type": {"questions": {"frustration": {"brier": {"max": 1}}}},
            "confusion is not a bound": {"questions": {"department": {"confusion": {"max": 1}}}},
            "unknown bound": {"questions": {"refund": {"brier": {"below": 1}}}},
            "empty bounds": {"questions": {"refund": {"brier": {}}}},
            "non-finite limit": {"questions": {"refund": {"brier": {"max": float("inf")}}}},
            "string limit": {"questions": {"refund": {"brier": {"max": "0.1"}}}},
        }.items():
            with self.subTest(label), self.assertRaises(DatasetError):
                load_requirements(spec, QUESTIONS)


class RunTest(unittest.TestCase):
    CASES = [Case("a", "first", {"department": "technical"}), Case("b", "second", {"department": "billing"})]

    def test_requirements_gate_the_report(self):
        answers = {"a": parse_answers(JEV_RESPONSE["answers"], QUESTIONS),
                   "b": parse_answers(JEV_RESPONSE["answers"], QUESTIONS)}
        report = evaluate(QUESTIONS, self.CASES, answers, [],
                          {"questions": {"department": {"accuracy": {"min": 0.5}}}})
        self.assertTrue(report["pass"])
        report = evaluate(QUESTIONS, self.CASES, answers, [],
                          {"questions": {"department": {"accuracy": {"min": 0.75}}}})
        self.assertFalse(report["pass"])
        self.assertEqual(report["requirements"][-1]["value"], 0.5)

    def test_requirement_on_an_unlabeled_question_fails(self):
        report = evaluate(QUESTIONS, self.CASES, {}, [], {"questions": {"refund": {"brier": {"max": 1}}}})
        self.assertIsNone(report["requirements"][-1]["value"])
        self.assertFalse(report["requirements"][-1]["pass"])

    def test_replay_records_malformed_responses_as_errors(self):
        bad = json.loads(json.dumps(JEV_RESPONSE))
        bad["answers"]["department"]["choice"] = "legal"
        answers, raw, errors = replay(JevBackend(env={}), QUESTIONS, self.CASES, {"a": JEV_RESPONSE, "b": bad})
        self.assertEqual(list(answers), ["a"])
        self.assertEqual(set(raw), {"a", "b"})
        self.assertEqual([e["id"] for e in errors], ["b"])
        report = evaluate(QUESTIONS, self.CASES, answers, errors)
        self.assertEqual(report["error_rate"], 0.5)
        self.assertFalse(report["pass"])  # max_error_rate defaults to 0
        self.assertTrue(evaluate(QUESTIONS, self.CASES, answers, errors, {"max_error_rate": 0.5})["pass"])

    def test_replay_counts_a_missing_response_as_an_error(self):
        answers, raw, errors = replay(JevBackend(env={}), QUESTIONS, self.CASES, {"a": JEV_RESPONSE})
        self.assertEqual((list(answers), list(raw)), (["a"], ["a"]))
        self.assertEqual(errors, [{"id": "b", "error": "no recorded response"}])
        with self.assertRaises(DatasetError):
            replay(JevBackend(env={}), QUESTIONS, self.CASES, {"a": JEV_RESPONSE, "z": JEV_RESPONSE})

    def test_live_errors_survive_a_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend, _ = jev(APIError("bad request", 400), JEV_RESPONSE)
            answers, raw, errors = run_live(backend, QUESTIONS, self.CASES)
            live = evaluate(QUESTIONS, self.CASES, answers, errors)
            write_records({"source": "live", **live, "jevdecision_version": "x", "backend": "jev",
                           "model": "m"}, raw, Path(tmp))
            recorded = load_responses(Path(tmp, "responses.jsonl").read_text())
            replayed = evaluate(QUESTIONS, self.CASES, *replay(JevBackend(env={}), QUESTIONS, self.CASES,
                                                                recorded)[::2])
            self.assertEqual(replayed["questions"], live["questions"])
            self.assertEqual(replayed["error_rate"], live["error_rate"])

    def test_case_results(self):
        cases = self.CASES + [Case("c", "x", {"refund": False})]
        answers, _, errors = replay(JevBackend(env={}), QUESTIONS, cases, {"a": JEV_RESPONSE})
        rows = case_results(QUESTIONS, cases, answers, errors)
        self.assertEqual([row["id"] for row in rows], ["a", "b", "c"])
        self.assertEqual(rows[1], {"id": "b", "error": "no recorded response"})
        self.assertEqual(set(rows[0]["questions"]), set(self.CASES[0].labels))
        for name, result in rows[0]["questions"].items():
            with self.subTest(name):
                self.assertEqual(set(result) - {"probability", "score"}, {"expected", "predicted", "correct"})
                self.assertEqual(result["correct"], result["expected"] == result["predicted"])
        self.assertEqual(rows[2], {"id": "c", "error": "no recorded response"})

    def test_case_results_are_written_and_misses_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = run_cli("--questions", QUESTIONS_FILE, "--cases", CASES_FILE, "--responses", RESPONSES_FILE,
                                 "--require", REQUIRE_FILE, "--out", Path(tmp, "out"))
            self.assertEqual(code, 0)
            rows = [json.loads(line) for line in Path(tmp, "out", "cases.jsonl").read_text().splitlines()]
            report = json.loads(Path(tmp, "out", "evaluation.json").read_text())
            markdown = Path(tmp, "out", "EVALUATION.md").read_text()
        self.assertEqual(len(rows), report["cases"])
        for name, metrics in report["questions"].items():
            results = [row["questions"][name] for row in rows if name in row.get("questions", {})]
            with self.subTest(name):
                self.assertEqual(len(results), metrics["n"])
                self.assertAlmostEqual(sum(r["correct"] for r in results) / len(results), metrics["accuracy"])
        misses = [(row["id"], name) for row in rows for name, r in row["questions"].items() if not r["correct"]]
        self.assertIn(f"Incorrect answers ({len(misses)};", markdown)
        for case_id, name in misses:
            self.assertIn(f"- `{case_id}` {name}: expected", markdown)

    def test_long_miss_lists_are_truncated(self):
        cases = [Case(str(i), "x", {"refund": True}) for i in range(25)]
        answers = {case.id: {"refund": parse_answers({"refund": {"noul": 0.1}}, [REFUND])["refund"]} for case in cases}
        report = {"jevdecision_version": "x", "backend": "jev", "model": "m", "source": "replay",
                  **evaluate([REFUND], cases, answers, [])}
        markdown = render_markdown(report, "d", case_results([REFUND], cases, answers, []))
        self.assertIn("Incorrect answers (25;", markdown)
        self.assertEqual(markdown.count(": expected true, got false"), 20)
        self.assertIn("- ... and 5 more", markdown)

    def test_replay_parses_the_openai_layout(self):
        answers, _, errors = replay(OpenAIDecisionsBackend(env={}), QUESTIONS, self.CASES,
                                    {"a": OPENAI_RESPONSE, "b": OPENAI_RESPONSE})
        self.assertEqual(errors, [])
        self.assertEqual(score_answers(QUESTIONS, self.CASES, answers)["department"]["accuracy"], 0.5)

    def test_live_run_continues_past_a_failing_case(self):
        backend, transport = jev(APIError("bad request", 400), JEV_RESPONSE)
        answers, raw, errors = run_live(backend, QUESTIONS, self.CASES)
        self.assertEqual(transport.calls, 2)
        self.assertEqual([e["id"] for e in errors], ["a"])
        self.assertEqual(list(answers), ["b"])
        self.assertEqual(raw["b"], JEV_RESPONSE)


class CLITest(unittest.TestCase):
    def test_example_passes_and_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = []
            for name in ("a", "b"):
                out = Path(tmp, name)
                code, stdout, _ = run_cli("--questions", QUESTIONS_FILE, "--cases", CASES_FILE,
                                          "--responses", RESPONSES_FILE, "--require", REQUIRE_FILE, "--out", out)
                self.assertEqual(code, 0, stdout)
                self.assertTrue(stdout.startswith("PASS "))
                records.append((out / "evaluation.json").read_bytes())
            self.assertEqual(records[0], records[1])
            report = json.loads(records[0])
            self.assertEqual((report["cases"], report["source"], report["model"]), (12, "replay", "jev-example"))
            self.assertIn("# Decision model evaluation: PASS", Path(tmp, "a", "EVALUATION.md").read_text())
            # The written responses replay to the same report.
            code, _, _ = run_cli("--questions", QUESTIONS_FILE, "--cases", CASES_FILE,
                                 "--responses", Path(tmp, "a", "responses.jsonl"), "--require", REQUIRE_FILE,
                                 "--out", Path(tmp, "c"))
            self.assertEqual(code, 0)
            self.assertEqual((Path(tmp, "c") / "evaluation.json").read_bytes(), records[0])

    def test_failing_requirement_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            strict = Path(tmp, "strict.json")
            strict.write_text(json.dumps({"questions": {"department": {"accuracy": {"min": 0.99}}}}))
            code, stdout, _ = run_cli("--questions", QUESTIONS_FILE, "--cases", CASES_FILE,
                                      "--responses", RESPONSES_FILE, "--require", strict, "--out", Path(tmp, "out"))
            self.assertEqual(code, 1)
            self.assertIn("department.accuracy", stdout)
            self.assertIn("| department.accuracy | min 0.99 |", Path(tmp, "out", "EVALUATION.md").read_text())

    def test_invalid_input_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.jsonl")
            bad.write_text(jsonl([{"id": "a", "state": "x", "labels": {"refund": "yes"}}]))
            code, _, err = run_cli("--questions", QUESTIONS_FILE, "--cases", bad,
                                   "--responses", RESPONSES_FILE, "--out", Path(tmp, "out"))
            self.assertEqual(code, 2)
            self.assertIn("noul label", err)
            code, _, _ = run_cli("--questions", QUESTIONS_FILE, "--cases", CASES_FILE,
                                 "--responses", Path(tmp, "missing.jsonl"), "--out", Path(tmp, "out"))
            self.assertEqual(code, 2)

    def test_live_run_without_a_key_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.dict("os.environ", {}, clear=True):
            code, _, err = run_cli("--questions", QUESTIONS_FILE, "--cases", CASES_FILE, "--out", Path(tmp, "out"))
            self.assertEqual(code, 1)
            self.assertIn("no API key", err)
            self.assertFalse(Path(tmp, "out").exists())

    def test_rejects_a_non_positive_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            for timeout in ("0", "-5"):
                with self.subTest(timeout), self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
                    main(["--questions", str(QUESTIONS_FILE), "--cases", str(CASES_FILE),
                          "--timeout", timeout, "--out", str(Path(tmp, "out"))])
                self.assertEqual(raised.exception.code, 2)
            self.assertFalse(Path(tmp, "out").exists())

    def test_refuses_a_non_empty_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "keep").write_text("x")
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                main(["--questions", str(QUESTIONS_FILE), "--cases", str(CASES_FILE),
                      "--responses", str(RESPONSES_FILE), "--out", tmp])


if __name__ == "__main__":
    unittest.main()
