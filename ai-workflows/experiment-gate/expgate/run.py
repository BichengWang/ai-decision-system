"""CLI: evaluate an experiment summary and write a decision record.

    python -m expgate.run --scenario win --out review-run
    python -m expgate.run --input examples/offer-ranker-v2.json --out review-run
    python -m expgate.run --all-scenarios --out review-run

Writes ``decision.json`` (deterministic, sorted keys) and ``DECISION.md`` per
experiment. ``--require-ship`` exits 1 unless every evaluated experiment ships,
so the command can gate a promotion step in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import __version__
from .decision import evaluate
from .generator import SCENARIOS, generate


def _fmt(x: float) -> str:
    return f"{x:.6g}"


def render_markdown(report: dict, digest: str) -> str:
    L = [f"# Experiment decision: {report['experiment']}\n",
         f"**Decision: {report['decision']}**\n"]
    L += [f"- {r}" for r in report["reasons"]]
    srm = report["sample_ratio"]
    L.append(f"\n- decision.json SHA-256: `{digest}`")
    L.append(f"- expgate {__version__}; alpha {report['policy']['alpha']}; SRM alpha {report['policy']['srm_alpha']}")
    L.append(f"- assignment: {srm['control_units']} control / {srm['treatment_units']} treatment "
             f"(expected treatment share {srm['expected_treatment_share']}); SRM p={srm['p_value']:.3g} "
             f"-> {'PASS' if srm['pass'] else 'FAIL'}\n")
    L.append("| Metric | Role | Control | Treatment | Improvement [bounds] | Margin | Status |")
    L.append("|---|---|---:|---:|---|---:|---|")
    for m in report["metrics"]:
        lo, hi = m["improvement_bounds"]
        L.append(f"| {m['metric']} | {m['role']} | {_fmt(m['control'])} | {_fmt(m['treatment'])} | "
                 f"{_fmt(m['improvement'])} [{_fmt(lo)}, {_fmt(hi)}] | {_fmt(m['margin']) if 'margin' in m else ''} | "
                 f"{m['status']} |")
    L.append("\nImprovement is signed so that positive values are desirable. Guardrail bounds are "
             "one-sided and Bonferroni-adjusted across guardrails.")
    return "\n".join(L) + "\n"


def write_record(report: dict, out: Path) -> str:
    out.mkdir(parents=True, exist_ok=True)
    blob = json.dumps({"expgate_version": __version__, **report}, indent=2, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    (out / "decision.json").write_bytes(blob)
    (out / "DECISION.md").write_text(render_markdown(report, digest))
    return digest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m expgate.run", description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--scenario", choices=sorted(SCENARIOS))
    src.add_argument("--all-scenarios", action="store_true")
    src.add_argument("--input", type=Path, help="experiment summary JSON")
    ap.add_argument("--out", type=Path, required=True, help="new or empty output directory")
    ap.add_argument("--require-ship", action="store_true", help="exit 1 unless every decision is SHIP")
    a = ap.parse_args(argv)

    if a.out.exists() and (not a.out.is_dir() or any(a.out.iterdir())):
        ap.error("--out must be a new path or an existing empty directory")

    if a.input:
        try:
            summaries = [json.loads(a.input.read_text())]
        except (OSError, ValueError) as exc:
            print(f"error: cannot read experiment summary: {exc}", file=sys.stderr)
            return 2
    elif a.all_scenarios:
        summaries = [generate(name) for name in sorted(SCENARIOS)]
    else:
        summaries = [generate(a.scenario)]

    decisions = []
    for summary in summaries:
        try:
            report = evaluate(summary)
        except (KeyError, TypeError, ValueError) as exc:
            print(f"error: invalid experiment summary: {exc}", file=sys.stderr)
            return 2
        target = a.out / report["experiment"] if len(summaries) > 1 else a.out
        digest = write_record(report, target)
        decisions.append(report["decision"])
        print(f"{report['experiment']}: {report['decision']} {digest}")

    return 1 if a.require_ship and any(d != "SHIP" for d in decisions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
