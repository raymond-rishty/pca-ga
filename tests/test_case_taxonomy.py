import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("case_taxonomy", ROOT / "scripts" / "12_case_taxonomy.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_canonical_and_legacy_ids_preserve_aliases():
    assert MODULE.canonical_id("2023-7") == "2023-07"
    assert MODULE.legacy_id("1985-06") == "1985-6"
    assert MODULE.canonical_id("Case #6") is None


def test_clean_title_removes_roster_metadata_and_normalizes_caption():
    raw = "Appeal of TE Evans v. Arizona. Decided 03/08/24. Sustained, with concurring opinions"
    assert MODULE.clean_title(raw) == "Evans v. Arizona"


def test_proceeding_type_and_disposition_are_controlled_codes():
    assert MODULE.classify_proceeding_type("Appeal of TE Evans v. Arizona") == "appeal"
    assert MODULE.classify_proceeding_type("BCO 40-5 Matter re Metropolitan NY") == "review_and_control"
    assert MODULE.classify_proceeding_type("Citation of Korean Southwest Presbytery") == "other"
    assert MODULE.classify_proceeding_type("Wichter Memorial re Case 2004-05") == "review_and_control"
    assert MODULE.classify_proceeding_type("In re Korean Eastern Presbytery") == "other"
    assert MODULE.normalize_disposition("administratively out of order") == "out_of_order"
    assert MODULE.normalize_disposition("mixed: specs 1 and 3 sustained") == "partially_sustained"
    assert MODULE.normalize_bco_code("I-14-4") == "14-4"
    assert MODULE.normalize_bco_code("38-3(a)") == "38-3.a"
    assert set(MODULE.PROCEEDING_TYPES) == {"complaint", "appeal", "reference", "review_and_control", "original_jurisdiction_request", "other"}
    assert set(MODULE.OUTCOMES) == {"sustained", "partially_sustained", "not_sustained", "denied", "dismissed", "out_of_order", "in_order", "administrative", "referred", "granted", "abandoned", "other"}
    assert set(MODULE.REVIEW_STANDARD_CODES) == {"clear_error_facts", "clear_error_discretion", "independent_constitutional", "bco_40_5"}
    assert set(MODULE.STANDARD_OF_REVIEW_CODES) == {"clear_error_facts", "clear_error_discretion", "independent_constitutional", "bco_40_5", "mixed", "not_reached", "not_applicable", "not_stated", "unknown"}


def test_review_standard_is_issue_level_and_excludes_separate_opinions():
    code, _, standards = MODULE.standard_of_review("ga45_2017__2016-14", "denied", "complaint")
    assert code == "mixed"
    assert standards == ["clear_error_discretion", "independent_constitutional"]

    code, _, standards = MODULE.standard_of_review("ga48_2021__2019-11", "denied", "complaint")
    assert code == "clear_error_discretion"
    assert standards == ["clear_error_discretion"]


def test_bco_40_5_is_one_review_standard():
    standard, detail = MODULE.contextual_review_standard("BCO 40-5 Matter re NW Georgia")
    assert standard == "bco_40_5"
    assert "important delinquency" in detail.lower()


def test_appended_manual_text_does_not_change_case_vehicle():
    page = """# Complaint of Moo Lim v. Korean Capital Presbytery

### Case 2001-36 COMPLAINT OF MOO LIM VS. KOREAN CAPITAL PRESBYTERY

### IV. Proposed SJC Manual Changes

### 16. PROCEDURE FOR HEARING A MEMORIAL (BCO 40-5)
"""
    headings = MODULE.case_page_headings(page)
    assert MODULE.classify_proceeding_type(headings) == "complaint"
    assert MODULE.contextual_review_standard(headings) == (None, None)


def test_non_merits_dispositions_do_not_receive_appellate_standards():
    assert MODULE._review_code([], True, "administrative", "review_and_control") == "not_reached"
    assert MODULE._review_code([], True, "referred", "review_and_control") == "not_reached"


def test_generated_catalog_carries_stable_evans_identity_and_all_roster_rows():
    rows = [
        __import__("json").loads(line)
        for line in (ROOT / "index" / "judicial_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 474
    evans = next(row for row in rows if row["case_id"] == "2023-07")
    assert evans["title"] == "Evans v. Arizona Presbytery"
    assert evans["legacy_case_id"] == "2023-7"
    assert evans["proceeding_type"] == "appeal"
    assert evans["outcome"] == "sustained"
    assert isinstance(evans["review_standards"], list)
    assert len({row["case_id"] for row in rows if row["case_id"]}) == 473
    assert all(row["outcome"] in MODULE.OUTCOMES for row in rows)
    assert all(row["proceeding_type"] in MODULE.PROCEEDING_TYPES for row in rows)
    assert all(row["standard_of_review"] in MODULE.STANDARD_OF_REVIEW_CODES for row in rows)
    assert all(set(row["review_standards"]).issubset(MODULE.REVIEW_STANDARD_CODES) for row in rows)
    assert all(row["summary_review_status"] in {"audited", "pending_audit"} for row in rows)
    assert all(
        re.fullmatch(r"\d{1,2}-\d{1,2}(?:\.[a-z0-9]+)*", provision)
        for row in rows for provision in row["bco_provisions"]
    )


def test_editorial_overrides_fill_source_grounded_summaries():
    json = __import__("json")
    rows = [
        json.loads(line)
        for line in (ROOT / "index" / "judicial_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    editorial = json.loads((ROOT / "index" / "judicial_case_editorial_overrides.json").read_text(encoding="utf-8"))
    by_id = {row["case_id"]: row for row in rows if row.get("case_id")}
    assert len(editorial) >= 100
    assert all(by_id[cid]["summary"] == override["summary"] for cid, override in editorial.items() if "summary" in override)
    assert all(by_id[cid]["summary_review_status"] == "audited" for cid in editorial)
    mapes = next(row for row in rows if row["case_id"] == "2018-01")
    assert mapes["outcome"] == "partially_sustained"
    assert "admonition" in mapes["summary"].lower()
    assert next(row for row in rows if row["case_id"] == "2003-07")["outcome"] == "out_of_order"
    assert next(row for row in rows if row["case_id"] == "2023-06")["summary_source"] == "official_decision_pdf"
    assert next(row for row in rows if row["case_id"] == "2023-06")["summary_review_status"] == "audited"


def test_human_index_is_generated_from_the_canonical_layer():
    index = (ROOT / "index" / "JUDICIAL-CASES.md").read_text(encoding="utf-8")
    assert "# Canonical judicial cases" in index
    assert "Review standard" in index
    assert "| `2023-07` | Evans v. Arizona Presbytery |" in index
    assert "| `1986-01` | Kenneth L. Gentry, Jr. et al. v. Calvary Presbytery |" in index
