"""Sign decision records and require those signatures when verifying.

The signed subject is the SHA-256 of the exact bytes of ``decision.json``, so an edit that re-hashes
``input_sha256`` and rewrites the derived fields still fails ``--require-signature``. HMAC proves
possession of a shared secret, not an identity; Sigstore verification is delegated to an external
``cosign``. The caller reads the record file once and passes those bytes here, so the signature, the
parse and the replay all see the same content.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import signing
from .records import SUPPORTED_SCHEMAS

PREDICATE_BASE = "https://github.com/BichengWang/ai-decision-system/predicate/expgate/decision/"
SCHEMA_BASE = "https://github.com/BichengWang/ai-decision-system/schema/expgate/decision."
ENVELOPE_SUFFIX = ".dsse.json"
BUNDLE_SUFFIX = ".sigstore.json"
RECORD_NAME = "decision.json"


def predicate_type(version: int) -> str:
    return f"{PREDICATE_BASE}v{version}"


def predicate(version: int) -> dict:
    return {"schema": f"{SCHEMA_BASE}v{version}.json"}


def describe(document) -> int:
    """Return the schema version of a decision record; anything unsupported is an input error (exit 2)."""
    version = document.get("schema_version") if isinstance(document, dict) else None
    if type(version) is not int or version not in SUPPORTED_SCHEMAS:
        raise ValueError("only schema 2 and schema 3 decision records can be signed or verified against a signature")
    return version


def envelope_path(record: Path) -> Path:
    return Path(str(record) + ENVELOPE_SUFFIX)


def sign_bytes(data: bytes, name: str, document, key: bytes) -> dict:
    """Return the DSSE envelope for the exact bytes of a decision file."""
    version = describe(document)
    return signing.sign(data, name, predicate_type(version), predicate(version), key)


def render_envelope(envelope: dict) -> str:
    return json.dumps(envelope, indent=2) + "\n"


def require_signature(record: Path, data: bytes, document, options, key: bytes | None) -> None:
    """Raise SignatureError (exit 1) or KeyFileError (exit 2) unless ``data`` is signed as required.

    ``data`` is the one read of the record file. ``options`` carries signature, sigstore_bundle,
    certificate_identity and certificate_oidc_issuer; ``key`` is the loaded HMAC key, or None for Sigstore.
    """
    expected = predicate_type(describe(document))
    if key is not None:
        path = Path(options.signature) if options.signature else envelope_path(record)
        try:
            text = path.read_bytes().decode("utf-8")
        except FileNotFoundError as error:
            raise signing.SignatureError(f"unsigned: no signature envelope at {path}") from error
        except (OSError, UnicodeError) as error:
            raise signing.SignatureError(f"cannot read signature envelope {path}: {error}") from error
        try:
            envelope = json.loads(text)
        except (ValueError, RecursionError) as error:
            raise signing.SignatureError(f"malformed DSSE envelope: {error}") from error
        signing.verify(data, envelope, {expected}, key)
        return
    bundle = Path(options.sigstore_bundle)
    if not bundle.is_file():
        raise signing.SignatureError(f"unsigned: no Sigstore bundle at {bundle}")
    # cosign reads a file, so give it a private copy of the bytes already read, never the original path.
    with tempfile.TemporaryDirectory(prefix="expgate-sigstore-") as directory:
        snapshot = Path(directory, RECORD_NAME)
        descriptor = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        signing.verify_sigstore(snapshot, bundle, expected, options.certificate_identity,
                                options.certificate_oidc_issuer)


def check_verify_options(args) -> str | None:
    """Return a usage problem for the signature flags of ``experiment-gate-verify``, or None."""
    given = {"--key": args.key, "--signature": args.signature, "--sigstore-bundle": args.sigstore_bundle,
             "--certificate-identity": args.certificate_identity,
             "--certificate-oidc-issuer": args.certificate_oidc_issuer}
    used = [flag for flag, value in given.items() if value is not None]
    if not args.require_signature:
        return f"{', '.join(used)} need --require-signature" if used else None
    if (args.key is None) == (args.sigstore_bundle is None):
        return "--require-signature needs exactly one of --key or --sigstore-bundle"
    if args.key is not None:
        if args.certificate_identity is not None or args.certificate_oidc_issuer is not None:
            return "--certificate-identity and --certificate-oidc-issuer go with --sigstore-bundle"
        if args.signature is not None and len(args.records) != 1:
            return "--signature names one envelope, so it needs exactly one record"
    else:
        if args.signature is not None:
            return "--signature goes with --key"
        if args.certificate_identity is None or args.certificate_oidc_issuer is None:
            return "--sigstore-bundle needs --certificate-identity and --certificate-oidc-issuer"
        if len(args.records) != 1:
            return "--sigstore-bundle names one bundle, so it needs exactly one record"
    return None


def command(argv: list[str]) -> int:
    """``keygen`` and ``predicate``, the helpers of ``experiment-gate`` that do not evaluate anything."""
    import argparse
    import sys

    from .verify import load_record

    parser = argparse.ArgumentParser(prog="experiment-gate")
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="write a new random HMAC signing key (mode 0600)")
    keygen.add_argument("out", type=Path, help="new key file; an existing file is never overwritten")
    pred = commands.add_parser("predicate", help="write the in-toto predicate for cosign attest-blob")
    pred.add_argument("--record", type=Path, required=True)
    pred.add_argument("--out", type=Path, required=True, help="new predicate file")
    args = parser.parse_args(argv)
    try:
        if args.command == "keygen":
            result = {"key_file": str(args.out), "key_id": signing.generate_key(args.out)}
        else:
            version = describe(load_record(args.record.read_bytes().decode("utf-8")))
            with open(args.out, "x", encoding="utf-8") as stream:
                json.dump(predicate(version), stream, indent=2)
                stream.write("\n")
            result = {"predicate_type": predicate_type(version), "predicate_file": str(args.out)}
    except (OSError, ValueError, RecursionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0
