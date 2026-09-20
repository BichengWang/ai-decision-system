"""Deterministic offer policy with hard eligibility and discount constraints."""
from __future__ import annotations

import numpy as np

from . import config as C
from .guards import build_features


# Fixed boundary cases for the human-review control. Twelve cases meet the
# critical-case definition; four controls sit below a basket or discount boundary.
_REVIEW_FIXTURE_BASKET = np.array([
    90.0, 95.0, 100.0, 110.0, 120.0, 130.0, 140.0, 150.0,
    175.0, 200.0, 250.0, 300.0, 89.99, 120.0, 200.0, 90.0,
])
_REVIEW_FIXTURE_DISCOUNT = np.array([
    0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20,
    0.20, 0.20, 0.20, 0.20, 0.20, 0.10, 0.00, 0.05,
])
# Fixture-owned expected labels are intentionally independent of the router
# implementation. This makes the boundary test capable of detecting a faulty
# routing rule rather than comparing the rule with itself.
_REVIEW_FIXTURE_EXPECTED_REQUIRED = np.array([True] * 12 + [False] * 4)


def critical_review_required(chosen, basket):
    """Return which decisions meet the frozen critical-review definition."""
    return (np.asarray(chosen) >= 0.20) & (np.asarray(basket) >= 90.0)


def route_to_human(chosen, basket):
    """Deterministic reference router: every required case enters human review."""
    return critical_review_required(chosen, basket)


def critical_review_fixture_report(router=None):
    """Measure routing on a fixed, nonempty set of boundary-focused cases."""
    if router is None:
        router = route_to_human
    required = _REVIEW_FIXTURE_EXPECTED_REQUIRED
    routed = np.asarray(router(_REVIEW_FIXTURE_DISCOUNT, _REVIEW_FIXTURE_BASKET), dtype=bool)
    if routed.shape != required.shape:
        raise ValueError("review router returned the wrong number of fixture decisions")
    denominator = int(required.sum())
    numerator = int((required & routed).sum())
    noncritical = ~required
    misrouted_noncritical = int((noncritical & routed).sum())
    return {
        "total_cases": int(len(required)),
        "critical_cases": denominator,
        "routed_critical_cases": numerator,
        "routing_rate": float(numerator / denominator) if denominator else 0.0,
        "noncritical_cases": int(noncritical.sum()),
        "misrouted_noncritical_cases": misrouted_noncritical,
    }


def allowed_mask(records, idx):
    """[n, n_levels] boolean mask of permitted discount levels per session."""
    cat = np.asarray(records["category"])[idx]
    basket = np.asarray(records["basket_value"])[idx]
    levels = np.array(C.DISCOUNT_LEVELS)
    max_disc = np.array(C.MAX_DISCOUNT_BY_CATEGORY)[cat]
    ok = levels[None, :] <= max_disc[:, None] + 1e-12
    ok &= (basket[:, None] >= C.MIN_BASKET_FOR_OFFER) | (levels[None, :] == 0.0)
    return ok


def decide(model, records, idx):
    """Return chosen discount per session, expected utility, and the review flag."""
    levels = np.array(C.DISCOUNT_LEVELS)
    basket = np.asarray(records["basket_value"])[idx]
    probs = np.column_stack([model.predict(build_features(records, idx, discount_override=d)) for d in levels])
    utility = probs * basket[:, None] * (C.MARGIN_RATE - levels[None, :])
    utility = np.where(allowed_mask(records, idx), utility, -np.inf)
    choice = utility.argmax(axis=1)
    chosen = levels[choice]
    # Use the same router exercised by the release fixture. A separate predicate here
    # could let the gate validate an orphan helper instead of the live decision path.
    critical = route_to_human(chosen, basket)
    return chosen, utility.max(axis=1), critical


def count_constraint_violations(records, idx, chosen):
    levels = np.array(C.DISCOUNT_LEVELS)
    ok = allowed_mask(records, idx)
    chosen = np.asarray(chosen, dtype=float)
    matches = np.isclose(chosen[:, None], levels[None, :], rtol=0.0, atol=1e-12)
    recognized = matches.any(axis=1)
    pos = matches.argmax(axis=1)
    return int((~recognized | ~ok[np.arange(len(pos)), pos]).sum())
