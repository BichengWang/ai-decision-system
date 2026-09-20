"""Deterministic synthetic-data generator.

Produces (1) offer-response sessions with a known ground-truth response
function and a controlled late-period shift, and (2) a ranking task with
graded relevance. Every column is synthetic.
"""
from __future__ import annotations

import hashlib
import numpy as np

from . import config as C


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def true_response_prob(basket, hour, category, tenure, mq, dist, weekend, discount, day):
    """Ground-truth conversion probability. Includes a concept shift after DRIFT_START_DAY."""
    cat_eff = np.array([0.30, 0.10, -0.10, 0.00, -0.25, 0.20])[category]
    disc_sens = np.array([6.0, 5.0, 3.0, 4.0, 2.0, 7.0])[category]
    # Non-linear structure by design: saturating discount response, discount x basket
    # interaction, a distance threshold, and an hour x category interaction.
    disc_resp = disc_sens * discount * (1.0 + 0.4 * (tenure == 0)) * np.where(basket > 45.0, 0.45, 1.0)
    late_food = ((hour >= 21) | (hour <= 1)) & (category <= 1)
    z = (-1.1 + cat_eff + 0.018 * (basket - 30.0) - 0.0002 * (basket - 30.0) ** 2
         + 0.35 * mq - 0.09 * dist - 0.55 * (dist > 5.0) + 0.12 * tenure + 0.15 * weekend
         + 0.25 * np.sin(2 * np.pi * (hour - 18) / 24.0) + 0.6 * late_food
         + disc_resp)
    shift = (day >= C.DRIFT_START_DAY).astype(float)
    z = z - 0.18 * shift * (category == 5) + 0.10 * shift * discount * 5.0
    return _sigmoid(z)


def generate_sessions(seed: int = C.GENERATOR_SEED, n_days: int = C.N_DAYS,
                      per_day: int = C.SESSIONS_PER_DAY, start_day: int = 0) -> dict:
    rng = np.random.default_rng(seed + 7919 * start_day)
    n = n_days * per_day
    day = np.repeat(np.arange(start_day, start_day + n_days), per_day)
    m_rng = np.random.default_rng(C.GENERATOR_SEED)          # merchants are fixed across calls
    m_quality = m_rng.normal(0, 1, C.N_MERCHANTS)
    m_category = m_rng.integers(0, C.N_CATEGORIES, C.N_MERCHANTS)
    merchant = rng.integers(0, C.N_MERCHANTS, n)
    category = m_category[merchant]
    shift = day >= C.DRIFT_START_DAY
    basket = rng.gamma(4.0, 8.0, n) * np.where(shift, 1.12, 1.0)   # covariate shift
    hour = rng.integers(0, 24, n)
    tenure = rng.integers(0, 4, n)
    dist = rng.gamma(2.0, 1.5, n)
    weekend = ((day % 7) >= 5).astype(int)
    # logged (historical) discount policy: randomized within constraints -> unconfounded labels
    max_disc = np.array(C.MAX_DISCOUNT_BY_CATEGORY)[category]
    levels = np.array(C.DISCOUNT_LEVELS)
    discount = levels[rng.integers(0, len(levels), n)]
    discount = np.where((discount > max_disc) | (basket < C.MIN_BASKET_FOR_OFFER), 0.0, discount)
    p = true_response_prob(basket, hour, category, tenure, m_quality[merchant], dist, weekend, discount, day)
    y = (rng.random(n) < p).astype(int)
    campaign = (merchant * 3 + day // 30) % 97
    return {
        "session_id": np.arange(n) + start_day * per_day,
        "day": day, "merchant": merchant, "campaign": campaign,
        "basket_value": basket, "hour": hour,
        "hour_sin": np.sin(2 * np.pi * hour / 24.0), "hour_cos": np.cos(2 * np.pi * hour / 24.0),
        "category": category, "tenure_bucket": tenure,
        "merchant_quality": m_quality[merchant], "distance_km": dist, "is_weekend": weekend,
        "discount": discount, "response": y, "true_p": p,
        # prohibited fields: one correlated with basket value, two random controls; never to be read
        "zip_income_proxy": rng.normal(0, 1, n) + 0.5 * (basket > 40),
        "device_price_tier": rng.integers(0, 3, n),
        "inferred_age_band": rng.integers(0, 5, n),
    }


def generate_ranking(seed: int = C.GENERATOR_SEED + 1, n_queries: int = C.N_RANK_QUERIES,
                     n_cand: int = C.RANK_CANDIDATES) -> dict:
    """Query-candidate pairs with graded relevance 0..3 and a non-linear interaction."""
    rng = np.random.default_rng(seed)
    n = n_queries * n_cand
    qid = np.repeat(np.arange(n_queries), n_cand)
    q_day = np.repeat(np.sort(rng.integers(0, C.N_DAYS, n_queries)), n_cand)
    q_intent = np.repeat(rng.integers(0, 4, n_queries), n_cand)
    sim = rng.beta(2, 5, n)                       # embedding-similarity surrogate
    pop = rng.normal(0, 1, n)                     # item popularity
    fresh = rng.random(n)
    c_type = rng.integers(0, 4, n)
    match = (c_type == q_intent).astype(float)
    score = 3.2 * sim + 0.25 * pop + 1.4 * match * sim * 2.0 + 0.5 * fresh * match + rng.normal(0, 0.45, n)
    rel = np.digitize(score, [1.2, 1.9, 2.7])     # 0..3
    return {"qid": qid, "day": q_day, "sim": sim, "pop": pop, "fresh": fresh,
            "q_intent": q_intent, "c_type": c_type, "relevance": rel}


def dataset_hash(d: dict) -> str:
    h = hashlib.sha256()
    for k in sorted(d):
        h.update(k.encode())
        h.update(np.ascontiguousarray(np.round(np.asarray(d[k], dtype=float), 10)).tobytes())
    return h.hexdigest()
