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


@dataclass(frozen=True)
class Covariate:
    """Summary of a pre-experiment covariate for one arm: its mean, sample sd, and its
    correlation with the outcome within the arm."""

    mean: float
    sd: float
    corr: float


def proportion_variance(successes: int, n: int) -> float:
    """Per-unit variance of a 0/1 outcome, p(1-p): the same variance the Wald error uses."""
    return (successes / n) * (1 - successes / n)


def cuped_effect(control_mean: float, control_var: float, control_n: int, control_cov: Covariate,
                 treatment_mean: float, treatment_var: float, treatment_n: int,
                 treatment_cov: Covariate) -> tuple[Effect, dict]:
    """Treatment minus control after regression adjustment on a pre-experiment covariate (CUPED).

    The adjusted outcome is ``y - theta * x`` with one ``theta`` shared by both arms, the pooled
    within-arm regression slope ``sum((n-1) cov) / sum((n-1) var_x)``. The adjusted difference is
    ``(ybar_t - ybar_c) - theta * (xbar_t - xbar_c)``. Assignment is random, so the covariate has
    the same expectation in both arms and the adjustment adds no bias; it only removes the part of
    the difference that is explained by a chance imbalance in ``x``. Each arm contributes
    ``var(y - theta x) = var_y + theta**2 var_x - 2 theta cov`` over its own units, taking ``theta``
    as fixed. With zero correlation this reduces to the unadjusted standard error.

    Returns the adjusted effect, whose ``control`` and ``treatment`` stay the raw arm means, and a
    dict describing the adjustment.
    """
    arms = ((control_mean, control_var, control_n, control_cov),
            (treatment_mean, treatment_var, treatment_n, treatment_cov))
    for _, var, n, cov in arms:
        if n <= 1 or var < 0 or cov.sd <= 0 or not -1.0 <= cov.corr <= 1.0:
            raise ValueError("CUPED needs units > 1, a non-negative outcome variance, "
                             "a positive covariate sd and a correlation in [-1, 1]")
    cov_xy = [c.corr * c.sd * sqrt(v) for _, v, _, c in arms]
    theta = (sum((n - 1) * cxy for (_, _, n, _), cxy in zip(arms, cov_xy))
             / sum((n - 1) * c.sd ** 2 for _, _, n, c in arms))
    adjusted_var = [v + theta ** 2 * c.sd ** 2 - 2 * theta * cxy for (_, v, _, c), cxy in zip(arms, cov_xy)]
    se = sqrt(sum(max(av, 0.0) / n for av, (_, _, n, _) in zip(adjusted_var, arms)))
    raw_diff = treatment_mean - control_mean
    raw_se = sqrt(control_var / control_n + treatment_var / treatment_n)
    diff = raw_diff - theta * (treatment_cov.mean - control_cov.mean)
    info = {"method": "cuped", "theta": theta, "raw_diff": raw_diff, "raw_se": raw_se,
            "variance_reduction": 1 - se ** 2 / raw_se ** 2 if raw_se > 0 else 0.0}
    return Effect(control_mean, treatment_mean, diff, se), info


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
