# Decision model evaluation: UNGATED

- evaluation.json SHA-256: `73c44102d3e3fd4cd4b6e3f235457f1d00c9c10682c024bc76686acd039ad1fa`
- jevdecision 0.2.0; backend jev; model jev-example; source replay
- 6 cases, 6 answered, 0 errors (rate 0)

- Calibration fitted (isotonic) on these cases: calibration.json SHA-256 `1144391dfc15c23cf25bda9ae9e018395e3448595002192c8c68ebb320ce4ca5`. Only a run on other cases with `--calibration` measures it.

- Replay origin is unverified; response model fields are supplied metadata, not proof of provider output.

- No explicit question metric bounds: metrics are descriptive, not a quality gate.

| Question | Type | n | Metrics |
|---|---|---:|---|
| refund | noul | 6 | accuracy 1, accuracy_lower 0.6097, accuracy_upper 1, brier 0.0058, log_loss 0.0731, ece 0.07, base_rate 0.3333, mean_probability 0.3567, refusals 0, refusal_rate 0 |
| department | choice | 6 | accuracy 1, accuracy_lower 0.6097, accuracy_upper 1, brier 0.0283, log_loss 0.1365, ece 0.1267, refusals 0, refusal_rate 0 |
| frustration | score | 6 | accuracy 1, accuracy_lower 0.6097, accuracy_upper 1, within_one 1, mae 0.08167, brier 0.05523, log_loss 0.184, ece 0.1633, refusals 0, refusal_rate 0 |

| Requirement | Bound | Value | Result |
|---|---|---:|---|
| error_rate | max 0 | 0 | pass |
