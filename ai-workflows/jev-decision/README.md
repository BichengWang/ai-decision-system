# Jev decision model (`jevdecision`)

The core decision model for this workspace. A decision model answers bounded
questions about a state with **typed, probability-bearing answers** instead of
generated text: a yes/no probability, one label from a fixed set, or a position
on an ordered scale. That makes it suitable for gating agent tool calls, routing
tickets, triage, and other steps where software acts on the answer directly.

[Jev](https://docs.typesafe.ai/api) (TypeSafe's System One model) is the default
backend. The [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions)
is a drop-in alternative: questions are defined once and answers come back in the
same types from either provider. The package uses only the Python standard
library, so it has no dependencies and no lockfile.

## Question types

| Type | Jev request | OpenAI request | Answer |
|---|---|---|---|
| `Noul` (alias `Predicate`) | `noul` | `predicate` | `NoulAnswer.probability`: probability of yes |
| `Choice` | `choice`, `criteria` = label → description | `choice`, `choices` = `[{value, description}]` | `ChoiceAnswer.choice`, `.probabilities` per label, `.confidence` |
| `Score` | `score`, `criteria` = ordered levels | `score`, `levels` = `[{label}]` | `ScoreAnswer.score` (probability-weighted level index), `.level`, `.probabilities` per level |

Questions are validated before anything is sent: names are unique identifiers,
instructions are non-empty, a choice has 1 to 255 options, and a score has 2 to
10 distinct levels. Responses are checked against the questions they answer.
Every question must be answered with its own type, a choice must be one of the
options, and probabilities and scores must lie in range. Anything else raises
`ResponseError`, so the application never acts on a malformed answer.

## Usage

```python
from jevdecision import Choice, DecisionModel, Noul, Score

model = DecisionModel.from_env()   # DECISION_BACKEND=jev (default) or openai

decision = model.decide(
    "Help! My payouts have been failing for 3 days.",
    [
        Noul("refund", "Is the customer asking for a refund?"),
        Choice("department", "Which team should handle this?", {
            "billing": "Payments, invoicing, refunds",
            "technical": "Bugs, outages, integrations",
            "sales": "Pricing, upgrades, new accounts",
        }),
        Score("frustration", "How frustrated is the customer?", ["Calm", "Frustrated", "Very angry"]),
    ],
)
decision["department"].choice        # "technical"
decision["frustration"].level        # "Frustrated"

# Single-question helpers
model.gate(state, refund_question, threshold=0.8)                  # bool
model.route(state, department_question, min_confidence=0.7,
            fallback="human_review")                               # label or fallback
```

`route` uses the provider's `confidence` when it returns one, otherwise the
probability of the chosen label.

## Configuration

| Variable | Backend | Meaning |
|---|---|---|
| `DECISION_BACKEND` | both | `jev` (default) or `openai` |
| `TYPESAFE_API_KEY` | `jev` | Bearer token for `https://api.typesafe.ai/v1/systemone` |
| `JEV_MODEL` | `jev` | Model route (default `jev-latest`) |
| `OPENAI_API_KEY` | `openai` | Bearer token for `https://api.openai.com/v1/decisions` |
| `OPENAI_DECISIONS_MODEL` | `openai` | Model (default `gpt-6-luna`) |

Every backend also takes `api_key`, `model`, `base_url`, `path`, `timeout`,
`max_retries`, and `transport` arguments. Use `base_url` and `path` for a gateway
that serves Jev elsewhere, for example `path="/v1/decisions"` with
`model="typesafe/jev"`. Rate-limit (429), server (5xx), and connection errors are
retried with exponential backoff (2 retries by default). Other HTTP errors are
raised as `APIError` immediately. `transport` is any callable
`(url, headers, body_bytes, timeout) -> dict`, which tests use to replace the
network.

The structured state can be text, a JSON object, or a list of strings. Jev
receives it unchanged. The OpenAI backend sends text, so it serializes an object
as JSON with sorted keys and joins a list with blank lines.

## Command line

From this directory, with Python 3.11 or later:

```bash
python3 -m unittest discover -s tests
python3 -m jevdecision --questions examples/support-ticket.json \
    --state "Help! My payouts have been failing for 3 days." --dry-run
python3 -m jevdecision --questions examples/support-ticket.json \
    --state-file ticket.json --backend openai
```

The questions file uses Jev's native question map
([`examples/support-ticket.json`](examples/support-ticket.json)). `predicate` is
accepted as an alias of `noul`. A `.json` state file is sent as structured
state, and any other file is sent as text. `--dry-run` prints the provider request
without sending it, so it needs no API key. The decision is printed as JSON. Exit
codes: 0 for success, 1 for a provider or response error, 2 for invalid input.

From the repository root, `make jev-test` runs the tests and
`make jev-dry-run` prints the example request for both backends.

## Limitations

- Both provider APIs are new. The Jev request and response shapes follow
  TypeSafe's published examples. The OpenAI Decisions API is in public beta, so
  the parser accepts both its object and its list answer layouts. Recheck the
  field mapping against the provider references before you depend on it in
  production.
- Image inputs and per-request options beyond the model are not modeled yet.
- Unit tests use recorded response shapes and never call a provider.
