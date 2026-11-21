"""The decision model facade used by applications."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Any, TypeVar, cast

from .answers import Answer, ChoiceAnswer, Decision, NoulAnswer, RefusalAnswer
from .backends import HTTPBackend, State, create_backend
from .questions import Choice, Noul, Question, check_question_set

from .errors import DecisionError

Fallback = TypeVar("Fallback")

DEFAULT_BACKEND = "jev"
BACKEND_ENV = "DECISION_BACKEND"


class DecisionModel:
    """Ask typed questions about a state; Jev by default, the OpenAI Decisions API optionally.

    Every request is validated before it is sent, and every response is checked
    against the questions it answers, so callers get typed answers or an error.
    """

    def __init__(self, backend: HTTPBackend | None = None) -> None:
        self.backend = backend if backend is not None else create_backend(DEFAULT_BACKEND)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **options: Any) -> DecisionModel:
        """Pick the backend from DECISION_BACKEND (`jev` or `openai`; default `jev`)."""
        env = os.environ if env is None else env
        name = env.get(BACKEND_ENV) or DEFAULT_BACKEND
        return cls(create_backend(name, env=env, **options))

    def decide(self, state: State, questions: Iterable[Question] | Question) -> Decision:
        """Answer every question about `state` in one request and return a Decision."""
        return self.backend.decide(state, check_question_set(questions))

    def ask(self, state: State, question: Question) -> Answer:
        """Answer a single question and return its typed answer."""
        return self.decide(state, [question])[question.name]

    def gate(self, state: State, question: Noul, threshold: float = 0.5) -> bool:
        """True when the probability of yes is at least `threshold`."""
        if not isinstance(question, Noul):
            raise DecisionError("gate() takes a Noul (yes/no) question")
        if not 0.0 <= threshold <= 1.0:
            raise DecisionError("threshold must lie in [0, 1]")
        answer = self.ask(state, question)
        return False if isinstance(answer, RefusalAnswer) else cast(NoulAnswer, answer).is_yes(threshold)

    def route(self, state: State, question: Choice, min_confidence: float = 0.0, fallback: Fallback | None = None) -> str | Fallback | None:
        """The chosen label, or `fallback` when confidence is unknown or below `min_confidence`.

        Confidence is the provider's own field when present, otherwise the
        reported probability of the chosen label. Missing values stay unknown,
        including when `min_confidence` is zero.
        """
        if not isinstance(question, Choice):
            raise DecisionError("route() takes a Choice question")
        if not 0.0 <= min_confidence <= 1.0:
            raise DecisionError("min_confidence must lie in [0, 1]")
        answer = self.ask(state, question)
        if isinstance(answer, RefusalAnswer):
            return fallback
        answer = cast(ChoiceAnswer, answer)
        confidence = answer.confidence if answer.confidence is not None else answer.probability
        if confidence is None or confidence < min_confidence:
            return fallback
        return answer.choice
