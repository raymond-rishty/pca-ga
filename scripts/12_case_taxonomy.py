#!/usr/bin/env python3
"""Build the canonical, one-row-per-case judicial taxonomy.

Inputs are the official SJC/CJB roster plus the reconciled extracted case index.
The output is intentionally separate from ``index/cases.jsonl``: that file has
legacy extraction rows and is still consumed by older builders, while this file
is the stable editorial/search layer for Issue #149.

Usage: python scripts/12_case_taxonomy.py [ROOT]
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict


ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, "index")
ROSTER = os.path.join(IDX, "sjc_official", "roster.jsonl")
CASES = os.path.join(IDX, "cases.jsonl")
CJB_PAGES = os.path.join(IDX, "cjb_pages.json")
CJB_CASES = os.path.join(IDX, "cjb_cases.json")
PAGE_MAP = os.path.join(IDX, "case_pages_map.json")
EDITORIAL_OVERRIDES = os.path.join(IDX, "judicial_case_editorial_overrides.json")
SUMMARY_AUDITS = os.path.join(IDX, "judicial_case_summary_audits.json")
OUT = os.path.join(IDX, "judicial_cases.jsonl")

PROCEEDING_TYPES = (
    "complaint", "appeal", "reference", "review_and_control",
    "original_jurisdiction_request", "other",
)
OUTCOMES = (
    "sustained", "partially_sustained", "not_sustained", "denied", "dismissed",
    "out_of_order", "in_order", "administrative", "referred", "granted",
    "abandoned", "other",
)
STANDARD_OF_REVIEW_CODES = (
    "clear_error_facts",
    "clear_error_discretion",
    "independent_constitutional",
    "mixed",
    "not_reached",
    "not_applicable",
    "not_stated",
    "unknown",
)

REVIEW_STANDARD_CODES = (
    "clear_error_facts",
    "clear_error_discretion",
    "independent_constitutional",
)


def canonical_id(raw):
    """Return a zero-padded canonical docket id, or None for a non-docket label."""
    m = re.fullmatch(r"\s*(\d{4})-(\d{1,3})([a-z]?)\s*", str(raw or ""), re.I)
    return f"{m.group(1)}-{int(m.group(2)):02d}{m.group(3).lower()}" if m else None


def legacy_id(raw):
    cid = canonical_id(raw)
    if not cid:
        return None
    m = re.fullmatch(r"(\d{4})-(\d+)([a-z]?)", cid)
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}"


def _strip_title_metadata(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip().rstrip(".")
    # Citations and the official roster's summary are metadata, not caption.
    text = re.split(r"\s*\[\s*M\s*\d+\s*GA\b", text, maxsplit=1, flags=re.I)[0]
    text = re.split(r"\s+[—-]\s+(?:M\s*\d+\s*GA\b|Decided\b|Not\s+|Sustained\b|Dismissed\b|"
                    r"Administratively\b|Out\s+of\s+Order\b|Withdrawn\b|Abandoned\b)",
                    text, maxsplit=1, flags=re.I)[0]
    text = re.sub(r"\s+Summary\s*:.*$", "", text, flags=re.I)
    text = re.sub(r"\s+Decided(?:\s+\d{1,2}/\d{1,2}/\d{2,4})?.*$", "", text, flags=re.I)
    text = re.sub(r"\s+(?:Not\s+Sustained|Sustained(?:\s+in\s+part)?|Dismissed|"
                  r"Administratively\s+out\s+of\s+order|Out\s+of\s+Order|Withdrawn|"
                  r"Abandoned)\s*$", "", text, flags=re.I)
    # Procedural labels and officer honorifics are not part of the public caption.
    text = re.sub(r"^(?:Appeal|Complaint|Petition)\s+of\s+", "", text, flags=re.I)
    text = re.sub(r"^Case\s*#?\s*\d+\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"^(?:TE|RE)\s+", "", text)
    text = re.sub(r"\s+et\s+al\.?$", " et al.", text, flags=re.I)
    text = re.sub(r"\s+vs?\.?\s+", " v. ", text, flags=re.I)
    return text.strip(" .—-")


def clean_title(roster_title, extracted_title=None):
    """Prefer an extracted clean caption, falling back to the roster caption."""
    candidates = [extracted_title, roster_title]
    for candidate in candidates:
        cleaned = _strip_title_metadata(candidate)
        # Roster PDF filenames occasionally leak into the title column. They
        # are useful provenance, but not a human-facing case caption.
        cleaned = re.sub(r"^(?:(?:\d{4}-\d+[a-z]?|[,;&])\s*)+", "", cleaned)
        if cleaned and re.search(r"\bv\.(?:\s|$)", cleaned, re.I):
            return cleaned
    for candidate in candidates:
        cleaned = _strip_title_metadata(candidate)
        cleaned = re.sub(r"^(?:(?:\d{4}-\d+[a-z]?|[,;&])\s*)+", "", cleaned)
        if not cleaned or re.match(r"^[,._\-\d\s]+$", cleaned) or "_" in cleaned:
            continue
        return cleaned
    return ""


def normalize_disposition(raw):
    """Map observed legacy/editorial wording to the controlled outcome code."""
    text = str(raw or "").strip().lower().replace("-", " ").replace("_", " ")
    if not text:
        return None
    if "sustained in part" in text or "partially sustained" in text or "mixed" in text:
        return "partially_sustained"
    if "administratively out of order" in text or "found out of order" in text:
        return "out_of_order"
    if "not in order" in text or "out of order" in text:
        return "out_of_order"
    if "deemed abandoned" in text or "abandoned" in text or "withdrawn" in text:
        return "abandoned"
    if "not sustained" in text:
        return "not_sustained"
    if "declared invalid" in text or "invalid" in text:
        return "sustained"
    if "sustained" in text:
        return "sustained"
    if "denied" in text:
        return "denied"
    if "dismissed" in text:
        return "dismissed"
    if "remanded" in text or "remitted" in text or "referred back" in text:
        return "referred"
    if "referred" in text:
        return "referred"
    if "in order" in text:
        return "in_order"
    if "administrative" in text:
        return "administrative"
    if "granted" in text:
        return "granted"
    if "not acceded" in text:
        return "denied"
    return "other"


def select_outcome(raw_disposition, summary, roster_title):
    """Resolve generic/stale extracted labels with a clear editorial holding.

    The extractor sometimes records ``granted`` for an appeal whose judgment says
    ``sustained``, or ``dismissed`` for a case ultimately found out of order. Only
    strong phrases in the editorial summary override that generic label; a
    narrative such as "prepared to sustain ... then dismissed" does not.
    """
    raw_code = normalize_disposition(raw_disposition)
    summary_text = str(summary or "")
    generic = {None, "other", "granted"}
    title_code = normalize_disposition(roster_title)
    # A roster caption often carries the only short final action (for example,
    # "Found out of order"), while the extracted disposition is merely "other".
    if raw_code in generic and title_code and title_code != "other":
        raw_code = title_code
    if raw_code in generic and re.search(r"\b(?:not\s+in\s+order|out\s+of\s+order|not\s+in\s+the\s+form\s+of\s+a\s+complaint|AOO)\b", summary_text, re.I):
        return "out_of_order"
    if re.search(r"\b(?:partially\s+)?sustained\b", summary_text, re.I) and re.search(
            r"\b(?:denied|dismissed|moot|remand|referred|vacat|revers|acquit)", summary_text, re.I):
        if re.search(r"\bpartially\s+sustained\b|\bsustained\b[^.!?]{0,180}\b(?:denied|dismissed)\b|"
                     r"\b(?:denied|dismissed)\b[^.!?]{0,180}\bsustained\b", summary_text, re.I):
            return "partially_sustained"
    if raw_code in generic and re.search(r"\bsustained\b", summary_text, re.I):
        return "sustained"
    if raw_code in generic and re.search(r"\bacquit(?:ted|s)\b|\bnot guilty\b", summary_text, re.I):
        return "not_sustained"
    if raw_code in generic and re.search(r"\bfound\s+in\s+order\b", summary_text, re.I):
        return "in_order"
    if raw_code in generic and re.search(r"\b(?:remand|remitted|returned|referred back|sent back)\b", summary_text, re.I):
        return "referred"
    if raw_code in generic and re.search(r"\b(?:decided|answered)\s+by\s+reference\b", summary_text, re.I):
        return "referred"
    if raw_code in generic and re.search(r"\b(?:citation|responses?\s+(?:were\s+)?(?:acceptable|satisfactory)|resolved the citation)\b", summary_text, re.I):
        return "administrative"
    if raw_code in generic and re.search(r"\b(?:appointed|inspect|investigate|docket listing|judgment .* approved|special committee)\b", summary_text, re.I):
        return "administrative"
    if raw_code in generic and re.search(r"\bnot\s+sustained\s+the\s+(?:appeal|complaint)\b", summary_text, re.I):
        return "not_sustained"
    if raw_code in generic and re.search(r"\bpartially\s+sustained\s+the\s+(?:appeal|complaint)\b", summary_text, re.I):
        return "partially_sustained"
    if raw_code in generic and re.search(r"\bsustained\s+the\s+(?:appeal|complaint)\b", summary_text, re.I):
        return "sustained"
    if raw_code in generic | {"dismissed"} and re.search(
            r"\b(?:administratively\s+)?(?:found|ruled|held|determined|declared|dismissed)"
            r"\b[^.!?]{0,100}\b(?:out\s+of\s+order|not\s+in\s+order)\b", summary_text, re.I):
        return "out_of_order"
    if raw_code:
        return raw_code
    return title_code or "other"


def classify_proceeding_type(*values):
    """Classify the BCO vehicle from caption/header-level metadata.

    Do not search the synopsis or the whole decision: a reference, memorial,
    or citation may appear in the history of an ordinary complaint. Submission
    forms and court actions are retained as detail/basis metadata rather than
    promoted to competing primary case types.
    """
    text = " ".join(str(v or "") for v in values).lower()
    if re.search(r"\bappeal(?:ed|s|ing)?\b|\bappellant\b", text):
        return "appeal"
    if re.search(r"assume original jurisdiction|original jurisdiction", text):
        return "original_jurisdiction_request"
    if re.search(
        r"\b(?:bco\s*40\s*[-.]\s*5|review\s+and\s+control|"
        r"important\s+delinquency|grossly\s+unconstitutional\s+proceedings)\b",
        text,
    ):
        return "review_and_control"
    if re.search(r"\b(?:reference|referenced|judicial\s+reference)\b", text):
        return "reference"
    if re.search(r"\b(?:complaint|complainant|complained)\b|\bv\.\s*", text):
        return "complaint"
    if re.search(r"\bpetition\b", text) and re.search(r"\b(?:jurisdiction|assume|request)\b", text):
        return "original_jurisdiction_request"
    return "other"


def supervisory_ground(*values):
    """Return the distinct BCO 40-5 intervention ground, when present."""
    text = " ".join(str(v or "") for v in values).lower()
    if re.search(r"\bbco\s*40\s*[-.]\s*5\b", text) or re.search(
        r"\b(?:important\s+delinquency|grossly\s+unconstitutional\s+proceedings)\b",
        text,
    ):
        return "bco_40_5", "Important delinquency or grossly unconstitutional proceedings"
    return None, None


def roster_summary(title):
    m = re.search(r"\bSummary:\s*(.*)$", str(title or ""), re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip(" .") if m else ""


def normalize_bco_code(raw):
    """Normalize an extracted BCO citation to chapter-section.subsection form."""
    text = str(raw or "").strip().replace("–", "-").replace("—", "-")
    match = re.search(r"(?<!\d)(\d{1,2})\s*-\s*(\d{1,2})([^\s,;]*)", text)
    if not match:
        return None
    suffix = match.group(3).lower()
    suffix = re.split(r"(?:see|through|to)$", suffix, maxsplit=1, flags=re.I)[0]
    suffix = suffix.replace("(", ".").replace(")", "")
    suffix = re.sub(r"\[[^\]]*\]", "", suffix).replace("-", ".")
    suffix = re.sub(r"\s+", "", suffix).strip(".-")
    if suffix:
        suffix = "." + suffix
    return f"{int(match.group(1))}-{int(match.group(2))}{suffix}"


def bco_codes(*values):
    found = []
    for value in values:
        # Free-text titles include Minutes page ranges such as 48-50. Only
        # capture a roster title's code when it explicitly says BCO; extracted
        # records contribute their already-normalized bco_cited_as values below.
        for code in re.findall(r"\bBCO\s*(\d{1,2}-\d{1,2}(?:[.\-()]?[0-9A-Za-z]+)*)\b", str(value or ""), re.I):
            normalized = normalize_bco_code(code)
            if normalized and normalized not in found:
                found.append(normalized)
    return found


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def record_key(record):
    return canonical_id(record.get("canonical_number") or record.get("case_number"))


def record_score(record):
    return sum(bool(record.get(key)) for key in ("synopsis", "topics", "bco_cited_as", "parties", "title"))


def token_set(text):
    stop = {"appeal", "complaint", "case", "presbytery", "the", "and", "et", "al", "of", "v", "vs"}
    return {x.lower() for x in re.findall(r"[A-Za-z]{4,}", str(text or "")) if x.lower() not in stop}


def cjb_match(title, year, cjb_cases):
    """Find the best early-era CJB editorial note by caption and year."""
    wanted = token_set(_strip_title_metadata(title))
    best, best_score = None, 0
    for candidate in cjb_cases:
        if int(candidate.get("year") or 0) != int(year or 0):
            continue
        score = len(wanted & token_set(candidate.get("parties")))
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= 2 else None


def era_info(roster_title, year, cjb_pages):
    """Recover explicit early-era Case # and printed identifiers when possible."""
    wanted = token_set(_strip_title_metadata(roster_title))
    best = None
    best_score = 0
    for page in cjb_pages:
        if int(page.get("year") or 0) != int(year or 0):
            continue
        score = len(wanted & token_set(page.get("parties")))
        if score > best_score:
            best, best_score = page, score
    if not best or best_score < 2:
        return None, None, [], None
    file = best.get("file")
    case_number = None
    if file:
        path = os.path.join(ROOT, "cases", f"{file}.md")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as source:
                opening = source.read(12000)
            # Prefer the page's own case header. A later combined commission
            # report may mention several Case #N values and must not relabel the
            # page based on the first one it happens to mention.
            match = re.search(r"(?im)^\s*#\s*(\d+)\s+[—-]", opening[:1500])
            if not match:
                match = re.search(r"(?im)^\s*Case\s*#?\s*(\d+)\s*[:—-]", opening[:1500])
            case_number = int(match.group(1)) if match else None
    # The filename is an extraction artifact, not evidence of the Minutes'
    # era-based case number. Leave the era alias empty unless the source text
    # explicitly says "Case #N".
    era = f"case-{case_number}" if case_number is not None else None
    label = f"Case #{case_number}" if case_number is not None else None
    minute_ids = [x.strip() for x in re.split(r"/", str(best.get("number") or "")) if x.strip()]
    return era, label, minute_ids, file


def page_disposition(file):
    """Read the disposition printed in a generated case-page header, if present."""
    if not file:
        return None
    path = os.path.join(ROOT, "cases", f"{file}.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as source:
        head = source.read(1800)
    match = re.search(r"\*\*Disposition:\*\*\s*([^\n·]+)", head, re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip(" .") if match else None


def page_text(file):
    if not file:
        return ""
    path = os.path.join(ROOT, "cases", f"{file}.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as source:
        return source.read()


def case_page_headings(body):
    """Return caption/intro headings without appended manual material."""
    intro = re.split(
        r"(?im)^\s*#{1,6}\s+.*\b(?:PROPOSED\s+SJC\s+MANUAL\s+CHANGES|"
        r"SJC\s+MANUAL\s+CHANGES)\b.*$",
        str(body or ""),
        maxsplit=1,
    )[0]
    return " ".join(
        line.strip() for line in intro.splitlines()[:30]
        if line.lstrip().startswith("#")
    )


def decision_text(file):
    """Return the adopted decision, excluding separately labeled opinions.

    Separate opinions commonly restate BCO 39-3 while arguing for a different
    result. They are important source material, but their proposed standard is
    not the standard applied by the court. The heading boundary is deliberately
    conservative: if a page does not label a separate opinion, its text remains
    available for classification.
    """
    body = page_text(file)
    if not body:
        return ""
    boundary = re.search(
        r"(?im)^\s*#{1,6}\s+.*\b(?:DISSENT|CONCURRING|CONCURRENCE|"
        r"OBJECTION|PROTEST|SEPARATE\s+OPINION)\b.*$|"
        r"^\s*(?:DISSENT(?:ING)?|CONCURRING|CONCURRENCE)\s+OPINION\b.*$",
        body,
    )
    return body[:boundary.start()] if boundary else body


def _review_standard_from_override(raw, outcome=None):
    """Translate the pre-issue-level vocabulary used by older overrides."""
    text = str(raw or "").strip().lower()
    if text == "great_deference_clear_error":
        return ["clear_error_facts", "clear_error_discretion"]
    if text == "constitutional_interpretation_no_deference":
        return ["independent_constitutional"]
    if text == "mixed":
        return list(REVIEW_STANDARD_CODES)
    if text in REVIEW_STANDARD_CODES:
        return [text]
    return []


def _review_code(standards, body_available=True, outcome=None, proceeding_type=None):
    if not body_available:
        return "unknown"
    if standards:
        return standards[0] if len(standards) == 1 else "mixed"
    if outcome in {"out_of_order", "abandoned", "dismissed", "administrative", "in_order", "referred"}:
        return "not_reached"
    if proceeding_type == "original_jurisdiction_request":
        return "not_applicable"
    return "not_stated"


def _review_detail(standards, code, outcome=None, proceeding_type=None):
    details = {
        "clear_error_facts": "BCO 39-3.2: factual findings receive great deference; reversal requires clear error.",
        "clear_error_discretion": "BCO 39-3.3: matters of discretion and judgment receive great deference; reversal requires clear error.",
        "independent_constitutional": "BCO 39-3.4: the higher court interprets and applies the Church Constitution according to its best ability, without the same deference to the lower court.",
    }
    if code == "mixed":
        return "Issue-level standards: " + "; ".join(details[x] for x in standards)
    if code in details:
        return details[code]
    if code == "not_reached":
        return "The matter was resolved procedurally, administratively, abandoned, dismissed, or referred before merits review."
    if code == "not_applicable":
        return "No appellate standard applies to this original-jurisdiction request or other non-appellate proceeding."
    if code == "unknown":
        return "Decision text is not available locally; standard of review not yet verified."
    return "The available decision does not state a distinct standard of review."


def standard_of_review(file, outcome, proceeding_type=None, override=None):
    """Return display code, explanation, and issue-level standards.

    The list is authoritative. ``standard_of_review`` is retained as a compact
    compatibility/display field and is derived from that list.
    """
    body = decision_text(file)
    if not body:
        if override and (override.get("review_standards") is not None or override.get("standard_of_review")):
            standards = [x for x in (override.get("review_standards") or []) if x in REVIEW_STANDARD_CODES]
            if not standards:
                standards = _review_standard_from_override(override.get("standard_of_review"), outcome)
            raw_code = str(override.get("standard_of_review") or "").lower()
            if raw_code == "not_applicable" and outcome in {"out_of_order", "abandoned", "dismissed"}:
                code = "not_reached"
            elif raw_code in STANDARD_OF_REVIEW_CODES:
                code = raw_code
            elif standards:
                code = _review_code(standards, True, outcome, proceeding_type)
            else:
                code = _review_code(standards, True, outcome, proceeding_type)
            return code, override.get("standard_of_review_detail") or _review_detail(standards, code), standards
        return "unknown", _review_detail([], "unknown"), []

    if override and override.get("review_standards") is not None:
        standards = [x for x in override["review_standards"] if x in REVIEW_STANDARD_CODES]
    elif override and override.get("standard_of_review"):
        standards = _review_standard_from_override(override["standard_of_review"], outcome)
    else:
        standards = []
        if re.search(
            r"\b39\s*[-.]\s*3\s*[.(]?\s*2\b|"
            r"\b(?:factual\s+(?:finding|matter)|finding\s+of\s+fact)\b[^.!?]{0,180}\bclear\s+error\b|"
            r"\bclear\s+error\b[^.!?]{0,180}\b(?:factual\s+(?:finding|matter)|finding\s+of\s+fact)\b",
            body, re.I,
        ):
            standards.append("clear_error_facts")
        if re.search(
            r"\b(?:39\s*[-.]\s*3\s*[.(]?\s*3|great\s+deference|"
            r"matters?\s+of\s+discretion\s+and\s+judgment)\b",
            body, re.I,
        ) and re.search(r"\b(?:clear\s+error|deference|39\s*[-.]\s*3)\b", body, re.I):
            standards.append("clear_error_discretion")
        if re.search(
            r"\b(?:39\s*[-.]\s*3\s*[.(]?\s*4|constitutional\s+interpretation|"
            r"without\s+(?:the\s+same\s+|great\s+)?deference)\b",
            body, re.I,
        ):
            standards.append("independent_constitutional")

    standards = list(dict.fromkeys(standards))

    code = _review_code(standards, True, outcome, proceeding_type)
    if override and not standards:
        raw_code = str(override.get("standard_of_review") or "").lower()
        if raw_code == "not_applicable":
            code = "not_reached" if outcome in {"out_of_order", "abandoned", "dismissed"} else "not_applicable"
        elif raw_code in {"not_reached", "not_stated", "unknown"}:
            code = raw_code
    return code, _review_detail(standards, code, outcome, proceeding_type), standards


def main():
    roster = load_jsonl(ROSTER)
    # The saved Historical Center pages repeat a small number of rows. Collapse
    # those source duplicates before producing the one-row-per-case layer; keep
    # the richer/longer title because it may carry the only editorial summary.
    unique_roster = {}
    unknown_roster = []
    for official in roster:
        key = canonical_id(official.get("case_number") or official.get("case_number_raw"))
        if not key:
            unknown_roster.append(official)
            continue
        previous = unique_roster.get(key)
        if previous is None or len(str(official.get("title") or "")) > len(str(previous.get("title") or "")):
            unique_roster[key] = official
    roster = list(unique_roster.values()) + unknown_roster
    extracted = load_jsonl(CASES)
    cjb_pages = json.load(open(CJB_PAGES, encoding="utf-8")) if os.path.exists(CJB_PAGES) else []
    cjb_cases = []
    if os.path.exists(CJB_CASES):
        for volume in json.load(open(CJB_CASES, encoding="utf-8")):
            match = re.search(r"_(\d{4})$", str(volume.get("vol") or ""))
            year = int(match.group(1)) if match else None
            for candidate in volume.get("cases") or []:
                cjb_cases.append({**candidate, "year": year})
    page_map = {}
    if os.path.exists(PAGE_MAP):
        with open(PAGE_MAP, encoding="utf-8") as source:
            page_map = json.load(source)
    editorial_overrides = {}
    if os.path.exists(EDITORIAL_OVERRIDES):
        with open(EDITORIAL_OVERRIDES, encoding="utf-8") as source:
            editorial_overrides = json.load(source)
    summary_audits = {}
    if os.path.exists(SUMMARY_AUDITS):
        with open(SUMMARY_AUDITS, encoding="utf-8") as source:
            summary_audits = json.load(source)
    by_key = defaultdict(list)
    for record in extracted:
        key = record_key(record)
        if key:
            by_key[key].append(record)

    rows = []
    for official in roster:
        cid = canonical_id(official.get("case_number") or official.get("case_number_raw"))
        matches = sorted(by_key.get(cid, []), key=record_score, reverse=True) if cid else []
        record = matches[0] if matches else {}
        raw_title = official.get("title") or record.get("title") or ""
        cjb = cjb_match(raw_title, official.get("year"), cjb_cases)
        title = clean_title(raw_title, (cjb or {}).get("parties") or record.get("title"))
        summary = record.get("synopsis") or roster_summary(raw_title) or (cjb or {}).get("notes") or None
        override = editorial_overrides.get(cid, {}) if cid else {}
        audit = summary_audits.get(cid, {}) if cid else {}
        title = override.get("title") or title
        summary = override.get("summary") or summary
        era, era_label, minute_ids, era_file = era_info(raw_title, official.get("year"), cjb_pages)
        page_entry = page_map.get(cid) or page_map.get(legacy_id(cid)) if cid else None
        page_file = page_entry.get("file") if page_entry else era_file
        page_body = page_text(page_file)
        page_header = page_body[:2400]
        page_headings = case_page_headings(page_body)
        posture = override.get("proceeding_type") or classify_proceeding_type(
            raw_title, title, record.get("title"), page_headings
        )
        ground, ground_detail = supervisory_ground(
            raw_title, title, record.get("title"), page_headings
        )
        if posture != "review_and_control" and not override.get("supervisory_ground"):
            ground, ground_detail = None, None
        elif posture == "review_and_control" and not ground and re.search(
            r"\bmemorial\b", " ".join((raw_title, title, record.get("title") or "")), re.I
        ):
            ground, ground_detail = "bco_40_5", "Important delinquency or grossly unconstitutional proceedings"
        detail = page_disposition(page_file) or record.get("disposition") or (cjb or {}).get("disposition") or (raw_title if matches else "")
        detail = override.get("disposition_detail") or detail
        outcome = override.get("outcome") or select_outcome(detail, summary, raw_title)
        review_code, review_detail, review_standards = standard_of_review(
            page_file, outcome, posture, override
        )
        review_detail = override.get("standard_of_review_detail") or review_detail
        ground = override.get("supervisory_ground") or ground
        ground_detail = override.get("supervisory_ground_detail") or ground_detail
        bco = []
        for raw_code in (record.get("bco_cited_as") or []):
            normalized = normalize_bco_code(raw_code)
            if normalized and normalized not in bco:
                bco.append(normalized)
        for code in bco_codes(raw_title, summary, record.get("topics")):
            if code not in bco:
                bco.append(code)
        topics = list(override.get("topic_tags") or record.get("topics") or [])
        bco = list(override.get("bco_provisions") or bco)
        classification_status = "classified"
        if not cid:
            classification_status = "roster_only"
        elif not matches and not cjb:
            classification_status = "roster_only"
        elif outcome == "other" or posture == "other":
            classification_status = "needs_review"
        rows.append({
            "roster_id": official.get("case_number_raw") or official.get("case_number"),
            "case_id": cid,
            "legacy_case_id": legacy_id(cid),
            "era_id": era,
            "era_label": era_label,
            "minute_ids": minute_ids,
            "title": title,
            "proceeding_type": posture,
            "outcome": outcome,
            "disposition": outcome,
            "disposition_detail": detail or None,
            "standard_of_review": review_code,
            "standard_of_review_detail": review_detail,
            "review_standards": review_standards,
            "supervisory_ground": ground,
            "supervisory_ground_detail": ground_detail,
            "summary": summary,
            "summary_review_status": override.get("summary_review_status") or audit.get("summary_review_status") or ("audited" if override.get("summary") else "pending_audit"),
            "bco_provisions": bco,
            "topic_tags": topics,
            "body": record.get("body") or ("CJB" if int(official.get("year") or 9999) <= 1987 else "SJC"),
            "decision_year": record.get("year") or official.get("year"),
            "assembly": record.get("ga_ordinal"),
            "dissent": bool(record.get("has_dissent")),
            "case_page": page_file,
            "official_pdf_url": official.get("pdf_url"),
            "classification_status": classification_status,
            "summary_source": override.get("summary_source") or audit.get("summary_source") or ("editorial_override" if override.get("summary") else None),
            "summary_audit_basis": override.get("summary_audit_basis") or audit.get("summary_audit_basis"),
        })

    rows.sort(key=lambda row: (row["case_id"] is None, row["case_id"] or row["roster_id"] or ""))
    with open(OUT, "w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[taxonomy] wrote {len(rows)} canonical judicial cases from {len(load_jsonl(ROSTER))} roster entries -> {OUT}")
    counts = defaultdict(int)
    for row in rows:
        counts[row["classification_status"]] += 1
    print("           status=" + ", ".join(f"{k}:{counts[k]}" for k in sorted(counts)))
    print("           proceeding_types=" + ", ".join(f"{k}:{sum(r['proceeding_type'] == k for r in rows)}" for k in PROCEEDING_TYPES))
    print("           outcomes=" + ", ".join(f"{k}:{sum(r['outcome'] == k for r in rows)}" for k in OUTCOMES))


if __name__ == "__main__":
    main()
