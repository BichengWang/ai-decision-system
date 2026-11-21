import copy
import hashlib
import io
import json
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from jevdecision import APIError, JevBackend, OpenAIDecisionsBackend, questions_from_spec
from jevdecision.__main__ import main as decide_main
from jevdecision.evaluation import main as eval_main
from jevdecision.records import DIGEST_FIELD, answer_record, dumps_record, record_digest
from jevdecision.verify import main as verify_main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
QUESTIONS_FILE = EXAMPLES / "support-ticket.json"
CASES_FILE = EXAMPLES / "support-ticket-cases.jsonl"
RESPONSES_FILE = EXAMPLES / "support-ticket-responses.jsonl"
REQUIRE_FILE = EXAMPLES / "support-ticket-requirements.json"
QUESTIONS = questions_from_spec(json.loads(QUESTIONS_FILE.read_text()))
RESPONSE = json.loads(RESPONSES_FILE.read_text().splitlines()[0])["response"]
STATE = "Help! My payouts have been failing for 3 days."


def run(main, *args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def make_record(response=RESPONSE, backend_class=JevBackend, questions=QUESTIONS):
    backend = backend_class(api_key="k", transport=lambda *a: copy.deepcopy(response), env={})
    return answer_record(backend.decide(STATE, questions), questions)


def reseal(record):
    record[DIGEST_FIELD] = record_digest(record)
    return record


class AnswerRecordTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def verify(self, record, text=None):
        path = self.dir / "answer.json"
        path.write_text(dumps_record(record) if text is None else text, encoding="utf-8")
        return run(verify_main, path)

    def test_fresh_record_verifies_and_is_canonical(self):
        record = make_record()
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(set(record["questions"]), {"refund", "department", "frustration"})
        self.assertEqual(record["response"], RESPONSE)
        code, out, _ = self.verify(record)
        self.assertEqual((code, out.strip().endswith("verified")), (0, True))
        # The written file is the JCS form: re-serializing the parsed file gives the same text.
        text = dumps_record(record)
        self.assertEqual(dumps_record(json.loads(text)), text)

    def test_openai_backend_record_verifies(self):
        response = {"model": "gpt-6-luna", "id": "r1", "usage": {"total_tokens": 7}, "answers": [
            {"type": "predicate", "name": "refund", "probability": 0.12},
            {"type": "choice", "name": "department", "value": "technical",
             "probabilities": [{"value": "billing", "probability": 0.08}, {"value": "technical", "probability": 0.85},
                               {"value": "sales", "probability": 0.07}]},
            {"type": "score", "name": "frustration", "score": 1, "probabilities": [
                {"label": "Calm", "probability": 0.0}, {"label": "Frustrated", "probability": 1.0},
                {"label": "Very angry", "probability": 0.0}]}]}
        record = make_record(response, OpenAIDecisionsBackend)
        self.assertEqual(record["backend"], "openai")
        self.assertEqual(self.verify(record)[0], 0)

    def test_refusal_and_integral_float_canonicalization_verify(self):
        response = {"id": "x", "answers": {"refund": {"type": "refusal"}, "department": {
            "choice": "billing", "probabilities": {"billing": 1.0, "technical": 0.0, "sales": 0.0}},
            "frustration": {"score": 2.0}}}
        record = make_record(response)
        self.assertEqual(record["answers"]["refund"], {"type": "refusal"})
        self.assertEqual(self.verify(record)[0], 0)
        # 1.0 is written as 1 in canonical text; the record still verifies after a round trip.
        self.assertIn('"billing":1', dumps_record(record))
        self.assertEqual(self.verify(record)[0], 0)

    def test_model_requested_but_not_echoed_is_recorded(self):
        response = {"answers": {k: v for k, v in RESPONSE["answers"].items()}}
        record = make_record(response)
        self.assertEqual(record["model"], "jev-latest")
        self.assertEqual(self.verify(record)[0], 0)
        record["model"] = ""
        self.assertEqual(self.verify(reseal(record))[0], 1)

    def test_altering_any_field_exits_1(self):
        edits = {
            "answers": lambda r: r["answers"]["refund"].update(probability=0.99),
            "answers-choice": lambda r: r["answers"]["department"].update(choice="sales"),
            "answers-removed": lambda r: r["answers"].pop("refund"),
            "model": lambda r: r.update(model="other"),
            "id": lambda r: r.update(id="forged"),
            "usage": lambda r: r.update(usage={"credits_used": 1}),
            "produced_by.version": lambda r: r["produced_by"].update(version="9.9.9"),
            "questions.instructions": lambda r: r["questions"]["refund"].update(instructions="Another question?"),
            "response.probability": lambda r: r["response"]["answers"]["refund"].update(noul=0.5),
            "response.extra": lambda r: r["response"].update(note="added"),
            "response.model": lambda r: r["response"].update(model="forged"),
            "backend": lambda r: r.update(backend="openai"),
        }
        for name, edit in edits.items():
            for sealed in (False, True):
                record = make_record()
                edit(record)
                if sealed:
                    reseal(record)
                with self.subTest(field=name, resealed=sealed):
                    code, out, err = self.verify(record)
                    if name in ("questions.instructions", "produced_by.version", "response.extra", "backend") and sealed:
                        # Not derivable from the response: a consistently re-sealed edit is not detectable.
                        self.assertEqual(code, 0, out + err)
                    else:
                        self.assertEqual(code, 1, out + err)

    def test_changed_question_definition_that_breaks_the_response_exits_1(self):
        record = make_record()
        record["questions"]["department"]["criteria"] = {"billing": "x", "other": "y"}
        for sealed in (False, True):
            if sealed:
                reseal(record)
            code, out, _ = self.verify(record)
            self.assertEqual(code, 1)
            self.assertIn("record_sha256" if not sealed else "does not parse", out)

    def test_every_response_byte_is_covered(self):
        text = dumps_record(make_record())
        start = text.index('"response":')
        checked = 0
        for position in range(start, len(text) - 80, 5):
            replacement = "0" if text[position] != "0" else "1"
            altered = text[:position] + replacement + text[position + 1:]
            try:
                json.loads(altered)
            except ValueError:
                continue
            checked += 1
            with self.subTest(position=position):
                self.assertNotEqual(self.verify(None, altered)[0], 0)
        self.assertGreater(checked, 20)

    def test_malformed_input_exits_2(self):
        good = make_record()
        cases = {
            "not json": "{",
            "empty": "",
            "list": "[]",
            "nan": dumps_record(good).replace('"noul":0.08', '"noul":NaN', 1),
            "huge exponent": dumps_record(good).replace('"noul":0.08', '"noul":1e999', 1),
            "duplicate key": dumps_record(good)[:-1] + ',"id":"again"}',
            "oversized integer": dumps_record(good).replace('"noul":0.08', '"noul":0.08,"x":1152921504606846976', 1),
            "duplicate nested key": dumps_record(good).replace('"noul":0.08', '"noul":0.08,"noul":0.5', 1),
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                code, _, err = self.verify(None, text)
                self.assertEqual(code, 2, err)
                self.assertIn("cannot verify", err)
        edits = {
            "missing field": lambda r: r.pop("questions"),
            "unexpected field": lambda r: r.update(extra=1),
            "unknown schema": lambda r: r.update(schema_version=3),
            "bool schema": lambda r: r.update(schema_version=True),
            "no schema": lambda r: r.pop("schema_version"),
            "bad producer": lambda r: r.update(produced_by={"name": "other", "version": "1"}),
            "unknown backend": lambda r: r.update(backend="other"),
            "short digest": lambda r: r.update(record_sha256="abc"),
            "uppercase digest": lambda r: r.update(record_sha256=r["record_sha256"].upper()),
            "response list": lambda r: r.update(response=[]),
            "usage list": lambda r: r.update(usage=[]),
            "answers list": lambda r: r.update(answers=[]),
            "empty questions": lambda r: r.update(questions={}),
            "unknown question type": lambda r: r["questions"]["refund"].update(type="other"),
            "predicate alias": lambda r: r["questions"]["refund"].update(type="predicate"),
            "extra question key": lambda r: r["questions"]["refund"].update(note="x"),
            "bad question name": lambda r: r["questions"].update({"1bad": r["questions"]["refund"]}),
        }
        for name, edit in edits.items():
            record = copy.deepcopy(good)
            edit(record)
            with self.subTest(name=name):
                code, _, err = self.verify(record)
                self.assertEqual(code, 2, err)

    def test_schema_1_is_unverifiable_and_exits_2(self):
        backend = JevBackend(api_key="k", transport=lambda *a: RESPONSE, env={})
        v1 = backend.decide(STATE, QUESTIONS).to_dict()
        self.assertEqual(v1["schema_version"], 1)
        code, out, err = self.verify(v1)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("schema 1 cannot be verified", err)

    def test_missing_file_exits_2_and_two_failures_report_the_worst(self):
        good = self.dir / "good.json"
        good.write_text(dumps_record(make_record()))
        bad = make_record()
        bad["id"] = "forged"
        tampered = self.dir / "tampered.json"
        tampered.write_text(dumps_record(bad))
        self.assertEqual(run(verify_main, self.dir / "missing.json")[0], 2)
        self.assertEqual(run(verify_main, good, tampered)[0], 1)
        self.assertEqual(run(verify_main, tampered, self.dir / "missing.json", good)[0], 2)
        self.assertEqual(run(verify_main, good, good)[0], 0)

    def test_usage_errors_exit_2(self):
        for args in ((), ("--questions", "q.json", "--evaluation", "a", "--evaluation", "b")):
            with self.subTest(args=args), self.assertRaises(SystemExit) as raised:
                run(verify_main, *args)
            self.assertEqual(raised.exception.code, 2)

    def test_cli_writes_schema_2_by_default_and_schema_1_on_request(self):
        backend = JevBackend(api_key="k", transport=lambda *a: copy.deepcopy(RESPONSE), env={})
        for argv, schema in (([], 2), (["--schema-version", "1"], 1), (["--schema-version", "2"], 2)):
            with self.subTest(argv=argv), unittest.mock.patch(
                    "jevdecision.__main__.create_backend", return_value=backend):
                code, out, _ = run(decide_main, "--questions", QUESTIONS_FILE, "--state", STATE, *argv)
                self.assertEqual(code, 0)
                record = json.loads(out)
                self.assertEqual(record["schema_version"], schema)
                if schema == 2:
                    self.assertEqual(out.strip(), dumps_record(record))
                    self.assertEqual(self.verify(None, out)[0], 0)
                else:
                    self.assertNotIn("response", record)

    def test_cli_with_unrecordable_response_exits_1(self):
        response = copy.deepcopy(RESPONSE)
        response["counter"] = 2 ** 60
        backend = JevBackend(api_key="k", transport=lambda *a: response, env={})
        with unittest.mock.patch("jevdecision.__main__.create_backend", return_value=backend):
            code, out, err = run(decide_main, "--questions", QUESTIONS_FILE, "--state", STATE)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("canonical", err)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_provenance(directory, mutate=None):
    provenance = json.loads((directory / "provenance.json").read_text())
    for name in provenance["outputs"]:
        if (directory / name).exists():
            provenance["outputs"][name]["sha256"] = sha((directory / name).read_bytes())
    if mutate:
        mutate(provenance)
    (directory / "provenance.json").write_text(
        json.dumps(provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


class EvaluationDirectoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.out = self.root / "run"
        code, _, _ = run(eval_main, "--questions", QUESTIONS_FILE, "--cases", CASES_FILE,
                         "--responses", RESPONSES_FILE, "--require", REQUIRE_FILE, "--out", self.out)
        self.assertEqual(code, 0)

    def copy(self, name="copy"):
        target = self.root / name
        target.mkdir()
        for path in self.out.iterdir():
            (target / path.name).write_bytes(path.read_bytes())
        return target

    def verify(self, directory, *extra):
        return run(verify_main, "--evaluation", directory, *extra)

    def test_fresh_run_verifies_and_retains_inputs(self):
        self.assertEqual((self.out / "questions.json").read_bytes(), QUESTIONS_FILE.read_bytes())
        self.assertEqual((self.out / "requirements.json").read_bytes(), REQUIRE_FILE.read_bytes())
        code, out, err = self.verify(self.out)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("verified", out)

    def test_altering_any_retained_file_exits_1(self):
        for name in ("evaluation.json", "EVALUATION.md", "responses.jsonl", "cases.jsonl", "questions.json",
                     "requirements.json"):
            for edit in ("append", "flip", "delete"):
                directory = self.copy(f"{name}-{edit}")
                path = directory / name
                data = path.read_bytes()
                if edit == "append":
                    path.write_bytes(data + b" ")
                elif edit == "flip":
                    path.write_bytes(data[:10] + bytes([data[10] ^ 1]) + data[11:])
                else:
                    path.unlink()
                with self.subTest(file=name, edit=edit):
                    code, out, err = self.verify(directory)
                    self.assertEqual(code, 1, out + err)
                    self.assertIn(name, out)

    def test_altered_content_with_rewritten_provenance_is_caught_by_rescoring(self):
        def edit_responses(directory):
            path = directory / "responses.jsonl"
            path.write_text(path.read_text().replace('"noul":0.08', '"noul":0.8', 1)
                            if '"noul":0.08' in path.read_text() else path.read_text().replace("0.08", "0.8", 1))

        def edit_report(directory):
            path = directory / "evaluation.json"
            report = json.loads(path.read_text())
            report["questions"]["refund"]["accuracy"] = 1.0
            path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))

        def edit_status(directory):
            path = directory / "evaluation.json"
            report = json.loads(path.read_text())
            report["status"] = "UNGATED"
            path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))

        def edit_label(directory):
            path = directory / "cases.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[0]["questions"]["department"]["expected"] = "sales"
            path.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows))

        def edit_questions(directory):
            path = directory / "questions.json"
            spec = json.loads(path.read_text())
            spec["department"]["criteria"]["sales"] = "Something else"
            spec["refund"]["instructions"] = "Different?"
            path.write_text(json.dumps(spec))
            # the original inputs hash no longer matches either, so this also changes nothing silently
            report_path = directory / "evaluation.json"
            report = json.loads(report_path.read_text())
            report["questions"]["department"]["n"] = 1
            report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))

        for edit in (edit_responses, edit_report, edit_status, edit_label, edit_questions):
            directory = self.copy(edit.__name__)
            edit(directory)
            write_provenance(directory)
            with self.subTest(edit=edit.__name__):
                code, out, err = self.verify(directory)
                self.assertEqual(code, 1, out + err)

    def test_requirement_bounds_are_rescored(self):
        directory = self.copy()
        path = directory / "evaluation.json"
        report = json.loads(path.read_text())
        report["requirements"][1]["limit"] = 0
        path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        write_provenance(directory)
        code, out, _ = self.verify(directory)
        self.assertEqual(code, 1)
        self.assertIn("evaluation.json:requirements", out)

    def test_derived_floats_compare_with_relative_tolerance_everything_else_exactly(self):
        def with_report(edit):
            directory = self.copy(f"tol-{len(list(self.root.iterdir()))}")
            path = directory / "evaluation.json"
            report = json.loads(path.read_text())
            edit(report)
            path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            write_provenance(directory)
            return self.verify(directory)

        def nudge(factor):
            def edit(report):
                metrics = report["questions"]["refund"]
                metrics["brier"] *= factor
                metrics["accuracy_lower"] *= factor
            return edit

        self.assertEqual(with_report(nudge(1 + 1e-11))[0], 0)
        self.assertEqual(with_report(nudge(1 - 1e-11))[0], 0)
        self.assertEqual(with_report(nudge(1 + 1e-6))[0], 1)
        self.assertEqual(with_report(lambda r: r["requirements"][0].update(value=5e-13))[0], 0)  # expected exactly 0
        self.assertEqual(with_report(lambda r: r["requirements"][0].update(value=1e-6))[0], 1)
        self.assertEqual(with_report(lambda r: r["requirements"][1].update(limit=r["requirements"][1]["limit"] * (1 + 1e-11)))[0], 1)
        self.assertEqual(with_report(lambda r: r["questions"]["refund"].update(n=r["questions"]["refund"]["n"] + 1))[0], 1)
        self.assertEqual(with_report(lambda r: r["questions"]["refund"].update(refusals=0.0))[0], 1)

    def test_response_mode_must_match_report_source(self):
        directory = self.copy()
        write_provenance(directory, lambda p: p.update(response_mode="live"))
        code, out, _ = self.verify(directory)
        self.assertEqual(code, 1)
        self.assertIn("provenance.json:response_mode", out)

    def test_extra_response_for_unknown_case_exits_1(self):
        directory = self.copy()
        path = directory / "responses.jsonl"
        path.write_text(path.read_text() + json.dumps({"id": "ghost", "response": RESPONSE}) + "\n")
        write_provenance(directory)
        self.assertEqual(self.verify(directory)[0], 1)

    def test_malformed_provenance_exits_2(self):
        def drop_output(p):
            del p["outputs"]["cases.jsonl"]

        for name, mutate in {
            "unsupported schema": lambda p: p.update(schema_version=1),
            "unexpected key": lambda p: p.update(extra=1),
            "bad hash": lambda p: p["outputs"]["cases.jsonl"].update(sha256="xyz"),
            "missing output": drop_output,
            "bad mode": lambda p: p.update(response_mode="other"),
            "inputs": lambda p: p.update(inputs={}),
        }.items():
            directory = self.copy(name.replace(" ", "-"))
            provenance = json.loads((directory / "provenance.json").read_text())
            mutate(provenance)
            (directory / "provenance.json").write_text(json.dumps(provenance))
            with self.subTest(name=name):
                code, _, err = self.verify(directory)
                self.assertEqual(code, 2, err)
                self.assertIn("cannot verify", err)

    def test_missing_unparseable_or_duplicate_key_files_exit_2(self):
        (self.root / "empty").mkdir()
        self.assertEqual(self.verify(self.root / "empty")[0], 2)
        self.assertEqual(self.verify(self.root / "absent")[0], 2)
        for name, text in (("not-json", "{"), ("duplicate", '{"schema_version":2,"schema_version":2}')):
            directory = self.copy(name)
            (directory / "provenance.json").write_text(text)
            with self.subTest(name=name):
                self.assertEqual(self.verify(directory)[0], 2)

    def test_hash_valid_but_unparseable_content_exits_2(self):
        for index, (name, text) in enumerate((
                ("cases.jsonl", "{"), ("responses.jsonl", '{"id":"t01"}\n'), ("evaluation.json", "[]"),
                ("questions.json", "{}"), ("cases.jsonl", '{"id":"t01","questions":{"nope":{"expected":1}}}\n'))):
            directory = self.copy(f"bad-{index}")
            (directory / name).write_text(text)
            write_provenance(directory, (lambda p: p["inputs"]["questions"].update(sha256=sha(b"{}")))
                             if name == "questions.json" else None)
            with self.subTest(file=name, text=text):
                code, _, err = self.verify(directory)
                self.assertEqual(code, 2, err)

    def test_run_without_retained_inputs_needs_the_original_files(self):
        directory = self.copy()
        for name in ("questions.json", "requirements.json"):
            (directory / name).unlink()

        def drop(provenance):
            del provenance["outputs"]["questions.json"], provenance["outputs"]["requirements.json"]

        write_provenance(directory, drop)
        code, _, err = self.verify(directory)
        self.assertEqual(code, 2)
        self.assertIn("--questions", err)
        code, _, err = self.verify(directory, "--questions", QUESTIONS_FILE)
        self.assertEqual(code, 2)
        self.assertIn("--requirements", err)
        self.assertEqual(self.verify(directory, "--questions", QUESTIONS_FILE, "--requirements", REQUIRE_FILE)[0], 0)
        wrong = self.root / "other.json"
        wrong.write_text(QUESTIONS_FILE.read_text() + " ")
        code, out, _ = self.verify(directory, "--questions", wrong, "--requirements", REQUIRE_FILE)
        self.assertEqual(code, 1)
        self.assertIn("differs from the questions input", out)

    def test_run_without_requirements_retains_none(self):
        directory = self.root / "ungated"
        code, _, _ = run(eval_main, "--questions", QUESTIONS_FILE, "--cases", CASES_FILE,
                         "--responses", RESPONSES_FILE, "--out", directory)
        self.assertEqual(code, 3)
        self.assertFalse((directory / "requirements.json").exists())
        self.assertEqual(self.verify(directory)[0], 0)
        # A requirement file added afterwards does not match the recorded absence of one.
        (directory / "requirements.json").write_bytes(REQUIRE_FILE.read_bytes())
        write_provenance(directory, lambda p: p["outputs"].update({"requirements.json": {"sha256": sha(REQUIRE_FILE.read_bytes())}}))
        self.assertEqual(self.verify(directory)[0], 1)

    def test_live_run_with_request_failure_and_unparseable_response_verifies(self):
        cases = [json.loads(line) for line in CASES_FILE.read_text().splitlines()][:3]
        responses = [RESPONSE, APIError("HTTP 500 from provider", 500), {"answers": {"refund": {"noul": 4}}}]

        def transport(*args):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        backend = JevBackend(api_key="k", transport=transport, sleep=lambda _: None, max_retries=0, env={})
        cases_file = self.root / "live-cases.jsonl"
        cases_file.write_text("".join(json.dumps(c) + "\n" for c in cases))
        out = self.root / "live"
        with unittest.mock.patch("jevdecision.evaluation.create_backend", return_value=backend):
            code, _, _ = run(eval_main, "--questions", QUESTIONS_FILE, "--cases", cases_file, "--out", out)
        self.assertEqual(code, 1)
        report = json.loads((out / "evaluation.json").read_text())
        self.assertEqual(report["source"], "live")
        self.assertEqual(len(report["errors"]), 2)
        self.assertEqual(self.verify(out), (0, f"{out}: verified\n", ""))
        # A forged error message for a response that exists is caught; one for a failed request is not derivable.
        forged = self.root / "forged"
        forged.mkdir()
        for path in out.iterdir():
            (forged / path.name).write_bytes(path.read_bytes())
        report["errors"][1]["error"] = "forged"
        (forged / "evaluation.json").write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
        write_provenance(forged)
        self.assertEqual(self.verify(forged)[0], 1)
        self.assertEqual(report["errors"][0]["id"], "t02")  # the failed request: no response to re-derive from

        def rewrite(name, edit):
            directory = self.root / name
            directory.mkdir()
            for path in out.iterdir():
                (directory / path.name).write_bytes(path.read_bytes())
            report = json.loads((directory / "evaluation.json").read_text())
            rows = [json.loads(line) for line in (directory / "cases.jsonl").read_text().splitlines()]
            edit(report, rows)
            (directory / "evaluation.json").write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
            (directory / "cases.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))
            write_provenance(directory)
            return directory

        # A non-string message copied consistently into evaluation.json and cases.jsonl is malformed (exit 2),
        # not verified. Any string message for the failed request is accepted: it cannot be re-derived.
        for index, value in enumerate(({"not": "a string"}, ["x"], 7, None, True)):
            def malformed(report, rows, value=value):
                report["errors"][0]["error"] = value
                next(row for row in rows if row["id"] == "t02")["error"] = value

            with self.subTest(value=value):
                code, stdout, stderr = self.verify(rewrite(f"bad-error-{index}", malformed))
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn("invalid errors entry", stderr)

        def reworded(report, rows):
            report["errors"][0]["error"] = "another message"
            next(row for row in rows if row["id"] == "t02")["error"] = "another message"

        self.assertEqual(self.verify(rewrite("reworded", reworded))[0], 0)

        def duplicated(report, rows):
            report["errors"].append(dict(report["errors"][0]))

        code, _, stderr = self.verify(rewrite("duplicated-error", duplicated))
        self.assertEqual(code, 2)
        self.assertIn("more than one error", stderr)

    def test_unicode_line_separators_in_a_response_verify_and_replay(self):
        rows = [json.loads(line) for line in RESPONSES_FILE.read_text().splitlines()]
        rows[0]["response"]["id"] = "example\u2028t01"
        responses = self.root / "separators.jsonl"
        responses.write_text("".join(json.dumps(row) + "\n" for row in rows))  # escaped in the input
        out, again = self.root / "separators", self.root / "separators-again"
        common = ("--questions", QUESTIONS_FILE, "--cases", CASES_FILE, "--require", REQUIRE_FILE)
        self.assertEqual(run(eval_main, *common, "--responses", responses, "--out", out)[0], 0)
        self.assertIn("\u2028", (out / "responses.jsonl").read_text(encoding="utf-8"))  # written unescaped
        self.assertEqual(self.verify(out), (0, f"{out}: verified\n", ""))
        self.assertEqual(run(eval_main, *common, "--responses", out / "responses.jsonl", "--out", again)[0], 0)
        self.assertEqual((again / "evaluation.json").read_bytes(), (out / "evaluation.json").read_bytes())

    def test_replay_error_entries_must_be_well_formed_too(self):
        directory = self.copy("replay-bad-error")
        report = json.loads((directory / "evaluation.json").read_text())
        report["errors"] = [{"id": "t01", "error": {"not": "a string"}}]
        (directory / "evaluation.json").write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
        write_provenance(directory)
        self.assertEqual(self.verify(directory)[0], 2)

    def test_cli_exits_zero_only_when_every_target_verifies(self):
        record = self.root / "answer.json"
        record.write_text(dumps_record(make_record()))
        self.assertEqual(run(verify_main, record, "--evaluation", self.out)[0], 0)
        tampered = self.copy()
        (tampered / "cases.jsonl").write_bytes(b"")
        self.assertEqual(run(verify_main, record, "--evaluation", self.out, "--evaluation", tampered)[0], 1)


if __name__ == "__main__":
    unittest.main()
