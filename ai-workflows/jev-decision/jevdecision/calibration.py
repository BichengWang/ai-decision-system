"""Calibrators fitted on a labeled evaluation, and the file that records them (calibration.json).

A decision model's probabilities can be miscalibrated even when its answers are right: a model
that says 0.95 and is right 70% of the time makes a threshold on its confidence meaningless.
`jev-decision-eval --fit-calibration METHOD` fits one monotone map per question on the run's
answered, labeled cases and writes it to calibration.json; `jev-decision-eval --calibration FILE`
applies it to an evaluation of *other* cases and reports the calibrated metrics next to the raw
ones. Calibrated metrics are only ever measured on held-out cases: a calibration fitted on any case
id of the evaluation it is applied to is refused.

What is calibrated is the probability each question's `ece` already measures:

| Type | Calibrated probability (`target`) | Calibrated metrics |
|---|---|---|
| `Noul` | probability of yes (`yes`) against the label | `calibrated_brier`, `calibrated_log_loss`, `calibrated_ece` |
| `Choice`, `Score` | probability of the chosen answer against its correctness (`chosen`) | `calibrated_ece` |

Methods (standard library, deterministic):

- `isotonic`: the nondecreasing step fit of pool-adjacent-violators over the observed
  probabilities, interpolated linearly between blocks and constant beyond them. It can return 0 or
  1 and needs a few hundred cases before its steps mean much.
- `platt`: `sigmoid(a * logit(p) + b)` fitted by Newton's method on Platt's smoothed targets
  (`(positives + 1) / (positives + 2)` and `1 / (negatives + 2)`), with `p` clipped to
  [1e-6, 1 - 1e-6]. Two parameters, so it suits the small sets an evaluation starts with.

calibration.json (schema 1) is written like evaluation.json (sorted keys, compact, UTF-8) and
carries no digest of its own; the evaluation directory's provenance.json pins its bytes:

    {"schema_version": 1, "produced_by": {"name": "jevdecision", "version": "..."},
     "method": "platt",
     "fitted_on": {"cases_sha256": "<cases.jsonl>", "responses_sha256": "<responses.jsonl>",
                   "case_ids": ["t01", ...]},
     "questions": {"refund": {"type": "noul", "target": "yes", "n": 12, "positives": 4,
                              "map": {"a": 1.3, "b": -0.2}}}}

To apply a fitted calibration outside an evaluation, before a probability threshold:

    from jevdecision.calibration import load
    calibration = load(Path("fit-run/calibration.json").read_bytes())
    p = calibration.calibrate("refund", decision["refund"].probability)
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
from dataclasses import dataclass

from .answers import RefusalAnswer
from .errors import DatasetError
from .questions import Noul, Score
from .records import loads_strict

SCHEMA_VERSION = 1
METHODS = ("isotonic", "platt")
TARGETS = {"noul": "yes", "choice": "chosen", "score": "chosen"}
CALIBRATED_METRICS = {
    "noul": ("calibrated_brier", "calibrated_log_loss", "calibrated_ece"),
    "choice": ("calibrated_ece",),
    "score": ("calibrated_ece",),
}
FILENAME = "calibration.json"
LOGIT_CLIP = 1e-6
_FIELDS = {"schema_version", "produced_by", "method", "fitted_on", "questions"}
_QUESTION_FIELDS = {"type", "target", "n", "positives", "map"}
_MAP_FIELDS = {"isotonic": {"x", "y"}, "platt": {"a", "b"}}


def labeled_pairs(question, cases, answers):
    """[(probability, outcome)] for the question's target, or None when it cannot be calibrated.

    Refused answers carry no probability and are left out. A Choice or Score answer without the
    probability of its chosen answer makes the whole question uncalibratable, as it makes `ece`
    unmeasured.
    """
    pairs = []
    for case in cases:
        if case.id not in answers or question.name not in case.labels:
            continue
        answer, expected = answers[case.id][question.name], case.labels[question.name]
        if isinstance(answer, RefusalAnswer):
            continue
        if answer.probability is None:
            return None
        if isinstance(question, Noul):
            pairs.append((answer.probability, expected))
        elif isinstance(question, Score):
            pairs.append((answer.probability, question.levels.index(answer.level) == expected))
        else:
            pairs.append((answer.probability, answer.choice == expected))
    return pairs or None


# Fitting -------------------------------------------------------------------

def fit_isotonic(pairs):
    """Pool-adjacent-violators on (probability, outcome); integer counts keep it exact."""
    groups = {}
    for probability, outcome in pairs:
        weight, positives = groups.get(probability, (0, 0))
        groups[probability] = (weight + 1, positives + int(outcome))
    blocks = []  # [low x, high x, weight, positives]
    for probability in sorted(groups):
        weight, positives = groups[probability]
        blocks.append([probability, probability, weight, positives])
        # Merge while the previous block's rate is at least this one's (cross-multiplied integers).
        while len(blocks) > 1 and blocks[-2][3] * blocks[-1][2] >= blocks[-1][3] * blocks[-2][2]:
            low, _, weight, positives = blocks.pop(-2)
            blocks[-1] = [low, blocks[-1][1], blocks[-1][2] + weight, blocks[-1][3] + positives]
    xs, ys = [], []
    for low, high, weight, positives in blocks:
        value = positives / weight
        xs.append(low)
        ys.append(value)
        if high != low:
            xs.append(high)
            ys.append(value)
    return {"x": xs, "y": ys}


def _logit(probability):
    p = min(max(probability, LOGIT_CLIP), 1 - LOGIT_CLIP)
    return math.log(p / (1 - p))


def _sigmoid(value):
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


def _softplus(value):
    return value + math.log1p(math.exp(-value)) if value > 0 else math.log1p(math.exp(value))


def fit_platt(pairs, max_iterations=100, strict=True):
    """Newton's method with backtracking on Platt's smoothed targets (Lin, Lin and Weng, 2007).

    It starts where Lin, Lin and Weng do, at the constant map (a = 0, b = logit of the mean target),
    where the Hessian is well conditioned. With a single distinct probability, a and b cannot both be
    identified, so that constant map is the answer. Once the loss stops changing above rounding, full
    Newton steps continue while they shrink the gradient. With `strict`, a fit that does not reach a
    near-zero gradient is an error rather than a map; a verifier refitting a recorded map passes False
    and compares the result instead.
    """
    positives = sum(1 for _, outcome in pairs if outcome)
    high, low = (positives + 1) / (positives + 2), 1 / (len(pairs) - positives + 2)
    data = [(_logit(probability), high if outcome else low) for probability, outcome in pairs]
    mean = math.fsum(t for _, t in data) / len(data)
    a, b = 0.0, math.log(mean / (1 - mean))
    if len({z for z, _ in data}) == 1:
        return {"a": a, "b": b}

    def loss(a, b):
        return math.fsum(t * _softplus(-(a * z + b)) + (1 - t) * _softplus(a * z + b) for z, t in data)

    def gradient(a, b):
        ga = gb = haa = hab = hbb = 0.0
        for z, t in data:
            p = _sigmoid(a * z + b)
            weight = p * (1 - p)
            ga += (p - t) * z
            gb += p - t
            haa += weight * z * z
            hab += weight * z
            hbb += weight
        return ga, gb, haa, hab, hbb

    ridge, current = 1e-12, loss(a, b)
    for _ in range(max_iterations):
        ga, gb, haa, hab, hbb = gradient(a, b)
        if max(abs(ga), abs(gb)) <= 1e-12 * len(data):
            break
        haa, hbb = haa + ridge, hbb + ridge
        determinant = haa * hbb - hab * hab
        da, db = -(hbb * ga - hab * gb) / determinant, -(haa * gb - hab * ga) / determinant
        slope, step = ga * da + gb * db, 1.0
        while step >= 1e-10:
            candidate = loss(a + step * da, b + step * db)
            if candidate <= current + 1e-4 * step * slope:
                break
            step /= 2
        else:
            # The loss no longer changes above rounding: finish with full Newton steps while they help.
            ga_next, gb_next, *_ = gradient(a + da, b + db)
            if max(abs(ga_next), abs(gb_next)) >= max(abs(ga), abs(gb)):
                break
            a, b = a + da, b + db
            current = loss(a, b)
            continue
        a, b, current = a + step * da, b + step * db, candidate
    ga, gb, *_ = gradient(a, b)
    if strict and max(abs(ga), abs(gb)) > 1e-8 * len(data):
        raise DatasetError(f"calibration: the platt fit did not converge (gradient {max(abs(ga), abs(gb)):.3g})")
    return {"a": a, "b": b}


def platt_identifiable(pairs):
    """Whether pairs determine both Platt parameters: two or more distinct clipped logits. Otherwise
    `fit_platt` returns the constant map (a = 0)."""
    return len({_logit(probability) for probability, _ in pairs}) > 1


def apply_map(method, mapping, probability):
    """The calibrated probability for one raw probability."""
    if method == "platt":
        return _sigmoid(mapping["a"] * _logit(probability) + mapping["b"])
    xs, ys = mapping["x"], mapping["y"]
    if probability <= xs[0]:
        return ys[0]
    if probability >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, probability) - 1
    if xs[i] == probability:
        return ys[i]
    return ys[i] + (ys[i + 1] - ys[i]) * (probability - xs[i]) / (xs[i + 1] - xs[i])


def fit(method, questions, cases, answers, fitted_on, produced_by, strict=True):
    """The calibration document for every question with labeled probabilities; DatasetError if none has.
    `strict=False` (for a verifier's refit) returns a Platt fit even if it stopped short of convergence."""
    if method not in METHODS:
        raise DatasetError(f"calibration method must be one of {list(METHODS)}")
    fitted = {}
    for question in questions:
        pairs = labeled_pairs(question, cases, answers)
        if pairs is None:
            continue
        fitted[question.name] = {"type": question.type, "target": TARGETS[question.type], "n": len(pairs),
                                 "positives": sum(1 for _, outcome in pairs if outcome),
                                 "map": fit_platt(pairs, strict=strict) if method == "platt" else fit_isotonic(pairs)}
    if not fitted:
        raise DatasetError("calibration: no question has answered, labeled cases with probabilities to fit")
    return {"schema_version": SCHEMA_VERSION, "produced_by": produced_by, "method": method,
            "fitted_on": fitted_on, "questions": fitted}


def fitted_on(cases_bytes, responses_bytes, cases):
    """The calibration set: hashes of the run's cases.jsonl and responses.jsonl, and its case ids."""
    return {"cases_sha256": hashlib.sha256(cases_bytes).hexdigest(),
            "responses_sha256": hashlib.sha256(responses_bytes).hexdigest(),
            "case_ids": sorted(case.id for case in cases)}


def dumps(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# Loading and applying ------------------------------------------------------

def _number(value, where, low=None, high=None):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) \
            or (low is not None and value < low) or (high is not None and value > high):
        raise DatasetError(f"calibration {where}: expected a finite number"
                           + (f" in [{low}, {high}]" if low is not None else ""))
    return value


def _fields(value, expected, where):
    if not isinstance(value, dict) or set(value) != expected:
        raise DatasetError(f"calibration {where}: expected exactly the members {sorted(expected)}")


def _check_map(method, mapping, where):
    _fields(mapping, _MAP_FIELDS[method], where)
    if method == "platt":
        _number(mapping["a"], f"{where}.a")
        _number(mapping["b"], f"{where}.b")
        return
    xs, ys = mapping["x"], mapping["y"]
    if not isinstance(xs, list) or not isinstance(ys, list) or not xs or len(xs) != len(ys):
        raise DatasetError(f"calibration {where}: x and y must be non-empty lists of the same length")
    for i, (x, y) in enumerate(zip(xs, ys)):
        _number(x, f"{where}.x[{i}]", 0, 1)
        _number(y, f"{where}.y[{i}]", 0, 1)
    if any(left >= right for left, right in zip(xs, xs[1:])) or any(left > right for left, right in zip(ys, ys[1:])):
        raise DatasetError(f"calibration {where}: x must increase strictly and y must not decrease")


def check(document):
    """Validate a calibration document (schema 1); raise DatasetError, return it unchanged."""
    _fields(document, _FIELDS, "file")
    if type(document["schema_version"]) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise DatasetError(f"unsupported calibration schema_version; expected {SCHEMA_VERSION}")
    producer = document["produced_by"]
    if not isinstance(producer, dict) or set(producer) != {"name", "version"} or producer["name"] != "jevdecision" \
            or not isinstance(producer["version"], str):
        raise DatasetError("calibration: invalid produced_by")
    method = document["method"]
    if method not in METHODS:
        raise DatasetError(f"calibration method must be one of {list(METHODS)}")
    basis = document["fitted_on"]
    _fields(basis, {"cases_sha256", "responses_sha256", "case_ids"}, "fitted_on")
    for name in ("cases_sha256", "responses_sha256"):
        digest = basis[name]
        if not isinstance(digest, str) or len(digest) != 64 or set(digest) - set("0123456789abcdef"):
            raise DatasetError(f"calibration fitted_on.{name}: expected 64 lowercase hex digits")
    ids = basis["case_ids"]
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids) \
            or ids != sorted(set(ids)):
        raise DatasetError("calibration fitted_on.case_ids: expected sorted, unique, non-empty strings")
    fitted = document["questions"]
    if not isinstance(fitted, dict) or not fitted:
        raise DatasetError("calibration questions: expected a non-empty object")
    for name, entry in fitted.items():
        where = f"questions.{name}"
        _fields(entry, _QUESTION_FIELDS, where)
        if not isinstance(entry["type"], str) or entry["type"] not in TARGETS \
                or entry["target"] != TARGETS[entry["type"]]:
            raise DatasetError(f"calibration {where}: invalid type or target")
        n, positives = entry["n"], entry["positives"]
        if type(n) is not int or type(positives) is not int or n < 1 or not 0 <= positives <= n:
            raise DatasetError(f"calibration {where}: n must be a positive integer and positives in [0, n]")
        _check_map(method, entry["map"], f"{where}.map")
    return document


@dataclass(frozen=True)
class Calibration:
    """A validated calibration document."""

    document: dict

    @property
    def method(self):
        return self.document["method"]

    @property
    def case_ids(self):
        return frozenset(self.document["fitted_on"]["case_ids"])

    def __contains__(self, name):
        return name in self.document["questions"]

    def check_applicable(self, questions, cases):
        """Every calibrated question must be one of `questions`, with the same type, and no case may be
        one the calibration was fitted on: calibrated metrics are measured on held-out cases only."""
        by_name = {question.name: question for question in questions}
        for name, entry in self.document["questions"].items():
            if name not in by_name or by_name[name].type != entry["type"]:
                raise DatasetError(f"calibration: {name!r} is not a {entry['type']} question of this question set")
        shared = sorted(self.case_ids & {case.id for case in cases})
        if shared:
            listed = ", ".join(shared[:5]) + (f" and {len(shared) - 5} more" if len(shared) > 5 else "")
            raise DatasetError(f"calibration was fitted on cases of this evaluation ({listed}); "
                               "evaluate it on held-out cases")

    def calibrate(self, name, probability):
        """Map a raw probability of question `name` (its target, see the module docstring)."""
        entry = self.document["questions"][name]
        return apply_map(self.method, entry["map"], probability)


def load(data):
    """Parse and validate calibration.json bytes; DatasetError for anything malformed."""
    try:
        document = loads_strict(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise DatasetError(f"calibration: not a JSON document: {error}") from None
    return Calibration(check(document))
