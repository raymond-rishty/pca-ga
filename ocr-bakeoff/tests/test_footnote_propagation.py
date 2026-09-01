import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "80_propagate_footnotes_to_extracted.py"
SPEC = importlib.util.spec_from_file_location("propagate_footnotes", MODULE_PATH)
assert SPEC and SPEC.loader
propagation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = propagation
SPEC.loader.exec_module(propagation)


class FootnotePropagationTests(unittest.TestCase):
    def test_repairs_marker_misclassified_at_concatenated_note_label(self) -> None:
        footnote_id = "fn-ga44-p518-n11"
        root = propagation.FOOTNOTES.PageChunk(
            page=518,
            start=0,
            end=200,
            text=(
                '<!-- PAGE ga=44 pdf_page=518 printed_page=516 -->\n'
                f'<a id="{footnote_id}"></a><sup>11</sup> Lauro Lines v. Chasser, 1989.'
            ),
        )
        page = propagation.FOOTNOTES.PageChunk(
            page=518,
            start=0,
            end=250,
            text=(
                '<!-- PAGE ga=44 pdf_page=518 printed_page=516 -->\n'
                f'<sup id="fnref-{footnote_id}"><a href="#{footnote_id}">11</a></sup>:'
                'Lauro Lines v. Chasser, 1989.'
            ),
        )
        change = propagation.definition_change_from_root(
            page, root, footnote_id, "11", html_style=True
        )
        self.assertIsNotNone(change)
        assert change is not None
        updated = propagation.FOOTNOTES.apply_changes(page.text, [change])
        self.assertIn(
            f'<a id="{footnote_id}"></a><sup>11</sup> Lauro Lines',
            updated,
        )
        self.assertNotIn(f'fnref-{footnote_id}', updated)


if __name__ == "__main__":
    unittest.main()
