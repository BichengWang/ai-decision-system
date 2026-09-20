import hashlib, json, os
from pathlib import Path

import numpy as np
import pytest
from relia import config as C, policy
from relia import run as run_module
from relia.generator import generate_sessions, dataset_hash
from relia.splits import time_group_split, assert_no_leakage
from relia.guards import GuardedRecords, build_features
from relia.metrics import ece, brier, log_loss, psi, ndcg_at_k, worst_slice_ece
from relia.gates import evaluate_gates
from relia.policy import allowed_mask, count_constraint_violations, critical_review_fixture_report
from relia.run import main

SMALL = dict(n_days=40, per_day=200)


def test_generator_deterministic():
    assert dataset_hash(generate_sessions(**SMALL)) == dataset_hash(generate_sessions(**SMALL))


def test_split_has_no_time_or_group_leakage():
    d = generate_sessions(**SMALL)
    idx = time_group_split(d["day"], d["merchant"])
    assert assert_no_leakage(idx, d["day"], d["merchant"], extra_ids=(d["session_id"],))
    assert all(len(idx[k]) > 0 for k in ("train", "calib", "test"))


def test_guard_counts_any_unauthorized_read_and_features_never_touch_them():
    d = generate_sessions(**SMALL)
    rec = GuardedRecords(d)
    build_features(rec)
    assert rec.prohibited_access_count == 0
    _ = rec["zip_income_proxy"]
    assert rec.prohibited_access_count == 1
    for key in ("true_p", "response", "session_id"):
        _ = rec[key]
    assert rec.prohibited_access_count == 4


def test_logged_policy_respects_constraints():
    d = generate_sessions(**SMALL)
    idx = np.arange(len(d["day"]))
    assert count_constraint_violations(d, idx, d["discount"]) == 0
    assert allowed_mask(d, idx)[:, 0].all()          # "no offer" is always permitted
    fixture = critical_review_fixture_report()
    assert fixture == {"total_cases": 16, "critical_cases": 12, "routed_critical_cases": 12,
                       "routing_rate": 1.0, "noncritical_cases": 4,
                       "misrouted_noncritical_cases": 0}
    route_none = lambda chosen, basket: np.zeros(len(chosen), dtype=bool)
    route_all = lambda chosen, basket: np.ones(len(chosen), dtype=bool)
    assert critical_review_fixture_report(route_none)["routed_critical_cases"] == 0
    assert critical_review_fixture_report(route_all)["misrouted_noncritical_cases"] == 4


def test_decision_path_and_fixture_use_the_live_review_router(monkeypatch):
    records = {name: np.zeros(2) for name in C.AUTHORIZED_FEATURES}
    records["basket_value"] = np.array([100.0, 120.0])
    records["category"] = np.array([0, 0])
    discount_col = C.AUTHORIZED_FEATURES.index("discount")

    class PreferTwentyPercent:
        def predict(self, features):
            return np.where(np.isclose(features[:, discount_col], 0.20), 0.99, 0.001)

    faulty_router = lambda chosen, basket: np.zeros(len(chosen), dtype=bool)
    monkeypatch.setattr(policy, "route_to_human", faulty_router)
    chosen, _, routed = policy.decide(PreferTwentyPercent(), records, np.arange(2))

    assert np.allclose(chosen, 0.20)
    assert not routed.any()
    assert policy.critical_review_fixture_report()["routed_critical_cases"] == 0


def test_violation_counter_detects_bad_decisions():
    d = generate_sessions(**SMALL)
    idx = np.arange(len(d["day"]))
    assert count_constraint_violations(d, idx, np.full(len(idx), 0.20)) > 0
    assert count_constraint_violations(d, idx, np.full(len(idx), 0.07)) == len(idx)


def test_metrics_sanity():
    rng = np.random.default_rng(0)
    p = rng.random(20000); y = (rng.random(20000) < p).astype(int)
    assert ece(y, p) < 0.02                         # perfectly calibrated by construction
    assert ece(y, np.clip(p + 0.2, 0, 1)) > 0.1      # miscalibrated
    assert brier(y, p) < brier(y, np.full_like(p, 0.5))
    assert log_loss(y, p) < log_loss(y, np.full_like(p, 0.5))
    assert psi(p, p) < 1e-6 and psi(p, p ** 3) > 0.25
    q = np.repeat(np.arange(50), 10); rel = rng.integers(0, 4, 500)
    assert abs(ndcg_at_k(q, rel, rel.astype(float)) - 1.0) < 1e-9
    assert worst_slice_ece(np.zeros(4), np.zeros(4), np.arange(4), min_n=2)[2] == 0


def test_gates_block_on_any_failure():
    good = dict(prohibited_access=0, constraint_violations=0, critical_review_fixture_n=12,
                critical_review_routing=1.0, critical_review_noncritical_misroutes=0,
                logloss_delta=-0.01, brier_delta=-0.001,
                ece=0.01, worst_slice_ece=0.02, worst_slice_eligible_count=6,
                stability=1.0, ndcg_gain=0.01)
    report = evaluate_gates(good)
    assert report["release_decision"] == "PASS" and len(report["gates"]) == 9
    assert report["comparator"] == "baseline"
    assert "near_equivalent_input_stability" in {g["gate"] for g in report["gates"]}
    assert {g["gate"] for g in report["gates"] if "comparator" in g} == {
        "logloss_delta_vs_baseline", "brier_delta_vs_baseline", "ranking_ndcg_gain_vs_baseline"
    }
    incremental = evaluate_gates(good, comparator="current_reference", skip=("ranking_ndcg_gain",))
    assert incremental["comparator"] == "current_reference"
    assert {g["gate"] for g in incremental["gates"] if "comparator" in g} == {
        "logloss_delta_vs_current_reference", "brier_delta_vs_current_reference"
    }
    for k, bad in [("prohibited_access", 1), ("constraint_violations", 2), ("critical_review_routing", 0.99),
                   ("logloss_delta", 0.001), ("brier_delta", 0.001), ("ece", 0.031),
                   ("worst_slice_ece", 0.06), ("stability", 0.99), ("ndcg_gain", -0.001)]:
        assert evaluate_gates({**good, k: bad})["release_decision"] == "BLOCK", k
    empty = evaluate_gates({**good, "critical_review_fixture_n": 0})
    assert empty["release_decision"] == "BLOCK"
    assert next(g for g in empty["gates"] if g["gate"] == "critical_review_routing_rate")["pass"] is False
    misrouted = evaluate_gates({**good, "critical_review_noncritical_misroutes": 1})
    assert misrouted["release_decision"] == "BLOCK"
    assert next(g for g in misrouted["gates"] if g["gate"] == "critical_review_routing_rate")["pass"] is False
    no_eligible_slices = evaluate_gates({**good, "worst_slice_eligible_count": 0})
    assert no_eligible_slices["release_decision"] == "BLOCK"
    assert next(g for g in no_eligible_slices["gates"] if g["gate"] == "worst_slice_ece")["pass"] is False


def test_spec_constants_frozen():
    assert C.SPLIT_FRACTIONS == (0.60, 0.20, 0.20) and len(C.TRAIN_SEEDS) == 5
    assert C.GATES.max_ece == 0.03 and C.GATES.max_worst_slice_ece == 0.05 and C.GATES.min_stability == 0.995
    assert C.GATES.min_worst_slice_eligible_count == 1
    assert C.GATES.min_critical_review_fixture_n == 12
    assert C.GATES.max_noncritical_review_misroutes == 0


def test_deterministic_artifacts_are_byte_reproducible(tmp_path):
    root = Path(__file__).resolve().parents[1]
    outputs = [tmp_path / "first", tmp_path / "second"]
    outputs[0].mkdir()
    for output in outputs:
        assert main(["--out", str(output)]) == 0

    for name in ("results.json", "MANIFEST.json"):
        first = (outputs[0] / name).read_bytes()
        second = (outputs[1] / name).read_bytes()
        assert first == second

    results = (outputs[0] / "results.json").read_bytes()
    manifest = json.loads((outputs[0] / "MANIFEST.json").read_text())
    assert hashlib.sha256(results).hexdigest() == manifest["results_sha256"]
    assert json.loads(results)["incremental_cycle"]["excluded_gates"] == [
        "ranking_ndcg_gain_vs_baseline"
    ]

    if os.environ.get("RELIA_VERIFY_STORED") == "1":
        assert results == (root / "results" / "results.json").read_bytes()
        assert (outputs[0] / "MANIFEST.json").read_bytes() == (root / "results" / "MANIFEST.json").read_bytes()


def test_cli_returns_nonzero_when_primary_gates_block(tmp_path, monkeypatch):
    evaluate_gates = run_module.evaluate_gates

    def force_primary_block(inputs):
        report = evaluate_gates(inputs)
        report["gates"][0]["pass"] = False
        report["release_decision"] = "BLOCK"
        return report

    monkeypatch.setattr(run_module, "evaluate_gates", force_primary_block)
    assert main(["--out", str(tmp_path / "blocked")]) == 1


def test_cli_refuses_nonempty_output_directory_before_running(tmp_path, monkeypatch):
    output = tmp_path / "existing"
    output.mkdir()
    stale = output / "stale.json"
    stale.write_text("do not overwrite")

    def should_not_run():
        raise AssertionError("evaluation started before output validation")

    monkeypatch.setattr(run_module, "run_all", should_not_run)
    with pytest.raises(SystemExit) as exc:
        main(["--out", str(output)])

    assert exc.value.code == 2
    assert stale.read_text() == "do not overwrite"
