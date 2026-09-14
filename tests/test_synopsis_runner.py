import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_synopses as r


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.probe = patch.object(r, 'preflight', return_value={'status': 'passed'}).start()
        self.addCleanup(patch.stopall)

    def test_preflight_failure_never_claims_or_calls_model(self):
        self.probe.side_effect = RuntimeError('sandbox failed')
        with tempfile.TemporaryDirectory() as name, patch.object(r.q, 'claim') as claim:
            with self.assertRaises(RuntimeError):
                r.run(Path(name), Path(name), 'codex', usage_reader=lambda _: self.fail('usage called'),
                      worker=lambda *args: self.fail('model called'))
            claim.assert_not_called()

    def test_command_no_shell_no_bypass(self):
        command = r.command('codex', Path('campaign'), {
            'batch': 2, 'model': 'gpt-5.6-sol', 'reasoning_effort': 'medium'})
        self.assertIn('--ephemeral', command)
        self.assertIn('workspace-write', command)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)
        self.assertEqual(command[-1], '-')
        self.assertEqual(command[command.index('-C') + 1], str(r.q.ROOT))
        self.assertIn('web_search="disabled"', command)
        self.assertIn('apps', command)

    def test_usage_not_guessed(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'events.jsonl'
            path.write_text('\n'.join(map(json.dumps, [
                {'type': 'thread.started', 'thread_id': 'test'},
                {'type': 'turn.completed', 'usage': {'input_tokens': 12, 'output_tokens': 3}}
            ])), encoding='utf-8')
            result = r.event_metrics(path)
            self.assertEqual(result['tokens']['input_tokens'], 12)
            self.assertTrue(result['turn_completed'])
            self.assertIsNone(result['cost'])
            self.assertIsNone(r.event_metrics(Path(name) / 'missing')['tokens'])

    def test_gate_prevents_dispatch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with patch.object(r.q, 'claim', return_value={'status': 'paused: primary reserve'}), \
                    patch.object(r, 'report', return_value={'counts': {'queued': 5}}):
                def forbidden(*args):
                    self.fail('worker called despite budget gate')
                result = r.run(root, root, 'codex', usage_reader=lambda _: {}, worker=forbidden)
                self.assertIn('paused', result['status'])

    def test_failed_usage_prevents_claim(self):
        with tempfile.TemporaryDirectory() as name:
            with patch.object(r.q, 'claim') as claim:
                def failure(_):
                    raise RuntimeError('offline')
                with self.assertRaises(RuntimeError):
                    r.run(Path(name), Path(name), 'codex', usage_reader=failure)
                claim.assert_not_called()

    def test_automatic_collection_and_stop_on_bad_output(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            r.q.ledger.save(folder / 'queue.json', {
                'runs': [{}], 'cases': [{'case_id': '2000-01', 'state': 'validation_failed'}]})
            assignment = {'status': 'claimed', 'case_ids': ['2000-01'], 'batch': 1}
            with patch.object(r.q, 'claim', return_value=assignment) as claim, \
                    patch.object(r.q, 'finish') as finish, \
                    patch.object(r, 'report', return_value={'counts': {'validation_failed': 1}}):
                result = r.run(folder, folder, 'codex', max_batches=3,
                    usage_reader=lambda _: {'captured_at': 'actual test fixture'},
                    worker=lambda *args: {'worker_exit_code': 0, 'turn_completed': True})
                self.assertIn('needs attention', result['status'])
                self.assertEqual(claim.call_count, 1)
                finish.assert_called_once()
                self.assertTrue((folder / 'attempts/run-001/after.json').exists())

    def test_ambiguous_worker_not_requeued(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            r.q.ledger.save(folder / 'queue.json', {'runs': [{}]})
            with patch.object(r.q, 'claim', return_value={
                    'status': 'claimed', 'case_ids': ['2000-01'], 'batch': 1}), \
                    patch.object(r.q, 'finish') as finish:
                def failure(*args):
                    raise RuntimeError('worker interrupted')
                with self.assertRaises(RuntimeError):
                    r.run(folder, folder, 'codex', usage_reader=lambda _: {}, worker=failure)
                finish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
