# Crosswalk to the NIST AI Risk Management Framework (AI RMF 1.0)

**Status:** profile-style mapping prepared for the 0.1.x release. It shows which AI RMF 1.0 Core subcategories each control and record in this framework is designed to implement for one class of systems (real-time pricing, offer, ranking, and recommendation models). It is the author's mapping. NIST has not reviewed, certified, or endorsed this framework, and the AI RMF is voluntary. Subcategory wording below paraphrases AI RMF 1.0 (NIST AI 100-1, January 2023) and must be checked against the published Core before publication.

## Why a crosswalk

The AI RMF organizes trustworthy-AI practice into four functions (Govern, Map, Measure, Manage). It deliberately does not prescribe tests. This framework supplies executable tests, gates, and records for one system class. The crosswalk lets an adopting team show, subcategory by subcategory, which RMF outcomes the framework's artifacts produce, and which it does not.

## Mapping

| AI RMF function / subcategory (paraphrased) | Framework control or record | Evidence the framework produces |
|---|---|---|
| **MAP 2.3** Scientific integrity and TEVV considerations identified and documented: experimental design, data selection and representativeness, construct validity | Specification; deterministic synthetic generator with data card; time- and entity-separated partitions; leakage checks; fixed seeds; pre-registered holdout protocol (Q1 2027) | `SPEC.md`, `DATA_CARD.md`, partition report, holdout protocol tag |
| **MAP 3.5** Processes for human oversight defined, assessed, documented | Deterministic human-review routing with a 16-case boundary fixture (12 required-review cases must route; 4 controls must not) connected to the live decision path | Routing gate disposition; fixture and expected labels |
| **MEASURE 1.1** Approaches and metrics for measuring the most significant AI risks selected and implemented | Nine release gates covering leakage, calibration (overall and worst slice), prohibited-input use, constraint violation, review routing, stability, ranking quality, and harmful updates | Gate table with numerical rules; per-gate disposition |
| **MEASURE 2.1** Test sets, metrics, and TEVV tools documented | Versioned specification; metric definitions and denominators; fixed candidate set for ranking; test suite | `SPEC.md`; `tests/`; `RESULTS.md` |
| **MEASURE 2.3** Performance or assurance criteria measured and demonstrated for conditions similar to deployment | Evaluation on a held-out period with disjoint time and merchant partitions; worst-of-five-seeds aggregation | `results.json`; `MANIFEST.json` |
| **MEASURE 2.5** System demonstrated valid and reliable; limits of generalizability documented | Reproducibility hashes; two-execution byte-identity check; clean-environment reproduction form; `LIMITATIONS.md` stating what synthetic results do not show | Reproduction record; limitations statement |
| **MEASURE 2.6** Evaluated regularly for safety risks; deployment conditions where failure is unacceptable identified | Zero-tolerance gates for constraint violations and unauthorized-input reads; release blocked on any failure | Gate dispositions; blocked-release record |
| **MEASURE 2.8** Transparency and accountability risks examined and documented | Decision-log schema; release record that preserves the reason for every release, stop, or rejection | Decision logs; `templates/release-record.md` |
| **MEASURE 2.11** Fairness and bias evaluated and results documented | Worst-slice calibration gate with a minimum eligible denominator; near-equivalent-input stability gate (inputs differing only in prohibited fields must yield the same decision) | Slice report; stability result |
| **MEASURE 3.1** Approaches and documentation in place to identify and track existing, unanticipated, and emergent risks | Offline drift report (population stability); alert-to-action matrix; adverse and null results retained | Drift report; alert matrix; retained rejected update |
| **MEASURE 4.2** Measurement results informed by input from domain experts and relevant AI actors | Outside-review log; unaffiliated reproduction reports; defect and adaptation log | Review and reproduction records |
| **MANAGE 2.2** Mechanisms to sustain the value of deployed systems | Guarded model-update test: a retrained model is compared with the current reference on a new period across five seeds and rejected if any applicable gate fails | Update decision record (accepted or rejected, with excluded gates listed) |
| **MANAGE 2.3** Procedures to respond to and recover from a previously unknown risk | Incident record template; rollback procedure with restored-artifact hash verification; incident drills (Q2-Q3 2027) | `templates/incident-record.md`; `templates/rollback-procedure.md`; drill records |
| **MANAGE 2.4** Mechanisms and responsibilities to supersede, disengage, or deactivate systems inconsistent with intended use | Failing process status on a primary BLOCK; rollback to last accepted release; alert-to-action matrix mapping states to responses | Blocked-release exit status; rollback record |
| **MANAGE 4.1** Post-deployment monitoring plans, including appeal and override, incident response, recovery, change management | Monitoring records, review routing, incident and rollback procedures, versioned change control (new version and renewed reproduction for any substantive change) | Operational templates; version tags; change records |
| **MANAGE 4.3** Incidents and errors communicated to relevant actors and documented | Public retention of adverse results, defects, and incidents in release notes and progress notes | Release notes; quarterly progress notes |
| **GOVERN 1.5** Ongoing monitoring and periodic review of the risk-management process planned and organizational roles assigned | Adopter mapping worksheet requires named owners for each gate and record; maintenance decision documented in Year 3 | Mapping worksheet; maintenance record |
| **GOVERN 4.3** Practices enable AI testing, incident identification, and information sharing | Open license; public repository; reproduction form; outside-review and defect logs | Repository, release, and logs |

## What the crosswalk does not claim

This framework does not implement the full AI RMF, does not address subcategories concerning organizational governance beyond the adopter worksheet, and does not validate production-scale operation, real-world fairness, or legal compliance. An adopting team maps its own decision to the framework and remains responsible for its own RMF profile. The mapping is offered so that the evaluation and control outcomes the RMF describes can be produced by executable, reproducible artifacts rather than by narrative assurance.

## Planned use

- Published with the 0.1.x release and cited in the technical report.
- Submitted to NIST's AI RMF resource or public-comment process where such a process accepts profile-style contributions (Year 2 milestone); submission is recorded whether or not it is accepted, and no acceptance is claimed unless it occurs.

---

# Regulatory evidence map (added September 2026)

**Status:** informational mapping prepared with the 0.1.x release. It shows which record produced by this framework answers which question that U.S. regulators and legislators have recently asked operators of pricing, offer, ranking, and recommendation models. It is not legal advice, takes no position on what any law requires, and does nothing to personalize a price. An operator remains responsible for its own legal analysis. No agency has reviewed or endorsed this framework.

| Question now asked of operators | Source | Framework record that answers it |
|---|---|---|
| Does an algorithm use a consumer's personal data to set a price? | N.Y. Gen. Bus. Law § 349-a (Algorithmic Pricing Disclosure Act, eff. Nov. 10, 2025) | Input guard log: every model or policy read outside the authorized-feature allowlist is recorded and blocks release; the allowlist itself is a versioned declaration of what the model may read |
| Is the price personalized, on what basis, and using what types of data? | FTC proposed Enforcement Policy Statement on Personalized Pricing (Aug. 19, 2026; docket FTC-2026-1057) | Decision log (inputs, constraints, decision, version); versioned specification of declared inputs; release record stating what the model was evaluated on |
| What are the company's pricing testing practices? | House Committee on Oversight and Government Reform, surveillance-pricing investigation (Mar. 5, 2026) | Evaluation protocol (partitions, seeds, metrics, denominators); gate table and per-gate dispositions; retained adverse results; guarded-update test record |
| What pricing experiments were run, and what compliance controls exist? | California Attorney General surveillance-pricing sweep (Jan. 27, 2026) | Release records (why released, stopped, or rejected); constraint checks with zero tolerance; review-routing fixture; rollback procedure and drill records |
| Does the model's use of a common pricing algorithm follow anticompetitive coordination? | California AB 325 (eff. Jan. 1, 2026) | Versioned specification and provenance of inputs and models (what the model is and where its inputs come from); the framework does not detect coordination and makes no claim to |
| Can an AI agent that shops or sets prices be trusted to act reliably? | NIST AI Agent Standards Initiative (Feb. 17, 2026) | Year 3 scope: same gates, routing, and rollback applied to tool-using decision paths; not implemented in 0.1.x |

## What the map does not claim

The framework produces records; it does not determine legal sufficiency, does not implement any disclosure, and does not evaluate a company's actual pricing practices. Synthetic results say nothing about a particular operator's compliance. The map is offered so that operators, auditors, and regulators can see which executable, reproducible artifacts correspond to the questions being asked, instead of relying on narrative assurance.
