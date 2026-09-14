import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.agents/skills/pca-ga-case-synopses/scripts/batch_synopses.py'
spec = importlib.util.spec_from_file_location('synopsis_batch', SCRIPT)
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class SynopsisBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'docs').mkdir()
        (self.root / batch.BENCHMARK).write_text('benchmark', encoding='utf-8')
        (self.root / 'source.md').write_text('decision', encoding='utf-8')
        (self.root / 'index').mkdir()
        batch.save(self.root / 'index/judicial_case_editorial_overrides.json',
                   {'2000-01': {'topic_tags': ['preserve me']}})
        self.rows = {'2000-01': {'case_id': '2000-01', 'roster_id': '2000-01', 'case_page': 'shared'}}
        self.ledger = {'schema_version': 1, 'cases': {}}
        batch.sync(self.ledger, self.rows)

    def action(self, action, **payload):
        batch.record(self.root, self.ledger, self.rows, '2000-01', action,
                     dict(reviewer='editor', notes='actual evidence notes', **payload))

    def triage(self):
        self.action('triage', identity='docket verified', source_limits='complete',
                    sources=[{'path': 'source.md', 'locator': 'judgment', 'supports': 'relief'}])

    def draft(self):
        self.triage()
        self.action('draft', summary='A supported synopsis.', benchmark_examples='C01')

    def verify(self):
        self.action('verify', claim_checks='each sentence checked', qualifications='mixed relief checked',
                    pass_kind='separate_pass_same_reviewer', scores=dict.fromkeys(batch.DIMENSIONS, 2), passed=True)

    def test_full_handoff_preserves_overrides_and_does_not_publish(self):
        self.draft()
        self.verify()
        self.action('approve', authorization='user-approved pilot')
        packet = batch.packet(self.root, self.ledger, self.rows, ['2000-01'])
        self.assertEqual(packet['changes']['2000-01']['after']['topic_tags'], ['preserve me'])
        self.assertNotIn('summary', batch.read(self.root / 'index/judicial_case_editorial_overrides.json')['2000-01'])

    def test_no_verification_or_approval_shortcuts(self):
        with self.assertRaises(ValueError):
            self.verify()
        self.draft()
        with self.assertRaises(ValueError):
            self.action('approve', authorization='user')
        with self.assertRaises(ValueError):
            batch.packet(self.root, self.ledger, self.rows, ['2000-01'])

    def test_fidelity_veto(self):
        self.draft()
        scores = dict.fromkeys(batch.DIMENSIONS, 2)
        scores['fidelity'] = 1
        with self.assertRaises(ValueError):
            self.action('verify', claim_checks='checked', qualifications='checked',
                        pass_kind='separate_pass_same_reviewer', scores=scores, passed=True)

    def test_source_change_requires_retriage(self):
        self.draft()
        (self.root / 'source.md').write_text('corrected decision', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.verify()
        self.triage()
        self.assertNotIn('draft', self.ledger['cases']['2000-01'])

    def test_redraft_invalidates_review(self):
        self.draft()
        self.verify()
        self.action('draft', summary='Revised summary.', benchmark_examples='C02')
        self.assertNotIn('verification', self.ledger['cases']['2000-01'])

    def test_sync_preserves_work_and_separate_shared_dockets(self):
        self.draft()
        self.rows['roster:era6'] = {'case_id': None, 'roster_id': 'era6', 'case_page': 'shared'}
        batch.sync(self.ledger, self.rows)
        self.assertEqual(len(self.ledger['cases']), 2)
        self.assertEqual(self.ledger['cases']['2000-01']['stage'], 'drafted')
        self.assertIsNone(self.ledger['cases']['roster:era6']['case_id'])

    def test_catalog_and_benchmark_changes_are_stale(self):
        self.triage()
        self.rows['2000-01']['title'] = 'corrected'
        self.assertFalse(batch.fresh(self.root, self.ledger['cases']['2000-01'], self.rows))
        self.triage()
        (self.root / batch.BENCHMARK).write_text('new benchmark', encoding='utf-8')
        self.assertFalse(batch.fresh(self.root, self.ledger['cases']['2000-01'], self.rows))

    def test_repair_blocks_drafting_and_history_survives(self):
        self.draft()
        self.action('repair')
        with self.assertRaises(ValueError):
            self.action('draft', summary='guess', benchmark_examples='C01')
        self.triage()
        self.assertTrue(any(e['action'] == 'repair' for e in self.ledger['cases']['2000-01']['history']))

    def test_paths_cannot_escape_repository(self):
        with self.assertRaises(ValueError):
            batch.source_path(self.root, '../outside.md')


if __name__ == '__main__':
    unittest.main()
