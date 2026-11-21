"""Convert a GrowthBook experiment-results export into an expgate experiment summary.

Input is the body of ``GET /api/v1/experiments/{id}/results`` (``{"experiment": ..., "result": ...}``),
read from a file; this module never opens a network connection. A small mapping file supplies what the
export does not carry: each imported metric's type, direction and (for guardrails) non-inferiority margin,
and what the export cannot establish about the snapshot (``snapshot``: its allocation weights and that it
was computed without regression adjustment). The results endpoint pairs the latest successful snapshot with
the experiment's *current* settings, so those two facts are operator-asserted, recorded in
``source.asserted``, and rejected when the export's current settings contradict them.

The conversion keeps the SHA-256 of the file's exact bytes in ``source.export_sha256`` of the returned
summary, so the record's own input digest covers it. GrowthBook's own statistics (p-values or chance to
beat control) are never used for the decision: expgate recomputes it from the exported counts, means and
standard deviations. They are only *read*, with the same ship/hold/rollback vocabulary, so that a record can
say where GrowthBook's reading and expgate's policy part ways (``source.reading``).

Unsupported exports raise :class:`GrowthBookImportError` (a ``ValueError``; the CLI exits 2): other
dimensions than "none", experiments that are not plain two-variation A/B tests, regression adjustment or
sequential testing (the exported numbers are then not the raw aggregates), allocation weights that
contradict the assertion, and metrics whose exported shape contradicts the mapped type. Post-stratification
is accepted: it changes only GrowthBook's own effect estimate, never the per-arm aggregates.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

from ..decision import evaluate

FORMAT = "growthbook"

_MAPPING_KEYS = {"primary", "policy", "growthbook", "snapshot", "metrics"}
_SNAPSHOT_KEYS = {"expected_treatment_share", "regression_adjustment"}
_PHASE = re.compile(r"0|[1-9][0-9]*")
_METRIC_KEYS = {"name", "type", "direction", "margin"}
_POLICY_KEYS = {"alpha", "srm_alpha", "power"}
_READING_KEYS = {"alpha", "srm_alpha"}
_GB_ALPHA, _GB_SRM_ALPHA = 0.05, 0.001  # GrowthBook's defaults; the organization's values are not in the export
_RELATIVE = 1e-6  # consistency tolerance between exported fields that GrowthBook derives from each other


class GrowthBookImportError(ValueError):
    """The export or mapping cannot be converted; the message names the offending field."""


def _fail(message: str):
    raise GrowthBookImportError(message)


def _g(value: float) -> str:
    return f"{value:.4g}"


def _object(value, where: str) -> dict:
    if not isinstance(value, dict):
        _fail(f"{where} must be a JSON object")
    return value


def _list(value, where: str) -> list:
    if not isinstance(value, list):
        _fail(f"{where} must be a JSON array")
    return value


def _number(value, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(f"{where} must be a finite number")
    return value


def _count(value, where: str) -> int:
    value = _number(value, where)
    if value != int(value) or value < 0:
        _fail(f"{where} must be a non-negative whole number, got {value!r}")
    return int(value)


def _probability(value, where: str) -> float:
    value = _number(value, where)
    if not 0 <= value <= 1:
        _fail(f"{where} must be a probability in [0, 1], got {value!r}")
    return value


def _string(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{where} must be a non-empty string")
    return value


def _known_keys(value: dict, allowed: set, where: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        _fail(f"{where} has unknown keys {sorted(unknown)}; expected only {sorted(allowed)}")


def _no_duplicates(pairs):
    parsed = {}
    for key, value in pairs:
        if key in parsed:
            _fail(f"duplicate object key {key!r}")
        parsed[key] = value
    return parsed


def _no_constant(name):
    _fail(f"non-finite number {name} is not valid JSON")


def parse_json(data: bytes, what: str):
    """Strict JSON: UTF-8, no duplicate keys, no NaN/Infinity."""
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except UnicodeDecodeError as exc:
        _fail(f"{what} is not UTF-8: {exc}")
    except json.JSONDecodeError as exc:
        _fail(f"{what} is not valid JSON: {exc}")
    except RecursionError:
        _fail(f"{what} is nested too deeply")


def load_mapping(data: bytes) -> dict:
    """Validate the mapping file: per-metric type, direction and margin, plus optional policy settings."""
    mapping = _object(parse_json(data, "mapping file"), "mapping file")
    _known_keys(mapping, _MAPPING_KEYS, "mapping file")
    metrics = _object(mapping.get("metrics"), "mapping 'metrics'")
    if not metrics:
        _fail("mapping 'metrics' must name at least one metric id")
    for metric_id, entry in metrics.items():
        where = f"mapping metric {metric_id!r}"
        _object(entry, where)
        _known_keys(entry, _METRIC_KEYS, where)
        if entry.get("type") not in ("proportion", "mean", "ratio"):
            _fail(f"{where}: type must be 'proportion', 'mean' or 'ratio'")
        if entry.get("direction") not in ("increase", "decrease"):
            _fail(f"{where}: direction must be 'increase' or 'decrease'")
        if "name" in entry:
            _string(entry["name"], f"{where} name")
        if "margin" in entry and _number(entry["margin"], f"{where} margin") < 0:
            _fail(f"{where}: margin must be non-negative")
    if "primary" in mapping:
        _string(mapping["primary"], "mapping 'primary'")
    policy = _object(mapping.get("policy", {}), "mapping 'policy'")
    _known_keys(policy, _POLICY_KEYS, "mapping 'policy'")
    snapshot = _object(mapping.get("snapshot"), "mapping 'snapshot' (what the export cannot establish)")
    _known_keys(snapshot, _SNAPSHOT_KEYS, "mapping 'snapshot'")
    share = snapshot.get("expected_treatment_share")
    if share is None or not 0 < _number(share, "mapping snapshot expected_treatment_share") < 1:
        _fail("mapping snapshot expected_treatment_share is required and must be in (0, 1): the treatment share "
              "of the allocation weights the snapshot was taken under")
    if snapshot.get("regression_adjustment") is not False:
        _fail("mapping snapshot regression_adjustment must be false: assert that the snapshot was computed "
              "without regression adjustment (CUPED); adjusted exports are not supported")
    reading = _object(mapping.get("growthbook", {}), "mapping 'growthbook'")
    _known_keys(reading, _READING_KEYS, "mapping 'growthbook'")
    for key in reading:
        if not 0 < _number(reading[key], f"mapping growthbook {key}") < 1:
            _fail(f"mapping growthbook {key} must be in (0, 1)")
    return mapping


def _metric_refs(settings: dict, key: str) -> list[str]:
    refs = []
    for item in _list(settings.get(key, []), f"settings.{key}"):
        ref = _string(_object(item, f"settings.{key} entry").get("metricId"), f"settings.{key} metricId")
        refs.append(ref)
        overrides = _object(item.get("overrides", {}), f"settings.{key} {ref!r} overrides")
        if overrides.get("regressionAdjustmentEnabled") is True:
            _fail(f"metric {ref!r} uses regression adjustment (CUPED); its exported mean and standard "
                  "deviation are not the raw aggregates expgate needs")
    return refs


def _analysis(variation: dict, engine: str, where: str) -> dict:
    analyses = _list(variation.get("analyses"), f"{where} analyses")
    if not analyses:
        _fail(f"{where} has no analyses")
    for candidate in analyses:
        if _object(candidate, f"{where} analysis").get("engine") == engine:
            return candidate
    return _object(analyses[0], f"{where} analysis")


def _stat(kind: str, users: int, analysis: dict, where: str) -> dict:
    """One arm's expgate statistic from GrowthBook's numerator / denominator / mean / stddev."""
    numerator = _number(analysis.get("numerator"), f"{where} numerator")
    denominator = _number(analysis.get("denominator"), f"{where} denominator")
    mean = _number(analysis.get("mean"), f"{where} mean")
    sd = _number(analysis.get("stddev"), f"{where} stddev")
    if sd < 0:
        _fail(f"{where} stddev must be non-negative")
    if analysis.get("errorMessage"):
        _fail(f"{where}: GrowthBook reported an error for this metric: {analysis['errorMessage']}")
    if kind != "ratio" and denominator != 0:
        _fail(f"{where}: exported denominator is {denominator!r}, which only a ratio metric has; "
              f"it is mapped as '{kind}'")
    if kind == "proportion":
        successes = _count(numerator, f"{where} numerator (successes of a proportion metric)")
        if successes > users:
            _fail(f"{where}: {successes} successes exceed {users} users")
        p = successes / users
        if abs(mean - p) > _RELATIVE * max(p, 1e-12):
            _fail(f"{where}: mean {mean!r} is not successes/users ({p!r}); is it really a proportion metric?")
        if abs(sd - math.sqrt(p * (1 - p))) > _RELATIVE * max(sd, 1e-12):
            _fail(f"{where}: stddev {sd!r} is not that of a proportion; is it really a proportion metric?")
        return {"successes": successes}
    if kind == "mean":
        if abs(mean - numerator / users) > _RELATIVE * max(abs(mean), 1e-12):
            _fail(f"{where}: mean {mean!r} is not numerator/users ({numerator / users!r})")
        return {"mean": mean, "sd": sd}
    if denominator <= 0:
        _fail(f"{where}: a ratio metric needs a positive exported denominator, got {denominator!r}")
    if abs(mean - numerator / denominator) > _RELATIVE * max(abs(mean), 1e-12):
        _fail(f"{where}: mean {mean!r} is not numerator/denominator ({numerator / denominator!r})")
    # The export carries one per-unit delta-method standard deviation, not the per-unit numerator and
    # denominator spreads and their correlation. expgate's delta-method variance
    # (sd_y^2 - 2 R corr sd_y sd_x + R^2 sd_x^2) / (mean_x^2 n) equals GrowthBook's when the linearised
    # numerator carries all of it: sd_y = stddev * mean_x, sd_x = 0, corr = 0.
    denominator_mean = denominator / users
    return {"numerator": {"mean": numerator / users, "sd": sd * denominator_mean},
            "denominator": {"mean": denominator_mean, "sd": 0.0}, "corr": 0.0}


def _significance(analysis: dict, engine: str, direction: float, alpha: float, where: str) -> tuple[str, str]:
    """GrowthBook's own reading of one metric: ('better' | 'worse' | 'not_significant', evidence text)."""
    if engine == "frequentist":
        p = _probability(analysis.get("pValue"), f"{where} pValue")
        change = _number(analysis.get("percentChange"), f"{where} percentChange") * direction
        if p < alpha and change != 0:
            return ("better" if change > 0 else "worse"), f"two-sided p {_g(p)} < {_g(alpha)}"
        return "not_significant", f"two-sided p {_g(p)} >= {_g(alpha)}"
    chance = _probability(analysis.get("chanceToBeatControl"), f"{where} chanceToBeatControl")
    if chance >= 1 - alpha:
        return "better", f"chance to beat control {_g(chance)} >= {_g(1 - alpha)}"
    if chance <= alpha:
        return "worse", f"chance to beat control {_g(chance)} <= {_g(alpha)}"
    return "not_significant", f"chance to beat control {_g(chance)} between {_g(alpha)} and {_g(1 - alpha)}"


def _one_sided_p(improvement: float, se: float) -> float:
    return 0.5 * math.erfc(improvement / se / math.sqrt(2))


def _reading(report: dict, reads: dict, srm_p: float, srm_alpha: float, alpha: float) -> dict:
    """GrowthBook's reading of the export, and where it differs from the expgate report."""
    rows = {row["metric"]: row for row in report["metrics"]}
    basis = [f"{'primary' if rows[name]['role'] == 'primary' else 'guardrail'} {name}: {status.replace('_', ' ')} ({evidence})"
             for name, (status, evidence) in reads.items()]
    basis.append(f"sample ratio: GrowthBook p {_g(srm_p)} {'<' if srm_p < srm_alpha else '>='} {_g(srm_alpha)}")
    worse = any(status == "worse" for status, _ in reads.values())
    primary = next(name for name, row in rows.items() if row["role"] == "primary")
    if srm_p < srm_alpha:
        decision = "INVALID"
    elif reads[primary][0] == "worse" or worse:
        decision = "ROLLBACK"
    elif reads[primary][0] == "better":
        decision = "SHIP"
    else:
        decision = "HOLD"

    differences = []
    if (srm_p < srm_alpha) != (not report["sample_ratio"]["pass"]):
        differences.append(f"sample ratio: GrowthBook's check gives p {_g(srm_p)} (flagged below {_g(srm_alpha)}); "
                           f"expgate computes p {_g(report['sample_ratio']['p_value'])} from the arm sizes and "
                           f"flags below {_g(report['policy']['srm_alpha'])}")
    expected = {"IMPROVED": "better", "DEGRADED": "worse", "INCONCLUSIVE": "not_significant"}
    for name, (status, evidence) in reads.items():
        row = rows[name]
        if row["se"] == 0:
            continue
        if row["role"] == "primary":
            if expected[row["status"]] != status:
                differences.append(
                    f"primary {name}: GrowthBook reads it as {status.replace('_', ' ')} ({evidence}); expgate "
                    f"tests the primary metric one-sided at alpha {_g(report['policy']['alpha'])} on the exported "
                    f"aggregates and finds it {row['status'].lower()} (one-sided p "
                    f"{_g(_one_sided_p(row['improvement'], row['se']))}); GrowthBook's own statistic is not used")
        elif status != "worse" and row["status"] != "NON_INFERIOR":
            lo = row["improvement_bounds"][0]
            if row["status"] == "BREACH":
                differences.append(
                    f"guardrail {name}: GrowthBook reads it as {status.replace('_', ' ')} ({evidence}); expgate's "
                    f"one-sided bound shows degradation (point degradation {_g(-row['improvement'])} exceeds its "
                    f"margin {_g(row['margin'])})")
            else:
                differences.append(
                    f"guardrail {name}: GrowthBook reports no significant degradation ({evidence}), but expgate "
                    f"requires every guardrail to be shown non-inferior and its one-sided upper bound of the "
                    f"degradation, {_g(-lo)}, is not below the margin {_g(row['margin'])}; GrowthBook has no "
                    "non-inferiority margin")
        elif status == "worse" and row["status"] != "BREACH":
            differences.append(
                f"guardrail {name}: GrowthBook flags significant degradation ({evidence}); expgate rolls back only "
                f"if its one-sided bound shows degradation and the point degradation {_g(-row['improvement'])} "
                f"exceeds the margin {_g(row['margin'])}, and finds it {row['status'].lower().replace('_', ' ')}")
    return {"decision": decision, "alpha": alpha, "srm_alpha": srm_alpha, "basis": basis,
            "differences": differences}


def convert(export: bytes, mapping: dict) -> dict:
    """Return the expgate summary for the exact bytes of a GrowthBook results export."""
    document = _object(parse_json(export, "export"), "export")
    if "experiment" not in document or "result" not in document:
        _fail("expected the body of GET /api/v1/experiments/{id}/results, an object with 'experiment' and 'result'")
    experiment, result = _object(document["experiment"], "'experiment'"), _object(document["result"], "'result'")
    if experiment.get("type", "standard") != "standard":
        _fail(f"experiment type {experiment.get('type')!r} is not supported; only standard A/B tests")
    dimension = _object(result.get("dimension"), "result.dimension")
    if dimension.get("type") != "none":
        _fail(f"result is broken down by dimension {dimension.get('type')!r}; export the overall results")

    settings = _object(result.get("settings"), "result.settings")
    # The endpoint pairs the latest successful snapshot with the experiment's CURRENT settings, and the export
    # carries neither the snapshot's adjustment flags nor its allocation weights, so the mapping asserts them
    # and the current values may only contradict the assertion, never establish it (see the README).
    experiment_settings = _object(experiment.get("settings", {}), "experiment.settings")
    for owner, flags in (("result.settings", settings), ("experiment.settings", experiment_settings)):
        for flag in ("regressionAdjustmentEnabled", "sequentialTestingEnabled"):
            if flags.get(flag) is True:
                _fail(f"{owner}.{flag} is true; the exported statistics are then not raw aggregates (or are "
                      "sequential), which expgate cannot recompute. If it was switched on after the snapshot, "
                      "refresh the analysis in GrowthBook and export again")
    for override in _list(experiment_settings.get("metricOverrides", []), "experiment.settings.metricOverrides"):
        if (_object(override, "metric override").get("regressionAdjustmentOverride") is True
                and override.get("regressionAdjustmentEnabled") is True):
            _fail(f"metric {override.get('id')!r} has a regression adjustment override (CUPED); its exported "
                  "standard deviation is not the raw one")
    engine = settings.get("statsEngine")
    if engine not in ("bayesian", "frequentist"):
        _fail("result.settings.statsEngine must be 'bayesian' or 'frequentist'")

    variations = _list(experiment.get("variations"), "experiment.variations")
    if len(variations) != 2:
        _fail(f"{len(variations)} variations: only two-variation experiments are supported")
    control_id, treatment_id = (_string(_object(v, "variation").get("variationId"), "variation id") for v in variations)
    if control_id == treatment_id:
        _fail("both variations have the same id")

    rows = _list(result.get("results"), "result.results")
    if len(rows) != 1:
        _fail(f"result.results has {len(rows)} entries; expected exactly one overall row")
    row = _object(rows[0], "result.results[0]")
    srm_p = _probability(_object(row.get("checks"), "result checks").get("srm"), "result checks.srm")
    exported = {}
    for metric in _list(row.get("metrics"), "result.results[0].metrics"):
        metric_id = _string(_object(metric, "metric").get("metricId"), "metricId")
        if metric_id in exported:
            _fail(f"metric {metric_id!r} appears twice in the export")
        exported[metric_id] = metric

    goals, guardrails = _metric_refs(settings, "goals"), _metric_refs(settings, "guardrails")
    _metric_refs(settings, "secondaryMetrics")  # also rejects regression-adjusted secondaries
    mapped = mapping["metrics"]
    primary = mapping.get("primary")
    if primary is None:
        if len(goals) != 1:
            _fail(f"the export lists {len(goals)} goal metrics but expgate has one primary metric; "
                  "set 'primary' in the mapping to one of them" if goals else
                  "the export lists no goal metric to use as the primary metric")
        primary = goals[0]
    elif primary not in goals:
        _fail(f"mapping 'primary' {primary!r} is not one of the export's goal metrics {goals}")
    if primary in guardrails:
        _fail(f"metric {primary!r} is both primary and a guardrail")
    imported = [primary] + [metric_id for metric_id in guardrails if metric_id != primary]
    stray = sorted(set(mapped) - set(imported))
    if stray:
        _fail(f"mapping describes metrics the import does not use (not the primary or a guardrail): {stray}")

    names, spec_metrics, arms_metrics = {}, {}, {"control": {}, "treatment": {}}
    users = {}
    reads = {}
    reading = mapping.get("growthbook", {})
    reading_alpha = reading.get("alpha", _GB_ALPHA)
    reading_srm_alpha = reading.get("srm_alpha", _GB_SRM_ALPHA)
    for metric_id in imported:
        entry = mapped.get(metric_id)
        if entry is None:
            _fail(f"metric {metric_id!r} needs an entry under 'metrics' in the mapping (type, direction"
                  f"{'' if metric_id == primary else ', margin'})")
        if metric_id not in exported:
            _fail(f"metric {metric_id!r} has no results in the export")
        role = "primary" if metric_id == primary else "guardrail"
        if role == "primary" and "margin" in entry:
            _fail(f"metric {metric_id!r}: the primary metric takes no margin")
        if role == "guardrail" and "margin" not in entry:
            _fail(f"metric {metric_id!r}: a guardrail needs a 'margin' in the mapping")
        name = entry.get("name") or exported[metric_id].get("metricName") or metric_id
        _string(name, f"metric {metric_id!r} name")
        if name in names.values():
            _fail(f"two imported metrics are named {name!r}; set distinct 'name' values in the mapping")
        names[metric_id] = name
        spec = {"type": entry["type"], "role": role, "direction": entry["direction"]}
        if role == "guardrail":
            spec["margin"] = entry["margin"]
        spec_metrics[name] = spec

        variation_entries = _list(exported[metric_id].get("variations"), f"metric {name!r} variations")
        by_variation = {}
        for variation in variation_entries:
            variation_id = _string(_object(variation, "variation").get("variationId"), "variationId")
            if variation_id in by_variation:
                _fail(f"metric {name!r} has more than one result for variation {variation_id!r}")
            by_variation[variation_id] = variation
        if len(variation_entries) != 2 or set(by_variation) != {control_id, treatment_id}:
            _fail(f"metric {name!r} has results for variations {sorted(by_variation)}, "
                  f"expected exactly {sorted([control_id, treatment_id])}")
        analyses = {}
        for arm, variation_id in (("control", control_id), ("treatment", treatment_id)):
            where = f"metric {name!r} {arm}"
            variation = by_variation[variation_id]
            count = _count(variation.get("users"), f"{where} users")
            if count < 1:
                _fail(f"{where} has no users")
            if users.setdefault(arm, count) != count:
                _fail(f"{where}: {count} users differs from {users[arm]} for another metric; "
                      "metrics analysed on different user counts are not supported")
            analyses[arm] = _analysis(variation, engine, where)
            arms_metrics[arm][name] = _stat(entry["type"], count, analyses[arm], where)
        sign = 1.0 if entry["direction"] == "increase" else -1.0
        reads[name] = _significance(analyses["treatment"], engine, sign, reading_alpha,
                                    f"metric {name!r} treatment")

    asserted_share = mapping["snapshot"]["expected_treatment_share"]
    current_share = _traffic_share(experiment, result, control_id, treatment_id)
    if abs(current_share - asserted_share) > 1e-9:
        _fail(f"mapping snapshot expected_treatment_share {asserted_share!r} contradicts the experiment's current "
              f"allocation weights in the export (treatment share {current_share!r}). GrowthBook pairs the latest "
              "snapshot with the current weights, so if they were edited after the snapshot, refresh the analysis "
              "and export again; otherwise correct the mapping")
    policy = dict(mapping.get("policy", {}))
    summary = {
        "experiment": _string(experiment.get("trackingKey") or experiment.get("name") or experiment.get("id"),
                              "experiment trackingKey, name or id"),
        "description": f"Imported from a GrowthBook experiment-results export "
                       f"(experiment {experiment.get('id')}, {engine} statistics).",
        "assignment": {"expected_treatment_share": mapping["snapshot"]["expected_treatment_share"]},
        "metrics": spec_metrics,
        "arms": {arm: {"units": users[arm], "metrics": arms_metrics[arm]} for arm in ("control", "treatment")},
    }
    if policy:
        summary["policy"] = policy
    try:
        report = evaluate(summary)
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        _fail(f"the converted summary is not valid input: {exc}")
    summary["source"] = {
        "asserted": dict(mapping["snapshot"]),
        "format": FORMAT,
        "export_sha256": hashlib.sha256(export).hexdigest(),
        "experiment_id": _string(experiment.get("id") or result.get("experimentId"), "experiment id"),
        "snapshot_id": _string(result.get("id"), "result id"),
        "snapshot_updated": _string(result.get("dateUpdated"), "result dateUpdated"),
        "stats_engine": engine,
        "reading": _reading(report, reads, srm_p, reading_srm_alpha, reading_alpha),
    }
    return summary


def _traffic_share(experiment: dict, result: dict, control_id: str, treatment_id: str) -> float:
    """The treatment share of the experiment's *current* weights for the result's phase."""
    phases = _list(experiment.get("phases"), "experiment.phases")
    text = result.get("phase")
    if not isinstance(text, str) or not _PHASE.fullmatch(text) or int(text) >= len(phases):
        _fail(f"result.phase {text!r} is not the zero-based index (as a string such as \"0\") of one of the "
              f"{len(phases)} entries of experiment.phases")
    phase = _object(phases[int(text)], "experiment phase")
    weights = {}
    for split in _list(phase.get("trafficSplit"), "experiment phase trafficSplit"):
        _object(split, "trafficSplit entry")
        weights[split.get("variationId")] = _number(split.get("weight"), "trafficSplit weight")
    if set(weights) != {control_id, treatment_id} or min(weights.values()) <= 0:
        _fail("experiment phase trafficSplit must give both variations a positive weight")
    return weights[treatment_id] / (weights[control_id] + weights[treatment_id])
