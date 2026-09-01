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
        self.assertEqual(MODULE.normalize_docket("95-4"), "1995-4")
        self.assertEqual(MODULE.normalize_docket("1995-04"), "1995-4")
        self.assertEqual(MODULE.docket_tokens("Case 02-03", {"2002-3"}), ["2002-3"])
        self.assertEqual(MODULE.docket_tokens("Case 01-34", {"2001-34"}), ["2001-34"])
        self.assertEqual(MODULE.docket_tokens("Case 1-34", {"2001-34"}), ["1-34"])

    def test_abbreviated_dockets_require_local_case_context(self):
        known = {"2001-34", "2002-3", "2018-3", "1990-9"}

        def is_case_reference(line):
            surface, _, start, end = MODULE.raw_docket_tokens(line, known)[-1]
            return MODULE.raw_docket_is_case_reference(line, surface, start, end)

        self.assertTrue(is_case_reference("See ROC 01-34, p. 4 for the underlying complaint."))
        self.assertTrue(is_case_reference("The panel proceeded to consideration of complaint 90-9."))
        self.assertFalse(is_case_reference("The Book of Church Order (B.O.C.O.) cites 18-3."))
        self.assertFalse(is_case_reference("The vote on the motion was 18-3."))
        self.assertFalse(is_case_reference("The SJC approved the Decision on the following 18-3 vote."))
        self.assertFalse(is_case_reference("The meeting occurred January 16-17, 1978."))
        self.assertFalse(is_case_reference("See 1 Timothy 2:11-12."))
        self.assertFalse(is_case_reference("This judicial case discusses RAO 18-3."))
        self.assertFalse(is_case_reference("- **B.** This case discusses BCO 18-3."))
        self.assertFalse(is_case_reference("The case was assigned to a judicial commission according to 18-3."))
        self.assertFalse(is_case_reference("See Decision at 6.18-3."))

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

    def test_caption_candidates_do_not_emit_nested_suffixes(self):
        line = "See earlier decisions (1980, Bogue et al. vs. Presbytery of Ascension; 1986, Gentry et al. vs Calvary Presbytery)."
        surfaces = [surface for surface, _, _ in MODULE.caption_candidates(line)]
        self.assertEqual(
            surfaces,
            [
                "1980, Bogue et al. vs. Presbytery of Ascension",
                "1986, Gentry et al. vs Calvary Presbytery",
            ],
        )

    def test_caption_candidates_reject_numbered_abbreviations_and_generic_comparisons(self):
        self.assertEqual(MODULE.caption_candidates("The Session of V7PC adopted the motion."), [])
        self.assertEqual(MODULE.caption_candidates("The Session of V 7PC adopted the motion."), [])

        evolution = "The Session discussed the matter of Evolution vs Creation."
        surface, start, _ = MODULE.caption_candidates(evolution)[0]
        self.assertFalse(MODULE.caption_candidate_is_case_like(evolution, start, surface))

        case_line = "The decision in Smith v. Central Presbytery controls."
        surface, start, _ = MODULE.caption_candidates(case_line)[0]
        self.assertTrue(MODULE.caption_candidate_is_case_like(case_line, start, surface))

        prose = "The decision in Smith v. Central Presbytery. The court affirmed it."
        self.assertEqual(MODULE.caption_candidates(prose)[0][0], "Smith v. Central Presbytery")

        trailer = "The decision in Smith v. Central Presbytery concerned an appeal."
        self.assertEqual(MODULE.caption_candidates(trailer)[0][0], "Smith v. Central Presbytery")

    def test_caption_context_uses_only_nearby_unique_evidence(self):
        docket_map = {"1991-5": {"case-1991-5"}, "1995-11": {"case-1995-11"}}
        known = set(docket_map)
        line = "The judgment in Gunter v. Central Florida Presbytery (SJC Docket 91-5) was approved."
        surface, start, end = MODULE.caption_candidates(line)[0]
        self.assertEqual(
            MODULE.nearby_caption_evidence(line, start, end, docket_map, {}, known, 1996),
            ("case-1991-5", ["docket-context"], ["1991-5"]),
        )

        distant = "Decision Case 95-11. " + ("unrelated prose " * 10) + "Gentry v. Calvary Presbytery."
        surface, start, end = MODULE.caption_candidates(distant)[0]
        self.assertIsNone(MODULE.nearby_caption_evidence(distant, start, end, docket_map, {}, known, 1997))

    def test_structured_caption_extraction_stops_before_later_citations(self):
        line = (
            "Lee v. Korean Eastern Presbytery (Case No. 2010-26). Also see a report "
            "(M10GA, page 109); Lyons v. Western Carolina."
        )
        match = list(MODULE.CASE_CITATION_RE.finditer(line))[0]
        self.assertIsNone(MODULE.extract_caption_after_docket(line, match))

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
        self.assertTrue(any("Case 2012-08" in x["surface_text"] for x in candidates if x["source_file"] == "cases/ga52_2025__2024-08.md"))

        ruff = [x for x in candidates if x["source_decision"] == "ga41_2013__2011-18" and "2009-28" in x["surface_text"]]
        self.assertGreaterEqual(len(ruff), 5)
        self.assertEqual({x["target_decision"] for x in ruff}, {"ga39_2011__2009-28"})

    def test_sequential_structured_citations_are_not_swallowed(self):
        candidates = read_json("case_reference_candidates.json")["occurrences"]
        unresolved = read_json("case_reference_unresolved.json")["occurrences"]

        herron_sources = {
            "cases/ga50_2023__2021-14.md",
            "cases/ga50_2023__2021-15.md",
            "cases/ga50_2023__2022-11.md",
        }
        for source_file in herron_sources:
            final_decision = [
                x for x in candidates
                if x["source_file"] == source_file
                and x["match_type"] == "docket_caption"
                and x["surface_text"] == "Case 2022-10 PCA v. Herron"
            ]
            self.assertEqual(len(final_decision), 1, source_file)
            self.assertEqual(final_decision[0]["target_decision"], "ga50_2023__2022-10")

            pending = [
                x for x in candidates
                if x["source_file"] == source_file
                and x["surface_text"] == "Cases 2021-14, 2021-15 & 2022-02"
            ]
            self.assertEqual(
                {x["target_decision"] for x in pending},
                {
                    "ga50_2023__2021-14",
                    "ga50_2023__2021-15",
                    "ga50_2023__2022-02",
                },
            )
            self.assertTrue(all(x["match_type"] == "docket" for x in pending))

            pending_unresolved = [
                x for x in unresolved
                if x["source_file"] == source_file
                and x["surface_text"] == "Cases 2021-14, 2021-15 & 2022-02"
            ]
            self.assertEqual(pending_unresolved, [], source_file)

        wills = [
            x for x in candidates
            if x["source_file"] == "cases/ga46_2018__2017-01.md" and x["line"] == 334
        ]
        self.assertEqual(len(wills), 2)
        self.assertEqual(
            {x["target_decision"] for x in wills},
            {"ga44_2016__2015-12", "ga45_2017__2016-14"},
        )
        self.assertTrue(all(x["match_type"] == "docket_caption_minutes" for x in wills))
        self.assertTrue(all("ga45_2017__2016-12" in x["ambiguity"]["minutes_targets"] for x in wills))
        self.assertFalse(any(x["source_file"] == "cases/ga46_2018__2017-01.md" and x["line"] == 334 for x in unresolved))

    def test_related_page_records_share_canonical_decision_nodes(self):
        registry = read_json("case_identity_registry.json")["entries"]
        by_id = {entry["decision_id"]: entry for entry in registry}

        self.assertEqual(
            by_id["ga30_2002__2002-02_2002-03"]["canonical_decision_id"],
            "ga33_2005__2001-34_2002-02_2002-03",
        )
        self.assertEqual(
            by_id["ga49_2022__stub_2020-07"]["canonical_decision_id"],
            "ga49_2022__2020-09",
        )
        self.assertEqual(
            by_id["ga49_2022__stub_2020-08"]["canonical_decision_id"],
            "ga49_2022__2020-09",
        )

        candidates = read_json("case_reference_candidates.json")["occurrences"]
        for surface in ("Case 2002-2", "Judicial Case 2002-02", "Case 2020-07", "Case No. 2020-07"):
            self.assertTrue(
                any(x["surface_text"] == surface and x["target_decision"] in {
                    "ga33_2005__2001-34_2002-02_2002-03",
                    "ga49_2022__2020-09",
                } for x in candidates),
                surface,
            )

    def test_review_ledger_is_fully_addressed_and_preserves_conflicts(self):
        scan_stats = read_json("case_reference_candidates.json")["scan_stats"]
        self.assertEqual(scan_stats["review_overrides_applied"], scan_stats["review_overrides_total"])
        self.assertEqual(scan_stats["review_overrides_unmatched"], [])

        candidates = read_json("case_reference_candidates.json")["occurrences"]
        jackson = [x for x in candidates if x["surface_text"].startswith("Case 2012-08") and x["source_file"] in {
            "cases/ga48_2021__2020-01.md",
            "cases/ga48_2021__2020-13.md",
            "cases/ga50_2023__2022-08.md",
            "cases/ga52_2025__2023-16.md",
            "cases/ga52_2025__2024-08.md",
        }]
        self.assertEqual({x["target_decision"] for x in jackson}, {"ga43_2015__2013-08"})
        self.assertTrue(all(x["ambiguity"] for x in jackson))
        self.assertTrue(any(x["surface_text"] == "Case 2020-04 Williams v. Chesapeake" and x["target_decision"] == "ga48_2021__2019-04" for x in candidates))
        self.assertTrue(any(x["surface_text"] == "M50GA, 2023, p. 924" and x["target_decision"] == "ga50_2023__2022-16" for x in candidates))

    def test_ambiguous_shorthand_non_pca_and_self_references_are_not_guessed(self):
        candidates = read_json("case_reference_candidates.json")["occurrences"]
        unresolved = read_json("case_reference_unresolved.json")["occurrences"]
        graph = read_json("case_citations.json")

        self.assertTrue(any(x.get("self_reference") for x in candidates))
        self.assertFalse(any(edge["source"] == edge["target"] for edge in graph["edges"]))
        self.assertTrue(any(x["match_type"] == "alias" and "Chappell Case" in x["surface_text"] and x["target_decision"] == "ga19_1991__1990-04" for x in candidates))
        self.assertTrue(any(x["match_type"] == "manual" and x["surface_text"] == "the Lee Case" and x["target_decision"] == "ga40_2012__2010-26" for x in candidates))
        self.assertFalse(any(x["surface_text"] == "the Lee Case" for x in unresolved))
        self.assertFalse(any(x["target_decision"] and x["surface_text"] in {"31-2", "40-5"} for x in candidates))
        self.assertFalse(any(x["surface_text"] == "18-3" and "B.O.C.O." in x["context"] for x in candidates))
        self.assertFalse(any(x["surface_text"] == "21-1" and "B.O.C.O." in x["context"] for x in candidates))
        self.assertFalse(any("Walter V Worsham" in x["surface_text"] and x["target_decision"] for x in candidates))

    def test_report_surfaces_occurrence_ambiguities_separately_from_identity_collisions(self):
        unresolved = read_json("case_reference_unresolved.json")["occurrences"]
        observed = [x for x in unresolved if MODULE.is_observed_ambiguity(x)]
        compound = [x for x in unresolved if MODULE.is_compound_docket_occurrence(x)]
        self.assertEqual(len(observed), 0)
        self.assertEqual(len(compound), 9)

        report = (ROOT / "index" / "CASE-REFERENCE-REPORT.md").read_text(encoding="utf-8")
        self.assertIn("### Observed ambiguous citation occurrences", report)
        self.assertIn("**0**", report)
        self.assertIn("Compound/multi-docket occurrences still needing decomposition: **9**", report)
        self.assertIn("Evidence-backed occurrence conflicts resolved with ambiguity evidence retained: **9**", report)
        self.assertIn("Line-addressed review overrides applied: **74** of 74", report)
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
