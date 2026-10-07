"""Typed answers and the provider-neutral response parser.

Both providers return one answer per question with probabilities, but spell the
fields differently (Jev keys answers by question name and probabilities by
label; the OpenAI Decisions API may return a list of named answers and a list of
per-option probabilities). `parse_answers` accepts either shape and checks every
answer against the question it answers, so callers see one typed result.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import ResponseError
from .questions import Choice, Noul, Score

# Providers round probabilities; tolerate that much overshoot of [0, 1].
PROBABILITY_SLACK = 1e-6
LABEL_KEYS = ("value", "label", "choice", "level", "name")
PROBABILITY_KEYS = ("probability", "p", "prob")


@dataclass(frozen=True)
class NoulAnswer:
    name: str
    probability: float
    type = "noul"

    def is_yes(self, threshold=0.5):
        return self.probability >= threshold

    def to_dict(self):
        return {"type": self.type, "probability": self.probability}


@dataclass(frozen=True)
class ChoiceAnswer:
    name: str
    choice: str
    probabilities: "dict[str, float]"
    confidence: Optional[float] = None
    type = "choice"

    @property
    def probability(self):
        return self.probabilities.get(self.choice)

    def ranked(self):
        """Labels with their probabilities, most likely first (ties keep option order)."""
        return sorted(self.probabilities.items(), key=lambda item: -item[1])

    def to_dict(self):
        return {
            "type": self.type,
            "choice": self.choice,
            "probabilities": dict(self.probabilities),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ScoreAnswer:
    name: str
    score: float
    levels: "tuple[str, ...]"
    probabilities: "tuple[float, ...]"
    confidence: Optional[float] = None
    type = "score"

    @property
    def level(self):
        """The level nearest to the score."""
        index = min(max(int(math.floor(self.score + 0.5)), 0), len(self.levels) - 1)
        return self.levels[index]

    @property
    def normalized(self):
        """The score rescaled to [0, 1]."""
        return self.score / (len(self.levels) - 1)

    def to_dict(self):
        return {
            "type": self.type,
            "score": self.score,
            "level": self.level,
            "levels": list(self.levels),
            "probabilities": list(self.probabilities),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Decision:
    """All answers for one request, keyed by question name."""

    answers: "dict[str, Any]"
    backend: str
    model: Optional[str] = None
    usage: "dict[str, Any]" = field(default_factory=dict)
    id: Optional[str] = None
    raw: "dict[str, Any]" = field(default_factory=dict, repr=False, compare=False)

    def __getitem__(self, name):
        return self.answers[name]

    def __iter__(self):
        return iter(self.answers)

    def __len__(self):
        return len(self.answers)

    def to_dict(self):
        return {
            "backend": self.backend,
            "model": self.model,
            "id": self.id,
            "usage": dict(self.usage),
            "answers": {name: answer.to_dict() for name, answer in self.answers.items()},
        }


# Parsing -------------------------------------------------------------------

def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResponseError(f"{where}: expected a number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ResponseError(f"{where}: expected a finite number, got {value!r}")
    return value


def _probability(value, where):
    value = _number(value, where)
    if not -PROBABILITY_SLACK <= value <= 1 + PROBABILITY_SLACK:
        raise ResponseError(f"{where}: probability {value} is outside [0, 1]")
    return min(max(value, 0.0), 1.0)


def _first(entry, keys):
    for key in keys:
        if key in entry and entry[key] is not None:
            return entry[key]
    return None


def _probability_map(raw, where):
    """Return {key: probability} from a mapping, or a list of {label, probability} objects."""
    if isinstance(raw, dict):
        return {str(key): _probability(value, f"{where}[{key!r}]") for key, value in raw.items()}
    if isinstance(raw, list):
        result = {}
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ResponseError(f"{where}[{index}]: expected an object, got {item!r}")
            key = _first(item, LABEL_KEYS)
            value = _first(item, PROBABILITY_KEYS)
            if key is None or value is None:
                raise ResponseError(f"{where}[{index}]: needs a label and a probability")
            result[str(key)] = _probability(value, f"{where}[{key!r}]")
        return result
    raise ResponseError(f"{where}: expected an object or a list, got {raw!r}")


def _confidence(entry, where):
    value = entry.get("confidence")
    return None if value is None else _probability(value, f"{where}.confidence")


def _parse_noul(question, entry, where):
    value = _first(entry, ("noul", "probability", "predicate", "value"))
    if value is None:
        raise ResponseError(f"{where}: missing the probability of yes")
    return NoulAnswer(question.name, _probability(value, where))


def _parse_choice(question, entry, where):
    labels = question.labels
    choice = _first(entry, ("choice", "value", "label"))
    if choice not in question.options:
        raise ResponseError(f"{where}: choice {choice!r} is not one of {list(labels)}")
    raw = entry.get("probabilities")
    probabilities = _probability_map(raw, f"{where}.probabilities") if raw is not None else {}
    unknown = set(probabilities) - set(labels)
    if unknown:
        raise ResponseError(f"{where}: probabilities name unknown options {sorted(unknown)}")
    ordered = {label: probabilities.get(label, 0.0) for label in labels}
    if not probabilities:
        ordered[choice] = 1.0
    return ChoiceAnswer(question.name, choice, ordered, _confidence(entry, where))


def _parse_score(question, entry, where):
    levels = question.levels
    raw = entry.get("probabilities")
    probabilities = [0.0] * len(levels)
    if isinstance(raw, list) and all(not isinstance(item, dict) for item in raw):
        if len(raw) != len(levels):
            raise ResponseError(f"{where}: expected {len(levels)} probabilities, got {len(raw)}")
        probabilities = [_probability(value, f"{where}.probabilities[{i}]") for i, value in enumerate(raw)]
    elif raw is not None:
        for key, value in _probability_map(raw, f"{where}.probabilities").items():
            if key in levels:
                index = levels.index(key)
            elif key.isdigit() and int(key) < len(levels):
                index = int(key)
            else:
                raise ResponseError(f"{where}: probabilities name unknown level {key!r}")
            probabilities[index] = value
    score = entry.get("score")
    if score is None:
        if raw is None:
            raise ResponseError(f"{where}: missing the score")
        total = sum(probabilities)
        if total <= 0:
            raise ResponseError(f"{where}: probabilities are all zero")
        score = sum(i * p for i, p in enumerate(probabilities)) / total
    score = _number(score, f"{where}.score")
    if not -PROBABILITY_SLACK <= score <= len(levels) - 1 + PROBABILITY_SLACK:
        raise ResponseError(f"{where}: score {score} is outside [0, {len(levels) - 1}]")
    score = min(max(score, 0.0), float(len(levels) - 1))
    return ScoreAnswer(question.name, score, levels, tuple(probabilities), _confidence(entry, where))


PARSERS = {Noul: _parse_noul, Choice: _parse_choice, Score: _parse_score}
TYPE_ALIASES = {"noul": "noul", "predicate": "noul", "choice": "choice", "score": "score"}


def _entries_by_name(raw_answers):
    if isinstance(raw_answers, dict):
        return raw_answers
    if isinstance(raw_answers, list):
        entries = {}
        for index, entry in enumerate(raw_answers):
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                raise ResponseError(f"answers[{index}]: expected an object with a name")
            if entry["name"] in entries:
                raise ResponseError(f"answers: duplicate answer for {entry['name']!r}")
            entries[entry["name"]] = entry
        return entries
    raise ResponseError(f"answers: expected an object or a list, got {type(raw_answers).__name__}")


def parse_answers(raw_answers, questions):
    """Return {name: answer} for `questions`; raise ResponseError on any mismatch."""
    entries = _entries_by_name(raw_answers)
    asked = {question.name for question in questions}
    extra = set(entries) - asked
    if extra:
        raise ResponseError(f"answers: unexpected answers for {sorted(extra)}")
    answers = {}
    for question in questions:
        where = f"answers[{question.name!r}]"
        entry = entries.get(question.name)
        if not isinstance(entry, dict):
            raise ResponseError(f"{where}: missing or not an object")
        kind = entry.get("type")
        if kind is not None and TYPE_ALIASES.get(kind) != question.type:
            raise ResponseError(f"{where}: answered as {kind!r}, asked as {question.type!r}")
        answers[question.name] = PARSERS[type(question)](question, entry, where)
    return answers
