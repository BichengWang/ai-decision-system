# Changelog

All notable changes are documented here, following [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - Unreleased

### Compatibility and upgrading

Breaking for scripts that parse the `jev-decision` command's standard output; the Python API and the
evaluation record schema numbers are unchanged.

- **`jev-decision` prints a different record by default.** It writes an answer record of
  `schema_version: 2` as RFC 8785 canonical JSON: it embeds the `questions` and the raw provider `response`
  and carries `record_sha256`, so `jev-decision-verify` can re-check it offline. 0.1.0 printed the typed
  answers only; `--schema-version 1` prints that earlier shape. The command also exits 1 when the provider
  response cannot be recorded as canonical JSON.
- **Schema 1 answer records** (written by 0.1.0) stay readable but `jev-decision-verify` exits 2 for them:
  they embed neither the questions nor the response, so they cannot be re-verified.
- **Evaluations written by 0.1.0** lack `questions.json` and `requirements.json`; pass the original files
  with `--questions` and `--requirements` to `jev-decision-verify --evaluation`. Runs of 0.2.0
  `jev-decision-eval` retain exact copies of both and list them in `provenance.json` `outputs`.
- **New verifier.** `jev-decision-verify` is new in this release (0.1.0 had no record-only verifier). Exit 0
  verified, 1 mismatch, 2 malformed or unverifiable.
- **Replay tolerance.** Recomputed metric floats compare with a relative tolerance of 1e-9; everything else
  compares exactly.
- **Unchanged:** Python 3.11 or later, no runtime dependencies, `DecisionModel` and the question and answer
  types, evaluation and provenance `schema_version: 2`, `jev-decision-eval` options.

### Added
- `jev-decision-verify answer.json` re-parses the embedded raw provider response with the embedded question
  definitions, compares typed answers, refusals, `id`, `usage` and `model`, and recomputes the digest. Exit
  0 verified, 1 mismatch, 2 malformed or unverifiable.
- `jev-decision-verify --evaluation DIR` hashes every file listed in `provenance.json` and re-scores the
  retained responses against `evaluation.json` and `cases.jsonl` without calling a provider; recomputed
  metric floats compare with a relative tolerance of 1e-9, everything else exactly.
- Answer record schema 2: embeds `questions` and the raw `response` and carries `record_sha256`, the SHA-256
  of the RFC 8785 (JCS) canonical record without that member. `jevdecision/jcs.py` ships with the RFC 8785
  test vectors. `jev-decision --schema-version {1,2}`.
- `jev-decision --out FILE` writes the answer record to a new file (never over an existing one) instead of
  standard output.
- Signed records (P-012): `jev-decision --out FILE --sign-key KEYFILE` and `jev-decision-eval --sign-key
  KEYFILE` write an in-toto Statement v1 in an HMAC-SHA256 DSSE envelope (`FILE.dsse.json`,
  `provenance.json.dsse.json`) over the exact file bytes; `jev-decision --generate-key KEYFILE` creates a
  0600 key and never overwrites. `jev-decision-verify` gains `--require-signature` with `--key KEYFILE
  [--signature ENVELOPE]` or `--sigstore-bundle BUNDLE --certificate-identity ID
  --certificate-oidc-issuer URL` (external `cosign`), and `--predicate-out FILE` for `cosign attest-blob`.
  Unsigned, wrongly keyed, re-hashed, wrong-predicate or malformed-envelope input (including null or
  odd-typed `sig`, `payload`, `predicateType`, `subject` or digest values) exits 1; a bad key file or
  missing `cosign` exits 2. `jevdecision/signing.py` is the shared signing module. Signed files are read
  once; `cosign` verifies private copies of those bytes.
- JSON Schemas (2020-12) for answer records 1 and 2, `evaluation.json` 2 and `provenance.json` 2, shipped as
  package data in `jevdecision/schema/`.
- Conformance vectors under `conformance/` (valid, tampered and invalid answer records and evaluation
  directories, with canonical bytes and `bytes` digests), `conformance/manifest.json` and the deterministic
  `conformance/generate.py`. CI validates them with the built wheel and a separate Node job validates every
  vector and recomputes every digest.
- `conformance/generate.py --check` compares the committed vectors with a fresh generation without writing
  (exit 1 and the differing paths on stderr; evaluation `evaluation.json` floats compare with the
  verifier's 1e-9 tolerance, so a tree generated on another platform passes), `--out DIR` writes or checks
  another directory, and unknown arguments exit 2. Run without arguments it still rewrites the tree.

### Changed
- `jev-decision` prints schema 2 answer records by default (see Compatibility and upgrading).
- `jev-decision-eval` retains exact copies of the question file and any requirement file as
  `questions.json` and `requirements.json` and lists them in `provenance.json` `outputs`.

### Fixed
- `urllib_transport` closes the HTTP error response after reading its body and headers; it was left for
  garbage collection, which emitted `ResourceWarning`.

### Security
- Signed records and `--require-signature` bind a record to a key: an edited record whose `record_sha256` was
  recomputed passes the digest check but fails the signature check. HMAC proves possession of the shared
  key, not an individual author; a signature does not show the provider's response is genuine. See the
  repository `SECURITY.md` for key generation, storage and rotation.

## [0.1.0] - 2026-10-13

### Added
- Installable standard-library-only package, annotated public API, MIT license, source/sdist examples, and `jev-decision` / `jev-decision-eval` commands.
- Typed per-question refusals, refusal counts/rates, and score Brier, log-loss and ECE metrics.
- Versioned decision/evaluation/provenance records with producer metadata and canonical JSON.

### Changed
- Live evaluation durably appends responses and case results in a sibling staging directory; completed output is published atomically. Authentication failures stop with exit 2.
- Decision CLI returns exit 1 for a result containing refusals while retaining sibling answers.

### Fixed
- Correctly rounded floating-point accumulation gives identical bundled replay metrics on Python 3.11 and 3.13.
- Examples ship once in the source/sdist, rather than being duplicated in the installed package.
- Missing score probabilities stay unknown; only complete distributions can derive a score. Missing metric inputs fail requirements.
- Probability values must be finite and within [0,1]; complete distributions must sum to 1 within rounding tolerance.
- HTTP protocol failures become retryable `APIError`; HTTP 408 is retryable.

### Security
- Remote provider URLs require HTTPS; HTTP is limited to loopback hosts. URL credentials are rejected and authenticated POST redirects are never followed.
