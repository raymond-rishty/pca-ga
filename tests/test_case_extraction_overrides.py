from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location(
    "case_extraction_overrides", ROOT / "scripts" / "69_reextract_case_overrides.py")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CaseExtractionOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((ROOT / "index" / "case_extraction_overrides.json").read_text(
            encoding="utf-8"))
        cls.by_id = {case_id: row for row in cls.rows for case_id in row["case_ids"]}

    def test_rendered_pages_match_pinned_sources(self):
        for row in self.rows:
            with self.subTest(case_ids=row["case_ids"]):
                expected = MODULE.render(row)
                actual = (ROOT / "cases" / f"{row['file']}.md").read_text(encoding="utf-8")
                self.assertEqual(actual, expected)

    def test_contracted_pages_exclude_neighboring_dockets(self):
        forbidden = {
            "1991-05": "SJC Docket 91-7",
            "1992-08": "SJC Docket 92-9b",
            "1997-17": "panel decision in case 98-2",
            "1998-06": "case 98-7 be declared",
        }
        for case_id, phrase in forbidden.items():
            row = self.by_id[case_id]
            page = (ROOT / "cases" / f"{row['file']}.md").read_text(encoding="utf-8")
            self.assertNotIn(phrase, page, case_id)

    def test_expanded_pages_include_missing_decisions(self):
        required = {
            "1983-08": "### ADJUDICATION OF CASE 8",
            "1998-06": "The Committee on 98-6 recommended",
            "1998-07": "did not file a complaint after the Presbytery",
            "1999-06": "### III. JUDGMENT",
        }
        for case_id, phrase in required.items():
            row = self.by_id[case_id]
            page = (ROOT / "cases" / f"{row['file']}.md").read_text(encoding="utf-8")
            self.assertIn(phrase, page, case_id)

    def test_split_cases_have_distinct_canonical_pages(self):
        page_map = json.loads((ROOT / "index" / "case_pages_map.json").read_text(
            encoding="utf-8"))
        self.assertEqual(page_map["1998-03"]["file"], "ga27_1999__1998-03")
        self.assertEqual(page_map["1998-04"]["file"], "ga27_1999__1998-04")
        self.assertNotEqual(page_map["1998-03"]["file"], page_map["1998-04"]["file"])

    def test_reordered_case_stops_before_the_next_source_section(self):
        row = self.by_id["1999-06"]
        page = (ROOT / "cases" / f"{row['file']}.md").read_text(encoding="utf-8")
        self.assertIn("13 concur, 1 dissent", page)
        self.assertNotIn("PROCEDURES FOR ASSUMING OF ORIGINAL JURISDICTION", page)


if __name__ == "__main__":
    unittest.main()
