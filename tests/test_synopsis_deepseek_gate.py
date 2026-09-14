from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import synopsis_deepseek_gate as gate


def candidate(**changes):
    value = {
        'matter_type': 'complaint',
        'final_dispositions': ['denied'],
        'repair_needed': False,
        'scores': {
            'concrete_dispute': 2,
            'decision': 2,
            'decisive_reason': 2,
            'distinctive_value': 2,
            'fidelity': 2,
            'economy': 2,
        },
    }
    value.update(changes)
    return value


class SynopsisDeepSeekGateTests(unittest.TestCase):
    def test_accepts_descriptive_benchmark_citation_with_supplied_id(self):
        value = {
            'case_id': '2001-25',
            'title': 'A sufficiently descriptive title',
            'matter_type': 'complaint',
            'final_dispositions': ['not_sustained'],
            'disposition_detail': 'The complaint was not sustained.',
            'first_summary': 'A sufficiently descriptive first synopsis draft.',
            'summary': 'A sufficiently descriptive corrected synopsis draft.',
            'sources': [{
                'path': 'cases/ga30_2002__2001-25.md',
                'sha256': 'a' * 64,
                'locator': 'lines 1-20',
                'supports': 'The material decision and reasons.',
            }],
            'evidence_notes': {
                'identity_and_adoption': 'Identity evidence.',
                'dispute': 'Dispute evidence.',
                'outcomes_and_reasons': 'Outcome evidence.',
                'qualifications': 'Qualification evidence.',
                'incorporated_decisions': 'No incorporated decision.',
            },
            'source_limits': 'No material source limitation.',
            'benchmark_examples': [
                'C01 (Allin): preserve material results.',
                'Sparse-record synopses should remain short.',
            ],
            'scores': candidate()['scores'],
            'score_reasons': {
                'concrete_dispute': 'Reason.',
                'decision': 'Reason.',
                'decisive_reason': 'Reason.',
                'distinctive_value': 'Reason.',
                'fidelity': 'Reason.',
                'economy': 'Reason.',
            },
            'verification_notes': 'Rechecked the operative judgment.',
            'repair_needed': False,
            'repair_notes': '',
        }
        entry = {
            'case_id': '2001-25',
            'source': 'cases/ga30_2002__2001-25.md',
            'source_sha256': 'a' * 64,
            'benchmark_examples': ['C01', 'C20'],
        }
        gate.validate_candidate(value, entry)

    def test_accepts_simple_high_fidelity_candidate(self):
        reasons = gate.candidate_reasons(
            candidate(), {'source': 'cases/ga49_2022__2020-06.md'})
        self.assertEqual(reasons, [])

    def test_rejects_mixed_and_shared_source_candidate(self):
        reasons = gate.candidate_reasons(candidate(
            final_dispositions=['partially_sustained', 'annulled', 'remanded']), {
                'source': 'cases/ga51_2024__2023-06_2023-08.md'})
        self.assertIn('partially_sustained', reasons)
        self.assertIn('more_than_two_dispositions', reasons)
        self.assertIn('shared_case_source', reasons)

    def test_rejects_repair_other_low_score_and_low_fidelity(self):
        value = candidate(
            matter_type='other', repair_needed=True,
            scores={
                'concrete_dispute': 1,
                'decision': 2,
                'decisive_reason': 1,
                'distinctive_value': 1,
                'fidelity': 1,
                'economy': 2,
            })
        reasons = gate.candidate_reasons(
            value, {'source': 'cases/ga49_2022__2021-07.md'})
        self.assertIn('repair_needed', reasons)
        self.assertIn('fidelity_below_2', reasons)
        self.assertIn('score_below_10', reasons)
        self.assertIn('other_taxonomy', reasons)


if __name__ == '__main__':
    unittest.main()
