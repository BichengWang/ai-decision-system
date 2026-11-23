# Phase 3: external evidence (2027-03-01 → 2027-05-31)

Goal: someone unaffiliated reproduces and verifies the records, a pilot result is
published with permission whatever it shows, and the method is written up.

RELIA's own release, reproduction and holdout milestones follow its
[roadmap](../ai-workflows/ai-decision-reliability/docs/ROADMAP.md); the reviewer
recruited for P-029 may also serve RELIA's reproduction if RELIA is frozen by then.

| ID | Task | Owner | Depends on | Acceptance |
| --- | --- | --- | --- | --- |
| P-028 | **Regulatory mapping.** `docs/REGULATORY_MAPPING.md`: for each record type, which fields serve EU AI Act Article 12(2)(a)–(c) logging, Articles 19 and 26(6) retention, ISO/IEC 42001 A.6.2.8 and NIST AI RMF MANAGE 4.1, and what each record does not cover. Cites the consolidated EUR-Lex text, including the application dates set by Regulation (EU) 2026/1744. **Status: drafted at [docs/REGULATORY_MAPPING.md](../docs/REGULATORY_MAPPING.md) and re-mapped to the current schema versions, replay rule and signing after P-011 and P-012 landed; owner review pending. The 2 December 2027 Annex III date is confirmed on EUR-Lex (2026-10-19). ISO/IEC 42001 text was not reviewed (paywalled). Re-map when a schema version or signing behavior changes** | agent drafts; owner reviews | P-011 | Every row cites primary text; the document makes no compliance claim and says so; dates match EUR-Lex |
| P-029 | **Unaffiliated reproduction.** A person with no relationship to the owner or the code installs 0.2.x from PyPI on a clean machine, runs the README quickstart, verifies the conformance vectors through the non-Python path, and reports any outcome with the disclosures used by RELIA's [reproduction form](../ai-workflows/ai-decision-reliability/docs/REPRODUCE.md) | owner recruits; agent supports | P-023 | A dated reproduction record with disclosures and the reviewer's permission to publish, by **2027-04-30**; defects it finds are fixed with regression tests |
| P-032 | **Pilot record.** Run the pilot frozen in Phase 2 (P-027) and publish the result, positive, negative or null, with the team's permission | owner; agent runs analysis | P-027 | Record published by **2027-05-15** with the frozen protocol, the decision records, and the team's written permission; or a dated note explaining why it was not run |
| P-030 | **Preprint.** "Re-verifiable records for AI go/no-go decisions": record design, the canonical-form finding, conformance and golden vectors, signing, bridges, pilot and reproduction outcomes, limits. Venue chosen in March after checking workshop deadlines | agent drafts; owner owns authorship | P-029, P-032 | Posted to arXiv by **2027-05-31**; every number traces to a committed record |
| P-031 | **Quarterly review and JOSS gate.** Compare [decisions.md](decisions.md) with the [success measures](README.md#success-measures); report PyPI downloads without mirrors. Check [JOSS](https://joss.readthedocs.io/en/latest/submitting.html) gates: more than six months of public development (expgate since 2026-09-24, decision-control since 2026-10-11) and demonstrated research use | owner | – | Decisions updated and the next two phases planned; JOSS submitted only if every gate is met with evidence |

## Status (2026-10-19)

| ID | Status | Evidence, or the exact owner action needed |
| --- | --- | --- |
| P-028 | **Drafted; owner review pending** | [docs/REGULATORY_MAPPING.md](../docs/REGULATORY_MAPPING.md) (#247, then re-mapped to the current schemas, replay rule and signing in #258). It makes no compliance claim. The 2 December 2027 Annex III date was confirmed on EUR-Lex on 2026-10-19; ISO/IEC 42001 text is paywalled and was not reviewed. The owner reviews it; it needs re-mapping whenever a schema version or signing behavior changes |
| P-029 | **Blocked on owner** | The owner recruits a person with no relationship to the owner or the code. Needs 0.2.x on PyPI (P-023, blocked on P-020 and owner release; P-016 done). Due 2027-04-30. No reproduction record exists |
| P-032 | **Blocked on owner** | The owner needs a pilot team (P-027 is only a drafted template) and its written permission. Due 2027-05-15, or a dated note why it was not run |
| P-030 | **Blocked on P-029 and P-032** | The preprint needs the reproduction and pilot outcomes; no preprint draft is committed in this repository. The workshop draft in [docs/paper/](../docs/paper/README.md) belongs to P-037 and holds neither outcome. Due 2027-05-31; every number must trace to a committed record |
| P-031 | **Not started; owner** | Quarterly review and JOSS gate check. No JOSS submission is planned until every gate is met with evidence |

## Exit criteria

- [ ] **Not met (2026-10-19):** One unaffiliated reproduction recorded. None exists; P-029 is blocked on the owner.
- [ ] **Not met (2026-10-19):** One pilot result published, whatever it shows, or a dated reason it was not. No pilot team exists (P-027, P-032).
- [ ] **Not met (2026-10-19):** Preprint posted. Blocked on P-029 and P-032 (P-030).
