# Roadmap

Calendar targets after the initial release depend on that release. If it slips, the new
date is recorded here and every dependent milestone is rescheduled prospectively; nothing is
backdated. Year 1 runs October 2026 through September 2027.

| Milestone | Target | Scope |
|---|---|---|
| Public comment on personalized-pricing evidence | September 2026 | Technical comment to the Federal Trade Commission's proposed Enforcement Policy Statement on Personalized Pricing (docket FTC-2026-1057) describing how input allowlists, input-access logs, decision records, and release records make the contemplated disclosures verifiable; publish the regulatory evidence map with the release |
| Initial public release (package 0.1.x; specification 0.1.3) | Within 60 days of the response | Prepare candidate 0.1.5 under `projects/ai-decision-reliability-framework/` in `BichengWang/ai-decision-system`; complete module and rights review; include the cleared license text and metadata before freeze; freeze source commit M and project tree T; export standalone commit E with root tree T; reproduce E on a qualifying clean machine/account; record maintainer acceptance; publish that same E on `relia-release` with an annotated `relia/v<version>` tag; include the technical report, NIST AI RMF crosswalk, and regulatory evidence map; retain source/export, bundle, tag, result, and manifest identities externally |
| Post-release validation | Q4 2026 | Portability run on a second operating system or processor architecture under per-metric tolerances fixed before the run; record setup/run time, peak memory and disk, and the hardware envelope the measurements support; extend the input guard to the ranking path; deliver the tagged release and reproduction form to at least three outside reviewers; target at least one completed unaffiliated clean-environment reproduction; register for a NIST/CAISI AI Agent Standards Initiative listening session or comment opportunity |
| Prospective ranking-and-recommendation holdout | Q1 2027 | Publish a tagged protocol fixing the generator and seed rule, candidate-set and query construction, partitions, models, NDCG@10 and MRR definitions and denominators, exclusions, thresholds, and analysis code before the holdout is generated; run once; preserve the first pass-or-fail result; any correction gets a new version and a different holdout |
| Incident drills and report | Q2-Q3 2027 | Two artifact-level drills (failed-gate trigger; artifact/hash-mismatch trigger) with detection, decision, reversion, verification, and elapsed time recorded; a drill passes only if the restored hash and rerun gate report match the last accepted release; second technical report; submission to a peer-reviewed venue or workshop on ML reliability or operations, with the acknowledgement retained |
| Adapter contract and additional scenarios | Year 2 (Oct. 2027-Sept. 2028) | Publish the adapter schema and mapping worksheet; implement the adapter contract; add category-aware contextual recommendation (missing context, catalog churn, out-of-stock filtering) and merchant-promotion offer selection (eligibility-rule changes, budget exhaustion) without changing base prices; invite at least one outside team to configure a new scenario under a pre-published protocol; resolve documented outside defects; publish portability notes; submit the AI RMF crosswalk to NIST's resource or comment process where one accepts profile-style contributions |
| Agent-mediated commerce decisions and stabilization | Year 3 (Oct. 2028-Sept. 2029) | Extend the same gates, review routing, and rollback controls to retrieval-augmented and agent-mediated purchasing decisions (an assistant that selects offers or ranks products for a shopper or merchant), the reliability concern NIST's AI Agent Standards Initiative raised in February 2026; stabilize the specification and interface; consolidate reproduction, issue, and limitation history into a practitioner guide; document the maintenance decision |

After the first release: quarterly progress notes; failed and null results retained; dated
outreach, responses, defects, and adaptations logged; reviews published only with the
reviewer's permission. A request is not a review, a review is not use, and interest is not
adoption.

These are targets, not completed activities. The current candidate is unreleased; Apache-2.0
remains an intended license pending rights clearance. Development validation and a new
directory on the maintainer's machine do not meet the unaffiliated clean-reproduction
definition. Use [`REPRODUCE.md`](REPRODUCE.md), preserve actual development and publication
dates, and keep completed reports outside the immutable accepted release commit.
