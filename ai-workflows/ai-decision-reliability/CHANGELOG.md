# Changelog

Each entry describes the candidate at the stated date; older release-status statements are
historical snapshots.

## 0.1.5 candidate — 2026-09-19 (unreleased)

- Integrated the project into `BichengWang/ai-decision-system` at `ai-workflows/ai-decision-reliability/`, retaining its independent environment and lockfile and targeting the Python 3.13 series with the existing 3.13.7 reproduction pin.
- Defined a project-only `relia-release` export and annotated `relia/v<version>` tag scheme. The reviewed monorepo commit and standalone export commit are distinct; their project/root trees must match, and the accepted export commit must survive publication unchanged.
- Aligned frozen execution, clean-machine/account disclosures, per-field comparison requirements, and external release records with that layout. Added a comparison helper and regression coverage; record the actual suite count and outcome for this candidate rather than inheriting 0.1.4's count.
- Added a technical report and explicit project license scope. Rights clearance, license grant, maintainer acceptance, unaffiliated reproduction, and public release remain pending.
- Retained specification `0.1.3`: the generator, partitions, metrics, thresholds, models, gates, and benchmark semantics are unchanged. Regenerated version-bearing artifacts; the result content matches the historical 0.1.4 result after excluding the package-version field. The full 35-test suite passed locally and two explicit fresh runs produced identical result and manifest bytes. Historical 0.1.4 checksums do not identify this candidate. These checks are development validation, not clean-machine or unaffiliated reproduction.

## 0.1.4 candidate — 2026-09-18 (unreleased)

- Made the command return exit status `1` after writing a primary `BLOCK` result, while a primary `PASS` returns `0`, so automation cannot mistake a blocked candidate for a successful release decision.
- Made `--out` reject files and nonempty directories before evaluation begins; a new path or existing empty directory remains valid, preventing a retry from mixing stale and new artifacts.
- Added regression tests for both release controls. The candidate now contains 12 tests.
- Expanded the existing release-record template with blank actor-level attribution, source-derivation and rights, clean-reproduction, and maintainer acceptance-or-rejection fields; aligned the publishing and security controls to one external completed copy of that record; and identified the initial blocked-run document as a preserved historical summary because its source artifacts are not retained in this candidate.
- Neutralized case-specific wording in the public candidate and kept completed attribution, rights, acceptance, and disclosure records outside the tracked release.
- Kept specification version `0.1.3`: the release-control fixes do not change the generator, partitions, metrics, thresholds, gates, models, or stored adverse decision. Regenerated development artifacts under package candidate `0.1.4`.
- No public repository, annotated tag, or release exists.

## 0.1.3 candidate — 2026-09-17 (superseded before release)

- Connected the live `decide()` path to the same `route_to_human()` function exercised by the fixed review fixture. Candidate 0.1.2 correctly tested the router but the decision path called the underlying predicate directly, so that gate could validate an orphan helper rather than the path it described.
- Made the fixture resolve the live router at call time and added a negative test showing that a faulty router changes both live decision routing and the fixture result.
- Made the worst-slice gate report its eligible-slice count and block when no slice meets the frozen minimum size; added a negative zero-eligible-slice test.
- Replaced the three-field denylist guard with an authorized-feature allowlist, so model/policy reads of labels, synthetic truth, identifiers, metadata, or named sensitive proxies all count as violations; expanded negative tests accordingly.
- Removed the duplicate `requirements.txt` dependency list; `pyproject.toml` and `uv.lock` are the sole dependency authorities.
- Removed the premature Apache-2.0 license grant and package metadata while ownership and publication rights remain unconfirmed; the cleared license is to be added before the exact release commit is frozen.
- Regenerated development artifacts. The primary candidate still passes all nine gates; the guarded update remains rejected on two of eight applicable offer-model gates.
- No public repository, annotated tag, or release exists.
- Later review found that the CLI returned success for a primary `BLOCK` and permitted reuse of a nonempty output directory. It was never published or tagged and is superseded by 0.1.4.

## 0.1.2 candidate — 2026-09-17 (superseded before release)

- Replaced the self-confirming review fixture with fixture-owned expected labels independent of the router under test. The existing review gate still counts as one of nine gates and now requires 12/12 required cases routed and 0/4 nonrequired controls routed.
- Made the constraint counter reject a decision outside the exact permitted discount set instead of mapping it to the nearest permitted level.
- Added negative tests for a faulty review router, nonrequired-case misrouting, and a non-enumerated discount.
- Added MRR to the human-readable results summary; it was already present in the machine-readable per-seed record.
- Required per-metric tolerances, unchanged primary and guarded-update decisions, and unchanged gate dispositions for noncanonical reproduction.
- Converted the future roadmap from calendar-assigned release numbers to evidence milestones; specified a prospectively frozen holdout protocol and local artifact-level rollback drills.
- Regenerated development artifacts. The primary candidate still passes all nine gates; the guarded update remains rejected on two of eight applicable offer-model gates.
- No public repository, annotated tag, or release exists.
- Later review found that the fixed router was tested independently but the live decision path called the underlying predicate rather than that router. It was never published or tagged and is superseded by 0.1.3.

## 0.1.1 candidate — 2026-09-17 (superseded before release)

- Replaced the vacuous zero-denominator human-review check with a deterministic 16-case fixture containing 12 required-review cases. The existing routing gate now also requires a fixture denominator of at least 12; the primary benchmark still has nine gates.
- Changed the guarded offer-model update cycle from one seed to all five fixed seeds, restored the specification's 500-row minimum slice size, measured review routing on the same fixture, and made ranking the sole excluded gate (eight applicable gates).
- Added negative gate coverage for Brier degradation, NDCG degradation, and an empty human-review denominator.
- Renamed the simulated reference-result field to `current_reference`; nothing in this repository is deployed or released.
- Made comparative gate labels comparator-aware and recorded comparator metadata, so the primary run remains labeled against `baseline` while the guarded update is labeled against `current_reference`.
- Aligned the emitted stability-gate label with the specification's `near_equivalent_input_stability` terminology.
- Kept the excluded ranking gate's identity as `ranking_ndcg_gain_vs_baseline`; the guarded update does not evaluate that gate and therefore does not assign it the update comparator.
- Qualified smoke/canary steps as deployment-specific and conditional; this repository does not implement a canary protocol.
- Scoped byte-identical reproduction to `results.json` and `MANIFEST.json`, excluding machine-dependent `runtime.json`, and added a commit/tree/bundle chain plus clean-machine/account attestation for prepublication reproduction.
- Regenerated development results. The primary candidate passes all nine gates; the guarded update remains rejected, now on worst-of-five-seed evidence.
- Narrowed future scope to synthetic digital-commerce pricing, offers, ranking, and recommendation scenarios. Recorded Apache-2.0 as the intended future license in package metadata; no license grant is made before rights clearance and addition of the actual license text.
- Later review found that the fixture derived expected routing from the router's own predicate and did not score its four nonrequired controls, while the constraint counter mapped arbitrary discounts to the nearest permitted level. It was never published or tagged and is superseded by 0.1.2.

## 0.1.0 candidate — 2026-09-17 (superseded before release)

- Prepared the initial pre-release specification, implementation, and development results for maintainer review.
- Subsequent review found that its human-review gate could pass with zero critical cases and that its guarded update evaluated only one seed with a 200-row slice threshold. It was never published or tagged and is superseded by 0.1.1.
