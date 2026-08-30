import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("case_citation_inventory", ROOT / "scripts" / "48_case_citation_inventory.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def read_json(name):
    return json.loads((ROOT / "index" / name).read_text(encoding="utf-8"))


class CaseCitationInventoryTests(unittest.TestCase):
    def test_docket_normalization_handles_ocr_and_two_digit_forms(self):
        self.assertEqual(MODULE.normalize_docket("92-9b"), "1992-9b")
        self.assertEqual(MODULE.normalize_docket("92-09B"), "1992-9b")
        self.assertEqual(MODULE.normalize_docket("3 - 12"), "3-12")
        self.assertEqual(MODULE.normalize_docket("01-34", {"2001-34"}), "2001-34")

    def test_caption_normalization_is_limited_to_demonstrated_variants(self):
        forms = [
            "Hann v. Pee Dee Presbytery",
            "Hann vs Pee Dee Presbytery",
            "Hann versus Pee Dee Presbytery",
        ]
        self.assertEqual({MODULE.caption_key(form) for form in forms}, {"hann v pee dee presbytery"})
        self.assertEqual(
            MODULE.caption_key("Complaint of TE John Evans vs. Arizona Presbytery", remove_roles=True),
            "john evans v arizona presbytery",
        )
        self.assertNotIn("x v y presbytery", MODULE.caption_keys("Presbytery of X versus Y Presbytery"))

    def test_known_consolidated_and_conflicted_examples(self):
        registry = read_json("case_identity_registry.json")["entries"]
        by_docket = {
            docket: entry
            for entry in registry
            for docket in entry["docket_numbers"]
        }
        self.assertIs(by_docket["2019-10"], by_docket["2019-12"])
        self.assertTrue(by_docket["2019-10"]["consolidated"])
        self.assertIn("2023-8", by_docket)

        candidates = read_json("case_reference_candidates.json")["occurrences"]
        unresolved = read_json("case_reference_unresolved.json")["occurrences"]

        evans = [x for x in candidates if x["source_decision"] == "ga51_2024__2023-07" and "2019-10" in x["surface_text"]]
        self.assertEqual(len(evans), 1)
        self.assertEqual(evans[0]["target_decision"], by_docket["2019-10"]["decision_id"])
        self.assertEqual(set(evans[0]["target_dockets"]), {"2019-10", "2019-12"})

        bigelow = [x for x in candidates if x["source_decision"] == "ga52_2025__2024-08"]
        for docket in ("2023-1", "2020-13", "2020-1", "2012-6", "1992-9b"):
            self.assertTrue(any(docket in x.get("cited_dockets", []) for x in bigelow), docket)
        self.assertTrue(any("Case 2012-08" in x["surface_text"] for x in unresolved if x["source_decision"] == "ga52_2025__2024-08"))

        ruff = [x for x in candidates if x["source_decision"] == "ga41_2013__2011-18" and "2009-28" in x["surface_text"]]
        self.assertGreaterEqual(len(ruff), 5)
        self.assertEqual({x["target_decision"] for x in ruff}, {"ga39_2011__2009-28"})

    def test_ambiguous_shorthand_non_pca_and_self_references_are_not_guessed(self):
        candidates = read_json("case_reference_candidates.json")["occurrences"]
        unresolved = read_json("case_reference_unresolved.json")["occurrences"]
        graph = read_json("case_citations.json")

        self.assertTrue(any(x.get("self_reference") for x in candidates))
        self.assertFalse(any(edge["source"] == edge["target"] for edge in graph["edges"]))
        self.assertTrue(any(x["match_type"] == "short_alias" and "Chappell Case" in x["surface_text"] for x in unresolved))
        self.assertFalse(any(x["target_decision"] and x["surface_text"] in {"31-2", "40-5"} for x in candidates))
        self.assertFalse(any("Walter V Worsham" in x["surface_text"] and x["target_decision"] for x in candidates))

    def test_report_surfaces_occurrence_ambiguities_separately_from_identity_collisions(self):
        unresolved = read_json("case_reference_unresolved.json")["occurrences"]
        observed = [x for x in unresolved if MODULE.is_observed_ambiguity(x)]
        compound = [x for x in unresolved if MODULE.is_compound_docket_occurrence(x)]
        self.assertEqual(len(observed), 111)
        self.assertEqual(len(compound), 75)

        report = (ROOT / "index" / "CASE-REFERENCE-REPORT.md").read_text(encoding="utf-8")
        self.assertIn("### Observed ambiguous citation occurrences", report)
        self.assertIn("**111**", report)
        self.assertIn("Compound/multi-docket occurrences needing decomposition: **75**", report)
        self.assertIn("cases/ga52_2025__2024-08.md", report)
        self.assertIn("Case 2012-08", report)
        self.assertIn("### Identity-level alias collisions (not necessarily observed citation ambiguities)", report)
        self.assertIn("hugo andrino v southern florida", report)

    def test_inventory_is_reproducible(self):
        command = [sys.executable, str(ROOT / "scripts" / "48_case_citation_inventory.py"), "--root", str(ROOT)]
        paths = [
            ROOT / "index" / "case_identity_registry.json",
            ROOT / "index" / "case_reference_candidates.json",
            ROOT / "index" / "case_reference_unresolved.json",
            ROOT / "index" / "case_citations.json",
            ROOT / "index" / "CASE-REFERENCE-REPORT.md",
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        first = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
        subprocess.run(command, check=True, capture_output=True, text=True)
        second = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
