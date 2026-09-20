"""Metric definitions. Every metric states numerator, denominator and exclusions in docs/SPEC.md."""
from __future__ import annotations

import numpy as np


def log_loss(y, p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p):
    return float(np.mean((p - y) ** 2))


def ece(y, p, bins=15):
    """Expected calibration error, equal-width bins; empty bins excluded."""
    edges = np.linspace(0, 1, bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total = 0.0
    for k in range(bins):
        m = b == k
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(total)


def worst_slice_ece(y, p, slices, bins=15, min_n=500):
    worst, worst_key = 0.0, None
    eligible_count = 0
    for key in np.unique(slices):
        m = slices == key
        if m.sum() >= min_n:
            eligible_count += 1
            e = ece(y[m], p[m], bins)
            if e > worst:
                worst, worst_key = e, int(key)
    return float(worst), worst_key, eligible_count


def murphy_decomposition(y, p, bins=15):
    """Brier = reliability - resolution + uncertainty (binned)."""
    edges = np.linspace(0, 1, bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    base = y.mean(); rel = res = 0.0
    for k in range(bins):
        m = b == k
        if m.any():
            w = m.mean()
            rel += w * (p[m].mean() - y[m].mean()) ** 2
            res += w * (y[m].mean() - base) ** 2
    return {"reliability": float(rel), "resolution": float(res), "uncertainty": float(base * (1 - base))}


def psi(expected, actual, bins=10):
    """Population stability index using quantile bins of the reference sample."""
    qs = np.quantile(expected, np.linspace(0, 1, bins + 1)[1:-1])
    e = np.bincount(np.digitize(expected, qs), minlength=bins) / len(expected)
    a = np.bincount(np.digitize(actual, qs), minlength=bins) / len(actual)
    e = np.clip(e, 1e-6, None); a = np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))


def ndcg_at_k(qid, rel, score, k=10):
    order = np.lexsort((-score, qid))
    qid_s, rel_s = qid[order], rel[order]
    starts = np.r_[0, np.where(np.diff(qid_s) != 0)[0] + 1, len(qid_s)]
    out = []
    disc = 1.0 / np.log2(np.arange(2, k + 2))
    for a, b in zip(starts[:-1], starts[1:]):
        r = rel_s[a:b]
        gains = (2.0 ** r[:k] - 1)
        ideal = (2.0 ** np.sort(r)[::-1][:k] - 1)
        idcg = float((ideal * disc[: len(ideal)]).sum())
        if idcg > 0:
            out.append(float((gains * disc[: len(gains)]).sum()) / idcg)
    return float(np.mean(out))


def mrr(qid, rel, score, min_rel=2):
    order = np.lexsort((-score, qid))
    qid_s, rel_s = qid[order], rel[order]
    starts = np.r_[0, np.where(np.diff(qid_s) != 0)[0] + 1, len(qid_s)]
    out = []
    for a, b in zip(starts[:-1], starts[1:]):
        hit = np.where(rel_s[a:b] >= min_rel)[0]
        out.append(1.0 / (hit[0] + 1) if len(hit) else 0.0)
    return float(np.mean(out))
