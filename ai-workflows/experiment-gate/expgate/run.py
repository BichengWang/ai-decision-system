"""CLI: evaluate an experiment summary and write a decision record.

    python -m expgate.run --scenario win --out review-run
    python -m expgate.run --input examples/offer-ranker-v2.json --out review-run
    python -m expgate.run --input exports/*.json --out review-run
    python -m expgate.run --all-scenarios --out review-run

Writes ``decision.json`` (deterministic, sorted keys) and ``DECISION.md`` per
experiment, in ``--out`` itself for one experiment and in ``--out/<experiment>/`` for
several. Every summary is read and evaluated before anything is written, so invalid
input leaves no partial records. ``--require-ship`` exits 1 unless every evaluated experiment ships,
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
    L.append(f"- expgate {__version__}; alpha {report['policy']['alpha']}; SRM alpha {report['policy']['srm_alpha']}; "
             f"power {report['policy']['power']}")
    L.append(f"- assignment: {srm['control_units']} control / {srm['treatment_units']} treatment "
             f"(expected treatment share {srm['expected_treatment_share']}); SRM p={srm['p_value']:.3g} "
             f"-> {'PASS' if srm['pass'] else 'FAIL'}\n")
    L.append("| Metric | Role | Control | Treatment | Improvement [bounds] | Margin | MDE | Status |")
    L.append("|---|---|---:|---:|---|---:|---:|---|")
    for m in report["metrics"]:
        lo, hi = m["improvement_bounds"]
        L.append(f"| {m['metric']} | {m['role']} | {_fmt(m['control'])} | {_fmt(m['treatment'])} | "
                 f"{_fmt(m['improvement'])} [{_fmt(lo)}, {_fmt(hi)}] | {_fmt(m['margin']) if 'margin' in m else ''} | "
                 f"{_fmt(m['mde'])} | {m['status']} |")
    L.append("\nImprovement is signed so that positive values are desirable. Guardrail bounds are "
             "one-sided and Bonferroni-adjusted across guardrails. MDE is the smallest true improvement "
             f"each bound would detect with {report['policy']['power']:.0%} power at the current sample size.")
    if "sequential" in report:
        q = report["sequential"]
        L.append(f"\nSequential monitoring: {q['units']} of {q['planned_units']} planned units "
                 f"({q['information_fraction']:.0%}). Bounds are always-valid confidence sequences, so this "
                 "decision stays valid however often the experiment has been checked.")
    for m in report["metrics"]:
        if "adjustment" in m:
            a = m["adjustment"]
            L.append(f"\nCUPED on `{m['metric']}`: theta {_fmt(a['theta'])}; unadjusted difference {_fmt(a['raw_diff'])} "
                     f"(SE {_fmt(a['raw_se'])}), adjusted {_fmt(m['diff'])} (SE {_fmt(m['se'])}); "
                     f"variance reduction {a['variance_reduction']:.1%}.")
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
    src.add_argument("--input", type=Path, nargs="+", help="one or more experiment summary JSON files")
    ap.add_argument("--out", type=Path, required=True, help="new or empty output directory")
    ap.add_argument("--require-ship", action="store_true", help="exit 1 unless every decision is SHIP")
    a = ap.parse_args(argv)

    if a.out.exists() and (not a.out.is_dir() or any(a.out.iterdir())):
        ap.error("--out must be a new path or an existing empty directory")

    if a.input:
        summaries = []
        for path in a.input:
            try:
                summaries.append((str(path), json.loads(path.read_text())))
            except (OSError, ValueError) as exc:
                print(f"error: cannot read experiment summary {path}: {exc}", file=sys.stderr)
                return 2
    elif a.all_scenarios:
        summaries = [(name, generate(name)) for name in sorted(SCENARIOS)]
    else:
        summaries = [(a.scenario, generate(a.scenario))]

    reports = []
    for source, summary in summaries:
        try:
            reports.append(evaluate(summary))
        except (KeyError, TypeError, ValueError) as exc:
            print(f"error: invalid experiment summary {source}: {exc}", file=sys.stderr)
            return 2
    if len(reports) > 1:
        problem = _batch_problem(summaries, reports)
        if problem:
            print(f"error: {problem}", file=sys.stderr)
            return 2

    decisions = []
    for report in reports:
        target = a.out / report["experiment"] if len(reports) > 1 else a.out
        digest = write_record(report, target)
        decisions.append(report["decision"])
        print(f"{report['experiment']}: {report['decision']} {digest}")

    return 1 if a.require_ship and any(d != "SHIP" for d in decisions) else 0


def _batch_problem(summaries, reports) -> str | None:
    """Several records share --out, one directory per experiment, so names must be usable and unique."""
    seen = {}
    for (source, summary), report in zip(summaries, reports):
        name = report["experiment"]
        if "experiment" not in summary:
            return f"{source}: an experiment name is required when evaluating several summaries"
        if name in (".", "..") or name.startswith(".") or any(c in name for c in "/\\\0") or name != name.strip():
            return f"{source}: experiment name {name!r} cannot be used as a directory name"
        if name.casefold() in seen:
            return f"{source}: experiment name {name!r} is also used by {seen[name.casefold()]}"
        seen[name.casefold()] = source
    return None


if __name__ == "__main__":
    raise SystemExit(main())
