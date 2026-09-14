import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import synopsis_batch_api as common
import synopsis_deepseek_api as deepseek


class SynopsisDeepSeekApiTests(unittest.TestCase):
    def test_request_matches_deepseek_responses_api(self):
        record = deepseek.request_record(
            deepseek.ROOT, '2023-05', 'deepseek-flash', 'high', 12000)
        self.assertEqual(record['url'], '/responses')
        body = record['body']
        self.assertEqual(body['model'], 'deepseek-flash')
        self.assertEqual(body['reasoning'], {'effort': 'high'})
        self.assertNotIn('store', body)
        self.assertNotIn('prompt_cache_options', body)
        self.assertNotIn('2023-05', body['instructions'])
        self.assertIn('2023-05', body['input'])
        self.assertEqual(body['text']['format']['type'], 'json_schema')
        self.assertNotIn('uniqueItems', json.dumps(body['text']['format']['schema']))

    def test_deepseek_request_validator(self):
        record = deepseek.request_record(
            deepseek.ROOT, '2023-05', 'deepseek-flash', 'high', 12000)
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'requests.jsonl'
            path.write_text(json.dumps(record) + '\n', encoding='utf-8')
            result = common.validate_request_file(path, ['2023-05'], 'deepseek')
        self.assertEqual(result['requests'], 1)

    def test_roster_case_filename_is_windows_safe(self):
        self.assertEqual(common.case_filename('roster:1988-__'),
                         'roster%3A1988-__.json')


if __name__ == '__main__':
    unittest.main()
