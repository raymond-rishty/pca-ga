import importlib.util
import json
import sys
import tempfile
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

    def test_does_not_rewrite_dotted_bco_citation_number(self):
        source = """<!-- PAGE ga=48 pdf_page=684 printed_page=667 -->

BCO 34-5 stipulates this rule. Teaching should follow BCO 27.5.a.
"""
        updated, summary = apply_footnotes.apply_volume_text(
            "ga48",
            source,
            [link(
                marker_page=684,
                note_page=684,
                marker_value="5",
                marker_line_text="BCO 34-5 stipulates this rule. Teaching should follow BCO 27.5.a.",
                marker_before_text="BCO 34-",
                marker_after_text=" stipulates",
                note_text="5 A citation, not a footnote.",
            )],
        )
        self.assertEqual(updated, source)
        self.assertEqual(summary["applied_markers"], 0)
        self.assertEqual(summary["applied_definitions"], 0)
        self.assertEqual(summary["failures"][0]["kind"], "marker")

    def test_gold_fallback_does_not_rewrite_dotted_bco_citation_number(self):
        source = """<!-- PAGE ga=48 pdf_page=684 printed_page=667 -->

Teaching should follow BCO 27.5.a.
"""
        updated, summary = apply_footnotes.apply_volume_text(
            "ga48",
            source,
            [link(
                marker_page=684,
                note_page=684,
                marker_value="5",
                marker_line_text="BCO 27.5.a.",
                marker_before_text="BCO 27.",
                marker_after_text=".a.",
                note_text="5 A citation, not a footnote.",
            )],
            allow_gold_fallback=True,
        )
        self.assertEqual(updated, source)
        self.assertEqual(summary["applied_markers"], 0)
        self.assertEqual(summary["applied_definitions"], 0)
        self.assertEqual(summary["failures"][0]["kind"], "marker")

    def test_gold_filter_accepts_only_expected_marker_occurrences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gold.json"
            path.write_text(json.dumps({
                "volume": "ga14_1986",
                "pages": [{"page": 2, "expected_markers": ["3"]}],
            }), encoding="utf-8")
            allowed = apply_footnotes.load_gold_markers([path])
        self.assertEqual(allowed, {("ga14", 2): {"3"}})

    def test_value_without_context_is_not_treated_as_marker(self):
        source = "<!-- PAGE ga=18 pdf_page=164 printed_page=162 -->\n\n76 Minutes of the Ninety-Ninth Assembly.\n"
        page = apply_footnotes.page_chunks(source)[164]
        self.assertIsNone(
            apply_footnotes.marker_change(
                page,
                link(
                    marker_page=164,
                    note_page=164,
                    marker_value="76",
                    marker_line_text="the rightness and wisdom. 24.7.76",
                    marker_before_text="the rightness and wisdom. 24.7.",
                ),
                "fn-ga18-p164-n76",
            )
        )

    def test_repairs_gold_sequence_without_creating_a_link(self):
        source = """<!-- PAGE ga=26 pdf_page=112 printed_page=110 -->

[^fn-ga26-p112-n4]: In the Beginning. 5 Next note body.
"""
        updated, repaired = apply_footnotes.repair_concatenated_definitions(
            "ga26", source, {112: {"4", "5"}}
        )
        self.assertEqual(repaired, 1)
        self.assertIn("[^fn-ga26-p112-n4]: In the Beginning.\n\n5 Next note body.", updated)

    def test_sequence_repair_prefers_retained_next_note_text(self):
        source = """<!-- PAGE ga=50 pdf_page=953 printed_page=945 -->

[^fn-ga50-p953-n39]: First citation, 40. History citation, 20. 40 Minutes of the General Assembly, 274.
"""
        updated, repaired = apply_footnotes.repair_concatenated_definitions(
            "ga50",
            source,
            {953: {"39", "40"}},
            {953: {"40": "40 Minutes of the General Assembly"}},
        )
        self.assertEqual(repaired, 1)
        self.assertIn(
            "[^fn-ga50-p953-n39]: First citation, 40. History citation, 20.\n\n40 Minutes",
            updated,
        )

    def test_gold_fallback_materializes_omitted_table_marker(self):
        source = """<!-- PAGE ga=14 pdf_page=2 printed_page=2 -->

<table><tr><td>Director salary and benefits</td></tr></table>

The 1987 figure is a 6% increase over 1986.
"""
        updated, summary = apply_footnotes.apply_volume_text(
            "ga14",
            source,
            [link(
                marker_page=2,
                note_page=2,
                marker_value="1",
                marker_line_text="Director salary and benefits1",
                marker_before_text="D irector salary and benefits",
                marker_after_text="",
                note_text="1 The 1987 figure is a 6% increase over 1986.",
            )],
            allow_gold_fallback=True,
        )
        self.assertIn('benefits<sup id="fnref-fn-ga14-p2-n1"><a href="#fn-ga14-p2-n1">1</a></sup>', updated)
        self.assertIn('<a id="fn-ga14-p2-n1"></a><sup>1</sup> The 1987 figure', updated)
        self.assertEqual(summary["failures"], [])

    def test_gold_fallback_materializes_bare_numeric_definition(self):
        source = """<!-- PAGE ga=50 pdf_page=853 printed_page=845 -->

Ramsay supposed that debarment was an incitement to prompt prosecution.13

13 By this logic, the three-year period is interpreted as an incitement to diligence.
"""
        updated, summary = apply_footnotes.apply_volume_text(
            "ga50",
            source,
            [link(
                marker_page=853,
                note_page=853,
                marker_value="13",
                marker_line_text="Ramsay supposed that debarment was an incitement to prompt prosecution.13",
                marker_before_text="Ramsay supposed that debarment was an incitement to prompt prosecution.",
                marker_after_text="",
                note_text="13",
            )],
            allow_gold_fallback=True,
        )
        self.assertIn("prosecution.[^fn-ga50-p853-n13]", updated)
        self.assertIn("[^fn-ga50-p853-n13]: By this logic", updated)
        self.assertEqual(summary["failures"], [])

    def test_marker_after_context_disambiguates_trailing_superscript(self):
        source = """<!-- PAGE ga=49 pdf_page=790 printed_page=773 -->

The cited essay ends at (Essay on Confessional Foundations, p. 23)23

23 PCA Statements at https://example.test/source.
"""
        updated, summary = apply_footnotes.apply_volume_text(
            "ga49",
            source,
            [link(
                marker_page=790,
                note_page=790,
                marker_value="23",
                marker_cluster_id="p790-m007",
                marker_line_text="The cited essay ends at (Essay on Confessional Foundations, p. 23)23",
                marker_before_text="The cited essay ends at (Essay on Confessional Foundations, p. ",
                marker_after_text=")23",
                note_text="23",
            )],
            allow_gold_fallback=True,
        )
        self.assertIn("p. 23)[^fn-ga49-p790-n23]", updated)
        self.assertNotIn("p. [^fn-ga49-p790-n23])23", updated)
        self.assertIn("[^fn-ga49-p790-n23]: PCA Statements", updated)
        self.assertEqual(summary["failures"], [])


if __name__ == "__main__":
    unittest.main()
