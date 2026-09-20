"""End-to-end frozen evaluation: train -> calibrate -> test -> gates, for N seeds."""
from __future__ import annotations

import numpy as np

from . import config as C
from .generator import generate_sessions, generate_ranking, dataset_hash
from .guards import GuardedRecords, build_features
from .metrics import log_loss, brier, ece, worst_slice_ece, murphy_decomposition, ndcg_at_k, mrr
from .models import CalibratedModel, make_baseline, make_candidate, make_ranker
from .monitoring import drift_report
from .policy import critical_review_fixture_report, decide, count_constraint_violations
from .splits import time_group_split, assert_no_leakage


def _stability(model, data, idx, rng):
    """Share of equivalent-input pairs receiving the identical decision.

    The twin differs only in session id, all prohibited fields, and sub-cent basket noise."""
    twin = {k: np.array(v, copy=True) for k, v in data.items()}
    n = len(twin["basket_value"])
    twin["basket_value"] = twin["basket_value"] + rng.uniform(-0.004, 0.004, n)
    twin["zip_income_proxy"] = rng.normal(0, 3, n)
    twin["device_price_tier"] = rng.integers(0, 3, n)
    twin["inferred_age_band"] = rng.integers(0, 5, n)
    a, _, _ = decide(model, GuardedRecords(data), idx)
    b, _, _ = decide(model, GuardedRecords(twin), idx)
    return float(np.mean(a == b))


def _ranking_eval(seed):
    r = generate_ranking()
    qday = r["day"]
    t1, t2 = np.quantile(qday, [0.6, 0.8])
    tr, te = qday < t1, qday >= t2
    X = np.column_stack([r["sim"], r["pop"], r["fresh"], (r["q_intent"] == r["c_type"]).astype(float),
                         r["q_intent"], r["c_type"]])
    out = {}
    for kind in ("baseline", "candidate"):
        m = make_ranker(kind, seed).fit(X[tr], r["relevance"][tr])
        s = m.predict(X[te])
        out[kind] = {"ndcg@10": ndcg_at_k(r["qid"][te], r["relevance"][te], s, C.RANK_K),
                     "mrr": mrr(r["qid"][te], r["relevance"][te], s)}
    out["ndcg_gain"] = out["candidate"]["ndcg@10"] - out["baseline"]["ndcg@10"]
    out["dataset_sha256"] = dataset_hash(r)
    out["n_test_queries"] = int(len(np.unique(r["qid"][te])))
    return out


def run_seed(seed: int, data: dict, idx: dict) -> dict:
    rec = GuardedRecords(data)
    Xtr, Xca, Xte = (build_features(rec, idx[k]) for k in ("train", "calib", "test"))
    y = data["response"]; ytr, yca, yte = y[idx["train"]], y[idx["calib"]], y[idx["test"]]
    base = CalibratedModel(make_baseline(seed)).fit(Xtr, ytr, Xca, yca)
    cand = CalibratedModel(make_candidate(seed)).fit(Xtr, ytr, Xca, yca)
    pb, pc = base.predict(Xte), cand.predict(Xte)
    chosen, util, critical = decide(cand, rec, idx["test"])
    review_fixture = critical_review_fixture_report()
    ws, ws_key, ws_eligible = worst_slice_ece(
        yte, pc, data["category"][idx["test"]], C.GATES.ece_bins, C.GATES.min_slice_n
    )
    rank = _ranking_eval(seed)
    # oracle regret against the known synthetic ground truth (diagnostic, not a gate)
    m = {
        "seed": seed,
        "baseline": {"log_loss": log_loss(yte, pb), "brier": brier(yte, pb), "ece": ece(yte, pb, C.GATES.ece_bins)},
        "candidate": {"log_loss": log_loss(yte, pc), "brier": brier(yte, pc), "ece": ece(yte, pc, C.GATES.ece_bins),
                      "murphy": murphy_decomposition(yte, pc, C.GATES.ece_bins)},
        "logloss_delta": log_loss(yte, pc) - log_loss(yte, pb),
        "brier_delta": brier(yte, pc) - brier(yte, pb),
        "ece": ece(yte, pc, C.GATES.ece_bins),
        "worst_slice_ece": ws, "worst_slice_category": ws_key,
        "worst_slice_eligible_count": ws_eligible,
        "prohibited_access": rec.prohibited_access_count,
        "constraint_violations": count_constraint_violations(data, idx["test"], chosen),
        "decision_critical_cases": int(critical.sum()),
        "critical_review_fixture": review_fixture,
        "critical_review_fixture_n": review_fixture["critical_cases"],
        "critical_review_routing": review_fixture["routing_rate"],
        "critical_review_noncritical_misroutes": review_fixture["misrouted_noncritical_cases"],
        "stability": _stability(cand, data, idx["test"], np.random.default_rng(seed)),
        "offer_rate": float(np.mean(chosen > 0)), "mean_discount": float(chosen.mean()),
        "ranking": rank, "ndcg_gain": rank["ndcg_gain"],
        "drift": drift_report(data, idx["train"], idx["test"], cand.predict(Xtr), pc, yte),
    }
    return m, cand


def run_all(seeds=C.TRAIN_SEEDS):
    data = generate_sessions()
    idx = time_group_split(data["day"], data["merchant"])
    assert_no_leakage(idx, data["day"], data["merchant"], extra_ids=(data["session_id"],))
    per_seed, models = [], {}
    for s in seeds:
        m, cand = run_seed(s, data, idx)
        per_seed.append(m); models[s] = cand
    return data, idx, per_seed, models
