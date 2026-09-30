from __future__ import annotations

import importlib.util
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "minutes_page_markup", ROOT / "scripts" / "46_minutes_page_markup.py")
assert spec and spec.loader
markup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = markup
spec.loader.exec_module(markup)

from source_links import pdf_page_for_anchor
import importlib.util as import_util

refs_spec = import_util.spec_from_file_location(
    "minutes_link_refs", ROOT / "scripts" / "44_link_constitution_refs.py")
assert refs_spec and refs_spec.loader
refs_module = import_util.module_from_spec(refs_spec)
sys.modules[refs_spec.name] = refs_module
refs_spec.loader.exec_module(refs_module)


def volume_html(pages: list[tuple[int, str]], ga: int = 51) -> str:
    body = []
    for pdf_page, printed_page in pages:
        body.extend([
            f'<p><a id="ga{ga}-p{pdf_page}"></a></p>',
            f'<!-- PAGE ga={ga} pdf_page={pdf_page} printed_page={printed_page} -->',
            f'<p>Text on PDF page {pdf_page}.</p>',
        ])
    return '<html><article class="reading-col">' + "\n".join(body) + '</article></html>'


class MinutesPageAnchorTests(unittest.TestCase):
    def test_pdf_and_printed_targets_are_distinct_and_migrate_legacy_collision(self) -> None:
        source = volume_html([(808, "801"), (815, "808")])
        rendered, _, wrappers = markup.transform_volume(source, Path("ga51_2024.html"))
        self.assertEqual(wrappers, 2)
        self.assertIn('id="ga51-pdf-p808"', rendered)
        self.assertIn('id="ga51-p801"', rendered)
        self.assertIn('id="ga51-pdf-p815"', rendered)
        self.assertIn('id="ga51-p808"', rendered)
        self.assertEqual(rendered.count('id="ga51-p808"'), 1)
        self.assertNotIn('<a id="ga51-p808"></a>', rendered)

    def test_repeated_printed_folio_gets_unique_occurrence_targets(self) -> None:
        source = volume_html([(302, "300"), (590, "300")], ga=33)
        rendered, _, _ = markup.transform_volume(source, Path("ga33_2005.html"))
        self.assertEqual(rendered.count('id="ga33-p300"'), 1)
        self.assertIn('id="ga33-p300-at-pdf302"', rendered)
        self.assertIn('id="ga33-p300-at-pdf590"', rendered)
        self.assertIn('href="#ga33-p300-at-pdf590"', rendered)

    def test_transform_is_idempotent_and_repairs_old_generated_markup(self) -> None:
        source = volume_html([(808, "801"), (815, "808")])
        rendered, _, _ = markup.transform_volume(source, Path("ga51_2024.html"))
        repeated, _, _ = markup.transform_volume(rendered, Path("ga51_2024.html"))
        self.assertEqual(repeated, rendered)

    def test_nested_page_markers_are_idempotent_without_wrappers(self) -> None:
        source = (
            '<html><article class="reading-col"><ul>'
            '<li><!-- PAGE ga=15 pdf_page=20 printed_page=null -->First</li>'
            '<li><!-- PAGE ga=15 pdf_page=21 printed_page=null -->Second</li>'
            '</ul></article></html>'
        )
        rendered, _, wrappers = markup.transform_volume(source, Path("ga15_1987.html"))
        repeated, _, _ = markup.transform_volume(rendered, Path("ga15_1987.html"))
        self.assertEqual(wrappers, 0)
        self.assertEqual(repeated, rendered)
        self.assertEqual(rendered.count('class="page-marker"'), 2)

    def test_source_resolver_treats_bare_page_fragment_as_printed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "markdown").mkdir()
            (root / "markdown" / "ga51_2024.md").write_text(
                "<!-- PAGE ga=51 pdf_page=808 printed_page=801 -->\n"
                "<!-- PAGE ga=51 pdf_page=815 printed_page=808 -->\n",
                encoding="utf-8")
            self.assertEqual(pdf_page_for_anchor(root, "ga51_2024", "ga51-p808"), 815)
            self.assertEqual(pdf_page_for_anchor(root, "ga51_2024", "ga51-pdf-p808"), 808)

    def test_page_index_keeps_repeated_folio_occurrences_by_pdf_coordinate(self) -> None:
        source = volume_html([(302, "300"), (590, "300")], ga=33)
        rendered, _, _ = markup.transform_volume(source, Path("ga33_2005.html"))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minutes = root / "markdown"
            minutes.mkdir()
            (minutes / "ga33_2005.html").write_text(rendered, encoding="utf-8")
            refs, payload = refs_module.build_minutes_page_index(root)
        volume = payload["volumes"]["33"]
        self.assertEqual(payload["version"], 2)
        self.assertEqual(volume["pages"]["300"]["pdf_page"], 302)
        self.assertEqual(set(volume["pdf_pages"]), {"302", "590"})
        self.assertEqual(len(volume["occurrences"]), 2)
        self.assertEqual(refs["33"]["300"]["anchor"], "ga33-p300")


if __name__ == "__main__":
    unittest.main()
