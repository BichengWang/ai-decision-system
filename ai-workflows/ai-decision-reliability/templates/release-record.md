# Release record

Use one completed copy of this template for one exact standalone candidate. Keep that
completed record outside the tracked candidate so later commit, bundle, reproduction, and
publication identifiers do not change the artifact they identify. A blank field is
unresolved and blocks acceptance or publication; attach or identify the supporting record
for each material entry. Review, adoption, or acceptance is not original authorship.

Keep completed records private unless a redacted public summary has been approved by every
identified person; never publish signatures or confidential employment or rights records.

## 1. Artifact identity and review

| Field | Entry |
|---|---|
| Candidate version; specification version | |
| Reviewed monorepo source commit M | |
| Project path (ai-workflows/ai-decision-reliability) | |
| Project tree T at source M | |
| Standalone prepublication export commit E | |
| Export root tree; evidence it equals T | |
| Export inventory and history review; prior project release parent if applicable | |
| Prepublication bundle SHA-256 | |
| Bundle verification and fresh-clone check of E/T; transfer inventory and date | |
| Python pin; uv version; project lock SHA-256 | |
| Dataset SHA-256 | |
| Stored `results.json` SHA-256 | |
| Stored `MANIFEST.json` SHA-256 | |
| Gate report (attach `RESULTS.md`) | |
| Exact staged-file inventory and synthetic-data review | |
| Credential/secret scan method, date, scope, and result | |
| Known adverse or null results | |
| Rollback target and verification | |
| Reviewer decision, name, date | |

## 2. Actor-level attribution

Do not group files that have different actor histories. For each action, identify what the
person actually did; do not convert review, execution, adoption, or acceptance into a claim
of original authorship.

| Component or exact paths | Original human author(s), if known | Accepting maintainer's personally performed design, writing, review, change, or execution | Action date(s) | Supporting record | Include, rewrite, regenerate, or exclude |
|---|---|---|---|---|---|
| Specification and limitations | | | | | |
| Generator, splits, and synthetic-data schema | | | | | |
| Models, metrics, and calibration | | | | | |
| Guards, policy, routing, and release gates | | | | | |
| Guarded-update evaluation | | | | | |
| Monitoring and operational templates | | | | | |
| Tests, stored results, and manifest | | | | | |
| Reproduction and development records | | | | | |
| Monorepo integration, export procedure, and comparison tooling | | | | | |

## 3. Source derivation and publication rights

Identify every starting source, dependency, and reused contribution. If an actor, source,
or publication right cannot be established, record that result and remove or rewrite the
affected component from documented, rights-cleared sources before freeze.

| Component or exact paths | Starting source, prior work, dependency, or outside assistance | License or other permission | Employer/customer material, equipment, account, or credential used? | Rights decision and supporting record | Disposition |
|---|---|---|---|---|---|
| Specification and limitations | | | | | |
| Generator, splits, and synthetic-data schema | | | | | |
| Models, metrics, and calibration | | | | | |
| Guards, policy, routing, and release gates | | | | | |
| Guarded-update evaluation | | | | | |
| Monitoring and operational templates | | | | | |
| Tests, stored results, and manifest | | | | | |
| Reproduction and development records | | | | | |
| Monorepo integration, export procedure, and comparison tooling | | | | | |

## 4. Clean reproduction

| Field | Entry |
|---|---|
| Reproducer name, relationship, and required disclosures | |
| Clean machine/account attestation and date: neither previously held candidate or source monorepo; basis | |
| Verified bundle SHA-256, commit hash, and tree hash | |
| Environment, dependency artifact identities, numerical builds, thread settings, and lock SHA-256 | |
| Package-cache status; setup, test, and run times | |
| Commands and assistance used | |
| Actual tests collected, passed, failed, and skipped; retained output | |
| Fresh run 1: decision; `results.json` and `MANIFEST.json` SHA-256 | |
| Fresh run 2: decision; `results.json` and `MANIFEST.json` SHA-256 | |
| Guarded-update decision(s), failed gates, and excluded ranking gate observed | |
| Dataset SHA-256 | |
| Prespecified field-level protocol path, SHA-256, freeze date, platform, and rationale | |
| Exact invariants, per-field differences/tolerances, and full comparison outcome | |
| Deviations, errors, or unresolved variance | |

## 5. Maintainer acceptance or rejection

Complete every field for the exact artifact identified in § 1. A rejection or qualified
decision is retained and does not authorize publication.

| Maintainer decision field | Entry |
|---|---|
| Maintainer name | |
| Exact source M, tree T, export E, bundle, result, and manifest identifiers reviewed | |
| Review date and materials reviewed | |
| What the maintainer personally designed | |
| What the maintainer personally wrote | |
| What the maintainer personally reviewed | |
| What the maintainer personally changed | |
| What the maintainer personally ran or observed | |
| Components authored or contributed by others | |
| Source-derivation and rights review completed | |
| Employer/customer material, equipment, accounts, or credentials remaining | |
| Tests, gate results, and decisions observed | |
| Known defects, adverse/null results, and limitations | |
| Decision — `ACCEPT`, `REJECT`, or `QUALIFIED` | |
| Qualifications, required corrections, or reason for rejection | |
| Publication authorized for this exact artifact — `YES` or `NO` | |
| Maintainer signature and date | |

## 6. Publication (complete only after publication)

| Field | Entry |
|---|---|
| Maintainer-controlled public repository URL (planned: BichengWang/ai-decision-system) | |
| Published monorepo source commit M-public; evidence its project tree equals T | |
| Standalone release branch (planned: relia-release) | |
| Publication date | |
| Release URL and date | |
| Annotated tag name (relia/v<version>) and tag-object ID | |
| Published standalone commit E and root tree T | |
| Fresh public retrieval record: same accepted E/T, tag object, and artifact checksums | |
| Consent and location for any published reproduction report; accepted E/tag unchanged | |
