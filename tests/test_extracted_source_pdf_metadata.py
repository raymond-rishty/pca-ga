from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "source_links.py"
spec = importlib.util.spec_from_file_location("source_links", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ExtractedSourcePdfMetadataTests(unittest.TestCase):
    def test_resolves_printed_anchor_to_pdf_page_and_source_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "markdown").mkdir()
            (root / "cases").mkdir()
            (root / "markdown" / "ga51_2024.md").write_text(
                "<!-- PAGE ga=51 pdf_page=749 printed_page=742 -->\n"
                "Minutes text\n",
                encoding="utf-8",
            )
            page = (
                "# 2022-23 — Woodham v. South Florida Presbytery\n\n"
                "*Source: [ga51_2024 pp. 742–766]"
                "(../markdown/ga51_2024.md#ga51-p742)*\n"
            )

            links = module.extract_source_links(root, page)

            self.assertEqual(
                links,
                [{
                    "type": "minutes",
                    "source_id": "minutes:ga51_2024",
                    "label": "Minutes PDF · p. 749",
                    "file": "51st_pcaga_2024.pdf",
                    "volume": "ga51_2024",
                    "pdf_page": 749,
                    "url": "https://www.pcahistory.org/pca/ga/51st_pcaga_2024.pdf#page=749",
                }],
            )

    def test_repeated_printed_folio_uses_the_first_source_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "markdown").mkdir()
            (root / "markdown" / "ga33_2005.md").write_text(
                "<!-- PAGE ga=33 pdf_page=302 printed_page=300 -->\n"
                "General Assembly business\n"
                "<!-- PAGE ga=33 pdf_page=590 printed_page=300 -->\n"
                "Appendix\n",
                encoding="utf-8",
            )
            page = (
                "*[ga33_2005 p. 300]"
                "(../markdown/ga33_2005.md#ga33-p300)*\n"
            )

            links = module.extract_source_links(root, page)

            self.assertEqual(links[0]["pdf_page"], 302)
            self.assertEqual(
                links[0]["url"],
                "https://www.pcahistory.org/pca/ga/33rd_pcaga_2005.pdf#page=302",
            )

    def test_resolves_inline_page_marker_when_source_link_has_no_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "markdown").mkdir()
            page = (
                "**Assembly:** 51st (2024)\n\n"
                "<!-- PAGE ga=51 pdf_page=749 -->\n"
            )

            links = module.extract_source_links(root, page)

            self.assertEqual(links[0]["source_id"], "minutes:ga51_2024")
            self.assertEqual(links[0]["pdf_page"], 749)
            self.assertEqual(links[0]["url"], "https://www.pcahistory.org/pca/ga/51st_pcaga_2024.pdf#page=749")

    def test_preserves_dedicated_pdf_before_minutes_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "markdown").mkdir()
            (root / "studies").mkdir()
            (root / "markdown" / "ga21_1993.md").write_text(
                "<!-- PAGE ga=21 pdf_page=132 printed_page=130 -->\n",
                encoding="utf-8",
            )
            page = (
                "📄 **[Original PDF](https://www.pcahistory.org/pca/studies/example.pdf)**\n\n"
                "*Source: [ga21_1993 p. 130]"
                "(../markdown/ga21_1993.md#ga21-p130)*\n"
            )

            links = module.extract_source_links(root, page)

            self.assertEqual(links[0]["type"], "dedicated")
            self.assertTrue(links[0]["source_id"].startswith("dedicated-pdf:"))
            self.assertEqual(links[0]["url"], "https://www.pcahistory.org/pca/studies/example.pdf")
            self.assertEqual(links[1]["source_id"], "minutes:ga21_1993")
            self.assertEqual(links[1]["pdf_page"], 132)

    def test_record_resolver_prefers_registry_dedicated_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "index").mkdir()
            (root / "markdown").mkdir()
            (root / "index" / "source_registry.json").write_text(
                '{"sources": ['
                '{"source_id": "case-pdf:2022-23_Woodham", "kind": "dedicated_pdf", '
                '"url": "https://www.pcahistory.org/pca/sjc/cases/2022-23_Woodham.pdf", '
                '"pdf_path": "pca/sjc/cases/2022-23_Woodham.pdf"},'
                '{"source_id": "minutes:ga51_2024", "kind": "minutes", '
                '"volume": "ga51_2024", "pdf_path": "pca/ga/51st_pcaga_2024.pdf", '
                '"url": "https://www.pcahistory.org/pca/ga/51st_pcaga_2024.pdf"}'
                '], "record_sources": {"case:2022-23": '
                '["case-pdf:2022-23_Woodham", "minutes:ga51_2024"]}}',
                encoding="utf-8",
            )

            links = module.source_entries_for_record(
                root, "case", "2022-23", "ga51_2024", 749
            )

            self.assertEqual(links[0]["source_id"], "case-pdf:2022-23_Woodham")
            self.assertEqual(links[1]["source_id"], "minutes:ga51_2024")
            self.assertEqual(links[1]["pdf_page"], 749)

            legacy = (
                "*Source: [ga51_2024 p. 742]"
                "(../markdown/ga51_2024.md#ga51-p742)*\\n"
            )
            inferred = module.source_entries_for_path(
                root, Path("cases/ga51_2024__2022-23.md"), legacy
            )
            self.assertEqual(inferred[0]["source_id"], "case-pdf:2022-23_Woodham")

    def test_normalize_adds_front_matter_without_touching_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "markdown").mkdir()
            (root / "markdown" / "ga51_2024.md").write_text(
                "<!-- PAGE ga=51 pdf_page=749 printed_page=742 -->\n",
                encoding="utf-8",
            )
            page = "*Source: [ga51_2024 p. 742](../markdown/ga51_2024.md#ga51-p742)*\n"

            normalized, changed = module.normalize_text(root, page)

            self.assertTrue(changed)
            self.assertIn(
                'source_id: "minutes:ga51_2024"\n    label: "Minutes PDF · p. 749"',
                normalized,
            )
            self.assertIn("pdf_page: 749", normalized)
            self.assertTrue(normalized.endswith(page))


if __name__ == "__main__":
    unittest.main()
