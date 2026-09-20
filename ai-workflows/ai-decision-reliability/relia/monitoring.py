"""Monitoring record schema, alert actions, and drift report."""
from __future__ import annotations

import numpy as np

from . import config as C
from .metrics import ece, psi, brier

DECISION_LOG_SCHEMA = {
    "request_id": "str", "ts": "iso8601", "model_version": "str", "spec_version": "str",
    "authorized_fields_read": "list[str]", "prohibited_access_count": "int",
    "decision_discount": "float", "expected_utility": "float",
    "review_route": "none|human", "constraint_check": "pass|fail",
    "latency_ms": "float", "error": "str|null",
}

DRIFT_FEATURES = ("basket_value", "distance_km", "merchant_quality")
PSI_WARN, PSI_ALERT = 0.10, 0.25


def drift_report(records, ref_idx, cur_idx, p_ref, p_cur, y_cur=None) -> dict:
    out = {"features": {}, "score_psi": psi(p_ref, p_cur)}
    for f in DRIFT_FEATURES:
        v = np.asarray(records[f], dtype=float)
        out["features"][f] = psi(v[ref_idx], v[cur_idx])
    worst = max([out["score_psi"], *out["features"].values()])
    out["status"] = "ALERT" if worst >= PSI_ALERT else "WARN" if worst >= PSI_WARN else "OK"
    if y_cur is not None:
        out["current_ece"] = ece(y_cur, p_cur, C.GATES.ece_bins)
        out["current_brier"] = brier(y_cur, p_cur)
    return out


ALERT_TO_ACTION = [
    {"signal": "prohibited_access_count > 0", "severity": "SEV1", "action": "pause version; rollback; incident record"},
    {"signal": "constraint_check == fail", "severity": "SEV1", "action": "pause version; rollback; incident record"},
    {"signal": "critical case not routed to human", "severity": "SEV1", "action": "pause; rollback; incident record"},
    {"signal": "weekly ECE > gate", "severity": "SEV2", "action": "human review; recalibrate candidate; rerun frozen gates"},
    {"signal": "PSI >= 0.25 on score or monitored feature", "severity": "SEV2", "action": "human review; guarded incremental update"},
    {"signal": "PSI in [0.10, 0.25)", "severity": "SEV3", "action": "annotate weekly report; watch"},
    {"signal": "p95 latency or error-rate regression", "severity": "SEV2", "action": "pause rollout; diagnose; rerun deployment-specific smoke/canary test when defined"},
]
