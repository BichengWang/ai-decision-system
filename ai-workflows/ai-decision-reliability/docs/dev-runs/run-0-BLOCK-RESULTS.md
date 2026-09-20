# Preserved summary record — development run 0, relia v0.1.0 candidate

All data are synthetic. These results do not establish real-world performance, legal compliance, or fairness across real populations. See `docs/LIMITATIONS.md`.

This file preserves reported summary values from an exploratory run. The source run directory, command transcript, environment record, and matching machine-readable artifacts are not retained in this candidate. It is therefore not a reproducible retained run or independent proof of execution. Treat the values below only as a historical summary of the reported blocked result.

- results.json SHA-256: `c223896fd5d4fe7695d01403617d0f995575ae9708e593d98d9887d4111f837e`
- dataset SHA-256: `d44fb5f11a09744a9c4a7759e2720fc7ef81e634acb34e5b42290de923b2b64c`
- partitions (rows): {'train': 21795, 'calib': 2339, 'test': 2326}; time boundaries (day): [72, 96]

## Release gates (worst of five seeds)

| Gate | Value | Rule | Result |
|---|---:|---|---|
| prohibited_field_access | 0.0 | <= 0 | PASS |
| constraint_violations | 0.0 | <= 0 | PASS |
| critical_review_routing_rate | 1.0 | >= 1.0 | PASS |
| logloss_delta_vs_baseline | 0.010353 | <= 0.0 | FAIL |
| brier_delta_vs_baseline | 0.001249 | <= 0.0 | FAIL |
| ece | 0.029827 | <= 0.03 | PASS |
| worst_slice_ece | 0.066241 | <= 0.05 | FAIL |
| equivalent_input_stability | 0.99957 | >= 0.995 | PASS |
| ranking_ndcg_gain_vs_baseline | 0.010035 | >= 0.0 | PASS |

**Release decision: BLOCK**

## Held-out test metrics (mean [min, max] over five seeds)

| Metric | Baseline (logistic) | Candidate (gradient-boosted) |
|---|---|---|
| Log loss | 0.5816 [0.5816, 0.5816] | 0.5881 [0.5840, 0.5920] |
| Brier | 0.1967 [0.1967, 0.1967] | 0.1975 [0.1972, 0.1980] |
| ECE (15 bins) | 0.0207 [0.0207, 0.0207] | 0.0245 [0.0205, 0.0298] |
| Ranking NDCG@10 | 0.9105 [0.9105, 0.9105] | 0.9209 [0.9206, 0.9212] |

Worst-slice ECE: 0.0605 [0.0546, 0.0662]. Equivalent-input stability: 0.9997 [0.9996, 1.0000].

## Drift (train vs. test period, seed 11)

Status **WARN**; score PSI 0.0077; feature PSI basket_value 0.0347, distance_km 0.0031, merchant_quality 0.1317.

## Guarded incremental cycle

Decision: **REJECT_UPDATE_KEEP_CURRENT_REFERENCE** (n_test=1232).

| Model | Log loss | Brier | ECE |
|---|---:|---:|---:|
| current_reference | 0.5849 | 0.1973 | 0.0262 |
| updated_candidate | 0.5942 | 0.1990 | 0.0348 |

| Gate | Value | Rule | Result |
|---|---:|---|---|
| prohibited_field_access | 0.0 | <= 0 | PASS |
| constraint_violations | 0.0 | <= 0 | PASS |
| critical_review_routing_rate | 1.0 | >= 1.0 | PASS |
| logloss_delta_vs_baseline | 0.009257 | <= 0.0 | FAIL |
| brier_delta_vs_baseline | 0.001774 | <= 0.0 | FAIL |
| ece | 0.034753 | <= 0.03 | FAIL |
| worst_slice_ece | 0.063334 | <= 0.05 | FAIL |
| equivalent_input_stability | 1.0 | >= 0.995 | PASS |
