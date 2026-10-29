# Regulatory mapping: decision records and logging provisions

> **No compliance claim. Not legal advice.** This document does not state, imply or
> support a claim that any record, package or deployment complies with, conforms to,
> or is certified under the EU AI Act, ISO/IEC 42001, the NIST AI RMF or any other
> law or standard. It maps field names that exist today to the *kind* of information
> each provision names, and lists what the records do not cover. Whether an AI system
> is high-risk, who is its provider or deployer, and what a given provision requires
> of a given organisation are legal questions this document does not answer. Ask a
> qualified lawyer or auditor.

Status: drafted for plan item P-028; owner review pending. The record mapping was
re-done against `main` after P-011 (JSON Schemas, conformance vectors, RFC 8785
records) and P-012 (signed records) landed, and describes the current schema version
of each record, citing the schema files shipped as package data. The legal sources
below were retrieved on **2026-10-19** and were not re-retrieved for the re-map.
Re-check this document when a schema version or signing behavior changes.

## What "serves" means here

A field "serves" a provision when it carries information of the kind the provision
names. It does not mean the provision is satisfied. Three limits apply to every row.

- The packages are not AI systems and are not wired into one. Article 12 concerns the
  logging capability of a high-risk AI system itself, recording events over the
  system's lifetime. The records here are produced by separate tooling around a
  go/no-go decision, from a run of that tooling, not by the AI system.
- Records are files (JSON, JSONL, Markdown) and, for decision-control, rows in a
  SQLite file that can be exported. Retention is the duty of whoever keeps the files.
  No package sets, enforces or evidences a retention period.
- Digests and checksums detect change after the fact. They do not authenticate who
  wrote a record, and anyone who edits a record can recompute them. A signature
  checked with `--require-signature` closes that gap for a re-hashed edit, and only
  within the limits stated under [Signing](#signing-what-it-gives-and-what-it-does-not).
  See [Encoding and integrity](DECISION_RECORDS.md#encoding-and-integrity) and
  [Compatibility and limits](DECISION_RECORDS.md#compatibility-and-limits).

## Primary texts and dates

| Source | URL | Retrieved | What was read |
| --- | --- | --- | --- |
| Regulation (EU) 2024/1689 (AI Act), consolidated text of 2026-07-27 | <https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02024R1689-20260727> | 2026-10-19 | Articles 12, 19, 26, 72, 113. EUR-Lex marks this text "purely as a documentation tool" with no legal effect; the authentic text is the Official Journal. |
| Regulation (EU) 2024/1689, Official Journal text of 2024-07-12 | <https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689> (ELI <http://data.europa.eu/eli/reg/2024/1689/oj>) | 2026-10-19 | Original unamended text; not compared line by line with the consolidated text, from which the articles were quoted |
| Regulation (EU) 2026/1744 (Digital Omnibus on AI), of 8 July 2026, OJ L 1744, 24.7.2026 | <https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32026R1744> (ELI <http://data.europa.eu/eli/reg/2026/1744/oj>) | 2026-10-19 | Recital 40 and the amendment to Article 113 (Article 1, point 40) |
| NIST AI 100-1, Artificial Intelligence Risk Management Framework (AI RMF 1.0), January 2023 | <https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf> (DOI <https://doi.org/10.6028/NIST.AI.100-1>) | 2026-10-19 | Table 4, MANAGE 4.1, printed page 33. AI RMF Playbook not reviewed |
| ISO/IEC 42001:2023, Annex A control A.6.2.8 | <https://www.iso.org/standard/42001> (public preview: ISO Online Browsing Platform) | 2026-10-19 | **Full text not reviewed; it is paywalled.** The public preview's table of contents stops at clause 8.4 and does not list Annex A. The number and title "A.6.2.8 AI system recording of event logs" were confirmed only from a third party's published statement of applicability ([Darktrace v1.11, 2025-12-03](https://cdn.prod.website-files.com/626ff4d25aca2edf4325ff97/6931b27220b329fdba170de2_Darktrace%20ISO%2042001%20Statement%20of%20Applicability.pdf)). This document relies on the title only and does not paraphrase the control's requirements or Annex B guidance |

### Application dates (confirmed against EUR-Lex)

Regulation (EU) 2026/1744 replaces Article 113, third paragraph, point (c) of
Regulation (EU) 2024/1689. In the consolidated text it reads:

> Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply from:
> (i) 2 December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III; and
> (ii) 2 August 2028 as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I;

Recital 40 of Regulation (EU) 2026/1744 gives the same two dates. Article 12 sits in
Chapter III Section 2; Articles 19 and 26 sit in Section 3. The roadmap's statement
that Annex III obligations moved to 2 December 2027 is therefore **confirmed** on
EUR-Lex; no correction to the plan was needed on the date. (The plan cited secondary
sources; this document and `.plan/README.md` now cite EUR-Lex.)

Other dates read in the same texts:

- Regulation (EU) 2026/1744 was published in the Official Journal on 24 July 2026 and
  enters into force on the third day after publication. The consolidated text is
  dated 2026-07-27, and Article 113, third paragraph, point (d), as amended, sets
  27 July 2026 for Articles 102 to 110.
- The general date of application of Regulation (EU) 2024/1689 remains 2 August 2026
  in the base text of Article 113, which the amendment does not replace.
- Articles 12, 19 and 26 carry no amendment marker in the consolidated text:
  Regulation (EU) 2026/1744 did not change their wording. It did amend Article 72(3)
  (guidance and template on the post-market monitoring plan, due by 2 September 2027,
  instead of an implementing act).

Whether any given AI-assisted decision involves a system "classified as high-risk
pursuant to Article 6(2) and Annex III" is a classification this document does not make.

### Provision text used

Quoted from the consolidated text above. EUR-Lex remains authoritative for the
exact wording.

**Article 12(1)**: "High-risk AI systems shall technically allow for the automatic
recording of events (logs) over the lifetime of the system."

**Article 12(2)**: "In order to ensure a level of traceability of the functioning of
a high-risk AI system that is appropriate to the intended purpose of the system,
logging capabilities shall enable the recording of events relevant for:
(a) identifying situations that may result in the high-risk AI system presenting a
risk within the meaning of Article 79(1) or in a substantial modification;
(b) facilitating the post-market monitoring referred to in Article 72; and
(c) monitoring the operation of high-risk AI systems referred to in Article 26(5)."

**Article 12(3)** sets minimum logging content only for high-risk AI systems referred
to in Annex III, point 1(a) (period of each use, reference database, matched input
data, identification of the persons verifying results). None of the records here is
designed for such systems, and paragraph 3 is not mapped below.

**Article 19(1)**: "Providers of high-risk AI systems shall keep the logs referred to
in Article 12(1), automatically generated by their high-risk AI systems, to the
extent such logs are under their control. Without prejudice to applicable Union or
national law, the logs shall be kept for a period appropriate to the intended purpose
of the high-risk AI system, of at least six months, unless provided otherwise in the
applicable Union or national law, in particular in Union law on the protection of
personal data." Article 19(2) concerns providers that are financial institutions.

**Article 26(6)**: "Deployers of high-risk AI systems shall keep the logs
automatically generated by that high-risk AI system to the extent such logs are
under their control, for a period appropriate to the intended purpose of the
high-risk AI system, of at least six months, unless provided otherwise in applicable
Union or national law, in particular in Union law on the protection of personal
data." Article 26(5) (cross-referenced by 12(2)(c)) requires deployers to monitor
operation on the basis of the instructions for use, to inform providers in
accordance with Article 72, and in defined cases to inform the provider or
distributor and the market surveillance authority, to suspend use, and to report
serious incidents.

**NIST AI 100-1, MANAGE 4.1**: "Post-deployment AI system monitoring plans are
implemented, including mechanisms for capturing and evaluating input from users and
other relevant AI actors, appeal and override, decommissioning, incident response,
recovery, and change management."

**ISO/IEC 42001:2023, A.6.2.8**: title "AI system recording of event logs" only; see
the source table.

## Mapping by record type

Record names follow [Records and checks](DECISION_RECORDS.md#records-and-checks).
Field names are those of the **current schema version** of each record, as declared
in the JSON Schema files shipped with each package (paths under
`ai-workflows/`; earlier versions have sibling files `<record>.v<N>.json`):

| Record (current schema) | Schema file |
| --- | --- |
| expgate `decision.json` (3) | `experiment-gate/expgate/schema/decision.v3.json` |
| Jev typed answer (2) | `jev-decision/jevdecision/schema/answer.v2.json` |
| Jev `evaluation.json` (2; 3 with a calibration) | `jev-decision/jevdecision/schema/evaluation.v2.json`, `evaluation.v3.json` |
| Jev `provenance.json` (2; 3 with a calibration) | `jev-decision/jevdecision/schema/provenance.v2.json`, `provenance.v3.json` |
| Jev `calibration.json` (1) | `jev-decision/jevdecision/schema/calibration.v1.json` |
| decision-control exported record (4: `record` + `sha256`) | `decision-control/decisioncontrol/schema/record.v4.json` |
| decision-control `evaluation.json` (2: `report` + `sha256`) | `decision-control/decisioncontrol/schema/evaluation.v2.json` |

Committed conformance vectors (synthetic) are under each package's `conformance/`
directory with a `manifest.json`. "-" in the table below means no field serves the
provision.

| Record | Art. 12(2)(a): risk situations, substantial modification | Art. 12(2)(b): post-market monitoring (Art. 72) | Art. 12(2)(c): deployer monitoring (Art. 26(5)) | Retention (Art. 19 provider, Art. 26(6) deployer) | ISO/IEC 42001 A.6.2.8 | NIST MANAGE 4.1 | Does not cover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **expgate `decision.json`** (schema 3) and `DECISION.md` | `decision` (SHIP/HOLD/ROLLBACK/INVALID), `reasons`, `metrics[].status` and `improvement_bounds` for guardrails, `sample_ratio.pass` flag a change that failed its predeclared guardrails before release | `experiment`, `policy`, `metrics`, `produced_by`, `expgate_version` give a comparable per-change data point a monitoring process could ingest | - | `input` embedded with `input_sha256` (RFC 8785 digest of `/input`) and `schema_version`; a detached signature file (`decision.json.dsse.json` or a Sigstore bundle) is a separate file that has to be retained with the record. `DECISION.md` carries the SHA-256 of the `decision.json` bytes but is not itself signed | Not assessed (control text not reviewed). Fact: one aggregate record per evaluation, with no event times | `decision`, `policy` and `input_sha256` document one change-management gate: what was evaluated and under which thresholds | No timestamp or event time in the record. Aggregate summary only, no per-use events. Does not say whether a change is a substantial modification. Input provenance is the caller's. `produced_by` is a label, not an authenticated identity. No retention period, deletion, access control or legal hold |
| **Jev typed answer** (schema 2) | `answers[*]` by `type`: `refusal` (type only); `noul` (`probability`); `choice` (`choice`, `probabilities`, `confidence`); `score` (`score`, `level`, `levels`, `probabilities`, `confidence`). They expose uncertainty or refusal per question | `model`, `backend`, `id`, `usage`, `produced_by` identify the response that fed a decision; `questions` (the question definitions), `response` (the raw provider response) and `record_sha256` make that one answer re-derivable offline | - | `record_sha256` (RFC 8785 digest of the whole record without that member); detached signature file retained separately. Schema 1 records stay readable but carry no digest and cannot be verified | Not assessed (control text not reviewed). Fact: one model response, with no timestamp | - | No timestamp. The question text and response are embedded, so the record may contain personal data supplied by the caller. `model`, `backend` and `id` are supplied metadata; nothing authenticates that the provider sent the response. Not a log of every use. No retention handling |
| **Jev `evaluation.json`** (schema 2) with **`provenance.json`** (schema 2), `responses.jsonl`, `cases.jsonl`, `questions.json`, `requirements.json` | `status` (PASS/FAIL/UNGATED), `error_rate`, `errors`, per-question `refusal_rate`, `refusals`, accuracy bounds, `requirements[].pass` show measured quality against stated requirements on labeled cases | `jevdecision_version`, `produced_by`, `model`, `backend` and `source` (replay/live) identify the run. `jev-decision-verify --evaluation DIR` re-scores the retained files (`responses.jsonl`, `questions.json`, `requirements.json`, the labels in `cases.jsonl`); `cases` in `evaluation.json` is only a count | - | `provenance.json` records SHA-256 of exact input and output bytes (`inputs.*`, `outputs`), so retained files can be re-checked; `response_origin` states whether responses were hand-supplied. The original case states are not retained. A signature over `provenance.json` pins every file it hashes | Not assessed (control text not reviewed). Fact: offline scoring record, with no timestamps | A repeatable evaluation artifact usable as an input to change management and periodic re-evaluation; nothing here implements monitoring | Offline scoring of saved responses, not runtime events. No timestamps. Case states and the supplied responses file are not re-checked. `responses.jsonl` holds raw provider responses and labeled cases may contain personal data; minimisation and erasure are the keeper's concern. Synthetic fixtures show software behavior, not live-model quality |
| **decision-control exported record** `record-*.json` (schema 4; 1, 2 and 3 replay under their original rules) | `evaluation.verdict` and `evaluation.reasons` (ALLOW/REVIEW/ABSTAIN/DENY), `recommendation.refused`, `recommendation.probability`, `status` (e.g. CANCELLED, STALE) | `created_at`, `events[].at`, `policy.version`, `policy_sha256`, `recommendation.model`, `recommendation.question_version` give a dated, policy-pinned data point per decision | `review.decision`, `review.reviewer`, `review.note`, `review.at`; `events` including `CANCELLED` (a reversed approval stays on record); `result` shows what was executed | `sha256` (RFC 8785 digest of `record`) plus embedded policy, ticket snapshot, review and events make an exported file self-contained and change-evident; the working store is a mutable SQLite file and only exports carry the checksum and can be signed | Not assessed (control text not reviewed). Fact: the only record here with timestamped events (`events[].at`, `review.at`), one record per decision, written by the workflow and not by an AI system | `review` (human approval or denial before execution), `CANCELLED` (reversal of an earlier approval), `policy.reviewers` and `policy_sha256` evidence an approval, override and change-control step for one decision | Does not capture user or affected-person input, appeals, incident response, serious-incident reporting, decommissioning or recovery. Does not detect a deleted or withheld record. No hash chain across records. Replay executes nothing. `proposed_by`, `review.reviewer` and `produced_by` are caller-asserted labels. No retention period, deletion or legal hold |
| **decision-control `evaluation.json`** (schema 2, `report` + `sha256`) | `metrics` (e.g. `unsafe_auto_allow_rate`, `incorrect_approval_rate`, `required_review_recall`), `gates`, `disposition` on labeled cases | `kind`, `source`, `confidence_level`, `policy`, `requirements` and the embedded `case_results` allow the same cases to be re-evaluated against a changed policy (`cases` is only a count) | - | `sha256` over `report` (RFC 8785); replay recomputes the report from the embedded content; detached signature file retained separately | Not assessed (control text not reviewed). Fact: offline report, with no timestamps | A policy-evaluation report usable as change-management evidence before a policy or model change | No `produced_by` and no timestamps in this schema. Offline evaluation of supplied cases, not runtime events. Labeled cases are the caller's. No retention handling |

### Replay, integrity and signature by record

Replay compares recomputed values with recorded ones under the adopted float rule:
**derived floating-point values that are recomputed from inputs agree within a
relative 1e-9** (absolute 1e-12 where the recomputed value is exactly 0), because
`log`, `exp`, `erf` and the normal quantile come from the platform math library and
their last digits differ across platforms. Everything else compares exactly: inputs,
strings, integers, booleans, dispositions and structure. Digest checks are always
byte-exact. Older schema versions keep their original comparison rules.

| Record | Digest | Replay comparison | Signature, when `--require-signature` is used |
| --- | --- | --- | --- |
| expgate `decision.json` (3; 2 uses the same comparison) | `input_sha256` over `/input`, RFC 8785 (schema 2: python-json-v1) | Relative 1e-9 on computed statistics only: `sample_ratio.p_value` and, per metric row, `diff`, `se`, `improvement`, `improvement_bounds`, `z`, `mde` and the CUPED `adjustment` numbers. Inputs, policy, counts, `reasons` strings, `decision` and structure are exact. Schema 3 rejects duplicate keys, non-finite numbers and integers beyond 2^53-1 (exit 2) | Over the exact bytes of `decision.json`; `DECISION.md` is not covered |
| Jev typed answer (2) | `record_sha256` | Exact: the only arithmetic on recorded floats is addition, multiplication and division, which are bit-portable | Over the exact bytes of the answer file |
| Jev `evaluation.json` / `provenance.json` (2) | `provenance.json` holds SHA-256 of exact file bytes; the digests are exact | Re-scored metric floats, including each requirement's `value`, within relative 1e-9; requirement bounds, counts, strings, booleans, statuses, `cases.jsonl` rows and file hashes are exact | Over the exact bytes of `provenance.json`, which pins the other files by hash |
| decision-control record (4) | `sha256` over `record`, RFC 8785 (schemas 1 to 3: python-json-v1) | Exact. The verdict is recomputed from the frozen policy; checksum, lifecycle, separation of duties and `policy_sha256` agree. Schema 4 rejects duplicate keys, non-finite numbers and integers beyond 2^53-1 | Over the exact bytes of the exported record file |
| decision-control `evaluation.json` (2; 1 replays under its original rules) | `sha256` over `report`, RFC 8785 (schema 1: python-json-v1) | Exact, with no tolerance, for both schemas: only correctly rounded IEEE 754 operations are used (`+`, `-`, `*`, `/` and `math.sqrt`) and no transcendental platform math-library function (`log`, `exp`, `erf`, inverse CDF) | Over the exact bytes of `evaluation.json` |

Evidence for the cross-platform limit and its rule is in the package READMEs
(expgate "Both schemas share one replay comparison", Jev "Metrics use `math.log`",
decision-control "Replay recomputes every metric"). Records written under older
schema versions are still compared under their original rules.

### Reading the table

- **12(2)(a)** and **12(2)(c)** concern events from operating a high-risk system. Only
  the decision-control exported record carries per-decision, time-stamped lifecycle
  events (`events`, `review`), and those describe the approval workflow around a
  recommendation, not events inside an AI system. The evaluation records describe
  measured quality on labeled cases and say nothing about events during use.
- **12(2)(b)** concerns data that supports a provider's post-market monitoring system
  under Article 72. The records contribute re-scorable, hashed data points. They are
  not a monitoring plan (Article 72(3)) and not an incident report (Article 73).
- **Retention** is a duty of the provider (Article 19) or deployer (Article 26(6)) for
  logs "under their control", and the period depends on the intended purpose and other
  law, including data protection law. The packages produce files and offer integrity
  checks over them; storing, retaining, protecting and deleting them, including the
  detached signature envelopes and Sigstore bundles, is outside the packages.
- **ISO/IEC 42001 A.6.2.8**: the control text was not reviewed (see the source
  table), so no statement is made about what it requires or whether any record could
  serve it. The column lists only facts about each record, in particular whether it
  carries event times. Only the decision-control exported record does.
- **MANAGE 4.1** lists mechanisms (input from users and other actors, appeal and
  override, decommissioning, incident response, recovery, change management). The
  records can evidence the override and change-management items for the decisions they
  cover. They do not implement any monitoring plan.

## Signing: what it gives and what it does not

Each package can sign its records and verify them with `--require-signature`
(READMEs, "Signed records"). The packages' own HMAC envelopes are an in-toto
Statement v1 in a DSSE envelope. The Sigstore path is different: it uses the
external `cosign attest-blob --type <predicate type URI>`, which in cosign v3.1.3
writes `_type` `https://in-toto.io/Statement/v0.1`, not v1 (cosign
`pkg/cosign/attestation/attestation.go` L242-267 at v3.1.3; in-toto-golang v0.11.0
`attestations.go` L11-18; both read on 2026-10-19). In both
cases the subject is the SHA-256 of the **exact bytes of the signed file**, and
its predicate type names the record type and schema version, so a signature for one
record type or version does not vouch for another. Without `--require-signature`
the verifiers ignore envelopes and behave as before.

**What signing adds.** An edited record that is re-hashed (new digest, consistent
content) passes digest-only verification but fails `--require-signature`: the
signature no longer covers the file's bytes, so the verifier exits 1. Re-formatting
the file also breaks the signature. This is tamper evidence against a re-hashed
forgery by someone who lacks the signing key (HMAC) or the signing identity
(Sigstore). An unsigned file, a wrongly keyed file and a file with a different
predicate type also exit 1.

| | HMAC-SHA256 (standard library, package-made) | Sigstore (external `cosign`, keyless in CI) |
| --- | --- | --- |
| Who creates the signature | The package, with `--sign-key` and a local key file | `cosign attest-blob`, run by the signer. The packages never sign with Sigstore |
| What verification proves | The signer held the shared secret key (the envelope names it by a key id of the form `hmac-sha256:<prefix>`) | `cosign verify-blob-attestation` accepted the bundle for this file's bytes and predicate type, for the exact `--certificate-identity` and `--certificate-oidc-issuer` supplied |
| Identity | None. Every verifier holds the same key and could also sign, so it does not show who signed or distinguish signers | With keyless signing in a CI workflow, the certificate identity names the workflow and ref (for example `.../.github/workflows/<workflow>.yml@refs/heads/main`). It is a workflow identity, not a person, and a record signed on another ref or workflow needs that exact identity to verify |
| Public log | None | Keyless signing writes the signer identity and the record digest to the public Rekor transparency log permanently, so it is unsuitable for private decisions |
| Trusted time | None. The envelope carries no time | Not provided by the packages: they pass `cosign` only `--bundle`, `--type`, `--certificate-identity`, `--certificate-oidc-issuer` and the file, read no time from the bundle and record none. A trusted signing time would be Rekor's inclusion time held in the Sigstore bundle, which a verifier would have to retain, read and check separately; how `cosign` treats it was not reviewed here |
| Key custody | Keys are the keeper's problem: keep them out of the repository and untrusted backups, rotate by making a new key and keeping old keys to verify old envelopes. No revocation | No long-lived key for keyless signing; the identity provider and Sigstore trust root are external dependencies |

Neither mechanism provides trusted time on its own. In particular, the
decision-control `created_at`, `events[].at` and `review.at` come from the local
system clock when the record is written. A valid signature makes those values
tamper-evident from the signing moment onward. It does not make them true or show
when the file was signed.

A signature shows who (or which shared-secret holder) attested to the file. It does
not show that the proposer, reviewer, model or labels inside the record are
authentic, that the provider response is genuine, that the records are complete or
ordered, or that an organisation retained them. Synthetic records signed in CI are
software checks, not adoption evidence.

## What none of the records cover

These apply across the tables and are stated once here.

- **Identity of the people and systems named in a record.** Producer, model,
  proposer and reviewer are labels the caller supplies. A signature binds the file
  to a key (HMAC: a shared secret, not an identity) or to a workflow identity
  (Sigstore), not to the named reviewer or proposer. Without `--require-signature`,
  or for a record that is unsigned, nothing binds a record to a person or system.
- **System-level logging.** The records are not the automatic event logs of an AI
  system (Article 12(1)), do not record each use, and carry none of the Article 12(3)
  items.
- **Retention enforcement.** No retention period field, deletion policy, backup,
  access control, encryption, legal hold or personal-data erasure workflow exists.
- **Completeness and ordering.** Nothing shows that every decision produced a record,
  that no record was removed, or that records are in order across runs. There is no
  hash chain across records. Rekor logs a Sigstore signature, not the existence of
  the decisions that were never signed.
- **Trusted time.** See the signing section: no package supplies or checks a
  trusted signing time. Only decision-control records timestamps, from the local
  system clock; expgate and Jev records have none.
- **Provider origin.** No record authenticates that a model response came from a
  named provider. Jev's `response_origin` states this limit.
- **Operator duties.** Instructions for use, human-oversight assignment, informing
  providers or authorities, suspension of use and serious-incident reporting
  (Articles 26 and 73) are organisational processes that the records do not perform
  or evidence.
- **Evidence of real-world use.** Hand-written and synthetic fixtures, including the
  conformance vectors, establish software behavior, not live-model quality,
  calibration, adoption or production use.
- **RELIA.** The reliability benchmark (`results.json`, `MANIFEST.json`) is outside
  this mapping. It is a synthetic comparison, not a decision record.

## Maintenance

Update this document when a schema version, record field, signing behavior or
application date changes, and on any amendment to Regulation (EU) 2024/1689 after the
2026-07-27 consolidated version. Re-check the NIST AI RMF text when NIST publishes
its revision (on 2026-10-19, <https://airc.nist.gov/airmf-resources/airmf/> states
that AI RMF 1.0 "is being updated"; this document uses AI RMF 1.0 as published in
January 2023). Re-read the ISO/IEC 42001 control from a licensed copy before
describing it in more detail.
