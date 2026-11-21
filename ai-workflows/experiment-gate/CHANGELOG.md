# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - Unreleased

### Compatibility and upgrading

Breaking for anything that reads or checks records; no command or option of 0.1.0 was removed.

- **New default record schema.** `experiment-gate`, `expgate.evaluate(summary)` and the GrowthBook importer
  write `schema_version: 3`. Its `input_sha256` is the SHA-256 of the RFC 8785 (JCS) canonical form of
  `input`, not of 0.1.0's python-json-v1 form, so the digest of the same input changes wherever the two
  spell a number differently (for example `20.0`). `produced_by.version` is `0.2.0`.
- **0.1.0 cannot verify schema 3.** A 0.1.0 `experiment-gate-verify` rejects a schema 3 record as
  unsupported. Pin 0.2.0 wherever new records are checked. `evaluate(..., schema_version=2)` still writes the
  0.1.0 form.
- **Old records keep verifying.** `experiment-gate-verify` verifies schema 2 (python-json-v1 digest, 0.1.0
  tail formulas, lenient parsing, unchanged) and schema 3. Schema 1 and any other schema still exit 2. No
  record that verified before stops verifying.
- **Schema 3 numbers.** New records use the accurate tails (`exact_tail=True`): the `srm` scenario records
  `p_value` 6.7e-49 where schema 2 recorded 0.0. Decisions are unchanged; the defaults of
  `stats.sample_ratio_p_value` and `stats.z_for` are unchanged.
- **Stricter schema 3 parsing.** Duplicate keys, non-finite numbers, integers beyond 2^53-1 and lone
  surrogates anywhere in a schema 3 record exit 2 (schema 2 stays lenient).
- **Replay comparison.** Recomputed statistics now agree within a relative 1e-9 (absolute 1e-12 where the
  replayed value is exactly 0) for both schemas, so records written on one platform verify on another. Inputs,
  digests, strings, booleans, dispositions and structure stay exact.
- **Unchanged:** Python 3.11 or later, no runtime dependencies, decision rules, existing options and exit
  codes of `experiment-gate` and `experiment-gate-verify` without the new flags.

### Added
- Decision record **schema 3**, written by default (`expgate/jcs.py`, checked against 647 number, structure
  and rejection vectors).
- JSON Schemas for schema 2 and 3 as package data (`expgate/schema/decision.v2.json`, `decision.v3.json`).
- Conformance vectors under `conformance/`: valid, tampered and invalid records for schemas 2 and 3, a
  schema-1 record, exact canonical input bytes, `manifest.json`, and a deterministic generator
  (`conformance/generate.py [--check]`). CI validates CLI-produced records against the schemas with a pinned
  dev-only `jsonschema`, verifies the vectors with the built wheel, and a separate Node job validates every
  vector and recomputes every digest.
- Signed records (P-012): `experiment-gate keygen KEY` and `--sign-key KEY` on the producer (one
  `decision.json.dsse.json` per record, also for `--all-scenarios`), and `--require-signature` (`--key
  [--signature]`, or `--sigstore-bundle` with `--certificate-identity` and `--certificate-oidc-issuer`) on
  `experiment-gate-verify`. HMAC-SHA256 DSSE envelopes carry an in-toto Statement v1 whose subject is the
  SHA-256 of the exact `decision.json` bytes; the predicate type names the schema version. Sigstore signing
  is external `cosign`; verification delegates to `cosign verify-blob-attestation` on a private copy of the
  bytes already read. `experiment-gate predicate` writes the predicate for `cosign attest-blob`. The file is
  read once: signature, parse and replay see the same bytes. Unsigned, wrong key, edited-and-re-hashed,
  wrong predicate type or malformed envelope fields (null or odd-typed `sig`, `payload`, `predicateType`,
  `subject` or digest) exit 1; a bad key file, missing `cosign` or flag misuse exits 2 (a bad `--sign-key`
  before any output is written). Behavior without the flags is unchanged. CI signs a record keylessly and
  verifies it with the package, and the wheel smoke check round-trips an HMAC signature.
- `experiment-gate --from growthbook results.json --mapping mapping.json` (P-025): converts the body of
  GrowthBook's `GET /api/v1/experiments/{id}/results` (per-variation users, counts, means and standard
  deviations) into an expgate input, evaluates it under expgate's rules and writes a normal schema-3 record.
  Offline and standard library only (`expgate/importers/growthbook.py`). A mapping file supplies what the
  export lacks: metric type, direction and guardrail margin, and a `snapshot` block asserting the snapshot's
  allocation share and that it was not regression-adjusted, because the results endpoint pairs the latest
  snapshot with the experiment's current settings; the assertions are recorded in `source.asserted` and the
  import is refused when the export's current weights or adjustment flags contradict them. A malformed or
  unsupported export or mapping (other dimensions than none, more than two variations or a repeated
  variation id, regression adjustment or sequential testing, a phase that is not a valid index, a
  probability outside [0, 1], a metric whose shape contradicts its type, duplicate keys, `NaN`) exits 2 with
  the field named. Post-stratification is accepted. GrowthBook's p-values, intervals and chance to win are
  never used for the decision. The README has the field mapping and what is and is not imported.
- Optional `source` object in a schema-3 `input` (`format`, `export_sha256`, experiment and snapshot ids,
  `stats_engine`, `asserted`, `reading`) in `decision.v3.json`. `export_sha256` is the SHA-256 of the export
  file's exact bytes, so `input_sha256` covers it and `experiment-gate-verify` detects an edit. `reading`
  holds the importer's reading of GrowthBook's own statistics (ship, hold or rollback) and, when it differs
  from expgate's decision, the `policy difference:` lines that `reasons` then repeats; replay reproduces
  them. Decisions never depend on `source`. Schema 2 rejects it.
- Fixtures captured from a throwaway self-hosted GrowthBook 5.1.0 with a synthetic warehouse
  (`tests/fixtures/growthbook/`: three exports, a mapping file and the dev-only capture script and compose
  stack), and `tests/test_growthbook.py`. One export shows GrowthBook's reading and expgate's decision
  agreeing, one a SHIP reading that expgate holds because a guardrail is not shown non-inferior, one a HOLD
  reading that expgate ships by its one-sided test. They are software-behavior evidence only: the data is
  synthetic.
- Golden vectors under `tests/golden/` that compare every estimator in `expgate.stats` with scipy,
  statsmodels, gbstats and confseq (P-013; dev-only, pinned in `tests/golden/requirements.txt`). The default
  tests read the committed JSON and need no third-party library; a CI job regenerates the vectors and fails
  on any difference. The README documents references, versions, tolerances and the deliberate differences
  (pooled versus unpooled proportion variance, normal versus t critical values, the CUPED slope and
  standard error).
- `exact_tail=True` on `stats.sample_ratio_p_value` and `stats.z_for` (`erfc` and `-inv_cdf(alpha)`). The
  cross-checks showed the defaults lose digits in the tails: the sample-ratio p-value below about 1e-7 and
  as exactly 0.0 past `z` of about 8.3, `z_for` for `alpha` below about 1e-9. The defaults are unchanged:
  schema-2 records, including every 0.1.0 scenario record (now committed as test fixtures), replay with the
  formulas that produced them. Schema 3 uses `exact_tail=True` (one mapping, `records.EXACT_TAIL`).

### Changed
- New records have `schema_version: 3` (see Compatibility and upgrading).
- Replay comparison for schemas 2 and 3 is one function with a relative 1e-9 tolerance on computed
  statistics (see Compatibility and upgrading).
- Schema 3 canonicalizes the whole record when verifying, so ignored members with unsafe integers,
  overflowed floats or lone surrogates exit 2, and `evaluate` raises `ValueError` for a schema-3 input whose
  statistics overflow to infinity.

### Fixed
- `experiment-gate-verify` no longer reports last-digit float differences between platforms: the 0.1.0
  scenario records written on macOS now verify on Linux (five of seven failed before).
- `experiment-gate-verify` exits 2 instead of stopping with a traceback and exit 1 when a record's input
  cannot be replayed because a statistic divides by a square that underflows to zero (a covariate `sd` of
  1e-200, say; `verify_record` raises `ValueError`), or when a record is nested too deeply to parse or
  canonicalize. The remaining records are still checked. A `--require-signature` envelope nested too deeply
  exits 1 like any malformed envelope, and `experiment-gate predicate` exits 2 for such a record.
- `experiment-gate` exits 2 instead of stopping with a traceback and exit 1, the `--require-ship` refusal
  code, for a summary whose statistics cannot be computed (a count beyond the float range, an `sd` whose
  square overflows, a covariate `sd` whose square underflows to zero) or that is nested too deeply to parse or
  canonicalize. `--from growthbook` exits 2 for an export with such numbers.
- `experiment-gate --input` with several summaries exits 2 when two experiment names differ only in Unicode
  normalization (`café` composed and decomposed), as it already did for names differing only in case. macOS
  stores both in one directory, so one record silently replaced the other while both were reported as written.
- A `null` `policy.alpha`, `srm_alpha`, `power` or `assignment.expected_treatment_share` is rejected with the
  field named (`ValueError`, exit 2). It passed validation before, and `evaluate` then raised a `TypeError` such
  as `unsupported operand type(s) for /: 'NoneType' and 'int'`.
- `experiment-gate-verify` reports a `sequential` mismatch (exit 1) for a record with `"sequential": null` whose
  replay has no sequential monitoring. It verified before, although expgate never writes that member and
  `decision.v2.json` and `decision.v3.json` reject it.

### Security
- Signed records (see Added) bind a record to a key: an edited record whose digest was recomputed passes
  the digest check but fails `--require-signature`. HMAC proves possession of the shared key, not an
  individual author; hashes and signatures do not prove the input data is true. See the repository
  `SECURITY.md` for key generation, storage and rotation.
- Schema 3 rejects duplicate keys, non-finite numbers, out-of-range integers and lone surrogates instead of
  silently accepting them.

## [0.1.0] - 2026-10-13

### Added
- Installable standard-library-only package, MIT license, `experiment-gate` and
  `experiment-gate-verify` commands, `python -m expgate`, and a small public API.
- Schema-2 records with producer version, embedded input and canonical input SHA-256;
  offline verification reports hash and replay mismatches. Schema 1 remains readable
  but cannot be verified without embedded input.
- Ratio, CUPED and sequential examples, wheel smoke checks and replay coverage.

### Changed
- Whole runs publish atomically from an adjacent staging directory, allowing retry
  after a write failure without partial output.
- MDE now states its normal-approximation basis; sequential MDE describes the current
  look and does not promise power under a stopping rule.

### Fixed
- Reject unknown summary/spec keys and undeclared arm metrics instead of ignoring them.
- Treat zero-standard-error primary and guardrail metrics as inconclusive, preventing
  unsupported significance and non-inferiority claims.
