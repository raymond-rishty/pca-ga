#!/usr/bin/env python3
"""Find likely judicial-case identity mismatches without changing the corpus.

The Historical Center roster is an important checklist, but some early roster
IDs use a decision year or otherwise disagree with the docket printed in the
minutes.  This audit compares roster captions, extracted cases, the canonical
taxonomy, early ``Case #N`` labels, and explicit later ``Case YY-N`` citations.

The default command writes an inspectable JSON report and a compact Markdown
report.  ``--write-candidates`` also writes a starter override file.  Candidate
overrides are deliberately marked ``needs_review``; this script never changes
case IDs or source files.

Usage::

    python scripts/78_audit_case_identities.py
    python scripts/78_audit_case_identities.py --max-year 1995 --write-candidates
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STOP_WORDS = {
    "a", "against", "al", "and", "appeal", "case", "church", "complaint",
    "et", "in", "jr", "of", "presbyterian", "presbytery", "re", "rev",
    "session", "sr", "te", "the", "v", "vs",
}
GENERIC_TITLE_TOKENS = {
    "central", "eastern", "florida", "grace", "north", "south", "southern",
    "valley", "western",
}
EXPLICIT_DOCKET = re.compile(
    r"\b(?:Judicial\s+)?Case(?:\s+(?:No\.?|Number))?\s+"
    r"(?P<year>\d{2}|\d{4})\s*[-‐‑‒–—]\s*"
    r"(?P<number>\d{1,3})(?P<suffix>[a-z]?)\b",
    re.IGNORECASE,
)
CASE_PAGE_HEADER = re.compile(
    r"^#\s+(?P<case_id>\d{4}-\d{1,3}[a-z]?)\s+[—–-]\s+(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
TOP_BODY_DOCKET = re.compile(
    r"^\s*(?P<quote>>\s*)?(?P<heading>#{2,6}\s*)?(?:\*{0,2})?"
    r"(?:CASE(?:\s+NO\.?)?\s*)?(?P<year>\d{4})\s*[-‐‑‒–—]\s*"
    r"(?P<number>\d{1,3})(?P<suffix>[a-z]?)\b"
    r"\s*(?:[:—–-]\s*)?(?P<caption>.*)$",
    re.IGNORECASE,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_source_line"] = line_number
        rows.append(row)
    return rows


def canonical_id(raw: Any) -> str | None:
    match = re.fullmatch(r"\s*(\d{4})-(\d{1,3})([a-z]?)\s*", str(raw or ""), re.I)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}{match.group(3).lower()}"


def explicit_id(year: str, number: str, suffix: str = "") -> str:
    value = int(year)
    if len(year) == 2:
        value += 1900 if value >= 70 else 2000
    return f"{value:04d}-{int(number):02d}{suffix.lower()}"


def clean_caption(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\[[^\]]*]", " ", text)
    text = re.split(r"\s+Summary\s*:", text, maxsplit=1, flags=re.I)[0]
    text = re.split(r"\s+[—–-]\s+(?:M\s*\d+\s*GA|Decided|Sustained|Not\s+Sustained|Dismissed)",
                    text, maxsplit=1, flags=re.I)[0]
    text = re.split(
        r"\.\s+(?:Decided|Sustained|Not\s+Sustained|Denied|Dismissed|"
        r"Administratively\s+Out\s+of\s+Order|Judicially\s+Out\s+of\s+Order)\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    text = re.sub(r"\([^)]*(?:appeal|complaint|case\s*#|M\d+GA|p\.\s*\d+)[^)]*\)", " ", text,
                  flags=re.I)
    text = re.sub(r"\([^)]*(?:charismatic gifts|candidate|church)[^)]*\)$", " ", text,
                  flags=re.I)
    text = re.sub(r"^\s*(?:Case\s*#?\s*\d+[a-z]?\s*:\s*)", "", text, flags=re.I)
    text = re.sub(r"^\s*(?:Appeal|Complaint|Petition)(?:\s+of)?\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\bvs?\.?\b", " v ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" .,:;-—")


def title_tokens(value: Any) -> set[str]:
    text = clean_caption(value).casefold()
    words = re.findall(r"[a-z0-9]+", text)
    return {word for word in words if len(word) > 1 and word not in STOP_WORDS}


def title_score(left: Any, right: Any) -> float:
    a, b = title_tokens(left), title_tokens(right)
    if not a or not b:
        return 0.0
    overlap = a & b
    score = 2 * len(overlap) / (len(a) + len(b))
    distinctive_a = a - GENERIC_TITLE_TOKENS
    distinctive_b = b - GENERIC_TITLE_TOKENS
    if distinctive_a and distinctive_b and not (distinctive_a & distinctive_b):
        score *= 0.45
    return round(score, 4)


def citation_title_score(title: Any, context: Any) -> float:
    """Score whether a short caption is contained in a longer citation line."""
    caption, line = title_tokens(title), title_tokens(context)
    if not caption or not line:
        return 0.0
    overlap = caption & line
    distinctive = (caption - GENERIC_TITLE_TOKENS) & line
    if not distinctive:
        return 0.0
    return round(len(overlap) / len(caption), 4)


def disposition_quality(row: dict[str, Any]) -> int:
    disposition = str(row.get("disposition") or "").lower()
    synopsis = str(row.get("synopsis") or "")
    description = str(row.get("description") or "")
    return (
        (4 if disposition not in {"", "other", "administrative", "pending"} else 0)
        + min(len(synopsis) // 80, 4)
        + min(len(description) // 1000, 4)
        + (2 if row.get("bco_cited_as") else 0)
    )


def best_matches(title: str, cases: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    matches = []
    for case in cases:
        score = title_score(title, case.get("title"))
        if score:
            matches.append({
                "case_id": canonical_id(case.get("case_id") or case.get("case_number")),
                "title": case.get("title"),
                "score": score,
                "source_line": case.get("_source_line"),
                "quality": disposition_quality(case),
            })
    matches.sort(key=lambda item: (item["score"], item["quality"]), reverse=True)
    return matches[:limit]


def scan_explicit_citations(root: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for folder in (root / "cases", root / "markdown"):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                for match in EXPLICIT_DOCKET.finditer(line):
                    evidence.append({
                        "case_id": explicit_id(match.group("year"), match.group("number"), match.group("suffix")),
                        "path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "text": re.sub(r"\s+", " ", line).strip()[:500],
                    })
    return evidence


def scan_case_page_identity(root: Path) -> list[dict[str, Any]]:
    """Compare each case-page heading with the first caption in its own body.

    The caption printed at the start of the decision or status notice is the
    strongest local identity evidence.  Later citations can corroborate it,
    but cannot cure a mismatch at the top of the source body.
    """
    findings: list[dict[str, Any]] = []
    for path in sorted((root / "cases").glob("*.md")):
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        header_match = next((CASE_PAGE_HEADER.match(line) for line in lines[:8]
                             if CASE_PAGE_HEADER.match(line)), None)
        if not header_match:
            continue
        header_id = canonical_id(header_match.group("case_id"))
        header_title = clean_caption(header_match.group("title"))
        body_match = None
        body_line_number = None
        body_title = None
        for line_number, line in enumerate(lines[1:121], 2):
            candidate = TOP_BODY_DOCKET.match(line)
            if not candidate:
                continue
            caption = clean_caption(candidate.group("caption"))
            if candidate.group("heading"):
                # Official decisions often put "CASE NO. YYYY-NN" on one
                # heading and the party caption on the next.  Bind those
                # headings and stop before any later cited-case headings.
                if len(title_tokens(caption)) < 2:
                    for following in lines[line_number:line_number + 3]:
                        heading = re.match(r"^\s*#{2,6}\s+(?P<caption>.+)$", following)
                        if heading and len(title_tokens(heading.group("caption"))) >= 2:
                            caption = clean_caption(heading.group("caption"))
                            break
                body_match = candidate
                body_line_number = line_number
                body_title = caption
                break
            # Ignore bare docket lists and status-only references.  Identity
            # evidence needs a caption-like phrase, not merely another number.
            if len(title_tokens(caption)) < 2:
                continue
            caption_like = bool(re.search(
                r"\b(?:v(?:s)?\.?|presbytery|session|complaint|appeal|request|citation)\b",
                caption,
                re.I,
            ))
            if not candidate.group("quote") or not caption_like:
                continue
            if re.match(r"^(?:and\s+)?\d{4}\s*[-‐‑‒–—]\s*\d+", caption, re.I):
                continue
            if re.match(r"^(?:and|was|were|is|are|has|have)\b", caption, re.I):
                continue
            body_match = candidate
            body_line_number = line_number
            body_title = caption
            break
        if not body_match:
            continue
        body_id = explicit_id(
            body_match.group("year"), body_match.group("number"), body_match.group("suffix")
        )
        body_title = body_title or clean_caption(body_match.group("caption"))
        score = title_score(header_title, body_title)
        flags: list[str] = []
        if body_id != header_id:
            flags.append("case_page_body_docket_conflict")
        distinctive_overlap = (
            (title_tokens(header_title) - GENERIC_TITLE_TOKENS)
            & (title_tokens(body_title) - GENERIC_TITLE_TOKENS)
        )
        if (body_id == header_id and len(title_tokens(body_title)) >= 2
                and score < 0.35 and not distinctive_overlap):
            flags.append("case_page_body_caption_conflict")
        if not flags:
            continue
        findings.append({
            "kind": "case_page_source_conflict",
            "confidence": "high",
            "case_id": header_id,
            "title": header_title,
            "case_page": path.relative_to(root).as_posix(),
            "header_case_id": header_id,
            "header_title": header_title,
            "body_case_id": body_id,
            "body_title": body_title,
            "body_title_score": score,
            "body_locator": f"{path.relative_to(root).as_posix()}:{body_line_number}",
            "flags": flags,
            "suggested_canonical_id": body_id,
            "suggested_corrected_title": body_title,
            "suggestion_reasons": ["top-of-body docket caption conflicts with the page heading"],
            "suggested_override": None,
        })
    return findings


def citation_matches(title: str, citations: list[dict[str, Any]], minimum: float) -> list[dict[str, Any]]:
    matches = []
    for citation in citations:
        score = citation_title_score(title, citation["text"])
        if score >= minimum:
            matches.append({**citation, "title_score": score})
    matches.sort(key=lambda item: item["title_score"], reverse=True)
    unique: dict[tuple[str, str, int], dict[str, Any]] = {}
    for item in matches:
        unique.setdefault((item["case_id"], item["path"], item["line"]), item)
    return list(unique.values())[:8]


def era_suffix(case_id: str | None) -> str | None:
    match = re.search(r"-(\d+)([a-z]?)$", str(case_id or ""), re.I)
    return f"{int(match.group(1))}{match.group(2).lower()}" if match else None


def era_number(era_id: Any) -> str | None:
    match = re.fullmatch(r"case-(\d+)([a-z]?)", str(era_id or ""), re.I)
    return f"{int(match.group(1))}{match.group(2).lower()}" if match else None


def load_identity_rules(root: Path) -> list[dict[str, Any]]:
    path = root / "index/case_identity_overrides.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rules = payload.get("overrides", []) if isinstance(payload, dict) else payload
    return [rule for rule in rules if rule.get("status") == "approved"]


def resolved_identity(raw_id: Any, title: Any, rules: list[dict[str, Any]]) -> str | None:
    """Apply the same caption-sensitive identity rules as the taxonomy builder."""
    source_id = canonical_id(raw_id)
    caption = str(title or "").casefold()
    for rule in rules:
        if canonical_id(rule.get("roster_id")) != source_id:
            continue
        discriminator = str(rule.get("title_contains") or "").strip().casefold()
        if discriminator and discriminator not in caption:
            continue
        corrected = canonical_id(rule.get("canonical_id"))
        if corrected:
            return corrected
    return source_id


def resolved_roster_title(raw_id: Any, title: Any, rules: list[dict[str, Any]]) -> str:
    source_id = canonical_id(raw_id)
    original = str(title or "")
    for rule in rules:
        if canonical_id(rule.get("roster_id")) != source_id:
            continue
        discriminator = str(rule.get("title_contains") or "").strip().casefold()
        if discriminator and discriminator not in original.casefold():
            continue
        if rule.get("corrected_title"):
            return str(rule["corrected_title"])
    return original


def audit(root: Path, max_year: int | None, minimum: float, strong: float) -> dict[str, Any]:
    roster = load_jsonl(root / "index/sjc_official/roster.jsonl")
    extracted = load_jsonl(root / "index/cases.jsonl")
    canonical = load_jsonl(root / "index/judicial_cases.jsonl")
    identity_rules = load_identity_rules(root)
    # Keep the complete canonical ID set for representation checks.  The year
    # window limits source review; it must not make later decisions appear absent.
    all_canonical_ids = {canonical_id(row.get("case_id")) for row in canonical}
    if max_year is not None:
        roster = [row for row in roster if int(row.get("year") or 9999) <= max_year]

    citations = scan_explicit_citations(root)
    extracted_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in extracted:
        case_id = resolved_identity(
            row.get("case_id") or row.get("case_number"), row.get("title"), identity_rules
        )
        if case_id:
            extracted_by_id[case_id].append(row)
    canonical_ids = all_canonical_ids
    canonical_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in canonical:
        case_id = canonical_id(row.get("case_id"))
        if case_id:
            canonical_by_id[case_id].append(row)

    findings: list[dict[str, Any]] = []
    for roster_index, row in enumerate(roster):
        raw_roster_id = canonical_id(row.get("case_number_raw") or row.get("case_number"))
        raw_title = str(row.get("title") or "")
        effective_title = resolved_roster_title(raw_roster_id, raw_title, identity_rules)
        # Audit the source roster caption, not an already-corrected display
        # caption.  Otherwise a durable override can hide the upstream error
        # this report is intended to expose.
        title = raw_title
        roster_id = resolved_identity(raw_roster_id, raw_title, identity_rules)
        same = extracted_by_id.get(roster_id or "", []) + canonical_by_id.get(roster_id or "", [])
        same_score = max((title_score(title, item.get("title")) for item in same), default=0.0)
        matches = best_matches(title, extracted)
        best = matches[0] if matches else None
        cross = None
        # A later case between the same parties is not identity evidence when
        # the current ID already has a plausible caption match.  The lower
        # conflict threshold also tolerates spelling variants such as
        # Sartorius/Sartorious.
        if not same:
            cross = best if best and resolved_identity(best["case_id"], best["title"], identity_rules) != roster_id else next(
                (item for item in matches
                 if resolved_identity(item["case_id"], item["title"], identity_rules) != roster_id), None
            )
            if cross:
                cross = {**cross, "case_id": resolved_identity(cross["case_id"], cross["title"], identity_rules)}
        cites = citation_matches(title, citations, minimum)
        cited_ids = Counter(item["case_id"] for item in cites)
        # A caption can recur in unrelated later litigation.  Citation evidence
        # becomes actionable only when it corroborates the best independently
        # extracted cross-ID match (or is the sole evidence for a missing row).
        cited_id = cross["case_id"] if cross and cross["case_id"] in cited_ids else None
        if not cited_id and not same and len(cited_ids) == 1:
            cited_id = next(iter(cited_ids))
        cited_support = cited_ids.get(cited_id, 0) if cited_id else 0
        flags: list[str] = []
        if same and same_score < 0.35:
            flags.append("same_id_caption_conflict")
        if not same:
            flags.append("no_same_id_extracted_case")
        if cross and cross["score"] >= strong:
            flags.append("strong_cross_id_caption_match")
        elif cross and cross["score"] >= minimum:
            flags.append("possible_cross_id_caption_match")
        if cited_id and cited_id != roster_id:
            flags.append("explicit_citation_disagrees_with_roster")

        suggestion = None
        corrected_title = None
        reasons: list[str] = []
        # If the same docket is independently present in the minutes-derived
        # corpus, a conflicting Historical Center caption is a caption repair,
        # not evidence that the docket itself should be reassigned.  Recurring
        # litigants make cross-ID title matches unsafe for this situation.
        if same and same_score < 0.35:
            same_best = max(
                same,
                key=lambda item: (disposition_quality(item), len(str(item.get("title") or ""))),
            )
            corrected_title = str(same_best.get("title") or "").strip() or None
            suggestion = roster_id
            reasons.append("same docket in the minutes-derived corpus has a conflicting caption")
        elif not same and cited_id and cited_id != roster_id and cited_support >= 1:
            candidate_score = next((item["score"] for item in matches if item["case_id"] == cited_id), 0.0)
            if candidate_score >= minimum or (cross and cross["case_id"] == cited_id):
                suggestion = cited_id
                reasons.append("explicit citation and caption agree")
        if not suggestion and not same and cross and cross["score"] >= strong:
            suggestion = cross["case_id"]
            reasons.append("strong caption match conflicts with absent or different same-ID record")
        if not flags:
            continue
        confidence = "high" if suggestion and (
            "explicit_citation_disagrees_with_roster" in flags
            or "same_id_caption_conflict" in flags
        ) else "medium" if suggestion else "review"
        findings.append({
            "kind": "roster_reconciliation",
            "confidence": confidence,
            "roster_id": roster_id,
            "roster_id_raw_normalized": raw_roster_id,
            "roster_id_raw": row.get("case_number_raw") or row.get("case_number"),
            "roster_title": title,
            "effective_roster_title": effective_title,
            "roster_year": row.get("year"),
            "roster_source_line": row.get("_source_line"),
            "same_id_title_score": same_score,
            "same_id_cases": [
                {"case_id": roster_id, "title": item.get("title"), "source_line": item.get("_source_line")}
                for item in same
            ],
            "best_extracted_matches": matches,
            "explicit_citations": cites,
            "flags": flags,
            "suggested_canonical_id": suggestion,
            "suggested_corrected_title": corrected_title,
            "suggestion_reasons": reasons,
            "suggested_override": ({
                "status": "needs_review",
                "roster_id": roster_id,
                "title_contains": next(iter(sorted(title_tokens(title) - GENERIC_TITLE_TOKENS)), ""),
                "canonical_id": suggestion,
                **({"corrected_title": corrected_title} if corrected_title else {}),
                "evidence": (
                    [f"{item['path']}:{item['line']}" for item in cites if item["case_id"] == suggestion][:3]
                    or [f"index/cases.jsonl:{item['_source_line']}" for item in same if item.get("_source_line")][:2]
                ),
                "note": "; ".join(reasons),
            } if suggestion else None),
        })

    represented_titles = [(row.get("title"), canonical_id(row.get("case_id"))) for row in canonical]
    for row in extracted:
        case_id = resolved_identity(
            row.get("case_id") or row.get("case_number"), row.get("title"), identity_rules
        )
        if max_year is not None and case_id and int(case_id[:4]) > max_year:
            continue
        if not case_id or case_id in canonical_ids or disposition_quality(row) < 4:
            continue
        best_catalog_score = max((title_score(row.get("title"), title) for title, _ in represented_titles), default=0)
        roster_matches = best_matches(str(row.get("title") or ""), roster)
        findings.append({
            "kind": "unrepresented_extracted_case",
            "confidence": "high" if best_catalog_score < 0.35 else "review",
            "case_id": case_id,
            "title": row.get("title"),
            "year": row.get("year"),
            "source_line": row.get("_source_line"),
            "quality": disposition_quality(row),
            "best_catalog_title_score": best_catalog_score,
            "best_roster_matches": roster_matches,
            "flags": ["substantive_extracted_case_absent_from_canonical_catalog"],
            "suggested_canonical_id": None,
            "suggested_override": None,
        })

    findings.extend(scan_case_page_identity(root))

    rank = {"high": 0, "medium": 1, "review": 2}
    findings.sort(key=lambda item: (
        rank.get(item.get("confidence", "review"), 9),
        item.get("roster_id") or item.get("case_id") or "",
        item["kind"],
    ))
    counts = Counter(item["kind"] for item in findings)
    flag_counts = Counter(flag for item in findings for flag in item.get("flags", []))
    return {
        "schema_version": 1,
        "policy": {
            "description": "Identity discrepancies are candidates, not automatic corrections.",
            "evidence_order": [
                "case's own docket caption at the top of the decision or status notice",
                "explicit year-based docket in the decision",
                "later SJC/GA citation pairing caption and year-based docket",
                "contemporary Case #N era label",
                "Historical Center roster fallback",
            ],
            "title_score_minimum": minimum,
            "title_score_strong": strong,
            "max_roster_year": max_year,
        },
        "summary": {
            "roster_rows_checked": len(roster),
            "extracted_rows_checked": len(extracted),
            "canonical_rows_checked": len(canonical),
            "explicit_citations_scanned": len(citations),
            "findings": len(findings),
            "high_confidence": sum(item.get("confidence") == "high" for item in findings),
            "medium_confidence": sum(item.get("confidence") == "medium" for item in findings),
            "by_kind": dict(sorted(counts.items())),
            "by_flag": dict(sorted(flag_counts.items())),
        },
        "findings": findings,
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Judicial Case Identity Audit",
        "",
        "This report identifies candidates for source review. It does not establish that every",
        "canonical/era mismatch is erroneous and does not modify the corpus.",
        "",
        f"- Findings: {summary['findings']}",
        f"- High confidence: {summary['high_confidence']}",
        f"- Medium confidence: {summary['medium_confidence']}",
        f"- Roster rows checked: {summary['roster_rows_checked']}",
        "",
        "| Confidence | Roster/current ID | Suggested ID | Caption | Signals | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for item in report["findings"]:
        current = item.get("roster_id") or item.get("case_id") or "—"
        suggestion = item.get("suggested_canonical_id") or "—"
        title = str(item.get("roster_title") or item.get("title") or "").replace("|", "\\|")
        flags = ", ".join(item.get("flags", [])).replace("_", " ")
        evidence = "; ".join(
            f"{entry['path']}:{entry['line']}" for entry in item.get("explicit_citations", [])[:3]
        ) or str(item.get("case_page") or "—")
        lines.append(
            f"| {item.get('confidence', 'review')} | `{current}` | `{suggestion}` | "
            f"{title} | {flags} | {evidence} |"
        )
    lines.extend([
        "",
        "## Review procedure",
        "",
        "1. Confirm a proposed ID against the decision heading and any explicit later citation.",
        "2. Treat `Case #N` as an era ID; do not force it to equal the canonical suffix.",
        "3. Review the whole collision chain before approving one mapping.",
        "4. Move approved entries into the durable identity-override file used by the taxonomy builder.",
        "5. Regenerate the case indexes and verify that no substantive extracted case disappeared.",
        "",
    ])
    return "\n".join(lines)


def promote_approved(root: Path, candidates_path: Path, overrides_path: Path) -> int:
    """Merge explicitly approved candidates into the durable override file."""
    if not candidates_path.exists():
        raise SystemExit(f"candidate file does not exist: {candidates_path}")
    payload = json.loads(candidates_path.read_text(encoding="utf-8-sig"))
    rules = payload.get("overrides", []) if isinstance(payload, dict) else payload
    approved = [rule for rule in rules if rule.get("status") == "approved"]
    if not approved:
        raise SystemExit("no candidate overrides are marked approved")
    for rule in approved:
        if not canonical_id(rule.get("roster_id")):
            raise SystemExit(f"approved override has an invalid roster_id: {rule!r}")
        if not canonical_id(rule.get("canonical_id")):
            raise SystemExit(f"approved override has an invalid canonical_id: {rule!r}")
        if not str(rule.get("title_contains") or "").strip():
            raise SystemExit(f"approved override needs title_contains: {rule!r}")
        if not rule.get("evidence"):
            raise SystemExit(f"approved override needs at least one evidence locator: {rule!r}")

    existing: list[dict[str, Any]] = []
    if overrides_path.exists():
        prior = json.loads(overrides_path.read_text(encoding="utf-8-sig"))
        existing = prior.get("overrides", []) if isinstance(prior, dict) else prior
    merged = {
        (canonical_id(rule.get("roster_id")), str(rule.get("title_contains") or "").casefold()): rule
        for rule in existing
    }
    for rule in approved:
        clean = dict(rule)
        clean["status"] = "approved"
        clean["roster_id"] = canonical_id(rule["roster_id"])
        clean["canonical_id"] = canonical_id(rule["canonical_id"])
        merged[(clean["roster_id"], clean["title_contains"].casefold())] = clean
    ordered = sorted(merged.values(), key=lambda rule: (
        rule.get("roster_id", ""), rule.get("title_contains", "")
    ))
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_path.write_text(json.dumps({
        "schema_version": 1,
        "description": "Audited caption-sensitive corrections to Historical Center roster IDs.",
        "overrides": ordered,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(approved)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-year", type=int, default=0,
                        help="latest roster year to audit; use 0 for all years (default: all years)")
    parser.add_argument("--min-title-score", type=float, default=0.62)
    parser.add_argument("--strong-title-score", type=float, default=0.82)
    parser.add_argument("--json", type=Path, default=Path("index/case_identity_audit.json"))
    parser.add_argument("--markdown", type=Path, default=Path("index/CASE-IDENTITY-AUDIT.md"))
    parser.add_argument("--write-candidates", action="store_true",
                        help="write needs-review override candidates; never applies them")
    parser.add_argument("--candidates", type=Path,
                        default=Path("index/case_identity_override_candidates.json"))
    parser.add_argument("--apply-approved", action="store_true",
                        help="promote candidates marked approved into the durable override file")
    parser.add_argument("--overrides", type=Path,
                        default=Path("index/case_identity_overrides.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    max_year = None if args.max_year == 0 else args.max_year
    candidates_path = args.candidates if args.candidates.is_absolute() else root / args.candidates
    if args.apply_approved:
        overrides_path = args.overrides if args.overrides.is_absolute() else root / args.overrides
        count = promote_approved(root, candidates_path, overrides_path)
        print(f"promoted {count} approved identity overrides -> {overrides_path}")
        return
    report = audit(root, max_year, args.min_title_score, args.strong_title_score)

    json_path = args.json if args.json.is_absolute() else root / args.json
    markdown_path = args.markdown if args.markdown.is_absolute() else root / args.markdown
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")

    if args.write_candidates:
        candidates = [
            item["suggested_override"] for item in report["findings"]
            if item.get("suggested_override")
        ]
        # Preserve review decisions and hand-added evidence when refreshing the
        # mechanical suggestions.  The roster ID plus caption discriminator is
        # the stable identity of a rule; the proposed target remains auditable.
        prior_by_key: dict[tuple[str | None, str], dict[str, Any]] = {}
        if candidates_path.exists():
            prior_payload = json.loads(candidates_path.read_text(encoding="utf-8-sig"))
            prior_rules = prior_payload.get("overrides", []) if isinstance(prior_payload, dict) else prior_payload
            prior_by_key = {
                (canonical_id(rule.get("roster_id")), str(rule.get("title_contains") or "").casefold()): rule
                for rule in prior_rules
            }
        for candidate in candidates:
            key = (canonical_id(candidate.get("roster_id")),
                   str(candidate.get("title_contains") or "").casefold())
            prior = prior_by_key.get(key)
            if not prior:
                continue
            if prior.get("status") in {"approved", "rejected"}:
                candidate["status"] = prior["status"]
            if prior.get("evidence"):
                candidate["evidence"] = prior["evidence"]
            if prior.get("review_notes"):
                candidate["review_notes"] = prior["review_notes"]
        candidates_path.write_text(json.dumps({
            "schema_version": 1,
            "warning": "Review the complete collision chain and source evidence before approval.",
            "overrides": candidates,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {len(candidates)} candidate overrides -> {candidates_path}")

    print(json.dumps(report["summary"], indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")


if __name__ == "__main__":
    main()
