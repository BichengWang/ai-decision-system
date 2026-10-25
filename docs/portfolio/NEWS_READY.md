# News and reviewer briefing

Prepared 2026-10-11. **First-party announcement and editorial pitch**, not independent reporting, peer review, a press placement, or a product-release certification. The [technical report](PUBLICATION_REPORT.md) is the claim authority; [source notes](NIW_SOURCE_NOTES.md) explain the NIW evidence boundary.

## Announcement copy

### AI decision-system portfolio makes local controls and adverse results inspectable

Bicheng (Kenneth) Wang's AI decision-system research repository documents four independent Python projects for evaluating model recommendations and controlling bounded decisions: RELIA, experiment-gate, Jev decision, and decision-control.

The portfolio now includes a reproducible publication-evidence workflow that invokes each project's existing checks and demonstrations, retains commands and logs, identifies tested source files by SHA-256, and verifies expected outcomes—including rejected updates and failed adverse fixtures. It does not call a model provider or combine the four projects into a production system.

A reporting correction in Jev decision distinguishes explicitly gated evaluations from ungated descriptive metrics. CLI reports now use PASS, FAIL, or UNGATED; ungated evaluations return a separate non-success exit code. A provenance manifest records exact input and output hashes and makes clear that supplied replay responses are not authenticated provider output.

The demonstrations cover synthetic commerce release controls, A/B experiment decisions, hand-authored typed-answer evaluation, and actual local SQLite ticket reassignment with persistent review and replayable evidence. Their public technical report preserves limitations and adverse outcomes rather than implying every candidate should ship.

These are local software demonstrations. They do not establish real-world savings, calibrated live-model quality, deployed safety, independent adoption, or national impact. RELIA remains an unreleased candidate with no license grant pending its existing rights and release-acceptance process. Other components' permissions follow their own project files; this announcement does not extend them.

Technical methods, observed outcomes, reproduction instructions, and evidence gaps are documented in the repository's [publication report](PUBLICATION_REPORT.md). Interested technical reviewers can assess the scoped workflows and disclose their methods, relationship to the author, and any limitations or unfavorable findings. No endorsement is implied by this invitation.

## Editorial pitch

**Subject:** Reproducible AI decision controls that retain “do not ship” evidence

The technical story is not a new foundation model. It is an inspectable approach to the decisions around models: evaluating a candidate, analyzing an experiment, distinguishing descriptive metrics from a real gate, and ensuring a recommendation does not itself authorize a local action.

The repository supplies concrete, credential-free demonstrations and an author-produced report. A useful independent story would test whether these bounded controls help a real operator and what remains missing—not reproduce the author's claims as verified impact. A journalist or reviewer should be able to inspect the evidence and report adverse findings.

**Available demonstrations:** synthetic RELIA release/update decisions; experiment SHIP/HOLD/ROLLBACK/INVALID cases; Jev gated versus ungated replay; decision-control ALLOW/REVIEW/DENY/ABSTAIN with local database changes.

**Known limitations:** synthetic/hand-authored inputs; no independently measured live-provider performance or production adoption; local-host trust rather than identity authentication; separate project boundaries; RELIA's uncleared release rights.

**Contact:** repository maintainer through the [public repository](https://github.com/BichengWang/ai-decision-system). No journalist, customer, or independent expert endorsement is claimed.

## Publication checks

1. Link the exact public report/source revision and its evidence summary. State whether it is a development branch or accepted release; do not turn a merged PR into a RELIA release.
2. Check every number against the identified run; retain rejected updates and failed fixtures. Do not describe fixture accuracy as model performance.
3. Keep the announcement first-party. Disclose paid placements, sponsorship, syndication, author involvement, and editorial status wherever applicable. A new website URL alone does not create independence.
4. Obtain permission before quoting a reviewer or sharing private correspondence, ticket data, employer material, or upstream artifacts. RELIA distribution/reuse needs its separate rights clearance.
5. Retain actual publication URL, date, outlet/byline, disclosures, exact published text, and any later corrections. This preparation is not proof of press coverage.
6. For an EB-2 NIW file, keep this report as technical-progress material. Obtain person-specific eligibility documents and genuine corroboration; do not claim a legal determination from software verification.

## Questions an independent reviewer should answer

- Which exact source and output identities were examined? Were the workflows actually executed?
- What relationship, compensation, referral, and other interests exist?
- Are labels, data, thresholds, baselines, and uncertainty suitable for the intended application?
- What adverse results or defects were found? Could the controls be bypassed by the host/operator?
- Has any real user adopted the work, for which task, and with what attributable result?
- What evidence supports transferability beyond one employer, and what remains conjecture?

Record actual answers and permission to publish them; do not prewrite favorable endorsements.
