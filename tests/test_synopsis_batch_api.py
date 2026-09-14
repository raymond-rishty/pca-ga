import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import synopsis_batch_api as api


class SynopsisBatchApiTests(unittest.TestCase):
    def test_default_campaign_is_the_conservative_gate_failure_queue(self):
        self.assertEqual(
            api.DEFAULT_CAMPAIGN,
            'index/synopsis_workflow/openai-sol-deepseek-failures-1')

    def test_request_uses_responses_schema_and_explicit_cache(self):
        record = api.request_record(api.ROOT, '2023-05', 'gpt-5.6-sol', 'medium', 12000)
        self.assertEqual(record['url'], '/v1/responses')
        body = record['body']
        self.assertEqual(body['model'], 'gpt-5.6-sol')
        self.assertEqual(body['prompt_cache_options']['mode'], 'explicit')
        developer = body['input'][0]
        self.assertEqual(developer['role'], 'developer')
        self.assertEqual(developer['content'][0]['prompt_cache_breakpoint']['mode'], 'explicit')
        self.assertNotIn('2023-05', developer['content'][0]['text'])
        self.assertIn('2023-05', body['input'][1]['content'][0]['text'])
        self.assertTrue(body['text']['format']['strict'])
        self.assertNotIn('uniqueItems', json.dumps(body['text']['format']['schema']))
        benchmark_items = body['text']['format']['schema']['properties'][
            'benchmark_examples']['items']
        self.assertEqual(benchmark_items['enum'], ['C01', 'C20'])

    def test_normalizes_annotated_supplied_benchmark_ids(self):
        candidate = {'benchmark_examples': [
            'C01 illustrates mixed outcomes.',
            'C02 illustrates issue-specific relief.',
        ]}
        normalized, note = api.normalize_benchmark_examples(candidate, {
            'benchmark_examples': ['C01', 'C02']})
        self.assertEqual(normalized['benchmark_examples'], ['C01', 'C02'])
        self.assertIn('annotated', note['reason'])

    def test_normalization_does_not_hide_an_unprovided_benchmark(self):
        candidate = {'benchmark_examples': ['C01 and A19 were useful.']}
        normalized, note = api.normalize_benchmark_examples(candidate, {
            'benchmark_examples': ['C01', 'C02']})
        self.assertIs(normalized, candidate)
        self.assertIsNone(note)

    def test_normalizes_generic_benchmark_prose_to_supplied_set(self):
        candidate = {'benchmark_examples': ['The mixed-outcome examples were used.']}
        normalized, note = api.normalize_benchmark_examples(candidate, {
            'benchmark_examples': ['C01', 'C02']})
        self.assertEqual(normalized['benchmark_examples'], ['C01', 'C02'])
        self.assertIn('supplied in the request', note['reason'])

    def test_selection_omits_every_discovered_sol_case(self):
        selected, processed, _ = api.select_cases(api.ROOT)
        self.assertGreaterEqual(len(processed), 25)
        self.assertFalse(set(selected) & set(processed))
        self.assertIn('1975-01', processed)
        self.assertNotIn('1975-01', selected)

    def test_schema_validator_rejects_extra_fields(self):
        with self.assertRaisesRegex(ValueError, 'extra fields'):
            api.validate_value({'unexpected': True}, {
                'type': 'object', 'required': [], 'additionalProperties': False,
                'properties': {}})

    def test_extracts_responses_output_text(self):
        value = api.output_text({'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps({'ok': True})}]}]})
        self.assertEqual(json.loads(value), {'ok': True})

    def test_retry_allows_only_terminal_zero_success_batch(self):
        self.assertEqual(api.retry_disposition({
            'status': 'failed',
            'request_counts': {'completed': 0, 'failed': 72, 'total': 72},
        }), 'retry_zero_success')
        self.assertEqual(api.retry_disposition({
            'status': 'expired',
            'request_counts': {'completed': 3, 'failed': 69, 'total': 72},
            'output_file_id': 'file-output',
        }), 'partial_results')
        self.assertEqual(api.retry_disposition({
            'status': 'in_progress',
            'request_counts': {'completed': 0, 'failed': 0, 'total': 72},
        }), 'still_running')
        self.assertEqual(api.retry_disposition({
            'status': 'completed',
            'request_counts': {'completed': 72, 'failed': 0, 'total': 72},
        }), 'download')

    def test_preflight_rejects_completed_campaign_after_source_repairs(self):
        # The frozen campaign predates the minutes-based repair of 1983-06.
        # Reusing its paid request shards must fail closed rather than silently
        # treating the old source hash as current.
        with self.assertRaisesRegex(ValueError, 'Case source changed after build: 1983-06'):
            api.preflight(api.campaign_path(api.DEFAULT_CAMPAIGN))


if __name__ == '__main__':
    unittest.main()
