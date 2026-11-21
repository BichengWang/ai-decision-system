"""Typed answers and the provider-neutral response parser.

Both providers return one answer per question with probabilities, but spell the
fields differently (Jev keys answers by question name and probabilities by
label; the OpenAI Decisions API may return a list of named answers and a list of
per-option probabilities). `parse_answers` accepts either shape and checks every
answer against the question it answers, so callers see one typed result.
"""

from __future__ import annotations

from collections.abc import Iterator
import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import ResponseError
from .questions import Choice, Noul, Score

# Retain the existing rounding tolerance for numeric score indices only.
PROBABILITY_SLACK = 1e-6
LABEL_KEYS = ("value", "label", "choice", "level", "name")
LEVEL_INDEX_RE = re.compile(r"[0-9]+")
PROBABILITY_KEYS = ("probability", "p", "prob")


@dataclass(frozen=True)
class RefusalAnswer:
    """A provider declined this question; sibling answers remain usable."""
    name: str
    type = "refusal"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type}


@dataclass(frozen=True)
class NoulAnswer:
    name: str
    probability: float
    type = "noul"

    def is_yes(self, threshold: float = 0.5) -> bool:
        return self.probability >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "probability": self.probability}


@dataclass(frozen=True)
class ChoiceAnswer:
    name: str
    choice: str
    probabilities: "dict[str, float]"
    confidence: Optional[float] = None
    type = "choice"

    @property
    def probability(self) -> Optional[float]:
        return self.probabilities.get(self.choice)

    def ranked(self) -> list[tuple[str, float]]:
        """Labels with their probabilities, most likely first (ties keep option order)."""
        return sorted(self.probabilities.items(), key=lambda item: -item[1])

    def to_dict(self) -> dict[str, Any]:
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
    probabilities: "tuple[Optional[float], ...]"
    confidence: Optional[float] = None
    type = "score"

    @property
    def level(self) -> str:
        """The level nearest to the score."""
        index = min(max(int(math.floor(self.score + 0.5)), 0), len(self.levels) - 1)
        return self.levels[index]

    @property
    def probability(self) -> Optional[float]:
        return self.probabilities[self.levels.index(self.level)]

    @property
    def normalized(self) -> float:
        """The score rescaled to [0, 1]."""
        return self.score / (len(self.levels) - 1)

    def to_dict(self) -> dict[str, Any]:
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

    answers: "dict[str, Answer]"
    backend: str
    model: Optional[str] = None
    usage: "dict[str, Any]" = field(default_factory=dict)
    id: Optional[str] = None
    raw: "dict[str, Any]" = field(default_factory=dict, repr=False, compare=False)

    def __getitem__(self, name: str) -> Answer:
        return self.answers[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.answers)

    def __len__(self) -> int:
        return len(self.answers)

    def to_dict(self) -> dict[str, Any]:
        from . import __version__
        return {
            "schema_version": 1,
            "produced_by": {"name": "jevdecision", "version": __version__},
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
    try:
        value = float(value)
    except OverflowError:
        raise ResponseError(f"{where}: expected a finite number, got an integer too large for a float") from None
    if not math.isfinite(value):
        raise ResponseError(f"{where}: expected a finite number, got {value!r}")
    return value


def _probability(value, where):
    value = _number(value, where)
    if not 0 <= value <= 1:
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
            if not isinstance(key, (str, int)) or isinstance(key, bool):
                raise ResponseError(f"{where}[{index}]: label must be a string or an index, got {key!r}")
            if str(key) in result:
                raise ResponseError(f"{where}: label {str(key)!r} appears more than once")
            result[str(key)] = _probability(value, f"{where}[{key!r}]")
        return result
    raise ResponseError(f"{where}: expected an object or a list, got {raw!r}")


def _distribution(values, where):
    values = tuple(values)
    if abs(sum(values) - 1) > 1e-6 * len(values) + 1e-3:
        raise ResponseError(f"{where}: probability distribution must sum to 1")


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
    if not isinstance(choice, str) or choice not in question.options:
        raise ResponseError(f"{where}: choice {choice!r} is not one of {list(labels)}")
    raw = entry.get("probabilities")
    probabilities = _probability_map(raw, f"{where}.probabilities") if raw is not None else {}
    unknown = set(probabilities) - set(labels)
    if unknown:
        raise ResponseError(f"{where}: probabilities name unknown options {sorted(unknown)}")
    if len(probabilities) == len(labels):
        _distribution(probabilities.values(), where)
    ordered = {label: probabilities[label] for label in labels if label in probabilities}
    return ChoiceAnswer(question.name, choice, ordered, _confidence(entry, where))


def _parse_score(question, entry, where):
    levels = question.levels
    raw = entry.get("probabilities")
    probabilities = [None] * len(levels)
    if isinstance(raw, list) and all(not isinstance(item, dict) for item in raw):
        if len(raw) > len(levels):
            raise ResponseError(f"{where}: expected {len(levels)} probabilities, got {len(raw)}")
        probabilities[:len(raw)] = [None if value is None else _probability(value, f"{where}.probabilities[{i}]")
                                  for i, value in enumerate(raw)]
    elif raw is not None:
        named = set()
        for key, value in _probability_map(raw, f"{where}.probabilities").items():
            if key in levels:
                index = levels.index(key)
            elif LEVEL_INDEX_RE.fullmatch(key) and int(key) < len(levels):
                index = int(key)
            else:
                raise ResponseError(f"{where}: probabilities name unknown level {key!r}")
            if index in named:
                raise ResponseError(f"{where}: probabilities name level {levels[index]!r} more than once")
            named.add(index)
            probabilities[index] = value
    complete = all(p is not None for p in probabilities)
    if complete:
        _distribution(probabilities, where)
    score = entry.get("score")
    if score is None:
        if not complete:
            raise ResponseError(f"{where}: missing score; deriving it requires a complete probability distribution")
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
        if kind == "refusal":
            answers[question.name] = RefusalAnswer(question.name)
            continue
        if kind is not None and (not isinstance(kind, str) or TYPE_ALIASES.get(kind) != question.type):
            raise ResponseError(f"{where}: answered as {kind!r}, asked as {question.type!r}")
        answers[question.name] = PARSERS[type(question)](question, entry, where)
    return answers


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer | RefusalAnswer
