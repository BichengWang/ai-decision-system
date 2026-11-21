"""Signed decision records: HMAC DSSE envelopes over exact file bytes and --require-signature."""
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expgate import attestation, signing
from expgate.decision import evaluate
from expgate.run import main as run_main, record_bytes
from expgate.verify import main as verify_main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SIGSTORE = ("--sigstore-bundle", "--certificate-identity", "--certificate-oidc-issuer")


def call(main, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(map(str, args)))
        except SystemExit as exit_:  # argparse usage errors
            code = exit_.code
    return code, out.getvalue(), err.getvalue()


class SigningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key, self.other = self.root / "signing.key", self.root / "other.key"
        self.assertEqual(call(run_main, "keygen", self.key)[0], 0)
        self.assertEqual(call(run_main, "keygen", self.other)[0], 0)
        out = self.root / "signed"
        self.assertEqual(call(run_main, "--scenario", "win", "--out", out, "--sign-key", self.key)[0], 0)
        self.record = out / "decision.json"
        self.envelope = Path(str(self.record) + ".dsse.json")

    def verify(self, record=None, *extra, key=None):
        return call(verify_main, record or self.record, "--require-signature", "--key", key or self.key, *extra)

    def forged_copy(self, name="forged"):
        """A record whose input was edited and fully re-derived: it passes the digest check on its own."""
        record = json.loads(self.record.read_text(encoding="utf-8"))
        edited = copy.deepcopy(record["input"])
        edited["arms"]["treatment"]["metrics"]["conversion"]["successes"] -= 300
        path = self.root / name / "decision.json"
        path.parent.mkdir()
        path.write_bytes(record_bytes(evaluate(edited)))
        Path(str(path) + ".dsse.json").write_bytes(self.envelope.read_bytes())
        return path

    def test_signed_record_verifies_and_envelope_is_in_toto_dsse(self):
        code, out, err = self.verify()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("verified", out)
        envelope = json.loads(self.envelope.read_text(encoding="utf-8"))
        self.assertEqual(envelope["payloadType"], "application/vnd.in-toto+json")
        statement = json.loads(base64.b64decode(envelope["payload"]))
        self.assertEqual(statement["_type"], "https://in-toto.io/Statement/v1")
        self.assertEqual(statement["subject"],
                         [{"name": "decision.json", "digest": {"sha256": hashlib.sha256(self.record.read_bytes()).hexdigest()}}])
        self.assertEqual(statement["predicateType"],
                         "https://github.com/BichengWang/ai-decision-system/predicate/expgate/decision/v3")
        self.assertEqual(statement["predicate"],
                         {"schema": "https://github.com/BichengWang/ai-decision-system/schema/expgate/decision.v3.json"})
        self.assertEqual(envelope["signatures"][0]["keyid"], signing.key_id(signing.load_key(self.key)))

    def test_every_scenario_gets_its_own_envelope(self):
        out = self.root / "all"
        self.assertEqual(call(run_main, "--all-scenarios", "--out", out, "--sign-key", self.key)[0], 0)
        records = sorted(out.glob("*/decision.json"))
        self.assertEqual(len(records), 7)
        for record in records:
            self.assertTrue(Path(str(record) + ".dsse.json").is_file(), record)
        code, _, err = call(verify_main, *records, "--require-signature", "--key", self.key)
        self.assertEqual((code, err), (0, ""))

    def test_unchanged_behavior_without_the_flag(self):
        plain = self.root / "plain"
        self.assertEqual(call(run_main, "--scenario", "win", "--out", plain)[0], 0)
        self.assertEqual(sorted(p.name for p in plain.iterdir()), ["DECISION.md", "decision.json"])
        self.assertEqual(call(verify_main, plain / "decision.json")[0], 0)
        # envelopes are ignored without the flag, even a wrong one
        self.assertEqual(call(verify_main, self.forged_copy())[0], 0)

    def test_edited_and_rehashed_record_passes_digest_check_but_fails_signature(self):
        forged = self.forged_copy()
        self.assertEqual(call(verify_main, forged)[0], 0)
        code, _, err = self.verify(forged)
        self.assertEqual(code, 1)
        self.assertIn("different record bytes", err)

    def test_whitespace_only_change_breaks_the_signature(self):
        reformatted = self.root / "reformatted" / "decision.json"
        reformatted.parent.mkdir()
        reformatted.write_text(json.dumps(json.loads(self.record.read_text(encoding="utf-8"))), encoding="utf-8")
        Path(str(reformatted) + ".dsse.json").write_bytes(self.envelope.read_bytes())
        self.assertEqual(call(verify_main, reformatted)[0], 0)
        self.assertEqual(self.verify(reformatted)[0], 1)

    def test_wrong_key_exits_one(self):
        code, _, err = self.verify(key=self.other)
        self.assertEqual(code, 1)
        self.assertIn("no valid signature", err)

    def test_unsigned_record_exits_one(self):
        self.envelope.unlink()
        code, _, err = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("unsigned", err)

    def test_explicit_signature_path(self):
        moved = self.root / "elsewhere.json"
        self.envelope.rename(moved)
        self.assertEqual(self.verify()[0], 1)
        self.assertEqual(self.verify(None, "--signature", moved)[0], 0)

    def test_wrong_predicate_type_exits_one(self):
        data = self.record.read_bytes()
        document = json.loads(data)
        for kind in ("https://github.com/BichengWang/ai-decision-system/predicate/expgate/decision/v2",
                     "https://github.com/BichengWang/ai-decision-system/predicate/decisioncontrol/record/v4"):
            envelope = signing.sign(data, "decision.json", kind, {"schema": "x"}, signing.load_key(self.key))
            self.envelope.write_text(json.dumps(envelope), encoding="utf-8")
            with self.subTest(kind=kind):
                code, _, err = self.verify()
                self.assertEqual(code, 1)
                self.assertIn("predicate type", err)
        self.assertEqual(attestation.describe(document), 3)

    def test_malformed_envelopes_exit_one(self):
        data = self.record.read_bytes()
        good = json.loads(self.envelope.read_text(encoding="utf-8"))
        cases = {
            "not json": "{",
            "array": "[]",
            "wrong payloadType": json.dumps({**good, "payloadType": "text/plain"}),
            "payload not base64": json.dumps({**good, "payload": "***"}),
            "missing signatures": json.dumps({k: v for k, v in good.items() if k != "signatures"}),
            "signatures not a list": json.dumps({**good, "signatures": "x"}),
            "empty signatures": json.dumps({**good, "signatures": []}),
            "bad sig encoding": json.dumps({**good, "signatures": [{"keyid": good["signatures"][0]["keyid"], "sig": "***"}]}),
            "payload is not a statement": json.dumps({**good, "payload": base64.b64encode(b"[]").decode()}),
            "not utf-8": b"\xff\xfe",
            "nested too deeply": "[" * 200_000 + "]" * 200_000,
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.envelope.write_bytes(text if isinstance(text, bytes) else text.encode())
                self.assertEqual(self.verify()[0], 1)
        self.envelope.write_text(json.dumps(good), encoding="utf-8")
        self.assertEqual(self.verify()[0], 0)
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         json.loads(base64.b64decode(good["payload"]))["subject"][0]["digest"]["sha256"])


    def odd_signed_envelopes(self, good, key):
        """Envelopes whose HMAC is valid but whose statement has fields of unexpected types."""
        import hashlib
        import hmac
        statement = json.loads(base64.b64decode(good["payload"]))

        def signed(body):
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            mac = hmac.new(key, signing.pae(signing.PAYLOAD_TYPE, payload), hashlib.sha256).digest()
            return {"payloadType": signing.PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
                    "signatures": [{"keyid": signing.key_id(key), "sig": base64.b64encode(mac).decode()}]}

        subject = statement["subject"]
        return {
            "predicateType is a list": signed({**statement, "predicateType": ["x"]}),
            "predicateType is a dict": signed({**statement, "predicateType": {"x": 1}}),
            "subject is a number": signed({**statement, "subject": 7}),
            "subject is a string": signed({**statement, "subject": "abc"}),
            "subject is null": signed({**statement, "subject": None}),
            "subject entries are not objects": signed({**statement, "subject": [1, "x", None, [], True]}),
            "digest is not an object": signed({**statement, "subject": [{"name": "x", "digest": "abc"}]}),
            "digest value is a number": signed({**statement, "subject": [{"name": "x", "digest": {"sha256": 5}}]}),
            "digest value is a list": signed({**statement, "subject": [{"name": "x", "digest": {"sha256": [1]}}]}),
            "digest value is non-ASCII": signed({**statement, "subject": [{"name": "x", "digest": {"sha256": "\u00e9" * 64}}]}),
            "high surrogate digest": signed({**statement, "subject": [{"name": "x", "digest": {"sha256": "\ud800"}}]}),
            "low surrogate digest": signed({**statement, "subject": [{"name": "x", "digest": {"sha256": "\udc00" * 64}}]}),
            "uppercase hex digest": signed({**statement, "subject": [
                {"name": "x", "digest": {"sha256": statement["subject"][0]["digest"]["sha256"].upper()}}]}),
            "63 character digest": signed({**statement, "subject": [
                {"name": "x", "digest": {"sha256": statement["subject"][0]["digest"]["sha256"][:63]}}]}),
            "65 character digest": signed({**statement, "subject": [
                {"name": "x", "digest": {"sha256": statement["subject"][0]["digest"]["sha256"] + "0"}}]}),
            "deeply nested list digest": signed(json.dumps({**statement, "subject": [
                {"name": "x", "digest": {"sha256": "NESTED"}}]}).encode().replace(
                    b'"NESTED"', b"[" * 100000 + b"]" * 100000)),
            "deeply nested payload": signed(b"[" * 100000),
            "statement _type is a list": signed({**statement, "_type": []}),
            "subject is an object": signed({**statement, "subject": subject[0]}),
        }

    def sig_field_variants(self, good):
        keyid = good["signatures"][0]["keyid"]
        return {
            "sig is null": [{"keyid": keyid, "sig": None}],
            "sig missing": [{"keyid": keyid}],
            "sig is a number": [{"keyid": keyid, "sig": 7}],
            "sig is a list": [{"keyid": keyid, "sig": ["a"]}],
            "sig is an object": [{"keyid": keyid, "sig": {"a": 1}}],
            "sig is true": [{"keyid": keyid, "sig": True}],
            "keyid is a list": [{"keyid": ["a"], "sig": good["signatures"][0]["sig"]}],
            "entry is null": [None],
        }

    def test_null_and_odd_typed_signature_fields_exit_one(self):
        good = json.loads(self.envelope.read_text(encoding="utf-8"))
        key = signing.load_key(self.key)
        cases = {name: {**good, "signatures": entries} for name, entries in self.sig_field_variants(good).items()}
        cases.update({"payload is a number": {**good, "payload": 5}, "payload is null": {**good, "payload": None},
                      "payload is a list": {**good, "payload": ["a"]}, "payload is non-ASCII": {**good, "payload": "\u00e9"}})
        cases.update(self.odd_signed_envelopes(good, key))
        for name, envelope in cases.items():
            self.envelope.write_text(json.dumps(envelope), encoding="utf-8")
            with self.subTest(name):
                code, _, err = self.verify()
                self.assertEqual(code, 1, err)
                self.assertNotIn("Traceback", err)
        self.envelope.write_text(json.dumps(good), encoding="utf-8")
        self.assertEqual(self.verify()[0], 0)

    def test_tampered_statement_digest_exits_one(self):
        good = json.loads(self.envelope.read_text(encoding="utf-8"))
        statement = json.loads(base64.b64decode(good["payload"]))
        statement["subject"][0]["digest"]["sha256"] = "0" * 64
        payload = signing.canonicalize(statement)
        good["payload"] = base64.b64encode(payload).decode()  # signature no longer matches the payload
        self.envelope.write_text(json.dumps(good), encoding="utf-8")
        self.assertEqual(self.verify()[0], 1)

    def test_bad_key_file_exits_two_and_writes_nothing(self):
        cases = {"missing": self.root / "nope.key", "short": self.root / "short.key", "not hex": self.root / "hex.key",
                 "directory": self.root}
        cases["short"].write_text("ab" * 8, encoding="ascii")
        cases["not hex"].write_text("zz" * 40, encoding="ascii")
        for name, key in cases.items():
            out = self.root / f"out-{name.replace(' ', '-')}"
            with self.subTest(case=name):
                code, stdout, stderr = call(run_main, "--all-scenarios", "--out", out, "--sign-key", key)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertFalse(out.exists())
                self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".out-")], [])
                code, stdout, stderr = self.verify(key=key)
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn("cannot verify", stderr)

    def test_key_generation_is_mode_0600_and_never_overwrites(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.key).st_mode), 0o600)
        text = self.key.read_text(encoding="ascii").strip()
        self.assertEqual(len(bytes.fromhex(text)), 32)
        before = self.key.read_bytes()
        code, _, err = call(run_main, "keygen", self.key)
        self.assertEqual(code, 2)
        self.assertIn("exists", err)
        self.assertEqual(self.key.read_bytes(), before)
        code, out, _ = call(run_main, "keygen", self.root / "third.key")
        self.assertEqual(json.loads(out)["key_id"], signing.key_id(signing.load_key(self.root / "third.key")))

    def test_schema_1_and_unsupported_records_are_input_errors_under_the_flag(self):
        for name, text in (("legacy", json.dumps({"decision": "SHIP"})), ("v4", json.dumps({"schema_version": 4})),
                           ("malformed", "{"), ("array", "[]")):
            path = self.root / f"{name}.json"
            path.write_text(text, encoding="utf-8")
            with self.subTest(name=name):
                self.assertEqual(self.verify(path)[0], 2)

    def test_flag_combinations_are_usage_errors(self):
        record, key = self.record, self.key
        bundle = self.root / "b.sigstore.json"
        cases = [
            (record, "--key", key),
            (record, "--signature", self.envelope),
            (record, "--require-signature"),
            (record, "--require-signature", "--key", key, "--sigstore-bundle", bundle,
             "--certificate-identity", "i", "--certificate-oidc-issuer", "u"),
            (record, "--require-signature", "--key", key, "--certificate-identity", "i"),
            (record, "--require-signature", "--sigstore-bundle", bundle),
            (record, "--require-signature", "--sigstore-bundle", bundle, "--certificate-identity", "i",
             "--certificate-oidc-issuer", "u", "--signature", self.envelope),
            (record, record, "--require-signature", "--key", key, "--signature", self.envelope),
            (record, record, "--require-signature", "--sigstore-bundle", bundle, "--certificate-identity", "i",
             "--certificate-oidc-issuer", "u"),
        ]
        for case in cases:
            with self.subTest(case=[str(c) for c in case]):
                self.assertEqual(call(verify_main, *case)[0], 2)

    def test_signature_failure_exits_one_even_when_another_record_is_fine(self):
        forged = self.forged_copy()
        code, out, err = call(verify_main, forged, self.record, "--require-signature", "--key", self.key)
        self.assertEqual(code, 1)
        self.assertIn(f"{self.record}: verified", out)

    def test_signed_batch_run_with_require_ship_keeps_its_exit_code(self):
        out = self.root / "gate"
        self.assertEqual(call(run_main, "--scenario", "flat", "--out", out, "--sign-key", self.key, "--require-ship")[0], 1)
        self.assertTrue((out / "decision.json.dsse.json").is_file())

    def test_existing_envelope_target_is_not_left_half_signed(self):
        out = self.root / "retry"
        with mock.patch("expgate.run._write_envelope", side_effect=OSError("disk full")):
            self.assertEqual(call(run_main, "--scenario", "win", "--out", out, "--sign-key", self.key)[0], 2)
        self.assertFalse(out.exists())


class SnapshotTest(unittest.TestCase):
    """The record file is read once; a swap after that read changes nothing the verifier trusts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key = self.root / "k"
        call(run_main, "keygen", self.key)
        out = self.root / "signed"
        call(run_main, "--scenario", "win", "--out", out, "--sign-key", self.key)
        self.record = out / "decision.json"
        self.genuine = self.record.read_bytes()
        record = json.loads(self.genuine)
        edited = copy.deepcopy(record["input"])
        edited["arms"]["treatment"]["metrics"]["conversion"]["successes"] -= 300
        self.forged = record_bytes(evaluate(edited))

    def swap_after_first_read(self, first, later):
        """Path.read_bytes on the record returns ``first`` once and ``later`` for any further read."""
        real = Path.read_bytes
        reads = []

        def read_bytes(path):
            if path == self.record:
                reads.append(path)
                return first if len(reads) == 1 else later
            return real(path)

        return mock.patch.object(Path, "read_bytes", read_bytes), reads

    def test_forged_first_read_is_not_rescued_by_a_genuine_second_read(self):
        patch, reads = self.swap_after_first_read(self.forged, self.genuine)
        with patch:
            code, _, err = call(verify_main, self.record, "--require-signature", "--key", self.key)
        self.assertEqual((code, len(reads)), (1, 1))
        self.assertIn("different record bytes", err)

    def test_genuine_first_read_is_replayed_without_a_second_read(self):
        # Were the file read again, the forged bytes (a different decision input) would change the outcome.
        patch, reads = self.swap_after_first_read(self.genuine, self.forged)
        with patch:
            code, out, _ = call(verify_main, self.record, "--require-signature", "--key", self.key)
        self.assertEqual((code, len(reads)), (0, 1))

    def test_sigstore_gets_a_private_snapshot_not_the_original_path(self):
        bundle = self.root / "b.sigstore.json"
        bundle.write_text("{}", encoding="utf-8")
        seen = {}

        def fake_verify(path, bundle_path, kind, identity, issuer):
            seen.update(path=Path(path), mode=stat.S_IMODE(os.stat(path).st_mode), data=Path(path).read_bytes(),
                        parent_mode=stat.S_IMODE(os.stat(Path(path).parent).st_mode), kind=kind,
                        args=(bundle_path, identity, issuer))
            # the original is swapped after the snapshot; the snapshot must be what cosign sees
            self.record.write_bytes(self.forged)

        patch, reads = self.swap_after_first_read(self.genuine, self.forged)
        with patch, mock.patch.object(signing, "verify_sigstore", fake_verify):
            code, out, err = call(verify_main, self.record, "--require-signature", "--sigstore-bundle", bundle,
                                  "--certificate-identity", "ID", "--certificate-oidc-issuer", "ISS")
        self.assertEqual((code, err, len(reads)), (0, "", 1))
        self.assertNotEqual(seen["path"], self.record)
        self.assertEqual(seen["data"], self.genuine)
        self.assertEqual(seen["mode"], 0o600)
        self.assertEqual(seen["parent_mode"], 0o700)
        self.assertEqual(seen["kind"], "https://github.com/BichengWang/ai-decision-system/predicate/expgate/decision/v3")
        self.assertEqual(seen["args"], (bundle, "ID", "ISS"))
        self.assertFalse(seen["path"].exists(), "the snapshot is removed after verification")

    def test_sigstore_rejection_missing_bundle_and_missing_cosign(self):
        args = ("--require-signature", "--certificate-identity", "ID", "--certificate-oidc-issuer", "ISS")
        missing = self.root / "none.sigstore.json"
        code, _, err = call(verify_main, self.record, *args, "--sigstore-bundle", missing)
        self.assertEqual(code, 1)
        self.assertIn("unsigned", err)
        bundle = self.root / "b.sigstore.json"
        bundle.write_text("{}", encoding="utf-8")
        with mock.patch("shutil.which", return_value=None):
            code, _, err = call(verify_main, self.record, *args, "--sigstore-bundle", bundle)
        self.assertEqual(code, 2)
        self.assertIn("cosign is not installed", err)
        completed = mock.Mock(returncode=1, stderr="no matching signatures")
        with mock.patch("shutil.which", return_value="/usr/bin/cosign"), \
                mock.patch("subprocess.run", return_value=completed) as run:
            code, _, err = call(verify_main, self.record, *args, "--sigstore-bundle", bundle)
        self.assertEqual(code, 1)
        self.assertIn("cosign rejected", err)
        command = run.call_args[0][0]
        self.assertEqual(command[:2], ["/usr/bin/cosign", "verify-blob-attestation"])
        self.assertEqual(command[command.index("--type") + 1],
                         "https://github.com/BichengWang/ai-decision-system/predicate/expgate/decision/v3")
        self.assertEqual(command[command.index("--certificate-identity") + 1], "ID")
        self.assertEqual(command[command.index("--certificate-oidc-issuer") + 1], "ISS")
        self.assertNotEqual(Path(command[-1]), self.record)


class PredicateTest(unittest.TestCase):
    def test_predicate_command_writes_the_attest_blob_predicate_for_each_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = json.loads((EXAMPLES / "offer-ranker-v2.json").read_text(encoding="utf-8"))
            for version in (2, 3):
                record = root / f"v{version}.json"
                record.write_bytes(record_bytes(evaluate(summary, schema_version=version)))
                out = root / f"pred{version}.json"
                code, stdout, _ = call(run_main, "predicate", "--record", record, "--out", out)
                self.assertEqual(code, 0)
                result = json.loads(stdout)
                self.assertEqual(result["predicate_type"],
                                 f"https://github.com/BichengWang/ai-decision-system/predicate/expgate/decision/v{version}")
                self.assertEqual(json.loads(out.read_text(encoding="utf-8")),
                                 {"schema": f"https://github.com/BichengWang/ai-decision-system/schema/expgate/decision.v{version}.json"})
                self.assertEqual(call(run_main, "predicate", "--record", record, "--out", out)[0], 2)  # no overwrite
            self.assertEqual(call(run_main, "predicate", "--record", root / "missing.json", "--out", root / "p")[0], 2)
            deep = root / "deep.json"
            deep.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
            self.assertEqual(call(run_main, "predicate", "--record", deep, "--out", root / "p")[0], 2)

    def test_schema_files_exist_for_every_signable_version(self):
        schema = Path(attestation.__file__).parent / "schema"
        for version in attestation.SUPPORTED_SCHEMAS:
            document = json.loads((schema / f"decision.v{version}.json").read_text(encoding="utf-8"))
            self.assertEqual(document["$id"], attestation.predicate(version)["schema"])


if __name__ == "__main__":
    unittest.main()
