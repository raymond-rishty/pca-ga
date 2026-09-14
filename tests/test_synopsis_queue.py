import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('queue_module', Path(__file__).resolve().parents[1] / 'scripts/synopsis_queue.py')
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.data = {'reserve_percent': 20, 'max_snapshot_age_seconds': 300,
                     'max_account_percentage_points': 10, 'runs': []}
        self.snapshot = {'captured_at': self.now.isoformat(), 'rateLimitsByLimitId': {'codex': {
            'primary': {'usedPercent': 10, 'resetsAt': self.now.timestamp() + 900},
            'secondary': {'usedPercent': 45, 'resetsAt': self.now.timestamp() + 9000}}}}

    def test_ready(self):
        self.assertEqual(q.gate(self.data, self.snapshot, self.now), 'ready')

    def test_reserve(self):
        self.snapshot['rateLimitsByLimitId']['codex']['primary']['usedPercent'] = 88
        self.assertIn('reserve', q.gate(self.data, self.snapshot, self.now))

    def test_weekly_reserve(self):
        self.snapshot['rateLimitsByLimitId']['codex']['secondary']['usedPercent'] = 80
        self.assertIn('secondary', q.gate(self.data, self.snapshot, self.now))

    def test_missing_usage_fails_closed(self):
        self.assertIn('paused', q.gate(self.data, {}, self.now))
        self.snapshot['rateLimitsByLimitId']['codex']['primary']['usedPercent'] = None
        self.assertIn('paused', q.gate(self.data, self.snapshot, self.now))

    def test_stale(self):
        self.assertIn('stale', q.gate(self.data, self.snapshot, self.now + timedelta(seconds=301)))

    def test_reset_requires_refresh(self):
        self.snapshot['rateLimitsByLimitId']['codex']['primary']['resetsAt'] = self.now.timestamp() - 1
        self.assertIn('refresh', q.gate(self.data, self.snapshot, self.now))

    def test_one_worker(self):
        self.data['runs'] = [{'before': self.snapshot}]
        self.assertIn('unfinished', q.gate(self.data, self.snapshot, self.now))

    def test_campaign_budget(self):
        import copy
        after = copy.deepcopy(self.snapshot)
        after['rateLimitsByLimitId']['codex']['primary']['usedPercent'] = 20
        self.data['runs'] = [{'before': self.snapshot, 'after': after}]
        self.assertIn('budget', q.gate(self.data, after, self.now))

    def test_reset_not_negative_cost(self):
        import copy
        after = copy.deepcopy(self.snapshot)
        after['rateLimitsByLimitId']['codex']['primary']['resetsAt'] += 300
        self.data['runs'] = [{'before': self.snapshot, 'after': after}]
        self.assertIn('manual budget review', q.gate(self.data, after, self.now))

    def test_path_boundary(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaises(ValueError):
                q.inside(Path(name), '../escape')

    def test_lock(self):
        with tempfile.TemporaryDirectory() as name:
            with q.locked(Path(name)):
                with self.assertRaises(FileExistsError):
                    with q.locked(Path(name)):
                        pass
            self.assertFalse((Path(name) / '.queue.lock').exists())

    def test_reuses_legacy_sol_but_not_terra(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            base = root / 'index/synopsis_workflow/bakeoff'
            q.ledger.save(base / 'runs.json', {'arms': [
                {'model': 'gpt-5.6-sol', 'output_directory': 'index/synopsis_workflow/bakeoff/sol'},
                {'model': 'gpt-5.6-terra', 'output_directory': 'index/synopsis_workflow/bakeoff/terra'}]})
            q.ledger.save(base / 'sol/2000-01.json', {
                'case_id': '2000-01', 'summary': 'Existing draft.', 'dispositions': ['denied']})
            q.ledger.save(base / 'terra/2000-02.json', {
                'case_id': '2000-02', 'summary': 'Other model.'})
            found = q.existing_sol(root)
            self.assertEqual(set(found), {'2000-01'})
            self.assertFalse(found['2000-01'][0]['source_hashes_match'])
            self.assertFalse(found['2000-01'][0]['publication_approved'])

    def test_claim_finish_and_retry_only_missing(self):
        import json
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            folder = root / 'campaign'
            folder.mkdir()
            (root / 'index').mkdir()
            (root / 'index/judicial_cases.jsonl').write_text(
                json.dumps({'case_id': '2000-01'}) + '\n', encoding='utf-8')
            (root / 'source.md').write_text('source', encoding='utf-8')
            row = {'case_id': '2000-01'}
            data = dict(self.data, reference_hashes={}, packet_hashes={},
                        model='gpt-5.6-sol', reasoning_effort='medium',
                        batches=[['2000-01']], cases=[{
                            'case_id': '2000-01', 'state': 'queued', 'path': 'source.md',
                            'sha256': q.ledger.file_hash(root / 'source.md'),
                            'catalog_hash': q.ledger.digest(row)}])
            q.ledger.save(folder / 'queue.json', data)
            self.assertEqual(q.claim(root, folder, self.snapshot)['status'], 'claimed')
            self.assertIn('unfinished', q.claim(root, folder, self.snapshot)['status'])
            result = q.finish(root, folder, self.snapshot)
            self.assertEqual(result['cases']['2000-01'], 'queued')
            (root / 'source.md').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Stale source'):
                q.claim(root, folder, self.snapshot)


if __name__ == '__main__':
    unittest.main()
