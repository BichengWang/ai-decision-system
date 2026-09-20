"""One guarded update cycle: refit on newer synthetic data, rerun frozen gates, accept or reject."""
from __future__ import annotations

import numpy as np

from . import config as C
from .gates import evaluate_gates
from .generator import generate_sessions
from .guards import GuardedRecords, build_features
from .metrics import log_loss, brier, ece, worst_slice_ece
from .models import CalibratedModel, make_candidate
from .policy import critical_review_fixture_report, decide, count_constraint_violations
from .splits import assert_no_leakage, time_group_split


def _agg(rows, model, metric):
    values = [row[model][metric] for row in rows]
    return {"mean": float(np.mean(values)), "min": float(np.min(values)), "max": float(np.max(values))}


def guarded_update(current_models, seeds=C.TRAIN_SEEDS, new_days=60):
    """Compare five updated candidates with their seed-matched current references.

    The offer-model cycle applies eight gates. Ranking is the sole exclusion because
    this cycle neither changes nor reevaluates the separate ranking model.
    """
    from .pipeline import _stability

    new = generate_sessions(n_days=new_days, start_day=C.N_DAYS)
    idx = time_group_split(new["day"], new["merchant"])
    assert_no_leakage(idx, new["day"], new["merchant"], extra_ids=(new["session_id"],))
    y = new["response"]
    yte = y[idx["test"]]
    fixture = critical_review_fixture_report()
    per_seed = []
    for seed in seeds:
        rec = GuardedRecords(new)
        Xtr, Xca, Xte = (build_features(rec, idx[k]) for k in ("train", "calib", "test"))
        updated = CalibratedModel(make_candidate(seed)).fit(Xtr, y[idx["train"]], Xca, y[idx["calib"]])
        p_reference = current_models[seed].predict(Xte)
        p_updated = updated.predict(Xte)
        chosen, _, critical = decide(updated, rec, idx["test"])
        ws, ws_key, ws_eligible = worst_slice_ece(
            yte, p_updated, new["category"][idx["test"]], C.GATES.ece_bins, C.GATES.min_slice_n
        )
        gate_inputs = {
            "prohibited_access": rec.prohibited_access_count,
            "constraint_violations": count_constraint_violations(new, idx["test"], chosen),
            "critical_review_fixture_n": fixture["critical_cases"],
            "critical_review_routing": fixture["routing_rate"],
            "critical_review_noncritical_misroutes": fixture["misrouted_noncritical_cases"],
            "logloss_delta": log_loss(yte, p_updated) - log_loss(yte, p_reference),
            "brier_delta": brier(yte, p_updated) - brier(yte, p_reference),
            "ece": ece(yte, p_updated, C.GATES.ece_bins),
            "worst_slice_ece": ws,
            "worst_slice_eligible_count": ws_eligible,
            "stability": _stability(updated, new, idx["test"], np.random.default_rng(seed)),
        }
        per_seed.append({
            "seed": seed,
            "current_reference": {
                "log_loss": log_loss(yte, p_reference),
                "brier": brier(yte, p_reference),
                "ece": ece(yte, p_reference, C.GATES.ece_bins),
            },
            "updated_candidate": {
                "log_loss": log_loss(yte, p_updated),
                "brier": brier(yte, p_updated),
                "ece": gate_inputs["ece"],
            },
            "gate_inputs": gate_inputs,
            "worst_slice_category": ws_key,
            "decision_critical_cases": int(critical.sum()),
        })

    worst = {
        "prohibited_access": max(row["gate_inputs"]["prohibited_access"] for row in per_seed),
        "constraint_violations": max(row["gate_inputs"]["constraint_violations"] for row in per_seed),
        "critical_review_fixture_n": min(row["gate_inputs"]["critical_review_fixture_n"] for row in per_seed),
        "critical_review_routing": min(row["gate_inputs"]["critical_review_routing"] for row in per_seed),
        "critical_review_noncritical_misroutes": max(
            row["gate_inputs"]["critical_review_noncritical_misroutes"] for row in per_seed
        ),
        "logloss_delta": max(row["gate_inputs"]["logloss_delta"] for row in per_seed),
        "brier_delta": max(row["gate_inputs"]["brier_delta"] for row in per_seed),
        "ece": max(row["gate_inputs"]["ece"] for row in per_seed),
        "worst_slice_ece": max(row["gate_inputs"]["worst_slice_ece"] for row in per_seed),
        "worst_slice_eligible_count": min(
            row["gate_inputs"]["worst_slice_eligible_count"] for row in per_seed
        ),
        "stability": min(row["gate_inputs"]["stability"] for row in per_seed),
    }
    comparator = "current_reference"
    excluded = ("ranking_ndcg_gain_vs_baseline",)
    gate_report = evaluate_gates(worst, skip=("ranking_ndcg_gain",), comparator=comparator)
    summary = {
        model: {metric: _agg(per_seed, model, metric) for metric in ("log_loss", "brier", "ece")}
        for model in ("current_reference", "updated_candidate")
    }
    return {
        "period_days_inclusive": [C.N_DAYS, C.N_DAYS + new_days - 1],
        "partition_sizes": {key: int(len(idx[key])) for key in ("train", "calib", "test")},
        "train_seeds": list(seeds),
        "summary": summary,
        "critical_review_fixture": fixture,
        "per_seed": per_seed,
        "worst_seed_gate_inputs": worst,
        "gate_comparator": gate_report["comparator"],
        "applicable_gate_count": len(gate_report["gates"]),
        "excluded_gates": list(excluded),
        "gates": gate_report["gates"],
        "decision": "ACCEPT_UPDATE" if gate_report["release_decision"] == "PASS" else "REJECT_UPDATE_KEEP_CURRENT_REFERENCE",
        "note": "Deltas compare each updated offer model with its seed-matched current reference. Ranking is the only excluded gate because this cycle does not change or reevaluate the separate ranking model.",
    }
