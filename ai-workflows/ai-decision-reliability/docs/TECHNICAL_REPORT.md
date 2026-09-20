# RELIA reference implementation: scope, method, and evidence

Package candidate 0.1.5; specification 0.1.3. This technical report describes an
unreleased synthetic reference implementation. Maintainer acceptance, rights
clearance, unaffiliated reproduction, and public release remain separate events.

## Problem and intended users

Teams operating commerce offer-selection and ranking models need inspectable
checks for leakage, calibration, prohibited input dependencies, policy violations,
review routing, and deterioration after a model update. RELIA supplies a small
CPU-only example of those checks and their records. Intended readers are engineers
and evaluators who need a concrete starting point for their own scenario-specific
validation; usefulness to an outside team has not yet been established by adoption.

The offer task chooses a permitted discount or no offer for a synthetic session.
It does not change an individualized base price. The ranking task orders a fixed
synthetic candidate set; it does not evaluate retrieval recall or customer behavior.

## Evaluation method

The deterministic generator produces 120 days of commerce sessions and assigns
merchants to distinct partitions. The time split is 60/20/20; rows whose time and
merchant partitions disagree are discarded. A regularized logistic baseline and
gradient-boosted candidate are calibrated only on the calibration partition.
Five fixed seeds vary model training, not the underlying dataset. The release
decision evaluates the worst seed for each of nine gates.

Controls include an authorized-feature record view, enumerated policy decisions,
a 16-case review fixture with independently specified expected labels, minimum
eligible slice sizes, and stability under the specified near-equivalent inputs.
One later-period offer-model update is compared with each seed's current reference
using eight applicable gates. Ranking is recorded as excluded from that update.
The full definitions, denominators, and thresholds are in [SPEC.md](SPEC.md).

The input guard only observes access through its record view. The review fixture
tests routing; it does not show that a person reviewed a decision or that a queue
delivered a case. A guarded-update rejection represents a simulated control
decision, not a production rollback. See [LIMITATIONS.md](LIMITATIONS.md).

## Recorded results and interpretation

The identified stored results are [RESULTS.md](../results/RESULTS.md),
[results.json](../results/results.json), and [MANIFEST.json](../results/MANIFEST.json).
The reference primary candidate passes all nine gates. The proposed guarded update
is rejected because the worst-seed log-loss-delta and worst-slice-ECE gates fail;
the retained decision is `REJECT_UPDATE_KEEP_CURRENT_REFERENCE`.

These are point estimates on synthetic data. The generator was changed during
development after an earlier blocked run; the [development log](DEVELOPMENT_LOG.md)
and [limitations](LIMITATIONS.md) retain that history. The results do not establish
statistical superiority, fairness in real populations, legal compliance, commercial
performance, consumer benefit, or transferability to a particular organization.
The earlier blocked-run document is a historical summary, not a retained executable
version that this candidate can reproduce.

## Reproduction and distribution

The framework has its own Python pin, dependency lock, and source layout inside the
development monorepo. A standalone release export must have exactly the reviewed
project tree, and its accepted commit is preserved when publicly tagged. Two fresh
runs in one environment must have identical result and manifest bytes. Comparisons
against a stored result from a different environment require a field-level protocol
fixed before execution, matching decisions/gate dispositions, and disclosed variances.

[REPRODUCE.md](REPRODUCE.md) defines the procedure, reviewer disclosures, environment
record, and report form. The comparison helper checks a supplied protocol; it cannot
prove when that protocol was fixed or that a reviewer is independent. CI and local
verification are automation records, not unaffiliated reproduction attestations.

## Adaptation and next evidence

An adapting team must supply its own appropriate data, partitions, input permissions,
decision constraints, thresholds, and human-review operation. Passing this reference
benchmark does not validate those choices. The [roadmap](ROADMAP.md) proposes further
commerce scenarios, portability work, external reproduction, and artifact-level
incident drills. Each completed activity should retain its dated protocol, actual
findings, defects, and limitations.

The [NIST crosswalk](NIST_AI_RMF_CROSSWALK.md) is a proposed mapping for inspection,
not certification or agency endorsement. Its individual authority references need
review before publication. [Licensing status](../LICENSE) remains unresolved for
public release; this report grants no additional rights.
