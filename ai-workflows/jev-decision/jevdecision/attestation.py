"""Sign answer records and evaluation provenance, and require those signatures when verifying.

The signed subject is the SHA-256 of the exact bytes of the signed file, so an edit that re-hashes
the embedded digest still fails `--require-signature`. An answer record is signed as a whole; for an
evaluation directory the signed file is `provenance.json`, which already pins every other file by
hash. HMAC proves possession of a shared secret, not an identity; Sigstore verification is
delegated to an external `cosign`.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import signing

PREDICATE_BASE = "https://github.com/BichengWang/ai-decision-system/predicate/jevdecision/"
SCHEMA_BASE = "https://github.com/BichengWang/ai-decision-system/schema/jevdecision/"
SUPPORTED = {"answer": (1, 2), "provenance": (2, 3)}
ENVELOPE_SUFFIX = ".dsse.json"
BUNDLE_SUFFIX = ".sigstore.json"
PROVENANCE = "provenance.json"


def predicate_type(kind: str, version: int) -> str:
    return f"{PREDICATE_BASE}{kind}/v{version}"


def predicate(kind: str, version: int) -> dict[str, str]:
    return {"schema": f"{SCHEMA_BASE}{kind}.v{version}.json"}


def answer_version(record: Any) -> int:
    """Schema version of an answer record; anything unsupported is an input error (ValueError)."""
    return _version(record, "answer", "answer record")


def provenance_version(record: Any) -> int:
    """Schema version of an evaluation directory's provenance.json; unsupported is a ValueError."""
    return _version(record, "provenance")


def _version(record: Any, kind: str, label: str = "provenance") -> int:
    version = record.get("schema_version") if isinstance(record, dict) else None
    if type(version) is not int or version not in SUPPORTED[kind]:
        raise ValueError(f"unsupported {label} schema_version; expected "
                         + " or ".join(str(supported) for supported in SUPPORTED[kind]))
    return version


def envelope_path(record: Path) -> Path:
    return Path(str(record) + ENVELOPE_SUFFIX)


def sign_bytes(data: bytes, name: str, kind: str, version: int, key: bytes) -> dict:
    """The DSSE envelope for the exact bytes of a record file."""
    return signing.sign(data, name, predicate_type(kind, version), predicate(kind, version), key)


def render_envelope(envelope: dict) -> str:
    return json.dumps(envelope, indent=2) + "\n"


def require_signature(record: Path, data: bytes, kind: str, version: int, options: Any) -> None:
    """Raise SignatureError (exit 1) or KeyFileError (exit 2) unless the file is signed as required.

    `data` is the file's bytes, read once by the caller; nothing here reads `record` again.
    `options` carries key, signature, sigstore_bundle, certificate_identity and
    certificate_oidc_issuer; exactly one of key or sigstore_bundle is set.
    """
    expected = predicate_type(kind, version)
    if options.key is not None:
        key = signing.load_key(options.key)
        path = Path(options.signature) if options.signature else envelope_path(record)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise signing.SignatureError(f"unsigned: no signature envelope at {path}") from error
        except (OSError, UnicodeError) as error:
            raise signing.SignatureError(f"cannot read signature envelope {path}: {error}") from error
        try:
            envelope = json.loads(text)
        except ValueError as error:
            raise signing.SignatureError(f"malformed DSSE envelope: {error}") from error
        signing.verify(data, envelope, {expected}, key)
        return
    # cosign reads files itself, so it gets private copies of the bytes already read here: it then verifies
    # exactly the bytes that are parsed and re-checked afterwards, whatever happens to the original path.
    bundle = Path(options.sigstore_bundle)
    try:
        bundle_data = bundle.read_bytes()
    except FileNotFoundError as error:
        raise signing.SignatureError(f"unsigned: no Sigstore bundle at {bundle}") from error
    except OSError as error:
        raise signing.SignatureError(f"cannot read Sigstore bundle {bundle}: {error}") from error
    with tempfile.TemporaryDirectory(prefix="jev-sigstore-") as tmp:
        # Separate subdirectories: the record's own name cannot collide with the bundle copy.
        snapshot = Path(tmp) / "record" / record.name
        bundle_snapshot = Path(tmp) / "bundle" / "bundle.sigstore.json"
        for path, content in ((snapshot, data), (bundle_snapshot, bundle_data)):
            path.parent.mkdir(mode=0o700)
            with open(path, "xb", opener=lambda p, f: os.open(p, f, 0o600)) as stream:
                stream.write(content)
        signing.verify_sigstore(snapshot, bundle_snapshot, expected, options.certificate_identity,
                                options.certificate_oidc_issuer)
