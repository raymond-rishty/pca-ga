from pathlib import Path
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import synopsis_review_server as review


class SynopsisReviewServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.decisions = Path(self.temporary.name) / 'decisions.json'
        self.store = review.ReviewStore(
            review.ROOT, review.DEFAULT_REGISTRY, self.decisions)

    def tearDown(self):
        self.temporary.cleanup()

    def test_loads_all_registry_candidates_and_source(self):
        index = self.store.index()
        expected = len(self.store.entries)
        self.assertEqual(len(index['items']), expected)
        self.assertEqual(index['counts']['unreviewed'], expected)
        case = self.store.case('1976-01')
        self.assertEqual(case['candidate']['case_id'], '1976-01')
        self.assertTrue(case['source']['text'])

    def test_records_and_reverses_audited_decision(self):
        result = self.store.save_decision('1976-01', {
            'decision': 'approved', 'reviewer': 'tester', 'notes': ''})
        self.assertEqual(result['decision']['decision'], 'approved')
        self.assertTrue(result['decision']['acceptability_pass'])
        self.assertFalse(result['decision']['publication_authorized'])
        self.assertEqual(self.store.index()['counts']['approved'], 1)
        self.store.save_decision('1976-01', {
            'decision': 'unreviewed', 'reviewer': '', 'notes': ''})
        self.assertEqual(
            self.store.index()['counts']['unreviewed'], len(self.store.entries))

    def test_rejects_decision_without_reviewer(self):
        with self.assertRaisesRegex(ValueError, 'Reviewer'):
            self.store.save_decision('1976-01', {
                'decision': 'approved', 'reviewer': '', 'notes': ''})

    def test_correction_can_still_pass_statistical_threshold(self):
        case = self.store.case('1976-01')['candidate']
        result = self.store.save_decision('1976-01', {
            'decision': 'corrected',
            'reviewer': 'tester',
            'notes': 'Metadata-only repair.',
            'acceptability_pass': True,
            'summary': case['summary'],
            'matter_type': case['matter_type'],
            'final_dispositions': case['final_dispositions'],
        })
        self.assertTrue(result['decision']['acceptability_pass'])


if __name__ == '__main__':
    unittest.main()
