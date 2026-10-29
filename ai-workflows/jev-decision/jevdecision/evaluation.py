"""Offline evaluation: measure a decision model on labeled cases before acting on its answers.

A case is a state plus the expected answer to some or all questions: `true`/`false` for a
`Noul`, a label for a `Choice`, a level (or level index) for a `Score`. Answers come either
from supplied responses (replay, which needs no API key and gives the same report every
time) or from a live backend, whose raw responses are written out so the run can be
replayed later. Replay response origin is unverified.

Metrics per question:

| Type | Metrics |
|---|---|
| `Noul` | `accuracy` (at probability 0.5), `brier`, `log_loss`, `ece`, `base_rate`, `mean_probability` |
| `Choice` | `accuracy`, `brier` (summed over labels), `log_loss`, `ece` (probability of the chosen label against correctness), `confusion` |
| `Score` | `accuracy` (nearest level), `within_one`, `mae` (in level steps) |

Every question also reports `n`, its number of labeled and answered cases, and
`accuracy_lower` / `accuracy_upper`, the 95% Wilson score interval for `accuracy`. `ece` is the
expected calibration error over ten equal-width probability bins. Log loss clips
probabilities to [1e-6, 1 - 1e-6].

A requirement spec turns the report into a gate:

    {"max_error_rate": 0.0,
     "questions": {"refund": {"n": {"min": 50}, "brier": {"max": 0.1}}}}

A case whose request or response fails counts as an error, not as a wrong answer, and
`max_error_rate` (default 0) bounds the share of such cases.

Each run also writes `cases.jsonl`, one row per case with every labeled question's expected
and predicted answer (or the case's error), and EVALUATION.md lists the incorrect answers.

Calibration (see `jevdecision.calibration`): `--fit-calibration isotonic|platt` fits one map per
question on this run's labeled cases and writes `calibration.json`; `--calibration FILE` applies such
a file to a run on other cases and adds `calibrated_*` metrics, which requirements can bound. Both
write `evaluation.json` and `provenance.json` schema 3 (with a `calibration` member and input);
runs without calibration write schema 2.

Command line: exit 0 for PASS, 1 for FAIL/provider errors, 2 for invalid input,
and 3 for UNGATED (no explicit question metric bounds). CLI runs also write provenance.json
with exact input and output file SHA-256 hashes, separately from evaluation metrics, and a
retained copies of the question and requirement files (`questions.json`, `requirements.json`)
so `jev-decision-verify --evaluation` can re-score the run from the directory alone. With
`--sign-key KEYFILE` it also writes `provenance.json.dsse.json`, an HMAC-SHA256 DSSE envelope over the
exact bytes of provenance.json (which pins every other file by hash).

    python -m jevdecision.evaluation --questions examples/support-ticket.json \
        --cases examples/support-ticket-cases.jsonl \
        --responses examples/support-ticket-responses.jsonl \
        --require examples/support-ticket-requirements.json --out eval-run
"""

import argparse
import hashlib
import json
import math
import os
import tempfile
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

from . import __version__, attestation, calibration as calibrators, signing
from .backends import BACKENDS, _check_state, create_backend
from .errors import APIError, DatasetError, DecisionError, ResponseError
from .answers import RefusalAnswer
from .questions import Choice, Noul, Score

EPSILON = 1e-6
ECE_BINS = 10
CONFIDENCE = 0.95
_ACCURACY = ("accuracy", "accuracy_lower", "accuracy_upper")
METRICS = {
    "noul": ("n", *_ACCURACY, "brier", "log_loss", "ece", "base_rate", "mean_probability"),
    "choice": ("n", *_ACCURACY, "brier", "log_loss", "ece"),
    "score": ("n", *_ACCURACY, "within_one", "mae", "brier", "log_loss", "ece"),
}

for _metrics_type in METRICS:
    METRICS[_metrics_type] += ("refusals", "refusal_rate")


@dataclass(frozen=True)
class Case:
    """A state and its expected answers, keyed by question name."""

    id: str
    state: object
    labels: "dict[str, object]"


# Loading -------------------------------------------------------------------

def _expected(question, value, where):
    """Normalize a label: bool for Noul, label for Choice, level index for Score."""
    if isinstance(question, Noul):
        if not isinstance(value, bool):
            raise DatasetError(f"{where}: a noul label must be true or false, got {value!r}")
        return value
    if isinstance(question, Choice):
        if value not in question.options:
            raise DatasetError(f"{where}: {value!r} is not one of {list(question.labels)}")
        return value
    if isinstance(value, str) and value in question.levels:
        return question.levels.index(value)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(question.levels):
        return value
    raise DatasetError(f"{where}: {value!r} is not a level of {list(question.levels)} or its index")


def _jsonl(text, what):
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetError(f"{what} line {number}: not JSON: {error}") from None
        if not isinstance(row, dict):
            raise DatasetError(f"{what} line {number}: expected an object")
        rows.append((number, row))
    return rows


def load_cases(text, questions):
    """Parse JSON Lines of {"id", "state", "labels"} and check every label against `questions`."""
    by_name = {question.name: question for question in questions}
    cases, seen = [], set()
    for number, row in _jsonl(text, "cases"):
        where = f"cases line {number}"
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise DatasetError(f"{where}: id must be a non-empty string")
        if case_id in seen:
            raise DatasetError(f"{where}: duplicate id {case_id!r}")
        seen.add(case_id)
        try:
            state = _check_state(row.get("state"))
        except DecisionError as error:
            raise DatasetError(f"{where}: {error}") from None
        labels = row.get("labels")
        if not isinstance(labels, dict) or not labels:
            raise DatasetError(f"{where}: labels must be a non-empty object")
        unknown = set(labels) - set(by_name)
        if unknown:
            raise DatasetError(f"{where}: labels name unknown questions {sorted(unknown)}")
        expected = {name: _expected(by_name[name], value, f"{where} label {name!r}")
                    for name, value in labels.items()}
        cases.append(Case(case_id, state, expected))
    if not cases:
        raise DatasetError("cases: the file has no cases")
    return cases


def load_responses(text):
    """Parse supplied JSON Lines of {"id", "response"}; origin is not verified."""
    responses = {}
    for number, row in _jsonl(text, "responses"):
        case_id = row.get("id")
        if not isinstance(case_id, str) or "response" not in row:
            raise DatasetError(f"responses line {number}: needs a string id and a response")
        if case_id in responses:
            raise DatasetError(f"responses line {number}: duplicate id {case_id!r}")
        responses[case_id] = row["response"]
    return responses


def load_requirements(spec, questions):
    """Validate a requirement spec; return (max_error_rate, [(question, metric, bound, limit)])."""
    if not isinstance(spec, dict):
        raise DatasetError("requirements: expected an object")
    unknown = set(spec) - {"max_error_rate", "questions"}
    if unknown:
        raise DatasetError(f"requirements: unknown keys {sorted(unknown)}")
    max_error_rate = spec.get("max_error_rate", 0.0)
    if not _finite(max_error_rate) or not 0 <= max_error_rate <= 1:
        raise DatasetError("requirements: max_error_rate must be a number in [0, 1]")
    by_name = {question.name: question for question in questions}
    checks = []
    per_question = spec.get("questions", {})
    if not isinstance(per_question, dict):
        raise DatasetError("requirements: questions must be an object")
    for name, metrics in per_question.items():
        if name not in by_name:
            raise DatasetError(f"requirements: unknown question {name!r}")
        allowed = METRICS[by_name[name].type] + calibrators.CALIBRATED_METRICS[by_name[name].type]
        if not isinstance(metrics, dict) or not metrics:
            raise DatasetError(f"requirements {name!r}: expected an object of metric bounds")
        for metric, bounds in metrics.items():
            if metric not in allowed:
                raise DatasetError(f"requirements {name!r}: {metric!r} is not one of {list(allowed)}")
            if not isinstance(bounds, dict) or not bounds or set(bounds) - {"min", "max"}:
                raise DatasetError(f"requirements {name!r} {metric!r}: give a min and/or a max")
            for bound, limit in sorted(bounds.items()):
                if not _finite(limit):
                    raise DatasetError(f"requirements {name!r} {metric!r}: {bound} must be a finite number")
                checks.append((name, metric, bound, limit))
    return max_error_rate, checks


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# Metrics -------------------------------------------------------------------

def _mean(values):
    return math.fsum(values) / len(values) if values else None


def _log_loss(probability):
    return -math.log(min(max(probability, EPSILON), 1 - EPSILON))


def wilson_interval(successes, n, confidence=CONFIDENCE):
    """Two-sided Wilson score interval for a proportion; (None, None) when there are no cases.

    Unlike the normal (Wald) interval it stays inside [0, 1] and does not collapse to a point
    at 0% or 100% accuracy, which matters for the small labeled sets an evaluation starts with.
    """
    if n == 0:
        return None, None
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p, z2 = successes / n, z * z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z / (1 + z2 / n) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(center - half, 0.0), min(center + half, 1.0)


def _accuracy(correct):
    """`accuracy` with its Wilson interval, from one bool per case."""
    lower, upper = wilson_interval(sum(correct), len(correct))
    return {"accuracy": _mean([float(c) for c in correct]), "accuracy_lower": lower, "accuracy_upper": upper}


def expected_calibration_error(pairs, bins=ECE_BINS):
    """Weighted mean |accuracy - confidence| over equal-width bins of (confidence, correct) pairs."""
    if not pairs:
        return None
    grouped = {}
    for confidence, correct in pairs:
        grouped.setdefault(min(int(confidence * bins), bins - 1), []).append((confidence, correct))
    return math.fsum(len(group) * abs(_mean([float(c) for _, c in group]) - _mean([p for p, _ in group]))
               for group in grouped.values()) / len(pairs)


def _noul_metrics(pairs):
    """`pairs` is [(probability of yes, expected bool)]."""
    return {
        "n": len(pairs),
        **_accuracy([(p >= 0.5) == y for p, y in pairs]),
        "brier": _mean([(p - y) ** 2 for p, y in pairs]),
        "log_loss": _mean([_log_loss(p if y else 1 - p) for p, y in pairs]),
        "ece": expected_calibration_error([(p, y) for p, y in pairs]),
        "base_rate": _mean([float(y) for _, y in pairs]),
        "mean_probability": _mean([p for p, _ in pairs]),
    }


def _choice_metrics(question, pairs):
    """`pairs` is [(ChoiceAnswer, expected label)]."""
    confusion = {label: {} for label in question.labels}
    for answer, expected in pairs:
        row = confusion[expected]
        row[answer.choice] = row.get(answer.choice, 0) + 1
    return {
        "n": len(pairs),
        **_accuracy([a.choice == y for a, y in pairs]),
        "brier": _mean([math.fsum((a.probabilities[label] - (label == y)) ** 2 for label in question.labels)
                        for a, y in pairs])
                 if all(all(label in a.probabilities for label in question.labels) for a, _ in pairs) else None,
        "log_loss": _mean([_log_loss(a.probabilities[y]) for a, y in pairs])
                    if all(y in a.probabilities for a, y in pairs) else None,
        "ece": expected_calibration_error([(a.probability, a.choice == y) for a, y in pairs])
               if all(a.probability is not None for a, _ in pairs) else None,
        "confusion": {label: row for label, row in confusion.items() if row},
    }


def _score_metrics(question, pairs):
    """`pairs` is [(ScoreAnswer, expected level index)]."""
    return {
        "n": len(pairs),
        **_accuracy([question.levels.index(a.level) == y for a, y in pairs]),
        "within_one": _mean([float(abs(question.levels.index(a.level) - y) <= 1) for a, y in pairs]),
        "mae": _mean([abs(a.score - y) for a, y in pairs]),
        "brier": _mean([math.fsum((p - (i == y)) ** 2 for i, p in enumerate(a.probabilities))
                        for a, y in pairs]) if all(all(p is not None for p in a.probabilities) for a, _ in pairs) else None,
        "log_loss": _mean([_log_loss(a.probabilities[y]) for a, y in pairs])
                    if all(a.probabilities[y] is not None for a, y in pairs) else None,
        "ece": expected_calibration_error([(a.probability, question.levels.index(a.level) == y) for a, y in pairs])
               if all(a.probability is not None for a, _ in pairs) else None,
    }


def _calibrated_metrics(question, cases, answers, calibration):
    """Held-out metrics of the calibrated probabilities; None where the question has no calibrator,
    a refusal, or an answer without the probability its raw `ece` needs."""
    metrics = dict.fromkeys(calibrators.CALIBRATED_METRICS[question.type])
    refused = any(isinstance(answers[case.id][question.name], RefusalAnswer)
                  for case in cases if case.id in answers and question.name in case.labels)
    pairs = None if refused or question.name not in calibration else \
        calibrators.labeled_pairs(question, cases, answers)
    if pairs:
        pairs = [(calibration.calibrate(question.name, p), y) for p, y in pairs]
        metrics["calibrated_ece"] = expected_calibration_error(pairs)
        if isinstance(question, Noul):
            metrics["calibrated_brier"] = _mean([(p - y) ** 2 for p, y in pairs])
            metrics["calibrated_log_loss"] = _mean([_log_loss(p if y else 1 - p) for p, y in pairs])
    return metrics


def score_answers(questions, cases, answers, calibration=None):
    """Metrics per question. `answers` maps case id to {question name: answer} for answered cases;
    with a `calibration.Calibration`, every question also gets its `calibrated_*` metrics."""
    report = {}
    for question in questions:
        pairs = [(answers[case.id][question.name], case.labels[question.name])
                 for case in cases if case.id in answers and question.name in case.labels]
        refusals = sum(isinstance(a, RefusalAnswer) for a, _ in pairs)
        valid = [(a, y) for a, y in pairs if not isinstance(a, RefusalAnswer)]
        if isinstance(question, Noul):
            metrics = _noul_metrics([(answer.probability, expected) for answer, expected in valid])
        elif isinstance(question, Choice):
            metrics = _choice_metrics(question, valid)
        else:
            metrics = _score_metrics(question, valid)
        if refusals:
            correct = [row["correct"] for row in (_case_result(question, a, y) for a, y in pairs)]
            metrics.update(_accuracy(correct))
            for key in ("brier", "log_loss", "ece", "mean_probability", "mae", "within_one"):
                if key in metrics:
                    metrics[key] = None
            if isinstance(question, Noul):
                metrics["base_rate"] = _mean([float(y) for _, y in pairs])
        metrics.update(n=len(pairs), refusals=refusals, refusal_rate=refusals / len(pairs) if pairs else None)
        if calibration is not None:
            metrics.update(_calibrated_metrics(question, cases, answers, calibration))
        report[question.name] = {"type": question.type, **metrics}
    return report


def _case_result(question, answer, expected):
    """Expected and predicted answer for one labeled question in one case."""
    if isinstance(answer, RefusalAnswer):
        return {"expected": question.levels[expected] if isinstance(question, Score) else expected,
                "predicted": None, "probability": None, "refused": True, "correct": False}
    if isinstance(question, Noul):
        return {"expected": expected, "predicted": answer.is_yes(), "probability": answer.probability,
                "correct": answer.is_yes() == expected}
    if isinstance(question, Choice):
        return {"expected": expected, "predicted": answer.choice, "probability": answer.probability,
                "correct": answer.choice == expected}
    level = question.levels[expected]
    return {"expected": level, "predicted": answer.level, "score": answer.score, "correct": answer.level == level}


def case_results(questions, cases, answers, errors):
    """One row per case: each labeled question's expected and predicted answer, or the case's error."""
    failed = {error["id"]: error["error"] for error in errors}
    rows = []
    for case in cases:
        row = {"id": case.id}
        if case.id in answers:
            row["questions"] = {question.name: _case_result(question, answers[case.id][question.name],
                                                            case.labels[question.name])
                                for question in questions if question.name in case.labels}
        else:
            row["error"] = failed.get(case.id, "no answer")
        rows.append(row)
    return rows


# Running -------------------------------------------------------------------

def replay(backend, questions, cases, responses):
    """Parse recorded responses for every case; return ({id: answers}, {id: raw}, [errors]).

    A case without a recorded response is an error, as it was in the live run that recorded them.
    """
    unknown = sorted(set(responses) - {case.id for case in cases})
    if unknown:
        raise DatasetError(f"responses: recorded for unknown cases {unknown}")
    answers, raw, errors = {}, {}, []
    for case in cases:
        if case.id not in responses:
            errors.append({"id": case.id, "error": "no recorded response"})
            continue
        raw[case.id] = responses[case.id]
        try:
            answers[case.id] = backend.parse_response(responses[case.id], questions).answers
        except DecisionError as error:
            errors.append({"id": case.id, "error": str(error)})
    return answers, raw, errors


def run_live(backend, questions, cases, progress=None):
    """Ask the backend about every case; a failing case is recorded as an error, not raised."""
    answers, raw, errors = {}, {}, []
    for case in cases:
        try:
            decision = backend.decide(case.state, questions)
        except DecisionError as error:
            errors.append({"id": case.id, "error": str(error)})
            if isinstance(error, ResponseError) and error.response_received:
                raw[case.id] = error.response
            if progress:
                if isinstance(error, ResponseError) and error.response_received:
                    progress(case, None, errors[-1], error.response)
                else:
                    progress(case, None, errors[-1])
            if isinstance(error, APIError) and error.status in (401, 403):
                raise
            continue
        answers[case.id], raw[case.id] = decision.answers, decision.raw
        if progress:
            progress(case, decision, None)
    return answers, raw, errors


def evaluate(questions, cases, answers, errors, requirements=None, calibration=None):
    """Apply validated bounds: FAIL on a failed check, otherwise PASS only with question bounds.

    A bound on a `calibrated_*` metric fails unless `calibration` measured it."""
    max_error_rate, checks = load_requirements({} if requirements is None else requirements, questions)
    metrics = score_answers(questions, cases, answers, calibration)
    error_rate = len(errors) / len(cases)
    results = [{"check": "error_rate", "bound": "max", "limit": max_error_rate, "value": error_rate,
                "pass": error_rate <= max_error_rate}]
    for name, metric, bound, limit in checks:
        value = metrics[name].get(metric)
        ok = value is not None and (value >= limit if bound == "min" else value <= limit)
        results.append({"check": f"{name}.{metric}", "bound": bound, "limit": limit, "value": value, "pass": ok})
    return {
        "cases": len(cases),
        "answered": len(answers),
        "errors": errors,
        "error_rate": error_rate,
        "questions": metrics,
        "requirements": results,
        "status": "FAIL" if not all(result["pass"] for result in results) else "PASS" if checks else "UNGATED",
    }


# Records -------------------------------------------------------------------

def _fmt(value):
    return "unmeasured" if value is None else f"{value:.4g}"


MAX_LISTED_MISSES = 20


def render_markdown(report, digest, cases=None):
    lines = [f"# Decision model evaluation: {report['status']}\n",
             f"- evaluation.json SHA-256: `{digest}`",
             f"- jevdecision {report['jevdecision_version']}; backend {report['backend']}; "
             f"model {report['model']}; source {report['source']}",
             f"- {report['cases']} cases, {report['answered']} answered, "
             f"{len(report['errors'])} errors (rate {_fmt(report['error_rate'])})\n",
             "| Question | Type | n | Metrics |", "|---|---|---:|---|"]
    if report["status"] == "UNGATED":
        lines.insert(4, "- No explicit question metric bounds: metrics are descriptive, not a quality gate.\n")
    if report["source"] == "replay":
        lines.insert(4, "- Replay origin is unverified; response model fields are supplied metadata, "
                     "not proof of provider output.\n")
    calibration = report.get("calibration")
    if calibration and calibration["role"] == "fitted":
        lines.insert(4, f"- Calibration fitted ({calibration['method']}) on these cases: calibration.json SHA-256 "
                     f"`{calibration['sha256']}`. Only a run on other cases with `--calibration` measures it.\n")
    elif calibration:
        lines.insert(4, f"- Calibration applied ({calibration['method']}): calibration.json SHA-256 "
                     f"`{calibration['sha256']}`, fitted on other cases; `calibrated_*` metrics are held out.\n")
    for name, metrics in report["questions"].items():
        keys = METRICS[metrics["type"]][1:] + tuple(
            key for key in calibrators.CALIBRATED_METRICS[metrics["type"]] if key in metrics)
        shown = ", ".join(f"{key} {_fmt(metrics[key])}" for key in keys)
        lines.append(f"| {name} | {metrics['type']} | {metrics['n']} | {shown} |")
    lines += ["\n| Requirement | Bound | Value | Result |", "|---|---|---:|---|"]
    for result in report["requirements"]:
        lines.append(f"| {result['check']} | {result['bound']} {_fmt(result['limit'])} | "
                     f"{_fmt(result['value'])} | {'pass' if result['pass'] else 'FAIL'} |")
    if report["errors"]:
        lines.append("\nErrors:\n")
        lines += [f"- `{error['id']}`: {error['error']}" for error in report["errors"]]
    misses = [(row["id"], name, result) for row in cases or () for name, result in row.get("questions", {}).items()
              if not result["correct"]]
    if misses:
        lines.append(f"\nIncorrect answers ({len(misses)}; every case is in `cases.jsonl`):\n")
        shown = lambda value: json.dumps(value, ensure_ascii=False)  # noqa: E731
        lines += [f"- `{case_id}` {name}: expected {shown(result['expected'])}, got {shown(result['predicted'])}"
                  for case_id, name, result in misses[:MAX_LISTED_MISSES]]
        if len(misses) > MAX_LISTED_MISSES:
            lines.append(f"- ... and {len(misses) - MAX_LISTED_MISSES} more")
    return "\n".join(lines) + "\n"


def _write_jsonl(path, rows):
    lines = [json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for row in rows]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def _write_report(report, out, cases=None):
    """Write evaluation.json (sorted keys) and EVALUATION.md; return evaluation.json's SHA-256."""
    blob = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    (out / "evaluation.json").write_bytes(blob)
    (out / "EVALUATION.md").write_text(render_markdown(report, digest, cases), encoding="utf-8")
    return digest


def _write_streams(raw, out, cases=None, preserve_streams=False):
    """Write the raw responses as JSON Lines and, when `cases` (from `case_results`) is given, the
    per-case results as cases.jsonl; with `preserve_streams`, keep files a live run already wrote."""
    if not preserve_streams or not (out / "responses.jsonl").exists():
        _write_jsonl(out / "responses.jsonl", ({"id": case_id, "response": response} for case_id, response in raw.items()))
    if cases is not None and (not preserve_streams or not (out / "cases.jsonl").exists()):
        _write_jsonl(out / "cases.jsonl", cases)


def _write_records(report, raw, out, cases=None, preserve_streams=False):
    out.mkdir(parents=True, exist_ok=True)
    digest = _write_report(report, out, cases)
    _write_streams(raw, out, cases, preserve_streams)
    return digest


def write_records(report, raw, out, cases=None):
    """Publish complete records from a staging directory beside the target."""
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise DatasetError("output must be new or empty")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    digest = _write_records(report, raw, staging, cases)
    os.replace(staging, out)
    return digest


def _append_jsonl(path, row):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    from .__main__ import positive_seconds
    from .questions import check_question_set, questions_from_spec

    parser = argparse.ArgumentParser(prog="python -m jevdecision.evaluation",
                                     description="Evaluate a decision model on labeled cases.")
    parser.add_argument("--questions", required=True, type=Path, help="JSON question map (Jev format)")
    parser.add_argument("--cases", required=True, type=Path, help='JSON Lines of {"id", "state", "labels"}')
    parser.add_argument("--responses", type=Path,
                        help='supplied JSON Lines of {"id", "response"}; unverified origin, no provider call')
    parser.add_argument("--require", type=Path, help="JSON requirement spec")
    parser.add_argument("--out", required=True, type=Path, help="new or empty output directory")
    parser.add_argument("--sign-key", type=Path,
                        help="HMAC key file; also writes OUT/provenance.json.dsse.json, a DSSE envelope over the "
                             "exact bytes of provenance.json")
    parser.add_argument("--backend", choices=sorted(BACKENDS), default="jev",
                        help="provider whose response format is replayed or called (default: jev)")
    parser.add_argument("--model", help="model id for a live run (default: the backend's)")
    parser.add_argument("--base-url", help="provider or gateway base URL for a live run")
    parser.add_argument("--path", help="endpoint path for a live run")
    parser.add_argument("--timeout", type=positive_seconds, default=30.0, help="seconds for a live run (default: 30)")
    calibration_flags = parser.add_mutually_exclusive_group()
    calibration_flags.add_argument("--fit-calibration", choices=calibrators.METHODS, metavar="METHOD",
                                   help="fit a calibrator per question on these cases (isotonic or platt) and "
                                        "write OUT/calibration.json")
    calibration_flags.add_argument("--calibration", type=Path, metavar="FILE",
                                   help="calibration.json fitted on other cases; adds calibrated_* metrics")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        parser.error("--out must be a new path or an existing empty directory")
    calibrating = args.fit_calibration is not None or args.calibration is not None
    schema_version = 3 if calibrating else 2
    staging = None
    try:
        key = signing.load_key(args.sign_key) if args.sign_key is not None else None  # before any work
        inputs = {name: path.read_bytes() if path else None for name, path in (
            ("questions", args.questions), ("cases", args.cases),
            ("requirements", args.require), ("responses", args.responses),
            *((("calibration", args.calibration),) if calibrating else ()))}
        questions = check_question_set(questions_from_spec(json.loads(inputs["questions"].decode("utf-8"))))
        cases = load_cases(inputs["cases"].decode("utf-8"), questions)
        requirements = json.loads(inputs["requirements"].decode("utf-8")) if args.require else {}
        load_requirements(requirements, questions)
        calibration = calibrators.load(inputs["calibration"]) if args.calibration else None
        if calibration is not None:
            calibration.check_applicable(questions, cases)
        backend = create_backend(args.backend, model=args.model, base_url=args.base_url,
                                 path=args.path, timeout=args.timeout)
        if args.responses:
            responses = load_responses(inputs["responses"].decode("utf-8"))
            answers, raw, errors = replay(backend, questions, cases, responses)
        else:
            backend.headers()  # fail before the first case when there is no API key
            args.out.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=f".{args.out.name}-", dir=args.out.parent))
            print(f"Live progress: {staging}", file=sys.stderr)
            no_response = object()
            def progress(case, decision, error, response=no_response):
                if decision is not None:
                    _append_jsonl(staging / "responses.jsonl", {"id": case.id, "response": decision.raw})
                elif response is not no_response:
                    _append_jsonl(staging / "responses.jsonl", {"id": case.id, "response": response})
                rows = case_results(questions, [case], {case.id: decision.answers} if decision else {},
                                    [error] if error else [])
                _append_jsonl(staging / "cases.jsonl", rows[0])
            answers, raw, errors = run_live(backend, questions, cases, progress)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except DecisionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if isinstance(error, APIError) and error.status in (401, 403) else 1

    models = sorted({str(r.get("model")) for r in raw.values() if isinstance(r, dict) and r.get("model")})
    producer = {"name": "jevdecision", "version": __version__}
    report = {"schema_version": schema_version, "produced_by": producer,
              "jevdecision_version": __version__, "backend": backend.name,
              "model": ", ".join(models) or backend.model,
              "source": "replay" if args.responses else "live",
              **evaluate(questions, cases, answers, errors, requirements, calibration)}
    try:
        if staging is None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=f".{args.out.name}-", dir=args.out.parent))
        rows = case_results(questions, cases, answers, errors)
        _write_streams(raw, staging, rows, preserve_streams=not args.responses)
        retained = {"questions": "questions.json", "requirements": "requirements.json",
                    "calibration": calibrators.FILENAME}
        for role, filename in retained.items():
            if inputs.get(role) is not None:
                (staging / filename).write_bytes(inputs[role])
        if args.fit_calibration:
            basis = calibrators.fitted_on((staging / "cases.jsonl").read_bytes(),
                                          (staging / "responses.jsonl").read_bytes(), cases)
            (staging / calibrators.FILENAME).write_bytes(calibrators.dumps(
                calibrators.fit(args.fit_calibration, questions, cases, answers, basis, producer)))
        if calibrating:
            report["calibration"] = {
                "role": "fitted" if args.fit_calibration else "applied",
                "method": args.fit_calibration or calibration.method,
                "sha256": hashlib.sha256((staging / calibrators.FILENAME).read_bytes()).hexdigest()}
        digest = _write_report(report, staging, rows)
        provenance = {
            "schema_version": schema_version,
            "produced_by": {"name": "jevdecision", "version": __version__},
            "response_mode": report["source"],
            "response_origin": ("unverified: supplied replay responses may be hand-written; model fields "
                                "do not authenticate provider output" if args.responses else
                                "live: responses obtained by this CLI through the configured backend"),
            "inputs": {name: {"sha256": hashlib.sha256(blob).hexdigest()} if blob is not None else None
                       for name, blob in inputs.items()},
            "outputs": {name: {"sha256": hashlib.sha256((staging / name).read_bytes()).hexdigest()}
                        for name in ("evaluation.json", "EVALUATION.md", "responses.jsonl", "cases.jsonl",
                                     *(filename for role, filename in retained.items()
                                       if inputs.get(role) is not None),
                                     *((calibrators.FILENAME,) if args.fit_calibration else ()))},
        }
        (staging / "provenance.json").write_text(
            json.dumps(provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        if key is not None:
            envelope = attestation.sign_bytes((staging / "provenance.json").read_bytes(), "provenance.json",
                                              "provenance", schema_version, key)
            (staging / ("provenance.json" + attestation.ENVELOPE_SUFFIX)).write_text(
                attestation.render_envelope(envelope), encoding="utf-8")
        os.replace(staging, args.out)
    except (OSError, ValueError) as error:  # ValueError: DatasetError from fitting a calibration
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"{report['status']} {digest}")
    if report["status"] == "UNGATED":
        print("  No explicit question metric bounds; descriptive metrics only.")
    if args.responses:
        print("  Replay origin is unverified; supplied responses are not authenticated provider output.")
    for result in report["requirements"]:
        if not result["pass"]:
            print(f"  {result['check']}: {_fmt(result['value'])} fails {result['bound']} {_fmt(result['limit'])}")
    return {"PASS": 0, "FAIL": 1, "UNGATED": 3}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
