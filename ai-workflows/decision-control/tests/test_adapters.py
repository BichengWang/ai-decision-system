"""Frozen OPA and Cedar decisions: freezing, mapping, binding, digest-only and re-evaluated replay."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from decisioncontrol import (DecisionError, Evaluation, RecordMismatch, Recommendation, RoutingPolicy, Ticket,
                             TicketStore, Verdict)
from decisioncontrol import export_record, replay
from decisioncontrol.adapters import _binding, cedar, engine_for, opa
from decisioncontrol.cli import main
from decisioncontrol.jcs import canonicalize
from decisioncontrol.policy import combine
from dc_support import rehash_record

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "policy-engines"
RECORDS = sorted((FIXTURES / "records").glob("*.json"))
HAVE_OPA, HAVE_CEDAR = shutil.which("opa") is not None, shutil.which("cedar") is not None


def load(name):
    return json.loads((FIXTURES / "records" / f"{name}.json").read_text(encoding="utf-8"))


def refreeze(envelope, edit):
    """Edit the frozen external decision and recompute both digests: what a forger can do."""
    envelope = deepcopy(envelope)
    edit(envelope["record"]["external_policy"])
    envelope["record"]["external_policy_sha256"] = hashlib.sha256(
        canonicalize(envelope["record"]["external_policy"])).hexdigest()
    return rehash_record(envelope)


def run_cli(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(argv))
    return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()


class NoTools:
    """PATH without opa or cedar: the digest-only environment."""

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patch = patch.dict(os.environ, {"PATH": self.directory.name})
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()
        self.directory.cleanup()


class CombineTests(unittest.TestCase):
    def test_the_more_restrictive_verdict_wins_and_keeps_only_its_reasons(self):
        allow, review = Evaluation(Verdict.ALLOW, ("a",)), Evaluation(Verdict.REVIEW, ("r",))
        deny, abstain = Evaluation(Verdict.DENY, ("d",)), Evaluation(Verdict.ABSTAIN, ("s",))
        self.assertEqual(combine(allow, review), review)
        self.assertEqual(combine(review, allow), review)
        self.assertEqual(combine(review, abstain), abstain)
        self.assertEqual(combine(abstain, deny), deny)
        self.assertEqual(combine(allow, deny), deny)

    def test_equal_verdicts_merge_reasons_without_duplicates(self):
        merged = combine(Evaluation(Verdict.DENY, ("x", "y")), Evaluation(Verdict.DENY, ("y", "z")))
        self.assertEqual(merged, Evaluation(Verdict.DENY, ("x", "y", "z")))


class OpaAdapterTests(unittest.TestCase):
    def frozen(self, **changes):
        base = {"engine": "opa", "decision_id": "d1", "path": "ticket/routing/decision",
                "bundles": {"b": {"revision": "r1"}}, "input": {"a": 1}, "result": True,
                "modules": {"routing.rego": "package ticket.routing"}, "data": {}}
        return {**base, **changes}

    def test_query_quotes_what_is_not_a_plain_rego_name(self):
        self.assertEqual(opa.query("ticket/routing/decision"), "data.ticket.routing.decision")
        self.assertEqual(opa.query("/a/b-c/default/"), 'data.a["b-c"]["default"]')
        for bad in ("", "//", "a//b", " a"):
            with self.subTest(path=bad), self.assertRaises(DecisionError):
                opa.query(bad)

    def test_results_map_to_verdicts(self):
        self.assertEqual(opa.evaluation(self.frozen(result=True)), Evaluation(Verdict.ALLOW, ("opa:allow",)))
        self.assertEqual(opa.evaluation(self.frozen(result=False)), Evaluation(Verdict.DENY, ("opa:deny",)))
        self.assertEqual(opa.evaluation(self.frozen(result={"verdict": "REVIEW", "reasons": ["why"], "extra": 1})),
                         Evaluation(Verdict.REVIEW, ("opa:why",)))
        self.assertEqual(opa.evaluation(self.frozen(result={"verdict": "ABSTAIN"})).reasons, ("opa:policy_decision",))
        for bad in (None, 1, "allow", [], {}, {"allow": True}, {"verdict": "MAYBE"}, {"verdict": "ALLOW", "reasons": []},
                    {"verdict": "ALLOW", "reasons": [" x"]}):
            with self.subTest(result=bad), self.assertRaises(DecisionError):
                opa.evaluation(self.frozen(result=bad))

    def test_validate_is_strict(self):
        self.assertEqual(opa.validate(self.frozen())["decision_id"], "d1")
        for changes in ({"engine": "cedar"}, {"decision_id": ""}, {"path": "//"}, {"bundles": []},
                        {"bundles": {"b": {}}}, {"bundles": {"b": {"revision": 1}}}, {"input": []}, {"data": []},
                        {"modules": {}}, {"modules": {"../x.rego": "p"}}, {"modules": {"/x.rego": "p"}},
                        {"modules": {"x.txt": "p"}}, {"modules": {".hidden.rego": "p"}}, {"modules": {"a.rego": 1}},
                        {"timestamp": " "}, {"labels": []}, {"extra": 1}, {"result": float("nan")}):
            with self.subTest(changes=changes), self.assertRaises(DecisionError):
                opa.validate(self.frozen(**changes))
        missing = self.frozen()
        del missing["result"]
        with self.assertRaises(DecisionError):
            opa.validate(missing)

    def test_log_entries_come_from_json_arrays_and_json_lines(self):
        first, second = {"decision_id": "a", "result": 1}, {"decision_id": "b", "result": 2}
        lines = "\n".join(json.dumps(item) for item in (first, {"msg": "noise"}, second)) + "\n"
        self.assertEqual(opa.entries_from_log(lines), [first, second])
        self.assertEqual(opa.entries_from_log(json.dumps([first, second])), [first, second])
        self.assertEqual(opa.entries_from_log(json.dumps(first)), [first])
        with self.assertRaises(DecisionError):
            opa.entries_from_log('{"decision_id": "a"}\nnot json\n')
        self.assertEqual(opa.select_entry([first], None), first)
        self.assertEqual(opa.select_entry([first, second], "b"), second)
        for entries, wanted in (([first, second], None), ([first], "zzz"), ([], None)):
            with self.subTest(wanted=wanted), self.assertRaises(DecisionError):
                opa.select_entry(entries, wanted)

    def test_freeze_refuses_masked_or_erased_entries_and_wrong_bundle_revisions(self):
        entry = {"decision_id": "d", "path": "a/b", "input": {}, "result": True, "bundles": {"x": {"revision": "r1"}}}
        modules = {"p.rego": "package a"}
        frozen = opa.freeze(entry, modules, None, bundle_revision="r1")
        self.assertEqual((frozen["data"], frozen["bundles"]), ({}, {"x": {"revision": "r1"}}))
        for extra in ({"erased": ["/input/x"]}, {"masked": ["/input/y"]}):
            with self.subTest(extra=extra), self.assertRaises(DecisionError):
                opa.freeze({**entry, **extra}, modules)
        with self.assertRaises(DecisionError):
            opa.freeze(entry, modules, bundle_revision="r2")
        for name in ("decision_id", "path", "input", "result"):
            partial = dict(entry)
            del partial[name]
            with self.subTest(missing=name), self.assertRaises(DecisionError):
                opa.freeze(partial, modules)

    def test_policy_directory_is_read_strictly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertRaises(DecisionError, opa.load_policy_dir, root)
            (root / "sub").mkdir()
            (root / "sub" / "a.rego").write_text("package a", encoding="utf-8")
            (root / "data.json").write_text('{"k": 1}', encoding="utf-8")
            (root / ".manifest").write_text('{"revision": "r7"}', encoding="utf-8")
            self.assertEqual(opa.load_policy_dir(root), ({"sub/a.rego": "package a"}, {"k": 1}, "r7"))
            (root / "sub" / "data.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(DecisionError, "root data.json"):
                opa.load_policy_dir(root)
            (root / "sub" / "data.json").unlink()
            (root / "link.rego").symlink_to(root / "sub" / "a.rego")
            with self.assertRaisesRegex(DecisionError, "symbolic"):
                opa.load_policy_dir(root)


class CedarAdapterTests(unittest.TestCase):
    def frozen(self, **changes):
        base = {"engine": "cedar", "policies": {"format": "cedar", "text": "permit(principal, action, resource);"},
                "entities": [], "decision": "Allow", "diagnostics": {"reason": ["policy0"], "errors": []},
                "request": {"principal": 'User::"a"', "action": 'Action::"b"', "resource": 'Ticket::"c"', "context": {}}}
        return {**base, **changes}

    def test_request_escapes_cedar_string_literals(self):
        proposal = Recommendation("reassign_ticket", 'T"1\\', "support", 0.9, "m", "q")
        from decisioncontrol import Ticket
        request = cedar.authorization_request(proposal, Ticket('T"1\\', "intake"), "al\nice")
        self.assertEqual(request["principal"], 'User::"al\\u{a}ice"')
        self.assertEqual(request["resource"], 'Ticket::"T\\"1\\\\"')
        self.assertEqual(request["context"], {"requested": "support", "current": "intake",
                                              "proposal_sha256": _binding.proposal_sha256(proposal, Ticket('T"1\\', "intake"), "al\nice")})
        priority = Recommendation("set_ticket_priority", "t", None, 0.9, "m", "q", priority="high")
        context = cedar.authorization_request(priority, Ticket("t", "d"), "a")["context"]
        self.assertEqual(set(context), {"requested", "proposal_sha256"})
        self.assertEqual(context["requested"], "high")

    def test_decisions_map_to_verdicts_with_the_determining_policies(self):
        self.assertEqual(cedar.evaluation(self.frozen()), Evaluation(Verdict.ALLOW, ("cedar:permit:policy0",)))
        deny = self.frozen(decision="Deny", diagnostics={"reason": ["z", "f"], "errors": []})
        self.assertEqual(cedar.evaluation(deny), Evaluation(Verdict.DENY, ("cedar:forbid:f", "cedar:forbid:z")))
        default = self.frozen(decision="Deny", diagnostics={"reason": [], "errors": []})
        self.assertEqual(cedar.evaluation(default), Evaluation(Verdict.DENY, ("cedar:no_permit_applied",)))
        with self.assertRaises(RecordMismatch):
            cedar.evaluation(self.frozen(diagnostics={"reason": [], "errors": []}))

    def test_validate_is_strict(self):
        self.assertEqual(cedar.validate(self.frozen())["decision"], "Allow")
        json_policies = {"format": "json", "json": {"staticPolicies": {}}}
        self.assertEqual(cedar.validate(self.frozen(policies=json_policies))["policies"], json_policies)
        bad_request = self.frozen()["request"]
        for changes in ({"engine": "opa"}, {"decision": "ALLOW"}, {"entities": {}}, {"entities": [1]},
                        {"policies": {"format": "yaml", "text": ""}}, {"policies": {"format": "cedar"}},
                        {"policies": {"format": "json", "json": []}}, {"diagnostics": {"reason": ["a", "a"], "errors": []}},
                        {"diagnostics": {"reason": [], "errors": [{"error": "x"}]}},
                        {"diagnostics": {"reason": [], "errors": {}}}, {"diagnostics": {"reason": []}},
                        {"request": {**bad_request, "context": []}}, {"request": {"principal": "x"}}, {"extra": 1}):
            with self.subTest(changes=changes), self.assertRaises(DecisionError):
                cedar.validate(self.frozen(**changes))

    def test_freeze_from_a_recorded_response_needs_no_tool(self):
        response = {"decision": "Allow", "diagnostics": {"reason": ["policy0"], "errors": []}}
        with NoTools():
            frozen = cedar.freeze({"format": "cedar", "text": "permit(principal, action, resource);"}, [],
                                  self.frozen()["request"], response)
            self.assertEqual(frozen["decision"], "Allow")
            with self.assertRaisesRegex(DecisionError, "cedar is not on PATH"):
                cedar.freeze({"format": "cedar", "text": "x"}, [], self.frozen()["request"])
            with self.assertRaises(DecisionError):
                cedar.freeze({"format": "cedar", "text": "x"}, [], self.frozen()["request"], {"decision": "Allow"})

    def test_engine_lookup_rejects_unknown_engines(self):
        self.assertIs(engine_for({"engine": "opa"}), opa)
        self.assertIs(engine_for({"engine": "cedar"}), cedar)
        for value in ({"engine": "rego"}, {}, None, {"engine": 1}):
            with self.subTest(value=value), self.assertRaises(DecisionError):
                engine_for(value)


class RecordedFixtureTests(unittest.TestCase):
    """The committed recordings: real OPA and Cedar decisions (see fixtures/policy-engines)."""

    def test_the_recordings_exist_for_both_engines_and_both_actions(self):
        names = {path.stem for path in RECORDS}
        self.assertEqual(len(names), 8)
        engines = {load(name)["record"]["external_policy"]["engine"] for name in names}
        actions = {load(name)["record"]["recommendation"]["action"] for name in names}
        self.assertEqual((engines, actions), ({"opa", "cedar"}, {"reassign_ticket", "set_ticket_priority"}))
        verdicts = {load(name)["record"]["evaluation"]["verdict"] for name in names}
        self.assertEqual(verdicts, {"ALLOW", "REVIEW", "DENY"})

    def test_opa_entries_keep_the_decision_log_members(self):
        for path in RECORDS:
            frozen = json.loads(path.read_text(encoding="utf-8"))["record"]["external_policy"]
            if frozen["engine"] != "opa":
                continue
            with self.subTest(path=path.name):
                self.assertRegex(frozen["decision_id"], r"^[0-9a-f-]{36}$")
                self.assertEqual(frozen["bundles"], {"bundle": {"revision": "ticket-routing-2026-10-19.1"}})
                self.assertEqual(frozen["path"], "ticket/routing/decision")
                self.assertEqual(frozen["labels"]["version"], "1.21.2")
        log = (FIXTURES / "opa" / "decision-log.jsonl").read_text(encoding="utf-8")
        logged = {entry["decision_id"]: entry for entry in opa.entries_from_log(log)}
        for path in RECORDS:
            frozen = json.loads(path.read_text(encoding="utf-8"))["record"]["external_policy"]
            if frozen["engine"] == "opa":
                entry = logged[frozen["decision_id"]]
                self.assertEqual((frozen["input"], frozen["result"], frozen["bundles"]),
                                 (entry["input"], entry["result"], entry["bundles"]))

    def test_every_recording_replays_with_exit_zero(self):
        for path in RECORDS:
            with self.subTest(path=path.name):
                code, result, error = run_cli("replay", "--record", str(path))
                self.assertEqual(code, 0, error)
                expected = "reevaluated" if (HAVE_OPA if "opa-" in path.name else HAVE_CEDAR) else "digest-only"
                self.assertEqual(result["external_policy"]["verification"], expected)

    def test_without_the_tools_replay_is_digest_only_with_a_distinct_message(self):
        with NoTools():
            for path in RECORDS:
                with self.subTest(path=path.name):
                    code, result, error = run_cli("replay", "--record", str(path))
                    engine = "opa" if "opa-" in path.name else "cedar"
                    self.assertEqual(code, 0)
                    self.assertEqual(result["external_policy"], {
                        "engine": engine, "verification": "digest-only", "reason": f"{engine} was not found on PATH"})
                    self.assertIn("decision-control: policy NOT re-evaluated", error)
                    self.assertIn("digest-only verification", error)

    def test_require_reevaluation_exits_two_without_the_tool_and_zero_with_it(self):
        path = FIXTURES / "records" / "opa-reassign-allow-executed.json"
        with NoTools():
            code, result, error = run_cli("replay", "--record", str(path), "--require-reevaluation")
            self.assertEqual((code, result), (2, None))
            self.assertIn("--require-reevaluation", error)
            self.assertNotIn("NOT re-evaluated", error)
        if HAVE_OPA:
            code, result, _ = run_cli("replay", "--record", str(path), "--require-reevaluation")
            self.assertEqual((code, result["external_policy"]["verification"]), (0, "reevaluated"))

    def test_require_reevaluation_does_not_apply_to_records_without_an_external_policy(self):
        envelope = rehash_record({"record": {**load("opa-reassign-allow-executed")["record"],
                                             "external_policy": None, "external_policy_sha256": None,
                                             "evaluation": {"verdict": "ALLOW", "reasons": ["policy_permits_reassignment"]}},
                                  "sha256": ""})
        with tempfile.TemporaryDirectory() as tmp, NoTools():
            path = Path(tmp) / "plain.json"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            code, result, error = run_cli("replay", "--record", str(path), "--require-reevaluation")
            self.assertEqual((code, "external_policy" in result), (0, False))
            self.assertNotIn("decision-control:", error)

    def test_library_replay_can_skip_reevaluation(self):
        envelope = load("cedar-reassign-allow-executed")
        self.assertEqual(replay(envelope, reevaluate=False)["external_policy"],
                         {"engine": "cedar", "verification": "digest-only", "reason": "re-evaluation was disabled"})


class TamperedFixtureTests(unittest.TestCase):
    """Editing the frozen input or result exits 1, with or without the tools."""

    def write(self, envelope):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "record.json"
        path.write_text(json.dumps(envelope), encoding="utf-8")
        return str(path)

    def exit_codes(self, envelope):
        path = self.write(envelope)
        with NoTools():
            offline = run_cli("replay", "--record", path)[0]
        return offline, run_cli("replay", "--record", path)[0]

    def test_editing_the_input_or_result_without_recomputing_the_checksum_exits_one(self):
        for name, edit in (
                ("opa-reassign-allow-executed", lambda f: f["input"]["recommendation"].update(destination="engineering")),
                ("opa-reassign-allow-executed", lambda f: f["result"].update(verdict="DENY")),
                ("cedar-reassign-allow-executed", lambda f: f["request"]["context"].update(requested="engineering")),
                ("cedar-reassign-allow-executed", lambda f: f.update(decision="Deny"))):
            envelope = load(name)
            edit(envelope["record"]["external_policy"])
            with self.subTest(name=name):
                self.assertEqual(self.exit_codes(envelope), (1, 1))

    def test_editing_the_input_or_result_and_recomputing_both_digests_exits_one(self):
        for name, edit in (
                ("opa-reassign-allow-executed", lambda f: f["input"].update(proposed_by="bob")),
                ("opa-reassign-allow-executed", lambda f: f["input"]["ticket"].update(department="support")),
                ("opa-reassign-allow-executed", lambda f: f["result"].update(verdict="DENY")),
                ("opa-reassign-denied", lambda f: f["result"].update(verdict="ALLOW")),
                ("opa-reassign-denied", lambda f: f.update(result=True)),
                ("cedar-reassign-allow-executed", lambda f: f["request"].update(principal='User::"bob"')),
                ("cedar-reassign-denied", lambda f: f.update(decision="Allow")),
                ("cedar-reassign-forbidden", lambda f: f["diagnostics"].update(reason=[]))):
            with self.subTest(name=name):
                self.assertEqual(self.exit_codes(refreeze(load(name), edit)), (1, 1))

    def test_a_frozen_decision_from_another_proposal_cannot_be_transplanted(self):
        donor = load("opa-reassign-allow-executed")["record"]["external_policy"]
        envelope = deepcopy(load("opa-reassign-review-approved-executed"))
        envelope["record"]["external_policy"] = donor
        envelope["record"]["external_policy_sha256"] = hashlib.sha256(canonicalize(donor)).hexdigest()
        self.assertEqual(self.exit_codes(rehash_record(envelope)), (1, 1))

    def test_malformed_frozen_decisions_exit_two(self):
        for name, edit in (
                ("opa-reassign-allow-executed", lambda f: f.update(engine="rego")),
                ("opa-reassign-allow-executed", lambda f: f["modules"].update({"../x.rego": "package x"})),
                ("opa-reassign-allow-executed", lambda f: f.pop("modules")),
                ("cedar-reassign-denied", lambda f: f.update(decision="Permit"))):
            with self.subTest(name=name):
                self.assertEqual(self.exit_codes(refreeze(load(name), edit)), (2, 2))

    def test_external_digest_must_be_null_exactly_when_the_policy_is(self):
        envelope = load("opa-reassign-allow-executed")
        envelope["record"]["external_policy_sha256"] = None
        self.assertEqual(self.exit_codes(rehash_record(envelope)), (1, 1))
        plain = deepcopy(envelope)
        plain["record"]["external_policy"] = None
        plain["record"]["external_policy_sha256"] = "0" * 64
        self.assertEqual(self.exit_codes(rehash_record(plain)), (2, 2))

    @unittest.skipUnless(HAVE_OPA, "opa is required")
    def test_editing_the_frozen_rego_is_only_caught_by_reevaluation(self):
        def loosen(frozen):
            name = next(iter(frozen["modules"]))
            frozen["modules"][name] = frozen["modules"][name].replace(
                'default decision := {"verdict": "DENY", "reasons": ["no_rule_matched"]}',
                'default decision := {"verdict": "ALLOW", "reasons": ["no_rule_matched"]}')
        envelope = refreeze(load("opa-reassign-denied"), loosen)
        self.assertEqual(envelope["record"]["evaluation"]["verdict"], "DENY")
        self.assertNotEqual(envelope, load("opa-reassign-denied"))
        offline, online = self.exit_codes(envelope)
        self.assertEqual((offline, online), (0, 1))

    @unittest.skipUnless(HAVE_OPA, "opa is required")
    def test_replay_does_not_let_a_frozen_policy_reach_the_network(self):
        def probe(frozen):
            name = next(iter(frozen["modules"]))
            frozen["modules"][name] += ('\ndecision := {"verdict": "ALLOW", "reasons": ["router_reassigns_to_open_destination"]} if {\n'
                                        '\tinput.action == "reassign_ticket"\n'
                                        '\thttp.send({"method": "GET", "url": "http://127.0.0.1:9/"})\n}\n')
        envelope = refreeze(load("opa-reassign-allow-executed"), probe)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            code, _, error = run_cli("replay", "--record", str(path))
        self.assertEqual(code, 1)
        self.assertIn("could not evaluate the frozen policy", error)

    @unittest.skipUnless(HAVE_CEDAR, "cedar is required")
    def test_editing_the_frozen_cedar_policies_is_only_caught_by_reevaluation(self):
        def drop_permit(frozen):
            frozen["policies"]["text"] = frozen["policies"]["text"].replace("support", "nowhere")
        envelope = refreeze(load("cedar-reassign-allow-executed"), drop_permit)
        offline, online = self.exit_codes(envelope)
        self.assertEqual((offline, online), (0, 1))

    @unittest.skipUnless(HAVE_CEDAR, "cedar is required")
    def test_unparseable_frozen_cedar_policies_exit_one(self):
        envelope = refreeze(load("cedar-reassign-allow-executed"),
                            lambda frozen: frozen["policies"].update(text="this is not cedar"))
        self.assertEqual(self.exit_codes(envelope), (0, 1))


class SubmitExternalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = TicketStore(self.root / "queue.sqlite3")
        self.addCleanup(self.store.close)
        self.store.create_ticket("T-201", "intake")
        self.policy = RoutingPolicy("p", ("support", "engineering"), ("engineering",), ("bob",))
        self.frozen = load("opa-reassign-allow-executed")["record"]["external_policy"]
        self.proposal = Recommendation("reassign_ticket", "T-201", "support", 0.95,
                                       "recorded-fixture-not-a-provider", "routing-question-1")

    def test_a_matching_decision_is_frozen_and_digested(self):
        record = self.store.submit(self.proposal, self.policy, "alice", self.frozen)
        self.assertEqual(record["external_policy"], self.frozen)
        self.assertEqual(record["external_policy_sha256"], hashlib.sha256(canonicalize(self.frozen)).hexdigest())
        self.assertEqual(record["evaluation"], {"verdict": "ALLOW", "reasons": ["policy_permits_reassignment",
                                                                              "opa:router_reassigns_to_open_destination"]})
        self.assertEqual(self.store.get(record["id"]), record)
        self.assertTrue(replay(export_record(self.store.execute(record["id"])))["valid"])

    def test_a_decision_for_a_different_proposer_or_proposal_is_refused(self):
        with self.assertRaises(RecordMismatch):
            self.store.submit(self.proposal, self.policy, "bob", self.frozen)
        other = Recommendation("reassign_ticket", "T-201", "engineering", 0.95, "m", "q")
        with self.assertRaises(RecordMismatch):
            self.store.submit(other, self.policy, "alice", self.frozen)
        self.assertEqual(self.store.pending(), [])

    def test_an_invalid_external_block_is_refused_before_anything_is_stored(self):
        for block in ({"engine": "rego"}, {**self.frozen, "extra": 1}, "opa"):
            with self.subTest(block=block), self.assertRaises(DecisionError):
                self.store.submit(self.proposal, self.policy, "alice", block)

    def test_an_external_deny_overrides_a_builtin_allow(self):
        denied = load("opa-reassign-denied")["record"]
        self.store.create_ticket("T-203", "intake")
        proposal = Recommendation.from_dict(denied["recommendation"])
        record = self.store.submit(proposal, self.policy, "mallory", denied["external_policy"])
        self.assertEqual((record["evaluation"]["verdict"], record["status"]), ("DENY", "DENIED"))
        self.assertEqual(record["evaluation"]["reasons"], ["opa:no_rule_matched"])

    def test_an_external_review_overrides_a_builtin_allow(self):
        review = load("opa-reassign-review-approved-executed")["record"]["external_policy"]
        self.store.create_ticket("T-202", "intake")
        proposal = Recommendation("reassign_ticket", "T-202", "engineering", 0.95,
                                  "recorded-fixture-not-a-provider", "routing-question-1")
        policy = RoutingPolicy("p", ("support", "engineering"), (), ("bob",))
        record = self.store.submit(proposal, policy, "alice", review)
        self.assertEqual((record["evaluation"]["verdict"], record["status"]), ("REVIEW", "PENDING_REVIEW"))


class BindingCompletenessTests(unittest.TestCase):
    """A frozen decision is bound to the complete proposal and ticket snapshot, for both engines."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TicketStore(Path(self.tmp.name) / "queue.sqlite3")
        self.addCleanup(self.store.close)
        self.policy = RoutingPolicy("p", ("support", "engineering", "legal"), ("engineering",), ("bob",),
                                    0.8, ("low", "normal", "high", "urgent"), ("urgent",))

    def recorded(self, name):
        record = load(name)["record"]
        self.store.create_ticket(record["ticket"]["id"], record["ticket"]["department"],
                                 record["ticket"].get("priority"))
        return record, Recommendation.from_dict(record["recommendation"])

    def test_cedar_authorization_cannot_be_reused_after_the_ticket_moved_to_another_revision(self):
        """The reviewer's reproduction: revision 0 authorization, ticket at revision 1."""
        record, proposal = self.recorded("cedar-reassign-allow-executed")
        frozen = record["external_policy"]
        self.assertEqual(self.store.submit(proposal, self.policy, "alice", frozen)["ticket"]["revision"], 0)
        self.store.create_ticket("T-211b", "intake")
        bumped = Recommendation("set_ticket_priority", "T-211b", None, 0.95, "m", "q", priority="high")
        self.store.execute(self.store.submit(bumped, self.policy, "alice")["id"])
        self.assertEqual(self.store.get_ticket("T-211b").revision, 1)
        again = Recommendation.from_dict({**record["recommendation"], "ticket_id": "T-211b"})
        with self.assertRaises(RecordMismatch):
            self.store.submit(again, self.policy, "alice", frozen)

    def test_same_ticket_at_revision_one_is_refused(self):
        record, proposal = self.recorded("cedar-reassign-allow-executed")
        self.store.execute(self.store.submit(
            Recommendation("set_ticket_priority", "T-211", None, 0.95, "m", "q", priority="high"),
            self.policy, "alice")["id"])
        self.assertEqual(self.store.get_ticket("T-211").revision, 1)
        with self.assertRaises(RecordMismatch):
            self.store.submit(proposal, self.policy, "alice", record["external_policy"])

    def test_each_recommendation_member_is_bound_for_both_engines(self):
        for name in ("cedar-reassign-allow-executed", "opa-reassign-allow-executed"):
            record, proposal = self.recorded(name)
            frozen = record["external_policy"]
            for change in ({"model": "another"}, {"question_version": "q2"}, {"probability": 0.9},
                           {"probability": None}, {"refused": True}):
                changed = Recommendation.from_dict({**record["recommendation"], **change})
                with self.subTest(name=name, change=change), self.assertRaises(RecordMismatch):
                    self.store.submit(changed, self.policy, "alice", frozen)

    def test_each_ticket_member_is_bound_for_both_engines(self):
        for name in ("cedar-reassign-allow-executed", "opa-reassign-allow-executed"):
            record, proposal = self.recorded(name)
            frozen = record["external_policy"]
            ticket = Ticket.from_dict(record["ticket"])
            for changed in (Ticket(ticket.id, ticket.department, 1), Ticket(ticket.id, ticket.department, 0, "low"),
                            Ticket(ticket.id, "other", 0)):
                with self.subTest(name=name, ticket=changed.to_dict()), self.assertRaises(RecordMismatch):
                    (cedar if frozen["engine"] == "cedar" else opa).bind(frozen, proposal, changed, "alice")
            (cedar if frozen["engine"] == "cedar" else opa).bind(frozen, proposal, ticket, "alice")

    def test_replay_rejects_an_edited_snapshot_or_recommendation_with_only_the_record_checksum_recomputed(self):
        for name in ("cedar-reassign-allow-executed", "opa-reassign-allow-executed"):
            for edit in (lambda r: r["ticket"].update(revision=1), lambda r: r["result"].update(revision=2),
                         lambda r: r["recommendation"].update(probability=0.9),
                         lambda r: r["recommendation"].update(question_version="q2")):
                envelope = load(name)
                edit(envelope["record"])
                path = Path(self.tmp.name) / "edited.json"
                path.write_text(json.dumps(rehash_record(envelope)), encoding="utf-8")
                with self.subTest(name=name):
                    self.assertEqual(run_cli("replay", "--record", str(path))[0], 1)
                    with NoTools():
                        self.assertEqual(run_cli("replay", "--record", str(path))[0], 1)


class FreezeCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = str(self.root / "queue.sqlite3")
        self.policy = FIXTURES / "policy.json"

    def test_freeze_opa_from_the_recorded_log_and_submit_it(self):
        log = FIXTURES / "opa" / "decision-log.jsonl"
        entries = opa.entries_from_log(log.read_text(encoding="utf-8"))
        wanted = load("opa-reassign-allow-executed")["record"]["external_policy"]["decision_id"]
        out = self.root / "external.json"
        args = ["freeze-opa", "--decision-log", str(log), "--policy-dir", str(FIXTURES / "opa" / "bundle"),
                "--out", str(out)]
        code, _, error = run_cli(*args)
        self.assertEqual(code, 2, "several entries need --decision-id")
        self.assertIn("--decision-id", error)
        code, frozen, _ = run_cli(*args, "--decision-id", wanted)
        self.assertEqual(code, 0)
        self.assertEqual(frozen, load("opa-reassign-allow-executed")["record"]["external_policy"])
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), frozen)
        self.assertEqual(len(entries), 4)

    def test_freeze_cedar_from_a_recorded_response_and_policy_input(self):
        reference = load("cedar-reassign-forbidden")["record"]["external_policy"]
        files = {"policies.cedar": reference["policies"]["text"], "entities.json": json.dumps(reference["entities"]),
                 "request.json": json.dumps(reference["request"]),
                 "response.json": json.dumps({"decision": reference["decision"], "diagnostics": reference["diagnostics"]})}
        for name, text in files.items():
            (self.root / name).write_text(text, encoding="utf-8")
        code, frozen, error = run_cli("freeze-cedar", "--policies", str(self.root / "policies.cedar"),
                                      "--entities", str(self.root / "entities.json"),
                                      "--request", str(self.root / "request.json"),
                                      "--response", str(self.root / "response.json"))
        self.assertEqual(code, 0, error)
        self.assertEqual(frozen, reference)

    @unittest.skipUnless(HAVE_CEDAR, "cedar is required")
    def test_freeze_cedar_runs_the_cli_and_agrees_with_the_recording(self):
        reference = load("cedar-reassign-forbidden")["record"]["external_policy"]
        (self.root / "entities.json").write_text(json.dumps(reference["entities"]), encoding="utf-8")
        (self.root / "request.json").write_text(json.dumps(reference["request"]), encoding="utf-8")
        code, frozen, error = run_cli("freeze-cedar", "--policies", str(FIXTURES / "cedar" / "policies.cedar"),
                                      "--entities", str(self.root / "entities.json"),
                                      "--request", str(self.root / "request.json"))
        self.assertEqual(code, 0, error)
        self.assertEqual(frozen, reference)

    @unittest.skipUnless(HAVE_CEDAR, "cedar is required")
    def test_freeze_cedar_json_policies_and_diagnostic_errors(self):
        policies = {"staticPolicies": {"p": {"effect": "permit", "principal": {"op": "All"}, "action": {"op": "All"},
                                             "resource": {"op": "All"},
                                             "conditions": [{"kind": "when", "body": {"==": {"left": {".": {
                                                 "left": {"Var": "context"}, "attr": "missing"}},
                                                 "right": {"Value": 1}}}}]}},
                    "templates": {}, "templateLinks": []}
        request = {"principal": 'User::"a"', "action": 'Action::"b"', "resource": 'Ticket::"c"', "context": {}}
        for name, value in (("policies.json", policies), ("entities.json", []), ("request.json", request)):
            (self.root / name).write_text(json.dumps(value), encoding="utf-8")
        code, frozen, _ = run_cli("freeze-cedar", "--policies", str(self.root / "policies.json"),
                                  "--policy-format", "json", "--entities", str(self.root / "entities.json"),
                                  "--request", str(self.root / "request.json"))
        self.assertEqual(code, 0)
        self.assertEqual(frozen["decision"], "Deny")
        self.assertEqual([error["policyId"] for error in frozen["diagnostics"]["errors"]], ["p"])
        self.assertEqual(cedar.reevaluate(frozen) is not None, True)

    def test_policy_input_prints_what_replay_requires(self):
        self.assertEqual(run_cli("--db", self.db, "ticket-create", "--ticket-id", "T-9", "--department", "intake")[0], 0)
        proposal = self.root / "proposal.json"
        proposal.write_text(json.dumps({"action": "reassign_ticket", "ticket_id": "T-9", "destination": "support",
                                        "probability": 0.9, "model": "m", "question_version": "q"}), encoding="utf-8")
        code, document, _ = run_cli("--db", self.db, "policy-input", "--engine", "opa", "--proposal", str(proposal),
                                    "--proposed-by", "alice")
        self.assertEqual((code, document["proposed_by"], document["ticket"]["department"]), (0, "alice", "intake"))
        code, request, _ = run_cli("--db", self.db, "policy-input", "--engine", "cedar", "--proposal", str(proposal),
                                   "--proposed-by", "alice")
        self.assertEqual((code, request["principal"]), (0, 'User::"alice"'))
        self.assertEqual({key: request["context"][key] for key in ("requested", "current")},
                         {"requested": "support", "current": "intake"})
        self.assertRegex(request["context"]["proposal_sha256"], "^[0-9a-f]{64}$")

    def test_submit_with_an_external_policy_file_exports_a_replayable_record(self):
        external = self.root / "external.json"
        external.write_text(json.dumps(load("opa-reassign-allow-executed")["record"]["external_policy"]),
                            encoding="utf-8")
        proposal = self.root / "proposal.json"
        proposal.write_text(json.dumps(load("opa-reassign-allow-executed")["record"]["recommendation"]), encoding="utf-8")
        self.assertEqual(run_cli("--db", self.db, "ticket-create", "--ticket-id", "T-201", "--department", "intake")[0], 0)
        code, record, error = run_cli("--db", self.db, "submit", "--proposal", str(proposal), "--policy", str(self.policy),
                                      "--proposed-by", "alice", "--external-policy", str(external))
        self.assertEqual((code, record["status"]), (0, "READY"), error)
        self.assertEqual(run_cli("--db", self.db, "execute", record["id"])[0], 0)
        out = self.root / "record.json"
        self.assertEqual(run_cli("--db", self.db, "export", record["id"], "--out", str(out))[0], 0)
        code, replayed, _ = run_cli("replay", "--record", str(out))
        self.assertEqual((code, replayed["external_policy"]["engine"]), (0, "opa"))
        wrong = run_cli("--db", self.db, "submit", "--proposal", str(proposal), "--policy", str(self.policy),
                        "--proposed-by", "bob", "--external-policy", str(external))
        self.assertEqual(wrong[0], 2)
        self.assertIn("does not describe", wrong[2])

    def test_a_null_external_policy_or_response_file_is_refused_not_ignored(self):
        null = self.root / "null.json"
        null.write_text("null\n", encoding="utf-8")
        proposal = self.root / "proposal.json"
        proposal.write_text(json.dumps(load("opa-reassign-allow-executed")["record"]["recommendation"]), encoding="utf-8")
        self.assertEqual(run_cli("--db", self.db, "ticket-create", "--ticket-id", "T-201", "--department", "intake")[0], 0)
        code, record, _ = run_cli("--db", self.db, "submit", "--proposal", str(proposal), "--policy", str(self.policy),
                                  "--proposed-by", "alice", "--external-policy", str(null))
        self.assertEqual((code, record), (2, None))
        with TicketStore(self.db) as store:
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 0)
        reference = load("cedar-reassign-forbidden")["record"]["external_policy"]
        for name, text in (("policies.cedar", reference["policies"]["text"]),
                           ("entities.json", json.dumps(reference["entities"])),
                           ("request.json", json.dumps(reference["request"]))):
            (self.root / name).write_text(text, encoding="utf-8")
        with patch("decisioncontrol.adapters.cedar.authorize", return_value=("Allow", {"reason": ["p"], "errors": []})) \
                as authorize:
            code, frozen, _ = run_cli("freeze-cedar", "--policies", str(self.root / "policies.cedar"),
                                      "--entities", str(self.root / "entities.json"),
                                      "--request", str(self.root / "request.json"), "--response", str(null))
        self.assertEqual((code, frozen), (2, None))
        authorize.assert_not_called()


@unittest.skipUnless(HAVE_OPA and HAVE_CEDAR, "opa and cedar are required")
class RecorderTests(unittest.TestCase):
    def test_the_recorder_runs_into_a_new_directory_and_its_records_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([sys.executable, str(FIXTURES / "record.py"), "--out", tmp],
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
            records = sorted((Path(tmp) / "records").glob("*.json"))
            self.assertEqual([path.name for path in records], [path.name for path in RECORDS])
            self.assertTrue((Path(tmp) / "opa" / "decision-log.jsonl").is_file())
            for path in records:
                self.assertEqual(run_cli("replay", "--record", str(path), "--require-reevaluation")[0], 0, path.name)


@unittest.skipUnless(os.environ.get("DECISION_CONTROL_REQUIRE_POLICY_TOOLS") == "1",
                     "CI sets DECISION_CONTROL_REQUIRE_POLICY_TOOLS=1 so that skipped re-evaluation tests fail loudly")
class RequiredToolsTests(unittest.TestCase):
    def test_the_tools_the_fixtures_were_recorded_with_are_on_path(self):
        recorded = (FIXTURES / "tool-versions.txt").read_text(encoding="utf-8").splitlines()
        self.assertTrue(HAVE_OPA and HAVE_CEDAR, "opa and cedar must be on PATH")
        self.assertIn(opa._version(shutil.which("opa"), FIXTURES), recorded)
        self.assertIn(cedar.reevaluate(load("cedar-reassign-allow-executed")["record"]["external_policy"]), recorded)


if __name__ == "__main__":
    unittest.main()
