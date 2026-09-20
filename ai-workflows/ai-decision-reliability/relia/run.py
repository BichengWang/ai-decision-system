"""CLI example: python -m relia.run --out review-run

Writes results.json (deterministic, hashed), RESULTS.md, MANIFEST.json and runtime.json
(timing; machine-dependent and therefore excluded from the determinism hash)."""
from __future__ import annotations

import argparse, hashlib, json, os, platform, time
from importlib.metadata import version
from pathlib import Path

import numpy as np

from . import __version__, SPEC_VERSION, config as C
from .gates import evaluate_gates
from .generator import dataset_hash
from .guards import GuardedRecords
from .incremental import guarded_update
from .monitoring import DECISION_LOG_SCHEMA, ALERT_TO_ACTION
from .pipeline import run_all
from .policy import decide


def _agg(per_seed, path):
    vals = []
    for m in per_seed:
        v = m
        for k in path:
            v = v[k]
        vals.append(v)
    return {"mean": float(np.mean(vals)), "min": float(np.min(vals)), "max": float(np.max(vals))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        if not out.is_dir() or any(out.iterdir()):
            ap.error("--out must be a new path or an existing empty directory")
    else:
        out.mkdir(parents=True)

    data, idx, per_seed, models = run_all()
    # Gate on the WORST seed for every metric: a release must pass for all five seeds.
    worst = {
        "prohibited_access": max(m["prohibited_access"] for m in per_seed),
        "constraint_violations": max(m["constraint_violations"] for m in per_seed),
        "critical_review_fixture_n": min(m["critical_review_fixture_n"] for m in per_seed),
        "critical_review_routing": min(m["critical_review_routing"] for m in per_seed),
        "critical_review_noncritical_misroutes": max(
            m["critical_review_noncritical_misroutes"] for m in per_seed
        ),
        "logloss_delta": max(m["logloss_delta"] for m in per_seed),
        "brier_delta": max(m["brier_delta"] for m in per_seed),
        "ece": max(m["ece"] for m in per_seed),
        "worst_slice_ece": max(m["worst_slice_ece"] for m in per_seed),
        "worst_slice_eligible_count": min(m["worst_slice_eligible_count"] for m in per_seed),
        "stability": min(m["stability"] for m in per_seed),
        "ndcg_gain": min(m["ndcg_gain"] for m in per_seed),
    }
    gate_report = evaluate_gates(worst)
    incr = guarded_update(models)

    results = {
        "package_version": __version__, "spec_version": SPEC_VERSION,
        "generator_seed": C.GENERATOR_SEED, "train_seeds": list(C.TRAIN_SEEDS),
        "dataset_sha256": dataset_hash(data),
        "partition_sizes": {k: int(len(idx[k])) for k in ("train", "calib", "test")},
        "time_boundaries_days": list(idx["_boundaries"]),
        "critical_review_fixture": per_seed[0]["critical_review_fixture"],
        "summary": {
            "baseline_log_loss": _agg(per_seed, ("baseline", "log_loss")),
            "candidate_log_loss": _agg(per_seed, ("candidate", "log_loss")),
            "baseline_brier": _agg(per_seed, ("baseline", "brier")),
            "candidate_brier": _agg(per_seed, ("candidate", "brier")),
            "baseline_ece": _agg(per_seed, ("baseline", "ece")),
            "candidate_ece": _agg(per_seed, ("ece",)),
            "worst_slice_ece": _agg(per_seed, ("worst_slice_ece",)),
            "stability": _agg(per_seed, ("stability",)),
            "ranking_baseline_ndcg@10": _agg(per_seed, ("ranking", "baseline", "ndcg@10")),
            "ranking_candidate_ndcg@10": _agg(per_seed, ("ranking", "candidate", "ndcg@10")),
            "ranking_baseline_mrr": _agg(per_seed, ("ranking", "baseline", "mrr")),
            "ranking_candidate_mrr": _agg(per_seed, ("ranking", "candidate", "mrr")),
        },
        "worst_seed_gate_inputs": worst,
        "gate_report": gate_report,
        "incremental_cycle": incr,
        "per_seed": per_seed,
        "decision_log_schema": DECISION_LOG_SCHEMA,
        "alert_to_action": ALERT_TO_ACTION,
    }
    blob = json.dumps(results, indent=2, sort_keys=True, default=float).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    with open(os.path.join(a.out, "results.json"), "wb") as f:
        f.write(blob)

    # runtime (not hashed)
    rec = GuardedRecords(data); sub = idx["test"][:300]; lat = []
    for i in sub:
        t = time.perf_counter(); decide(models[C.TRAIN_SEEDS[0]], rec, np.array([i])); lat.append((time.perf_counter() - t) * 1e3)
    root = Path(__file__).resolve().parents[1]
    lock_path = root / "uv.lock"
    thread_keys = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
    runtime = {"single_request_latency_ms": {"p50": float(np.percentile(lat, 50)), "p95": float(np.percentile(lat, 95))},
               "n_requests": len(lat), "machine": platform.platform(), "architecture": platform.machine(),
               "processor": platform.processor(), "python": platform.python_version(),
               "dependency_versions": {name: version(name) for name in ("numpy", "scipy", "scikit-learn")},
               "uv_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
               "thread_environment": {key: os.environ.get(key) for key in thread_keys},
               "note": "In-process timing on the machine that produced this file; not a service-level measurement."}
    json.dump(runtime, open(os.path.join(a.out, "runtime.json"), "w"), indent=2)
    manifest = json.dumps({"results_sha256": digest, "dataset_sha256": results["dataset_sha256"],
                           "package_version": __version__, "spec_version": SPEC_VERSION}, indent=2)
    with open(os.path.join(a.out, "MANIFEST.json"), "wb") as f:
        f.write(manifest.encode("utf-8"))

    s = results["summary"]; L = []
    L.append(f"# Development results — relia v{__version__} candidate (spec candidate {SPEC_VERSION})\n")
    L.append("All data are synthetic. These results do not establish real-world performance, legal compliance, or fairness across real populations. See `docs/LIMITATIONS.md`.\n")
    L.append(f"- results.json SHA-256: `{digest}`\n- dataset SHA-256: `{results['dataset_sha256']}`")
    L.append(f"- partitions (rows): {results['partition_sizes']}; time boundaries (day): {results['time_boundaries_days']}\n")
    L.append("## Release gates (worst of five seeds)\n\n| Gate | Value | Rule | Result |\n|---|---:|---|---|")
    for g in gate_report["gates"]:
        L.append(f"| {g['gate']} | {g['value']} | {g['rule']} | {'PASS' if g['pass'] else 'FAIL'} |")
    fixture = results["critical_review_fixture"]
    L.append(
        f"\nHuman-review fixture: {fixture['routed_critical_cases']}/{fixture['critical_cases']} "
        f"required-review cases routed; {fixture['misrouted_noncritical_cases']}/"
        f"{fixture['noncritical_cases']} nonrequired cases routed "
        f"({fixture['total_cases']} total boundary cases).\n"
    )
    L.append(f"\n**Release decision: {gate_report['release_decision']}**\n")
    L.append("## Held-out test metrics (mean [min, max] over five seeds)\n\n| Metric | Baseline (logistic) | Candidate (gradient-boosted) |\n|---|---|---|")
    f3 = lambda d: f"{d['mean']:.4f} [{d['min']:.4f}, {d['max']:.4f}]"
    L.append(f"| Log loss | {f3(s['baseline_log_loss'])} | {f3(s['candidate_log_loss'])} |")
    L.append(f"| Brier | {f3(s['baseline_brier'])} | {f3(s['candidate_brier'])} |")
    L.append(f"| ECE (15 bins) | {f3(s['baseline_ece'])} | {f3(s['candidate_ece'])} |")
    L.append(f"| Ranking NDCG@10 | {f3(s['ranking_baseline_ndcg@10'])} | {f3(s['ranking_candidate_ndcg@10'])} |")
    L.append(f"| Ranking MRR | {f3(s['ranking_baseline_mrr'])} | {f3(s['ranking_candidate_mrr'])} |")
    L.append(f"\nWorst-slice ECE: {f3(s['worst_slice_ece'])}. Near-equivalent-input stability: {f3(s['stability'])}.\n")
    d0 = per_seed[0]["drift"]
    L.append(f"## Drift (train vs. test period, seed {per_seed[0]['seed']})\n\nStatus **{d0['status']}**; score PSI {d0['score_psi']:.4f}; feature PSI " + ", ".join(f"{k} {v:.4f}" for k, v in d0["features"].items()) + ".\n")
    L.append(
        f"## Guarded incremental cycle\n\nDecision: **{incr['decision']}** "
        f"(worst of {len(incr['train_seeds'])} seeds; n_test={incr['partition_sizes']['test']}; "
        f"{incr['applicable_gate_count']} applicable gates; ranking alone excluded). "
        f"Delta comparator: **{incr['gate_comparator']}**.\n\n"
        "| Model | Log loss | Brier | ECE |\n|---|---:|---:|---:|"
    )
    for k in ("current_reference", "updated_candidate"):
        v = incr["summary"][k]
        L.append(f"| {k} | {f3(v['log_loss'])} | {f3(v['brier'])} | {f3(v['ece'])} |")
    L.append("\n| Gate | Value | Rule | Result |\n|---|---:|---|---|")
    for g in incr["gates"]:
        L.append(f"| {g['gate']} | {g['value']} | {g['rule']} | {'PASS' if g['pass'] else 'FAIL'} |")
    open(os.path.join(a.out, "RESULTS.md"), "w").write("\n".join(L) + "\n")
    print(gate_report["release_decision"], digest)
    return 0 if gate_report["release_decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
