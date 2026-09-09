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
    "complaint", "appeal", "reference", "original_jurisdiction_request",
    "constitutional_matter", "petition", "citation", "memorial",
    "administrative_review", "other",
)
OUTCOMES = (
    "sustained", "partially_sustained", "not_sustained", "denied", "dismissed",
    "out_of_order", "in_order", "administrative", "referred", "granted",
    "abandoned", "other",
)
STANDARD_OF_REVIEW_CODES = (
    "great_deference_clear_error",
    "constitutional_interpretation_no_deference",
    "mixed",
    "not_applicable",
    "not_stated",
    "unknown",
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
    """Classify procedural posture from caption and metadata, in priority order."""
    text = " ".join(str(v or "") for v in values).lower()
    if re.search(r"\bappeal(?:ed|s|ing)?\b|\bappellant\b", text):
        return "appeal"
    if re.search(r"assume original jurisdiction|original jurisdiction", text):
        return "original_jurisdiction_request"
    if re.search(r"\b(reference|referenced|judicial reference)\b", text):
        return "reference"
    if re.search(r"\b(constitutional matter|bco\s*40[- ]5|matter re:)\b", text):
        return "constitutional_matter"
    if re.search(r"\bpetition\b", text):
        return "petition"
    if re.search(r"\bcitation\b", text):
        return "citation"
    if re.search(r"\bmemorial\b", text):
        return "memorial"
    if re.search(r"\bin\s+re\b", text):
        return "administrative_review"
    if re.search(r"\bcomplaint|complainant|complained\b|\bv\.\s*", text):
        return "complaint"
    return "other"


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


def standard_of_review(file, outcome):
    """Classify the review standard stated in the available decision text."""
    body = page_text(file)
    if not body:
        return "unknown", "Decision text is not available locally; standard of review not yet verified."
    deference = bool(re.search(
        r"\b(?:great\s+deference|clear\s+error|39\s*[-.]\s*3\s*[.(]?\s*[23])\b|"
        r"matters?\s+of\s+discretion\s+and\s+judgment", body, re.I
    ))
    constitutional = bool(re.search(
        r"\b(?:39\s*[-.]\s*3\s*[.(]?\s*4|constitutional\s+interpretation|"
        r"without\s+(?:great\s+)?deference)\b", body, re.I
    ))
    if deference and constitutional:
        return "mixed", "Great deference applies to factual and discretionary matters, while constitutional interpretation receives no such deference (BCO 39-3(2)-(4))."
    if deference:
        return "great_deference_clear_error", "Great deference applies to factual and discretionary matters; reversal requires clear error (BCO 39-3(2)-(3))."
    if constitutional:
        return "constitutional_interpretation_no_deference", "Constitutional interpretation receives no deference of the kind applicable to factual or discretionary matters (BCO 39-3(4))."
    if outcome in {"out_of_order", "administrative", "abandoned", "dismissed"}:
        return "not_applicable", "No merits standard of review was necessary; the matter was resolved procedurally or administratively."
    return "not_stated", "No distinct standard of review is stated in the available decision text."


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
        posture = classify_proceeding_type(raw_title, title, record.get("title"), (cjb or {}).get("parties"), record.get("parties"), record.get("description"), record.get("synopsis"))
        era, era_label, minute_ids, era_file = era_info(raw_title, official.get("year"), cjb_pages)
        page_entry = page_map.get(cid) or page_map.get(legacy_id(cid)) if cid else None
        page_file = page_entry.get("file") if page_entry else era_file
        detail = page_disposition(page_file) or record.get("disposition") or (cjb or {}).get("disposition") or (raw_title if matches else "")
        detail = override.get("disposition_detail") or detail
        outcome = override.get("outcome") or select_outcome(detail, summary, raw_title)
        review_code, review_detail = standard_of_review(page_file, outcome)
        review_code = override.get("standard_of_review") or review_code
        review_detail = override.get("standard_of_review_detail") or review_detail
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
