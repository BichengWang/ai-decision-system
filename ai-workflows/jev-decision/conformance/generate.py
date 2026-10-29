"""Generate the Jev conformance vectors and manifest.json (standard library only, deterministic).

    python3 conformance/generate.py            # rewrite conformance/{valid,tampered,invalid} and manifest.json
    python3 conformance/generate.py --check    # compare with the committed tree, write nothing; exit 1 if it differs
    python3 conformance/generate.py --out DIR  # write the tree under DIR instead (with --check: compare DIR)

Every vector is derived from fixed inputs: the example questions, cases and responses in
`examples/`, hand-written provider responses below, and named edits recorded in each vector's
`note`. Nothing here is output from a live provider. `--check` and `tests/test_conformance.py` assert
that the committed tree equals a fresh generation under `tree_differences` (byte-exact except for the
platform difference of metric floats in evaluation directories). Regenerate after changing the record formats or the
package version (records carry `produced_by.version`).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPONENT = ROOT.parent
sys.path.insert(0, str(COMPONENT))

from jevdecision import APIError, JevBackend, OpenAIDecisionsBackend, questions_from_spec  # noqa: E402
from jevdecision.evaluation import main as evaluate_main, render_markdown  # noqa: E402
from jevdecision.jcs import canonicalize  # noqa: E402
from jevdecision.records import DIGEST_FIELD, answer_record, dumps_record, record_digest  # noqa: E402
from jevdecision.verify import _close  # noqa: E402

EXAMPLES = COMPONENT / "examples"
QUESTIONS_FILE = EXAMPLES / "support-ticket.json"
CASES_FILE = EXAMPLES / "support-ticket-cases.jsonl"
RESPONSES_FILE = EXAMPLES / "support-ticket-responses.jsonl"
REQUIRE_FILE = EXAMPLES / "support-ticket-requirements.json"
STATE = "Help! My payouts have been failing for 3 days."
SCHEMA_DIR = "jevdecision/schema/"
VERIFY = "jev-decision-verify"

# Hand-written responses in the providers' formats; synthetic, not provider output.
JEV_RESPONSE = json.loads(RESPONSES_FILE.read_text(encoding="utf-8").splitlines()[0])["response"]
OPENAI_RESPONSE = {
    "model": "decisions-example", "id": "example-openai-1", "usage": {"total_tokens": 7},
    "answers": [
        {"type": "predicate", "name": "refund", "probability": 0.12},
        {"type": "choice", "name": "department", "value": "technical",
         "probabilities": [{"value": "billing", "probability": 0.08}, {"value": "technical", "probability": 0.85},
                           {"value": "sales", "probability": 0.07}]},
        {"type": "score", "name": "frustration", "score": 1, "probabilities": [
            {"label": "Calm", "probability": 0.0}, {"label": "Frustrated", "probability": 1.0},
            {"label": "Very angry", "probability": 0.0}]},
    ],
}
# Exercises canonical number formatting (1e-7, 5e-324, integral floats), non-ASCII text and
# UTF-16 member ordering (the emoji and the Hebrew letter sort differently by code point).
CANON_QUESTIONS = {
    "tone": {"type": "choice", "instructions": "Which tone fits? Réponse: ✓ 日本語",
             "criteria": {"a": "Plain", "é": "Accent", "€": "Euro sign", "😀": "Emoji", "\ufb33": "Hebrew dagesh"}},
    "urgency": {"type": "score", "instructions": "How urgent is it?", "criteria": ["low", "high"]},
    "rare": {"type": "noul", "instructions": "Is this a rare event?"},
    "refund": {"type": "noul", "instructions": "Is the customer asking for a refund?"},
}
CANON_RESPONSE = {
    "model": "jev-example", "id": "example-canon-1", "usage": {"credits_used": 12.0},
    "answers": {
        "tone": {"type": "choice", "choice": "a", "probabilities": {
            "a": 0.5, "é": 0.25, "€": 0.125, "😀": 0.0625, "\ufb33": 0.0625}},
        "urgency": {"type": "score", "score": 1.0, "probabilities": [1e-07, 0.9999999]},
        "rare": {"type": "noul", "noul": 5e-324},
        "refund": {"type": "refusal"},
    },
}


class Tree:
    """Files and manifest entries for one generation."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.vectors: list[dict] = []

    def add_file(self, path, data):
        assert path not in self.files, path
        self.files[path] = data if isinstance(data, bytes) else data.encode("utf-8")

    def add_vector(self, path, expect, command, note, documents=None, digests=None):
        vector = {"path": path, "expect": expect,
                  "verify": {"command": command, "exit_code": {"valid": 0, "tampered": 1, "invalid": 2}[expect]}}
        if documents:
            vector["documents"] = documents
        if digests:
            vector["digests"] = digests
        vector["note"] = note
        self.vectors.append(vector)

    def manifest(self):
        return json.dumps({"format": 1, "package": "jevdecision", "vectors": self.vectors},
                          indent=2, ensure_ascii=False) + "\n"


def append_newline(data):
    """The named edit of tampered/evaluation-markdown-edited: one newline appended to EVALUATION.md."""
    return data + b"\n"


def document(schema, valid, path="."):
    return {"path": path, "schema": SCHEMA_DIR + schema, "schema_valid": valid}


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


# Answer records ------------------------------------------------------------

def make_answer(spec, response, backend_class=JevBackend):
    questions = questions_from_spec(spec)
    backend = backend_class(api_key="offline", transport=lambda *args: copy.deepcopy(response), env={})
    return answer_record(backend.decide(STATE, questions), questions)


def line(record):
    return dumps_record(record) + "\n"


def reseal(record):
    record[DIGEST_FIELD] = record_digest(record)
    return record


def add_answers(tree):
    support = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    base = {
        "answer-v2-jev": (make_answer(support, JEV_RESPONSE), "Jev-format response, noul/choice/score answers"),
        "answer-v2-openai": (make_answer(support, OPENAI_RESPONSE, OpenAIDecisionsBackend),
                             "OpenAI Decisions list-format response; backend openai"),
        "answer-v2-canonical-numbers": (make_answer(CANON_QUESTIONS, CANON_RESPONSE),
                                        "refusal, 1e-7, 5e-324, integral floats written as integers, "
                                        "non-ASCII text and UTF-16 key ordering in the canonical form"),
    }
    schema = "answer.v2.json"
    for name, (record, note) in base.items():
        path = f"valid/{name}.json"
        tree.add_file(path, line(record))
        covered = {k: v for k, v in record.items() if k != DIGEST_FIELD}
        canonical = f"valid/{name}.canonical"
        tree.add_file(canonical, canonicalize(covered))
        assert sha(canonicalize(covered)) == record[DIGEST_FIELD]
        tree.add_vector(path, "valid", [VERIFY, "{path}"], note, [document(schema, True)], [{
            "document": ".", "value": "/record_sha256", "covers": "", "exclude": [DIGEST_FIELD],
            "canonicalization": "rfc8785", "canonical_file": canonical}])

    jev = base["answer-v2-jev"][0]

    def edited(edit, sealed=False):
        record = copy.deepcopy(jev)
        edit(record)
        return reseal(record) if sealed else record

    tampered = {
        "answer-v2-answer-edited": (edited(lambda r: r["answers"]["refund"].update(probability=0.99)),
                                    "answers.refund.probability changed from 0.08 to 0.99; record_sha256 left"),
        "answer-v2-answer-edited-resealed": (
            edited(lambda r: r["answers"]["refund"].update(probability=0.99), True),
            "answers.refund.probability changed to 0.99 and record_sha256 recomputed; the embedded response "
            "no longer reproduces the answer"),
        "answer-v2-response-edited": (edited(lambda r: r["response"]["answers"]["refund"].update(noul=0.8)),
                                      "response.answers.refund.noul changed from 0.08 to 0.8; record_sha256 left"),
        "answer-v2-response-edited-resealed": (
            edited(lambda r: r["response"]["answers"]["refund"].update(noul=0.8), True),
            "response.answers.refund.noul changed to 0.8 and record_sha256 recomputed; the recorded answer no "
            "longer follows from the response"),
        "answer-v2-question-edited": (
            edited(lambda r: r["questions"]["refund"].update(instructions="Is the customer angry?")),
            "questions.refund.instructions changed; record_sha256 left"),
        "answer-v2-id-edited-resealed": (edited(lambda r: r.update(id="forged-id"), True),
                                         "id changed to forged-id and record_sha256 recomputed; the response id differs"),
    }
    for name, (record, note) in tampered.items():
        path = f"tampered/{name}.json"
        tree.add_file(path, line(record))
        tree.add_vector(path, "tampered", [VERIFY, "{path}"], note, [document(schema, True)])

    # Invalid inputs.
    from jevdecision import DecisionModel
    v1 = DecisionModel(JevBackend(api_key="offline", transport=lambda *a: copy.deepcopy(JEV_RESPONSE), env={})
                       ).decide(STATE, questions_from_spec(support)).to_dict()
    tree.add_file("invalid/answer-v1.json", compact(v1) + "\n")
    tree.add_vector("invalid/answer-v1.json", "invalid", [VERIFY, "{path}"],
                    "schema 1 answer record (0.1.0 shape): readable, but it embeds no questions or response, so it "
                    "is unverifiable", [document("answer.v1.json", True)])

    def invalid(name, record_or_text, note, schema_valid=None):
        path = f"invalid/{name}.json"
        text = record_or_text if isinstance(record_or_text, str) else line(record_or_text)
        tree.add_file(path, text)
        tree.add_vector(path, "invalid", [VERIFY, "{path}"], note,
                        None if schema_valid is None else [document(schema, schema_valid)])

    schema3 = edited(lambda r: r.update(schema_version=3))
    invalid("answer-v2-unsupported-schema", schema3, "schema_version changed to 3", False)
    missing = edited(lambda r: r.pop("questions"))
    invalid("answer-v2-missing-questions", missing, "questions member removed", False)
    text = line(jev)
    invalid("answer-v2-duplicate-key", text.rstrip("\n")[:-1] + ',"id":"example-t01"}\n',
            "a second id member appended to the top-level object (duplicate object keys)")
    invalid("answer-v2-non-finite", text.replace('"noul":0.08', '"noul":NaN', 1),
            "response.answers.refund.noul replaced by the non-JSON literal NaN")
    invalid("answer-v2-oversized-integer", text.replace('"response":{', '"response":{"counter":1152921504606846976,', 1),
            "response.counter = 2^60 inserted: outside the I-JSON safe range, so the record cannot be "
            "canonicalized; record_sha256 left", True)
    unnormalized = edited(lambda r: r["questions"]["refund"].update(type="predicate"))
    invalid("answer-v2-unnormalized-questions", unnormalized,
            "questions.refund.type changed to the alias predicate (not the normalized question map form)", False)


# Evaluation directories ----------------------------------------------------

def run_eval(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = evaluate_main([str(arg) for arg in args])
    return code


def read_dir(path):
    return {item.name: item.read_bytes() for item in sorted(path.iterdir())}


def reseal_dir(files, mutate=None):
    """Rewrite provenance.json so every listed output hash matches the files, then apply `mutate`."""
    provenance = json.loads(files["provenance.json"])
    for name in provenance["outputs"]:
        if name in files:
            provenance["outputs"][name]["sha256"] = sha(files[name])
    if mutate:
        mutate(provenance)
    files["provenance.json"] = compact(provenance).encode("utf-8")


def eval_digests(files, extra):
    """`bytes` digest entries for every hash in provenance.json whose file is in the vector directory."""
    provenance = json.loads(files["provenance.json"])
    entries = []
    for name in provenance["outputs"]:
        entries.append({"document": "provenance.json", "value": f"/outputs/{name}/sha256",
                        "canonicalization": "bytes", "covers_file": name})
    for role, entry in provenance["inputs"].items():
        if entry is not None:
            covers = {"questions": "questions.json", "requirements": "requirements.json",
                      "calibration": "calibration.json"}.get(role, extra.get(role))
            entries.append({"document": "provenance.json", "value": f"/inputs/{role}/sha256",
                            "canonicalization": "bytes", "covers_file": covers})
            assert sha(files[covers]) == entry["sha256"], role
    return entries


def add_dir(tree, kind, name, files, command_note, digests=None, documents=None):
    for filename, data in files.items():
        tree.add_file(f"{kind}/{name}/{filename}", data)
    tree.add_vector(f"{kind}/{name}", kind, [VERIFY, "--evaluation", "{path}"], command_note, documents, digests)


EVAL_DOCUMENTS = [document("evaluation.v2.json", True, "evaluation.json"),
                  document("provenance.v2.json", True, "provenance.json")]
CALIBRATED_DOCUMENTS = [document("evaluation.v3.json", True, "evaluation.json"),
                        document("provenance.v3.json", True, "provenance.json"),
                        document("calibration.v1.json", True, "calibration.json")]
# Requirements of the applied-calibration vector: a held-out bound on a calibrated metric.
CALIBRATED_REQUIREMENTS = {"questions": {"refund": {"n": {"min": 6}, "calibrated_ece": {"max": 0.15}}}}


def add_evaluations(tree):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        assert run_eval(["--questions", QUESTIONS_FILE, "--cases", CASES_FILE, "--responses", RESPONSES_FILE,
                         "--require", REQUIRE_FILE, "--out", tmp / "gated"]) == 0
        assert run_eval(["--questions", QUESTIONS_FILE, "--cases", CASES_FILE, "--responses", RESPONSES_FILE,
                         "--out", tmp / "ungated"]) == 3

        three = tmp / "three-cases.jsonl"
        three.write_text("".join(CASES_FILE.read_text(encoding="utf-8").splitlines(True)[:3]), encoding="utf-8")
        queue = [JEV_RESPONSE, APIError("HTTP 500 from provider", 500), {"answers": {"refund": {"noul": 4}}}]

        def transport(*args):
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return copy.deepcopy(item)

        backend = JevBackend(api_key="offline", transport=transport, sleep=lambda _: None, max_retries=0, env={})
        with unittest.mock.patch("jevdecision.evaluation.create_backend", return_value=backend):
            assert run_eval(["--questions", QUESTIONS_FILE, "--cases", three, "--out", tmp / "live"]) == 1

        gated, ungated, live = (read_dir(tmp / name) for name in ("gated", "ungated", "live"))
        inputs = {"cases": CASES_FILE.read_bytes(), "responses": RESPONSES_FILE.read_bytes()}
        extra_names = {"cases": "input-cases.jsonl", "responses": "input-responses.jsonl"}

        def with_inputs(files, cases=None):
            full = dict(files)
            full["input-cases.jsonl"] = inputs["cases"] if cases is None else cases
            if "input-responses.jsonl" not in full and json.loads(files["provenance.json"])["inputs"]["responses"]:
                full["input-responses.jsonl"] = inputs["responses"]
            return full

        gated_full, ungated_full = with_inputs(gated), with_inputs(ungated)
        live_full = with_inputs(live, three.read_bytes())
        live_full.pop("input-responses.jsonl", None)

        valid = (
            ("evaluation-replay-gated", gated_full, "replay of the 12 example cases with requirements (PASS); "
             "inputs retained for the cases and responses hashes"),
            ("evaluation-replay-ungated", ungated_full, "replay without requirements (UNGATED); no "
             "requirements.json and inputs.requirements null"),
            ("evaluation-live-failures", live_full, "recorded live run of 3 cases: one answered, one failed request "
             "(error text only in evaluation.json), one unparseable response"),
        )
        for name, files, note in valid:
            add_dir(tree, "valid", name, files, note, eval_digests(files, extra_names), EVAL_DOCUMENTS)

        # Tampered copies of the gated replay.
        def flip(data, offset=20):
            return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]

        files = dict(gated_full)
        files["responses.jsonl"] = flip(files["responses.jsonl"])
        add_dir(tree, "tampered", "evaluation-responses-edited", files,
                "one byte of responses.jsonl flipped; provenance.json left", None, EVAL_DOCUMENTS)

        files = dict(gated_full)
        report = json.loads(files["evaluation.json"])
        report["status"] = "FAIL"
        files["evaluation.json"] = compact(report).encode("utf-8")
        reseal_dir(files)
        add_dir(tree, "tampered", "evaluation-report-resealed", files,
                "evaluation.json status changed from PASS to FAIL and its provenance hash recomputed; re-scoring "
                "disagrees", None, EVAL_DOCUMENTS)

        files = dict(gated_full)
        spec = json.loads(files["requirements.json"])
        spec["max_error_rate"] = 0.5
        files["requirements.json"] = compact(spec).encode("utf-8")
        report = json.loads(files["evaluation.json"])
        report["requirements"][0]["limit"] = 0.5
        files["evaluation.json"] = compact(report).encode("utf-8")

        def rehash_requirements(provenance):
            provenance["inputs"]["requirements"]["sha256"] = sha(files["requirements.json"])

        reseal_dir(files, rehash_requirements)
        add_dir(tree, "tampered", "evaluation-requirements-edited-resealed", files,
                "retained requirements.json loosened (max_error_rate 0.5) and the error_rate limit, "
                "evaluation.json and provenance hashes rewritten consistently; the recorded check results no "
                "longer follow from the responses", None, EVAL_DOCUMENTS)

        files = dict(gated_full)
        del files["cases.jsonl"]
        add_dir(tree, "tampered", "evaluation-file-missing", files,
                "cases.jsonl removed although provenance.json lists it", None, EVAL_DOCUMENTS)

        files = dict(gated_full)
        files["EVALUATION.md"] = append_newline(files["EVALUATION.md"])
        add_dir(tree, "tampered", "evaluation-markdown-edited", files,
                "a newline appended to EVALUATION.md; provenance.json left", None, EVAL_DOCUMENTS)

        # Invalid directories.
        files = dict(gated_full)
        provenance = json.loads(files["provenance.json"])
        provenance["schema_version"] = 1
        files["provenance.json"] = compact(provenance).encode("utf-8")
        add_dir(tree, "invalid", "evaluation-provenance-schema-1", files,
                "provenance.json schema_version changed to 1 (unsupported)",
                None, [document("provenance.v2.json", False, "provenance.json")])

        files = dict(gated_full)
        text = files["provenance.json"].decode("utf-8")
        files["provenance.json"] = (text[:-1] + ',"response_mode":"replay"}').encode("utf-8")
        add_dir(tree, "invalid", "evaluation-provenance-duplicate-key", files,
                "a second response_mode member appended to provenance.json (duplicate object keys)")

        files = dict(gated_full)
        files["cases.jsonl"] = b"{\n"
        reseal_dir(files)
        add_dir(tree, "invalid", "evaluation-cases-unparseable", files,
                "cases.jsonl replaced by an unparseable line and its provenance hash recomputed",
                None, EVAL_DOCUMENTS)

        files = dict(gated_full)
        provenance = json.loads(files["provenance.json"])
        del provenance["outputs"]["cases.jsonl"]
        files["provenance.json"] = compact(provenance).encode("utf-8")
        add_dir(tree, "invalid", "evaluation-provenance-missing-output", files,
                "the cases.jsonl entry removed from provenance.json outputs",
                None, [document("provenance.v2.json", False, "provenance.json")])

        add_calibrations(tree, tmp, extra_names)


def add_calibrations(tree, tmp, extra_names):
    """Fit an isotonic calibration on cases t01-t06 and apply it to t07-t12. Isotonic fitting uses only
    integer counts and one division per block, so calibration.json is the same bytes on every platform."""
    cases, responses = (path.read_text(encoding="utf-8").splitlines(True) for path in (CASES_FILE, RESPONSES_FILE))
    halves = {}
    for name, rows in (("fit", slice(0, 6)), ("held-out", slice(6, 12))):
        halves[name] = tuple("".join(lines[rows]).encode("utf-8") for lines in (cases, responses))
        for suffix, data in zip(("cases", "responses"), halves[name]):
            (tmp / f"{name}-{suffix}.jsonl").write_bytes(data)
    (tmp / "calibrated-requirements.json").write_text(compact(CALIBRATED_REQUIREMENTS), encoding="utf-8")
    assert run_eval(["--questions", QUESTIONS_FILE, "--cases", tmp / "fit-cases.jsonl",
                     "--responses", tmp / "fit-responses.jsonl", "--fit-calibration", "isotonic",
                     "--out", tmp / "fitted"]) == 3
    assert run_eval(["--questions", QUESTIONS_FILE, "--cases", tmp / "held-out-cases.jsonl",
                     "--responses", tmp / "held-out-responses.jsonl", "--calibration", tmp / "fitted" / "calibration.json",
                     "--require", tmp / "calibrated-requirements.json", "--out", tmp / "applied"]) == 0

    def with_inputs(path, half):
        files = read_dir(path)
        files["input-cases.jsonl"], files["input-responses.jsonl"] = halves[half]
        return files

    fitted, applied = with_inputs(tmp / "fitted", "fit"), with_inputs(tmp / "applied", "held-out")
    for name, files, note in (
            ("evaluation-calibration-fitted", fitted, "isotonic calibration fitted on example cases t01-t06 "
             "(schema 3, UNGATED); the verifier refits calibration.json from responses.jsonl and cases.jsonl"),
            ("evaluation-calibration-applied", applied, "the fitted calibration applied to held-out cases t07-t12 "
             "with a calibrated_ece bound (PASS); calibration.json is the retained calibration input")):
        add_dir(tree, "valid", name, files, note, eval_digests(files, extra_names), CALIBRATED_DOCUMENTS)

    def rewrite_calibration(files, edit, rehash_input=False):
        document = json.loads(files["calibration.json"])
        edit(document)
        files["calibration.json"] = compact(document).encode("utf-8")
        report = json.loads(files["evaluation.json"])
        report["calibration"]["sha256"] = sha(files["calibration.json"])
        files["evaluation.json"] = compact(report).encode("utf-8")

        def rehash(provenance):
            if rehash_input:
                provenance["inputs"]["calibration"]["sha256"] = sha(files["calibration.json"])

        reseal_dir(files, rehash)

    files = dict(fitted)
    rewrite_calibration(files, lambda d: d["questions"]["refund"]["map"].update(y=[0.0, 0.25, 1.0, 1.0]))
    add_dir(tree, "tampered", "evaluation-calibration-refit-differs", files,
            "calibration.json refund map y changed from [0, 0, 1, 1] to [0, 0.25, 1, 1], and the calibration "
            "hash in evaluation.json and provenance.json recomputed; refitting gives the original map",
            None, CALIBRATED_DOCUMENTS)

    files = dict(applied)
    report = json.loads(files["evaluation.json"])
    report["questions"]["refund"]["calibrated_ece"] = 0.01
    files["evaluation.json"] = compact(report).encode("utf-8")
    reseal_dir(files)
    add_dir(tree, "tampered", "evaluation-calibrated-metric-edited-resealed", files,
            "evaluation.json refund calibrated_ece changed to 0.01 and its provenance hash recomputed; "
            "re-applying calibration.json disagrees", None, CALIBRATED_DOCUMENTS)

    files = dict(applied)
    rewrite_calibration(files, lambda d: d["fitted_on"].update(case_ids=sorted(d["fitted_on"]["case_ids"] + ["t07"])),
                        rehash_input=True)
    add_dir(tree, "invalid", "evaluation-calibration-overlap", files,
            "held-out case t07 added to calibration.json fitted_on.case_ids, with every calibration hash "
            "recomputed: a calibration fitted on a case of the evaluation it is applied to is refused",
            None, CALIBRATED_DOCUMENTS)


def generate():
    tree = Tree()
    add_answers(tree)
    add_evaluations(tree)
    order = {"valid": 0, "tampered": 1, "invalid": 2}
    tree.vectors.sort(key=lambda vector: (order[vector["expect"]], vector["path"]))
    tree.add_file("manifest.json", tree.manifest())
    return tree.files


class Mismatch(AssertionError):
    """A committed vector is not a fresh generation under the comparison rules."""


def require(condition, message):
    if not condition:
        raise Mismatch(message)


DIGEST_LINE = re.compile(rb"(- evaluation\.json SHA-256: `)[0-9a-f]{64}(`)")
# Vectors whose provenance.json deliberately lists a hash that is not that of the committed file.
STALE_BY_DESIGN = {"evaluation-markdown-edited": ("EVALUATION.md", lambda data: data[:-1])}
# Every tampered and invalid evaluation vector is derived from a valid one by a named edit: this one, or
# its entry in SOURCE_VECTORS. Only the edits that change EVALUATION.md appear in MARKDOWN_EDITS; all
# others leave it byte-identical to the source.
SOURCE_VECTOR = "evaluation-replay-gated"
SOURCE_VECTORS = {"evaluation-calibration-refit-differs": "evaluation-calibration-fitted",
                  "evaluation-calibrated-metric-edited-resealed": "evaluation-calibration-applied",
                  "evaluation-calibration-overlap": "evaluation-calibration-applied"}
MARKDOWN_EDITS = {"evaluation-markdown-edited": lambda data: data + b"\n"}
EVALUATION_RULE_FILES = ("evaluation.json", "EVALUATION.md", "provenance.json")
KINDS = ("valid", "tampered", "invalid")
EVALUATION_DIRECTORIES = 17


def check_derived_hashes(name, directory, files):
    """provenance.json's hashes of evaluation.json and EVALUATION.md must be those files' SHA-256, except
    where the vector deliberately leaves a stale one. Returns provenance.json with those two values masked."""
    provenance = json.loads(files["provenance.json"])
    outputs = provenance.get("outputs", {})
    for filename in ("evaluation.json", "EVALUATION.md"):
        if filename not in outputs:
            continue
        recorded, outputs[filename]["sha256"] = outputs[filename]["sha256"], "X"
        data = files.get(filename)
        if data is None:
            continue
        if directory in STALE_BY_DESIGN and STALE_BY_DESIGN[directory][0] == filename:
            data = STALE_BY_DESIGN[directory][1](data)
        require(recorded == hashlib.sha256(data).hexdigest(), f"{name}: provenance hash of {filename}")
    return provenance


def compare_evaluation_directory(kind, directory, committed, fresh, source=None, fresh_source=None):
    """Compare a committed evaluation vector with a fresh generation, allowing only the platform
    difference of metric floats and what follows from it. Raises Mismatch on the first difference and
    returns the filenames covered by a rule instead of byte equality.

    - evaluation.json: compared with the verifier's tolerance.
    - EVALUATION.md, valid vectors: equal to the fresh Markdown apart from its digest line, and the
      committed one exactly the rendering of the committed report and cases with the committed report's
      actual digest. Tampered and invalid vectors: the digest line is not normalized; in BOTH trees the
      Markdown equals that tree's own source vector's Markdown plus the vector's named edit, byte for byte.
    - provenance.json: equal apart from the two hashes derived from the files above; in BOTH trees those
      two hashes are the SHA-256 of that tree's files (checked independently), except for the deliberate
      stale hash.
    - every other file is byte-equal.
    """
    name = f"{kind}/{directory}"
    for filename in committed:
        if filename not in EVALUATION_RULE_FILES:
            require(committed[filename] == fresh[filename], f"{name}/{filename}")
    if "evaluation.json" in committed:
        require(_close(json.loads(fresh["evaluation.json"]), json.loads(committed["evaluation.json"]),
                       frozenset({"limit"})), f"{name}/evaluation.json")
    if "EVALUATION.md" in committed and kind == "valid":
        require(DIGEST_LINE.sub(rb"\1X\2", committed["EVALUATION.md"]) == DIGEST_LINE.sub(
            rb"\1X\2", fresh["EVALUATION.md"]), f"{name}/EVALUATION.md")
    elif "EVALUATION.md" in committed:
        require(source is not None and fresh_source is not None, f"{name}: needs the source vector of each tree")
        edit = MARKDOWN_EDITS.get(directory, lambda data: data)
        require(committed["EVALUATION.md"] == edit(source["EVALUATION.md"]),
                f"{name}/EVALUATION.md (committed) differs from the source vector plus its named edit")
        require(fresh["EVALUATION.md"] == edit(fresh_source["EVALUATION.md"]),
                f"{name}/EVALUATION.md (fresh) differs from the source vector plus its named edit")
    require(check_derived_hashes(name, directory, committed) == check_derived_hashes(name, directory, fresh),
            f"{name}/provenance.json")
    if kind == "valid":
        digest = hashlib.sha256(committed["evaluation.json"]).hexdigest()
        # evaluation.json and cases.jsonl are written with sorted keys; the Markdown lists questions in
        # the order of the question file, so restore that order from the retained questions.json.
        order = list(json.loads(committed["questions.json"]))
        report = json.loads(committed["evaluation.json"])
        report["questions"] = {key: report["questions"][key] for key in order if key in report["questions"]}
        cases = []
        for line in committed["cases.jsonl"].decode("utf-8").splitlines():
            row = json.loads(line)
            if "questions" in row:
                row["questions"] = {key: row["questions"][key] for key in order if key in row["questions"]}
            cases.append(row)
        rendered = render_markdown(report, digest, cases)
        require(committed["EVALUATION.md"] == rendered.encode("utf-8"), f"{name}/EVALUATION.md is not the rendering")
    return {filename for filename in committed if filename in EVALUATION_RULE_FILES}


def read_tree(target):
    """The files `write(target)` produces: the three vector directories and manifest.json."""
    found = {}
    for kind in KINDS:
        for path in sorted((target / kind).rglob("*")):
            if path.is_file():
                found[path.relative_to(target).as_posix()] = path.read_bytes()
    if (target / "manifest.json").is_file():
        found["manifest.json"] = (target / "manifest.json").read_bytes()
    return found


def tree_differences(committed, fresh):
    """Compare a committed tree with a fresh generation. Returns (differing paths or reasons, covered paths).

    Everything is byte-exact except the evaluation directories, which follow `compare_evaluation_directory`:
    the platform difference of metric floats is allowed, so a tree generated on macOS passes on Linux.
    """
    problems = [f"{path} (missing from the {'fresh' if path in committed else 'committed'} tree)"
                for path in sorted(committed.keys() ^ fresh.keys())]
    directories = {}
    for name in sorted(committed.keys() | fresh.keys()):
        parts = Path(name).parts
        if len(parts) == 3 and parts[1].startswith("evaluation-"):
            directories.setdefault(parts[:2], []).append(parts[2])
        elif name in committed and name in fresh and committed[name] != fresh[name]:
            problems.append(name)
    if len(directories) != EVALUATION_DIRECTORIES:
        problems.append(f"expected {EVALUATION_DIRECTORIES} evaluation vector directories, found {len(directories)}")
    # A directory with a file missing on either side is already reported above; its files cannot be paired.
    pairable = {key for key, files in directories.items()
                if all(f"{key[0]}/{key[1]}/{f}" in committed and f"{key[0]}/{key[1]}/{f}" in fresh for f in files)}
    sources = {("valid", name) for name in (SOURCE_VECTOR, *SOURCE_VECTORS.values())}
    covered = set()
    missing = sorted(sources - pairable)
    if missing:
        return problems + [f"{kind}/{name} (the source vector of evaluation edits)" for kind, name in missing], covered

    def files_of(tree, key):
        return {f: tree[f"{key[0]}/{key[1]}/{f}"] for f in directories[key]}

    for key in sorted(pairable):
        source_key = ("valid", SOURCE_VECTORS.get(key[1], SOURCE_VECTOR))
        try:
            for filename in compare_evaluation_directory(
                    key[0], key[1], files_of(committed, key), files_of(fresh, key),
                    files_of(committed, source_key), files_of(fresh, source_key)):
                covered.add(f"{key[0]}/{key[1]}/{filename}")
        except Mismatch as error:
            problems.append(str(error))
        except (ValueError, KeyError, TypeError, AttributeError) as error:  # a mangled committed file
            problems.append(f"{key[0]}/{key[1]} (unreadable: {type(error).__name__}: {error})")
    return problems, covered


def compare_trees(committed, fresh):
    """Raise Mismatch unless the committed tree equals the fresh one under `tree_differences`; return the
    paths covered by a rule instead of byte equality."""
    problems, covered = tree_differences(committed, fresh)
    require(not problems, "; ".join(problems))
    return covered


def write(target):
    for kind in KINDS:
        shutil.rmtree(target / kind, ignore_errors=True)
    files = generate()
    for relative, data in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare the tree with a fresh generation without writing; exit 1 and list the "
                             "differing paths on a difference")
    parser.add_argument("--out", type=Path, default=ROOT, metavar="DIR",
                        help="the tree to write or, with --check, to compare (default: this directory)")
    args = parser.parse_args(argv)
    if args.check:
        problems, _ = tree_differences(read_tree(args.out), generate())
        for problem in problems:
            print(f"differs: {problem}", file=sys.stderr)
        return 1 if problems else 0
    print(f"wrote {write(args.out)} files under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
