# Experiment gate (`expgate`)

Replayable decision records for AI-assisted go/no-go decisions. This small,
deterministic workflow handles the step that follows offline release gates:
deciding whether a real-time decision model that is **already in an online A/B
test** should be shipped, held for more data, or rolled back.

It reads the aggregate summary an experimentation platform exports (units per
arm, successes for proportion metrics, mean and standard deviation for mean
metrics) and writes a decision record. It uses only the Python standard library,
so it has no dependencies and no lockfile.

## Decision rules

Rules are applied in order; the first match wins.

| Decision | When |
|---|---|
| `INVALID` | Sample-ratio mismatch: the observed assignment split differs from the design (chi-square, `srm_alpha`, default 0.001). No effect estimate is trusted. |
| `ROLLBACK` | The primary metric is significantly worse, or a guardrail is significantly worse **and** its point degradation exceeds its margin. |
| `SHIP` | The primary metric is significantly better **and** every guardrail is shown non-inferior (its upper degradation bound is below its margin). |
| `HOLD` | Anything else: the experiment is inconclusive. |

The primary metric uses a one-sided test at `alpha` (default 0.05). Guardrail
bounds are one-sided and Bonferroni-adjusted across guardrails. Proportions use
the unpooled Wald standard error; means use the Welch standard error; ratio
metrics use a delta-method standard error (see [Ratio metrics](#ratio-metrics)).
All are large-sample approximations. A metric can optionally be estimated with CUPED
regression adjustment, which narrows its interval (see
[Variance reduction](#variance-reduction-cuped)). A test that is checked while it
runs can replace every bound with an always-valid confidence sequence (see
[Sequential monitoring](#sequential-monitoring)).

Every metric reports `mde = (z + z_power) * se`, using its critical value,
observed standard error, and `policy.power` (default 0.8). For fixed-horizon
analysis, `mde_basis` is `fixed_horizon_normal_approximation`: approximate
single-metric detectability at the current sample size, not a guarantee that all
guardrails pass or the experiment ships. For sequential analysis it is
`current_look_normal_approximation`: a sensitivity estimate for this look,
**not a guarantee of power under repeated looks or a stopping rule**. The formula
and thresholds are unchanged. A zero standard error makes the metric inconclusive;
its numerical MDE of zero is not evidence of detectability.

## Quick start

Install the published 0.1.0 package with Python 3.11 or later:

```bash
pip install expgate
experiment-gate --input examples/offer-ranker-v2.json --out review-run --require-ship
experiment-gate-verify review-run/decision.json
```

Features documented on `main` beyond 0.1.0 (schema 3, signing and the GrowthBook
importer) ship in 0.2.0, which is not yet published. Until then, install from
source in this directory:

```bash
pip install .
```

The examples live in this repository; supply your own exported summary after
installation. From this directory:

```bash
python3 -m unittest discover -s tests
python3 -m expgate.run --all-scenarios --out review-run
python3 -m expgate.run --input examples/offer-ranker-v2.json --out review-run/example --require-ship
```

`python -m expgate` is also supported; `python -m expgate.run` remains available.

`--out` must be new or empty. Each evaluation writes `decision.json` (sorted
keys; byte-identical across runs for the same input) and a readable
`DECISION.md`. `--input` takes several summaries at once (`--input exports/*.json`);
each record then goes to `--out/<experiment>/`, so every summary must name its
`experiment`, and the names must be distinct (ignoring case and Unicode normalization) and usable as a
directory name. Every summary is read and evaluated before anything is written,
so one invalid file leaves no partial records. The entire run is written into a
staging directory next to `--out` and atomically published with `os.replace`; a
write failure leaves the target untouched and the run can be retried. `--require-ship` exits 1 unless every decision is `SHIP`, so the
command can gate a promotion job.

`--from growthbook results.json --mapping mapping.json` converts a GrowthBook results
export instead of reading a summary (see [Importing a GrowthBook export](#importing-a-growthbook-export)).

| Exit | Evaluation CLI | Verification CLI |
|---|---|---|
| 0 | Records written; required SHIP condition met, if requested | All records verified |
| 1 | Completed, but `--require-ship` was not met | Hash or replay content mismatch; under `--require-signature`, a missing, wrong or non-matching signature |
| 2 | Invalid input, usage, unreadable file, bad `--sign-key` file, or output failure | Unreadable/invalid record, usage, bad key file, or unsupported/legacy schema |

Without `--require-ship`, writing a HOLD, ROLLBACK, or INVALID decision succeeds
with exit 0; inspect the record or request the gate explicitly.

From the repository root, `make expgate-test` and
`make expgate-run EXPGATE_OUT=/abs/new/dir` run the same commands.

## Input format

See [`examples/offer-ranker-v2.json`](examples/offer-ranker-v2.json). Exactly
one metric has `"role": "primary"`; every other metric is a `"guardrail"` with a
non-negative `margin` in the metric's own units. `direction` states which way is
better (`increase` or `decrease`). `policy` and `assignment` are optional;
`policy.sequential` turns on sequential monitoring.

The summary is validated before any statistic is computed: counts must be
integers within range, means, standard deviations and guardrail margins must be finite,
`alpha`, `srm_alpha`, `power` and `expected_treatment_share` must lie in (0, 1), and
`policy.sequential.planned_units` must be an integer of at least 2. `experiment`,
when present, must be a non-empty string. The allowed top-level keys are
`experiment`, `description`, `seed` (synthetic metadata), `source` (provenance of an
[imported](#importing-a-growthbook-export) summary, schema 3 only), `metrics`, `arms`,
`policy`, and `assignment`. Metric specs allow only `type`, `role`, `direction`,
and `margin`; arm metrics must all be declared in the specs. Unknown keys at
the summary top level, in metric specs, in `policy`,
`policy.sequential`, `assignment`, an arm's metric statistics, and a `covariate`
are rejected rather than ignored, so a misspelled setting such as `alpah` cannot
silently fall back to its default.
Any violation exits 2 with the offending field named, so malformed input is
never mistaken for a `--require-ship` refusal (exit 1). Every metric with zero
standard error (including zero-event or all-event proportions, zero-variance
means/ratios, and perfectly adjusted CUPED outcomes) is `INCONCLUSIVE`; it can
neither establish significant improvement/harm nor non-inferiority. A zero-error
primary or guardrail therefore prevents SHIP.

## Decision records and offline verification

`decision.json` carries the decision, reasons, policy, sample-ratio, metrics, and
`expgate_version`, plus integer `schema_version`, `produced_by:
{"name": "expgate", "version": "0.2.0"}`, the full parsed `input`, and `input_sha256`.
New records use **schema 3**: `input_sha256` is the lowercase SHA-256 of the
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) (JCS) canonical form of `input`, so
other languages can reproduce it byte for byte (`expgate/jcs.py`; integral floats
such as `2.0` become `2`, so the int/float distinction is not part of the digest).
**Schema 2** records (python-json-v1: `json.dumps(input, sort_keys=True,
separators=(",", ":"), ensure_ascii=False)` as UTF-8) remain verifiable under their
original rules. `DECISION.md` shows the SHA-256 of the actual `decision.json` bytes
(including formatting), which is a different digest.

```bash
python -m expgate.verify review-run/decision.json
experiment-gate-verify review-run/*/decision.json
```

Verification recomputes the input digest under the record's schema and calls
`evaluate` with the running version and the record's schema. It names mismatches in
the decision, reasons, metrics, experiment, policy, sample-ratio, and sequential
fields. It needs no network access. Missing `schema_version` means schema 1: existing
JSON remains readable, but lacks the embedded input needed for verification and
exits 2 with an explanation, as does any schema other than 2 or 3. Future versions may
produce different replay results; a mismatch is reported, not hidden. Hashes detect
changes, not forgery or authenticity: someone who rewrites the input and recomputes
the report can produce a consistent record.

| | Schema 2 (0.1.0) | Schema 3 |
|---|---|---|
| Input digest | SHA-256 of python-json-v1 | SHA-256 of RFC 8785 |
| Tail formulas | `2 * (1 - cdf)`, `inv_cdf(1 - alpha)` (the sample-ratio p-value is exactly 0.0 beyond about 8.3 standard deviations) | `erfc`, `-inv_cdf(alpha)` (`exact_tail=True`; one mapping, `records.EXACT_TAIL`) |
| Parsing | lenient (a repeated key keeps its last value; `NaN` accepted) | duplicate keys, `NaN`/`Infinity`, integers beyond 2^53-1 and lone surrogates exit 2 |

Both schemas share one replay comparison. Only computed statistics agree within a relative 1e-9
(absolute 1e-12 where the replayed value is exactly 0): `sample_ratio.p_value` and, per metric row, `diff`,
`se`, `improvement`, `improvement_bounds`, `z`, `mde` and the CUPED `adjustment` numbers. Everything else
compares exactly: inputs, copied policy values and margins, expected shares, counts and units (by value,
whatever their `2` or `2.0` spelling), strings, booleans, dispositions and structure, and the input
digest stays a byte comparison. A non-finite statistic must be identical (same infinity, or NaN on
both sides); a finite/non-finite pair never agrees. Schema 3 also checks the whole document with RFC 8785
canonicalization, so an ignored member holding `1e999`, an integer beyond 2^53-1 or a lone surrogate exits 2,
and `evaluate` refuses (exit 2 in `experiment-gate`) a schema-3 input whose statistics overflow to infinity.
The tolerance exists because `log`, `exp`, `erf` and the normal quantile come
from the platform libm, so a bit-exact replay fails across platforms. Strings that embed floats
(`reasons`) are compared exactly and print four significant digits (`:.4g`) or three (`:.2e`),
far coarser than 1e-9, so they differ across platforms only if a value sits within about 1e-9 of
a rounding boundary. A sequential record is the most exposed case (the mixing variance comes from
a search on a flat optimum; one-ulp differences move it by about 1e-9 relative); the vectors for
both schemas include one.

The public API exports `evaluate`, `verify_record`, and `__version__` from
`expgate`. `evaluate(summary)` returns a schema-3 report; `schema_version=2` produces
the 0.1.0 form (digest and tail formulas). `verify_record(record)` returns a list of mismatched field names and
raises `ValueError` for invalid/unsupported records; it cannot see duplicate keys,
which only the file parser (`expgate.verify.load_record`) rejects.

### JSON Schemas and conformance vectors

`expgate/schema/decision.v2.json` and `decision.v3.json` (JSON Schema 2020-12) ship
as package data; each `$comment` states the canonicalization and the digested
fields (`/input` only). They are as strict as the verifier: objects that the
verifier rejects for unknown keys (`input` and its nested settings, metric specs and
statistics, `policy`, `sample_ratio`, metric rows) are closed, top-level members
the verifier ignores are allowed. Rules relating several fields (one primary metric,
`successes <= units`, every derived field equal to the replay) are the verifier's
job. There is no schema 1 file: a schema-1 record is any JSON without
`schema_version`, which cannot be pinned down, and the verifier exits 2 for it anyway.

`conformance/` holds the vectors other implementations can test against:
`valid/` (exit 0; each with the exact canonical bytes of its input in
`*.input.canonical`), `tampered/` (exit 1: input edited with a stale digest, input
edited and re-digested, decision edited, metric edited, digest computed with the
other schema's canonicalization) and `invalid/` (exit 2: truncated JSON, unknown
schema, missing input, `NaN`, schema 1, and for schema 3 duplicate keys and an
out-of-range integer, including one in an ignored member). `manifest.json` lists every vector with its expected verifier
exit code, schema validity and digests. Schema 2 has no duplicate-key vector because
its reader accepts them. The `jcs-edge` vectors use one input under both schemas
(`40.0`-style floats, `1e-7`, escapes, members whose UTF-16 order differs from code point
order), so the two digests differ. `python conformance/generate.py` regenerates the
tree deterministically (`--check` compares); a unit test fails if it drifts, for
example after a version bump (it tolerates last-digit differences in computed statistics, so a tree
generated on macOS passes on Linux). The vectors are committed from macOS and verified by Linux CI.
The vectors are synthetic and demonstrate the format,
not adoption.

Development checks use `pip install jsonschema==4.26.0` (never a runtime dependency):
`python tests/schema_validation.py review-run/*/decision.json` validates records, and the
unit tests skip the schema checks when it is absent.

### Signed records

A digest is recomputable by anyone who edits a record: change the input, re-derive the report, write
a new `input_sha256`, and `experiment-gate-verify` passes. A signature binds the **exact bytes of
`decision.json`** to a secret key (HMAC) or to a signer identity (Sigstore). The signed subject is the
SHA-256 of those bytes, so reformatting the file also breaks the signature. It is an in-toto Statement
v1 in a DSSE envelope; the predicate type is
`https://github.com/BichengWang/ai-decision-system/predicate/expgate/decision/v<N>` for the record's
`schema_version` `N` (2 or 3), with predicate `{"schema": "<the schema $id>"}`, so a signature over one
record type or schema version cannot vouch for another.

```bash
experiment-gate keygen signing.key             # 32 random bytes as hex, mode 0600, never overwrites
experiment-gate --all-scenarios --out review-run --sign-key signing.key   # review-run/*/decision.json.dsse.json
experiment-gate-verify review-run/*/decision.json --require-signature --key signing.key
```

`--sign-key` (on `experiment-gate`, `python -m expgate.run` and `python -m expgate`) writes
`decision.json.dsse.json` next to every `decision.json`, one envelope per record, published with the
record in the same atomic step. The key is read before anything else, so a bad key exits 2 and writes
nothing. `--signature ENVELOPE` selects a different envelope (one record only). Without
`--require-signature`, the verifier behaves exactly as before and ignores envelopes. With it, the
file is read **once**; the signature is checked over those bytes, and the same bytes are then parsed and
replayed, so swapping the file between the check and the replay changes nothing. Every flag combination
that does not make sense (`--key` without `--require-signature`, both key and Sigstore flags, several
records with `--signature` or `--sigstore-bundle`) is a usage error, exit 2.

| Situation under `--require-signature` | Exit |
| --- | --- |
| Unsigned (no envelope or bundle), wrong key, record edited and re-hashed, wrong predicate type, malformed envelope, Sigstore rejection | 1 |
| Missing, short or non-hex key file, `cosign` not installed, schema 1 or unsupported record, malformed record, conflicting or incomplete flags | 2 |
| Signature valid, then the normal verification: agreement / mismatch | 0 / 1 |

**Sigstore.** `experiment-gate predicate --record decision.json --out pred.json` writes the predicate and
prints its type. Sign with an external `cosign` (this package never signs with Sigstore and has no
dependency on it), for example keylessly in GitHub Actions with `permissions: id-token: write`:

```bash
cosign attest-blob --yes --predicate pred.json --type "$PREDICATE_TYPE" \
  --bundle decision.sigstore.json decision.json
experiment-gate-verify decision.json --require-signature --sigstore-bundle decision.sigstore.json \
  --certificate-identity "$SIGNER_IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Verification shells out to `cosign verify-blob-attestation`, handing it a private mode-0600 copy of the
bytes already read (in a temporary directory), never the original path. The expected certificate
identity includes the signing ref, for example
`https://github.com/OWNER/REPO/.github/workflows/expgate-ci.yml@refs/heads/main`: a record signed on
another ref, or by another workflow, verifies only with exactly that identity. CI exercises this keylessly in the
`expgate sigstore attestation` job (skipped for fork and Dependabot pull requests, which get no OIDC
token) and asserts that an edited and re-derived record and a different identity both exit 1.

**Key handling.**
- *Generate and store:* `keygen` creates the key file with mode 0600 and refuses to overwrite it. Keep
  keys outside the repository and out of backups you do not trust; anyone who can read the key can sign.
- *Rotate:* make a new key (a new `hmac-sha256:` key id, printed by `keygen` and written in each
  envelope) and sign new records with it. Keep old keys to verify old envelopes. An envelope may carry
  several signatures; the verifier accepts it when one matches the supplied key.
- *What HMAC proves:* the signer held the shared secret. It is not an identity, and every verifier
  holds the same key and so could also sign. For an attributable identity use Sigstore.
- *Sigstore trade-off:* keyless signing writes the signer identity and the record digest to the public
  Rekor transparency log, permanently. Do not use it for private decisions.

A signature shows who attested to the file, not that the experiment summary behind it is true.
Signatures on synthetic scenario records made in CI are software checks, not adoption evidence.

## Bundled examples

All examples are hand-written schema demonstrations, not live-model,
calibration, adoption, or production evidence:

| Input | Demonstrates |
|---|---|
| `examples/offer-ranker-v2.json` | Proportion primary and proportion/mean guardrails |
| `examples/ratio.json` | Revenue per session with user-level numerator/denominator summaries |
| `examples/cuped.json` | Mean primary adjusted by one pre-assignment covariate |
| `examples/sequential.json` | An interim look toward 200,000 planned units |

```bash
experiment-gate --input examples/*.json --out example-records
experiment-gate-verify example-records/*/decision.json
```

## Importing a GrowthBook export

`experiment-gate --from growthbook results.json --mapping mapping.json --out review-run` converts
the experiment-results export of a [GrowthBook](https://www.growthbook.io/) experiment into an
expgate input, evaluates it under expgate's frozen rules, and writes a normal schema-3
record that `experiment-gate-verify` accepts. The importer reads a file you already have; it
opens no connection and adds no dependency. `--out`, `--require-ship` and the exit codes work as
for `--input`; a malformed or unsupported export, mapping file or option exits 2 with the
offending field named. One export per run.

Get the export from your instance with GrowthBook's documented REST endpoint (this call is yours,
not the package's; the 5.1.0 `openapi.yaml` calls it `getExperimentResults`):

```bash
curl -sS "$GROWTHBOOK_API/api/v1/experiments/$EXPERIMENT_ID/results" \
     -H "Authorization: Bearer $GROWTHBOOK_SECRET_KEY" -o results.json
```

Keep the bytes as they are. The record stores the SHA-256 of the file's exact bytes in
`input.source.export_sha256` (and `DECISION.md` shows it), and `input_sha256` covers it, so
`shasum -a 256 results.json` ties the record to the file it came from. A reformatted copy
of the same export has a different digest. The digest detects change; it does not show that the
export came from GrowthBook or that the numbers are right.

### Mapping file

The export names metrics by id and says which are goals and guardrails, but not whether a metric
is a proportion, a mean or a ratio, which direction is better (GrowthBook's `inverse` is not in
it), or how much a guardrail may degrade (GrowthBook has no non-inferiority margin). The mapping
file supplies those, keyed by the `metricId` in the export (types and `inverse` are in
`GET /api/v1/fact-metrics`):

```json
{
  "primary": "fact__abc123",
  "policy": {"alpha": 0.05, "srm_alpha": 0.001, "power": 0.8},
  "growthbook": {"alpha": 0.05, "srm_alpha": 0.001},
  "snapshot": {"expected_treatment_share": 0.5, "regression_adjustment": false},
  "metrics": {
    "fact__abc123": {"name": "purchase_rate", "type": "proportion", "direction": "increase"},
    "fact__def456": {"type": "mean", "direction": "decrease", "margin": 4.0}
  }
}
```

`snapshot` is required (below). `metrics` is required and must describe the primary metric and every guardrail of the export, and
only those (a stray id is an error, so a typo cannot silently drop a margin). `type` is
`proportion`, `mean` or `ratio`, `direction` is `increase` or `decrease`, a guardrail needs a
non-negative `margin` in the metric's own units and the primary takes none, `name` (default: the
export's `metricName`) is the metric's name in the record. `primary` is only needed when the export lists
several goal metrics; the other goals are then not imported. `policy` is copied into the expgate
input (`alpha`, `srm_alpha`, `power`; sequential monitoring is not available for imports).
`growthbook` states the significance levels GrowthBook was run with, used only for the reading
below; the export does not carry them and the defaults are GrowthBook's 0.05 and 0.001.

[`tests/fixtures/growthbook/mapping.json`](tests/fixtures/growthbook/mapping.json) is a complete
example.

### Field mapping

| GrowthBook export | expgate input | Notes |
|---|---|---|
| `experiment.trackingKey` (else `name`, `id`) | `experiment` | |
| `experiment.variations[0]`, `[1]` | `arms.control`, `arms.treatment` | The first variation is GrowthBook's baseline; exactly two are supported |
| `experiment.phases[result.phase].trafficSplit` | checked against `snapshot.expected_treatment_share` | The current weights may only contradict the asserted share, not establish it (below); the sample-ratio check uses the asserted share |
| `result.results[0].metrics[].variations[].users` | `arms.<arm>.units` | Must be the same for every imported metric |
| `result.settings.goals[]` | the `primary` metric | One goal, or `primary` in the mapping |
| `result.settings.guardrails[]` | `guardrail` metrics | Margin from the mapping |
| `result.settings.secondaryMetrics[]` | not imported | expgate has no secondary role |
| proportion: `numerator` | `successes` | Must be a whole number at most `users`; the export's `denominator` must be 0, `mean` must equal `numerator / users` and `stddev` that of a proportion, or the metric is probably not a proportion and the import exits 2 |
| mean: `mean`, `stddev` | `mean`, `sd` | `denominator` must be 0 and `mean` equal `numerator / users` |
| ratio: `numerator`, `denominator`, `mean`, `stddev` | numerator mean `numerator / users`, denominator mean `denominator / users`, `corr` 0, denominator `sd` 0, numerator `sd` `stddev * denominator mean` | The export has one per-unit delta-method standard deviation instead of the two spreads and their correlation. This encoding reproduces GrowthBook's variance under expgate's delta-method formula (up to floating-point rounding); it is not the real numerator and denominator spread |
| `result.settings.statsEngine`, `result.id`, `result.dateUpdated`, `experiment.id` | `source.stats_engine`, `snapshot_id`, `snapshot_updated`, `experiment_id` | Provenance only |
| the file's bytes | `source.export_sha256` | SHA-256, lowercase hex |
| mapping `snapshot` | `source.asserted` | Operator-asserted allocation share and "no regression adjustment"; not in the export (below) |
| `checks.srm`, `analyses[].pValue`, `chanceToBeatControl`, `percentChange` | `source.reading` | Read, never used for the decision |
| `ciLow`, `ciHigh`, `effectStandardError`, `risk`, relative effects | not imported | |

Exports the importer refuses (exit 2): not the `{experiment, result}` body of `getExperimentResults`;
an experiment that is not a `standard` two-variation test; a result broken down by a dimension;
`regressionAdjustmentEnabled` or `sequentialTestingEnabled` set, or a metric-level regression adjustment
override (the exported standard deviation is then not the raw one); allocation weights that contradict the
mapping's `snapshot.expected_treatment_share`; a `result.phase` that is not a zero-based index string within
`experiment.phases`; more or fewer than exactly two variation results per metric, or a repeated variation id;
a `pValue`, `chanceToBeatControl` or `checks.srm` outside [0, 1]; a metric with an analysis error, missing data,
or a shape that contradicts its mapped type; duplicate keys, `NaN` or invalid UTF-8. Post-stratification
(`postStratificationEnabled`, on by default in GrowthBook) is accepted: by inspection of GrowthBook's source at
`7cbc85d1` it is applied in GrowthBook's effect estimate, not to the per-arm users, numerators, means or
standard deviations that expgate reads, but the export does not let the importer check that.

### What the export cannot establish about the snapshot

`GET /api/v1/experiments/{id}/results` returns the **latest successful snapshot** together with the experiment's
**current** settings (GrowthBook `7cbc85d1`, `getExperimentResults.ts` and `toSnapshotApiInterface`). The metric
lists, `trafficSplit` weights and adjustment flags in the export are therefore not necessarily the ones the snapshot
was computed with, and the snapshot's own adjustment flags and weights are not exported. Two edits after a
snapshot are silent: switching CUPED off leaves regression-adjusted standard deviations next to a `false` flag
(a mean or ratio metric then carries a variance that does not belong to its raw mean), and editing weights within
a phase leaves the old counts next to the new weights (a valid snapshot then looks like a sample-ratio mismatch).

So the importer does not take either from the export. The mapping must **assert** them in `snapshot`:
`expected_treatment_share` (the share of the allocation the snapshot was taken under) and
`regression_adjustment: false` (the snapshot was computed without regression adjustment). Both are recorded in
`input.source.asserted`, are operator statements the importer cannot verify, and the import is refused when the
export's current settings contradict them (weights that do not match the asserted share, adjustment or sequential
testing switched on): refresh the analysis in GrowthBook and export again. The decision and the sample-ratio check
use the asserted share. What is still not covered: an adjustment that was on when the snapshot ran and was
switched off since is indistinguishable from a raw snapshot (hence the assertion), and the goal and guardrail
lists are current, not snapshot-time (the mapping's explicit per-metric entries, and the requirement that
each has results in the export, bound the damage).

Alternatives that were checked and not used: comparing `experiment.dateUpdated` with the snapshot time is
unusable, since running a snapshot itself updates the experiment (in all three fixtures `experiment.dateUpdated`
is about a second after `result.dateUpdated` for an untouched experiment); a snapshot document with snapshot-time
settings is not in the public API (`GET /api/v1/snapshots/{id}` returns only `id`, `experiment` and `status`).

### GrowthBook's reading and policy differences

expgate never uses GrowthBook's p-values, intervals or Bayesian chance to win. It recomputes
every statistic from the exported counts, means and standard deviations with its own estimators
(unpooled Wald for proportions, Welch for means, delta method for ratios) and its own rules: a
**one-sided** test of the primary metric at `alpha`, and **non-inferiority within a margin** for every guardrail
with `alpha` split across them. GrowthBook's frequentist engine reports **two-sided** p-values and
intervals and has no margins; its Bayesian engine reports a chance to beat control.

So the record can say where the two part ways, the importer also *reads* GrowthBook's own numbers with
the same ship/hold/rollback vocabulary and stores the result in `input.source.reading`. This reading is
the importer's, not a verdict GrowthBook computes: its open-source API exposes no decision.
A metric is *better* or *worse* when the frequentist `pValue` is below the GrowthBook significance level (0.05 by default,
signed by `percentChange` and the mapped direction) or the Bayesian `chanceToBeatControl` is at least
one minus it, or at most it; otherwise *not significant*. `INVALID` when GrowthBook's own `checks.srm` is below its
level (0.001); `ROLLBACK` when the primary or any guardrail is *worse*; `SHIP` when the primary is *better*;
otherwise `HOLD`. Whatever correction GrowthBook applied to its p-values is inherited, and the organization's real
significance levels are not in the export, so set `growthbook` in the mapping if they are not the defaults.

When the reading differs from expgate's decision, `reasons` says so, then adds one
`policy difference: …` line per metric that explains why, with the numbers (they are stored in the input, so
replay reproduces them):

```text
GrowthBook's own statistics read as HOLD; expgate decided SHIP
policy difference: primary purchase_rate: GrowthBook reads it as not significant (two-sided p 0.09086 >= 0.05); expgate tests the
primary metric one-sided at alpha 0.05 on the exported aggregates and finds it improved (one-sided p 0.04131); GrowthBook's own statistic is not used
```

When they agree, `reasons` is unchanged. The reading is metadata: `experiment-gate-verify` replays the
decision from the counts and the rules, and the reading and the export digest are part of the digested
input, so editing either (or any count) exits 1 unless the digest is recomputed too, as for any input edit.

### Evidence behind the importer

The three fixtures in [`tests/fixtures/growthbook/`](tests/fixtures/growthbook/README.md) are unmodified
`getExperimentResults` response bodies from a throwaway self-hosted GrowthBook 5.1.0 whose warehouse held
**synthetic** events for two variations (one proportion, one mean and one ratio metric, plus guardrails).
They are software-behavior evidence only: the importer reads the real export shape, and one capture shows
GrowthBook's reading and expgate's decision agreeing, one disagreeing because of the guardrail margin and one
because of the one-sided test. They say nothing about real experiments, users, models or effect sizes. The
README there lists the exact capture steps and `capture/capture.py` repeats them.

## Ratio metrics

Some metrics are a ratio of two per-unit totals: revenue per session, clicks per page view,
when users (not sessions) are randomized. Sessions from the same user are correlated, so
treating them as independent draws understates the standard error. Declare the metric with
`"type": "ratio"` and give each arm the per-unit mean and sample standard deviation of the
numerator and the denominator, and their correlation across units:

```json
"revenue_per_session": {"numerator": {"mean": 31.2, "sd": 40.5},
                        "denominator": {"mean": 3.1, "sd": 2.4}, "corr": 0.62}
```

The arm's value is `numerator.mean / denominator.mean`, and its variance comes from the
first-order delta method,
`(sd_y^2 - 2 R corr sd_y sd_x + R^2 sd_x^2) / (mean_x^2 n)` with `R` the ratio and `n` the
arm's units. The denominator mean must be positive. Ratio metrics take any role and direction,
work with sequential monitoring, and do not take a CUPED `covariate`.

In 1,000 simulated A/A tests that randomize 2,000 users per arm, each with a varying number
of sessions and a user-level spending propensity, the delta-method standard error averaged
0.212 against an empirical spread of 0.211, and a one-sided test at 0.05 shipped 4.6% of
them. Treating sessions as independent shipped 9.8%.

## Variance reduction (CUPED)

If you have a pre-experiment measurement of the same unit that predicts the outcome (last
month's revenue for this month's revenue, say), add a `covariate` summary to **that metric in
both arms** (the numbers below are illustrative):

```json
"revenue_per_user": {"mean": 20.57, "sd": 8.1,
                     "covariate": {"mean": 20.46, "sd": 7.9, "corr": 0.8}}
```

`covariate.mean` and `covariate.sd` describe the pre-experiment value, and `corr` is its
correlation with the outcome within the arm. Proportion metrics take the same block next to
`successes`. The estimate becomes `(ybar_t - ybar_c) - theta * (xbar_t - xbar_c)`, with one
`theta` shared by both arms: the pooled within-arm regression slope. The standard error
shrinks by about `1 - rho^2` in variance, and the adjustment also removes the part of the
difference caused by a chance imbalance in the covariate. The decision rules do not change, and
a metric's row in `decision.json` gains an `adjustment` object (`theta`, the unadjusted
difference and standard error, and the variance reduction).

Things the tool cannot check for you:

- The covariate must be measured **before assignment** and must not be affected by the
  treatment. A post-treatment covariate biases the estimate.
- The adjustment can move a single experiment's estimate either way. In the `cuped` scenario
  the treatment arm's covariate runs high by chance, the unadjusted lift is inflated, and the
  adjusted analysis holds. Across 300 simulated experiments with a real lift of 0.4 the adjusted
  analysis ships 80% of the time against 47% unadjusted. With no real lift over 1,500 runs they ship
  5.5% and 5.9% of the time, consistent with the nominal 5%.
- `theta` is treated as known. Its estimation error is negligible at the sample sizes this tool
  targets, but it is ignored.

## Sequential monitoring

The default bounds assume the summary is evaluated once, at a sample size fixed in advance.
Evaluating it every day and acting on the first `SHIP` or `ROLLBACK` inflates the error rates:
in 2,000 simulated A/A tests checked at 20 evenly spaced looks, re-applying the fixed-horizon
bounds at each look shipped 19.8% of them and rolled back 22.0%, against a nominal 5%.

To check a running test, declare the total sample size (both arms) the test is planned to reach:

```json
"policy": {"alpha": 0.05, "sequential": {"planned_units": 60000}}
```

Every bound then uses a normal-approximation confidence sequence: a one-sided normal-mixture
sequential probability ratio test on the same normal approximation, inverted into a bound. Under the
known-variance normal model, probability at least `1 - alpha` applies to each bound
at every look at once. With observed standard errors this is approximate, so the summary can be evaluated
as often as the platform refreshes it, and the experiment can stop at the first `SHIP` or
`ROLLBACK`. The decision rules, the Bonferroni split across guardrails and CUPED are unchanged;
only the multiplier on each standard error (the `z` in a metric's row) is larger. `decision.json`
gains a `sequential` object (planned and current units, and the information fraction), and
`DECISION.md` gains one line. A summary without `policy.sequential` uses fixed-horizon bounds.

`planned_units` tunes the mixing variance so the bound is narrowest at the planned size. It must be
fixed before the test starts; choosing it after seeing the data voids the guarantee. Under the known-variance normal model the bound
stays valid before and after the plan, only wider; the plug-in implementation remains approximate. A `HOLD` at or past the plan says that the
planned sample size was reached without a decision.

The price is power at the plan. In the same simulation, with a real conversion lift from 0.100 to
0.108 and 60,000 planned units, a single fixed-horizon analysis at the plan ships 95% of tests.
Sequential monitoring over 20 looks ships 74% of them, and those it ships stop on average at 56% of
the planned sample. Without a real effect it ships 1.0% and rolls back 1.2%. At the plan the
primary multiplier is 2.77 standard errors against 1.64 for the fixed-horizon test at
`alpha = 0.05`. Use sequential monitoring when stopping early (above all, rolling back a harmful
candidate early) is worth that cost.

## Synthetic scenarios

`--scenario` / `--all-scenarios` simulate an offer-ranking model with a fixed
seed (`expgate/generator.py`):

| Scenario | Expected decision |
|---|---|
| `win` | `SHIP` |
| `flat` | `HOLD` |
| `guardrail-breach` | `ROLLBACK` (latency) |
| `regression` | `ROLLBACK` (primary) |
| `srm` | `INVALID` |
| `cuped` | `HOLD` (a revenue lift that looks significant only because of a covariate imbalance) |
| `early-regression` | `ROLLBACK` (primary) at an interim look, a quarter of the way to the planned sample size |

## Cross-checks against reference libraries

Every estimator in `expgate/stats.py` is compared with an independent implementation on fixed
inputs. The references' answers are committed as JSON in
[`tests/golden/`](tests/golden/), so the default test suite
(`tests/test_golden.py`) checks them using only the standard library. The generator,
`tests/golden/generate.py`, needs the libraries locked in `tests/golden/requirements.txt` and
Python 3.10 (`confseq` 0.0.11, its latest release, has no wheels for newer interpreters; `gbstats`
0.8.0 pins `numpy<2` and `pandas<2`). The lock is compiled from the direct pins in
`tests/golden/requirements.in` and fixes every transitive dependency by version and hash, for Linux
and macOS, so the job cannot drift when an upstream package releases. A CI job (`golden vectors` in
`expgate-ci.yml`) installs from the lock, regenerates the files and fails on any difference.

```sh
python3.10 -m venv .venv && .venv/bin/pip install --require-hashes -r tests/golden/requirements.txt
.venv/bin/python tests/golden/generate.py             # rewrites tests/golden/*.json
```

To change a reference version, edit `requirements.in` and recompile with the `uv pip compile`
command in its header, then regenerate and review the diff of the vectors.

Pinned references: scipy 1.14.1, statsmodels 0.15.0, gbstats 0.8.0, confseq 0.0.11, numpy 1.26.4,
pandas 1.5.3. All are used for development and CI only; none is imported by `expgate`, listed as a
dependency, or shipped in the wheel. Licenses, from each distribution's metadata and bundled
license file: gbstats MIT (Copyright 2024 GrowthBook, Inc.), confseq MIT, statsmodels BSD-3-Clause,
scipy, numpy and pandas BSD. All permit this use. That finding covers the PyPI distributions we
install, not other parts of the GrowthBook repository.

| Method (`expgate.stats`) | Reference | Compared at | Result |
|---|---|---|---|
| `proportion_effect` (unpooled Wald) | statsmodels `test_proportions_2indep` and `confint_proportions_2indep` (`method="wald"`), gbstats `ProportionStatistic` | 1e-9 relative | agrees |
| `mean_effect` (Welch) | scipy `ttest_ind_from_stats(equal_var=False)`, gbstats `SampleMeanStatistic` | 1e-9 relative | agrees |
| `ratio_effect` (delta method) | gbstats `RatioStatistic`; linearization recomputed from raw per-unit data with numpy | 1e-9 relative | agrees |
| `cuped_effect` | OLS of `y ~ treated + x` on raw per-unit data (statsmodels) with the variance of `y - theta x` per arm (numpy); gbstats `RegressionAdjustedStatistic` where the method is the same | 1e-9 relative | agrees; gbstats differs by design, see below |
| `sample_ratio_p_value` | scipy `chisquare` | `exact_tail=True`: 1e-9 relative; schema-2 rule: 2.3e-16 absolute | tail limit in the schema-2 rule, documented |
| `minimum_detectable_effect` | scipy `norm.isf` and `norm.ppf`; statsmodels `NormalIndPower().power` at that effect equals the requested power | 1e-9 relative | agrees |
| `z_for` | scipy `norm.isf` | `exact_tail=True`: 1e-9 relative; schema-2 rule: 1e-9 above `alpha` = 1e-9, looser below | tail limit in the schema-2 rule, documented |
| mixture critical value at a fixed mixing ratio | scipy `quad` for the half-normal mixture integral and `brentq` for its root | 1e-9 relative | agrees |
| `sequential_multiplier` | confseq `normal_mixture_bound` (one-sided), mixing variance tuned with scipy `minimize_scalar` to be narrowest at the planned size | 1e-6 relative | agrees to 2.6e-7 at worst |

Vectors cover ordinary cases and boundaries: small samples, success rates at 0, at 1 and within
1e-5 of them, very unequal variances, negative effects, covariate imbalance, covariate
correlations of 0, 0.95 and -0.7, tiny and huge scales, unequal arms, and sample-ratio
mismatches from mild to a p-value of 1e-138. They are stored to eleven significant digits (seven
for the sequential boundary), so last-bit differences between platforms cannot change the
committed bytes.

**Tolerances.** Closed-form results must agree to 1e-9 relative. The one absolute floor applies
where the reference is exactly 0 (the CUPED slope and variance reduction when the covariate is
uncorrelated with the outcome, `z` at `alpha = 0.5`): there a difference below 1e-12 passes. The
generator stores 0.0 for the regression's rounding noise of about 1e-17, which differs between
platforms. Observed agreement was 7e-11 at worst, the size of the stored-digit quantization. The
sequential boundary is compared at 1e-6 relative because both sides iterate: confseq solves for
the boundary numerically and the mixing variance comes from a one-dimensional minimizer on an
objective that is flat at its minimum. The two agreed to 2.6e-7 at worst across 35 combinations
of `alpha` (0.001 to 0.2) and planned-to-current information ratio (0.1 to 10); a wrong boundary
would be off by far more (the fixed-horizon value at `alpha = 0.05` is 40% lower).

**Disagreements found: two tail-accuracy limits in the schema-2 rules.** Both come from computing
a tail through `1 - x`.

- The sample-ratio p-value is `2 * (1 - cdf(z))`. The subtraction is exact to about 1.1e-16, so
  below about 1e-7 the relative error exceeds 1e-9 (a split of 4,700 to 5,300 gives 1.9731754e-9,
  5.6e-8 off) and once `z` exceeds about 8.3 the result is exactly 0.0, where scipy gives 2.5e-43
  for 40,000 against 44,000 units. The `srm` scenario record written by 0.1.0 holds
  `p_value: 0.0` for 28,200 against 31,800 units; the true value is 6.7e-49. A 0.0 still fails any
  `srm_alpha`, so the decision is right; it matters only if you read tiny p-values or set
  `srm_alpha` below the true p-value.
- `z_for` is `inv_cdf(1 - alpha)`, which sees `1 - alpha` rounded to 1.1e-16. The critical value is
  within 1e-9 relative for `alpha` of 1e-9 and above, 1.9e-9 at 1e-10 and 4.4e-7 at 1e-12.

Accurate versions exist: `stats.sample_ratio_p_value(..., exact_tail=True)` uses `erfc` and
`stats.z_for(alpha, exact_tail=True)` uses `-inv_cdf(alpha)`; the golden vectors hold both to
1e-9 relative. Schema 3 uses them; the functions default to the old rules. A schema-2 record must replay with the formulas that
produced it, and the default changing would make the 0.1.0 `srm` record fail `expgate.verify`
(a regression test verifies every scenario record written by 0.1.0, committed under
`tests/fixtures/records-0.1.0`). Producers and the verifier therefore keep the 0.1.0 rules for
schema 2, and the vectors test those too, against the limits above (2.3e-16 absolute for the
p-value). Schema 3, the next decision schema and a new record format, uses the accurate tails
(a schema-3 `srm` record carries `p_value` 6.7e-49 and still verifies).

**Deliberate differences from the references.** These are method choices, not defects. The
vectors record the other side where it helps (the `informational` blocks are not asserted).

- *Proportions: unpooled variance.* statsmodels' `proportions_ztest` pools the variance under
  the null of no difference. expgate uses the unpooled (Wald) standard error because the same
  error builds the bounds around a non-zero estimate. For 100/1,000 against 150/1,000 the
  unpooled z is 3.3903 and the pooled z is 3.3806. The tests compare against the unpooled
  form (`method="wald"`).
- *Means: normal critical values.* A Welch t-test uses Student's t with Welch-Satterthwaite
  degrees of freedom; expgate uses the normal quantile at every sample size, as the estimators
  are documented to be large-sample. The standard errors agree; the one-sided 0.05 critical
  values do not at small `n` (1.645 against 5.08 for arms of 2 and 3 units, 1.645 against 1.650
  at 100 and 400).
- *CUPED: the slope.* expgate uses the pooled within-arm slope, the coefficient on `x` in
  `y ~ treated + x`. gbstats takes the slope of `y` on `x` over the pooled sample, ignoring arm.
  The two are equal when the arms' covariate means are equal. Otherwise the pooled sample also
  picks up the association between treatment and covariate: in the `covariate-imbalance` vector
  the slopes are 0.81128 and 0.81220 and the adjusted differences 0.29098 and 0.29024; in the
  `uncorrelated` vector, where the correlation within each arm is 0, expgate's slope is 0 and
  gbstats' is 0.0031. Vectors with equal covariate means are compared against gbstats; all are
  compared against the regression.
- *CUPED: the standard error.* expgate sums each arm's variance of `y - theta x` over its own
  units and treats `theta` as known (see the section above). The OLS standard error of the
  treatment coefficient pools residual variance across arms and includes the estimation error
  of `theta`; it is slightly larger (0.09687 against 0.09675 in the imbalance vector, 1.134
  against 1.007 with 4 and 3 units).
- *Sequential: other mixtures.* gbstats ships a two-sided sequential test (Waudby-Smith et al.
  2023, Gaussian mixture with a fixed tuning parameter) and confseq other boundaries. expgate's
  is the one-sided half-normal mixture, so only confseq's one-sided `normal_mixture_bound` is a
  reference for it. That function's own tuning rule is a closed-form approximation of the
  optimal mixing variance, and the multiplier it gives differs from expgate's optimized one by
  up to 0.8% (spot check at `alpha` 0.01 to 0.05 and information ratios 0.25 to 4). Both are
  valid; the vectors give confseq the optimized mixing variance so that only the boundary is
  compared.

What this shows and does not: the estimators implement the referenced formulas on these fixed
inputs. It does not show that a method is appropriate for a real experiment, and the vectors
are synthetic, not live or production evidence.

## Limitations

The simulation figures above describe synthetic experiments, not measured product
performance or calibration on live-model outcomes.

- Without `policy.sequential` the bounds are fixed-horizon: checking results repeatedly
  and stopping early inflates error rates.
- Sequential bounds plug in the observed standard error at each look, as the fixed-horizon
  bounds do. The guarantee is exact for normal estimates with known variance and holds only
  approximately at small samples. The sample-ratio check is not sequential: re-running it at
  every look raises its false alarm rate above `srm_alpha`.
- Replay is not bit-portable, and the verifier does not require it. The last digits of `exp`, `log` and the
  normal quantile differ between platforms: before this was fixed, the 0.1.0 scenario records written on
  macOS arm64 with Python 3.11 verified there but five of the seven reported a last-digit `metrics`
  mismatch on Linux (1e-9 relative or less). `expgate.verify` now compares computed statistics within a
  relative 1e-9 for schemas 2 and 3, so those records verify on Linux; `tests/test_expgate.py` runs the real
  verifier over the committed 0.1.0 records, and CI verifies the committed vectors on Linux. A sequential
  record's multiplier moves by about 1e-9 between builds (macOS Python 3.11 and 3.13 agree, 3.15 differs by
  1.3e-11), which stays inside the tolerance. An edit to a computed statistic smaller than 1e-9 relative is therefore
  not detected by replay (the input digest and every non-float field still are).
- CUPED is supported for one covariate per proportion or mean metric. There is no CUPED for
  ratio metrics, no multi-covariate adjustment, and no heterogeneous-effect analysis.
- The delta method is a first-order approximation. It needs enough units that the
  denominator mean is estimated well away from zero.
- Synthetic scenarios show that the rules behave as specified. They say nothing
  about any real product's effects.
- The GrowthBook importer needs a mapping file whose `snapshot` block asserts, without being able to check,
  the snapshot's allocation share and that it was not regression-adjusted (the results endpoint exports the
  experiment's current settings, not the snapshot's). It converts only plain two-variation experiments without
  regression adjustment, sequential testing or dimensions, and drops secondary
  metrics and GrowthBook's own intervals. A ratio metric is imported with a linearised numerator
  spread because the export lacks the real one. GrowthBook's "reading" in the record is the importer's
  reading of its p-values or chance to beat control at assumed significance levels, not a GrowthBook
  verdict. Only one GrowthBook version (5.1.0), one warehouse type and synthetic data were
  used to capture fixtures; no real GrowthBook installation has been tested.
