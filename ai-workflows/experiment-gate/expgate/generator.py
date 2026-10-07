"""Deterministic synthetic experiments for a real-time offer-ranking model.

Each scenario simulates unit-level outcomes (conversion, refund, decision
latency) with a fixed seed and reduces them to the aggregate summary format that
:func:`expgate.decision.evaluate` consumes. Only the standard library ``random``
module is used, so the same seed yields the same summary on any platform.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import sqrt

SEED = 20260924


@dataclass(frozen=True)
class Scenario:
    description: str
    units: int = 60_000
    treatment_share: float = 0.5
    observed_treatment_share: float | None = None  # set to inject a sample-ratio mismatch
    conversion: tuple[float, float] = (0.100, 0.100)
    refund: tuple[float, float] = (0.020, 0.020)
    latency_ms: tuple[float, float] = (40.0, 40.0)
    latency_sd: float = 12.0
    # Set to simulate a revenue experiment whose summary carries a pre-experiment covariate.
    covariate_corr: float | None = None
    revenue: tuple[float, float] = (20.0, 20.0)
    revenue_sd: float = 8.0
    # Set to simulate an interim look at a sequentially monitored test planned for this many units.
    planned_units: int | None = None


SCENARIOS = {
    "win": Scenario("Candidate lifts conversion with no guardrail cost",
                    conversion=(0.100, 0.112)),
    "flat": Scenario("Candidate is indistinguishable from control",
                     units=4_000),
    "guardrail-breach": Scenario("Candidate lifts conversion but adds 12 ms of decision latency",
                                 conversion=(0.100, 0.112), latency_ms=(40.0, 52.0)),
    "regression": Scenario("Candidate lowers conversion",
                           conversion=(0.100, 0.088)),
    "srm": Scenario("Assignment bug sends 53% of traffic to treatment",
                    conversion=(0.100, 0.112), observed_treatment_share=0.53),
    # Lift 0.4 is sized so the adjusted analysis has about 80% power (unadjusted: about 47%). At this
    # fixed seed the treatment arm's pre-period covariate happens to run high, which inflates the raw lift.
    "cuped": Scenario("Real revenue lift of 0.4; a chance covariate imbalance inflates the raw estimate",
                      units=4_000, covariate_corr=0.8, revenue=(20.0, 20.4)),
    # An interim look a quarter of the way into a sequentially monitored test: the conversion drop is
    # large enough that the always-valid bound already excludes zero, so the test can stop now.
    "early-regression": Scenario("Interim look at 15,000 of 60,000 planned units; candidate lowers conversion",
                                 units=15_000, conversion=(0.100, 0.075), planned_units=60_000),
}

METRICS = {
    "conversion": {"type": "proportion", "role": "primary", "direction": "increase"},
    "refund_rate": {"type": "proportion", "role": "guardrail", "direction": "decrease", "margin": 0.003},
    "latency_ms": {"type": "mean", "role": "guardrail", "direction": "decrease", "margin": 2.0},
}


METRICS_REVENUE = {
    "revenue_per_user": {"type": "mean", "role": "primary", "direction": "increase"},
}


def _arm_revenue(rng: random.Random, n: int, mean: float, sd: float, corr: float) -> dict:
    """Revenue per user with a pre-period covariate (same mean and sd) correlated ``corr`` with it."""
    sx = sxx = sy = syy = sxy = 0.0
    for _ in range(n):
        x = rng.gauss(20.0, sd)
        y = mean + corr * (x - 20.0) + sqrt(1 - corr ** 2) * sd * rng.gauss(0, 1)
        sx, sxx, sy, syy, sxy = sx + x, sxx + x * x, sy + y, syy + y * y, sxy + x * y
    mx, my = sx / n, sy / n
    vx, vy = (sxx - n * mx * mx) / (n - 1), (syy - n * my * my) / (n - 1)
    cov = (sxy - n * mx * my) / (n - 1)
    return {"units": n, "metrics": {"revenue_per_user": {
        "mean": round(my, 6), "sd": round(sqrt(vy), 6),
        "covariate": {"mean": round(mx, 6), "sd": round(sqrt(vx), 6), "corr": round(cov / sqrt(vx * vy), 6)},
    }}}


def _arm(rng: random.Random, n: int, conv: float, refund: float, lat: float, lat_sd: float) -> dict:
    conversions = refunds = 0
    total = total_sq = 0.0
    for _ in range(n):
        converted = rng.random() < conv
        conversions += converted
        refunds += converted and rng.random() < refund / conv
        x = max(0.0, rng.gauss(lat, lat_sd))
        total += x
        total_sq += x * x
    mean = total / n
    sd = ((total_sq - n * mean * mean) / (n - 1)) ** 0.5
    return {"units": n, "metrics": {
        "conversion": {"successes": conversions},
        "refund_rate": {"successes": int(refunds)},
        "latency_ms": {"mean": round(mean, 6), "sd": round(sd, 6)},
    }}


def generate(name: str, seed: int = SEED) -> dict:
    """Return the experiment summary for a named scenario."""
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}")
    s = SCENARIOS[name]
    rng = random.Random(f"{seed}:{name}")
    share = s.treatment_share if s.observed_treatment_share is None else s.observed_treatment_share
    n_t = round(s.units * share)
    n_c = s.units - n_t
    policy = {} if s.planned_units is None else {"policy": {"sequential": {"planned_units": s.planned_units}}}
    if s.covariate_corr is not None:
        return {
            "experiment": name,
            "description": s.description,
            "seed": seed,
            "assignment": {"expected_treatment_share": s.treatment_share},
            "metrics": METRICS_REVENUE,
            "arms": {
                "control": _arm_revenue(rng, n_c, s.revenue[0], s.revenue_sd, s.covariate_corr),
                "treatment": _arm_revenue(rng, n_t, s.revenue[1], s.revenue_sd, s.covariate_corr),
            },
        }
    return {
        "experiment": name,
        "description": s.description,
        "seed": seed,
        "assignment": {"expected_treatment_share": s.treatment_share},
        **policy,
        "metrics": METRICS,
        "arms": {
            "control": _arm(rng, n_c, s.conversion[0], s.refund[0], s.latency_ms[0], s.latency_sd),
            "treatment": _arm(rng, n_t, s.conversion[1], s.refund[1], s.latency_ms[1], s.latency_sd),
        },
    }
