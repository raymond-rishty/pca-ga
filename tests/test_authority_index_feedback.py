"""Regression fixtures for the authority index feedback in issue #200."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "authority-index"
sys.path.insert(0, str(SCRIPTS))

from provision_catalogue import _authority_rows, build_catalogue  # noqa: E402

import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("authority_index_feedback", SCRIPTS / "43_authority_index.py")
assert spec and spec.loader
authority = importlib.util.module_from_spec(spec)
spec.loader.exec_module(authority)
audit_spec = importlib.util.spec_from_file_location("authority_index_audit", SCRIPTS / "47_authority_index_audit.py")
assert audit_spec and audit_spec.loader
audit = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit)


class AuthorityIndexFeedbackTests(unittest.TestCase):
    def test_lowercase_page_pp_does_not_create_preliminary_principle_link(self):
        parser_spec = importlib.util.spec_from_file_location("case_provision_fixture", SCRIPTS / "44_case_provision_index.py")
        assert parser_spec and parser_spec.loader
        parser = importlib.util.module_from_spec(parser_spec)
        parser_spec.loader.exec_module(parser)
        hits = parser.text_hits(FIXTURES / "case-with-page-citation.md")
        self.assertEqual(set(hits), {"BCO Preliminary Principle 1"})
        self.assertNotIn("BCO Preliminary Principle 174", hits)

    def test_acree_projection_uses_only_the_audited_case_reverse_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            index = root / "index"
            cases = root / "cases"
            index.mkdir()
            cases.mkdir()
            (index / "case_provision_index.json").write_text(
                (FIXTURES / "acree-case-provision-index.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (index / "judicial_cases.jsonl").write_text(
                '{"case_id":"2021-7","title":"RE J. Lance Acree v. Tennessee Valley Presbytery",'
                '"topic_tags":["standing"]}\n', encoding="utf-8",
            )
            (cases / "ga50_2023__stub_2021-07.md").write_text(
                (FIXTURES / "acree-case.md").read_text(encoding="utf-8"), encoding="utf-8",
            )
            old_root, old_index, old_cases = authority.ROOT, authority.IDX, authority.CASES_DIR
            try:
                authority.ROOT, authority.IDX, authority.CASES_DIR = str(root), str(index), str(cases)
                rows = authority.build_case_rows()
            finally:
                authority.ROOT, authority.IDX, authority.CASES_DIR = old_root, old_index, old_cases
        self.assertEqual([row["provision"] for row in rows], ["BCO 43-1"])
        self.assertEqual(rows[0]["record_id"], "case:cases/ga50_2023__stub_2021-07.md")
        self.assertEqual(rows[0]["relationship_kind"], "explicit_citation")
        self.assertEqual(rows[0]["reader_scope"], "primary")

    def test_ccb_advice_remains_distinct_from_ordinary_inquiries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            index = root / "index"
            scripts = root / "scripts"
            index.mkdir()
            scripts.mkdir()
            for name in ("43_authority_index.py", "overture_catalogue.py", "provision_references.py"):
                shutil.copy2(SCRIPTS / name, scripts / name)
            (index / "inquiries_search.json").write_text(json.dumps([
                {"type": "inquiry", "title": "Ordinary inquiry", "year": 2001,
                 "url": "inquiries/ordinary.md", "provisions": ["BCO 11-4"]},
                {"type": "ccb-advice", "title": "CCB advice", "year": 2001,
                 "url": "inquiries/ccb.md", "provisions": ["BCO 11-4"]},
            ]), encoding="utf-8")
            rows = _authority_rows(root)
        self.assertEqual({row["type"] for row in rows}, {"Constitutional inquiry", "CCB advice"})
        ccb = next(row for row in rows if row["type"] == "CCB advice")
        inquiry = next(row for row in rows if row["type"] == "Constitutional inquiry")
        self.assertEqual(ccb["reader_scope"], "contextual")
        self.assertEqual(inquiry["reader_scope"], "primary")
        self.assertEqual(ccb["snippet"], "")
        self.assertEqual(inquiry["snippet"], "")

    def test_overture_targets_and_body_citations_keep_distinct_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / "index"
            index.mkdir()
            (index / "overture_dispositions.jsonl").write_text(
                '{"vol":"ga51_2024","number":10,"pdf_page":1277,"final_disposition":"Adopted (final)"}\n'
                '{"vol":"ga51_2024","number":11,"pdf_page":1278,"final_disposition":"Approved but not ratified"}\n',
                encoding="utf-8",
            )
            (index / "overture_titles.jsonl").write_text(
                '{"vol":"ga51_2024","number":10,"pdf_page":1277,"title":"Amend BCO 40-1"}\n'
                '{"vol":"ga51_2024","number":11,"pdf_page":1278,"title":"Amend BCO 41-2"}\n',
                encoding="utf-8",
            )
            (index / "overture_bodies.jsonl").write_text(
                '{"vol":"ga51_2024","number":10,"pdf_page":1277,"source":"North Presbytery",'
                '"body":"The proposal concerns BCO 40-1, compares BCO 12-1, and cites WCF 21-5."}\n'
                '{"vol":"ga51_2024","number":11,"pdf_page":1278,"source":"South Presbytery",'
                '"body":"The explanation also cites BCO 12-1."}\n',
                encoding="utf-8",
            )
            old_index = authority.IDX
            try:
                authority.IDX = str(index)
                rows = authority.build_overture_rows()
            finally:
                authority.IDX = old_index
        adopted_target = [row for row in rows if row["record_id"].endswith(":10")
                          and row["provision"] == "BCO 40-1" and row["relationship_kind"] == "proposal_target"]
        adopted_body = [row for row in rows if row["record_id"].endswith(":10")
                        and row["provision"] == "BCO 12-1" and row["relationship_kind"] == "explicit_citation"]
        body_wcf = [row for row in rows if row["record_id"].endswith(":10")
                    and row["provision"] == "WCF 21-5" and row["relationship_kind"] == "explicit_citation"]
        nonadopted_target = [row for row in rows if row["record_id"].endswith(":11")
                             and row["relationship_kind"] == "proposal_target"]
        self.assertEqual(len(adopted_target), 1)
        self.assertEqual(adopted_target[0]["reader_scope"], "primary")
        self.assertEqual(len(adopted_body), 1)
        self.assertEqual(adopted_body[0]["reader_scope"], "candidate")
        self.assertEqual(adopted_body[0]["evidence_basis"], "direct_text")
        self.assertEqual(adopted_body[0]["match_method"], "overture_body_explicit_reference_match")
        self.assertEqual(len(body_wcf), 1)
        self.assertEqual(len(nonadopted_target), 1)
        self.assertEqual(nonadopted_target[0]["reader_scope"], "candidate")
        self.assertIn("ga51-p1277", adopted_body[0]["url"])

    def test_overture_reader_policy_requires_a_curated_adopted_outcome(self):
        for outcome in ("Adopted", "Adopted (final)", "Approved & ratified (2002)",
                        "Approved and ratified", "Answered in the affirmative"):
            with self.subTest(outcome=outcome):
                self.assertTrue(authority.is_adopted_overture_action(outcome))
        for outcome in ("Approved but not ratified", "Approved → sent to presbyteries; ratification not located",
                        "Answered in the negative", "Answered by reference", "Referred"):
            with self.subTest(outcome=outcome):
                self.assertFalse(authority.is_adopted_overture_action(outcome))

    def test_audit_spot_check_accepts_only_the_canonical_acree_provision(self):
        relation = {"type": "Judicial case", "record_id": "case:acree", "title": "RE J. Lance Acree",
                    "metadata": {"case_numbers": ["2021-7"]}}
        catalogue = {"input_fingerprint": "fixture", "assessment_summary": {}, "unmatched_relationships": [],
                     "provisions": [
                         {"abbr": "BCO", "ref": "43-1", "relationships": [relation],
                          "coverage": {"recommendations": {"status": "incomplete"}}},
                     ]}
        self.assertTrue(audit.build_audit(catalogue)["known_case_spot_check"]["passes"])

    def test_audit_counts_each_match_method_without_stringifying_the_list(self):
        self.assertEqual(
            audit._count_dimension(
                [{"match_methods": ["case_text", "structured_tag"]}],
                "match_method", "match_methods",
            ),
            {"case_text": 1, "structured_tag": 1},
        )

    def test_audit_source_links_resolve_from_the_index_directory(self):
        self.assertEqual(audit._audit_source_target("cases/ga36_2008__2007-08.md"),
                         "../cases/ga36_2008__2007-08.md")
        self.assertEqual(audit._audit_source_target("https://example.test/case"),
                         "https://example.test/case")


if __name__ == "__main__":
    unittest.main()
