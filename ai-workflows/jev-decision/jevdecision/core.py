"""The decision model facade used by applications."""

import os

from .backends import create_backend
from .errors import DecisionError
from .questions import Choice, Noul, check_question_set

DEFAULT_BACKEND = "jev"
BACKEND_ENV = "DECISION_BACKEND"


class DecisionModel:
    """Ask typed questions about a state; Jev by default, the OpenAI Decisions API optionally.

    Every request is validated before it is sent, and every response is checked
    against the questions it answers, so callers get typed answers or an error.
    """

    def __init__(self, backend=None):
        self.backend = backend if backend is not None else create_backend(DEFAULT_BACKEND)

    @classmethod
    def from_env(cls, env=None, **options):
        """Pick the backend from DECISION_BACKEND (`jev` or `openai`; default `jev`)."""
        env = os.environ if env is None else env
        name = env.get(BACKEND_ENV) or DEFAULT_BACKEND
        return cls(create_backend(name, env=env, **options))

    def decide(self, state, questions):
        """Answer every question about `state` in one request and return a Decision."""
        return self.backend.decide(state, check_question_set(questions))

    def ask(self, state, question):
        """Answer a single question and return its typed answer."""
        return self.decide(state, [question])[question.name]

    def gate(self, state, question, threshold=0.5):
        """True when the probability of yes is at least `threshold`."""
        if not isinstance(question, Noul):
            raise DecisionError("gate() takes a Noul (yes/no) question")
        if not 0.0 <= threshold <= 1.0:
            raise DecisionError("threshold must lie in [0, 1]")
        return self.ask(state, question).is_yes(threshold)

    def route(self, state, question, min_confidence=0.0, fallback=None):
        """The chosen label, or `fallback` when the provider's confidence is below `min_confidence`.

        Confidence is the provider's own field when present, otherwise the
        probability of the chosen label.
        """
        if not isinstance(question, Choice):
            raise DecisionError("route() takes a Choice question")
        answer = self.ask(state, question)
        confidence = answer.confidence if answer.confidence is not None else answer.probability
        if confidence is None or confidence < min_confidence:
            return fallback
        return answer.choice
