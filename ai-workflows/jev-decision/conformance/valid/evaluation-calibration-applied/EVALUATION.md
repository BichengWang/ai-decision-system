# Decision model evaluation: PASS

- evaluation.json SHA-256: `7d0a7d1d79694c6e838465659f00797d3fc8de17d05a2ec7a56de408a78031a9`
- jevdecision 0.2.0; backend jev; model jev-example; source replay
- 6 cases, 6 answered, 0 errors (rate 0)

- Calibration applied (isotonic): calibration.json SHA-256 `1144391dfc15c23cf25bda9ae9e018395e3448595002192c8c68ebb320ce4ca5`, fitted on other cases; `calibrated_*` metrics are held out.

- Replay origin is unverified; response model fields are supplied metadata, not proof of provider output.

| Question | Type | n | Metrics |
|---|---|---:|---|
| refund | noul | 6 | accuracy 0.8333, accuracy_lower 0.4365, accuracy_upper 0.9699, brier 0.06348, log_loss 0.1996, ece 0.145, base_rate 0.5, mean_probability 0.395, refusals 0, refusal_rate 0, calibrated_brier 0.0697, calibrated_log_loss 0.1793, calibrated_ece 0.1139 |
| department | choice | 6 | accuracy 0.8333, accuracy_lower 0.4365, accuracy_upper 0.9699, brier 0.2113, log_loss 0.3546, ece 0.105, refusals 0, refusal_rate 0, calibrated_ece 0.1667 |
| frustration | score | 6 | accuracy 1, accuracy_lower 0.6097, accuracy_upper 1, within_one 1, mae 0.2867, brier 0.1969, log_loss 0.3645, ece 0.2917, refusals 0, refusal_rate 0, calibrated_ece 0 |

| Requirement | Bound | Value | Result |
|---|---|---:|---|
| error_rate | max 0 | 0 | pass |
| refund.calibrated_ece | max 0.15 | 0.1139 | pass |
| refund.n | min 6 | 6 | pass |

Incorrect answers (2; every case is in `cases.jsonl`):

- `t10` refund: expected true, got false
- `t10` department: expected "sales", got "billing"
