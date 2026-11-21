"""CLI: evaluate an experiment summary and write a decision record.

    python -m expgate.run --scenario win --out review-run
    python -m expgate.run --input examples/offer-ranker-v2.json --out review-run
    python -m expgate.run --input exports/*.json --out review-run
    python -m expgate.run --all-scenarios --out review-run
    python -m expgate.run --all-scenarios --out review-run --sign-key signing.key
    python -m expgate keygen signing.key
    python -m expgate.run --from growthbook results.json --mapping mapping.json --out review-run

Writes ``decision.json`` (deterministic, sorted keys) and ``DECISION.md`` per
experiment, in ``--out`` itself for one experiment and in ``--out/<experiment>/`` for
several. Every summary is read and evaluated before anything is written, so invalid
input leaves no partial records. ``--require-ship`` exits 1 unless every evaluated experiment ships,
so the command can gate a promotion step in CI. ``--sign-key KEYFILE`` also writes
``decision.json.dsse.json`` (an HMAC-signed in-toto statement about the exact bytes) next to each record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import sys
import unicodedata
from pathlib import Path

from . import __version__, attestation, signing
from .decision import evaluate
from .generator import SCENARIOS, generate
from .importers import growthbook


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
    source = report["input"].get("source")
    if source:
        L.insert(-1, f"- imported from a {source['format']} export, SHA-256 `{source['export_sha256']}`; "
                     "the decision uses only the exported counts, means and standard deviations")
    L.append("| Metric | Role | Control | Treatment | Improvement [bounds] | Margin | MDE | Status |")
    L.append("|---|---|---:|---:|---|---:|---:|---|")
    for m in report["metrics"]:
        lo, hi = m["improvement_bounds"]
        L.append(f"| {m['metric']} | {m['role']} | {_fmt(m['control'])} | {_fmt(m['treatment'])} | "
                 f"{_fmt(m['improvement'])} [{_fmt(lo)}, {_fmt(hi)}] | {_fmt(m['margin']) if 'margin' in m else ''} | "
                 f"{_fmt(m['mde'])} | {m['status']} |")
    L.append("\nImprovement is signed so that positive values are desirable. Guardrail bounds are "
             "one-sided and Bonferroni-adjusted across guardrails. MDE uses the normal approximation "
             "and the observed standard error; zero-error metrics are inconclusive.")
    if "sequential" in report:
        q = report["sequential"]
        L.append(f"\nSequential monitoring: {q['units']} of {q['planned_units']} planned units "
                 f"({q['information_fraction']:.0%}). Bounds are confidence sequences under "
                 "the normal model with known variance; observed-variance plug-in bounds are approximate. "
                 "MDE is a current-look approximation, not a sequential stopping-power guarantee.")
    for m in report["metrics"]:
        if "adjustment" in m:
            a = m["adjustment"]
            L.append(f"\nCUPED on `{m['metric']}`: theta {_fmt(a['theta'])}; unadjusted difference {_fmt(a['raw_diff'])} "
                     f"(SE {_fmt(a['raw_se'])}), adjusted {_fmt(m['diff'])} (SE {_fmt(m['se'])}); "
                     f"variance reduction {a['variance_reduction']:.1%}.")
    return "\n".join(L) + "\n"


def record_bytes(report: dict) -> bytes:
    """The exact ``decision.json`` bytes; pretty-printed, so unrelated to the canonical input digest."""
    return json.dumps({"expgate_version": __version__, **report}, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")


def write_record(report: dict, out: Path) -> str:
    out.mkdir(parents=True, exist_ok=True)
    blob = record_bytes(report)
    digest = hashlib.sha256(blob).hexdigest()
    (out / "decision.json").write_bytes(blob)
    (out / "DECISION.md").write_text(render_markdown(report, digest), encoding="utf-8")
    return digest


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args and args[0] in ("keygen", "predicate"):
        return attestation.command(args)
    ap = argparse.ArgumentParser(prog="python -m expgate.run", description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--scenario", choices=sorted(SCENARIOS))
    src.add_argument("--all-scenarios", action="store_true")
    src.add_argument("--input", type=Path, nargs="+", help="one or more experiment summary JSON files")
    src.add_argument("--from", dest="from_export", nargs=2, metavar=("FORMAT", "FILE"),
                     help="convert an exported results file (FORMAT: growthbook) instead of reading a summary; "
                          "requires --mapping")
    ap.add_argument("--mapping", type=Path, help="metric mapping JSON for --from (types, directions, margins)")
    ap.add_argument("--out", type=Path, required=True, help="new or empty output directory")
    ap.add_argument("--sign-key", type=Path, help="HMAC key file; writes decision.json.dsse.json next to each record")
    ap.add_argument("--require-ship", action="store_true", help="exit 1 unless every decision is SHIP")
    a = ap.parse_args(args)

    if a.out.exists() and (not a.out.is_dir() or any(a.out.iterdir())):
        ap.error("--out must be a new path or an existing empty directory")
    if a.mapping and not a.from_export:
        ap.error("--mapping is only used with --from")
    if a.from_export and not a.mapping:
        ap.error("--from needs --mapping: the export does not carry metric types, directions or guardrail margins")
    if a.from_export and a.from_export[0] != growthbook.FORMAT:
        ap.error(f"unsupported --from format {a.from_export[0]!r}; supported: {growthbook.FORMAT}")

    try:
        key = signing.load_key(a.sign_key) if a.sign_key else None  # read first: a bad key writes nothing
    except signing.KeyFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if a.input:
        summaries = []
        for path in a.input:
            try:
                summaries.append((str(path), json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, RecursionError) as exc:
                print(f"error: cannot read experiment summary {path}: {exc}", file=sys.stderr)
                return 2
    elif a.from_export:
        export_path = Path(a.from_export[1])
        try:
            export, mapping_bytes = export_path.read_bytes(), a.mapping.read_bytes()
        except OSError as exc:
            print(f"error: cannot read {exc.filename}: {exc.strerror}", file=sys.stderr)
            return 2
        try:
            summaries = [(str(export_path), growthbook.convert(export, growthbook.load_mapping(mapping_bytes)))]
        except growthbook.GrowthBookImportError as exc:
            print(f"error: cannot import GrowthBook export {export_path}: {exc}", file=sys.stderr)
            return 2
    elif a.all_scenarios:
        summaries = [(name, generate(name)) for name in sorted(SCENARIOS)]
    else:
        summaries = [(a.scenario, generate(a.scenario))]

    reports = []
    for source, summary in summaries:
        try:
            reports.append(evaluate(summary))
        except (KeyError, TypeError, ValueError, ArithmeticError, RecursionError) as exc:
            print(f"error: invalid experiment summary {source}: {exc}", file=sys.stderr)
            return 2
    if len(reports) > 1:
        problem = _batch_problem(summaries, reports)
        if problem:
            print(f"error: {problem}", file=sys.stderr)
            return 2

    completed = []
    try:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{a.out.name}-", dir=a.out.parent) as staging:
            staged = Path(staging) / "output"
            for report in reports:
                target = staged / report["experiment"] if len(reports) > 1 else staged
                completed.append((report, write_record(report, target)))
                if key is not None:
                    _write_envelope(target, report, key)
            os.replace(staged, a.out)
    except OSError as exc:
        print(f"error: cannot write decision records: {exc}", file=sys.stderr)
        return 2
    for report, digest in completed:
        print(f"{report['experiment']}: {report['decision']} {digest}")
    return 1 if a.require_ship and any(r["decision"] != "SHIP" for r in reports) else 0


def _write_envelope(target: Path, report: dict, key: bytes) -> None:
    """Sign the bytes of the ``decision.json`` just written, the exact subject a verifier will read."""
    data = (target / "decision.json").read_bytes()
    envelope = attestation.sign_bytes(data, "decision.json", report, key)
    (target / ("decision.json" + attestation.ENVELOPE_SUFFIX)).write_text(
        attestation.render_envelope(envelope), encoding="utf-8")


def _batch_problem(summaries, reports) -> str | None:
    """Several records share --out, one directory per experiment, so names must be usable and unique."""
    seen = {}
    for (source, summary), report in zip(summaries, reports):
        name = report["experiment"]
        if "experiment" not in summary:
            return f"{source}: an experiment name is required when evaluating several summaries"
        if name in (".", "..") or name.startswith(".") or any(c in name for c in "/\\\0") or name != name.strip():
            return f"{source}: experiment name {name!r} cannot be used as a directory name"
        # Canonical caseless match: macOS file systems treat case and normalization variants as one directory.
        key = unicodedata.normalize("NFD", unicodedata.normalize("NFD", name).casefold())
        if key in seen:
            return f"{source}: experiment name {name!r} is also used by {seen[key]}"
        seen[key] = source
    return None


if __name__ == "__main__":
    raise SystemExit(main())
