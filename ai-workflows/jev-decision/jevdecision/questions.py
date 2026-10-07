"""Typed decision questions shared by every backend.

Three question types cover both providers:

| Type | Jev | OpenAI Decisions API | Answer |
|---|---|---|---|
| `Noul` | `noul` | `predicate` | probability that the answer is yes |
| `Choice` | `choice` with `criteria` label -> description | `choice` with `choices` | one label plus a probability per label |
| `Score` | `score` with ordered `criteria` | `score` with `levels` | probability-weighted level index |
"""

import re
from dataclasses import dataclass, field
from types import MappingProxyType

from .errors import QuestionError

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10


def _check_common(name, instructions):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise QuestionError(
            f"question name {name!r} must start with a letter or underscore and contain "
            "only letters, digits, '_' or '-' (at most 64 characters)"
        )
    if not isinstance(instructions, str) or not instructions.strip():
        raise QuestionError(f"question {name!r}: instructions must be a non-empty string")


def _check_label(question, label, what):
    if not isinstance(label, str) or not label.strip():
        raise QuestionError(f"question {question!r}: every {what} must be a non-empty string")


@dataclass(frozen=True)
class Noul:
    """A yes/no question; the answer is the probability of yes."""

    name: str
    instructions: str
    type = "noul"

    def __post_init__(self):
        _check_common(self.name, self.instructions)


# The OpenAI Decisions API calls the same question type a predicate.
Predicate = Noul


@dataclass(frozen=True)
class Choice:
    """Pick one label from a fixed set; `options` maps each label to when it applies."""

    name: str
    instructions: str
    options: "dict[str, str]" = field(default_factory=dict)
    type = "choice"

    def __post_init__(self):
        _check_common(self.name, self.instructions)
        if not hasattr(self.options, "items"):
            raise QuestionError(f"question {self.name!r}: options must map labels to descriptions")
        options = dict(self.options)
        if not 1 <= len(options) <= MAX_CHOICE_OPTIONS:
            raise QuestionError(
                f"question {self.name!r}: a choice needs 1 to {MAX_CHOICE_OPTIONS} options, "
                f"got {len(options)}"
            )
        for label, description in options.items():
            _check_label(self.name, label, "option label")
            _check_label(self.name, description, "option description")
        object.__setattr__(self, "options", MappingProxyType(options))

    @property
    def labels(self):
        return tuple(self.options)


@dataclass(frozen=True)
class Score:
    """Place the state on an ordered scale; `levels` run from lowest (index 0) to highest."""

    name: str
    instructions: str
    levels: "tuple[str, ...]" = ()
    type = "score"

    def __post_init__(self):
        _check_common(self.name, self.instructions)
        if isinstance(self.levels, str):
            raise QuestionError(f"question {self.name!r}: levels must be a sequence of strings")
        levels = tuple(self.levels)
        if not MIN_SCORE_LEVELS <= len(levels) <= MAX_SCORE_LEVELS:
            raise QuestionError(
                f"question {self.name!r}: a score needs {MIN_SCORE_LEVELS} to "
                f"{MAX_SCORE_LEVELS} levels, got {len(levels)}"
            )
        for level in levels:
            _check_label(self.name, level, "level")
        if len(set(levels)) != len(levels):
            raise QuestionError(f"question {self.name!r}: levels must be distinct")
        object.__setattr__(self, "levels", levels)


QUESTION_TYPES = (Noul, Choice, Score)


def check_question_set(questions):
    """Return the questions as a tuple; raise QuestionError if the set is invalid."""
    if isinstance(questions, QUESTION_TYPES):
        questions = [questions]
    questions = tuple(questions)
    if not questions:
        raise QuestionError("at least one question is required")
    seen = set()
    for question in questions:
        if not isinstance(question, QUESTION_TYPES):
            raise QuestionError(f"unsupported question object: {question!r}")
        if question.name in seen:
            raise QuestionError(f"duplicate question name {question.name!r}")
        seen.add(question.name)
    return questions


def questions_from_spec(spec):
    """Build questions from Jev's native map: {name: {type, instructions, criteria}}.

    `criteria` is a label -> description map for `choice`, an ordered list of
    levels for `score`, and absent for `noul`. `predicate` is accepted as an
    alias of `noul`.
    """
    if not isinstance(spec, dict) or not spec:
        raise QuestionError("the question spec must be a non-empty object keyed by question name")
    questions = []
    for name, entry in spec.items():
        if not isinstance(entry, dict):
            raise QuestionError(f"question {name!r}: the spec entry must be an object")
        kind = entry.get("type")
        instructions = entry.get("instructions")
        criteria = entry.get("criteria")
        if kind in ("noul", "predicate"):
            questions.append(Noul(name, instructions))
        elif kind == "choice":
            if not isinstance(criteria, dict):
                raise QuestionError(f"question {name!r}: choice criteria must be an object")
            questions.append(Choice(name, instructions, criteria))
        elif kind == "score":
            if not isinstance(criteria, list):
                raise QuestionError(f"question {name!r}: score criteria must be a list")
            questions.append(Score(name, instructions, criteria))
        else:
            raise QuestionError(f"question {name!r}: unknown type {kind!r}")
    return check_question_set(questions)
