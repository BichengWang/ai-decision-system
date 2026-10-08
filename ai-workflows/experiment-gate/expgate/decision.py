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

A metric may carry a pre-experiment ``covariate`` summary in both arms. It is then
estimated with CUPED regression adjustment (see :func:`expgate.stats.cuped_effect`),
which narrows the interval without moving the decision rules above.

With ``policy.sequential.planned_units`` set, every bound is an always-valid confidence
sequence instead (see :func:`expgate.stats.sequential_multiplier`). The same rules then hold
at every interim look: the summary can be evaluated as often as the platform refreshes it,
and SHIP or ROLLBACK can be declared as soon as a bound clears, without inflating the error
rates that the fixed-horizon bounds would.
"""
from __future__ import annotations

import math

from . import stats

DECISIONS = ("SHIP", "HOLD", "ROLLBACK", "INVALID")
_DIRECTIONS = {"increase": 1.0, "decrease": -1.0}
_TYPES = ("proportion", "mean")


def _covariate(stat: dict) -> stats.Covariate:
    cov = stat["covariate"]
    return stats.Covariate(cov["mean"], cov["sd"], cov["corr"])


def _effect(spec: dict, control: dict, treatment: dict, name: str):
    """Return ``(Effect, adjustment)``; ``adjustment`` is None unless a covariate was supplied."""
    c, t = control["metrics"][name], treatment["metrics"][name]
    adjusted = "covariate" in c
    if spec["type"] == "proportion":
        if adjusted:
            return stats.cuped_effect(
                c["successes"] / control["units"], stats.proportion_variance(c["successes"], control["units"]),
                control["units"], _covariate(c),
                t["successes"] / treatment["units"], stats.proportion_variance(t["successes"], treatment["units"]),
                treatment["units"], _covariate(t))
        return stats.proportion_effect(c["successes"], control["units"], t["successes"], treatment["units"]), None
    if spec["type"] == "mean":
        if adjusted:
            return stats.cuped_effect(c["mean"], c["sd"] ** 2, control["units"], _covariate(c),
                                      t["mean"], t["sd"] ** 2, treatment["units"], _covariate(t))
        return stats.mean_effect(c["mean"], c["sd"], control["units"], t["mean"], t["sd"], treatment["units"]), None
    raise ValueError(f"metric {name!r}: unknown type {spec['type']!r}")


def _object(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be a JSON object")
    return value


def _number(value, where: str) -> float:
    # bool is an int subclass; JSON true/false is never a valid measurement.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where} must be a finite number")
    return value


def _count(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{where} must be an integer")
    return value


_POLICY_KEYS = {"alpha", "srm_alpha", "sequential"}
_SEQUENTIAL_KEYS = {"planned_units"}
_ASSIGNMENT_KEYS = {"expected_treatment_share"}


def _known_keys(value: dict, allowed: set, where: str) -> None:
    # A misspelled setting would otherwise be ignored and its default applied silently.
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{where} has unknown keys {sorted(unknown)}; expected only {sorted(allowed)}")


def _validate(summary: dict) -> None:
    _object(summary, "experiment summary")
    if "experiment" in summary and (not isinstance(summary["experiment"], str) or not summary["experiment"].strip()):
        raise ValueError("'experiment' must be a non-empty string")
    metrics = _object(summary.get("metrics"), "'metrics'")
    for name, spec in metrics.items():
        _object(spec, f"metric {name!r}")
    primaries = [n for n, s in metrics.items() if s.get("role") == "primary"]
    if len(primaries) != 1:
        raise ValueError("exactly one metric must have role 'primary'")
    for name, spec in metrics.items():
        if spec.get("role") not in ("primary", "guardrail"):
            raise ValueError(f"metric {name!r}: role must be 'primary' or 'guardrail'")
        if spec.get("type") not in _TYPES:
            raise ValueError(f"metric {name!r}: type must be 'proportion' or 'mean'")
        if spec.get("direction") not in _DIRECTIONS:
            raise ValueError(f"metric {name!r}: direction must be 'increase' or 'decrease'")
        if spec["role"] == "guardrail":
            if "margin" not in spec or _number(spec["margin"], f"guardrail {name!r} margin") < 0:
                raise ValueError(f"guardrail {name!r} needs a non-negative 'margin'")

    policy = _object(summary.get("policy", {}), "'policy'")
    _known_keys(policy, _POLICY_KEYS, "'policy'")
    for key in ("alpha", "srm_alpha"):
        value = policy.get(key)
        if value is not None and not 0 < _number(value, f"policy {key}") < 1:
            raise ValueError(f"policy {key} must be in (0, 1)")
    if "sequential" in policy:
        sequential = _object(policy["sequential"], "policy sequential")
        _known_keys(sequential, _SEQUENTIAL_KEYS, "policy sequential")
        if _count(sequential.get("planned_units"), "policy sequential planned_units") < 2:
            raise ValueError("policy sequential planned_units must be at least 2")
    assignment = _object(summary.get("assignment", {}), "'assignment'")
    _known_keys(assignment, _ASSIGNMENT_KEYS, "'assignment'")
    share = assignment.get("expected_treatment_share")
    if share is not None and not 0 < _number(share, "expected_treatment_share") < 1:
        raise ValueError("expected_treatment_share must be in (0, 1)")

    arms = _object(summary.get("arms"), "'arms'")
    for arm_name in ("control", "treatment"):
        arm = _object(arms.get(arm_name), f"arm {arm_name!r}")
        units = _count(arm.get("units"), f"arm {arm_name!r} units")
        if units < 1:
            raise ValueError(f"arm {arm_name!r} units must be at least 1")
        observed = _object(arm.get("metrics"), f"arm {arm_name!r} metrics")
        missing = set(metrics) - set(observed)
        if missing:
            raise ValueError(f"arm {arm_name!r} is missing metrics {sorted(missing)}")
        for name, spec in metrics.items():
            where = f"arm {arm_name!r} metric {name!r}"
            stat = _object(observed[name], where)
            fields = {"successes"} if spec["type"] == "proportion" else {"mean", "sd"}
            _known_keys(stat, fields | {"covariate"}, where)
            if spec["type"] == "proportion":
                successes = _count(stat.get("successes"), f"{where} successes")
                if not 0 <= successes <= units:
                    raise ValueError(f"{where} successes must be between 0 and units")
            else:
                _number(stat.get("mean"), f"{where} mean")
                if _number(stat.get("sd"), f"{where} sd") < 0:
                    raise ValueError(f"{where} sd must be non-negative")
            if "covariate" in stat:
                cov = _object(stat["covariate"], f"{where} covariate")
                _known_keys(cov, {"mean", "sd", "corr"}, f"{where} covariate")
                _number(cov.get("mean"), f"{where} covariate mean")
                if _number(cov.get("sd"), f"{where} covariate sd") <= 0:
                    raise ValueError(f"{where} covariate sd must be positive")
                if not -1 <= _number(cov.get("corr"), f"{where} covariate corr") <= 1:
                    raise ValueError(f"{where} covariate corr must be in [-1, 1]")
                if units < 2:
                    raise ValueError(f"{where} needs at least 2 units for a covariate adjustment")
    for name in metrics:
        have = ["covariate" in arms[a]["metrics"][name] for a in ("control", "treatment")]
        if have[0] != have[1]:
            raise ValueError(f"metric {name!r}: supply the covariate in both arms or in neither")


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
    alpha_primary, alpha_guard = policy["alpha"], policy["alpha"] / max(len(guardrails), 1)
    sequential = None
    if "sequential" in policy:
        units = control["units"] + treatment["units"]
        planned = policy["sequential"]["planned_units"]
        sequential = {"planned_units": planned, "units": units, "information_fraction": units / planned}
        z_primary = stats.sequential_multiplier(alpha_primary, planned / units)
        z_guard = stats.sequential_multiplier(alpha_guard, planned / units)
    else:
        z_primary, z_guard = stats.z_for(alpha_primary), stats.z_for(alpha_guard)

    rows, reasons = [], []
    primary_status = None
    guard_status = {}
    for name, spec in sorted(summary["metrics"].items(), key=lambda kv: (kv[1]["role"] != "primary", kv[0])):
        eff, adjustment = _effect(spec, control, treatment, name)
        sign = _DIRECTIONS[spec["direction"]]
        # "improvement" is positive when treatment moves the metric the desired way.
        improvement = sign * eff.diff
        z = z_primary if spec["role"] == "primary" else z_guard
        lo, hi = improvement - z * eff.se, improvement + z * eff.se
        row = {"metric": name, "role": spec["role"], "type": spec["type"], "direction": spec["direction"],
               "control": eff.control, "treatment": eff.treatment, "diff": eff.diff, "se": eff.se,
               "improvement": improvement, "improvement_bounds": [lo, hi], "z": z}
        if adjustment is not None:
            row["adjustment"] = adjustment
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
        if sequential is not None and sequential["information_fraction"] >= 1:
            reasons.append("planned sample size reached without a decision")

    report = {"experiment": summary.get("experiment", "unnamed"), "decision": decision, "reasons": reasons,
              "policy": policy, "sample_ratio": srm, "metrics": rows}
    if sequential is not None:
        report["sequential"] = sequential
    return report
