import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from jevdecision import (
    APIError,
    Choice,
    DecisionError,
    DecisionModel,
    JevBackend,
    Noul,
    OpenAIDecisionsBackend,
    Predicate,
    QuestionError,
    ResponseError,
    Score,
    create_backend,
    questions_from_spec,
)
from jevdecision.__main__ import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "support-ticket.json"
STATE = "Help! My payouts have been failing for 3 days."

REFUND = Noul("refund", "Is the customer asking for a refund?")
DEPARTMENT = Choice("department", "Which team should handle this?", {
    "billing": "Payments, invoicing, refunds",
    "technical": "Bugs, outages, integrations",
    "sales": "Pricing, upgrades, new accounts",
})
FRUSTRATION = Score("frustration", "How frustrated is the customer?", ["Calm", "Frustrated", "Very angry"])
QUESTIONS = [REFUND, DEPARTMENT, FRUSTRATION]

# Response shapes as published by each provider.
JEV_RESPONSE = {
    "model": "jev-1.13.0",
    "id": "gen-dec-1",
    "answers": {
        "refund": {"type": "noul", "noul": 0.12},
        "department": {
            "type": "choice",
            "choice": "technical",
            "probabilities": {"billing": 0.08, "technical": 0.85, "sales": 0.07},
            "confidence": 0.82,
        },
        "frustration": {
            "type": "score",
            "score": 1.05,
            "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
            "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05},
            "confidence": 0.92,
        },
    },
    "usage": {"input_tokens": 312, "output_tokens": 48},
}
OPENAI_RESPONSE = {
    "model": "gpt-6-luna",
    "answers": [
        {"type": "predicate", "name": "refund", "probability": 0.12},
        {
            "type": "choice",
            "name": "department",
            "value": "technical",
            "probabilities": [
                {"value": "billing", "probability": 0.08},
                {"value": "technical", "probability": 0.85},
                {"value": "sales", "probability": 0.07},
            ],
            "confidence": 0.82,
        },
        {
            "type": "score",
            "name": "frustration",
            "score": 1.05,
            "probabilities": [
                {"label": "Calm", "probability": 0.0},
                {"label": "Frustrated", "probability": 0.95},
                {"label": "Very angry", "probability": 0.05},
            ],
        },
    ],
    "credits_used": 1,
}


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def jev(*responses, **options):
    transport = FakeTransport(*responses)
    return JevBackend(api_key="k", transport=transport, sleep=lambda _: None, env={}, **options), transport


def openai(*responses, **options):
    transport = FakeTransport(*responses)
    backend = OpenAIDecisionsBackend(api_key="k", transport=transport, sleep=lambda _: None, env={}, **options)
    return backend, transport


class QuestionTest(unittest.TestCase):
    def test_predicate_is_noul(self):
        self.assertIs(Predicate, Noul)

    def test_invalid_questions(self):
        with self.assertRaises(QuestionError):
            Noul("1bad", "x")
        with self.assertRaises(QuestionError):
            Noul("ok", "  ")
        with self.assertRaises(QuestionError):
            Choice("c", "x", {})
        with self.assertRaises(QuestionError):
            Choice("c", "x", {str(i): "d" for i in range(256)})
        with self.assertRaises(QuestionError):
            Choice("c", "x", {"a": ""})
        with self.assertRaises(QuestionError):
            Score("s", "x", ["only"])
        with self.assertRaises(QuestionError):
            Score("s", "x", [str(i) for i in range(11)])
        with self.assertRaises(QuestionError):
            Score("s", "x", ["a", "a"])
        with self.assertRaises(QuestionError):
            Score("s", "x", "ab")

    def test_choice_options_are_read_only(self):
        with self.assertRaises(TypeError):
            DEPARTMENT.options["new"] = "x"

    def test_spec_round_trip(self):
        questions = questions_from_spec(json.loads(EXAMPLE.read_text()))
        self.assertEqual(questions, tuple(QUESTIONS))

    def test_spec_errors(self):
        for spec in ({}, {"q": {"type": "maybe", "instructions": "x"}},
                     {"q": {"type": "choice", "instructions": "x", "criteria": ["a"]}},
                     {"q": {"type": "score", "instructions": "x", "criteria": {"a": "b"}}}):
            with self.subTest(spec=spec), self.assertRaises(QuestionError):
                questions_from_spec(spec)

    def test_duplicate_names_rejected_before_sending(self):
        backend, transport = jev(JEV_RESPONSE)
        with self.assertRaises(QuestionError):
            DecisionModel(backend).decide(STATE, [REFUND, Noul("refund", "again?")])
        self.assertEqual(transport.calls, [])


class JevBackendTest(unittest.TestCase):
    def test_request_shape(self):
        backend, transport = jev(JEV_RESPONSE)
        DecisionModel(backend).decide(STATE, QUESTIONS)
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(call["headers"]["Authorization"], "Bearer k")
        self.assertEqual(call["body"], {
            "model": "jev-latest",
            "state": STATE,
            "questions": json.loads(EXAMPLE.read_text()),
        })

    def test_json_state_is_sent_as_is(self):
        backend, transport = jev({"answers": {"refund": {"type": "noul", "noul": 0.5}}})
        DecisionModel(backend).decide({"ticket": 7, "text": STATE}, [REFUND])
        self.assertEqual(transport.calls[0]["body"]["state"], {"ticket": 7, "text": STATE})

    def test_gateway_path_and_model(self):
        backend, transport = jev(JEV_RESPONSE, base_url="https://gw.example/", path="/v1/decisions",
                                 model="typesafe/jev")
        DecisionModel(backend).decide(STATE, QUESTIONS)
        self.assertEqual(transport.calls[0]["url"], "https://gw.example/v1/decisions")
        self.assertEqual(transport.calls[0]["body"]["model"], "typesafe/jev")

    def test_parses_typed_answers(self):
        backend, _ = jev(JEV_RESPONSE)
        decision = DecisionModel(backend).decide(STATE, QUESTIONS)
        self.assertEqual(decision.backend, "jev")
        self.assertEqual(decision.model, "jev-1.13.0")
        self.assertEqual(decision.id, "gen-dec-1")
        self.assertEqual(decision.usage, {"input_tokens": 312, "output_tokens": 48})
        self.assertAlmostEqual(decision["refund"].probability, 0.12)
        self.assertFalse(decision["refund"].is_yes())
        self.assertEqual(decision["department"].choice, "technical")
        self.assertAlmostEqual(decision["department"].probability, 0.85)
        self.assertEqual(decision["department"].ranked()[0], ("technical", 0.85))
        self.assertEqual(decision["frustration"].level, "Frustrated")
        self.assertEqual(decision["frustration"].probabilities, (0.0, 0.95, 0.05))
        self.assertAlmostEqual(decision["frustration"].normalized, 0.525)
        json.dumps(decision.to_dict())

    def test_missing_api_key(self):
        backend = JevBackend(env={}, transport=FakeTransport())
        with self.assertRaisesRegex(DecisionError, "TYPESAFE_API_KEY"):
            DecisionModel(backend).decide(STATE, [REFUND])

    def test_invalid_state(self):
        backend, _ = jev()
        for state in ("", {}, [], [1], [STATE, " "], None):
            with self.subTest(state=state), self.assertRaises(DecisionError):
                DecisionModel(backend).decide(state, [REFUND])


class OpenAIBackendTest(unittest.TestCase):
    def test_request_shape(self):
        backend, transport = openai(OPENAI_RESPONSE)
        DecisionModel(backend).decide(STATE, QUESTIONS)
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://api.openai.com/v1/decisions")
        body = call["body"]
        self.assertEqual(body["input"], STATE)
        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertEqual(body["questions"][0], {
            "type": "predicate", "name": "refund", "instructions": "Is the customer asking for a refund?"})
        self.assertEqual(body["questions"][1]["choices"][0],
                         {"value": "billing", "description": "Payments, invoicing, refunds"})
        self.assertEqual(body["questions"][2]["levels"],
                         [{"label": "Calm"}, {"label": "Frustrated"}, {"label": "Very angry"}])

    def test_structured_state_becomes_text(self):
        backend, transport = openai({"answers": {"refund": {"type": "noul", "noul": 0.5}}})
        DecisionModel(backend).decide({"b": 1, "a": 2}, [REFUND])
        self.assertEqual(transport.calls[0]["body"]["input"], '{"a": 2, "b": 1}')

    def test_same_answers_as_jev(self):
        jev_backend, _ = jev(JEV_RESPONSE)
        openai_backend, _ = openai(OPENAI_RESPONSE)
        a = DecisionModel(jev_backend).decide(STATE, QUESTIONS)
        b = DecisionModel(openai_backend).decide(STATE, QUESTIONS)
        self.assertEqual(a.answers["refund"], b.answers["refund"])
        self.assertEqual(a.answers["department"], b.answers["department"])
        self.assertEqual(b["frustration"].probabilities, (0.0, 0.95, 0.05))
        self.assertEqual(b.usage, {"credits_used": 1})

    def test_score_derived_from_probabilities(self):
        backend, _ = openai({"answers": [{"type": "score", "name": "frustration",
                                          "probabilities": [0.0, 0.5, 0.5]}]})
        answer = DecisionModel(backend).ask(STATE, FRUSTRATION)
        self.assertAlmostEqual(answer.score, 1.5)
        self.assertEqual(answer.level, "Very angry")


class ResponseValidationTest(unittest.TestCase):
    def check_rejects(self, answers):
        backend, _ = jev({"answers": answers})
        with self.assertRaises(ResponseError):
            DecisionModel(backend).decide(STATE, QUESTIONS)

    def answers(self, **changes):
        answers = json.loads(json.dumps(JEV_RESPONSE["answers"]))
        for name, entry in changes.items():
            if entry is None:
                del answers[name]
            else:
                answers[name].update(entry)
        return answers

    def test_rejects_mismatches(self):
        cases = {
            "missing answer": self.answers(refund=None),
            "probability out of range": self.answers(refund={"noul": 1.5}),
            "boolean probability": self.answers(refund={"noul": True}),
            "unknown choice": self.answers(department={"choice": "legal"}),
            "unknown option probability": self.answers(
                department={"probabilities": {"legal": 0.1, "technical": 0.9}}),
            "wrong type": self.answers(refund={"type": "choice"}),
            "score out of range": self.answers(frustration={"score": 2.5}),
            "unknown level": self.answers(frustration={"probabilities": {"7": 1.0}}),
            "nan confidence": self.answers(department={"confidence": float("nan")}),
        }
        for label, answers in cases.items():
            with self.subTest(label):
                self.check_rejects(answers)
        extra = self.answers()
        extra["other"] = {"type": "noul", "noul": 0.1}
        self.check_rejects(extra)

    def test_provider_error_body(self):
        backend, _ = jev({"error": {"message": "bad request"}})
        with self.assertRaises(APIError):
            DecisionModel(backend).decide(STATE, QUESTIONS)


class RetryTest(unittest.TestCase):
    def test_retries_transient_errors(self):
        backend, transport = jev(APIError("busy", 429), APIError("down", 503), JEV_RESPONSE)
        DecisionModel(backend).decide(STATE, QUESTIONS)
        self.assertEqual(len(transport.calls), 3)

    def test_gives_up_after_max_retries(self):
        backend, transport = jev(APIError("down", 503), APIError("down", 503), max_retries=1)
        with self.assertRaises(APIError):
            DecisionModel(backend).decide(STATE, QUESTIONS)
        self.assertEqual(len(transport.calls), 2)

    def test_client_errors_are_not_retried(self):
        backend, transport = jev(APIError("bad", 400), JEV_RESPONSE)
        with self.assertRaises(APIError):
            DecisionModel(backend).decide(STATE, QUESTIONS)
        self.assertEqual(len(transport.calls), 1)


class DecisionModelTest(unittest.TestCase):
    def test_from_env(self):
        self.assertIsInstance(DecisionModel.from_env(env={}).backend, JevBackend)
        model = DecisionModel.from_env(env={"DECISION_BACKEND": "openai", "OPENAI_API_KEY": "o",
                                            "OPENAI_DECISIONS_MODEL": "m"})
        self.assertIsInstance(model.backend, OpenAIDecisionsBackend)
        self.assertEqual((model.backend.api_key, model.backend.model), ("o", "m"))
        with self.assertRaises(DecisionError):
            DecisionModel.from_env(env={"DECISION_BACKEND": "other"})
        with self.assertRaises(DecisionError):
            create_backend("other")

    def test_gate(self):
        backend, _ = jev({"answers": {"refund": {"type": "noul", "noul": 0.7}}},
                         {"answers": {"refund": {"type": "noul", "noul": 0.7}}})
        model = DecisionModel(backend)
        self.assertTrue(model.gate(STATE, REFUND, threshold=0.7))
        self.assertFalse(model.gate(STATE, REFUND, threshold=0.71))
        with self.assertRaises(DecisionError):
            model.gate(STATE, DEPARTMENT)

    def test_route_with_confidence_floor(self):
        answer = {"department": JEV_RESPONSE["answers"]["department"]}
        backend, _ = jev({"answers": answer}, {"answers": answer})
        model = DecisionModel(backend)
        self.assertEqual(model.route(STATE, DEPARTMENT, min_confidence=0.8), "technical")
        self.assertEqual(model.route(STATE, DEPARTMENT, min_confidence=0.9, fallback="human"), "human")

    def test_route_uses_probability_without_confidence(self):
        backend, _ = jev({"answers": {"department": {"type": "choice", "choice": "sales",
                                                     "probabilities": {"sales": 0.4, "billing": 0.6}}}})
        self.assertIsNone(DecisionModel(backend).route(STATE, DEPARTMENT, min_confidence=0.5))


class CLITest(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        # A clean environment keeps provider keys and DECISION_BACKEND out of the tests.
        with mock.patch.dict(os.environ, {}, clear=True), redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_for_both_backends(self):
        for backend, url in (("jev", "https://api.typesafe.ai/v1/systemone"),
                             ("openai", "https://api.openai.com/v1/decisions")):
            with self.subTest(backend):
                code, out, _ = self.run_cli("--questions", str(EXAMPLE), "--state", STATE,
                                            "--backend", backend, "--dry-run")
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)["url"], url)

    def test_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"text": STATE}))
            code, out, _ = self.run_cli("--questions", str(EXAMPLE), "--state-file", str(path),
                                        "--backend", "jev", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["body"]["state"], {"text": STATE})

    def test_invalid_questions_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.json"
            path.write_text(json.dumps({"q": {"type": "score", "instructions": "x", "criteria": ["a"]}}))
            code, _, err = self.run_cli("--questions", str(path), "--state", STATE, "--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("levels", err)

    def test_invalid_state_exits_2_even_in_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = {"number.json": "5", "empty.json": "[]", "blank.json": '["ok", ""]', "blank.txt": "  \n"}
            for name, text in cases.items():
                path = Path(tmp) / name
                path.write_text(text)
                for dry_run in ((), ("--dry-run",)):
                    with self.subTest(name, dry_run=dry_run):
                        code, out, err = self.run_cli("--questions", str(EXAMPLE), "--state-file", str(path),
                                                      "--backend", "jev", *dry_run)
                        self.assertEqual(code, 2)
                        self.assertEqual(out, "")
                        self.assertIn("state must be", err)
        code, out, _ = self.run_cli("--questions", str(EXAMPLE), "--state", " ", "--dry-run")
        self.assertEqual((code, out), (2, ""))

    def test_undecodable_state_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.txt"
            path.write_bytes(b"\xff\xfe payouts")
            code, _, err = self.run_cli("--questions", str(EXAMPLE), "--state-file", str(path), "--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_timeout_must_be_positive(self):
        for timeout in ("0", "-1", "nan", "inf", "soon"):
            with self.subTest(timeout), self.assertRaises(SystemExit) as raised:
                self.run_cli("--questions", str(EXAMPLE), "--state", STATE, "--timeout", timeout, "--dry-run")
            self.assertEqual(raised.exception.code, 2)
        code, _, _ = self.run_cli("--questions", str(EXAMPLE), "--state", STATE, "--timeout", "2.5", "--dry-run")
        self.assertEqual(code, 0)

    def test_backend_rejects_invalid_timeout(self):
        for timeout in (0, -1.0, float("nan"), float("inf"), True, "30"):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(DecisionError, "timeout"):
                JevBackend(api_key="k", env={}, timeout=timeout)

    def test_missing_key_exits_1(self):
        code, _, err = self.run_cli("--questions", str(EXAMPLE), "--state", STATE, "--backend", "jev")
        self.assertEqual(code, 1)
        self.assertIn("API key", err)


if __name__ == "__main__":
    unittest.main()
