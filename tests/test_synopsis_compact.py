import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_synopses_compact as c


class CompactTests(unittest.TestCase):
    def test_schema_requires_contract_and_rejects_extras(self):
        value = c.schema()
        self.assertFalse(value['additionalProperties'])
        self.assertIn('first_summary', value['required'])
        self.assertIn('verification_notes', value['required'])
        self.assertIn('repair_needed', value['required'])

    def test_example_routing(self):
        self.assertEqual(c.examples({'matter_type': 'appeal',
            'final_dispositions': ['sustained', 'remanded']}), ['A01', 'A03'])
        self.assertEqual(c.examples({'matter_type': 'complaint',
            'final_dispositions': ['dismissed']}), ['C01', 'C20'])

    def test_command_is_tool_free_read_only_and_fresh(self):
        claim = {'model': 'gpt-5.6-sol', 'reasoning_effort': 'medium'}
        command = c.command('codex', Path('root'), claim, Path('schema'), Path('out'))
        self.assertIn('--ignore-user-config', command)
        self.assertIn('--ignore-rules', command)
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        self.assertIn('shell_tool', command)
        self.assertIn('web_search="disabled"', command)
        self.assertIn('--output-schema', command)

    def test_prompt_is_self_contained_and_source_numbered(self):
        prompt = c.build_prompt(c.q.ROOT, '2023-05')
        self.assertIn('AUTHORITATIVE CASE SOURCE:', prompt)
        self.assertIn('COMPACT RUNTIME CONTRACT:', prompt)
        self.assertIn('`judicial_reference`', prompt)
        self.assertIn('`judicially_out_of_order`', prompt)
        self.assertIn('Fidelity must be 2', prompt)
        self.assertIn('### C01.', prompt)
        self.assertIn('### C20.', prompt)
        self.assertIn('1: # 2023-05', prompt)
        self.assertLess(len(prompt), 26000)

    def test_runtime_contract_stays_compact(self):
        contract = (c.q.ROOT / c.RUNTIME_CONTRACT).read_text(encoding='utf-8')
        self.assertLess(len(contract), 6000)
        self.assertIn('incorporated decisions', contract)
        self.assertIn('no_final_disposition', contract)

    def test_claim_can_limit_one_case(self):
        # Behavioral coverage lives in queue tests; this guards the compact API.
        self.assertIn('max_cases', c.q.claim.__code__.co_varnames)


if __name__ == '__main__':
    unittest.main()
