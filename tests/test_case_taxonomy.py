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
    assert MODULE.roster_canonical_id({"case_number": "2002-26", "case_number_raw": "2002-26"}) == "2002-06"
    assert MODULE.roster_canonical_id({"case_number": "2012-13", "case_number_raw": "2012-13"}) == "2012-03"
    assert MODULE.ROSTER_COMPANION_IDS["2023-06"] == ("2023-08",)
    assert MODULE.roster_canonical_id({
        "case_number_raw": "1997-07",
        "title": "Black v. Eastern Carolina",
    }) == "1999-07"


def test_clean_title_removes_roster_metadata_and_normalizes_caption():
    raw = "Appeal of TE Evans v. Arizona. Decided 03/08/24. Sustained, with concurring opinions"
    assert MODULE.clean_title(raw) == "Evans v. Arizona"


def test_matter_type_and_final_disposition_are_controlled_codes():
    assert MODULE.classify_matter_type("Appeal of TE Evans v. Arizona") == "appeal"
    assert MODULE.classify_matter_type("BCO 40-5 Matter re Metropolitan NY") == "bco_40_5_matter"
    assert MODULE.classify_matter_type("Citation of Korean Southwest Presbytery") == "review_and_control"
    assert MODULE.classify_matter_type("Wichter Memorial re Case 2004-05") == "bco_40_5_matter"
    assert MODULE.classify_matter_type("Judicial Reference from Evangel Presbytery") == "judicial_reference"
    assert MODULE.normalize_disposition("administratively out of order") == "administratively_out_of_order"
    assert MODULE.normalize_disposition("judicially out of order") == "judicially_out_of_order"
    assert MODULE.normalize_disposition("mixed: specs 1 and 3 sustained") == "partially_sustained"
    assert MODULE.normalize_disposition("Complaint found invalid") == "not_sustained"
    assert MODULE.normalize_disposition(
        "specifications 1 and 2 sustained; specification 3 not sustained"
    ) == "partially_sustained"
    assert MODULE.classify_final_dispositions(
        "Appeal sustained; remanded for a new trial"
    ) == ["sustained", "remanded"]
    assert MODULE.classify_final_dispositions(
        "Both letters found administratively and judicially out of order"
    ) == ["administratively_out_of_order", "judicially_out_of_order"]
    assert MODULE.normalize_bco_code("I-14-4") == "14-4"
    assert MODULE.normalize_bco_code("38-3(a)") == "38-3.a"
    assert set(MODULE.MATTER_TYPES) == {"complaint", "appeal", "judicial_reference", "original_jurisdiction_request", "bco_40_5_matter", "review_and_control", "other"}
    assert {"not_guilty", "administratively_out_of_order", "judicially_out_of_order", "remanded", "no_final_disposition"}.issubset(MODULE.FINAL_DISPOSITIONS)
    assert set(MODULE.REVIEW_STANDARD_CODES) == {"factual_findings", "discretion_and_judgment", "constitutional_interpretation", "important_delinquency_or_grossly_unconstitutional_proceeding"}
    assert set(MODULE.STANDARD_OF_REVIEW_CODES) == {"factual_findings", "discretion_and_judgment", "constitutional_interpretation", "important_delinquency_or_grossly_unconstitutional_proceeding", "mixed", "not_reached", "not_applicable", "not_stated", "unknown"}


def test_review_standard_is_issue_level_and_excludes_separate_opinions():
    code, _, standards = MODULE.standard_of_review("ga45_2017__2016-14", "denied", "complaint")
    assert code == "mixed"
    assert standards == ["discretion_and_judgment", "constitutional_interpretation"]

    code, _, standards = MODULE.standard_of_review(
        "ga48_2021__2019-11", "denied", "complaint", case_id="2019-11"
    )
    assert code == "discretion_and_judgment"
    assert standards == ["discretion_and_judgment"]

    code, _, standards = MODULE.standard_of_review(
        "ga37_2009__2007-13",
        "denied",
        "complaint",
        {"review_standards": ["constitutional_interpretation"]},
        case_id="2007-13",
    )
    assert code == "not_stated"
    assert standards == []

    code, _, standards = MODULE.standard_of_review(
        "ga36_2008__2006-02",
        "sustained",
        "bco_40_5_matter",
        case_id="2006-02",
    )
    assert code == "important_delinquency_or_grossly_unconstitutional_proceeding"
    assert standards == ["important_delinquency_or_grossly_unconstitutional_proceeding"]

    code, _, standards = MODULE.standard_of_review(
        "ga38_2010__2008-15_2008-16_2008-17_2008-18_2009-01_2009-03",
        "denied",
        "complaint",
        case_id="2008-17",
    )
    assert code == "discretion_and_judgment"
    assert standards == ["discretion_and_judgment"]

    code, _, standards = MODULE.standard_of_review(
        "ga38_2010__2008-15_2008-16_2008-17_2008-18_2009-01_2009-03",
        "out_of_order",
        "complaint",
        case_id="2009-01",
    )
    assert code == "not_reached"
    assert standards == []

    code, _, standards = MODULE.standard_of_review(
        "ga42_2014__2011-11_2011-12_2011-15_2011-16",
        "denied",
        "complaint",
        case_id="2011-15",
    )
    assert code == "discretion_and_judgment"
    assert standards == ["discretion_and_judgment"]


def test_legacy_review_values_do_not_infer_basis_labels():
    code, _, standards = MODULE.standard_of_review(
        "ga37_2009__2007-13",
        "denied",
        "complaint",
        {"standard_of_review": "mixed", "standard_of_review_detail": "legacy"},
    )
    assert code == "not_stated"
    assert standards == []


def test_explicit_clear_error_and_unconstitutional_language_maps_to_astra_taxonomy():
    body = "It was a clear error of judgment to do so, and unconstitutional to do so per BCO 34-10."
    assert MODULE._detected_review_standards(body) == [
        "discretion_and_judgment",
        "constitutional_interpretation",
    ]


def test_bco_40_5_is_one_review_standard():
    standard, detail = MODULE.contextual_review_standard("BCO 40-5 Matter re NW Georgia")
    assert standard == "important_delinquency_or_grossly_unconstitutional_proceeding"
    assert "important delinquency" in detail.lower()


def test_appended_manual_text_does_not_change_case_vehicle():
    page = """# Complaint of Moo Lim v. Korean Capital Presbytery

### Case 2001-36 COMPLAINT OF MOO LIM VS. KOREAN CAPITAL PRESBYTERY

### IV. Proposed SJC Manual Changes

### 16. PROCEDURE FOR HEARING A MEMORIAL (BCO 40-5)
"""
    headings = MODULE.case_page_headings(page)
    assert MODULE.classify_matter_type(headings) == "complaint"
    assert MODULE.contextual_review_standard(headings) == (None, None)


def test_non_merits_dispositions_do_not_receive_appellate_standards():
    assert MODULE._review_code([], True, ["no_final_disposition"], "review_and_control") == "not_reached"
    assert MODULE._review_code([], True, ["referred"], "review_and_control") == "not_reached"
    code, _, standards = MODULE.standard_of_review(
        "ga45_2017__2016-08", "out_of_order", "complaint", case_id="2016-08"
    )
    assert code == "not_reached"
    assert standards == []


def test_generated_catalog_carries_stable_evans_identity_and_all_roster_rows():
    rows = [
        __import__("json").loads(line)
        for line in (ROOT / "index" / "judicial_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 477
    evans = next(row for row in rows if row["case_id"] == "2023-07")
    assert evans["title"] == "Evans v. Arizona Presbytery"
    assert evans["legacy_case_id"] == "2023-7"
    assert evans["matter_type"] == "appeal"
    assert "sustained" in evans["final_dispositions"]
    assert isinstance(evans["review_standards"], list)
    assert len({row["case_id"] for row in rows if row["case_id"]}) == 476
    assert {"2023-06", "2023-08", "2023-15", "2023-17", "2025-12", "2025-13"}.issubset(
        {row["case_id"] for row in rows}
    )
    assert all(row["matter_type"] in MODULE.MATTER_TYPES for row in rows)
    assert all(row["final_dispositions"] for row in rows)
    assert all(set(row["final_dispositions"]).issubset(MODULE.FINAL_DISPOSITIONS) for row in rows)
    assert all("outcome" not in row and "proceeding_type" not in row for row in rows)
    assert all(row["standard_of_review"] in MODULE.STANDARD_OF_REVIEW_CODES for row in rows)
    assert all(set(row["review_standards"]).issubset(MODULE.REVIEW_STANDARD_CODES) for row in rows)
    assert all(row["summary_review_status"] in {"audited", "pending_audit"} for row in rows)
    assert not [row for row in rows if row["classification_status"] == "needs_review"]
    assert all(
        re.fullmatch(r"\d{1,2}-\d{1,2}(?:\.[a-z0-9]+)*", provision)
        for row in rows for provision in row["bco_provisions"]
    )


def test_previously_unresolved_cases_have_source_grounded_classifications():
    rows = {
        row["case_id"]: row
        for line in (ROOT / "index" / "judicial_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [__import__("json").loads(line)]
    }
    expected = {
        "1978-01": ("complaint", "remanded"),
        "1980-02": ("complaint", "sustained"),
        "1981-02": ("complaint", "not_sustained"),
        "1985-01": ("complaint", "out_of_order"),
        "1991-07": ("complaint", "not_sustained"),
        "1992-09a": ("complaint", "partially_sustained"),
        "2000-08": ("complaint", "out_of_order"),
        "2004-11": ("appeal", "dismissed"),
        "2016-10": ("review_and_control", "no_final_disposition"),
        "2016-13": ("complaint", "dismissed"),
        "2017-10": ("review_and_control", "referred"),
        "2017-11": ("review_and_control", "referred"),
        "2017-12": ("review_and_control", "referred"),
        "2020-02": ("original_jurisdiction_request", "referred"),
        "2020-04": ("complaint", "remanded"),
        "2021-08": ("review_and_control", "no_final_disposition"),
        "2022-11": ("original_jurisdiction_request", "referred"),
        "2022-12": ("original_jurisdiction_request", "dismissed"),
        "2023-14": ("bco_40_5_matter", "partially_sustained"),
    }
    assert {
        case_id: (rows[case_id]["matter_type"], rows[case_id]["final_dispositions"][0])
        for case_id in expected
    } == expected


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
    assert mapes["final_dispositions"][0] == "partially_sustained"
    assert "admonition" in mapes["summary"].lower()
    assert "administratively_out_of_order" in next(row for row in rows if row["case_id"] == "2003-07")["final_dispositions"]
    assert next(row for row in rows if row["case_id"] == "2023-06")["summary_source"] == "official_decision_pdf"
    assert next(row for row in rows if row["case_id"] == "2023-06")["summary_review_status"] == "audited"


def test_source_checked_disagreements_use_the_decisions_dispositions():
    json = __import__("json")
    rows = {
        row["case_id"]: row
        for line in (ROOT / "index" / "judicial_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
    }
    expected = {
        "1976-01": ["not_sustained"],
        "1980-03": ["sustained", "remanded"],
        "1984-04": ["partially_sustained"],
        "1984-07": ["partially_sustained"],
        "1992-03": ["administratively_out_of_order"],
        "1992-04": ["administratively_out_of_order", "remanded"],
        "1997-07": ["judicially_out_of_order"],
        "1999-04": ["administratively_out_of_order"],
        "1999-07": ["not_sustained"],
        "2006-06": ["denied"],
        "2007-14": ["guilty", "dismissed"],
        "2010-08": ["judicially_out_of_order"],
        "2022-22": ["partially_sustained", "annulled", "remanded"],
        "2023-09": ["sustained", "reversed"],
    }
    assert {case_id: rows[case_id]["final_dispositions"] for case_id in expected} == expected
    assert rows["1997-07"]["title"] == "Steve Farris v. Central Florida Presbytery"
    assert rows["1997-07"]["bco_provisions"] == []
    assert rows["1997-07"]["dissent"] is False
    assert rows["1999-04"]["bco_provisions"] == ["42-2"]
    assert rows["1999-07"]["title"] == "Jeffrey M. Black v. Eastern Carolina Presbytery"


def test_audited_identity_corrections_survive_auxiliary_case_merge():
    json = __import__("json")
    rows = {
        row["case_number"]: row
        for line in (ROOT / "index" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
        if row.get("case_number")
    }
    assert rows["1992-3"]["title"] == "Richard E. Olson, et al. v. Heritage Presbytery"
    assert rows["1992-4"]["title"] == "William A. Conrad, et al. v. Central Carolina Presbytery"
    assert rows["1997-7"]["title"] == "Steve Farris v. Central Florida Presbytery"
    assert rows["1999-4"]["disposition"] == "administratively_out_of_order"
    assert rows["1999-7"]["title"] == "Jeffrey M. Black v. Eastern Carolina Presbytery"


def test_human_index_is_generated_from_the_canonical_layer():
    index = (ROOT / "index" / "JUDICIAL-CASES.md").read_text(encoding="utf-8")
    assert "# Canonical judicial cases" in index
    assert "Review basis" in index
    assert "Matter type" in index
    assert "Final disposition" in index
    assert "| `2023-07` | Evans v. Arizona Presbytery |" in index
    assert "| `1986-01` | Kenneth L. Gentry, Jr. et al. v. Calvary Presbytery |" in index
    assert "Factual findings — great deference; clear error" in index
    assert "factual_findings" not in index
    assert "partially_sustained" not in index
    assert "administratively_out_of_order" not in index


def test_assembly_index_uses_canonical_answers_with_friendly_labels():
    index = (ROOT / "index" / "CASES.md").read_text(encoding="utf-8")
    assert "| [1992-03](../cases/ga20_1992__1992-03.md) | Richard E. Olson, et al. v. Heritage Presbytery | Administratively out of order |" in index
    assert "| [1992-04](../cases/ga20_1992__1992-04.md) | William A. Conrad, et al. v. Central Carolina Presbytery  ·  *dissent* | Administratively out of order; Remanded |" in index
    assert "| [1997-07](../cases/ga26_1998__1997-07.md) | Steve Farris v. Central Florida Presbytery | Judicially out of order |" in index
    assert "| [1999-07](../cases/ga29_2001__1999-07.md) | Jeffrey M. Black v. Eastern Carolina Presbytery  ·  *dissent* | Not sustained |" in index
    assert "factual_findings" not in index
    assert "administratively_out_of_order" not in index
