import http.client
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from jevdecision import APIError, Choice, DecisionModel, JevBackend, Noul, QuestionError, ResponseError, Score, __version__
from jevdecision.answers import parse_answers
from jevdecision.backends import urllib_transport
from jevdecision.evaluation import Case, evaluate, main
N = Noul('n', 'yes?')
C = Choice('c', 'which?', {'a': 'first', 'b': 'second'})
S = Score('s', 'how?', ('low', 'high'))

class ReleaseTests(unittest.TestCase):
    def test_refusal_retains_siblings_and_never_authorizes(self):
        raw = {'answers': {'n': {'type': 'refusal'}, 'c': {'choice': 'a'}, 's': {'score': 1}}}
        answers = JevBackend().parse_response(raw, [N, C, S]).answers
        self.assertEqual(answers['n'].type, 'refusal')
        self.assertEqual(answers['c'].choice, 'a')
        for q in (N, C):
            model = DecisionModel(JevBackend(api_key='k', transport=lambda *a: {'answers': {q.name: {'type': 'refusal'}}}))
            if q is N:
                self.assertFalse(model.gate('state', N, threshold=0))
            else:
                self.assertEqual(model.route('state', C, fallback='human'), 'human')
        report = evaluate([N, C, S], [Case('1', 'state', {'n': True, 'c': 'a', 's': 1})], {'1': answers}, [])
        metrics = report['questions']['n']
        self.assertEqual((metrics['n'], metrics['accuracy'], metrics['refusals'], metrics['refusal_rate']), (1, 0, 1, 1))
        self.assertIsNone(metrics['brier'])

    def test_score_missing_probabilities_remain_unknown(self):
        for fields, expected in (({}, (None, None)), ({'probabilities': {}}, (None, None)), ({'probabilities': {'0': .2}}, (.2, None))):
            answer = parse_answers({'s': {'score': 1, **fields}}, [S])['s']
            self.assertEqual(answer.probabilities, expected)
            self.assertIsNone(answer.probability)
            report = evaluate([S], [Case('1', 'state', {'s': 1})], {'1': {'s': answer}}, [])
            self.assertIsNone(report['questions']['s']['brier'])
        with self.assertRaises(ResponseError):
            parse_answers({'s': {'probabilities': {'0': .2}}}, [S])

    def test_probability_ranges_and_distribution_totals(self):
        for value in (float('nan'), float('inf'), -.0000001, 1.0000001):
            with self.subTest(value=value), self.assertRaises(ResponseError):
                parse_answers({'n': {'noul': value}}, [N])
        for q, entry in ((C, {'choice': 'a', 'probabilities': {'a': .2, 'b': .2}}), (S, {'score': 1, 'probabilities': [.2, .2]})):
            with self.subTest(q=q), self.assertRaises(ResponseError):
                parse_answers({q.name: entry}, [q])
        self.assertEqual(parse_answers({'c': {'choice': 'a', 'probabilities': {'a': .5, 'b': .501}}}, [C])['c'].choice, 'a')

    def test_http_protocol_errors_and_408_are_retryable(self):
        for error in (http.client.IncompleteRead(b'x', 2), http.client.RemoteDisconnected('closed')):
            with mock.patch('urllib.request.OpenerDirector.open', side_effect=error), self.assertRaises(APIError) as raised:
                urllib_transport('https://example.com', {}, b'{}', 1)
            self.assertIsNone(raised.exception.status)
            self.assertTrue(raised.exception.retryable)
        self.assertTrue(APIError('timeout', 408).retryable)

    def test_insecure_remote_base_url_is_rejected(self):
        for url in ('http://example.com', 'ftp://127.0.0.1', 'https://user:secret@example.com'):
            with self.subTest(url=url), self.assertRaises(QuestionError):
                JevBackend(api_key='secret', base_url=url)
        for url in ('http://127.0.0.1:1234', 'http://[::1]:1234', 'http://localhost:1234'):
            JevBackend(api_key='secret', base_url=url)

    def test_path_cannot_change_the_host(self):
        # Without a leading '/', the path extends the host: http://localhost + .example.com/v1 is a remote URL.
        for base, path in (('http://localhost', '.example.com/v1'), ('https://api.typesafe.ai', '@example.com/v1'),
                           ('https://api.typesafe.ai', 'v1/systemone')):
            with self.subTest(base=base, path=path), self.assertRaises(QuestionError):
                JevBackend(api_key='secret', base_url=base, path=path)
        self.assertEqual(JevBackend(api_key='secret', path='/v1/decisions').url, 'https://api.typesafe.ai/v1/decisions')

    def test_authenticated_post_does_not_follow_redirects(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                calls.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/leak')
                self.end_headers()
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(APIError) as raised:
                urllib_transport(f'http://127.0.0.1:{server.server_port}/start', {'Authorization': 'Bearer secret'}, b'{}', 1)
            self.assertEqual(raised.exception.status, 302)
            self.assertFalse(raised.exception.retryable)
            self.assertEqual(calls, ['/start'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_live_progress_survives_crash_and_auth_stops_early(self):
        for failure in (KeyboardInterrupt(), APIError('denied', 401), APIError('denied', 403)):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'q.json').write_text(json.dumps({'n': {'type': 'noul', 'instructions': 'yes?'}}))
                (root/'cases.jsonl').write_text(''.join(json.dumps({'id': str(i), 'state': 'state', 'labels': {'n': True}})+'\n' for i in range(3)))
                count = []
                def transport(*args):
                    count.append(1)
                    if len(count) > 1:
                        progress = list(root.glob('out*/responses.jsonl')) + list(root.glob('.out*/responses.jsonl'))
                        self.assertTrue(progress, 'completed response must already be on disk')
                        self.assertEqual(len(progress[0].read_text().splitlines()), 1)
                        raise failure
                    return {'answers': {'n': {'noul': .9}}}
                backend = JevBackend(api_key='k', transport=transport)
                args = ['--questions', str(root/'q.json'), '--cases', str(root/'cases.jsonl'), '--out', str(root/'out')]
                with mock.patch('jevdecision.evaluation.create_backend', return_value=backend):
                    if isinstance(failure, KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt): main(args)
                    else: self.assertEqual(main(args), 2)
                self.assertEqual(len(count), 2)
                self.assertFalse((root/'out').exists())
                self.assertTrue(list(root.glob('.out*/cases.jsonl')))

    def test_partial_positional_score_distribution_stays_unknown(self):
        answer = parse_answers({'s': {'score': 1, 'probabilities': [.2]}}, [S])['s']
        self.assertEqual(answer.probabilities, (.2, None))
        self.assertIsNone(answer.probability)

    def test_invalid_live_response_is_saved_for_replay(self):
        from jevdecision.evaluation import run_live
        backend = JevBackend(api_key='k', transport=lambda *a: {'answers': {'n': {'noul': 4}}})
        answers, raw, errors = run_live(backend, [N], [Case('1', 'state', {'n': True})])
        self.assertEqual(raw['1'], {'answers': {'n': {'noul': 4}}})
        self.assertEqual(len(errors), 1)
        self.assertEqual(answers, {})

    def test_decision_cli_refusal_exit_and_record(self):
        from jevdecision.__main__ import main as decide_main
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'q.json'
            path.write_text(json.dumps({'n': {'type': 'noul', 'instructions': 'yes?'}}))
            backend = JevBackend(api_key='k', transport=lambda *a: {'answers': {'n': {'type': 'refusal'}}})
            output = io.StringIO()
            with mock.patch('jevdecision.__main__.create_backend', return_value=backend), redirect_stdout(output):
                self.assertEqual(decide_main(['--questions', str(path), '--state', 'state']), 1)
            record = json.loads(output.getvalue())
            self.assertEqual(record['schema_version'], 2)
            self.assertEqual(record['answers']['n']['type'], 'refusal')
            self.assertEqual(record['questions'], {'n': {'type': 'noul', 'instructions': 'yes?'}})
            self.assertEqual(record['produced_by'], {'name': 'jevdecision', 'version': __version__})
            self.assertEqual(record['answers']['n']['type'], 'refusal')

    def test_failed_output_publish_does_not_block_rerun(self):
        from jevdecision.evaluation import write_records
        report = {'status': 'UNGATED', 'jevdecision_version': '0.1.0', 'backend': 'jev', 'model': 'fixture',
                  'source': 'replay', 'cases': 0, 'answered': 0, 'errors': [], 'error_rate': 0,
                  'questions': {}, 'requirements': []}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'out'
            with mock.patch('jevdecision.evaluation.render_markdown', side_effect=OSError('disk full')):
                with self.assertRaises(OSError): write_records(report, {}, out, [])
            self.assertFalse(out.exists())
            write_records(report, {}, out, [])
            self.assertTrue((out/'evaluation.json').exists())

    def test_live_finalization_preserves_durable_jsonl(self):
        import jevdecision.evaluation as evaluation
        from contextlib import redirect_stdout, redirect_stderr
        import io
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'q.json').write_text(json.dumps({'n': {'type': 'noul', 'instructions': 'yes?'}}))
            (root/'cases.jsonl').write_text(json.dumps({'id': '1', 'state': 'state', 'labels': {'n': True}})+'\n')
            backend = JevBackend(api_key='k', transport=lambda *a: {'answers': {'n': {'noul': .9}}})
            original = evaluation._write_jsonl
            def guarded_write(path, rows):
                self.assertFalse(path.exists(), 'durable progress must not be truncated during finalization')
                original(path, rows)
            with mock.patch('jevdecision.evaluation.create_backend', return_value=backend), mock.patch('jevdecision.evaluation._write_jsonl', side_effect=guarded_write), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--questions', str(root/'q.json'), '--cases', str(root/'cases.jsonl'), '--out', str(root/'out')]), 3)

    def test_evaluation_output_io_error_exits_2_without_final_directory(self):
        from contextlib import redirect_stderr
        import io
        examples = Path(__file__).resolve().parents[1]/'examples'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'out'
            args = ['--questions', str(examples/'support-ticket.json'), '--cases', str(examples/'support-ticket-cases.jsonl'), '--responses', str(examples/'support-ticket-responses.jsonl'), '--out', str(out)]
            with mock.patch('jevdecision.evaluation.render_markdown', side_effect=OSError('disk full')), redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
            self.assertFalse(out.exists())

    def test_http_error_body_protocol_failure_is_retryable(self):
        import urllib.error
        error = urllib.error.HTTPError('https://example.com', 503, 'unavailable', {}, None)
        with mock.patch('urllib.request.OpenerDirector.open', side_effect=error), mock.patch.object(error, 'read', side_effect=http.client.IncompleteRead(b'x', 2)):
            with self.assertRaises(APIError) as raised:
                urllib_transport('https://example.com', {}, b'{}', 1)
        self.assertIsNone(raised.exception.status)
        self.assertTrue(raised.exception.retryable)

    def test_unknown_score_record_round_trips(self):
        answer = parse_answers({'s': {'score': 1}}, [S])['s']
        record = json.loads(json.dumps({'s': answer.to_dict()}))
        replayed = parse_answers(record, [S])['s']
        self.assertEqual(replayed, answer)

    def test_openai_refusal_and_mixed_denominators(self):
        from jevdecision import OpenAIDecisionsBackend
        from jevdecision.evaluation import case_results
        backend = OpenAIDecisionsBackend()
        refused = backend.parse_response({'answers': [{'name': q.name, 'type': 'refusal'} for q in (N, C, S)]}, [N, C, S]).answers
        accepted = parse_answers({'n': {'noul': .9}, 'c': {'choice': 'a', 'probabilities': {'a': .8, 'b': .2}}, 's': {'score': 1, 'probabilities': [.2, .8]}}, [N, C, S])
        cases = [Case(str(i), 'state', {'n': True, 'c': 'a', 's': 1}) for i in (1, 2)]
        answers = {'1': refused, '2': accepted}
        report = evaluate([N, C, S], cases, answers, [], {'questions': {'s': {'brier': {'max': 1}}}})
        self.assertEqual(report['status'], 'FAIL')
        for metric in report['questions'].values():
            self.assertEqual((metric['n'], metric['accuracy'], metric['refusals'], metric['refusal_rate']), (2, .5, 1, .5))
            self.assertIsNone(metric['brier'])
        self.assertTrue(all(not result['correct'] for result in case_results([N, C, S], cases, answers, [])[0]['questions'].values()))
        metrics = evaluate([S], cases[1:], {'2': accepted}, [])['questions']['s']
        self.assertAlmostEqual(metrics['brier'], .08)
        self.assertAlmostEqual(metrics['ece'], .2)

    def test_protocol_failure_and_408_retry_end_to_end(self):
        from io import BytesIO
        for error in (http.client.IncompleteRead(b'x', 2), http.client.RemoteDisconnected('closed'), APIError('timeout', 408)):
            if isinstance(error, APIError):
                transport = mock.Mock(side_effect=[error, {'answers': {'n': {'noul': .9}}}])
                backend = JevBackend(api_key='k', transport=transport, sleep=lambda _: None)
                self.assertEqual(DecisionModel(backend).ask('state', N).probability, .9)
                self.assertEqual(transport.call_count, 2)
            else:
                with mock.patch('urllib.request.OpenerDirector.open', side_effect=[error, BytesIO(b'{"answers":{"n":{"noul":0.9}}}')]) as opened:
                    backend = JevBackend(api_key='k', sleep=lambda _: None)
                    self.assertEqual(DecisionModel(backend).ask('state', N).probability, .9)
                    self.assertEqual(opened.call_count, 2)

    def test_live_null_json_response_is_preserved(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'q.json').write_text(json.dumps({'n': {'type': 'noul', 'instructions': 'yes?'}}))
            (root/'cases.jsonl').write_text(''.join(json.dumps({'id': str(i), 'state': 'state', 'labels': {'n': True}})+'\n' for i in (1, 2)))
            calls = []
            def transport(*args):
                calls.append(1)
                if len(calls) == 2:
                    saved = list(root.glob('.out*/responses.jsonl'))
                    self.assertTrue(saved)
                    self.assertEqual(json.loads(saved[0].read_text()), {'id': '1', 'response': None})
                    return {'answers': {'n': {'noul': .9}}}
                return None
            backend = JevBackend(api_key='k', transport=transport)
            with mock.patch('jevdecision.evaluation.create_backend', return_value=backend), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--questions', str(root/'q.json'), '--cases', str(root/'cases.jsonl'), '--out', str(root/'out')]), 1)
            self.assertEqual(json.loads((root/'out'/'responses.jsonl').read_text().splitlines()[0]), {'id': '1', 'response': None})
