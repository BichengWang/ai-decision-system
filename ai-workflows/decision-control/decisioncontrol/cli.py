"""JSON command line interface for trusted local operators."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import attestation, signing
from ._outputs import staged_output
from .actions import LEGACY_ACTIONS_SCHEMA
from .adapters import cedar, opa
from .evidence import export_record, parse_record, replay
from .evaluation import evaluate_cases, load_cases, parse_envelope, replay_evaluation, write_evaluation
from .models import DecisionError, Recommendation, RecordMismatch, RoutingPolicy, StateError
from .store import TicketStore


def _json_file(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _optional_json_file(path, option):
    """``None`` only when the option was not given; a file holding JSON ``null`` is invalid input."""
    if path is None:
        return None
    value = _json_file(path)
    if value is None:
        raise DecisionError(f"{option} file must not contain null")
    return value


def _text_file(path):
    return Path(path).read_text(encoding="utf-8")


def _verify_options(parser):
    parser.add_argument("--record", required=True)
    parser.add_argument("--require-signature", action="store_true",
                        help="also require a signature over the exact record file")
    parser.add_argument("--key", help="HMAC key file (with --require-signature)")
    parser.add_argument("--signature", help="DSSE envelope (default: RECORD.dsse.json)")
    parser.add_argument("--sigstore-bundle", help="Sigstore bundle verified with an external cosign")
    parser.add_argument("--certificate-identity", help="signer identity expected in the Sigstore certificate")
    parser.add_argument("--certificate-oidc-issuer", help="OIDC issuer expected in the Sigstore certificate")


def _check_verify_options(args):
    given = {"--key": args.key, "--signature": args.signature, "--sigstore-bundle": args.sigstore_bundle,
             "--certificate-identity": args.certificate_identity,
             "--certificate-oidc-issuer": args.certificate_oidc_issuer}
    used = [flag for flag, value in given.items() if value is not None]
    if not args.require_signature:
        if used:
            raise DecisionError(f"{', '.join(used)} need --require-signature")
        return
    if (args.key is None) == (args.sigstore_bundle is None):
        raise DecisionError("--require-signature needs exactly one of --key or --sigstore-bundle")
    if args.key is not None:
        if args.certificate_identity is not None or args.certificate_oidc_issuer is not None:
            raise DecisionError("--certificate-identity and --certificate-oidc-issuer go with --sigstore-bundle")
    elif args.signature is not None:
        raise DecisionError("--signature goes with --key")
    elif args.certificate_identity is None or args.certificate_oidc_issuer is None:
        raise DecisionError("--sigstore-bundle needs --certificate-identity and --certificate-oidc-issuer")


def _verified_document(args, kind, parse):
    """Read the file once, apply any signature requirement to its exact bytes, return the parsed document."""
    _check_verify_options(args)
    data = Path(args.record).read_bytes()
    document = parse(data.decode("utf-8"))
    if args.require_signature:
        attestation.require_signature(Path(args.record), data, document, kind, args)
    return document


def _write_json(out, value):
    """Publish ``value`` to a new file atomically."""
    with staged_output(out, directory=False) as staging:
        with staging.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")


def _parser():
    parser = argparse.ArgumentParser(prog="decision-control")
    parser.add_argument("--db", help="SQLite database path (required for storage commands)")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("ticket-create")
    create.add_argument("--ticket-id", required=True)
    create.add_argument("--department", required=True)
    create.add_argument("--priority", help="initial ticket priority (optional)")
    for name in ("ticket-show", "show", "execute"):
        commands.add_parser(name).add_argument("id")
    submit = commands.add_parser("submit")
    submit.add_argument("--proposal", required=True)
    submit.add_argument("--policy", required=True)
    submit.add_argument("--proposed-by", required=True)
    submit.add_argument("--external-policy", help="frozen OPA or Cedar decision from freeze-opa or freeze-cedar")
    commands.add_parser("pending")
    for name in ("approve", "reject", "cancel"):
        review = commands.add_parser(name)
        review.add_argument("id")
        review.add_argument("--reviewer", required=True)
        review.add_argument("--note", default="", required=name == "cancel")
    export = commands.add_parser("export")
    export.add_argument("id")
    export.add_argument("--out")
    export.add_argument("--sign-key", help="HMAC key file; writes OUT.dsse.json (needs --out)")
    replay_command = commands.add_parser("replay")
    _verify_options(replay_command)
    replay_command.add_argument("--require-reevaluation", action="store_true",
                                help="exit 2 instead of 0 when a frozen OPA or Cedar decision cannot be re-evaluated")
    policy_input = commands.add_parser("policy-input", help="print the OPA input or Cedar request for a proposal")
    policy_input.add_argument("--engine", choices=("opa", "cedar"), required=True)
    policy_input.add_argument("--proposal", required=True)
    policy_input.add_argument("--proposed-by", required=True)
    freeze_opa = commands.add_parser("freeze-opa", help="freeze an OPA decision log entry and its policy files")
    freeze_opa.add_argument("--decision-log", required=True, help="OPA decision log (JSON, array or JSON Lines)")
    freeze_opa.add_argument("--decision-id", help="entry to freeze; required when the log has several")
    freeze_opa.add_argument("--policy-dir", required=True, help="directory of .rego files, optional data.json and .manifest")
    freeze_opa.add_argument("--out")
    freeze_cedar = commands.add_parser("freeze-cedar", help="freeze a Cedar authorization")
    freeze_cedar.add_argument("--policies", required=True)
    freeze_cedar.add_argument("--policy-format", choices=("cedar", "json"), default="cedar")
    freeze_cedar.add_argument("--entities", required=True)
    freeze_cedar.add_argument("--request", required=True, help="request JSON as for cedar authorize --request-json")
    freeze_cedar.add_argument("--response", help="recorded Cedar response (decision, diagnostics); default runs cedar")
    freeze_cedar.add_argument("--out")
    demo = commands.add_parser("demo")
    demo.add_argument("--out", required=True)
    demo.add_argument("--sign-key", help="HMAC key file; signs each exported record")
    keygen = commands.add_parser("keygen", help="write a new random HMAC signing key (mode 0600)")
    keygen.add_argument("out", help="new key file; an existing file is never overwritten")
    predicate = commands.add_parser("predicate", help="write the in-toto predicate for cosign attest-blob")
    predicate.add_argument("--record", required=True)
    predicate.add_argument("--out", required=True)
    evaluation = commands.add_parser("evaluate", help="score supplied labeled recommendations; execute nothing")
    evaluation.add_argument("--cases", required=True, help="labeled JSON Lines cases")
    evaluation.add_argument("--policy", required=True)
    evaluation.add_argument("--require", help="metric/support gates; omitted means UNGATED")
    evaluation.add_argument("--out", required=True, help="new or empty output directory")
    evaluation.add_argument("--sign-key", help="HMAC key file; writes evaluation.json.dsse.json")
    _verify_options(commands.add_parser("replay-evaluation"))
    return parser


def _sign_key(args):
    return signing.load_key(args.sign_key) if args.sign_key else None


def _run(args):
    if args.command == "replay":
        result = replay(_verified_document(args, "record", parse_record))
        external = result.get("external_policy")
        if external and external["verification"] == "digest-only":
            if args.require_reevaluation:
                raise DecisionError(f"--require-reevaluation: the frozen {external['engine']} policy "
                                    f"could not be re-evaluated ({external['reason']})")
            print(f"decision-control: policy NOT re-evaluated ({external['reason']}); digest-only verification "
                  f"of the frozen {external['engine']} decision", file=sys.stderr)
        return result
    if args.command == "freeze-opa":
        modules, data, revision = opa.load_policy_dir(args.policy_dir)
        entry = opa.select_entry(opa.entries_from_log(_text_file(args.decision_log)), args.decision_id)
        frozen = opa.freeze(entry, modules, data, bundle_revision=revision)
        if args.out:
            _write_json(args.out, frozen)
        return frozen
    if args.command == "freeze-cedar":
        text = _text_file(args.policies)
        policies = ({"format": "cedar", "text": text} if args.policy_format == "cedar"
                    else {"format": "json", "json": json.loads(text)})
        frozen = cedar.freeze(policies, _json_file(args.entities), _json_file(args.request),
                              _optional_json_file(args.response, "--response"))
        if args.out:
            _write_json(args.out, frozen)
        return frozen
    if args.command == "keygen":
        return {"key_file": args.out, "key_id": signing.generate_key(Path(args.out))}
    if args.command == "predicate":
        kind, version = attestation.describe(parse_record(_text_file(args.record)))
        with staged_output(args.out, directory=False) as staging:
            with staging.open("x", encoding="utf-8") as stream:
                json.dump(attestation.predicate(kind, version), stream, indent=2)
                stream.write("\n")
        return {"predicate_type": attestation.predicate_type(kind, version), "predicate_file": args.out}
    if args.command == "demo":
        from .demo import run_demo
        return run_demo(args.out, _sign_key(args))
    if args.command == "evaluate":
        key = _sign_key(args)
        requirements = _optional_json_file(args.require, "--require")
        report = evaluate_cases(load_cases(args.cases),
                                RoutingPolicy.from_dict(_json_file(args.policy), LEGACY_ACTIONS_SCHEMA), requirements)
        return write_evaluation(report, args.out, key)
    if args.command == "replay-evaluation":
        return replay_evaluation(_verified_document(args, "evaluation", parse_envelope))
    if not args.db:
        raise DecisionError("--db is required for storage commands")
    # Validate the signing key before TicketStore creates or initializes the database.
    key = _sign_key(args) if args.command == "export" else None
    if key is not None and not args.out:
        raise DecisionError("--sign-key needs --out: the signature covers the exported file bytes")
    with TicketStore(args.db) as store:
        if args.command == "ticket-create":
            return store.create_ticket(args.ticket_id, args.department, args.priority).to_dict()
        if args.command == "ticket-show":
            return store.get_ticket(args.id).to_dict()
        if args.command == "submit":
            return store.submit(Recommendation.from_dict(_json_file(args.proposal)),
                                RoutingPolicy.from_dict(_json_file(args.policy)), args.proposed_by,
                                _optional_json_file(args.external_policy, "--external-policy"))
        if args.command == "policy-input":
            proposal = Recommendation.from_dict(_json_file(args.proposal))
            ticket = store.get_ticket(proposal.ticket_id)
            build = opa.decision_input if args.engine == "opa" else cedar.authorization_request
            return build(proposal, ticket, args.proposed_by)
        if args.command == "pending":
            return store.pending()
        if args.command == "show":
            return store.get(args.id)
        if args.command in ("approve", "reject", "cancel"):
            return getattr(store, args.command)(args.id, args.reviewer, args.note)
        if args.command == "execute":
            return store.execute(args.id)
        if args.command == "export":
            envelope = export_record(store.get(args.id))
            if args.out:
                _write_export(args.out, envelope, key)
            return envelope
    raise DecisionError("unknown command")


def _write_export(out, envelope, key):
    """Publish the record file and, when signing, its envelope; neither is left without the other."""
    signature = attestation.envelope_path(Path(out))
    if key is not None and (signature.exists() or signature.is_symlink()):
        raise DecisionError("output must be a new file or a new or empty directory")
    with staged_output(out, directory=False) as staging:
        with staging.open("x", encoding="utf-8") as stream:
            json.dump(envelope, stream, indent=2, allow_nan=False)
            stream.write("\n")
    if key is None:
        return
    try:
        signed = attestation.sign_bytes(Path(out).read_bytes(), Path(out).name, envelope, key, "record")
        with staged_output(signature, directory=False) as staging:
            staging.write_text(attestation.render_envelope(signed), encoding="utf-8")
    except BaseException:
        Path(out).unlink(missing_ok=True)
        raise


def main(argv=None):
    """Return 0, invalid input/IO 2, or blocked lifecycle/evaluation gate 1."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        result = _run(args)
    except RecordMismatch as error:
        print(f"decision-control: {error}", file=sys.stderr)
        return 1 if args.command in ("replay", "replay-evaluation") else 2
    except signing.SignatureError as error:
        print(f"decision-control: signature: {error}", file=sys.stderr)
        return 1
    except StateError as error:
        print(f"decision-control: {error}", file=sys.stderr)
        return 1
    # ValueError and RecursionError: JSON beyond the parser's limits (integer digits, nesting depth).
    except (DecisionError, signing.KeyFileError, OSError, UnicodeError, json.JSONDecodeError, sqlite3.Error,
            ValueError, RecursionError) as error:
        print(f"decision-control: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    if args.command == "pending" and result.skipped:
        for row in result.skipped:
            print(f"decision-control: skipped corrupt decision {row['id']}: {row['error']}", file=sys.stderr)
        return 1
    if args.command == "execute" and result["status"] == "STALE":
        return 1
    return 1 if args.command == "evaluate" and result["report"]["disposition"] == "FAIL" else 0
