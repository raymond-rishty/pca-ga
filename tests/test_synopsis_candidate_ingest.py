from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import synopsis_candidate_ingest as intake


class SynopsisCandidateIngestTests(unittest.TestCase):
    def test_workspace_registry_has_expected_provider_aware_coverage(self):
        report = intake.build_registry(intake.ROOT)
        counts = report['counts']
        self.assertEqual(counts['deepseek_gate_cases'], 225)
        self.assertEqual(counts['sol_cases'], 221)
        self.assertEqual(counts['selected_cases'], 446)
        self.assertEqual(counts['provider_overlaps'], 0)
        self.assertEqual(counts['conflicts'], 0)
        self.assertFalse(report['publication_authorized'])
        self.assertTrue(all(
            item['selected']['provider'] in {'openai', 'deepseek'}
            and item['status'] == 'awaiting_source_audit'
            and not item['publication_approved']
            for item in report['candidates']))


if __name__ == '__main__':
    unittest.main()
