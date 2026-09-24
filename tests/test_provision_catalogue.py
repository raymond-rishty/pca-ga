#!/usr/bin/env python3
"""Checks for stable catalogue identities and consistent generated projections."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from overture_catalogue import load_curated_overtures  # noqa: E402
from provision_catalogue import (
    _evidence_basis,
    _relation_occurrences,
    authority_projection,
    provision_search_rows,
)  # noqa: E402

case_index_spec = importlib.util.spec_from_file_location("case_provision_index", SCRIPTS / "44_case_provision_index.py")
assert case_index_spec and case_index_spec.loader
case_index = importlib.util.module_from_spec(case_index_spec)
case_index_spec.loader.exec_module(case_index)
authority_spec = importlib.util.spec_from_file_location("authority_index", SCRIPTS / "43_authority_index.py")
assert authority_spec and authority_spec.loader
authority_index = importlib.util.module_from_spec(authority_spec)
authority_spec.loader.exec_module(authority_index)


def load_api_module():
    path = SCRIPTS / "45_bco_manifests.py"
    spec = importlib.util.spec_from_file_location("bco_manifests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api = load_api_module()
research_spec = importlib.util.spec_from_file_location("provision_research", SCRIPTS / "46_provision_research.py")
assert research_spec and research_spec.loader
research = importlib.util.module_from_spec(research_spec)
research_spec.loader.exec_module(research)


def _unit(reference: str, route: str, relationship: dict | None = None) -> dict:
    return {
        "id": f"bco:{reference}",
        "book": "bco",
        "book_name": "Book of Church Order",
        "book_label": "Constitutional text",
        "abbr": "BCO",
        "ref": reference,
        "route_ref": route,
        "reader_ref": f"bco/{route}",
        "title": f"Section {reference}",
        "body": "<p>Current text with <em>emphasis</em>.</p>",
        "supplementary": False,
        "parent_id": None,
        "children": [],
        "coverage": {"relationships": "indexed_records", "recommendations": {"status": "incomplete"}},
        "history": [],
        "relationships": [relationship] if relationship else [],
    }


def _catalogue(*units: dict) -> dict:
    return {
        "schema_version": 1,
        "catalogue_version": 1,
        "source": {"name": "PCA Constitution Reader", "revision": "abc123", "edition": "Current Reader text", "files": {}},
        "input_fingerprint": "feedbeef",
        "provisions": list(units),
    }


class ProvisionCatalogueTests(unittest.TestCase):
    def test_structured_case_tag_does_not_claim_direct_text_or_show_an_unrelated_excerpt(self):
        row = {"type": "Judicial case", "url": "cases/example.md", "snippet": "Unrelated opening text."}
        basis = _evidence_basis("Judicial case", row, None)
        occurrences = _relation_occurrences(row, None, basis, "bco:40-1--case:example")
        self.assertEqual(basis, "structured_case_metadata")
        self.assertEqual(occurrences[0]["excerpt"], "")

    def test_generated_source_front_matter_is_not_treated_as_case_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "case.md"
            path.write_text(
                "---\nsource_links:\n  - source_id: case-pdf:BCO 99-9\n---\n"
                "# Case\nThe judgment cites BCO 40-1.\n",
                encoding="utf-8",
            )
            hits = case_index.text_hits(path)
            body = authority_index.without_front_matter(path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(hits), ["BCO 40-1"])
        self.assertEqual(hits["BCO 40-1"][0]["line"], 6)
        self.assertNotIn("source_links", hits["BCO 40-1"][0]["snippet"])
        self.assertNotIn("BCO 99-9", body)

    def test_api_and_legacy_authority_alias_are_identical_catalogue_projections(self):
        relation = {
            "id": "bco:40-1--overture:ga51_2024:10",
            "record_id": "overture:ga51_2024:10",
            "type": "Overture",
            "title": "Amend BCO 40-1",
            "year": 2024,
            "disposition": "Adopted",
            "authority_weight": "medium",
            "record_url": "markdown/ga51_2024.md",
            "evidence_basis": "title_subject_reference",
            "relevance_status": "unreviewed",
            "occurrences": [{
                "id": "occ-1",
                "url": "markdown/ga51_2024.md#ga51-p1277",
                "locator": {"fragment": "ga51-p1277", "page": 1277},
                "excerpt": "Amend BCO 40-1",
                "sources": [],
            }],
            "metadata": {},
        }
        catalogue = _catalogue(_unit("40-1", "40-1", relation))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            provisions = root / "api" / "provisions"
            bco = root / "api" / "bco"
            provision_count, alias_count = api.project_catalogue(root, catalogue, bco, provisions)
            canonical = provisions / "bco" / "40-1.json"
            alias = bco / "40-1.json"
            payload = json.loads(canonical.read_text(encoding="utf-8"))
            self.assertEqual(canonical.read_bytes(), alias.read_bytes())
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["id"], "bco:40-1")
            self.assertEqual(payload["current_text"]["text"], "Current text with emphasis.")
            self.assertEqual(payload["relationships"][0]["relevance_status"], "unreviewed")
            self.assertEqual(payload["relationships"][0]["id"], relation["id"])
            self.assertEqual(payload["relationships"][0]["record_id"], relation["record_id"])
            self.assertEqual(payload["relationships"][0]["occurrences"][0]["locator"]["page"], 1277)
            self.assertTrue(payload["relationships"][0]["occurrences"][0]["url"].endswith("#ga51-p1277"))
            self.assertEqual(provision_count, 1)
            self.assertEqual(alias_count, 1)
            self.assertEqual(authority_projection(catalogue)[0]["relationship_id"], relation["id"])
            self.assertEqual(provision_search_rows(catalogue)[0]["provision_id"], "bco:40-1")
            self.assertEqual(json.loads((bco / "index.json").read_text())["schema_version"], 2)
            rendered = research.render_unit(catalogue["provisions"][0], root, "/pca-ga", "abc123")
            self.assertIn(f'data-relationship-id="{relation["id"]}"', rendered)
            self.assertIn(f'data-record-id="{relation["record_id"]}"', rendered)

    def test_colliding_normalized_bco_aliases_are_not_published(self):
        catalogue = _catalogue(
            _unit("24-1.a", "24-1.a"),
            _unit("24-1-a", "24-1-a"),
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            count, aliases = api.project_catalogue(root, catalogue,
                                                   root / "api" / "bco",
                                                   root / "api" / "provisions")
            self.assertEqual(count, 2)
            self.assertEqual(aliases, 0)
            self.assertTrue((root / "api" / "provisions" / "bco" / "24-1.a.json").exists())
            self.assertFalse((root / "api" / "bco" / "24-1-a.json").exists())

    def test_distinct_overtures_keep_identity_and_page_locator(self):
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / "index"
            index.mkdir()
            (index / "overture_dispositions.jsonl").write_text(
                '{"vol":"ga51_2024","number":10,"pdf_page":1277,"disposition":"Approved","bco":["40-1"]}\n'
                '{"vol":"ga51_2024","number":11,"pdf_page":1278,"disposition":"Denied","bco":["40-1"]}\n',
                encoding="utf-8",
            )
            (index / "overture_titles.jsonl").write_text(
                '{"vol":"ga51_2024","number":10,"pdf_page":1277,"title":"Amend BCO 40-1 part A"}\n'
                '{"vol":"ga51_2024","number":11,"pdf_page":1278,"title":"Amend BCO 40-1 part B"}\n',
                encoding="utf-8",
            )
            (index / "overture_bodies.jsonl").write_text(
                '{"vol":"ga51_2024","number":10,"pdf_page":1277,"source":"North Presbytery"}\n'
                '{"vol":"ga51_2024","number":11,"pdf_page":1278,"source":"South Presbytery"}\n',
                encoding="utf-8",
            )
            records = load_curated_overtures(index)
        self.assertEqual([row["record_id"] for row in records], [
            "overture:ga51_2024:10", "overture:ga51_2024:11",
        ])
        self.assertEqual([row["url"] for row in records], [
            "markdown/ga51_2024.md#ga51-p1277",
            "markdown/ga51_2024.md#ga51-p1278",
        ])


if __name__ == "__main__":
    unittest.main()
