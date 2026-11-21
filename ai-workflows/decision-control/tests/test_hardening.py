"""Release regressions at SDK, persistence and CLI boundaries."""
import contextlib
import io
import json
import hashlib
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from decisioncontrol import DecisionError, Recommendation, RoutingPolicy, StateError, TicketStore, evaluate_cases, load_cases, write_evaluation, export_record, replay, __version__
from decisioncontrol.cli import main
from decisioncontrol.jcs import canonicalize
from dc_support import as_schema3, python_json_v1, rehash_record
from decisioncontrol.demo import run_demo

class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'queue.sqlite3'
        self.store = TicketStore(self.db)
        self.addCleanup(self.store.close)
        self.store.create_ticket('t1', 'intake')
        self.policy = RoutingPolicy('p1', ('support', 'legal'), ('legal',), ('alice', 'bob'))

    def submit(self, destination='legal'):
        return self.store.submit(Recommendation('reassign_ticket', 't1', destination, 0.95, 'fixture', 'q1'), self.policy, proposed_by='alice')

    def call(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(['--db', str(self.db), *args])
        return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()

    def test_proposer_cannot_approve_reject_or_cancel_review(self):
        for action in ('approve', 'reject', 'cancel'):
            with self.subTest(action=action):
                record = self.submit()
                with self.assertRaises(StateError):
                    getattr(self.store, action)(record['id'], 'alice', 'checked')
                self.assertEqual(self.store.get(record['id']), record)

    def test_pending_skips_corruption_and_cli_reports_it(self):
        bad, good = self.submit(), self.submit()
        with sqlite3.connect(self.db) as connection:
            connection.execute('UPDATE decisions SET record = ? WHERE id = ?', ('{broken', bad['id']))
        pending = self.store.pending()
        self.assertEqual([row['id'] for row in pending], [good['id']])
        self.assertEqual(pending.skipped[0]['id'], bad['id'])
        self.assertTrue(pending.skipped[0]['error'])
        code, output, error = self.call('pending')
        self.assertEqual(code, 1)
        self.assertEqual([row['id'] for row in output], [good['id']])
        self.assertIn(bad['id'], error)

    def test_pending_skips_rows_beyond_the_json_parser_limits(self):
        oversized, nested, good = self.submit(), self.submit(), self.submit()
        # Deep enough for the JSON parser (Python 3.11) or, when it parses, the RFC 8785 writer (3.14+).
        deep = {'engine': 'opa', 'decision_id': 'd', 'path': 'a/b', 'bundles': {}, 'input': {'deep': 'DEEP'},
                'result': True, 'modules': {'a.rego': 'package a'}, 'data': {}}
        edits = ((oversized, '"revision":0', '"revision":' + '1' * 5000),
                 (nested, '"external_policy":null',
                  '"external_policy":' + json.dumps(deep).replace('"DEEP"', '[' * 100000 + ']' * 100000, 1)))
        with sqlite3.connect(self.db) as connection:
            for record, needle, replacement in edits:
                text = json.dumps(record, separators=(',', ':'))
                self.assertIn(needle, text)
                connection.execute('UPDATE decisions SET record = ? WHERE id = ?',
                                   (text.replace(needle, replacement, 1), record['id']))
        pending = self.store.pending()
        self.assertEqual([row['id'] for row in pending], [good['id']])
        self.assertEqual([row['id'] for row in pending.skipped], [oversized['id'], nested['id']])
        code, output, error = self.call('pending')
        self.assertEqual((code, [row['id'] for row in output]), (1, [good['id']]))
        self.assertIn(nested['id'], error)

    def test_identical_rejection_is_idempotent_but_conflicts_error(self):
        record = self.submit()
        rejected = self.store.reject(record['id'], 'bob', 'unsafe')
        self.assertEqual(self.store.reject(record['id'], 'bob', 'unsafe'), rejected)
        for actor, note in (('alice', 'unsafe'), ('bob', 'different')):
            with self.assertRaises(StateError):
                self.store.reject(record['id'], actor, note)
        self.assertEqual(self.store.get(record['id']), rejected)

    def test_stale_execute_cli_exits_one_and_preserves_ticket(self):
        old = self.submit('support')
        self.store.execute(self.submit('support')['id'])
        code, output, _ = self.call('execute', old['id'])
        self.assertEqual(code, 1)
        self.assertEqual(output['status'], 'STALE')
        self.assertEqual(self.store.get_ticket('t1').revision, 1)

    def test_demo_write_failure_leaves_retryable_output(self):
        out = self.root / 'demo'
        from decisioncontrol.demo import _save
        count = 0
        def fail_second(path, value):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected write failure')
            return _save(path, value)
        with patch('decisioncontrol.demo._save', side_effect=fail_second):
            with self.assertRaises(OSError):
                run_demo(out)
        self.assertFalse(out.exists())
        self.assertTrue(run_demo(out)['repeat_execution_same_record'])

    def test_evaluation_write_failure_leaves_empty_target_retryable(self):
        source = Path(__file__).resolve().parents[1] / 'examples'
        report = evaluate_cases(load_cases(source / 'evaluation-cases.jsonl'), RoutingPolicy.from_dict(json.loads((source / 'policy.json').read_text())))
        out = self.root / 'evaluation'
        out.mkdir()
        with patch('decisioncontrol.evaluation.render_evaluation', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                write_evaluation(report, out)
        self.assertEqual(list(out.iterdir()), [])
        self.assertTrue(write_evaluation(report, out)['sha256'])

    def test_export_write_failure_leaves_retryable_file(self):
        record = self.submit()
        out = self.root / 'record.json'
        def partial(value, stream, **kwargs):
            stream.write('{partial')
            raise OSError('injected')
        with patch('decisioncontrol.cli.json.dump', side_effect=partial):
            self.assertEqual(self.call('export', record['id'], '--out', str(out))[0], 2)
        self.assertFalse(out.exists())
        self.assertEqual(self.call('export', record['id'], '--out', str(out))[0], 0)

    def test_store_stamps_schema_version(self):
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_newer_store_version_is_refused_without_modification(self):
        future = self.root / 'future.sqlite3'
        with sqlite3.connect(future) as connection:
            connection.execute('PRAGMA user_version = 999')
        with self.assertRaisesRegex(DecisionError, 'store schema.*999'):
            TicketStore(future)
        with sqlite3.connect(future) as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 999)
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['--db', str(future), 'pending']), 2)
        self.assertIn('999', error.getvalue())

    def test_submit_requires_a_valid_proposer_sdk_and_cli(self):
        proposal = Recommendation('reassign_ticket', 't1', 'legal', 0.95, 'fixture', 'q1')
        with self.assertRaises(TypeError):
            self.store.submit(proposal, self.policy)
        for label in ('', ' alice ', None, 42):
            with self.subTest(label=label), self.assertRaises(DecisionError):
                self.store.submit(proposal, self.policy, proposed_by=label)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(['--db', str(self.db), 'submit', '--proposal', 'unused', '--policy', 'unused'])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.store.pending(), [])

    def test_schema_five_freezes_policy_digest_and_producer(self):
        self.policy = RoutingPolicy('策略', ('support', 'legal'), ('legal',), ('alice', 'bob'))
        record = self.submit()
        self.assertEqual(record['schema_version'], 5)
        self.assertEqual((record['external_policy'], record['external_policy_sha256']), (None, None))
        self.assertEqual(record['proposed_by'], 'alice')
        self.assertEqual(record['produced_by'], {'name': 'decisioncontrol', 'version': __version__})
        digest = hashlib.sha256(canonicalize(record['policy'])).hexdigest()
        self.assertEqual(record['policy_sha256'], digest)
        self.assertEqual(self.store.get(record['id']), record)
        approved = self.store.approve(record['id'], 'bob', 'checked')
        self.assertEqual(approved['policy_sha256'], digest)
        envelope = export_record(approved)
        self.assertEqual(envelope['sha256'], hashlib.sha256(canonicalize(approved)).hexdigest())
        self.assertTrue(replay(envelope)['valid'])

    def test_replay_rejects_self_review_and_policy_digest_even_after_rehash(self):
        record = self.submit()
        approved = self.store.approve(record['id'], 'bob', 'checked')
        cancelled = self.store.cancel(record['id'], 'bob', 'withdraw')
        for original, field, value in ((approved, 'review', 'alice'),
                                       (cancelled, 'events', 'alice'),
                                       (record, 'policy_sha256', '0' * 64),
                                       (record, 'proposed_by', ''),
                                       (record, 'produced_by', {'name': 'other', 'version': '0.1.0'})):
            forged = deepcopy(original)
            if field == 'review':
                forged[field]['reviewer'] = value
            elif field == 'events':
                forged[field][-1]['reviewer'] = value
            else:
                forged[field] = value
            envelope = rehash_record({'record': forged, 'sha256': ''})
            with self.subTest(field=field), self.assertRaises(DecisionError):
                replay(envelope)

    def test_schema_three_records_keep_python_json_rules(self):
        record = self.submit()
        approved = self.store.approve(record['id'], 'bob', 'checked')
        legacy = as_schema3(approved)
        envelope = rehash_record({'record': legacy, 'sha256': ''})
        self.assertEqual(envelope['sha256'], hashlib.sha256(python_json_v1(legacy)).hexdigest())
        self.assertEqual(replay(envelope)['status'], 'READY')
        with sqlite3.connect(self.db) as connection:
            connection.execute('UPDATE decisions SET record = ? WHERE id = ?',
                               (json.dumps(legacy), record['id']))
        stored = self.store.get(record['id'])
        self.assertEqual(stored['schema_version'], 3)
        self.assertEqual(export_record(stored), envelope)
        cancelled = self.store.cancel(record['id'], 'bob', 'withdraw')
        self.assertEqual(cancelled['schema_version'], 3)
        self.assertEqual(replay(export_record(cancelled))['status'], 'CANCELLED')
        self.assertEqual(self.call('approve', record['id'], '--reviewer', 'alice')[0], 1)
        forged = deepcopy(legacy)
        forged['review']['reviewer'] = 'alice'
        with self.assertRaises(DecisionError):
            replay(rehash_record({'record': forged, 'sha256': ''}))

    def submit_whole_probability(self):
        policy = RoutingPolicy('p-one', ('support', 'legal'), ('legal',), ('alice', 'bob'), 1.0)
        return self.store.submit(Recommendation('reassign_ticket', 't1', 'legal', 1.0, 'fixture', 'q1'),
                                 policy, proposed_by='alice')

    def test_canonical_forms_differ_where_floats_are_whole_numbers(self):
        record = self.submit_whole_probability()
        self.assertEqual(record['policy']['min_probability'], 1.0)
        self.assertNotEqual(canonicalize(record['policy']), python_json_v1(record['policy']))
        self.assertEqual(record['policy_sha256'], hashlib.sha256(canonicalize(record['policy'])).hexdigest())
        envelope = export_record(record)
        self.assertEqual(envelope['sha256'], hashlib.sha256(canonicalize(record)).hexdigest())
        self.assertNotEqual(envelope['sha256'], hashlib.sha256(python_json_v1(record)).hexdigest())
        wrong_form = deepcopy(envelope)
        wrong_form['sha256'] = hashlib.sha256(python_json_v1(record)).hexdigest()
        with self.assertRaises(DecisionError):
            replay(wrong_form)
        legacy = as_schema3(record)
        self.assertNotEqual(legacy['policy_sha256'], record['policy_sha256'])
        self.assertTrue(replay(rehash_record({'record': legacy, 'sha256': ''}))['valid'])
        legacy['policy_sha256'] = record['policy_sha256']
        with self.assertRaises(DecisionError):
            replay(rehash_record({'record': legacy, 'sha256': ''}))

    def test_schema_four_replay_rejects_duplicate_keys_and_non_finite_numbers(self):
        record = self.submit()
        envelope = export_record(record)
        text = json.dumps(envelope)
        duplicate = text.replace('"status": "PENDING_REVIEW"', '"status": "READY", "status": "PENDING_REVIEW"', 1)
        self.assertNotEqual(duplicate, text)
        path = self.root / 'duplicate.json'
        path.write_text(duplicate, encoding='utf-8')
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['replay', '--record', str(path)]), 2)
        self.assertIn('duplicate', error.getvalue())
        with sqlite3.connect(self.db) as connection:
            connection.execute('UPDATE decisions SET record = ? WHERE id = ?',
                               (self.duplicate_status(record), record['id']))
        with self.assertRaisesRegex(DecisionError, 'duplicate'):
            self.store.get(record['id'])
        nan = text.replace('"probability": 0.95', '"probability": NaN', 1)
        self.assertNotEqual(nan, text)
        path.write_text(nan, encoding='utf-8')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['replay', '--record', str(path)]), 2)

    def test_json_beyond_the_parser_limits_is_invalid_input_not_a_traceback(self):
        text = json.dumps(export_record(self.submit()))
        oversized = text.replace('"revision": 0', '"revision": ' + '1' * 5000, 1)
        nested = text.replace('"review": null', '"review": ' + '[' * 100000 + ']' * 100000, 1)
        for name, edited in (('oversized', oversized), ('nested', nested)):
            self.assertNotEqual(edited, text)
            path = self.root / f'{name}.json'
            path.write_text(edited, encoding='utf-8')
            for command, argv in (('replay', ['replay', '--record', str(path)]),
                                  ('replay-evaluation', ['replay-evaluation', '--record', str(path)]),
                                  ('submit', ['--db', str(self.db), 'submit', '--proposal', str(path),
                                              '--policy', str(path), '--proposed-by', 'alice'])):
                with self.subTest(name=name, command=command):
                    with contextlib.redirect_stdout(io.StringIO()) as out, \
                            contextlib.redirect_stderr(io.StringIO()) as error:
                        self.assertEqual(main(argv), 2)
                    self.assertEqual(out.getvalue(), '')
                    self.assertTrue(error.getvalue().startswith('decision-control: '))

    def test_a_signature_envelope_beyond_the_parser_limits_is_a_malformed_signature(self):
        key = self.root / 'signing.key'
        record = self.root / 'record.json'
        self.assertEqual(self.call('keygen', str(key))[0], 0)
        self.assertEqual(self.call('export', self.submit()['id'], '--out', str(record))[0], 0)
        Path(str(record) + '.dsse.json').write_text('{"payloadType": ' + '[' * 100000 + ']' * 100000 + '}',
                                                    encoding='utf-8')
        code, output, error = self.call('replay', '--record', str(record), '--require-signature', '--key', str(key))
        self.assertEqual((code, output), (1, None))
        self.assertIn('signature', error)

    def duplicate_status(self, record):
        text = json.dumps(record, separators=(',', ':'))
        needle = '"status":"PENDING_REVIEW"'
        self.assertIn(needle, text)
        return text.replace(needle, '"status":"READY",' + needle, 1)

    def test_schema_three_replay_still_accepts_duplicate_keys_last_wins(self):
        record = as_schema3(self.store.approve(self.submit()['id'], 'bob', 'checked'))
        envelope = rehash_record({'record': record, 'sha256': ''})
        text = json.dumps(envelope).replace('"status": "READY"', '"status": "PENDING_REVIEW", "status": "READY"', 1)
        self.assertNotEqual(text, json.dumps(envelope))
        path = self.root / 'legacy-duplicate.json'
        path.write_text(text, encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['replay', '--record', str(path)]), 0)

    def test_schema_five_cancellation_retains_schema_and_blocks_proposer_after_approval(self):
        record = self.submit()
        approved = self.store.approve(record['id'], 'bob', 'checked')
        self.assertEqual(self.call('cancel', record['id'], '--reviewer', 'alice', '--note', 'stop')[0], 1)
        self.assertEqual(self.store.get(record['id']), approved)
        cancelled = self.store.cancel(record['id'], 'bob', 'stop')
        self.assertEqual(cancelled['schema_version'], 5)
        self.assertEqual(cancelled['policy_sha256'], record['policy_sha256'])
        self.assertEqual(replay(export_record(cancelled))['status'], 'CANCELLED')

    def test_cli_self_review_is_exit_one(self):
        for action in ('approve', 'reject', 'cancel'):
            record = self.submit()
            self.assertEqual(self.call(action, record['id'], '--reviewer', 'alice', '--note', 'checked')[0], 1)
            self.assertEqual(self.store.get(record['id']), record)

    def test_legacy_unversioned_store_is_opened_and_stamped(self):
        record = self.submit()
        self.store.close()
        with sqlite3.connect(self.db) as connection:
            connection.execute('PRAGMA user_version = 0')
        with TicketStore(self.db) as reopened:
            self.assertEqual(reopened.get(record['id']), record)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_replay_checksum_mismatch_exits_one_and_malformed_input_exits_two(self):
        record = self.submit()
        envelope = export_record(record)
        envelope['record']['proposed_by'] = 'changed'
        out = self.root / 'changed.json'
        out.write_text(json.dumps(envelope), encoding='utf-8')
        self.assertEqual(self.call('replay', '--record', str(out))[0], 1)
        out.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.call('replay', '--record', str(out))[0], 2)

    def test_replay_evaluation_mismatch_exits_one(self):
        source = Path(__file__).resolve().parents[1] / 'examples'
        report = evaluate_cases(load_cases(source / 'evaluation-cases.jsonl'),
                                RoutingPolicy.from_dict(json.loads((source / 'policy.json').read_text())))
        envelope = write_evaluation(report, self.root / 'evaluation')
        envelope['report']['metrics']['unsafe_auto_allow_rate']['value'] = 0.123
        out = self.root / 'changed-evaluation.json'
        out.write_text(json.dumps(envelope), encoding='utf-8')
        self.assertEqual(self.call('replay-evaluation', '--record', str(out))[0], 1)

    def test_pending_skips_invalid_utf8_blob_and_still_lists_valid_records(self):
        bad, good = self.submit(), self.submit()
        with sqlite3.connect(self.db) as connection:
            connection.execute('UPDATE decisions SET record = ? WHERE id = ?', (b'\xff', bad['id']))
        pending = self.store.pending()
        self.assertEqual([record['id'] for record in pending], [good['id']])
        self.assertEqual(pending.skipped[0]['id'], bad['id'])
        self.assertEqual(self.call('pending')[0], 1)
