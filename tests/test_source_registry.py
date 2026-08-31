from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_source_registry.py"
spec = importlib.util.spec_from_file_location("build_source_registry", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class SourceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = json.loads(
            (ROOT / "index" / "source_registry.json").read_text(encoding="utf-8")
        )
        self.inventory = json.loads(
            (ROOT / "index" / "dedicated_pdf_inventory.json").read_text(encoding="utf-8")
        )

    def test_committed_registry_is_valid(self) -> None:
        self.assertEqual(module.validate_registry(ROOT), [])

    def test_dedicated_inventory_is_complete_for_known_inputs(self) -> None:
        self.assertEqual(len(self.inventory["sources"]), 219)
        source_ids = {source["source_id"] for source in self.registry["sources"]}
        inventory_ids = {source["source_id"] for source in self.inventory["sources"]}
        self.assertEqual(
            inventory_ids,
            {
                source["source_id"]
                for source in self.registry["sources"]
                if source["kind"] == "dedicated_pdf"
            },
        )
        self.assertTrue(inventory_ids <= source_ids)
        self.assertEqual(self.registry["coverage"]["cases"]["records"], 645)
        self.assertEqual(self.registry["coverage"]["inquiries"]["records"], 436)
        self.assertEqual(self.registry["coverage"]["overtures"]["records"], 3543)
        self.assertEqual(self.registry["coverage"]["rpr"]["records"], 10636)
        self.assertEqual(self.registry["coverage"]["studies"]["records"], 83)
        self.assertEqual(
            len([key for key in self.registry["record_sources"] if key.startswith("rpr:")]),
            17669,
        )

    def test_source_ids_are_unique_and_record_references_resolve(self) -> None:
        source_ids = [source["source_id"] for source in self.registry["sources"]]
        self.assertEqual(len(source_ids), len(set(source_ids)))
        source_set = set(source_ids)
        for record_id, refs in self.registry["record_sources"].items():
            self.assertTrue(refs, record_id)
            self.assertTrue(set(refs) <= source_set, record_id)

    def test_external_pdf_inventory_is_explicit_about_nonvendored_binaries(self) -> None:
        for source in self.inventory["sources"]:
            self.assertRegex(source["url"], r"^https://(?:www\.)?pcahistory\.org/")
            self.assertTrue(source["pdf_path"].endswith(".pdf"))
            self.assertIsNone(source["local_pdf_path"])
            self.assertTrue(source["inventory_source"])
        self.assertEqual(
            {source["record_type"] for source in self.inventory["sources"]},
            {"case", "study"},
        )

    def test_pdf_url_validation_accepts_both_historical_center_hosts(self) -> None:
        for host in ("pcahistory.org", "www.pcahistory.org"):
            self.assertRegex(
                f"https://{host}/pca/sjc/cases/example.pdf",
                module.PDF_URL_RE,
            )


if __name__ == "__main__":
    unittest.main()
