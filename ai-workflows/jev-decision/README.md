# Jev decision model (`jevdecision`)

Replayable decision records for AI-assisted go/no-go decisions. A decision model answers bounded
questions about a state with **typed answers and reported probabilities** instead of
generated text: a yes/no probability, one label from a fixed set, or a position
on an ordered scale. These can inform gating agent tool calls, routing tickets,
and triage; missing choice uncertainty never becomes permission to route.

[Jev](https://docs.typesafe.ai/api) (TypeSafe's System One model) is the default
backend. The [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions)
is a drop-in alternative: questions are defined once and answers come back in the
same types from either provider. The package uses only the Python standard
library, so it has no dependencies and no lockfile.

## Install

Requires Python 3.11 or later; runtime dependencies: none. Examples live in the clone
and source distribution under `examples/`; they are not installed in the wheel.

```bash
# Published version: 0.1.0
pip install jevdecision
```

Schemas, `jev-decision-verify` and signing documented on `main` ship in 0.2.0,
which is not yet published. Until then, install from source in this directory:

```bash
pip install .
```

The distribution includes `jev-decision`, `jev-decision-eval` and `jev-decision-verify` (signing and verification of records: see Signed records); existing
`python -m jevdecision`, `python -m jevdecision.evaluation` and `python -m jevdecision.verify` commands remain supported.
Use the `examples/` directory in a clone or unpacked source distribution.

## Question types

| Type | Jev request | OpenAI request | Answer |
|---|---|---|---|
| `Noul` (alias `Predicate`) | `noul` | `predicate` | `NoulAnswer.probability`: probability of yes |
| `Choice` | `choice`, `criteria` = label → description | `choice`, `choices` = `[{value, description}]` | `ChoiceAnswer.choice`, `.probabilities` per label, `.confidence` |
| `Score` | `score`, `criteria` = ordered levels | `score`, `levels` = `[{label}]` | `ScoreAnswer.score` (probability-weighted level index), `.level`, `.probabilities` per level |

Questions are validated before anything is sent: names are unique identifiers,
instructions are non-empty, a choice has 1 to 255 options, and a score has 2 to
10 distinct levels. Responses are checked against the questions they answer.
Every question must have a matching answer or an explicit `type: "refusal"` result; a choice must be one of the
options, and probabilities and scores must lie in range. Probabilities must be finite and within [0,1]. Complete distributions must sum
to 1 within `1e-6 * number_of_options + 1e-3`; partial collections retain unknown
entries and are not treated as complete distributions. Invalid responses raise
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
reported probability of the chosen label. If neither is supplied, it returns
`fallback` (default `None`), even with `min_confidence=0.0`. A reported confidence
still takes precedence over a reported choice probability; neither is a calibrated
safety guarantee or a replacement for application policy.

### Refusals and score uncertainty

An explicit per-question refusal becomes `RefusalAnswer` with `.name` and
`.type == "refusal"`. `ask`/`decide` retain valid sibling answers. `gate` returns
`False` for a refusal, even at threshold zero; `route` returns its fallback.
The OpenAI guide documents this marker; TypeSafe's reference does not document
refusal fields, so no reason or other provider-specific field is assumed.

Score probabilities are a tuple in level order, with `None` for missing entries.
`.probability` is the reported probability of the nearest level, or `None`.
A supplied score remains usable without probabilities; deriving a missing score
requires a complete distribution. Missing values are never zero-filled.

### Choice uncertainty contract

`ask` and `decide` retain a valid choice even when its uncertainty is unknown:

- `.probabilities` contains only labels whose probabilities were actually supplied,
  in question-option order. Missing, null, or empty probability collections yield `{}`.
- `.probability` is `None` when the chosen label has no reported probability.
  A supplied `confidence` does not manufacture a choice probability.
- `.ranked()` ranks only reported probabilities. `to_dict()` preserves missing
  entries instead of fabricating a complete distribution.
- A reported `0.0` remains zero, distinct from an absent value.

**Safety correction:** earlier code fabricated probability `1.0` for a choice
without probabilities and filled omitted labels with `0.0`. Callers must use
`.probability` or `.probabilities.get(label)` and handle `None`; do not rely on
every label being present. To inspect an unscored recommendation, use `ask` or
`decide`, not a confidence-gated route with an invented probability.

## Configuration

| Variable | Backend | Meaning |
|---|---|---|
| `DECISION_BACKEND` | both | `jev` (default) or `openai` |
| `TYPESAFE_API_KEY` | `jev` | Bearer token for `https://api.typesafe.ai/v1/systemone` |
| `JEV_MODEL` | `jev` | Model route (default `jev-latest`) |
| `OPENAI_API_KEY` | `openai` | Bearer token for `https://api.openai.com/v1/decisions` |
| `OPENAI_DECISIONS_MODEL` | `openai` | Model (default `gpt-6-luna`) |

Every backend also takes `api_key`, `model`, `base_url`, `path`, `timeout`,
`max_retries`, `backoff`, `max_retry_wait`, and `transport` arguments.
`max_retries` must be a non-negative integer; zero disables retries. `backoff`
must be a finite non-negative number of seconds; zero permits immediate retries
unless `Retry-After` requests a wait. Invalid settings raise `DecisionError`
before any request is sent. Use `base_url` and `path` for a gateway
that serves Jev elsewhere, for example `path="/v1/decisions"` with
`model="typesafe/jev"`. Request timeout (408), rate-limit (429), server (5xx), connection and HTTP protocol errors are
retried with exponential backoff (2 retries by default). When the provider sends a
`Retry-After` header (seconds or an HTTP date), the client waits at least that long
before retrying. A provider that asks for more than `max_retry_wait` seconds (60 by
default) fails the request at once with `APIError`, whose `retry_after` attribute
carries the requested wait, instead of blocking the caller. Other HTTP errors are
raised as `APIError` immediately. `transport` is any callable
`(url, headers, body_bytes, timeout) -> dict`, which tests use to replace the
network.

Remote `base_url` values require HTTPS. HTTP is accepted only for `localhost`
or a literal loopback IP address (IPv4 or IPv6). Credentials, query strings and
fragments in the base URL are rejected with `QuestionError`. Authenticated POSTs
never follow redirects: every 3xx response raises a non-retryable `APIError`.
Custom transports must enforce equivalent credential protection themselves.

The structured state can be text, a JSON object, or a list of non-empty strings. Jev
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
without sending it, so it needs no API key; the state is validated first either
way. The decision is printed as one line of JSON, an answer record (see
[Answer records and verification](#answer-records-and-verification)). Exit codes: 0 for success, 1 for a result
containing refusals, a provider or response error, or a response that cannot be recorded as
canonical JSON, 2 for invalid input (questions, state, or a `--timeout` that is
not a positive number of seconds).

From the repository root, `make jev-test` runs the tests and
`make jev-dry-run` prints the example request for both backends.

## Answer records and verification

`jev-decision` prints a **schema 2** answer record by default (`--schema-version 1` prints the
earlier typed-answers-only record). Besides the typed answers, `backend`, `model`, `id`, `usage`
and `produced_by`, a schema 2 record embeds:

- `questions`: the question definitions in Jev's question map form (`type`, `instructions`,
  `criteria`), normalized (no `predicate` alias, no extra keys);
- `response`: the raw provider response exactly as received and parsed from JSON;
- `record_sha256`: lowercase hex SHA-256 of the [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)
  (JCS) canonical form of the whole record **without the `record_sha256` member**. It therefore
  covers every other field. The printed line is that canonical form.

The state text is not embedded; it may be sensitive and re-parsing does not need it. JCS writes `2.0`
as `2` and sorts object members, so the digest depends on neither the integer/float distinction nor
member order; score levels stay ordered because they are a list. A response containing integers
beyond 2^53-1 or non-finite numbers cannot be recorded canonically, and `jev-decision` then exits 1.

```bash
# Live provider call: needs TYPESAFE_API_KEY (or --backend openai with OPENAI_API_KEY)
python3 -m jevdecision --questions examples/support-ticket.json --state "My payouts are failing." > answer.json
jev-decision-verify answer.json            # python3 -m jevdecision.verify answer.json
# Without a key, verify a committed record instead
jev-decision-verify conformance/valid/answer-v2-jev.json
```

`jev-decision-verify` re-parses the embedded response with the embedded question definitions (the
same parser the SDK uses), compares the typed answers and refusals, the response `id`, `usage` and
`model` with the recorded ones, and recomputes `record_sha256`. It prints `PATH: verified`,
`PATH: mismatch: <fields>` or `PATH: cannot verify: <reason>` (stderr) for each argument.

`jev-decision-verify --evaluation DIR` checks an output directory of `jev-decision-eval`:

1. every file listed in `provenance.json` `outputs` is hashed byte for byte and compared;
2. the retained `responses.jsonl` is re-scored with the retained `questions.json`, the retained
   `requirements.json` (when the run had one), and the labels recorded in `cases.jsonl`, using the same
   evaluation code; the recomputed report must equal `evaluation.json` and the recomputed rows must
   equal `cases.jsonl`. Nothing is sent to a provider;
3. the `questions.json` and `requirements.json` copies must match the input hashes in `provenance.json`.

Metrics use `math.log` and `NormalDist.inv_cdf`, whose last digits can differ between platform math
libraries, so the re-scored metric floats (including each requirement's `value`) match `evaluation.json`
within a relative 1e-9 (absolute 1e-12 where the recomputed value is exactly 0). Everything else is exact:
requirement bounds, counts, strings, booleans, statuses, the rows of `cases.jsonl`, and every file hash.
Answer record verification is exact: the only arithmetic on recorded floats is addition,
multiplication and division, which are bit-portable. The committed conformance vectors are generated on one
platform and verified on others in CI. `jev-decision-eval` itself is unchanged: it writes whatever the
local math library computes, and its byte-for-byte reproducibility claim holds for the Python versions
named under Limitations, not across platforms.

Runs from 0.1.0 did not retain `questions.json` and `requirements.json`; pass the original files with
`--questions FILE` and `--requirements FILE` (their hashes must match `provenance.json`); the same
float tolerance applies to those directories. A failed
live request has no response to re-derive its error message from, so that message is taken from
`evaluation.json` (it must be a string, one per case, else the directory is malformed, exit 2). It and the
requested `model` name used when no response names one are the only values the re-scoring takes from the
record instead of recomputing. Case states and the supplied responses file are not retained and are not re-checked.

Output directories contain the question and requirement text verbatim (`questions.json`,
`requirements.json`), and `responses.jsonl` holds raw provider responses, so treat them as sensitive as
the inputs. `cases.jsonl` holds case ids, expected and predicted answers, not the case states.

| Exit | Meaning |
|---|---|
| 0 | every argument verified |
| 1 | mismatch: a field, response byte or retained file differs from what was recorded or re-derived (including a missing retained file) |
| 2 | malformed or unreadable input, duplicate object keys, non-finite numbers, unsupported schema, or an unverifiable record |

**Schema 1 answer records** (written by 0.1.0) stay readable but exit 2: they embed neither
questions nor the response, so there is nothing to re-derive ("schema 1 cannot be verified").
Verification checks that a record is internally consistent under this implementation; it does not
authenticate who produced the response or prove that a provider sent it, and a record whose content and
digest are rewritten consistently passes whenever its response still parses to its answers.

## Signed records

A digest is recomputable by anyone who edits a record. A signature binds the record file to a secret
key (HMAC) or to a signer identity (Sigstore), so a record edited and re-hashed fails
`--require-signature`. The signed subject is the SHA-256 of the **exact bytes of the file** (re-formatting
it breaks the signature), wrapped in an in-toto Statement v1 inside a DSSE envelope. The predicate type is
`https://github.com/BichengWang/ai-decision-system/predicate/jevdecision/<answer|provenance>/v<N>` with
predicate `{"schema": "<the schema $id>"}`, so a signature for one record type or schema version cannot
vouch for another. For an evaluation directory the signed file is `provenance.json`, which already pins
every other file by hash.

```bash
jev-decision --generate-key signing.key        # 32 random bytes as hex, mode 0600, never overwrites
jev-decision --questions q.json --state "..." --out answer.json --sign-key signing.key   # answer.json.dsse.json
jev-decision-verify answer.json --require-signature --key signing.key
jev-decision-eval --questions q.json --cases c.jsonl --responses r.jsonl --out run --sign-key signing.key
jev-decision-verify --evaluation run --require-signature --key signing.key   # run/provenance.json.dsse.json
```

`--sign-key` on `jev-decision` needs `--out` (the signature covers the written file; the record goes to
that file instead of stdout, and neither `--out` nor its envelope may already exist). The key is read before
any request or output, so a bad key exits 2 and leaves nothing behind. The envelope is `FILE.dsse.json` next to
the file; `--signature ENVELOPE` selects another. Without `--require-signature`, `jev-decision-verify`
behaves exactly as before and ignores envelopes. With it the signature is checked first, on the bytes read
once, and then the normal verification runs (for an evaluation directory: signature of `provenance.json`,
then the file hashes, then re-scoring).

| Situation | Exit |
| --- | --- |
| Unsigned (no envelope), wrong key, record edited and re-hashed, wrong predicate type, malformed envelope, or Sigstore rejection | 1 |
| Missing, short or non-hex key file; `cosign` not installed; conflicting or incomplete flags | 2 |

**Sigstore.** `jev-decision-verify RECORD --predicate-out pred.json` (or `--evaluation DIR --predicate-out
pred.json`) writes the predicate and prints its type without verifying anything. Sign with an external
`cosign`, for example keyless in GitHub Actions (`permissions: id-token: write`):

```bash
cosign attest-blob --yes --predicate pred.json --type "$PREDICATE_TYPE" \
  --bundle answer.json.sigstore.json answer.json
jev-decision-verify answer.json --require-signature --sigstore-bundle answer.json.sigstore.json \
  --certificate-identity "$SIGNER_IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Verification shells out to `cosign verify-blob-attestation`; the package never signs with Sigstore and has no
dependency on it. Each signed
file is read once: the signature (HMAC or Sigstore), parsing and every later check use those bytes, and `cosign`
is given private 0600 copies of the file and bundle in a temporary directory rather than the original paths, so
swapping a file while it is being verified cannot make one file's signature vouch for another's content. The
certificate identity includes the signing ref (`https://github.com/OWNER/REPO/.github/workflows/WORKFLOW.yml@refs/heads/main`),
so verifying a record signed on another ref or workflow needs that exact identity. CI exercises this keylessly in a `sigstore` job (skipped for fork and Dependabot pull
requests, which get no OIDC token).

**Key handling.** Generate with `--generate-key` (mode 0600, no overwrite); keep keys outside the
repository and out of backups you do not trust, because anyone who can read the key can sign anything. To
rotate, make a new key (a new `hmac-sha256:` key id, printed by `--generate-key` and written in each
envelope) and keep old keys to verify old envelopes. HMAC proves the signer held the shared secret; it is
not an identity, and every verifier holds the same key and so could also sign. Keyless Sigstore signing
writes the signer identity and the record digest to the public Rekor transparency log permanently, so do not
use it for private decisions. A signature shows who attested to the file, not that the provider response or
labels inside it are authentic. Synthetic records signed in CI are software checks, not adoption evidence.

## Evaluating a decision model

Measure the model on labeled cases before software acts on its answers.
`jevdecision.evaluation` scores every question against the expected answers and
can gate the result on thresholds you set.

A case file is JSON Lines with a state and the expected answer to some or all
questions: `true` or `false` for a `noul`, a label for a `choice`, and a level
(or its index) for a `score`:

```json
{"id": "t02", "state": "I was charged twice for March. Please refund the duplicate charge.",
 "labels": {"refund": true, "department": "billing", "frustration": "Frustrated"}}
```

| Type | Metrics |
|---|---|
| `noul` | `accuracy` (at probability 0.5), `brier`, `log_loss`, `ece`, `base_rate`, `mean_probability` |
| `choice` | `accuracy`, `brier` (summed over labels), `log_loss`, `ece` (probability of the chosen label against correctness), a confusion matrix |
| `score` | `accuracy` (nearest level), `within_one`, `mae` (in level steps), `brier`, `log_loss`, `ece` (nearest level probability) |

Every question also reports `n`, the number of cases that label it, and
`accuracy_lower` and `accuracy_upper`, the 95% Wilson score interval for
`accuracy`. With 12 cases, 11 correct answers give an accuracy of 0.917 but an
interval of [0.646, 0.985], so a gate on `accuracy_lower` asks for enough cases as
well as a high hit rate. `ece` is the
expected calibration error over ten equal-width probability bins. Log loss clips
probabilities to [1e-6, 1 - 1e-6].

Every question also reports `refusals` and `refusal_rate` among its labeled,
parsed results. Refusals count in `n`, accuracy and its Wilson interval as
incorrect, and make probability metrics unmeasured. Score MAE and within-one
are also unmeasured if any result refuses. Request/parse errors remain separate.

Missing choice probabilities do not exclude otherwise valid answers from `n`,
accuracy, its interval, or the confusion matrix. Probability metrics require the
inputs they measure on **every scored case**, not a selectively observed subset:

- Brier score requires a reported probability for every option.
- Log loss requires the expected label's reported probability.
- ECE requires the chosen label's reported probability; provider `confidence`
  is not substituted for that probability.

If any scored case lacks a metric's required inputs, that metric is `null` in
JSON and `unmeasured` in the report. A requirement on it fails. Per-case records
retain the prediction and a null chosen probability, and raw responses remain
available for replay. Re-evaluating older responses with missing probabilities
may therefore fail gates that previously scored fabricated values. Complete
probability responses retain their previous scores. Score Brier requires every
level probability, log loss requires the expected level probability, and ECE
requires the nearest level probability on every case. Missing inputs yield
`null` and fail metric requirements, as for choices.

A requirement file supplies explicit question metric bounds, each a `min` or
`max`. The overall JSON field is `status` (not a boolean `pass`):

- `PASS`: at least one valid question metric bound was supplied, and all checks pass.
- `FAIL`: an explicit metric bound or the error-rate check fails.
- `UNGATED`: all checks pass but there are no question metric bounds. Omitting
  `--require`, `{}`, `{"max_error_rate": 0}`, and `{"questions": {}}` are all
  ungated, not model-quality validation.

`max_error_rate` (default 0) bounds the share of cases whose request or response
failed; it alone is not a question gate. A failed case counts as an error, never
as a wrong answer. A bound on an unmeasured metric fails. A valid question bound
means a finite numeric `min`/`max` on a supported metric; it does not mean the
threshold is scientifically adequate. For example, an `n`-only gate checks sample
count, not accuracy. Select meaningful thresholds for the decision being made.
Malformed specs (including JSON `null`, `false`, arrays, empty per-question metric
objects and empty bounds) are invalid input, not ungated runs. In the Python
`evaluate()` API, `None` means no requirement spec. Individual requirement rows
retain boolean `pass` values; the overall report does not.

```json
{"max_error_rate": 0.0,
 "questions": {"refund": {"n": {"min": 10}, "accuracy_lower": {"min": 0.8}, "brier": {"max": 0.1}}}}
```

```bash
# Replay supplied responses: no API key; origin remains unverified
python3 -m jevdecision.evaluation --questions examples/support-ticket.json \
    --cases examples/support-ticket-cases.jsonl \
    --responses examples/support-ticket-responses.jsonl \
    --require examples/support-ticket-requirements.json --out eval-run

# Ask the provider live (needs its API key); no question bounds means UNGATED
python3 -m jevdecision.evaluation --questions examples/support-ticket.json \
    --cases examples/support-ticket-cases.jsonl --backend openai --out live-run
```

`--out` must be new or empty. Files are prepared in a sibling `.NAME-*` staging
directory, then published with `os.replace` after all summaries are complete.
Live runs print the staging path and append/fsync each completed response and
case result before requesting the next case, including malformed JSON responses
that parsed as JSON but failed answer validation. Interrupted runs retain these
JSONL files for inspection and replay; the target remains available for a rerun.
A 401/403 stops immediately with exit 2 and retains progress without a final report.
There is no automatic resume; replay the saved responses with the original cases
(missing responses count as errors), or start a new live run.

Each run writes `evaluation.json` (canonical JSON),
a readable `EVALUATION.md`, `responses.jsonl` with the supplied replay responses
or responses obtained through the live backend, and `cases.jsonl` with one row
per case: each labeled question's expected and predicted answer (with probability
or score) and whether it was correct, or the case's error. `EVALUATION.md` lists
the first 20 incorrect answers. Exported responses can be passed as `--responses`
to re-score without calling a provider. The bundled replay produces byte-identical
`evaluation.json`, `provenance.json`,
`responses.jsonl` and `cases.jsonl` on Python 3.11 and 3.13; live-to-replay
metrics remain the same, but the report's `source` changes.

Answer records use `schema_version: 2` (1 from 0.1.0 remains readable but cannot be verified);
evaluation and provenance records use `schema_version: 2`, or 3 for runs that fit or apply a calibration
([below](#calibrating-the-probabilities)). They carry `produced_by: {"name": "jevdecision", "version": "0.2.0"}`.
Raw provider response replay remains compatible with existing unversioned fixtures.
JSON records use sorted keys, compact separators and UTF-8 without ASCII escaping;
SHA-256 digests are lowercase hexadecimal. JSONL rows use the same encoding.

CLI runs also write a separate deterministic `provenance.json`:

- `inputs` records SHA-256 of the exact question, case, requirement and response
  file bytes read for the run, with `null` for absent optional inputs.
- `response_mode` is `live` or `replay`. Replay origin is explicitly **unverified**:
  files may be hand-written, and their `model` fields do not authenticate provider output.
- `outputs` records SHA-256 of `evaluation.json`, `EVALUATION.md`, `responses.jsonl`
  and `cases.jsonl`, plus `questions.json` and `requirements.json`: exact copies of the question
  file and of the requirement file (when `--require` was given) that `jev-decision-verify --evaluation`
  needs to re-score the run. The manifest does not hash itself, include timestamps, paths,
  headers or credentials, or enter the metric records. Whitespace-only input
  changes can therefore change provenance without changing `evaluation.json`.

Hashes identify bytes, not authenticity, reviewer independence or model quality.
Raw responses and labeled cases may contain sensitive material; inspect them
before sharing. `--backend` names the response format to replay (`jev` by default).
The CLI and Markdown display the same overall status. Exit codes: **0** for PASS,
**1** for FAIL or a provider that cannot be used, **2** for invalid input/unreadable files or live 401/403 (authentication failures
retain staged progress; invalid input produces no final artifacts), and **3** for UNGATED.

The example responses are hand-written in Jev's response format to show the
workflow. They are not output from Jev or any other model, and the example
report says nothing about any model's quality.

From the repository root, `make jev-eval` runs the example into a temporary directory.

### Calibrating the probabilities

A low `ece` is not something a provider promises: a model that says 0.95 and is right 70% of the time
makes any threshold on its confidence (decision-control's `min_probability`, Jev's `min_confidence`)
meaningless. Fit a monotone map per question on one labeled set and measure it on another:

```bash
# Fit on one labeled set: writes fit-run/calibration.json (isotonic or platt)
python3 -m jevdecision.evaluation --questions examples/support-ticket.json \
    --cases fit-cases.jsonl --responses fit-responses.jsonl --fit-calibration platt --out fit-run

# Apply it to held-out cases; requirements may bound calibrated_* metrics
python3 -m jevdecision.evaluation --questions examples/support-ticket.json \
    --cases held-out-cases.jsonl --responses held-out-responses.jsonl \
    --calibration fit-run/calibration.json --require calibrated-requirements.json --out held-out-run
```

| Type | Calibrated probability | Metrics added by `--calibration` |
|---|---|---|
| `noul` | probability of yes, against the label | `calibrated_brier`, `calibrated_log_loss`, `calibrated_ece` |
| `choice`, `score` | probability of the chosen answer, against its correctness | `calibrated_ece` |

- `isotonic` is pool-adjacent-violators: a nondecreasing step map, interpolated between steps. It can
  return 0 or 1 and needs a few hundred cases before its steps mean much.
- `platt` fits `sigmoid(a * logit(p) + b)` on Platt's smoothed targets: two parameters, so it suits
  small sets.
- Refused answers are left out of the fit. A question whose answers lack the probability its `ece`
  needs is not calibrated, and a held-out refusal makes its calibrated metrics unmeasured, as for the
  raw ones.
- The fitting run reports no calibrated metrics: measured on the cases they were fitted on, they would
  look better than they are. `--calibration` refuses a file fitted on any case id of the evaluation
  (exit 2), and requirements on `calibrated_*` fail in a run without `--calibration`. Calibration can
  make held-out metrics worse; that result is the reason to measure it.

`calibration.json` (schema 1, compact sorted-key JSON) holds the method, one map per question with its
`n` and positive count, and `fitted_on`: the SHA-256 of the fitting run's `cases.jsonl` and
`responses.jsonl` and its case ids. Both runs write `evaluation.json` and `provenance.json` schema 3:
`calibration` names the role (`fitted` or `applied`), the method and the SHA-256 of `calibration.json`,
which provenance lists as an output; the applying run also records it as input `calibration` and keeps
a copy. `jev-decision-verify --evaluation` refits a fitted calibration from the directory (isotonic maps
must match exactly; a Platt map must give the same calibrated probability within 1e-9 at every probability
it was fitted on, since its parameters move with last-digit math-library differences) and re-applies an
applied one. The two directories are linked
by hash: the applying run's `inputs.calibration` equals the fitting run's `outputs["calibration.json"]`.

To apply a calibration where the decision is made:

```python
from pathlib import Path
from jevdecision.calibration import load

calibration = load(Path("fit-run/calibration.json").read_bytes())
p = calibration.calibrate("refund", decision["refund"].probability)  # then compare p with your threshold
```

## JSON Schemas and conformance vectors

Every record version the readers accept has a JSON Schema (draft 2020-12), shipped in the wheel as
package data under `jevdecision/schema/`: `answer.v1.json`, `answer.v2.json`, `evaluation.v2.json`,
`evaluation.v3.json`, `provenance.v2.json`, `provenance.v3.json` and `calibration.v1.json`. Each `$id` is
`https://github.com/BichengWang/ai-decision-system/schema/jevdecision/<file>` (a stable name, not a URL
that must resolve) and its `$comment` states the canonicalization and what each digest covers: RFC 8785
for `record_sha256` in answer schema 2; none for provenance, whose digests are SHA-256 of exact file
bytes; `evaluation.json` is written as compact sorted-key JSON and carries no digest of its own. Schemas
check shape only; semantic checks are `jev-decision-verify`'s job.

`conformance/` holds vectors other implementations can run against: `valid/`, `tampered/` and `invalid/`
records and evaluation directories, and `manifest.json` listing for each one the command to run
(`jev-decision-verify {path}` or `--evaluation {path}`), the expected exit code (0, 1 or 2), the schema
each document must (or must not) validate against, and every digest it carries: the JCS canonical bytes
for `record_sha256` (`*.canonical`) and `bytes` digests of the retained files for provenance. All vectors
are produced by `python3 conformance/generate.py` from the bundled examples and hand-written responses
(synthetic, not provider output). `python3 conformance/generate.py --check` compares the committed tree
with a fresh generation without writing anything and exits 1, listing the differing paths on stderr, if
they differ; `--out DIR` writes the tree under `DIR` instead (with `--check`, compares `DIR`); any other
argument exits 2. Without arguments the script rewrites the committed tree. The unit tests assert the same
equality with the same comparison. For evaluation directories only
the platform difference of metric floats is allowed: `evaluation.json` is compared with the verifier's 1e-9
tolerance (the vectors were generated on macOS and CI on Linux produced a different `evaluation.json`),
on valid vectors `EVALUATION.md` must equal the fresh rendering apart from its digest line and exactly the
rendering of the committed report and cases; on tampered and invalid vectors it must equal its source
vector's Markdown plus the named edit, byte for byte, in both the committed and the fresh tree; and the two hashes in `provenance.json` that follow from
`evaluation.json` and `EVALUATION.md` are checked against the committed files' bytes. Everything else is
byte-exact. The tests also run the verifier over every vector and recompute every digest. After changing a record format or the
package version, rerun the generator and commit the result. With the test-only `jsonschema` pin from
`requirements-dev.txt` installed (CI does), the tests also validate every manifest document and the
records the commands produce against the schemas; without it those tests skip.

## Limitations

- Both provider APIs are new. The Jev request and response shapes follow
  TypeSafe's published examples. The OpenAI Decisions API is in public beta, so
  the parser accepts both its object and its list answer layouts. Recheck the
  field mapping against the provider references before you depend on it in
  production.
- Image inputs and per-request options beyond the model are not modeled yet.
- Calibration maps one probability per question; there is no conformal or abstention-coverage
  guarantee, and a map fitted on one period or population says nothing about another.
- Unit tests use recorded response shapes and never call a provider.
- Only accuracy carries a confidence interval. Brier, log loss, calibration
  error and MAE are point estimates, which are noisy with a few dozen cases, so set
  `n` minimums that match the thresholds you rely on.
- A live evaluation sends one request per case, sequentially.
- Float sums use `math.fsum` for correctly rounded accumulation. The bundled replay
  has identical bytes and hashes on Python 3.11 and 3.13; this check is not a
  guarantee for every platform, math library or future algorithm version.

## Local software verification

Release checks cover refusals, unknown probabilities, malformed distributions,
HTTP retries and redirect protection, interrupted live progress, authentication
stops and atomic publication. Tests use synthetic provider responses and a local
HTTP fixture. Fresh wheel installs exercise both backend dry runs and the gated
12-case replay example; exported responses reproduce the evaluation bytes across
Python 3.11 and 3.13. These checks are not live-provider calls, calibration results,
or deployment-safety evidence.
