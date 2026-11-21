"""Sign exported records and evaluation reports, and require those signatures when replaying.

The signed subject is the SHA-256 of the exact bytes of the record file, so an edit that
re-hashes the embedded checksum still fails ``--require-signature``. HMAC proves possession of
a shared secret, not an identity; Sigstore verification is delegated to an external ``cosign``.
"""
import json
import os
from pathlib import Path
import tempfile

from . import signing
from .evaluation import REPORT_SCHEMAS
from .evidence import SCHEMAS
from .models import DecisionError

PREDICATE_BASE = "https://github.com/BichengWang/ai-decision-system/predicate/decisioncontrol/"
SCHEMA_BASE = "https://github.com/BichengWang/ai-decision-system/schema/decisioncontrol/"
SUPPORTED = {"record": SCHEMAS, "evaluation": REPORT_SCHEMAS}
BODY = {"record": "record", "evaluation": "report"}
ENVELOPE_SUFFIX = ".dsse.json"
BUNDLE_SUFFIX = ".sigstore.json"


def predicate_type(kind: str, version: int) -> str:
    return f"{PREDICATE_BASE}{kind}/v{version}"


def predicate(kind: str, version: int) -> dict:
    return {"schema": f"{SCHEMA_BASE}{kind}.v{version}.json"}


def describe(document, kind=None):
    """Return ``(kind, schema_version)`` of an exported envelope; unsupported input is exit 2."""
    if not isinstance(document, dict):
        raise DecisionError("expected a JSON object")
    found = [name for name, member in BODY.items() if member in document]
    if kind is None:
        if len(found) != 1:
            raise DecisionError("expected an exported record or evaluation envelope")
        kind = found[0]
    body = document.get(BODY[kind])
    version = body.get("schema_version") if isinstance(body, dict) else None
    if type(version) is not int or version not in SUPPORTED[kind]:
        raise DecisionError(f"unsupported {kind} schema_version")
    return kind, version


def envelope_path(record: Path) -> Path:
    return Path(str(record) + ENVELOPE_SUFFIX)


def sign_bytes(data: bytes, name: str, document, key: bytes, kind=None) -> dict:
    """Return the DSSE envelope for the exact bytes of an exported file."""
    kind, version = describe(document, kind)
    return signing.sign(data, name, predicate_type(kind, version), predicate(kind, version), key)


def render_envelope(envelope: dict) -> str:
    return json.dumps(envelope, indent=2) + "\n"


def require_signature(record: Path, data: bytes, document, kind: str, options) -> None:
    """Raise SignatureError (exit 1) or KeyFileError (exit 2) unless the file is signed as required.

    ``data`` is the one snapshot of the file's bytes; the caller parses and replays only those
    bytes. ``options`` carries key, signature, sigstore_bundle, certificate_identity and
    certificate_oidc_issuer; exactly one of key or sigstore_bundle is set.
    """
    _, version = describe(document, kind)
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
        except (ValueError, RecursionError) as error:
            raise signing.SignatureError(f"malformed DSSE envelope: {error}") from error
        signing.verify(data, envelope, {expected}, key)
        return
    bundle = Path(options.sigstore_bundle)
    if not bundle.is_file():
        raise signing.SignatureError(f"unsigned: no Sigstore bundle at {bundle}")
    # cosign verifies a private copy of the very bytes the caller parsed, not the path, which
    # could be swapped between the caller's read and cosign's.
    with tempfile.TemporaryDirectory(prefix="decisioncontrol-") as directory:
        snapshot = Path(directory) / record.name
        with open(snapshot, "xb", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            stream.write(data)
        signing.verify_sigstore(snapshot, bundle, expected, options.certificate_identity,
                                options.certificate_oidc_issuer)
