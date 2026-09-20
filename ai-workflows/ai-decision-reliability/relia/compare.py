"""Compare result artifacts using a protocol fixed before reproduction."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


EXACT_FIELDS = {
    "prohibited_access", "constraint_violations", "critical_review_fixture_n",
    "critical_review_routing", "critical_review_noncritical_misroutes", "routing_rate",
    "worst_slice_eligible_count",
}
EXACT_GATES = {
    "prohibited_field_access", "constraint_violations", "critical_review_routing_rate",
}


def leaves(value, path="", exact=False):
    """Yield JSON-pointer leaves, with counter/routing floats marked exact."""
    if isinstance(value, dict):
        yield path, ({}, exact)
        for key, child in value.items():
            pointer = key.replace("~", "~0").replace("/", "~1")
            fixed = key in EXACT_FIELDS or (key == "value" and value.get("gate") in EXACT_GATES)
            yield from leaves(child, f"{path}/{pointer}", exact or fixed)
    elif isinstance(value, list):
        yield path, ([], exact)
        for index, child in enumerate(value):
            yield from leaves(child, f"{path}/{index}", exact)
    else:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"nonfinite value at {path}")
        yield path, (value, exact)


def protocol_template(reference_bytes):
    values = dict(leaves(json.loads(reference_bytes)))
    return {
        "schema_version": 1,
        "reference_sha256": hashlib.sha256(reference_bytes).hexdigest(),
        "target_platform": "",
        "rationale": "",
        "tolerances": {
            path: {"abs": 0 if exact else None, "rel": 0 if exact else None}
            for path, (value, exact) in values.items() if type(value) is float
        },
    }


def compare(reference_bytes, actual_bytes, protocol):
    if type(protocol.get("schema_version")) is not int or protocol["schema_version"] != 1:
        raise ValueError("protocol schema_version must be 1")
    if protocol.get("reference_sha256") != hashlib.sha256(reference_bytes).hexdigest():
        raise ValueError("protocol reference_sha256 does not match the reference file")
    for key in ("target_platform", "rationale"):
        if not isinstance(protocol.get(key), str) or not protocol[key].strip():
            raise ValueError(f"protocol requires {key}")
    reference = dict(leaves(json.loads(reference_bytes)))
    actual = dict(leaves(json.loads(actual_bytes)))
    floats = {path for path, (value, _) in reference.items() if type(value) is float}
    tolerances = protocol.get("tolerances")
    if not isinstance(tolerances, dict) or set(tolerances) != floats:
        raise ValueError("tolerances must name every reference float field, and no other fields")
    for path, tolerance in tolerances.items():
        if not isinstance(tolerance, dict) or set(tolerance) != {"abs", "rel"}:
            raise ValueError(f"invalid tolerance at {path}: require abs and rel")
        for number in tolerance.values():
            if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                raise ValueError(f"tolerance at {path} must be finite and nonnegative")
        if reference[path][1] and any(tolerance.values()):
            raise ValueError(f"counter/routing field requires zero tolerance: {path}")

    differences = []
    metrics = []
    for path in sorted(reference.keys() | actual.keys()):
        if path not in reference or path not in actual:
            differences.append({"field": path, "reason": "missing or unexpected field"})
            continue
        expected, _ = reference[path]
        observed, _ = actual[path]
        if type(expected) is not type(observed):
            differences.append({"field": path, "reason": "type changed"})
        elif type(expected) is float:
            tolerance = tolerances[path]
            allowed = tolerance["abs"] + tolerance["rel"] * abs(expected)
            if not math.isfinite(allowed):
                raise ValueError(f"combined tolerance is nonfinite: {path}")
            delta = abs(observed - expected)
            passed = delta <= allowed
            metrics.append({"field": path, "reference": expected, "actual": observed,
                            "difference": delta, "allowed": allowed, "pass": passed})
            if not passed:
                differences.append({"field": path, "reason": "metric outside tolerance"})
        elif observed != expected:
            differences.append({"field": path, "reason": "exact field changed"})
    return {"pass": not differences, "differences": differences, "metrics": metrics,
            "reference_sha256": hashlib.sha256(reference_bytes).hexdigest(),
            "actual_sha256": hashlib.sha256(actual_bytes).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("actual", nargs="?", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--protocol", type=Path)
    mode.add_argument("--write-protocol-template", type=Path)
    args = parser.parse_args(argv)
    try:
        reference = args.reference.read_bytes()
        if args.write_protocol_template:
            if args.actual:
                parser.error("template generation does not accept an actual run")
            with args.write_protocol_template.open("x") as output:
                json.dump(protocol_template(reference), output, indent=2, allow_nan=False)
                output.write("\n")
            return 0
        if not args.actual:
            parser.error("comparison requires an actual result file")
        protocol_bytes = args.protocol.read_bytes()
        report = compare(reference, args.actual.read_bytes(), json.loads(protocol_bytes))
        report["protocol_sha256"] = hashlib.sha256(protocol_bytes).hexdigest()
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if report["pass"] else 1
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
