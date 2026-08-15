import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("case_layout", ROOT / "scripts" / "69_case_layout_adjudication.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CaseLayoutTests(unittest.TestCase):
    def test_anchor_locator_accepts_normalized_source_text(self):
        text = "### Case #4: Appeal of TE Steele\n\nThe motion was adopted."
        found = MODULE.locate_anchor("Case 4 Appeal of TE Steele", text)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertTrue(text[found[0]:found[1]].startswith("Case #4: Appeal"))


    def test_validation_rejects_page_set_changes(self):
        request = {
            "case_file": "cases/ga14_1986__case4.md",
            "volume": "ga14_1986",
            "expected_pdf_pages": [163, 164, 165],
        }
        response = {
            "case_file": request["case_file"],
            "decision": "accept",
            "selected_pdf_pages": [163, 164],
            "start_page": 163,
            "end_page": 164,
            "start_anchor": "Case 4",
            "end_anchor": "Respectfully submitted",
            "confidence": 0.95,
            "evidence_ids": ["p163-b0"],
            "rationale": "test",
        }
        _, error = MODULE.validate_response(response, request)
        self.assertEqual(error, "page_set_changed")


    def test_replace_body_preserves_case_wrapper_and_footer(self):
        page = "# Title\n\n*Source: [ga03_1975 p. 50](../markdown/ga03_1975.md#ga03-p50)*\n\n---\n\nold\n\n---\n\nfooter\n"
        updated = MODULE.replace_body(page, "<!-- PAGE ga=3 pdf_page=50 -->\n\nnew")
        self.assertTrue(updated.startswith("# Title\n\n*Source:"))
        self.assertIn("new", updated)
        self.assertIn("footer", updated)

    def test_structure_preservation_keeps_short_heading(self):
        existing = "---\n\n*Source: [ga34_2006 p. 87](../markdown/ga34_2006.md#ga34-p87)*\n\n---\n\n### A\n\n---\n\nfooter\n"
        updated = "---\n\n*Source: [ga34_2006 p. 87](../markdown/ga34_2006.md#ga34-p87)*\n\n---\n\nA\n\n---\n\nfooter\n"
        preserved = MODULE.preserve_existing_structure(existing, updated)
        self.assertIn("### A", preserved)


if __name__ == "__main__":
    unittest.main()
