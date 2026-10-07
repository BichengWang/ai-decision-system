"""jevdecision: Jev as the core decision model, with an OpenAI Decisions API backend.

A decision model answers bounded questions about a state with typed,
probability-bearing answers instead of generated text. This package defines the
questions and answers once and talks to either provider:

    from jevdecision import Choice, DecisionModel, Noul

    model = DecisionModel.from_env()          # DECISION_BACKEND=jev (default) or openai
    decision = model.decide(
        "Help! My payouts have been failing for 3 days.",
        [
            Noul("refund", "Is the customer asking for a refund?"),
            Choice("department", "Which team should handle this?", {
                "billing": "Payments, invoicing, refunds",
                "technical": "Bugs, outages, integrations",
            }),
        ],
    )
    decision["department"].choice
"""

from .answers import ChoiceAnswer, Decision, NoulAnswer, ScoreAnswer
from .backends import JevBackend, OpenAIDecisionsBackend, create_backend
from .core import DecisionModel
from .errors import APIError, DecisionError, QuestionError, ResponseError
from .questions import Choice, Noul, Predicate, Score, questions_from_spec

__version__ = "0.1.0"

__all__ = [
    "APIError",
    "Choice",
    "ChoiceAnswer",
    "Decision",
    "DecisionError",
    "DecisionModel",
    "JevBackend",
    "Noul",
    "NoulAnswer",
    "OpenAIDecisionsBackend",
    "Predicate",
    "QuestionError",
    "ResponseError",
    "Score",
    "ScoreAnswer",
    "create_backend",
    "questions_from_spec",
]
