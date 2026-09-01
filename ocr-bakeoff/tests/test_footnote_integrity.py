import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "81_validate_footnote_integrity.py"
SPEC = importlib.util.spec_from_file_location("validate_footnote_integrity", MODULE_PATH)
assert SPEC and SPEC.loader
integrity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integrity
SPEC.loader.exec_module(integrity)


class FootnoteIntegrityTests(unittest.TestCase):
    def test_reference_without_definition_is_reported(self) -> None:
        report = integrity.inventory("Text[^fn-ga14-p2-n1].")
        self.assertEqual(report.missing_definitions, ["fn-ga14-p2-n1"])
        self.assertEqual(report.orphan_definitions, [])

    def test_definition_without_reference_is_reported(self) -> None:
        report = integrity.inventory("[^fn-ga14-p2-n1]: Note text.")
        self.assertEqual(report.missing_definitions, [])
        self.assertEqual(report.orphan_definitions, ["fn-ga14-p2-n1"])

    def test_duplicate_definition_is_reported(self) -> None:
        report = integrity.inventory(
            "Text[^fn-ga14-p2-n1].\n\n"
            "[^fn-ga14-p2-n1]: First.\n"
            "[^fn-ga14-p2-n1]: Duplicate."
        )
        self.assertEqual(report.duplicate_definitions, ["fn-ga14-p2-n1"])

    def test_concatenated_definitions_are_reported(self) -> None:
        report = integrity.inventory(
            "[^fn-ga14-p2-n1]: First. [^fn-ga14-p2-n2]: Second."
        )
        self.assertEqual(report.concatenated_definition_lines, (1,))
        self.assertIn("multiple definitions on one line: 1", report.issues)

    def test_html_reference_and_definition_are_paired(self) -> None:
        report = integrity.inventory(
            '<sup id="fnref-fn-ga14-p2-n1"><a href="#fn-ga14-p2-n1">1</a></sup>'
            '<a id="fn-ga14-p2-n1"></a><sup>1</sup> Note.'
        )
        self.assertEqual(report.issues, [])

    def test_page_locality_accepts_definition_in_encoded_page(self) -> None:
        text = (
            '<!-- PAGE ga=14 pdf_page=2 printed_page=2 -->\n'
            'Text<sup id="fnref-fn-ga14-p2-n1"><a href="#fn-ga14-p2-n1">1</a></sup>\n'
            '<a id="fn-ga14-p2-n1"></a><sup>1</sup> Note.\n'
            '<!-- PAGE ga=14 pdf_page=3 printed_page=3 -->\n'
        )
        self.assertEqual(integrity.page_locality_issues(text), [])

    def test_page_locality_rejects_definition_in_wrong_page(self) -> None:
        text = (
            '<!-- PAGE ga=14 pdf_page=2 printed_page=2 -->\n'
            'Text<sup id="fnref-fn-ga14-p2-n1"><a href="#fn-ga14-p2-n1">1</a></sup>\n'
            '<!-- PAGE ga=14 pdf_page=3 printed_page=3 -->\n'
            '<a id="fn-ga14-p2-n1"></a><sup>1</sup> Note.\n'
        )
        self.assertEqual(
            integrity.page_locality_issues(text),
            ["definition for fn-ga14-p2-n1 is in PAGE 3, expected PAGE 2"],
        )

    def test_published_corpus_has_paired_footnotes(self) -> None:
        paths = [ROOT / directory for directory in integrity.DEFAULT_DIRECTORIES]
        self.assertEqual(integrity.validate_paths(paths), [])


if __name__ == "__main__":
    unittest.main()
