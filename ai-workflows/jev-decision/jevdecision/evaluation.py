"""Offline evaluation: measure a decision model on labeled cases before acting on its answers.

A case is a state plus the expected answer to some or all questions: `true`/`false` for a
`Noul`, a label for a `Choice`, a level (or level index) for a `Score`. Answers come either
from recorded provider responses (replay, which needs no API key and gives the same report
every time) or from a live backend, whose raw responses are written out so the run can be
replayed later.

Metrics per question:

| Type | Metrics |
|---|---|
| `Noul` | `accuracy` (at probability 0.5), `brier`, `log_loss`, `ece`, `base_rate`, `mean_probability` |
| `Choice` | `accuracy`, `brier` (summed over labels), `log_loss`, `ece` (probability of the chosen label against correctness), `confusion` |
| `Score` | `accuracy` (nearest level), `within_one`, `mae` (in level steps) |

Every question also reports `n`, its number of labeled and answered cases. `ece` is the
expected calibration error over ten equal-width probability bins. Log loss clips
probabilities to [1e-6, 1 - 1e-6].

A requirement spec turns the report into a gate:

    {"max_error_rate": 0.0,
     "questions": {"refund": {"n": {"min": 50}, "brier": {"max": 0.1}}}}

A case whose request or response fails counts as an error, not as a wrong answer, and
`max_error_rate` (default 0) bounds the share of such cases.

Command line (exit 0 when every requirement passes, 1 when one fails, 2 for invalid input):

    python -m jevdecision.evaluation --questions examples/support-ticket.json \
        --cases examples/support-ticket-cases.jsonl \
        --responses examples/support-ticket-responses.jsonl \
        --require examples/support-ticket-requirements.json --out eval-run
"""

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .backends import BACKENDS, _check_state, create_backend
from .errors import DatasetError, DecisionError
from .questions import Choice, Noul, Score

EPSILON = 1e-6
ECE_BINS = 10
METRICS = {
    "noul": ("n", "accuracy", "brier", "log_loss", "ece", "base_rate", "mean_probability"),
    "choice": ("n", "accuracy", "brier", "log_loss", "ece"),
    "score": ("n", "accuracy", "within_one", "mae"),
}


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
    """Parse JSON Lines of {"id", "response"} recorded from a provider; return {id: response}."""
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
        allowed = METRICS[by_name[name].type]
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
    return sum(values) / len(values) if values else None


def _log_loss(probability):
    return -math.log(min(max(probability, EPSILON), 1 - EPSILON))


def expected_calibration_error(pairs, bins=ECE_BINS):
    """Weighted mean |accuracy - confidence| over equal-width bins of (confidence, correct) pairs."""
    if not pairs:
        return None
    grouped = {}
    for confidence, correct in pairs:
        grouped.setdefault(min(int(confidence * bins), bins - 1), []).append((confidence, correct))
    return sum(len(group) * abs(_mean([float(c) for _, c in group]) - _mean([p for p, _ in group]))
               for group in grouped.values()) / len(pairs)


def _noul_metrics(pairs):
    """`pairs` is [(probability of yes, expected bool)]."""
    return {
        "n": len(pairs),
        "accuracy": _mean([float((p >= 0.5) == y) for p, y in pairs]),
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
        "accuracy": _mean([float(a.choice == y) for a, y in pairs]),
        "brier": _mean([sum((p - (label == y)) ** 2 for label, p in a.probabilities.items()) for a, y in pairs]),
        "log_loss": _mean([_log_loss(a.probabilities.get(y, 0.0)) for a, y in pairs]),
        "ece": expected_calibration_error([(a.probabilities[a.choice], a.choice == y) for a, y in pairs]),
        "confusion": {label: row for label, row in confusion.items() if row},
    }


def _score_metrics(question, pairs):
    """`pairs` is [(ScoreAnswer, expected level index)]."""
    return {
        "n": len(pairs),
        "accuracy": _mean([float(question.levels.index(a.level) == y) for a, y in pairs]),
        "within_one": _mean([float(abs(question.levels.index(a.level) - y) <= 1) for a, y in pairs]),
        "mae": _mean([abs(a.score - y) for a, y in pairs]),
    }


def score_answers(questions, cases, answers):
    """Metrics per question. `answers` maps case id to {question name: answer} for answered cases."""
    report = {}
    for question in questions:
        pairs = [(answers[case.id][question.name], case.labels[question.name])
                 for case in cases if case.id in answers and question.name in case.labels]
        if isinstance(question, Noul):
            metrics = _noul_metrics([(answer.probability, expected) for answer, expected in pairs])
        elif isinstance(question, Choice):
            metrics = _choice_metrics(question, pairs)
        else:
            metrics = _score_metrics(question, pairs)
        report[question.name] = {"type": question.type, **metrics}
    return report


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


def run_live(backend, questions, cases):
    """Ask the backend about every case; a failing case is recorded as an error, not raised."""
    answers, raw, errors = {}, {}, []
    for case in cases:
        try:
            decision = backend.decide(case.state, questions)
        except DecisionError as error:
            errors.append({"id": case.id, "error": str(error)})
            continue
        answers[case.id], raw[case.id] = decision.answers, decision.raw
    return answers, raw, errors


def evaluate(questions, cases, answers, errors, requirements=None):
    """Build the evaluation report and apply the requirement spec (if any)."""
    max_error_rate, checks = load_requirements(requirements or {}, questions)
    metrics = score_answers(questions, cases, answers)
    error_rate = len(errors) / len(cases)
    results = [{"check": "error_rate", "bound": "max", "limit": max_error_rate, "value": error_rate,
                "pass": error_rate <= max_error_rate}]
    for name, metric, bound, limit in checks:
        value = metrics[name][metric]
        ok = value is not None and (value >= limit if bound == "min" else value <= limit)
        results.append({"check": f"{name}.{metric}", "bound": bound, "limit": limit, "value": value, "pass": ok})
    return {
        "cases": len(cases),
        "answered": len(answers),
        "errors": errors,
        "error_rate": error_rate,
        "questions": metrics,
        "requirements": results,
        "pass": all(result["pass"] for result in results),
    }


# Records -------------------------------------------------------------------

def _fmt(value):
    return "" if value is None else f"{value:.4g}"


def render_markdown(report, digest):
    lines = [f"# Decision model evaluation: {'PASS' if report['pass'] else 'FAIL'}\n",
             f"- evaluation.json SHA-256: `{digest}`",
             f"- jevdecision {report['jevdecision_version']}; backend {report['backend']}; "
             f"model {report['model']}; source {report['source']}",
             f"- {report['cases']} cases, {report['answered']} answered, "
             f"{len(report['errors'])} errors (rate {_fmt(report['error_rate'])})\n",
             "| Question | Type | n | Metrics |", "|---|---|---:|---|"]
    for name, metrics in report["questions"].items():
        shown = ", ".join(f"{key} {_fmt(metrics[key])}" for key in METRICS[metrics["type"]][1:])
        lines.append(f"| {name} | {metrics['type']} | {metrics['n']} | {shown} |")
    lines += ["\n| Requirement | Bound | Value | Result |", "|---|---|---:|---|"]
    for result in report["requirements"]:
        lines.append(f"| {result['check']} | {result['bound']} {_fmt(result['limit'])} | "
                     f"{_fmt(result['value'])} | {'pass' if result['pass'] else 'FAIL'} |")
    if report["errors"]:
        lines.append("\nErrors:\n")
        lines += [f"- `{error['id']}`: {error['error']}" for error in report["errors"]]
    return "\n".join(lines) + "\n"


def write_records(report, raw, out):
    """Write evaluation.json (sorted keys), EVALUATION.md, and the raw responses as JSON Lines."""
    out.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    (out / "evaluation.json").write_bytes(blob)
    (out / "EVALUATION.md").write_text(render_markdown(report, digest), encoding="utf-8")
    lines = [json.dumps({"id": case_id, "response": response}, sort_keys=True, ensure_ascii=False)
             for case_id, response in raw.items()]
    (out / "responses.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return digest


def main(argv=None):
    from .questions import check_question_set, questions_from_spec

    parser = argparse.ArgumentParser(prog="python -m jevdecision.evaluation",
                                     description="Evaluate a decision model on labeled cases.")
    parser.add_argument("--questions", required=True, type=Path, help="JSON question map (Jev format)")
    parser.add_argument("--cases", required=True, type=Path, help='JSON Lines of {"id", "state", "labels"}')
    parser.add_argument("--responses", type=Path,
                        help='recorded JSON Lines of {"id", "response"}; replays them instead of calling the provider')
    parser.add_argument("--require", type=Path, help="JSON requirement spec")
    parser.add_argument("--out", required=True, type=Path, help="new or empty output directory")
    parser.add_argument("--backend", choices=sorted(BACKENDS), default="jev",
                        help="provider whose response format is replayed or called (default: jev)")
    parser.add_argument("--model", help="model id for a live run (default: the backend's)")
    parser.add_argument("--base-url", help="provider or gateway base URL for a live run")
    parser.add_argument("--path", help="endpoint path for a live run")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        parser.error("--out must be a new path or an existing empty directory")
    try:
        questions = check_question_set(questions_from_spec(json.loads(args.questions.read_text(encoding="utf-8"))))
        cases = load_cases(args.cases.read_text(encoding="utf-8"), questions)
        requirements = json.loads(args.require.read_text(encoding="utf-8")) if args.require else {}
        load_requirements(requirements, questions)
        backend = create_backend(args.backend, model=args.model, base_url=args.base_url,
                                 path=args.path, timeout=args.timeout)
        if args.responses:
            responses = load_responses(args.responses.read_text(encoding="utf-8"))
            answers, raw, errors = replay(backend, questions, cases, responses)
        else:
            backend.headers()  # fail before the first case when there is no API key
            answers, raw, errors = run_live(backend, questions, cases)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except DecisionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    models = sorted({str(r.get("model")) for r in raw.values() if isinstance(r, dict) and r.get("model")})
    report = {"jevdecision_version": __version__, "backend": backend.name,
              "model": ", ".join(models) or backend.model,
              "source": "replay" if args.responses else "live",
              **evaluate(questions, cases, answers, errors, requirements)}
    digest = write_records(report, raw, args.out)
    print(f"{'PASS' if report['pass'] else 'FAIL'} {digest}")
    for result in report["requirements"]:
        if not result["pass"]:
            print(f"  {result['check']}: {_fmt(result['value'])} fails {result['bound']} {_fmt(result['limit'])}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
