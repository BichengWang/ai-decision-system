"""Large-sample estimators for two-arm online experiments (standard library only)."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import NormalDist

_N = NormalDist()


def z_for(alpha: float) -> float:
    """Critical value for a one-sided test at level ``alpha``."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    return _N.inv_cdf(1.0 - alpha)


@dataclass(frozen=True)
class Effect:
    """Treatment minus control, with its standard error."""

    control: float
    treatment: float
    diff: float
    se: float

    def bounds(self, z: float) -> tuple[float, float]:
        return self.diff - z * self.se, self.diff + z * self.se


def proportion_effect(control_successes: int, control_n: int,
                      treatment_successes: int, treatment_n: int) -> Effect:
    """Difference in proportions with the unpooled (Wald) standard error."""
    for k, n in ((control_successes, control_n), (treatment_successes, treatment_n)):
        if n <= 0 or not 0 <= k <= n:
            raise ValueError("proportion counts must satisfy 0 <= successes <= units and units > 0")
    pc, pt = control_successes / control_n, treatment_successes / treatment_n
    se = sqrt(pc * (1 - pc) / control_n + pt * (1 - pt) / treatment_n)
    return Effect(pc, pt, pt - pc, se)


def mean_effect(control_mean: float, control_sd: float, control_n: int,
                treatment_mean: float, treatment_sd: float, treatment_n: int) -> Effect:
    """Difference in means with the Welch (unequal-variance) standard error."""
    if control_n <= 1 or treatment_n <= 1 or control_sd < 0 or treatment_sd < 0:
        raise ValueError("mean metrics need units > 1 and non-negative standard deviations")
    se = sqrt(control_sd ** 2 / control_n + treatment_sd ** 2 / treatment_n)
    return Effect(control_mean, treatment_mean, treatment_mean - control_mean, se)


def sample_ratio_p_value(control_n: int, treatment_n: int, expected_treatment_share: float) -> float:
    """Chi-square (1 df) goodness-of-fit p-value for the observed assignment split."""
    if not 0.0 < expected_treatment_share < 1.0:
        raise ValueError("expected_treatment_share must be in (0, 1)")
    total = control_n + treatment_n
    if total <= 0:
        raise ValueError("experiment has no units")
    exp_t = total * expected_treatment_share
    exp_c = total - exp_t
    chi2 = (treatment_n - exp_t) ** 2 / exp_t + (control_n - exp_c) ** 2 / exp_c
    # With one degree of freedom, chi2 = z**2, so the p-value is two-sided normal.
    return 2.0 * (1.0 - _N.cdf(sqrt(chi2)))
