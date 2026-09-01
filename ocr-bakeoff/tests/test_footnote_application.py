import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "79_apply_footnotes.py"
SPEC = importlib.util.spec_from_file_location("apply_footnotes", MODULE_PATH)
assert SPEC and SPEC.loader
apply_footnotes = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = apply_footnotes
SPEC.loader.exec_module(apply_footnotes)


def link(**overrides):
    value = {
        "marker_page": 2,
        "note_page": 2,
        "marker_value": "3",
        "marker_cluster_id": "p2-m001",
        "classification": "confirmed",
        "marker_line_text": "The sentence ends here.3",
        "marker_before_text": "The sentence ends here.",
        "marker_after_text": "",
        "note_text": "3 A supporting explanation.",
    }
    value.update(overrides)
    return value


class FootnoteApplicationTests(unittest.TestCase):
    def test_applies_inline_reference_and_definition(self):
        source = """---
---
<!-- PAGE ga=14 pdf_page=2 printed_page=2 -->

The sentence ends here.3

### FOOTNOTES

3 A supporting explanation.
"""
        updated, summary = apply_footnotes.apply_volume_text("ga14", source, [link()])
        self.assertIn("The sentence ends here.[^fn-ga14-p2-n3]", updated)
        self.assertIn("[^fn-ga14-p2-n3]: A supporting explanation.", updated)
        self.assertEqual(summary["failures"], [])
        self.assertEqual(summary["skipped_ambiguous"], [])

    def test_strips_html_for_table_text_location(self):
        source = """<!-- PAGE ga=14 pdf_page=2 printed_page=2 -->

<table><tr><td>The sentence ends here.3</td></tr></table>

Footnotes

3 A supporting explanation.
        """
        updated, summary = apply_footnotes.apply_volume_text("ga14", source, [link()])
        self.assertIn(
            '<td>The sentence ends here.<sup id="fnref-fn-ga14-p2-n3"><a href="#fn-ga14-p2-n3">3</a></sup></td>',
            updated,
        )
        self.assertIn('<a id="fn-ga14-p2-n3"></a><sup>3</sup> A supporting explanation.', updated)
        self.assertEqual(summary["failures"], [])

    def test_skips_equally_distant_targets(self):
        source = """<!-- PAGE ga=14 pdf_page=2 printed_page=2 -->

The sentence ends here.3

3 A supporting explanation.
"""
        updated, summary = apply_footnotes.apply_volume_text(
            "ga14",
            source,
            [link(note_page=1), link(note_page=3)],
        )
        self.assertEqual(updated, source)
        self.assertEqual(len(summary["skipped_ambiguous"]), 1)

    def test_does_not_rewrite_citation_number(self):
        source = """<!-- PAGE ga=14 pdf_page=2 printed_page=2 -->

Deuteronomy 6:6-9.

### FOOTNOTES

6 A supporting explanation.
"""
        updated, summary = apply_footnotes.apply_volume_text(
            "ga14",
            source,
            [link(
                marker_value="6",
                marker_line_text="6:6-9.",
                marker_before_text="6:",
                marker_after_text="-9.",
                note_text="6 A supporting explanation.",
            )],
        )
        self.assertEqual(updated, source)
        self.assertEqual(summary["applied_markers"], 0)
        self.assertEqual(summary["applied_definitions"], 0)
        self.assertEqual(summary["failures"][0]["kind"], "marker")


if __name__ == "__main__":
    unittest.main()
