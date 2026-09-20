# Reliability-evaluation framework for real-time commerce decision systems

This package (import name `relia`) is a small, deterministic reference implementation of the release and
operating controls a team needs before and after it ships a machine-learning model that
makes real-time commercial decisions: which offer or discount to show, or how to rank the
candidates returned by a retrieval or recommendation system.

The framework addresses five failure classes: evaluation
leakage, poor calibration (overall or on a weak product category), use of inputs the model
should never read, decisions that escape stated constraints, and silent degradation after
the data shift or a retrained model is promoted. This framework makes these controls
inspectable and reproducible using a deterministic synthetic benchmark. No company's data,
code, or business logic is required to run it. Publication and reuse rights remain subject
to the license status below.

The scope is intentionally bounded to synthetic digital-commerce pricing, offers, ranking,
and recommendation. The roadmap deepens those scenarios (contextual recommendation,
merchant promotions, and, in Year 3, retrieval-augmented and agent-mediated purchasing
decisions) rather than expanding into a general-purpose automation framework.

## What is in package candidate 0.1.5 (specification 0.1.3)

Development belongs in `projects/ai-decision-reliability-framework/` on the `main` branch of
[`BichengWang/ai-decision-system`](https://github.com/BichengWang/ai-decision-system).
The project keeps its own Python environment and lockfile. Candidate 0.1.5 adds monorepo
integration, comparison tooling, and publication records while retaining specification
0.1.3's generator, metrics, gates, and benchmark semantics. It remains **unreleased**.

| Area | What the kit provides |
|---|---|
| Frozen evaluation | Time- and group-separated train / calibration / test partitions with an explicit leakage assertion; five fixed training seeds; a regularized logistic baseline and a gradient-boosted candidate |
| Calibration | Isotonic calibration fitted only on the calibration partition; log loss, Brier score, expected calibration error (ECE), worst-slice ECE, Murphy reliability/resolution decomposition |
| Input guard | An allowlisted record view that counts any model/policy read outside the authorized feature set (labels, truth fields, identifiers, named sensitive proxies) so an accidental dependency blocks release |
| Policy constraints | Deterministic eligibility, exact permitted discount levels, and per-category maximum-discount rules; constraint-violation counter |
| Human review | A fixed 16-case boundary fixture with router-independent expected labels; the gate requires 12/12 required cases routed and 0/4 nonrequired controls routed |
| Stability | At least 99.5% of near-equivalent pairs that differ only in prohibited fields and a sub-cent basket-value perturbation must receive the identical decision |
| Ranking module | Baseline vs. candidate ranker on a graded-relevance fixed-candidate task (the ranking step that follows retrieval); NDCG@10 and MRR |
| Drift | Population-stability index on model scores and monitored features, with OK / WARN / ALERT states |
| Release gates | Nine gates evaluated on the **worst** of five seeds; any failure blocks release |
| Guarded model updates | One update cycle on a later synthetic period across all five seeds; eight offer-model gates apply, with the unchanged ranking gate recorded as excluded |
| Operations materials | Decision-log schema, alert-to-action matrix, blank incident and release records, deployment-adaptation rollback procedure |
| Standards and regulatory mapping | [`docs/NIST_AI_RMF_CROSSWALK.md`](docs/NIST_AI_RMF_CROSSWALK.md): which NIST AI RMF 1.0 Core subcategories each control implements, and which record answers which question regulators now ask pricing operators |

## Quick start

On the monorepo's development branch, first enter
`projects/ai-decision-reliability-framework/`. In a future standalone release clone, run
these commands from the clone root. Python 3.13 is the declared series, with 3.13.7 pinned
for candidate reproduction; the monorepo's root research environment is not required.

```bash
uv sync --frozen
uv run --frozen python -m pytest -q
uv run --frozen python -m relia.run --out review-run
cat review-run/RESULTS.md
```

The output directory must be new or empty; preserve earlier runs under their original
names. The full suite executes benchmark runs, so record measured setup and test times.

Two fresh runs in one environment produce byte-identical `results.json` and `MANIFEST.json`
(and SHA-256 hashes). `runtime.json` is machine-dependent and excluded from that claim.
Equality with the stored `results/results.json` hash is expected only in the producing
environment with the same dependency artifacts and execution settings; on another platform,
fix per-metric tolerances before running and require every decision and gate disposition to
match. See [`docs/REPRODUCE.md`](docs/REPRODUCE.md) for the reproduction protocol and form.

## Current results

See [`results/RESULTS.md`](results/RESULTS.md) for the version identified by the stored
artifacts and [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) for their interpretation.
Local validation of candidate 0.1.5 records a primary nine-gate pass and
`REJECT_UPDATE_KEEP_CURRENT_REFERENCE` for the guarded update: the worst-of-five-seed
log-loss-delta and worst-slice-ECE gates fail against seed-matched current references.
Ranking is explicitly excluded from that offer-only update. The full 35-test suite passed,
and two explicit fresh local runs produced identical result and manifest bytes. These are
development checks, not unaffiliated reproduction or release acceptance. The first development run was blocked;
its preserved historical summary is in [`docs/dev-runs/`](docs/dev-runs/).

## What this is not

Synthetic results do not establish real-world commercial performance, legal compliance,
fairness across real populations, or consumer benefit. The gates are proposed engineering
thresholds, not government or industry standards, and every adaptation requires its own
evaluation. The crosswalk and regulatory map are the author's mappings; no agency has
reviewed or endorsed this framework. See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Documents

- [`docs/SPEC.md`](docs/SPEC.md) — specification 0.1.3 (decision, inputs, partitions, metrics, gates)
- [`docs/DATA_CARD.md`](docs/DATA_CARD.md) — synthetic data card
- [`docs/REPRODUCE.md`](docs/REPRODUCE.md) — clean-environment reproduction instructions and report form
- [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) — technical scope, retained evidence, and interpretation
- [`docs/NIST_AI_RMF_CROSSWALK.md`](docs/NIST_AI_RMF_CROSSWALK.md) — NIST AI RMF crosswalk and regulatory evidence map
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/DEVELOPMENT_LOG.md`](docs/DEVELOPMENT_LOG.md)
- [`templates/`](templates/) — blank incident and release records plus a deployment-adaptation rollback procedure

## Status, license, and maintainer

This is an unreleased development candidate. Publication is planned through a generated
`relia-release` branch in the same repository, with an annotated `relia/v<version>` tag
pointing to the exact standalone commit that was reproduced and accepted. Its root tree
must equal the reviewed monorepo project tree; the two commits have different identities.
No accepted release or tag is claimed here. See [`docs/REPRODUCE.md`](docs/REPRODUCE.md)
for the transfer and identity protocol.

No license grant is made for this candidate; see [`LICENSE`](LICENSE). Apache-2.0 is
intended only after publication rights are confirmed and the cleared license text and
metadata are included before freeze. The monorepo's root MIT license does not grant rights
to this project. Maintainer: Bicheng (Kenneth) Wang. See [`CONTRIBUTING.md`](CONTRIBUTING.md)
for reproduction and adaptation reports.
