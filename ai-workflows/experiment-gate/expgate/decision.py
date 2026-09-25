"""Ship / hold / rollback decision for a two-arm experiment summary.

Rules, applied in order:

1. INVALID  - sample-ratio mismatch (assignment split differs from the design at
              ``srm_alpha``); no effect estimate is trusted.
2. ROLLBACK - the primary metric is significantly worse than control, or any
              guardrail is significantly worse *and* its point degradation
              exceeds the guardrail margin.
3. SHIP     - the primary metric improves significantly and every guardrail is
              shown non-inferior (upper degradation bound below its margin).
4. HOLD     - anything else: the experiment is inconclusive; collect more data.

Guardrail bounds are one-sided and Bonferroni-adjusted across guardrails; the
primary metric uses a one-sided test at ``alpha``.
"""
from __future__ import annotations

from . import stats

DECISIONS = ("SHIP", "HOLD", "ROLLBACK", "INVALID")
_DIRECTIONS = {"increase": 1.0, "decrease": -1.0}


def _effect(spec: dict, control: dict, treatment: dict, name: str) -> stats.Effect:
    c, t = control["metrics"][name], treatment["metrics"][name]
    if spec["type"] == "proportion":
        return stats.proportion_effect(c["successes"], control["units"], t["successes"], treatment["units"])
    if spec["type"] == "mean":
        return stats.mean_effect(c["mean"], c["sd"], control["units"], t["mean"], t["sd"], treatment["units"])
    raise ValueError(f"metric {name!r}: unknown type {spec['type']!r}")


def _validate(summary: dict) -> None:
    metrics = summary.get("metrics") or {}
    primaries = [n for n, s in metrics.items() if s.get("role") == "primary"]
    if len(primaries) != 1:
        raise ValueError("exactly one metric must have role 'primary'")
    for name, spec in metrics.items():
        if spec.get("role") not in ("primary", "guardrail"):
            raise ValueError(f"metric {name!r}: role must be 'primary' or 'guardrail'")
        if spec.get("direction") not in _DIRECTIONS:
            raise ValueError(f"metric {name!r}: direction must be 'increase' or 'decrease'")
        if spec["role"] == "guardrail" and not spec.get("margin", -1) >= 0:
            raise ValueError(f"guardrail {name!r} needs a non-negative 'margin'")
    for arm in ("control", "treatment"):
        missing = set(metrics) - set(summary["arms"][arm]["metrics"])
        if missing:
            raise ValueError(f"arm {arm!r} is missing metrics {sorted(missing)}")


def evaluate(summary: dict) -> dict:
    """Return a JSON-serializable decision report for an experiment summary."""
    _validate(summary)
    policy = {"alpha": 0.05, "srm_alpha": 0.001, **summary.get("policy", {})}
    control, treatment = summary["arms"]["control"], summary["arms"]["treatment"]
    share = summary.get("assignment", {}).get("expected_treatment_share", 0.5)

    srm_p = stats.sample_ratio_p_value(control["units"], treatment["units"], share)
    srm = {"control_units": control["units"], "treatment_units": treatment["units"],
           "expected_treatment_share": share, "p_value": srm_p,
           "pass": srm_p >= policy["srm_alpha"]}

    guardrails = [n for n, s in summary["metrics"].items() if s["role"] == "guardrail"]
    z_primary = stats.z_for(policy["alpha"])
    z_guard = stats.z_for(policy["alpha"] / max(len(guardrails), 1))

    rows, reasons = [], []
    primary_status = None
    guard_status = {}
    for name, spec in sorted(summary["metrics"].items(), key=lambda kv: (kv[1]["role"] != "primary", kv[0])):
        eff = _effect(spec, control, treatment, name)
        sign = _DIRECTIONS[spec["direction"]]
        # "improvement" is positive when treatment moves the metric the desired way.
        improvement = sign * eff.diff
        z = z_primary if spec["role"] == "primary" else z_guard
        lo, hi = improvement - z * eff.se, improvement + z * eff.se
        row = {"metric": name, "role": spec["role"], "type": spec["type"], "direction": spec["direction"],
               "control": eff.control, "treatment": eff.treatment, "diff": eff.diff, "se": eff.se,
               "improvement": improvement, "improvement_bounds": [lo, hi], "z": z}
        if spec["role"] == "primary":
            status = "IMPROVED" if lo > 0 else ("DEGRADED" if hi < 0 else "INCONCLUSIVE")
            primary_status = status
        else:
            margin = spec["margin"]
            degradation, degr_lo, degr_hi = -improvement, -hi, -lo
            if degr_lo > 0 and degradation > margin:
                status = "BREACH"
            elif degr_hi < margin:
                status = "NON_INFERIOR"
            else:
                status = "INCONCLUSIVE"
            row["margin"] = margin
            guard_status[name] = status
        row["status"] = status
        rows.append(row)

    if not srm["pass"]:
        decision = "INVALID"
        reasons.append(f"sample-ratio mismatch (p={srm_p:.2e} < {policy['srm_alpha']})")
    elif primary_status == "DEGRADED" or any(s == "BREACH" for s in guard_status.values()):
        decision = "ROLLBACK"
        if primary_status == "DEGRADED":
            reasons.append("primary metric degraded")
        reasons += [f"guardrail {n} breached its margin" for n, s in sorted(guard_status.items()) if s == "BREACH"]
    elif primary_status == "IMPROVED" and all(s == "NON_INFERIOR" for s in guard_status.values()):
        decision = "SHIP"
        reasons.append("primary metric improved and all guardrails are non-inferior")
    else:
        decision = "HOLD"
        if primary_status != "IMPROVED":
            reasons.append(f"primary metric is {primary_status.lower()}")
        reasons += [f"guardrail {n} is inconclusive" for n, s in sorted(guard_status.items()) if s == "INCONCLUSIVE"]

    return {"experiment": summary.get("experiment", "unnamed"), "decision": decision, "reasons": reasons,
            "policy": policy, "sample_ratio": srm, "metrics": rows}
