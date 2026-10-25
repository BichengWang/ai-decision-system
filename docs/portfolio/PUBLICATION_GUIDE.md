# Portfolio evidence and publication protocol

Use the [technical report](PUBLICATION_REPORT.md) and [news briefing](NEWS_READY.md) for first-party dissemination. The [NIW source notes](NIW_SOURCE_NOTES.md) separate technical progress from person-specific legal evidence.

## Reproduce the four-project portfolio

From the repository root, with `uv` and Git available:

```bash
uv run --no-project --python 3.11 python scripts/publication_evidence.py \
  --out /tmp/ai-decision-evidence-new
uv run --no-project --python 3.11 python scripts/publication_evidence.py \
  --verify /tmp/ai-decision-evidence-new
```

The parent directory must exist; the evidence directory must not exist and must be outside the source repository. Use a different directory for every attempt, including failures. No model-provider credentials or live calls are used. RELIA needs its own frozen dependencies; the command invokes its existing reproduction helper rather than importing it into another project's environment.

The command:

1. Reads `workspace.json`; requires coverage of the four currently registered independent projects. New projects require an explicit evidence-protocol update rather than being silently skipped.
2. Hashes the actual project/tooling/workflow source files, including nonignored uncommitted files. HEAD is contextual metadata, not a claim that it identifies the worktree bytes.
3. Runs the three standard-library project suites and the registered workspace-tooling checks; RELIA's existing helper performs frozen setup, its suite, and two fresh benchmark runs. Export tests exercise fixtures, not an accepted release export.
4. Runs all experiment scenarios, explicit and ungated Jev replay, decision-control's persistent SQLite demo, its intentionally failing adverse evaluation, and replay of that failed evidence.
5. Checks dispositions and actual serialized demo ticket states. Expected adverse results are preserved: rejected RELIA update, experiment HOLD/ROLLBACK/INVALID, Jev UNGATED with exit 3, and policy-evaluation FAIL with exit 1.
6. Rejects changed source during execution. Writes `VERIFICATION.md` and `EVIDENCE.json` with commands, expected/actual exit statuses, timings, source hashes and retained artifact hashes. A failed step leaves its evidence and a FAIL report; no retry erases it.

Successful collection and retained-artifact integrity checks exit 0; a failed collection exits 1. Invalid invocation, unreadable inputs, or an artifact mismatch during `--verify` exits 2. `--verify` checks the retained artifact bytes against the recorded hashes, not author authenticity. Hashes are not signatures, and a malicious actor can rewrite the record. Keep the original record separately if integrity matters.

## Scope and claim limits

- The root legacy `src/` workbench is inventoried in the repository overview but is **not** covered by this four-project command. Its own bounded baseline remains in the [setup guide](../../src/README.md#baseline-check).
- RELIA's two-run agreement is same-environment local repeatability. This command does not complete stored-reference comparison, a clean-room reviewer attestation, rights review, or release acceptance. Follow [RELIA's separate protocol](../../ai-workflows/ai-decision-reliability/docs/REPRODUCE.md) for those claims.
- Bundled Jev responses, decision-control recommendations, and labels are hand-authored fixtures. No live-model quality, calibration, or production-safety inference follows.
- Projects remain independent. Shared subject matter is not a tested integrated application.
- Local test logs can contain paths, fixtures and environment metadata. Inspect them before external sharing. Do not upload employer/private data, credentials, reviewer identities or correspondence without permission.

## Publish the report, not an unaccepted release

Publish the authored report, news briefing, source notes and compact evidence summary on the existing public repository's development branch. Record the exact commit URL and document paths. A review PR is a public delivery record; it is not proof of acceptance, independent review, media coverage, a tagged package release or immigration eligibility.

The public compact summary identifies the local retained run and selected artifact hashes; it is not a complete verification directory. Reproduction requires executing the command and retaining its full output. Preserve the original full evidence directory and its SHA-256 record locally.

Do not create a RELIA release/tag, change its licensing metadata, announce reuse rights, or upload a standalone RELIA distribution until its existing rights-clearance and acceptance requirements are met. Root licensing does not override those project restrictions.

For external media, use the briefing only as an attributed first-party pitch. Retain actual outlet/byline, publication URL/date, editorial and sponsorship disclosures, consented source material, and corrections. Preparation or self-publication is not an independent news placement.
