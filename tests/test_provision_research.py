#!/usr/bin/env python3
"""Regression checks for stable provision routes and generated relation states."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "provision_research", ROOT / "scripts" / "46_provision_research.py"
)
assert SPEC and SPEC.loader
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


class ProvisionResearchTests(unittest.TestCase):
    def test_canonical_ids_and_routes_are_stable(self):
        self.assertEqual(research.canonical_id("BCO 40–1"), "bco:40-1")
        self.assertEqual(research.canonical_id("WCF XXVII"), "wcf:27")
        self.assertEqual(research.canonical_id("WLC Q&A 62"), "wlc:Q.62")
        self.assertEqual(research.provision_path("wlc", "Q.62"), "/pca-ga/provisions/wlc/q-62/")
        self.assertEqual(research.provision_path("bco", "40-1"), "/pca-ga/provisions/bco/40-1/")

    def test_empty_reference_state_is_explicit_in_a_canonical_page(self):
        unit = research._unit("wcf", "27.1", "Section 27.1", "<p>Current text.</p>")
        with tempfile.TemporaryDirectory() as folder:
            rendered = research.render_unit(unit, Path(folder), "/pca-ga", "")
        self.assertIn("No indexed records are currently linked to this provision.", rendered)
        self.assertIn('rel="canonical" href="https://raymond-rishty.github.io/pca-ga/provisions/wcf/27.1/"', rendered)

    def test_source_links_keep_available_occurrence_anchors(self):
        row = {
            "type": "Overture",
            "title": "Amend BCO 38-4",
            "url": "markdown/ga51_2024.md#ga51-p1277",
            "year": 2024,
            "relation_label": "Provision mentioned in overture subject",
        }
        with tempfile.TemporaryDirectory() as folder:
            rendered = research._record_html(row, Path(folder), "/pca-ga")
        self.assertIn('/pca-ga/markdown/ga51_2024.html#ga51-p1277', rendered)
        self.assertIn("51st GA · 2024", rendered)

    def test_case_evidence_links_to_the_cited_text_when_available(self):
        row = {
            "type": "Judicial case",
            "title": "Example v. Presbytery",
            "url": "cases/ga20_1992__1991-04.md",
            "evidence_snippet": "The court cited BCO 38-4 in this decision.",
            "evidence_line": 42,
        }
        with tempfile.TemporaryDirectory() as folder:
            rendered = research._record_html(row, Path(folder), "/pca-ga")
        self.assertIn("#:~:text=The%20court%20cited%20BCO%2038-4", rendered)
        self.assertIn("at cited text", rendered)

    def test_legacy_authority_page_links_to_canonical_route(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "authorities").mkdir()
            (root / "authorities" / "BCO-40-1.md").write_text("# BCO 40-1\n", encoding="utf-8")
            (root / "_site" / "authorities").mkdir(parents=True)
            rendered_path = root / "_site" / "authorities" / "BCO-40-1.html"
            rendered_path.write_text("<article><h1>BCO 40-1</h1><p>Legacy index.</p></article>", encoding="utf-8")
            unit = research._unit("bco", "40-1", "Section 40-1", "<p>Text</p>")
            count = research.add_legacy_authority_links(root, root / "_site", {unit["id"]: unit})
            result = rendered_path.read_text(encoding="utf-8")
        self.assertEqual(count, 1)
        self.assertIn('../provisions/bco/40-1/', result)

    def test_empty_reference_state_is_explicit_in_the_shared_page_view(self):
        unit = research._unit("bco", "40-1", "Section 40-1", "<p>Current text.</p>")
        with tempfile.TemporaryDirectory() as folder:
            rendered = research.render_unit(unit, Path(folder), "/pca-ga", "")
        self.assertIn("No indexed records are currently linked to this provision.", rendered)
        self.assertIn("How to read these links", rendered)

    def test_renumbering_status_is_preserved_as_qualified_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index").mkdir()
            (root / "index" / "bco_changes.jsonl").write_text("", encoding="utf-8")
            (root / "index" / "bco_renumberings.jsonl").write_text(
                '{"chapter":"24","adopted_year":1988,"ga":16,"mappings":[{"from":"24-6","to":"24-7"}],"status":"page_stated"}\n',
                encoding="utf-8",
            )
            unit = research._unit("bco", "24-7", "Section 24-7", "<p>Text</p>")
            research._history_for_units(root, {unit["id"]: unit})
        self.assertEqual(unit["history"][0]["status"], "page_stated")
        self.assertIn("BCO 24-6 → BCO 24-7", unit["history"][0]["note"])


if __name__ == "__main__":
    unittest.main()
