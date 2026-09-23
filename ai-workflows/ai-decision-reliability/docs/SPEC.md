# Candidate specification v0.1.3 (pre-release)

The metric definitions, thresholds, and evaluation protocol in this file and
`relia/config.py` are held constant for the current candidate. Any semantic change to them,
or any change after maintainer acceptance and freeze, requires a new candidate version, a
`CHANGELOG.md` entry, and regenerated results. Before that freeze, non-semantic metadata or
corrective text may remain within v0.1.3 if recorded in `CHANGELOG.md`; generated artifacts
must be regenerated whenever their content changes. Maintainer review, public release, and
an annotated tag remain pending.

## 1. Decisions under test

1. **Offer decision.** For each synthetic commerce session, decide whether the session is
   eligible for an offer and, if so, select one permitted discount level from
   {0, 5, 10, 20} percent, or return no offer. The system never changes an individualized
   base price.
2. **Ranking decision.** For each synthetic query, order 20 candidates; quality is measured
   against graded relevance labels (0-3).

## 2. Inputs

Authorized features: `basket_value, hour_sin, hour_cos, category, tenure_bucket,
merchant_quality, distance_km, is_weekend, discount`.

Only the authorized features above may be read through the model/policy record view. Any
other key—including labels, synthetic truth, identifiers, metadata, and the named sensitive
proxies `zip_income_proxy, device_price_tier, inferred_age_band`—increments the unauthorized-
access counter and blocks release. Evaluation code receives labels and partition metadata
separately; the guard does not police code that bypasses the record view.

## 3. Partitions

60 / 20 / 20 by simulated day (train / calibration / test). Every merchant is assigned to
exactly one partition; rows whose time partition and merchant partition disagree are
dropped. `assert_no_leakage` verifies that day ranges do not overlap and that merchant and
session identifiers do not cross partitions. The test labels are never used for fitting,
feature selection, threshold selection, or calibration.

A controlled covariate and concept shift begins on day 96, the first day of the test period.

## 4. Models

Baseline: standardized + one-hot regularized logistic regression. Candidate:
histogram gradient-boosted trees (depth 4, 250 iterations, learning rate 0.06, L2 1.0).
Both are calibrated with isotonic regression fitted on the calibration partition only.
Five fixed training seeds: 11, 23, 37, 41, 53.

## 5. Policy

Expected utility = P(response | discount) x basket x (margin 0.22 - discount). The policy
selects the highest-utility **permitted** level. Permitted means: discount <= the category
maximum (20, 20, 10, 10, 5, 20 percent) and basket >= 12.00 for any non-zero offer.
Critical cases (20 percent discount on a basket >= 90.00) are routed to human review.
Because no evaluated model decision happened to meet that definition, routing is gated on
a deterministic boundary fixture rather than on the observed-decision count. The fixture
has expected labels stored independently of the router: 12 required-review cases with
baskets from 90.00 through 300.00 at a 20 percent discount, plus four nonrequired controls
below a basket or discount boundary. All 12 required cases must route and none of the four
controls may route. The live decision path and the fixture both call the same router; the
fixture resolves that router at call time so a replaced or faulty router cannot be hidden
behind a previously captured default. A chosen discount outside the permitted set, tested with an absolute
numeric tolerance of 1e-12 and no relative tolerance, is a constraint violation; it is not
rounded or mapped to the nearest permitted level.

## 6. Metric definitions

| Metric | Definition | Denominator | Exclusions |
|---|---|---|---|
| Log loss | mean negative log-likelihood, probabilities clipped to [1e-7, 1-1e-7] | test rows | none |
| Brier | mean squared error of probability | test rows | none |
| ECE | sum over 15 equal-width bins of bin share x abs(mean p - mean y) | test rows | empty bins |
| Worst-slice ECE | maximum ECE across product categories; the eligible-slice count is reported and zero eligible slices blocks release | rows in slice | slices with fewer than 500 rows |
| Unauthorized-field access | count of model/policy reads outside the authorized feature allowlist through `GuardedRecords` | all reads through that view in the run | evaluation labels/metadata passed separately; direct raw-data bypass is outside the guard |
| Constraint violations | count of chosen discounts outside the permitted set | test decisions | none |
| Review-fixture routing | routed expected-required cases / expected-required cases; misrouted expected-nonrequired cases | 12 required cases; 4 nonrequired controls | none; an empty or undersized required denominator or any nonrequired misroute fails |
| Near-equivalent-input stability | share of pairs with identical decision after changing only prohibited fields and applying a sub-cent basket-value perturbation | test rows | none |
| NDCG@10, MRR (relevance >= 2) | standard definitions, gain 2^rel - 1 | test queries | queries with no relevant item (NDCG) |
| PSI | population-stability index, 10 reference-quantile bins | — | — |

## 7. Release gates (evaluated on the worst of five seeds)

| Gate | Rule |
|---|---|
| Prohibited-field access | = 0 |
| Constraint violations | = 0 |
| Review-fixture routing | = 100 percent, required denominator >= 12, and nonrequired misroutes = 0 |
| Log loss, candidate minus baseline | <= 0 |
| Brier, candidate minus baseline | <= 0 |
| ECE | <= 0.03 |
| Worst-slice ECE | <= 0.05 and at least one category slice has >= 500 rows |
| Near-equivalent-input stability | >= 99.5 percent |
| Ranking NDCG@10, candidate minus baseline | >= 0 |

These are proposed engineering gates, not government or industry standards. Comparative
gates are point estimates on one synthetic benchmark. The five seeds vary model training,
not the underlying dataset, and each gate's worst value may come from a different seed.
Passing does not establish statistical superiority or external validity.

## 8. Incremental learning

At most one planned update per cycle. For each of the five fixed seeds, the updated offer
model is trained only on newly generated synthetic data, calibrated, and compared with its
seed-matched **current reference** on the new period's held-out partition. The decision uses
the worst seed for all eight applicable offer-model gates, including the 500-row minimum for
worst-slice ECE and the measured review fixture. Ranking is the sole exclusion because the
cycle does not change or reevaluate the separate ranking model. Any failed gate rejects the
update.

## 9. Reproducibility and release identity

For two fresh runs in one executing environment, `results.json` and `MANIFEST.json`—and
the SHA-256 of each file—must be byte-identical. Machine-dependent `runtime.json` is
excluded. Equality with the stored result hash is limited to the attested producing
environment with the same dependency artifacts and execution settings; matching only
Python, OS, and architecture is insufficient. Before any other run, record each compared
numerical field's absolute and relative tolerances, including every per-seed field, and
their rationale. Both decisions, every gate disposition, counts, seeds, versions, exclusions,
and dataset identity remain exact invariants. Missing fields and nonfinite values fail the
comparison. Each named metric must satisfy its own frozen tolerance; do not assume the
stored hash will match. See [`REPRODUCE.md`](REPRODUCE.md) for the executable protocol.

Package candidate 0.1.5 is an unreleased integration of specification 0.1.3. Its canonical
development path is `ai-workflows/ai-decision-reliability/` in
`BichengWang/ai-decision-system`. Publication is planned through a generated `relia-release`
branch with the project at its root and an annotated `relia/v<version>` tag. No accepted
standalone release commit or tag is claimed. After provenance, rights, review, and acceptance
are complete, publish the same standalone commit that was reproduced. Record the monorepo
source commit, project tree, standalone export commit, bundle hash, and annotated tag object
externally; verify that the monorepo project tree equals the export's root tree. A matching
tree does not establish authorship or the age of the work.
Future work remains within synthetic digital-commerce pricing, offers, ranking, and
recommendation scenarios; see `ROADMAP.md`.
