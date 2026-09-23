# Clean-room reproduction

Package candidate 0.1.5 uses specification 0.1.3 and remains unreleased. Its stored output
was regenerated locally with CPython 3.13.7 on macOS 26.7 arm64, uv 0.10.11, NumPy 2.5.3,
SciPy 1.18.1, and scikit-learn 1.9.1. OMP, OpenBLAS, MKL, and vecLib thread environment
limits were each set to 1; existing package caches were used. This is a development run,
not an attested clean-machine reproduction. Check the version inside the identified
candidate's `results/results.json`; stored 0.1.4 artifacts are historical baselines.
Those labels alone do not define an exact environment: hardware, wheels/builds, numerical
libraries, and thread settings may affect floating-point output.

The project declares Python 3.13 and pins 3.13.7 in `.python-version`. `pyproject.toml` and
`uv.lock` are its dependency authorities. Retain each run's `runtime.json`, actual
`uv --version`, installed artifact identities, numerical-library/build details, hardware,
thread settings, cache use, and setup/test/run timings with the external provenance record.
Do not treat a lockfile alone as proof of which artifacts were installed.

`bash scripts/reproduce.sh /absolute/new/output-directory` runs frozen setup, the full
suite, and two fresh runs, retaining logs, elapsed seconds, test outputs, installed metadata
fingerprints, numerical-library configuration, and artifact checksums. The output directory
must not already exist and its parent must exist. The helper defaults the four thread
limits above to 1 if unset; freeze the intended settings before running. It does not
perform the separate stored-reference comparison or complete reviewer attestations.

For two fresh runs in one executing environment, `results.json` and `MANIFEST.json`—and
the SHA-256 of each file—must be byte-identical. `runtime.json` is machine-dependent and
excluded. Equality with stored output hashes is required only in the attested producing
environment with the same dependency artifacts and execution settings. Every other
environment uses a comparison protocol fixed before execution, as specified below.

## Source layout and release identity

Development is in `ai-workflows/ai-decision-reliability/` on `main` in
[`BichengWang/ai-decision-system`](https://github.com/BichengWang/ai-decision-system).
Enter that project directory before running `uv`; the root research environment is separate.
The planned `relia-release` branch contains a generated standalone project at its root.
Annotated release tags use `relia/v<version>`. These are planned names, not a claim that a
release or download exists.

The external release record identifies reviewed monorepo commit **M**, its project tree
**T**, standalone export commit **E**, and bundle **B**. The project tree at M must equal
the root tree of E:

```text
git rev-parse M:ai-workflows/ai-decision-reliability
    == git rev-parse E^{tree}
```

M and E are different commits. E must have only project-release history; it must not include
the monorepo or a private parent repository's history. A matching tree establishes content
identity, not authorship or the dates of the underlying work. The prepublication bundle and
later public annotated tag must identify the same E. Keep completed records outside E so
recording its hash does not change it. If published source M differs after review or merge,
record that source commit separately and verify its project tree still equals T.

## Reproduction procedure

For an **unaffiliated reproduction** record, the reviewer must not have authored or modified
the candidate, must disclose every relationship, referral path, compensation term, and other
interest, and must work from the identified artifact and instructions. Log every clarification
or other assistance. Other outside feedback may be useful but does not meet this definition.

1. Use a machine and account that have never held either this candidate or the source
   monorepo. Sign the clean-machine/account attestation and record its basis and the full
   environment record described above. A fresh directory on an existing machine/account
   does not satisfy this condition.
2. Before publication, receive the bundle created from E's standalone repository. Verify its
   SHA-256 against the value recorded before transfer, run `git bundle verify <bundle>`,
   clone it, and confirm `git rev-parse HEAD` equals E and `git rev-parse HEAD^{tree}` equals
   T. Label this a prepublication reproduction. After publication, clone
   `https://github.com/BichengWang/ai-decision-system.git` at the recorded `relia/v<version>`
   tag, confirm the tag is annotated, and record its tag-object ID, E, and T. The release
   clone has the project at its root; an ordinary `main` clone has the nested development
   layout. Reproduce the identified version rather than assuming it remains 0.1.5.
3. Before executing tests or the benchmark on a noncanonical environment, freeze the
   comparison protocol below, including its checksum, date, target platform, rationale,
   reference hash, and every numerical field's tolerances.
4. Run `uv sync --frozen` and retain setup output and time. Run
   `uv run --frozen python -m pytest -q`; retain its actual collected/passed count and output.
   Candidate 0.1.4 had 12 tests; record this candidate's actual count. The full suite itself
   runs the benchmark and may take appreciable time.
5. Run `uv run --frozen python -m relia.run --out repro-a`, then
   `uv run --frozen python -m relia.run --out repro-b`. Both output paths must be new or
   empty. Retain timings, runtime records, results, manifests, warnings, and any failures.
   Do not erase a failed attempt to reuse its path.
6. Run `cmp repro-a/results.json repro-b/results.json` and
   `cmp repro-a/MANIFEST.json repro-b/MANIFEST.json`. Both must succeed. Record both files'
   SHA-256 values from both runs; do not compare runtime records for byte identity.
7. Record primary decisions, all nine gates, and the guarded-update result from both runs.
   The retained reference behavior is a primary `PASS` and
   `REJECT_UPDATE_KEEP_CURRENT_REFERENCE`, with the update failing log-loss delta and
   worst-slice ECE; ranking is excluded from the eight applicable offer-model gates.
   Preserve any differing decision as a failure requiring investigation. A primary `BLOCK`
   also returns a failing process status; the rejected update is an expected recorded result.
8. Compare against the identified stored candidate. Only the attested producing environment
   may require exact stored-hash equality and run
   `RELIA_VERIFY_STORED=1 uv run --frozen python -m pytest -q`. For other environments, use
   the frozen field-level protocol and the command below, and retain the complete comparison
   output. Record stored and reproduced dataset hashes separately; an unexplained dataset
   discrepancy requires investigation and cannot be waived by a metric tolerance.

## Field-level comparison protocol

Create the protocol before the run from the identified reference `results/results.json`:

```bash
uv run --frozen python -m relia.compare results/results.json --write-protocol-template /path/to/frozen-protocol.json
```

The command refuses to overwrite an existing file. It lists every reference float field,
sets exact counter/routing fields to zero tolerance, and leaves the other tolerances and
required descriptions unfinished. Complete and freeze this template before execution.

Use schema version `1`, its SHA-256 as `reference_sha256`, nonempty `target_platform` and
`rationale` strings, and a `tolerances` object. Each numerical floating-point field to be
compared, including every per-seed field, needs its own JSON-pointer entry containing
nonnegative finite `abs` and `rel` tolerances. Counter/routing fields stored as floats must
have both tolerances set to zero. State why those limits are appropriate in
the rationale and linked development analysis. This document does not supply invented
cross-platform tolerances; a protocol that is not complete before execution is not ready
for a noncanonical reproduction.

Compare each permitted numerical field against its reference value using
`abs(actual - reference) <= abs_tolerance + rel_tolerance * abs(reference)`. Counters,
versions, seeds, array order and lengths, field sets, gate names, comparators, decisions,
dispositions, exclusions, and all other exact fields must remain unchanged. Missing or
unexpected fields, nonfinite values, changed exact fields, incomplete tolerance coverage,
or an exceeded tolerance fail comparison. Dataset identity is an exact invariant outside
numerical metric tolerances. Do not loosen limits after observing a mismatch; retain the
failed run and identify any revised protocol as a new attempt.

```bash
uv run --frozen python -m relia.compare results/results.json repro-a/results.json --protocol /path/to/frozen-protocol.json
uv run --frozen python -m relia.compare results/results.json repro-b/results.json --protocol /path/to/frozen-protocol.json
```

This comparison covers numerical agreement and exact invariants. It does not establish
reviewer independence, rights clearance, maintainer acceptance, deployment, or adoption.

## Reproduction report form

| Field | Entry |
|---|---|
| Reviewer name, title, organization | |
| Relationship/referral path; compensation; financial or other interest | |
| Did the reviewer author or modify any part of the candidate? If yes, do not classify the run as unaffiliated | |
| Clean-machine/account attestation: before transfer, neither had held this candidate or the source monorepo; basis for confirmation | |
| Date; source route (verified prepublication bundle or public clone) | |
| Source commit M; project path; tree T; standalone commit E | |
| Bundle/archive SHA-256 and transfer record; tag and annotated tag-object ID if published | |
| Environment (hardware/processor, OS, architecture, Python, uv, dependency artifacts, numerical builds, lock SHA-256, thread settings) | |
| Exact commands; package-manager cache used?; assistance received | |
| Retries or restarts; warnings; failures; deviations; resolution | |
| Setup time; test time; Run A time; Run B time; measured memory and disk if collected | |
| Candidate/specification versions; actual tests collected, passed, failed, skipped; retained test output | |
| Run A and Run B primary nine-gate decisions | |
| Run A and Run B guarded-update decisions; failed and excluded gates | |
| Run A and Run B SHA-256 for results.json and MANIFEST.json; are both files byte-identical across runs? | |
| Stored and reproduced results_sha256 and dataset_sha256; differences and investigation | |
| If noncanonical: protocol path, SHA-256, freeze date, target platform, rationale, per-field tolerances | |
| If noncanonical: exact invariants; each field's difference and tolerance result; retained comparison output | |
| Deviations, defects, or unclear definitions found | |
| Are the gates and metrics appropriate for the stated decisions? What would you change? | |
| Would this be useful in your own work or organization? For what, and what is missing? | |
| Signature and date | |

After publication, publish consented reports, including unfavorable ones, as release assets
or in `docs/reviews/` on a later development commit. Redact private information with the
reviewer's permission. Keep the accepted E and its annotated release tag unchanged.
