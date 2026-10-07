# Experiment gate (`expgate`)

A small, deterministic workflow for the step that follows offline release gates:
deciding whether a real-time decision model that is **already in an online A/B
test** should be shipped, held for more data, or rolled back.

It reads the aggregate summary an experimentation platform exports (units per
arm, successes for proportion metrics, mean and standard deviation for mean
metrics) and writes a decision record. It uses only the Python standard library,
so it has no dependencies and no lockfile.

## Decision rules

Rules are applied in order; the first match wins.

| Decision | When |
|---|---|
| `INVALID` | Sample-ratio mismatch: the observed assignment split differs from the design (chi-square, `srm_alpha`, default 0.001). No effect estimate is trusted. |
| `ROLLBACK` | The primary metric is significantly worse, or a guardrail is significantly worse **and** its point degradation exceeds its margin. |
| `SHIP` | The primary metric is significantly better **and** every guardrail is shown non-inferior (its upper degradation bound is below its margin). |
| `HOLD` | Anything else: the experiment is inconclusive. |

The primary metric uses a one-sided test at `alpha` (default 0.05). Guardrail
bounds are one-sided and Bonferroni-adjusted across guardrails. Proportions use
the unpooled Wald standard error; means use the Welch standard error. Both are
large-sample approximations. A metric can optionally be estimated with CUPED
regression adjustment, which narrows its interval (see
[Variance reduction](#variance-reduction-cuped)). A test that is checked while it
runs can replace every bound with an always-valid confidence sequence (see
[Sequential monitoring](#sequential-monitoring)).

## Quick start

From this directory, with Python 3.11 or later:

```bash
python3 -m unittest discover -s tests
python3 -m expgate.run --all-scenarios --out review-run
python3 -m expgate.run --input examples/offer-ranker-v2.json --out review-run/example --require-ship
```

`--out` must be new or empty. Each evaluation writes `decision.json` (sorted
keys; byte-identical across runs for the same input) and a readable
`DECISION.md`. `--require-ship` exits 1 unless every decision is `SHIP`, so the
command can gate a promotion job. Invalid input exits 2.

From the repository root, `make expgate-test` and
`make expgate-run EXPGATE_OUT=/abs/new/dir` run the same commands.

## Input format

See [`examples/offer-ranker-v2.json`](examples/offer-ranker-v2.json). Exactly
one metric has `"role": "primary"`; every other metric is a `"guardrail"` with a
non-negative `margin` in the metric's own units. `direction` states which way is
better (`increase` or `decrease`). `policy` and `assignment` are optional;
`policy.sequential` turns on sequential monitoring.

The summary is validated before any statistic is computed: counts must be
integers within range, means, standard deviations and margins must be finite,
`alpha`, `srm_alpha` and `expected_treatment_share` must lie in (0, 1), and
`policy.sequential.planned_units` must be an integer of at least 2.
Any violation exits 2 with the offending field named, so malformed input is
never mistaken for a `--require-ship` refusal (exit 1).

## Variance reduction (CUPED)

If you have a pre-experiment measurement of the same unit that predicts the outcome (last
month's revenue for this month's revenue, say), add a `covariate` summary to **that metric in
both arms** (the numbers below are illustrative):

```json
"revenue_per_user": {"mean": 20.57, "sd": 8.1,
                     "covariate": {"mean": 20.46, "sd": 7.9, "corr": 0.8}}
```

`covariate.mean` and `covariate.sd` describe the pre-experiment value, and `corr` is its
correlation with the outcome within the arm. Proportion metrics take the same block next to
`successes`. The estimate becomes `(ybar_t - ybar_c) - theta * (xbar_t - xbar_c)`, with one
`theta` shared by both arms: the pooled within-arm regression slope. The standard error
shrinks by about `1 - rho^2` in variance, and the adjustment also removes the part of the
difference caused by a chance imbalance in the covariate. The decision rules do not change, and
a metric's row in `decision.json` gains an `adjustment` object (`theta`, the unadjusted
difference and standard error, and the variance reduction).

Things the tool cannot check for you:

- The covariate must be measured **before assignment** and must not be affected by the
  treatment. A post-treatment covariate biases the estimate.
- The adjustment can move a single experiment's estimate either way. In the `cuped` scenario
  the treatment arm's covariate runs high by chance, the unadjusted lift is inflated, and the
  adjusted analysis holds. Across 300 simulated experiments with a real lift of 0.4 the adjusted
  analysis ships 80% of the time against 47% unadjusted. With no real lift over 1,500 runs they ship
  5.5% and 5.9% of the time, consistent with the nominal 5%.
- `theta` is treated as known. Its estimation error is negligible at the sample sizes this tool
  targets, but it is ignored.

## Sequential monitoring

The default bounds assume the summary is evaluated once, at a sample size fixed in advance.
Evaluating it every day and acting on the first `SHIP` or `ROLLBACK` inflates the error rates:
in 2,000 simulated A/A tests checked at 20 evenly spaced looks, re-applying the fixed-horizon
bounds at each look shipped 19.8% of them and rolled back 22.0%, against a nominal 5%.

To check a running test, declare the total sample size (both arms) the test is planned to reach:

```json
"policy": {"alpha": 0.05, "sequential": {"planned_units": 60000}}
```

Every bound then becomes an always-valid confidence sequence: a one-sided normal-mixture
sequential probability ratio test on the same normal approximation, inverted into a bound. With
probability at least `1 - alpha` it holds at every look at once, so the summary can be evaluated
as often as the platform refreshes it, and the experiment can stop at the first `SHIP` or
`ROLLBACK`. The decision rules, the Bonferroni split across guardrails and CUPED are unchanged;
only the multiplier on each standard error (the `z` in a metric's row) is larger. `decision.json`
gains a `sequential` object (planned and current units, and the information fraction), and
`DECISION.md` gains one line. A summary without `policy.sequential` is evaluated exactly as before.

`planned_units` tunes the mixing variance so the bound is narrowest at the planned size. It must be
fixed before the test starts; choosing it after seeing the data voids the guarantee. The bound
stays valid before and after the plan, only wider. A `HOLD` at or past the plan says that the
planned sample size was reached without a decision.

The price is power at the plan. In the same simulation, with a real conversion lift from 0.100 to
0.108 and 60,000 planned units, a single fixed-horizon analysis at the plan ships 95% of tests.
Sequential monitoring over 20 looks ships 74% of them, and those it ships stop on average at 56% of
the planned sample. Without a real effect it ships 1.0% and rolls back 1.2%. At the plan the
primary multiplier is 2.77 standard errors against 1.64 for the fixed-horizon test at
`alpha = 0.05`. Use sequential monitoring when stopping early (above all, rolling back a harmful
candidate early) is worth that cost.

## Synthetic scenarios

`--scenario` / `--all-scenarios` simulate an offer-ranking model with a fixed
seed (`expgate/generator.py`):

| Scenario | Expected decision |
|---|---|
| `win` | `SHIP` |
| `flat` | `HOLD` |
| `guardrail-breach` | `ROLLBACK` (latency) |
| `regression` | `ROLLBACK` (primary) |
| `srm` | `INVALID` |
| `cuped` | `HOLD` (a revenue lift that looks significant only because of a covariate imbalance) |
| `early-regression` | `ROLLBACK` (primary) at an interim look, a quarter of the way to the planned sample size |

## Limitations

- Without `policy.sequential` the bounds are fixed-horizon: checking results repeatedly
  and stopping early inflates error rates.
- Sequential bounds plug in the observed standard error at each look, as the fixed-horizon
  bounds do. The guarantee is exact for normal estimates with known variance and holds only
  approximately at small samples. The sample-ratio check is not sequential: re-running it at
  every look raises its false alarm rate above `srm_alpha`.
- CUPED is supported for one covariate per metric. There are no ratio metrics with
  delta-method standard errors, no multi-covariate adjustment, and no heterogeneous-effect
  analysis.
- Synthetic scenarios show that the rules behave as specified. They say nothing
  about any real product's effects.
