# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - Unreleased

### Compatibility and upgrading

Breaking for anything that reads new records or opens an upgraded database with 0.1.0; no command or option
of 0.1.0 was removed.

- **New default record schemas.** New decisions are stored and exported as schema 5 (RFC 8785
  canonicalization, plus the action-registry members and the required `external_policy` and
  `external_policy_sha256`, null without an external decision). New evaluation reports are schema 2. A 0.1.0
  `decision-control replay` rejects schemas 4 and 5 (and evaluation schema 2) as unsupported, so pin 0.2.0
  wherever new records are checked. `evaluate_cases(..., schema_version=2)` selects the report schema.
- **One-way store migration.** SQLite store schema 2 adds a nullable `tickets.priority` column. A store
  schema 1 database (0.1.0) is upgraded in place the first time 0.2.0 opens it; existing rows and records are
  unchanged, but 0.1.0 then refuses the database. Copy the file first if you may need to go back.
- **Old records keep their rules.** Records and reports of schema 4 and earlier still replay under their
  original rules and canonicalization, keep `reassign_ticket` as the only action and reject the schema 5
  members. Stored schema 3 and 4 decisions keep their schema through review, cancellation and export.
  `evaluate` and its reports still score `reassign_ticket` only.
- **Exit code.** A record or report with an unsupported or non-integer `schema_version` now exits 2 before its
  checksum is examined (previously a bad checksum could exit 1 first).
- **External policies replay digest-only without the tool.** `replay` of a record with a frozen OPA or Cedar
  decision re-evaluates it when `opa` or `cedar` is on PATH and exits 1 on disagreement; otherwise it exits 0,
  prints `policy NOT re-evaluated` on stderr and verifies the digests only. `replay
  --require-reevaluation` exits 2 instead. Records without an external policy are unaffected.
- **Stricter schema 4 and 5 and evaluation schema 2 parsing.** Replay rejects duplicate object keys, non-finite
  numbers, integers beyond 2^53-1 and unpaired surrogates (exit 2). Replay of schema 4 and 5 records also
  rejects a decision `id` that is not the canonical lowercase hyphenated UUID (`str(UUID(id)) == id`; uppercase,
  `urn:uuid:`, braces and unhyphenated spellings exit 2), and their JSON Schema `uuid` pattern is lowercase-only
  to match. Schemas 1-3 keep the 0.1.0 reader, which accepts anything `uuid.UUID()` parses; their schemas keep
  the hyphenated pattern and now say in a `$comment` that it is deliberately stricter than the reader.
- **Unchanged:** Python 3.11 or later, no runtime dependencies, the separation-of-duties rules since schema
  3, the commands and options of 0.1.0.

### Added
- Exported record schema 5 (RFC 8785, like schema 4) with the action-registry members and two required
  members, `external_policy` and `external_policy_sha256`; JSON Schema `record.v5.json`.
- Exported record schema 4 and `evaluation.json` schema 2: checksums (and the record `policy_sha256`) are
  SHA-256 of RFC 8785 (JCS) canonical bytes, via the bundled standard-library `decisioncontrol.jcs`
  (vectors in `tests/jcs_vectors.json`).
- Action registry (`decisioncontrol.actions.ACTIONS`): `reassign_ticket` moved into it and
  `set_ticket_priority` added through it only. Tickets gain an optional `priority` (`ticket-create
  --priority`), policies optional `allowed_priorities` and `review_priorities`, recommendations a `priority`
  member for the new action. All actions share one evaluation pipeline and executor; replay and the store
  name no action.
- Policy adapters (`decisioncontrol.adapters.opa`, `.cedar`) that freeze an OPA decision log entry
  (`decision_id`, `path`, bundle revisions, input, result, plus the Rego modules and data) or a Cedar
  authorization (policies as text or JSON, entities, request, decision, diagnostics) into the record. CLI:
  `freeze-opa`, `freeze-cedar`, `policy-input`, `submit --external-policy`. The frozen input or request must
  equal the one derived from the record's complete recommendation, ticket snapshot (including revision) and
  proposer, through one shared binding (Cedar carries a `proposal_sha256` context attribute); the external
  verdict is combined with the built-in policy by taking the more restrictive one.
- `replay` re-evaluates a frozen policy with `opa eval` or `cedar authorize` when the tool is on PATH (OPA
  with `http.send`, `net.lookup_ip_addr` and `opa.runtime` removed), exiting 1 on disagreement; the replay
  result gains `external_policy` for such records. See Compatibility and upgrading for the digest-only case.
- Recorded OPA 1.21.2 and Cedar CLI 4.14.0 decisions (`fixtures/policy-engines/`, with `record.py` and
  `tool-versions.txt`) and 47 schema 5 conformance vectors (valid, tampered, invalid), eight of the valid
  ones built from them. CI installs checksum-verified OPA and Cedar CLI release binaries, runs the suite with
  and without them and replays the fixtures re-evaluated and digest-only.
- `python3 conformance/generate.py --check` compares `valid/`, `tampered/`, `invalid/` and `manifest.json` with a
  fresh generation without writing: exit 1 and `differs: <path>` on stderr for a changed, missing or extra file
  inside those (other files in `conformance/` are not compared), exit 2 for an unknown
  argument. The invalid vectors `record-v4-uppercase-id`, `record-v4-urn-id`, `record-v5-uppercase-id` and
  `record-v5-urn-id` cover the canonical id rule.
- Signed records (P-012): `keygen`, `--sign-key` on `demo`, `evaluate` and `export`, and
  `--require-signature` (`--key [--signature]` or `--sigstore-bundle` with `--certificate-identity` and
  `--certificate-oidc-issuer`) on `replay` and `replay-evaluation`. HMAC-SHA256 DSSE envelopes
  (`<file>.dsse.json`) carry an in-toto Statement v1 whose subject is the SHA-256 of the exact file bytes; the
  predicate type names the record kind and schema version. Sigstore signing is external `cosign`;
  verification delegates to `cosign verify-blob-attestation`. `predicate` writes the predicate for `cosign
  attest-blob`. Unsigned, wrong key, edited-and-re-hashed, wrong predicate type or malformed envelope fields
  (null or odd-typed `sig`, `payload`, `predicateType`, `subject` or digest) exit 1; a bad key file or
  missing `cosign` exits 2, and `export --sign-key` loads and validates the key before opening the SQLite
  store, so a bad key leaves no new database behind. Behavior without the flags is unchanged. CI signs a demo
  record keylessly and verifies it with the package; the wheel smoke check round-trips an HMAC signature.
- LangGraph approvals example (P-026, `examples/langgraph/`): a two-node graph whose `propose` node submits a
  `set_ticket_priority` decision and whose `review` node surfaces it with `interrupt()`, records
  `Command(resume=...)` as `approve` or `reject` by a named reviewer, and exports a record that
  `decision-control replay` accepts. The proposer's own approval is refused by the store, and a record forged
  to name the proposer as reviewer fails replay (exit 1). The review note carries the LangGraph thread and
  checkpoint ids (no schema change). LangGraph 1.2.16 is a dev-only dependency pinned in
  `examples/langgraph/requirements-dev.txt`; `decisioncontrol` does not import it. Tests skip without it; CI
  installs it.
- JSON Schema 2020-12 files for record v1-v5 and evaluation v1-v2, shipped as package data under
  `decisioncontrol/schema/`.
- Conformance vectors with `manifest.json` and a deterministic generator under `conformance/`: valid,
  tampered (including recomputed-checksum self-approval and frozen-policy edits) and invalid vectors for
  every supported schema version. CI validates `decision-control demo` and `evaluate` output against the
  shipped schemas with pinned dev-only `jsonschema`, runs the vectors, and the wheel smoke check verifies
  packaged schemas and replays the vectors with the installed script; a separate Node job validates every
  vector and recomputes every digest.

### Changed
- New decisions are stored as schema 5 and new evaluations as schema 2 (separation-of-duties rules unchanged
  since schema 3).
- SQLite store schema 2 adds a nullable `tickets.priority` column; a store schema 1 database is upgraded in
  place on open, after which 0.1.0 refuses it.

### Fixed
- A record or report with an unsupported or non-integer `schema_version` exits 2 before its checksum is
  examined; a bad checksum could previously exit 1 first.
- `evaluate --require`, `submit --external-policy` and `freeze-cedar --response` exit 2 for a file that holds
  JSON `null`. It was treated as an omitted option: a gated evaluation ran `UNGATED` and exited 0, a
  submission was recorded without its external decision, and `freeze-cedar` ran `cedar` instead of freezing
  the recorded response.

### Security
- Signed records and `--require-signature` bind a record to a key: a record edited to name the proposer as
  reviewer, or any edit whose checksum was recomputed, passes the checksum check but fails the signature
  check. HMAC proves possession of the shared key, not an individual author; identities in records remain
  caller-asserted labels. See the repository `SECURITY.md` for key generation, storage and rotation.
- Frozen OPA and Cedar decisions are bound to the recommendation, ticket snapshot and proposer that produced
  them, so a verdict for a different input does not replay.
- Replay of schema 4 and 5 records and evaluation schema 2 rejects duplicate object keys, non-finite numbers,
  integers beyond 2^53-1 and unpaired surrogates.

## [0.1.0] - 2026-10-13

### Added
- Independent standard-library SDK, console CLI and module entry point for local
  ticket reassignment; strict policy/recommendation inputs and ALLOW/REVIEW/DENY/ABSTAIN.
- SQLite frozen decisions, durable review, revision conflicts, atomic idempotent
  local execution, and authorized pre-execution cancellation preserving approvals.
- Checksummed decision export and non-executing semantic replay; credential-free
  demo with hand-authored inputs, reopened approval and real local queue changes.
- Independently labeled policy evaluation, exposure-specific metrics, Wilson
  intervals, explicit sample/metric gates, frozen JSON/Markdown evidence and replay.
  Missing exposure cannot pass; ungated reports are not approvals.
- Adverse synthetic evaluation fixtures, concurrency/rollback regressions and
  Python 3.11/3.13 CI with installed-wheel lifecycle and evaluation smoke checks.
- Release metadata, dynamic package version, MIT SPDX license and project links.
- SQLite store schema 1 stamp and refusal of newer unknown database versions.

### Changed
- New decision records use schema 3 with required proposer identity, producer
  metadata and canonical policy digest. V1/v2 replay retains historical rules;
  cancelling a stored v1 decision promotes it to v2, preserving prior approval.
- Replay mismatches exit 1; malformed input and unsupported schemas exit 2.
- Demo, evaluation and file export publish complete staged outputs atomically.

### Fixed
- Corrupt pending rows no longer block valid queue entries; SDK diagnostics and
  CLI warnings expose skipped rows (exit 1).
- Identical rejection retries return the immutable recorded rejection.
- CLI execution of a stale decision exits 1 because no action was performed.

### Security
- Schema 3 REVIEW proposers cannot approve, reject or cancel their own decisions.
  Identities remain caller-asserted labels, not authentication; hashes detect
  change, not forgery. Local atomicity does not cover external actions.
- No provider calls, external executor, signed attestation or RELIA integration.
