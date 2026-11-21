"""Re-evaluate schema-2 and schema-3 decision records offline with the running version.

Schema 2 keeps its ``python-json-v1`` digest, the 0.1.0 tail formulas and the lenient parsing of the
original release. Schema 3 uses an RFC 8785 digest and rejects duplicate object keys, non-finite numbers,
unsafe integers and lone surrogates anywhere in the document. Both compare computed statistics with the
same relative tolerance and everything else exactly (see :func:`_agree`).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from . import attestation, signing
from .decision import evaluate
from .jcs import canonicalize
from .records import REPLAY_RELATIVE_TOLERANCE, REPLAY_ZERO_FLOOR, SUPPORTED_SCHEMAS, input_digest


def _reject_duplicate_keys(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"duplicate object key {key!r}")
        record[key] = value
    return record


def _reject_constant(name):
    raise ValueError(f"non-finite number {name} is not valid JSON")


def load_record(text: str):
    """Parse a decision record. Schema 3 is parsed strictly; other documents keep Python's defaults."""
    record = json.loads(text)
    if isinstance(record, dict) and type(record.get("schema_version")) is int and record["schema_version"] == 3:
        record = json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    return record


# Replayed values that are computed with libm functions or long arithmetic chains and may differ in the last
# digits between platforms. Paths use dict keys and "[]" for any list index. Everything else a record replays
# (copied input and policy values, counts, units, expected shares, margins, strings, booleans,
# dispositions, structure) compares exactly.
_DERIVED = frozenset({
    ("sample_ratio", "p_value"),
    ("metrics", "[]", "diff"),
    ("metrics", "[]", "se"),
    ("metrics", "[]", "improvement"),
    ("metrics", "[]", "improvement_bounds", "[]"),
    ("metrics", "[]", "z"),
    ("metrics", "[]", "mde"),
    ("metrics", "[]", "adjustment", "theta"),
    ("metrics", "[]", "adjustment", "raw_diff"),
    ("metrics", "[]", "adjustment", "raw_se"),
    ("metrics", "[]", "adjustment", "variance_reduction"),
})


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _close(recorded, replayed) -> bool:
    """Computed statistic: identical when either is non-finite, else within the replay tolerance."""
    if not (math.isfinite(recorded) and math.isfinite(replayed)):
        if math.isnan(recorded) or math.isnan(replayed):
            return math.isnan(recorded) and math.isnan(replayed)
        return recorded == replayed  # same infinity; a finite/non-finite pair is unequal
    if replayed == 0:
        return abs(recorded) <= REPLAY_ZERO_FLOOR
    return abs(recorded - replayed) <= REPLAY_RELATIVE_TOLERANCE * abs(replayed)


def _agree(recorded, replayed, path: tuple = ()) -> bool:
    """Replay comparison, shared by schemas 2 and 3.

    Only the computed statistics listed in ``_DERIVED`` agree within a relative 1e-9 (an absolute 1e-12
    where the replayed value is exactly 0), because ``log``, ``exp``, ``erf`` and the normal quantile come
    from the platform libm and differ in the last digits between machines; non-finite values must be
    identical. Everything else compares exactly: numbers by value whatever their int/float spelling,
    booleans, strings and structure. Digests are never compared here.
    """
    if isinstance(recorded, bool) or isinstance(replayed, bool):
        return recorded is replayed
    if _number(recorded) and _number(replayed):
        return _close(recorded, replayed) if path in _DERIVED else recorded == replayed
    if isinstance(recorded, dict) and isinstance(replayed, dict):
        return recorded.keys() == replayed.keys() and all(
            _agree(recorded[k], replayed[k], path + (k,)) for k in replayed)
    if isinstance(recorded, list) and isinstance(replayed, list):
        return len(recorded) == len(replayed) and all(
            _agree(a, b, path + ("[]",)) for a, b in zip(recorded, replayed))
    return type(recorded) is type(replayed) and recorded == replayed


def _same(recorded, replayed, field: str) -> bool:
    return _agree(recorded, replayed, (field,))


def verify_record(record: dict) -> list[str]:
    """Return mismatched fields; raise ValueError for invalid or legacy records."""
    if not isinstance(record, dict):
        raise ValueError("decision record must be a JSON object")
    schema = record.get("schema_version", 1)
    if schema == 1:
        raise ValueError("schema 1 cannot be verified: no embedded input")
    if type(schema) is not int or schema not in SUPPORTED_SCHEMAS:
        raise ValueError("unsupported schema_version; expected 2 or 3")
    if schema == 3:
        canonicalize(record)  # ValueError (exit 2): unsafe integers, infinities, lone surrogates anywhere
    producer = record.get("produced_by")
    if (not isinstance(producer, dict) or producer.get("name") != "expgate"
            or not isinstance(producer.get("version"), str)):
        raise ValueError("invalid produced_by")
    if not isinstance(record.get("input"), dict) or not isinstance(record.get("input_sha256"), str):
        raise ValueError("record needs input and input_sha256")
    for field in ("decision", "reasons", "metrics", "experiment", "policy", "sample_ratio"):
        if field not in record:
            raise ValueError(f"record missing {field}")
    mismatches = []
    if record["input_sha256"] != input_digest(record["input"], schema):
        mismatches.append("input_sha256")
    try:
        replay = evaluate(record["input"], schema_version=schema)
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        if mismatches:
            return mismatches + ["input (cannot replay)"]
        raise ValueError(f"invalid embedded input: {exc}") from exc
    for field in ("decision", "reasons", "metrics", "experiment", "policy", "sample_ratio", "sequential"):
        if not _same(record.get(field), replay.get(field), field):
            mismatches.append(field)
    return mismatches


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, nargs="+", metavar="DECISION_JSON")
    parser.add_argument("--require-signature", action="store_true",
                        help="also require a signature over the exact record file")
    parser.add_argument("--key", type=Path, help="HMAC key file (with --require-signature)")
    parser.add_argument("--signature", type=Path, help="DSSE envelope (default: DECISION_JSON.dsse.json)")
    parser.add_argument("--sigstore-bundle", type=Path, help="Sigstore bundle verified with an external cosign")
    parser.add_argument("--certificate-identity", help="signer identity expected in the Sigstore certificate")
    parser.add_argument("--certificate-oidc-issuer", help="OIDC issuer expected in the Sigstore certificate")
    args = parser.parse_args(argv)
    problem = attestation.check_verify_options(args)
    if problem:
        parser.error(problem)
    try:
        key = signing.load_key(args.key) if args.key is not None else None  # a bad key exits 2 before any output
    except signing.KeyFileError as exc:
        print(f"cannot verify: {exc}", file=sys.stderr)
        return 2
    result = 0
    for path in args.records:
        try:
            data = path.read_bytes()  # the only read: signature, parse and replay all use these bytes
            document = load_record(data.decode("utf-8"))
            if args.require_signature:
                attestation.require_signature(path, data, document, args, key)
            mismatches = verify_record(document)
        except signing.SignatureError as exc:
            print(f"{path}: signature: {exc}", file=sys.stderr)
            result = max(result, 1)
            continue
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            print(f"{path}: cannot verify: {exc}", file=sys.stderr)
            result = 2
            continue
        if mismatches:
            print(f"{path}: mismatch: {', '.join(mismatches)}")
            result = max(result, 1)
        else:
            print(f"{path}: verified")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
