# Development results — relia v0.1.5 candidate (spec candidate 0.1.3)

All data are synthetic. These results do not establish real-world performance, legal compliance, or fairness across real populations. See `docs/LIMITATIONS.md`.

- results.json SHA-256: `59dfe7ba224d220d26e5d97871078ffa2f8b9806e6446c684783cd96fabf6eb6`
- dataset SHA-256: `c49c2a981d6f8e34fe310b185ee28279c5e3b6fc27f0c547ef822e31235d1abe`
- partitions (rows): {'train': 108228, 'calib': 12005, 'test': 11927}; time boundaries (day): [72, 96]

## Release gates (worst of five seeds)

| Gate | Value | Rule | Result |
|---|---:|---|---|
| prohibited_field_access | 0.0 | <= 0 | PASS |
| constraint_violations | 0.0 | <= 0 | PASS |
| critical_review_routing_rate | 1.0 | >= 1.0 and fixture_n >= 12 and noncritical_misroutes <= 0 | PASS |
| logloss_delta_vs_baseline | -0.00808 | <= 0.0 | PASS |
| brier_delta_vs_baseline | -0.001705 | <= 0.0 | PASS |
| ece | 0.016152 | <= 0.03 | PASS |
| worst_slice_ece | 0.043802 | <= 0.05 and eligible_slices >= 1 | PASS |
| near_equivalent_input_stability | 0.999832 | >= 0.995 | PASS |
| ranking_ndcg_gain_vs_baseline | 0.009535 | >= 0.0 | PASS |

Human-review fixture: 12/12 required-review cases routed; 0/4 nonrequired cases routed (16 total boundary cases).


**Release decision: PASS**

## Held-out test metrics (mean [min, max] over five seeds)

| Metric | Baseline (logistic) | Candidate (gradient-boosted) |
|---|---|---|
| Log loss | 0.5688 [0.5688, 0.5688] | 0.5604 [0.5600, 0.5607] |
| Brier | 0.1904 [0.1904, 0.1904] | 0.1885 [0.1884, 0.1887] |
| ECE (15 bins) | 0.0148 [0.0148, 0.0148] | 0.0151 [0.0142, 0.0162] |
| Ranking NDCG@10 | 0.9105 [0.9105, 0.9105] | 0.9208 [0.9201, 0.9212] |
| Ranking MRR | 0.9256 [0.9256, 0.9256] | 0.9327 [0.9313, 0.9343] |

Worst-slice ECE: 0.0372 [0.0301, 0.0438]. Near-equivalent-input stability: 0.9999 [0.9998, 1.0000].

## Drift (train vs. test period, seed 11)

Status **WARN**; score PSI 0.0046; feature PSI basket_value 0.0583, distance_km 0.0006, merchant_quality 0.1340.

## Guarded incremental cycle

Decision: **REJECT_UPDATE_KEEP_CURRENT_REFERENCE** (worst of 5 seeds; n_test=5950; 8 applicable gates; ranking alone excluded). Delta comparator: **current_reference**.

| Model | Log loss | Brier | ECE |
|---|---:|---:|---:|
| current_reference | 0.5540 [0.5531, 0.5553] | 0.1863 [0.1862, 0.1867] | 0.0165 [0.0140, 0.0189] |
| updated_candidate | 0.5540 [0.5525, 0.5553] | 0.1857 [0.1853, 0.1858] | 0.0156 [0.0113, 0.0188] |

| Gate | Value | Rule | Result |
|---|---:|---|---|
| prohibited_field_access | 0.0 | <= 0 | PASS |
| constraint_violations | 0.0 | <= 0 | PASS |
| critical_review_routing_rate | 1.0 | >= 1.0 and fixture_n >= 12 and noncritical_misroutes <= 0 | PASS |
| logloss_delta_vs_current_reference | 0.002229 | <= 0.0 | FAIL |
| brier_delta_vs_current_reference | -0.000323 | <= 0.0 | PASS |
| ece | 0.018806 | <= 0.03 | PASS |
| worst_slice_ece | 0.069241 | <= 0.05 and eligible_slices >= 1 | FAIL |
| near_equivalent_input_stability | 0.999832 | >= 0.995 | PASS |
