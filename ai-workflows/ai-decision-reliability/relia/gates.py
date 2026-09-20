"""Release gates: every gate is evaluated and reported; any failure blocks release."""
from __future__ import annotations

from dataclasses import asdict

from . import config as C


def evaluate_gates(m: dict, gates: C.Gates = C.GATES, skip=(), comparator="baseline") -> dict:
    checks = [
        ("prohibited_field_access", "prohibited_access", "<=", gates.max_prohibited_access, False),
        ("constraint_violations", "constraint_violations", "<=", gates.max_constraint_violations, False),
        ("critical_review_routing_rate", "critical_review_routing", ">=", gates.min_critical_review_routing, False),
        ("logloss_delta", "logloss_delta", "<=", gates.max_logloss_degradation, True),
        ("brier_delta", "brier_delta", "<=", gates.max_brier_degradation, True),
        ("ece", "ece", "<=", gates.max_ece, False),
        ("worst_slice_ece", "worst_slice_ece", "<=", gates.max_worst_slice_ece, False),
        ("near_equivalent_input_stability", "stability", ">=", gates.min_stability, False),
        ("ranking_ndcg_gain", "ndcg_gain", ">=", gates.min_ndcg_gain, True),
    ]
    rows = []
    for base_name, key, op, thr, comparative in checks:
        name = f"{base_name}_vs_{comparator}" if comparative else base_name
        if name in skip or base_name in skip:
            continue
        value = m[key]
        ok = value <= thr if op == "<=" else value >= thr
        row = {"gate": name, "value": round(float(value), 6), "rule": f"{op} {thr}", "pass": bool(ok)}
        if comparative:
            row["comparator"] = comparator
        if name == "critical_review_routing_rate":
            fixture_n = int(m.get("critical_review_fixture_n", 0))
            noncritical_misroutes = int(m["critical_review_noncritical_misroutes"])
            row["fixture_n"] = fixture_n
            row["noncritical_misroutes"] = noncritical_misroutes
            row["rule"] = (
                f"{op} {thr} and fixture_n >= {gates.min_critical_review_fixture_n} "
                f"and noncritical_misroutes <= {gates.max_noncritical_review_misroutes}"
            )
            row["pass"] = bool(
                ok
                and fixture_n >= gates.min_critical_review_fixture_n
                and noncritical_misroutes <= gates.max_noncritical_review_misroutes
            )
        if name == "worst_slice_ece":
            eligible_slices = int(m.get("worst_slice_eligible_count", 0))
            row["eligible_slices"] = eligible_slices
            row["rule"] = (
                f"{op} {thr} and eligible_slices >= {gates.min_worst_slice_eligible_count}"
            )
            row["pass"] = bool(
                ok and eligible_slices >= gates.min_worst_slice_eligible_count
            )
        rows.append(row)
    return {"gates": rows, "release_decision": "PASS" if all(r["pass"] for r in rows) else "BLOCK",
            "comparator": comparator, "thresholds": asdict(gates)}
