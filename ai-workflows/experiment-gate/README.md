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
large-sample approximations.

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
better (`increase` or `decrease`). `policy` and `assignment` are optional.

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

## Limitations

- Fixed-horizon tests only. Checking results repeatedly while the test runs and
  stopping early inflates error rates; use a sequential method for that.
- No variance reduction (e.g. CUPED), no ratio metrics with delta-method
  standard errors, and no heterogeneous-effect analysis.
- Synthetic scenarios show that the rules behave as specified. They say nothing
  about any real product's effects.
