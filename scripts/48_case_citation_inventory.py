#!/usr/bin/env python3
"""Build an auditable, decision-level inventory of PCA case references.

This is an exploratory enrichment pass. It reads ``cases/*.md`` and the
existing case indexes, but never rewrites the verbatim case pages.

The important unit is a decision/page, not a printed case name. A consolidated
decision therefore has one ``decision_id`` and several docket aliases.

Outputs:
  index/case_identity_registry.json
  index/case_reference_candidates.json
  index/case_reference_unresolved.json
  index/case_citations.json
  index/CASE-REFERENCE-REPORT.md

The minutes/case pages remain the evidence. Index and map values are identity
 aids only; their noisy values are retained as provenance rather than silently
 promoted to authoritative printed text.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(os.environ.get("PCA_GA_ROOT", os.getcwd()))
CASES_INDEX = ROOT / "index" / "CASES.md"
CASE_MAP = ROOT / "index" / "case_pages_map.json"
ROSTER_PATH = ROOT / "index" / "sjc_official" / "roster.jsonl"
CASES_DIR = ROOT / "cases"
OUT_REGISTRY = ROOT / "index" / "case_identity_registry.json"
OUT_CANDIDATES = ROOT / "index" / "case_reference_candidates.json"
OUT_UNRESOLVED = ROOT / "index" / "case_reference_unresolved.json"
OUT_CITATIONS = ROOT / "index" / "case_citations.json"
OUT_REPORT = ROOT / "index" / "CASE-REFERENCE-REPORT.md"


# The space after a hyphen is accepted because it occurs in OCR-derived case
# text. Normalization is deliberately separate from the observed surface.
DOCKET_TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z-])(\d{1,4})\s*-\s*(\d{1,3})([A-Za-z]?)(?![0-9A-Za-z-])"
)
DOCKET_BODY = r"\d{1,4}\s*-\s*\d{1,3}[A-Za-z]?"

CASE_CITATION_RE = re.compile(
    rf"\b(?P<prefix>(?:(?:SJC|Judicial)\s+)?Cases?|"
    rf"SJC\s+Docket|Docket|No\.)\s*"
    rf"(?:Nos?\.?\s*)?(?P<dockets>{DOCKET_BODY}"
    rf"(?:\s*(?:,|&|and)\s*(?:Case\s*)?{DOCKET_BODY})*)",
    re.I,
)

CAPTION_CONNECTOR_RE = re.compile(r"\b(?:v\.?|vs\.?|versus)\b", re.I)
MINUTES_REF_RE = re.compile(
    r"\b(?P<ga>M?\d{1,2})GA\b[^\n]{0,35}?\bpp?\.?\s*"
    r"(?P<start>\d{1,4})(?:\s*[-–—]\s*(?P<end>\d{1,4}))?",
    re.I,
)
PAGE_SOURCE_RE = re.compile(
    r"\[([^\]]+)\]\(\.\./markdown/([^)#]+)(?:#[^)]+)?\)", re.I
)
VOL_RE = re.compile(r"ga(?P<ga>\d+)_(?P<year>\d{4})$", re.I)

PROCEEDING_PREFIX_RE = re.compile(
    r"^(?:complaints?\s+of|complaint\s+of|appeals?\s+of|appeal|"
    r"reference|petition|memorial|decision\s+in|ruling\s+in)\s+",
    re.I,
)
ROLE_PREFIX_RE = re.compile(
    r"\b(?:TE|RE|REV\.?|MR\.?|MRS\.?|MS\.?|DEACON|ELDER|"
    r"RULING\s+ELDER|TEACHING\s+ELDER)\s+",
    re.I,
)
DECISION_TRAILER_RE = re.compile(
    r"\s+(?:DECISION|RULING|JUDGMENT|OPINION)\b.*$", re.I
)
MAP_TRAILER_RE = re.compile(r"\s+—\s+M\d+GA\b.*$", re.I)
HTML_TAG_RE = re.compile(r"<[^>]+>")

# These are only for unresolved audit candidates. A caption-like string is not
# enough to make a PCA node; the right side or citation context must look
# ecclesiastical.
ECCLESIASTICAL_WORD_RE = re.compile(
    r"\b(?:presbytery|session|church|pca|judicial\s+commission|"
    r"general\s+assembly|congregation)\b",
    re.I,
)
SHORT_CASE_REF_RE = re.compile(
    r"\b(?:the\s+)?(?P<name>[A-Z][A-Za-z'’.-]+)\s+"
    r"(?P<qualifier>case|decision|ruling)\b|"
    r"\b(?P<name2>[A-Z][A-Za-z'’.-]+)\s+(?P<num>\d+)\b",
    re.I,
)


@dataclass(frozen=True)
class IndexRow:
    case_file: str
    case_label: str
    title: str
    disposition: str
    summary: str
    page_cell: str
    assembly_heading: str


@dataclass
class Occurrence:
    source_decision: str
    source_file: str
    source_dockets: list[str]
    target_decision: str | None
    target_dockets: list[str]
    surface_text: str
    match_type: str
    signals: list[str]
    confidence: float
    line: int
    context: str
    self_reference: bool
    evidence_key: str
    cited_dockets: list[str] = field(default_factory=list)
    ambiguity: dict[str, Any] | None = None


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_visible(text: str) -> str:
    """Remove presentation markup while retaining the visible wording."""
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("**", "").replace("__", "")
    return normalize_space(text)


def normalize_docket(raw: str, known_dockets: set[str] | None = None) -> str:
    """Return the comparison id for a docket token.

    Four-digit docket years are retained. Two-digit years from the SJC era
    (85--99) expand to 19xx; small prefixes remain early-GA item numbers, so
    ``3-12`` is not misread as 1903-12. Sequence zero padding is ignored.
    """
    value = clean_visible(raw).replace(" ", "")
    match = re.fullmatch(r"(\d{1,4})-(\d{1,3})([A-Za-z]?)", value)
    if not match:
        return value
    year_or_era, sequence, suffix = match.groups()
    prefix = int(year_or_era)
    if len(year_or_era) == 4:
        prefix_text = str(prefix)
    elif len(year_or_era) == 2:
        sequence_text = f"{int(sequence)}{suffix.lower()}"
        if prefix >= 85:
            prefix_text = str(1900 + prefix)
        elif known_dockets and f"{2000 + prefix}-{sequence_text}" in known_dockets:
            prefix_text = str(2000 + prefix)
        else:
            prefix_text = str(prefix)
    else:
        prefix_text = str(prefix)
    return f"{prefix_text}-{int(sequence)}{suffix.lower()}"


def docket_tokens(text: str) -> list[str]:
    """Return unique normalized docket tokens found in ``text``."""
    seen: list[str] = []
    for match in DOCKET_TOKEN_RE.finditer(clean_visible(text)):
        value = normalize_docket(match.group(0))
        if value not in seen:
            seen.append(value)
    return seen


def raw_docket_tokens(text: str) -> list[tuple[str, str, int, int]]:
    """Return (surface, normalized, start, end) docket matches."""
    visible = clean_visible(text)
    return [
        (m.group(0), normalize_docket(m.group(0)), m.start(), m.end())
        for m in DOCKET_TOKEN_RE.finditer(visible)
    ]


def caption_key(text: str, *, remove_roles: bool = False) -> str:
    """Conservative matching key, never a display/canonical caption."""
    text = clean_visible(text).replace("’", "'")
    text = MAP_TRAILER_RE.sub("", text)
    text = re.sub(r"\s+\(\s*(?:appeal|complaint|reference|petition)\s*\)\s*$", "", text, flags=re.I)
    docket_list = rf"{DOCKET_BODY}(?:\s*(?:,|/|&|and)\s*(?:case\s*)?{DOCKET_BODY})*"
    text = re.sub(r"^\s*(?:case|cases|sjc\s+case|judicial\s+case)\s*"
                  rf"(?:no\.?\s*)?(?:{docket_list})\s*[:,-]?\s*", "", text, flags=re.I)
    text = PROCEEDING_PREFIX_RE.sub("", text)
    text = DECISION_TRAILER_RE.sub("", text)
    if remove_roles:
        text = ROLE_PREFIX_RE.sub("", text)
    text = re.sub(r"\bversus\b|\bvs\.?\b|\bv\.?\b", " v ", text, flags=re.I)
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_space(text)


def caption_keys(text: str) -> list[str]:
    keys = [caption_key(text), caption_key(text, remove_roles=True)]
    # The corpus demonstrably shortens "Northwest Georgia Presbytery" to
    # "Northwest Georgia" in citations. Keep this as a separate comparison key
    # so collisions remain visible; do not rewrite the observed alias.
    for key in list(keys):
        if " v " in key:
            left, right = key.split(" v ", 1)
            if right.endswith(" presbytery"):
                keys.append(f"{left} v {right[:-11].rstrip()}")
    return list(dict.fromkeys(k for k in keys if k))


def is_caption_like(text: str) -> bool:
    if not text or len(text) < 8:
        return False
    connector = CAPTION_CONNECTOR_RE.search(text)
    return bool(connector and text[:connector.start()].strip() and text[connector.end():].strip())


def is_clean_provisional_caption(text: str) -> bool:
    """Prefer a concise page title over an extraction/report heading."""
    if not is_caption_like(text):
        return False
    if len(text.split()) > 24:
        return False
    return not re.search(
        r"\b(?:report of the cases|standing judicial commission|concurring|"
        r"dissent(?:ing)?|identical to|reference from the .* minutes)\b",
        text,
        re.I,
    )


def clean_title_for_caption(text: str) -> str:
    """Clean an index/map title without treating summary prose as a caption."""
    text = clean_visible(text)
    text = MAP_TRAILER_RE.sub("", text)
    text = re.sub(r"\s+####.*$", "", text)
    text = re.sub(r"\s+p\.?\s*\d+\s*$", "", text, flags=re.I)
    return normalize_space(text.strip(" -—:;."))


def strip_case_lead(text: str) -> str:
    text = clean_visible(text)
    docket_list = rf"{DOCKET_BODY}(?:\s*(?:,|/|&|and)\s*(?:case\s*)?{DOCKET_BODY})*"
    text = re.sub(r"^\s*(?:case|cases|sjc\s+case|judicial\s+case)\b"
                  rf"\s*(?:no\.?\s*)?(?:{docket_list})?\s*[:,-]?\s*", "", text, flags=re.I)
    return normalize_space(text)


def caption_from_heading(text: str) -> str:
    text = strip_case_lead(text)
    text = re.sub(r"^\s*(?:complaints?|appeals?)\s+of\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(?:DECISION|RULING|JUDGMENT|OPINION)\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+M\d+GA\b.*$", "", text, flags=re.I)
    return normalize_space(text.strip(" -—:;."))


def page_headings(path: Path) -> tuple[str, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    h1 = ""
    headings: list[str] = []
    for raw in lines[:90]:
        if raw.startswith("# ") and not h1:
            h1 = clean_visible(raw[2:])
        if raw.startswith("##") or raw.startswith("###"):
            heading = clean_visible(re.sub(r"^#+\s*", "", raw))
            if is_caption_like(heading) or re.search(r"\b(?:case|complaint|appeal|docket)\b", heading, re.I):
                headings.append(heading)
    # Concurring/dissenting headings may be beyond the first 90 lines, but only
    # collect them when they are unmistakably case-caption headings.
    for raw in lines[90:]:
        if not raw.startswith("##") and not raw.startswith("###"):
            continue
        heading = clean_visible(re.sub(r"^#+\s*", "", raw))
        if is_caption_like(heading) and re.search(r"\b(?:case|complaint|appeal|opinion)\b", heading, re.I):
            headings.append(heading)
    return h1, list(dict.fromkeys(headings))


def parse_index(path: Path) -> list[IndexRow]:
    rows: list[IndexRow] = []
    assembly_heading = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("## "):
            assembly_heading = raw[3:].strip()
            continue
        if not raw.startswith("|") or "../cases/" not in raw:
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        link = re.search(r"\.\./cases/([^/)]+)\.md", raw)
        if not link:
            continue
        label = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", cells[0])
        rows.append(IndexRow(
            case_file=link.group(1),
            case_label=clean_visible(label),
            title=clean_visible(cells[1]),
            disposition=clean_visible(cells[2]),
            summary=clean_visible(cells[3]),
            page_cell=clean_visible(cells[4]),
            assembly_heading=assembly_heading,
        ))
    return rows


def load_case_map(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_digest_roster(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def roster_dockets(row: dict[str, Any]) -> list[str]:
    values = []
    for value in [row.get("case_number"), row.get("case_number_raw")]:
        if value:
            values.extend(docket_tokens(str(value)))
    # A few roster rows encode the second member of a consolidated case in a
    # leading title fragment such as ``& 2023-08`` rather than the number
    # field. Restrict this recovery to that leading fragment so ordinary
    # summary text cannot add unrelated dockets.
    title = str(row.get("title", ""))
    extra = re.match(r"^\s*&\s*(\d{4}\s*-\s*\d{1,3}[A-Za-z]?)\b", title)
    if extra:
        values.extend(docket_tokens(extra.group(1)))
    return list(dict.fromkeys(values))


def digest_caption(title: str) -> str:
    """Extract only the roster's party caption, not its disposition/summary."""
    text = clean_visible(title)
    text = re.split(r"\s*\[", text, maxsplit=1)[0]
    text = re.split(
        r"\s+(?:decided|dismissed|sustained|not\s+sustained|complaint\s+declared|"
        r"administratively\s+out\s+of\s+order|judicially\s+out\s+of\s+order|"
        r"case\s+was\s+deemed|remand)\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    return normalize_space(text.strip(" -—:;."))


def map_by_file(case_map: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for key, value in case_map.items():
        record = dict(value)
        record["map_key"] = key
        grouped[record.get("file", "")].append(record)
    return grouped


def page_caption(h1: str) -> str:
    text = clean_visible(h1)
    if " — " in text:
        text = text.split(" — ", 1)[1]
    elif " - " in text and DOCKET_TOKEN_RE.search(text.split(" - ", 1)[0]):
        text = text.split(" - ", 1)[1]
    return clean_title_for_caption(text)


def parse_source(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    source = PAGE_SOURCE_RE.search(text)
    ga = year = None
    source_label = None
    source_volume = None
    pages: list[int] = []
    if source:
        source_label = clean_visible(source.group(1))
        source_volume = source.group(2).removesuffix(".md")
        volume_match = VOL_RE.search(source_volume)
        if volume_match:
            ga = int(volume_match.group("ga"))
            year = int(volume_match.group("year"))
        page_match = re.search(r"pp?\.?\s*(\d+)(?:\s*[-–—]\s*(\d+))?", source_label, re.I)
        if page_match:
            start, end = page_match.groups()
            pages = [int(start), int(end or start)]
    ga_meta = re.search(r"\*\*Assembly:\s*[^()]*\((\d{4})\)", text, re.I)
    if year is None and ga_meta:
        year = int(ga_meta.group(1))
    # Stub/early pages do not always carry a linked Minutes source. Their
    # filename still records the assembly/year pairing and is a safe fallback
    # for registry metadata, not for page-range identity.
    filename_source = re.match(r"^ga(?P<ga>\d+)_(?P<year>\d{4})(?:__|$)", path.stem, re.I)
    if filename_source:
        if ga is None:
            ga = int(filename_source.group("ga"))
        if year is None:
            year = int(filename_source.group("year"))
    disposition = ""
    disp = re.search(r"\*\*Disposition:\s*([^*]+)\*\*", text, re.I)
    if disp:
        disposition = normalize_space(disp.group(1))
    return {
        "ga": ga,
        "year": year,
        "source_label": source_label,
        "source_volume": source_volume,
        "pages": pages,
        "disposition": disposition,
    }


def add_provenance(entry: dict[str, Any], field: str, value: Any, source: str, **extra: Any) -> None:
    entry.setdefault("provenance", {}).setdefault(field, []).append({"value": value, "source": source, **extra})


def add_alias(entry: dict[str, Any], alias: str, source: str, *, observed_exact: bool = True, safe_for_matching: bool | None = None, **extra: Any) -> None:
    alias = normalize_space(clean_visible(alias).strip(" -—:;."))
    if not alias or not is_caption_like(alias):
        return
    if alias not in entry["aliases_observed"]:
        entry["aliases_observed"].append(alias)
    if safe_for_matching is not False and alias not in entry.setdefault("aliases_used_for_matching", []):
        entry["aliases_used_for_matching"].append(alias)
    record = {"alias": alias, "source": source, "observed_exact": observed_exact}
    if safe_for_matching is not None:
        record["safe_for_matching"] = safe_for_matching
    record.update(extra)
    if record not in entry.setdefault("alias_provenance", []):
        entry["alias_provenance"].append(record)


def build_registry(rows: list[IndexRow], case_map: dict[str, dict[str, Any]], digest_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows_by_file: dict[str, list[IndexRow]] = collections.defaultdict(list)
    for row in rows:
        rows_by_file[row.case_file].append(row)
    records_by_file = map_by_file(case_map)
    digest_by_docket: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for digest_row in digest_rows or []:
        for docket in roster_dockets(digest_row):
            digest_by_docket[docket].append(digest_row)

    registry: list[dict[str, Any]] = []
    for page in sorted(CASES_DIR.glob("*.md")):
        decision_id = page.stem
        h1, headings = page_headings(page)
        source = parse_source(page)
        map_records = records_by_file.get(decision_id, [])
        index_records = rows_by_file.get(decision_id, [])

        raw_docket_values: list[tuple[str, str]] = []
        for record in map_records:
            for value in record.get("numbers", []):
                raw_docket_values.append((str(value), f"case_pages_map:{record.get('map_key')}"))
        for row in index_records:
            for value in docket_tokens(row.case_label):
                raw_docket_values.append((value, "CASES.md:case-label"))
        # Filenames carry the cleanest aliases for modern consolidated pages.
        for value in docket_tokens(decision_id.replace("_", "/")):
            raw_docket_values.append((value, "case-file-name"))
        h1_prefix = h1.split(" — ", 1)[0] if h1 else ""
        for surface, _, _, _ in raw_docket_tokens(h1_prefix):
            raw_docket_values.append((surface, "page-h1:docket-label"))
        primary_dockets = {normalize_docket(raw) for raw, _ in raw_docket_values}
        # Structural printed headings recover old two-digit forms and early
        # docket labels not represented in case_pages_map.json.
        for heading in headings[:12]:
            for surface, value, _, _ in raw_docket_tokens(heading):
                if re.search(r"\b(?:case|docket|complaint|appeal)\b", heading, re.I):
                    raw_docket_values.append((surface, "printed-heading"))

        docket_numbers: list[str] = []
        docket_aliases: list[str] = []
        for raw, provenance in raw_docket_values:
            normalized = normalize_docket(raw, primary_dockets)
            if provenance == "printed-heading" and normalized not in primary_dockets:
                continue
            if normalized not in docket_numbers:
                docket_numbers.append(normalized)
            observed = clean_visible(raw)
            if observed not in docket_aliases:
                docket_aliases.append(observed)

        printed_captions: list[str] = []
        for heading in headings:
            caption = caption_from_heading(heading)
            if is_caption_like(caption) and caption not in printed_captions:
                printed_captions.append(caption)
        map_titles = [clean_title_for_caption(r.get("title", "")) for r in map_records]
        index_titles = [clean_title_for_caption(r.title) for r in index_records]
        h1_caption = page_caption(h1) if h1 else ""
        digest_matches: list[dict[str, Any]] = []
        for docket in docket_numbers:
            digest_matches.extend(digest_by_docket.get(docket, []))
        digest_matches = list({json.dumps(row, sort_keys=True): row for row in digest_matches}.values())
        # The roster may spell a consolidated docket list more completely than
        # the page map (for example 2023-6 & 2023-08). Enrich only an
        # unambiguous roster match; duplicate roster numbers stay evidence,
        # not an automatic identity merge.
        digest_added_dockets: list[str] = []
        if len(digest_matches) == 1:
            digest_row = digest_matches[0]
            for docket in roster_dockets(digest_row):
                if docket not in docket_numbers:
                    docket_numbers.append(docket)
                    docket_aliases.append(docket)
                    digest_added_dockets.append(docket)
        digest_captions = [digest_caption(row.get("title", "")) for row in digest_matches]
        digest_captions = [caption for caption in digest_captions if is_caption_like(caption)]

        # Minutes headings are the strongest caption evidence in the page. The
        # map/index are useful fallbacks and are retained as observed values.
        canonical = h1_caption if is_clean_provisional_caption(h1_caption) else ""
        if not canonical:
            canonical = next((x for x in printed_captions if is_clean_provisional_caption(x)), "")
        if not canonical and printed_captions:
            canonical = printed_captions[0]
        if not canonical and h1_caption and is_caption_like(h1_caption):
            canonical = h1_caption
        if not canonical:
            canonical = next((x for x in index_titles + map_titles if is_caption_like(x)), "")

        entry: dict[str, Any] = {
            "decision_id": decision_id,
            "case_file": f"cases/{decision_id}.md",
            "docket_numbers": docket_numbers,
            "docket_aliases_observed": docket_aliases,
            "canonical_caption_provisional": canonical,
            "digest_caption_provisional": digest_captions[0] if len(digest_captions) == 1 else "",
            "aliases_observed": [],
            "aliases_used_for_matching": [],
            "normalized_aliases": [],
            "alias_provenance": [],
            "ga": source.get("ga"),
            "year": source.get("year"),
            "source": "PCA General Assembly Minutes; Digest roster when matched",
            "disposition": source.get("disposition") or (index_records[0].disposition if index_records else ""),
            "minutes_source": {
                "volume": source.get("source_volume"),
                "label": source.get("source_label"),
                "pages": source.get("pages", []),
            },
            "consolidated": len(docket_numbers) > 1,
            "identity_status": "provisional",
            "digest_roster": digest_matches,
            "digest_roster_match": "none" if not digest_matches else ("unique" if len(digest_matches) == 1 else "ambiguous"),
            "index_titles_observed": list(dict.fromkeys(index_titles)),
            "map_titles_observed": list(dict.fromkeys(map_titles)),
            "page_h1": h1,
            "printed_headings_observed": headings,
            "provenance": {},
            "identity_conflicts": [],
        }

        for raw, provenance in raw_docket_values:
            add_provenance(entry, "docket_numbers", normalize_docket(raw), provenance, observed=clean_visible(raw))
        for docket in digest_added_dockets:
            add_provenance(entry, "docket_numbers", docket, "sjc_official/roster.jsonl", observed=docket)
        for row in index_records:
            add_provenance(entry, "index", row.title, "CASES.md", label=row.case_label, disposition=row.disposition)
        for record in map_records:
            add_provenance(entry, "map", record.get("title", ""), "case_pages_map.json", map_key=record.get("map_key"))
        add_provenance(entry, "minutes_source", entry["minutes_source"], f"{entry['case_file']}:front-matter")

        if canonical:
            add_alias(entry, canonical, "printed-heading" if printed_captions else "page-h1", observed_exact=True)
        if not canonical and len(digest_captions) == 1:
            canonical = digest_captions[0]
            entry["canonical_caption_provisional"] = canonical
            add_alias(entry, canonical, "digest-roster", observed_exact=True)
        for caption in printed_captions:
            add_alias(entry, caption, "printed-heading", observed_exact=True)
        printed_keys = {caption_key(x, remove_roles=True) for x in printed_captions}
        for value in [h1_caption, *index_titles, *map_titles]:
            if is_caption_like(value):
                source_name = "page-h1" if value == h1_caption else "index-or-map"
                # If Minutes-extracted headings exist, a disagreeing H1/index
                # caption remains provenance but is not allowed to become a
                # matching alias. This prevents stale map titles from linking
                # a citation to the wrong decision (e.g. Bigelow's 2012-08).
                safe = not printed_keys or caption_key(value, remove_roles=True) in printed_keys
                add_alias(entry, value, source_name, observed_exact=True, safe_for_matching=safe)

        # A page heading and an index/map title disagreeing on parties is useful
        # QA evidence, especially for old or stale extracted titles.
        other_values = [x for x in index_titles + map_titles if is_caption_like(x)]
        for value in other_values:
            if printed_keys and caption_key(value, remove_roles=True) not in printed_keys:
                entry["identity_conflicts"].append({"field": "caption", "printed": printed_captions, "other": value})
                break

        entry["normalized_aliases"] = sorted({key for alias in entry["aliases_used_for_matching"] for key in caption_keys(alias)})
        if entry["digest_roster_match"] == "unique":
            entry["identity_status"] = "roster-matched"
        registry.append(entry)
    return registry


def make_maps(registry: list[dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, dict[str, Any]]]:
    docket_map: dict[str, set[str]] = collections.defaultdict(set)
    alias_map: dict[str, set[str]] = collections.defaultdict(set)
    by_id: dict[str, dict[str, Any]] = {}
    for entry in registry:
        by_id[entry["decision_id"]] = entry
        for docket in entry["docket_numbers"]:
            docket_map[docket].add(entry["decision_id"])
        for alias in entry.get("aliases_used_for_matching", entry["aliases_observed"]):
            for key in caption_keys(alias):
                alias_map[key].add(entry["decision_id"])
    return docket_map, alias_map, by_id


def caption_party_tokens(text: str) -> tuple[set[str], set[str]]:
    """Return conservative party tokens for conflict detection only."""
    key = caption_key(text, remove_roles=True)
    if " v " not in key:
        return set(), set()
    left, right = key.split(" v ", 1)
    ignored = {
        "a", "al", "and", "case", "complaint", "complaints", "et", "of",
        "the", "to", "v",
    }
    token_sets = []
    for side in (left, right):
        token_sets.append({token for token in side.split() if len(token) >= 3 and token not in ignored})
    return token_sets[0], token_sets[1]


def caption_fingerprint_targets(caption: str, registry: list[dict[str, Any]]) -> set[str]:
    """Find possible caption collisions without making them resolvable.

    This catches abbreviated forms such as ``NW Georgia`` versus ``Northwest
    Georgia`` so a docket+caption mismatch is surfaced even when the exact
    abbreviated alias was not previously observed. It is deliberately used
    only as a conflict detector; it never resolves a caption on its own.
    """
    source_left, source_right = caption_party_tokens(caption)
    if not source_left or not source_right:
        return set()
    targets: set[str] = set()
    for entry in registry:
        for alias in entry.get("aliases_used_for_matching", []):
            left, right = caption_party_tokens(alias)
            # Require two matching left-party tokens for this secondary
            # conflict signal. A single shared surname/word such as
            # ``Georgia`` or ``Presbytery`` is too broad for identity QA.
            if len(source_left & left) >= 2 and source_right & right:
                targets.add(entry["decision_id"])
                break
    return targets


def caption_compatible_with_target(caption: str, target: str, by_id: dict[str, dict[str, Any]]) -> bool:
    """Allow docket precedence for a shortened caption of the same parties."""
    source_left, source_right = caption_party_tokens(caption)
    if not source_left or not source_right:
        return False
    entry = by_id.get(target, {})
    for alias in entry.get("aliases_used_for_matching", []):
        left, right = caption_party_tokens(alias)
        if source_left & left and source_right & right:
            return True
    return False


def source_dockets(decision_id: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    return list(by_id.get(decision_id, {}).get("docket_numbers", []))


def context_window(line: str, start: int, end: int, width: int = 170) -> str:
    return normalize_space(line[max(0, start - width):min(len(line), end + width)])


def minutes_key_candidates(registry: list[dict[str, Any]]) -> dict[tuple[int, int], set[str]]:
    out: dict[tuple[int, int], set[str]] = collections.defaultdict(set)
    for entry in registry:
        ga = entry.get("ga")
        pages = entry.get("minutes_source", {}).get("pages", [])
        if not ga or len(pages) != 2:
            continue
        for page in range(int(pages[0]), int(pages[1]) + 1):
            out[(int(ga), page)].add(entry["decision_id"])
    return out


def resolve_minutes(ga: int, start: int, end: int, page_map: dict[tuple[int, int], set[str]]) -> set[str]:
    targets: set[str] = set()
    for page in range(start, end + 1):
        targets.update(page_map.get((ga, page), set()))
    return targets


def split_docket_list(text: str) -> list[tuple[str, str]]:
    return [(m.group(0), normalize_docket(m.group(0))) for m in DOCKET_TOKEN_RE.finditer(text)]


def extract_caption_after_docket(line: str, match: re.Match[str], stop_at: int | None = None) -> tuple[str, int, int] | None:
    """Extract a caption immediately following a structured case citation."""
    after_start = match.end()
    tail_end = after_start + 240
    if stop_at is not None:
        tail_end = min(tail_end, stop_at)
    tail = line[after_start:tail_end]
    connector = CAPTION_CONNECTOR_RE.search(tail)
    if not connector:
        return None
    left = tail[:connector.start()]
    left = re.sub(r"^[\s,:;–—-]+", "", left)
    left = re.sub(r"^(?:complaints?|appeals?)\s+of\s+", "", left, flags=re.I)
    left = re.sub(r"^(?:decision|ruling|judgment)\s+in\s+", "", left, flags=re.I)
    right_tail = tail[connector.end():]
    right_tail = re.split(r"\s*(?:\(|\)|;|,|\bM\d+GA\b|\bStatus\s*:|\bthe\s+\d+(?:st|nd|rd|th)\s+General\b|\s+(?:TE|RE|REV\.?|MR\.?|MRS\.?|MS\.?|DEACON)\s+[A-Z])", right_tail, maxsplit=1, flags=re.I)[0]
    right_tail = right_tail.strip(" \t,:;–—-.")
    right_tail = re.sub(r"\s+(?:decision|ruling|judgment|opinion)\b.*$", "", right_tail, flags=re.I)
    left = left.strip(" \t,:;–—-.()")
    if not left or not right_tail:
        return None
    surface = f"{left} {line[after_start + connector.start():after_start + connector.end()]} {right_tail}"
    actual_start = line.find(left, after_start, after_start + connector.start() + 1)
    if actual_start < 0:
        actual_start = after_start
    actual_end = line.find(right_tail, after_start + connector.end(), after_start + len(tail))
    if actual_end < 0:
        actual_end = after_start + len(tail)
    actual_end += len(right_tail)
    return normalize_space(surface), actual_start, actual_end


def citation_unit_end(line: str, start: int, match_end: int, caption_span: tuple[int, int] | None) -> int:
    end = caption_span[1] if caption_span else match_end
    if caption_span and line[end:end + 1] == ")":
        end += 1
    next_case = re.search(r",\s*(?:and\s+)?Case\b|;\s*Case\b", line[end:], re.I)
    limit = end + next_case.start() if next_case else min(len(line), end + 100)
    locator = re.search(r"\(?\s*M\d+GA\b[^;)]{0,60}\bpp?\.?\s*\d+(?:\s*[-–—]\s*\d+)?\s*\)?", line[end:limit], re.I)
    if locator:
        end += locator.end()
    return max(start, min(end, len(line)))


def add_occurrence(
    out: list[Occurrence],
    seen: set[tuple[Any, ...]],
    *,
    source_decision: str,
    source_file: str,
    source_ds: list[str],
    target: str | None,
    target_dockets: list[str],
    cited_dockets: list[str] | None = None,
    surface: str,
    match_type: str,
    signals: Iterable[str],
    confidence: float,
    line_no: int,
    context: str,
    ambiguity: dict[str, Any] | None = None,
    self_reference: bool | None = None,
) -> None:
    signals_list = list(dict.fromkeys(signals))
    if self_reference is None:
        self_reference = bool(target and target == source_decision)
    key = (source_decision, target, line_no, surface, match_type)
    if key in seen:
        return
    seen.add(key)
    out.append(Occurrence(
        source_decision=source_decision,
        source_file=source_file,
        source_dockets=source_ds,
        target_decision=target,
        target_dockets=target_dockets,
        cited_dockets=cited_dockets or [],
        surface_text=surface,
        match_type=match_type,
        signals=signals_list,
        confidence=confidence,
        line=line_no,
        context=context,
        self_reference=self_reference,
        evidence_key=f"{source_file}:L{line_no}",
        ambiguity=ambiguity,
    ))


def caption_candidates(line: str) -> list[tuple[str, int, int]]:
    """Generate bounded caption windows around v/vs/versus connectors."""
    out: list[tuple[str, int, int]] = []
    for connector in CAPTION_CONNECTOR_RE.finditer(line):
        left_start = max(0, connector.start() - 150)
        left = line[left_start:connector.start()]
        starts = {0}
        for marker in re.finditer(r"[,;:(]|\b(?:of|in|see|case|decision)\b", left, re.I):
            starts.add(marker.end())
        right_limit = min(len(line), connector.end() + 160)
        right = line[connector.end():right_limit]
        right = re.split(r"\s*(?:\(|\)|;|,|\bM\d+GA\b|\bStatus\s*:|\bthe\s+\d+(?:st|nd|rd|th)\s+General\b|\s+(?:TE|RE|REV\.?|MR\.?|MRS\.?|MS\.?|DEACON)\s+[A-Z])", right, maxsplit=1, flags=re.I)[0]
        for start in sorted(starts):
            left_part = left[start:].strip(" \t,:;–—-.()")
            left_part = re.sub(r"^(?:complaints?|appeals?)\s+of\s+", "", left_part, flags=re.I)
            if not left_part or not right.strip():
                continue
            surface = normalize_space(f"{left_part} {line[connector.start():connector.end()]} {right.strip(' \t,:;–—-.()')}")
            actual_start = left_start + start
            actual_end = connector.end() + len(right.rstrip())
            if actual_end <= actual_start:
                continue
            out.append((surface, actual_start, min(len(line), actual_end)))
    return list(dict.fromkeys(sorted(out, key=lambda x: (x[1], -(x[2] - x[1])))))


def is_identity_heading(line: str, source: str, by_id: dict[str, dict[str, Any]], line_no: int) -> bool:
    if not line.lstrip().startswith("#") or line_no > 80:
        return False
    source_d = set(source_dockets(source, by_id))
    if any(normalize_docket(x) in source_d for x in docket_tokens(line)):
        return True
    own_caption = by_id.get(source, {}).get("canonical_caption_provisional", "")
    if own_caption and caption_key(own_caption, remove_roles=True) in {
        caption_key(line, remove_roles=True),
        caption_key(caption_from_heading(line.lstrip("# ")), remove_roles=True),
    }:
        return True
    return bool(re.search(r"^#+\s*(?:case|complaint|appeal|judicial case)\b", line, re.I))


def harvested_alias(entry: dict[str, Any], caption: str, source_file: str, line_no: int, docket: str | None) -> None:
    add_alias(entry, caption, "case-reference", observed_exact=True, safe_for_matching=True, source_file=source_file, line=line_no, docket=docket)


def scan_references(registry: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    docket_map, alias_map, by_id = make_maps(registry)
    minutes_map = minutes_key_candidates(registry)
    initial_alias_map = alias_map
    surname_names = surname_alias_map(registry)
    resolved: list[Occurrence] = []
    unresolved: list[Occurrence] = []
    seen_resolved: set[tuple[Any, ...]] = set()
    seen_unresolved: set[tuple[Any, ...]] = set()
    stats: dict[str, Any] = {
        "lines_scanned": 0,
        "caption_like_filtered": 0,
        "caption_like_filtered_examples": [],
        "bco_like_mentions": 0,
        "structured_units": 0,
        "learned_aliases": 0,
        "compound_docket_units_decomposed": 0,
    }

    for page in sorted(CASES_DIR.glob("*.md")):
        source = page.stem
        source_ds = source_dockets(source, by_id)
        lines = page.read_text(encoding="utf-8").splitlines()
        start_ix = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                start_ix = i + 1
                break
        for i in range(start_ix, len(lines)):
            line = lines[i]
            line_no = i + 1
            if not line.strip() or line.lstrip().startswith("<!--"):
                continue
            stats["lines_scanned"] += 1
            stats["bco_like_mentions"] += len(re.findall(r"\bBCO\s+\d{1,3}\s*-\s*\d{1,3}\b", line, re.I))
            if is_identity_heading(line, source, by_id, line_no):
                continue
            # Markdown headings are document structure (case titles, opinions,
            # recommendation labels), not ordinary citation prose. Excluding
            # them prevents a page's own printed title from becoming a false
            # self-reference while retaining body-text references verbatim.
            if line.lstrip().startswith("#"):
                continue

            occupied: list[tuple[int, int]] = []
            structured: list[tuple[re.Match[str], list[tuple[str, str]], str | None, tuple[int, int] | None]] = []
            structured_matches = list(CASE_CITATION_RE.finditer(line))
            for match_index, match in enumerate(structured_matches):
                dockets = split_docket_list(match.group("dockets"))
                next_citation_start = (
                    structured_matches[match_index + 1].start()
                    if match_index + 1 < len(structured_matches)
                    else None
                )
                caption_info = extract_caption_after_docket(line, match, stop_at=next_citation_start)
                caption = caption_info[0] if caption_info else None
                caption_span = (caption_info[1], caption_info[2]) if caption_info else None
                structured.append((match, dockets, caption, caption_span))
            for match, cited_dockets, caption, caption_span in structured:
                stats["structured_units"] += 1
                unit_end = citation_unit_end(line, match.start(), match.end(), caption_span)
                occupied.append((match.start(), unit_end))
                cited_norm = list(dict.fromkeys(value for _, value in cited_dockets))
                docket_targets = set().union(*(docket_map.get(value, set()) for value in cited_norm)) if cited_norm else set()
                missing_dockets = [value for value in cited_norm if value not in docket_map]
                docket_target_groups: dict[str, list[str]] = collections.defaultdict(list)
                for docket in cited_norm:
                    targets_for_docket = docket_map.get(docket, set())
                    if len(targets_for_docket) == 1:
                        docket_target_groups[next(iter(targets_for_docket))].append(docket)
                caption_targets: set[str] = set()
                if caption:
                    for key in caption_keys(caption):
                        caption_targets.update(initial_alias_map.get(key, set()))
                fingerprint_targets = caption_fingerprint_targets(caption, registry) if caption else set()
                all_caption_targets = caption_targets | fingerprint_targets
                minutes_targets: set[str] = set()
                minutes_match = MINUTES_REF_RE.search(line[match.end():unit_end])
                if minutes_match:
                    ga_token = minutes_match.group("ga")
                    ga = int(ga_token.lstrip("Mm"))
                    start_page = int(minutes_match.group("start"))
                    end_page = int(minutes_match.group("end") or start_page)
                    minutes_targets = resolve_minutes(ga, start_page, end_page, minutes_map)

                all_target_sets = [set(docket_targets), set(all_caption_targets), set(minutes_targets)]
                nonempty = [x for x in all_target_sets if x]
                union = set.union(*nonempty) if nonempty else set()
                signals = ["docket"]
                if caption:
                    signals.append("caption")
                if minutes_match:
                    signals.append("minutes")
                surface = line[match.start():unit_end].strip()

                docket_target = next(iter(docket_targets), None)
                caption_conflict = bool(
                    all_caption_targets
                    and docket_target not in all_caption_targets
                    and docket_target is not None
                    and not caption_compatible_with_target(caption, docket_target, by_id)
                )
                if len(docket_targets) == 1 and not caption_conflict and not missing_dockets:
                    target = next(iter(docket_targets))
                    match_type = "docket"
                    if caption and minutes_match:
                        match_type = "docket_caption_minutes"
                    elif caption:
                        match_type = "docket_caption"
                    elif minutes_match:
                        match_type = "docket_minutes"
                    ambiguity_details: dict[str, Any] = {}
                    if len(all_caption_targets) > 1:
                        ambiguity_details["caption_targets"] = sorted(caption_targets)
                        if fingerprint_targets - caption_targets:
                            ambiguity_details["caption_fingerprint_targets"] = sorted(fingerprint_targets - caption_targets)
                    if minutes_targets and minutes_targets != {target}:
                        ambiguity_details["minutes_targets"] = sorted(minutes_targets)
                    add_occurrence(
                        resolved, seen_resolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                        target=target, target_dockets=source_dockets(target, by_id), cited_dockets=cited_norm, surface=surface,
                        match_type=match_type, signals=signals,
                        confidence=0.98 if ambiguity_details else (1.0 if caption_targets or minutes_targets else 0.98),
                        line_no=line_no, context=context_window(line, match.start(), unit_end),
                        ambiguity=ambiguity_details or None,
                    )
                    if caption:
                        entry = by_id[target]
                        before = len(entry["aliases_observed"])
                        harvested_alias(entry, caption, str(page.relative_to(ROOT)), line_no, cited_norm[0] if cited_norm else None)
                        stats["learned_aliases"] += int(len(entry["aliases_observed"]) > before)
                    continue

                # An explicit list can identify several distinct decisions.
                # Decompose it into one resolved occurrence per uniquely mapped
                # target when the caption, if present, agrees with that target
                # set. Minutes ranges may still overlap other registry pages;
                # retain that as secondary ambiguity evidence without allowing
                # it to override explicit docket-plus-caption identity.
                compound_targets = set(docket_target_groups)
                compound_resolvable = bool(
                    len(cited_norm) > 1
                    and not missing_dockets
                    and len(docket_target_groups) > 1
                    and all(len(docket_map.get(docket, set())) == 1 for docket in cited_norm)
                    and (not all_caption_targets or all_caption_targets == compound_targets)
                )
                if compound_resolvable:
                    stats["compound_docket_units_decomposed"] += 1
                    for target in sorted(compound_targets):
                        ambiguity_details: dict[str, Any] = {}
                        if minutes_targets and not minutes_targets <= compound_targets:
                            ambiguity_details["minutes_targets"] = sorted(minutes_targets)
                        add_occurrence(
                            resolved, seen_resolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                            target=target, target_dockets=source_dockets(target, by_id), cited_dockets=docket_target_groups[target], surface=surface,
                            match_type="docket_caption_minutes" if caption and minutes_match else ("docket_caption" if caption else ("docket_minutes" if minutes_match else "docket")),
                            signals=signals, confidence=0.98 if ambiguity_details else 1.0, line_no=line_no,
                            context=context_window(line, match.start(), unit_end), ambiguity=ambiguity_details or None,
                        )
                        if caption:
                            entry = by_id[target]
                            before = len(entry["aliases_observed"])
                            cited_docket = docket_target_groups[target][0]
                            harvested_alias(entry, caption, str(page.relative_to(ROOT)), line_no, cited_docket)
                            stats["learned_aliases"] += int(len(entry["aliases_observed"]) > before)
                    continue

                ambiguity = {
                    "cited_dockets": cited_norm,
                    "docket_targets": sorted(docket_targets),
                    "caption_targets": sorted(caption_targets),
                    "caption_fingerprint_targets": sorted(fingerprint_targets),
                    "minutes_targets": sorted(minutes_targets),
                    "missing_dockets": missing_dockets,
                }
                add_occurrence(
                    unresolved, seen_unresolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                    target=None, target_dockets=cited_norm, cited_dockets=cited_norm, surface=surface,
                    match_type="docket_caption_conflict" if caption and len(union) > 1 else "docket_unresolved",
                    signals=signals, confidence=0.35 if len(union) > 1 else 0.2,
                    line_no=line_no, context=context_window(line, match.start(), unit_end), ambiguity=ambiguity,
                )

            # Docket-only forms not covered by a Case/SJC/Docket structured unit.
            for surface, normalized, start, end in raw_docket_tokens(line):
                if any(a <= start < b or a < end <= b for a, b in occupied):
                    continue
                targets = docket_map.get(normalized, set())
                if len(targets) != 1:
                    continue
                target = next(iter(targets))
                prefix = line[max(0, start - 55):start]
                explicit = bool(re.search(r"\b(?:case|cases|sjc|judicial|docket|decision|ruling|no\.?)\b", prefix, re.I))
                add_occurrence(
                    resolved, seen_resolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                    target=target, target_dockets=source_dockets(target, by_id), cited_dockets=[normalized], surface=surface, match_type="docket_explicit" if explicit else "docket_known",
                    signals=["docket"], confidence=0.99 if explicit else 0.95, line_no=line_no,
                    context=context_window(line, start, end),
                )

            # Full-caption/alias forms. Candidate windows are compared only to
            # observed aliases (including role-stripped keys), never guessed from
            # a surname alone.
            for surface, start, end in caption_candidates(line):
                if any(start < b and end > a for a, b in occupied):
                    continue
                targets: set[str] = set()
                for key in caption_keys(surface):
                    targets.update(alias_map.get(key, set()))
                if len(targets) == 1:
                    target = next(iter(targets))
                    add_occurrence(
                        resolved, seen_resolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                        target=target, target_dockets=source_dockets(target, by_id), surface=surface, match_type="caption",
                        signals=["caption"], confidence=0.96, line_no=line_no, context=context_window(line, start, end),
                    )
                elif len(targets) > 1:
                    add_occurrence(
                        unresolved, seen_unresolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                        target=None, target_dockets=[], surface=surface, match_type="caption_ambiguous", signals=["caption"], confidence=0.35,
                        line_no=line_no, context=context_window(line, start, end), ambiguity={"caption_targets": sorted(targets)},
                    )
                elif ECCLESIASTICAL_WORD_RE.search(surface) or re.search(r"\b(?:case|sjc|judicial|docket)\b", line[max(0, start - 40):start], re.I):
                    add_occurrence(
                        unresolved, seen_unresolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                        target=None, target_dockets=[], surface=surface, match_type="caption_unresolved", signals=["caption"], confidence=0.25,
                        line_no=line_no, context=context_window(line, start, end),
                    )
                else:
                    stats["caption_like_filtered"] += 1
                    if len(stats["caption_like_filtered_examples"]) < 20:
                        stats["caption_like_filtered_examples"].append(surface)

            # Minutes-only references. Structured docket+minutes units above
            # already own their evidence span; this captures standalone locators.
            for m in MINUTES_REF_RE.finditer(line):
                if any(a <= m.start() < b for a, b in occupied):
                    continue
                ga_token = m.group("ga")
                ga = int(ga_token.lstrip("Mm"))
                start_page = int(m.group("start")); end_page = int(m.group("end") or start_page)
                targets = resolve_minutes(ga, start_page, end_page, minutes_map)
                surface = m.group(0)
                if len(targets) == 1:
                    target = next(iter(targets))
                    add_occurrence(
                        resolved, seen_resolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                        target=target, target_dockets=source_dockets(target, by_id), surface=surface, match_type="minutes",
                        signals=["minutes"], confidence=0.92, line_no=line_no, context=context_window(line, m.start(), m.end()),
                    )
                elif targets:
                    add_occurrence(
                        unresolved, seen_unresolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                        target=None, target_dockets=[], surface=surface, match_type="minutes_ambiguous", signals=["minutes"], confidence=0.3,
                        line_no=line_no, context=context_window(line, m.start(), m.end()), ambiguity={"minutes_targets": sorted(targets)},
                    )

            # Surname-plus-case/decision forms are retained as unresolved even
            # when only one matching caption exists. This honors the rule that
            # surname-only shorthand is not automatically safe.
            for m in SHORT_CASE_REF_RE.finditer(line):
                name = m.group("name") or m.group("name2")
                if not name or name.casefold() not in surname_names:
                    continue
                surface = m.group(0)
                add_occurrence(
                    unresolved, seen_unresolved, source_decision=source, source_file=str(page.relative_to(ROOT)), source_ds=source_ds,
                    target=None, target_dockets=[], surface=surface, match_type="short_alias", signals=["alias"], confidence=0.2,
                    line_no=line_no, context=context_window(line, m.start(), m.end()), ambiguity={"surname_targets": sorted(surname_names[name.casefold()])},
                )

    # A docket+caption occurrence can teach the registry a concise alias that
    # appears later as caption-only prose. Run a deterministic second pass over
    # only those previously unresolved caption candidates. Ambiguous learned
    # keys remain unresolved; shorthand is never promoted here.
    _, learned_alias_map, learned_by_id = make_maps(registry)
    still_unresolved: list[Occurrence] = []
    for occurrence in unresolved:
        if occurrence.match_type != "caption_unresolved":
            still_unresolved.append(occurrence)
            continue
        targets: set[str] = set()
        for key in caption_keys(occurrence.surface_text):
            targets.update(learned_alias_map.get(key, set()))
        if len(targets) != 1:
            still_unresolved.append(occurrence)
            continue
        target = next(iter(targets))
        item = asdict(occurrence)
        item.update({
            "target_decision": target,
            "target_dockets": source_dockets(target, learned_by_id),
            "match_type": "caption_learned",
            "signals": ["caption"],
            "confidence": 0.9,
            "self_reference": target == item["source_decision"],
            "ambiguity": None,
        })
        resolved.append(Occurrence(**item))
        stats["caption_resolved_from_learned_aliases"] = stats.get("caption_resolved_from_learned_aliases", 0) + 1
    unresolved = still_unresolved

    # Learned aliases are now reflected in normalized_aliases and explicit
    # collision metadata. They are observations, not automatically safe keys.
    _, final_alias_map, _ = make_maps(registry)
    for entry in registry:
        entry["normalized_aliases"] = sorted({key for alias in entry.get("aliases_used_for_matching", entry["aliases_observed"]) for key in caption_keys(alias)})
        collisions = []
        for key in entry["normalized_aliases"]:
            targets = sorted(final_alias_map.get(key, set()))
            if len(targets) > 1:
                collisions.append({"key": key, "decision_ids": targets})
        entry["alias_collisions"] = collisions
    return [asdict(x) for x in resolved], [asdict(x) for x in unresolved], stats


def surname_alias_map(registry: list[dict[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = collections.defaultdict(set)
    generic = {
        "appeal", "case", "commission", "complaint", "congregation", "decision",
        "docket", "judicial", "matter", "opinion", "pca", "petition", "reference",
        "report", "ruling", "session", "v",
    }
    for entry in registry:
        for alias in entry.get("aliases_observed", []):
            key = caption_key(alias)
            if " v " not in key:
                continue
            left = key.split(" v ", 1)[0].split()
            if left and left[-1] not in generic and re.fullmatch(r"[a-z][a-z'’-]{2,}", left[-1], re.I):
                out[left[-1]].add(entry["decision_id"])
    return out


def graph_edges(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for candidate in candidates:
        source = candidate.get("source_decision")
        target = candidate.get("target_decision")
        if not source or not target or candidate.get("self_reference"):
            continue
        buckets[(source, target)].append(candidate)
    edges: list[dict[str, Any]] = []
    for (source, target), occurrences in sorted(buckets.items()):
        edges.append({
            "source": source,
            "target": target,
            "occurrences": len(occurrences),
            "evidence": [{
                "surface_text": item["surface_text"],
                "cited_dockets": item.get("cited_dockets", []),
                "target_dockets": item.get("target_dockets", []),
                "match_type": item["match_type"],
                "signals": item.get("signals", []),
                "confidence": item["confidence"],
                "source_file": item["source_file"],
                "line": item["line"],
                "context": item["context"],
            } for item in occurrences],
        })
    return edges


def citation_graph(candidates: list[dict[str, Any]], decision_ids: Iterable[str] | None = None) -> dict[str, Any]:
    edges = graph_edges(candidates)
    forward: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    backward: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for index, edge in enumerate(edges):
        forward[edge["source"]].append({"decision_id": edge["target"], "occurrences": edge["occurrences"], "edge_index": index})
        backward[edge["target"]].append({"decision_id": edge["source"], "occurrences": edge["occurrences"], "edge_index": index})
    for decision_id in decision_ids or []:
        forward.setdefault(decision_id, [])
        backward.setdefault(decision_id, [])
    return {
        "version": 1,
        "status": "exploratory",
        "identity_unit": "decision/page; consolidated dockets share one node",
        "edges": edges,
        "forward": {key: value for key, value in sorted(forward.items())},
        "backward": {key: value for key, value in sorted(backward.items())},
        "cites": {key: [x["decision_id"] for x in value] for key, value in sorted(forward.items())},
        "cited_by": {key: [x["decision_id"] for x in value] for key, value in sorted(backward.items())},
    }


def entry_label(decision_id: str, by_id: dict[str, dict[str, Any]]) -> str:
    entry = by_id.get(decision_id, {})
    return entry.get("canonical_caption_provisional") or decision_id


def pct(n: int, denominator: int) -> str:
    return f"{(100.0 * n / denominator):.1f}%" if denominator else "0.0%"


def occurrence_form(item: dict[str, Any]) -> str:
    signals = set(item.get("signals", []))
    if item.get("match_type") == "short_alias":
        return "shortened reference"
    if item.get("match_type") == "docket_caption_conflict":
        return "docket + caption conflict"
    if signals == {"docket"}:
        return "docket-only"
    if signals == {"caption"}:
        return "full/observed caption"
    if signals == {"minutes"}:
        return "minutes-only"
    if signals == {"docket", "caption", "minutes"}:
        return "docket + caption + minutes"
    if signals == {"docket", "caption"}:
        return "docket + caption"
    if signals == {"docket", "minutes"}:
        return "docket + minutes"
    return item.get("match_type", "other")


def display_example(items: list[dict[str, Any]], form: str) -> str | None:
    for item in items:
        if occurrence_form(item) == form:
            return f"`{item['surface_text']}` ({item['source_file']}:L{item['line']})"
    return None


def occurrence_target_options(item: dict[str, Any]) -> list[str]:
    """Return all registered decision targets suggested by an occurrence.

    The unresolved dataset keeps the evidence sources separate because a
    docket, caption, fingerprint, and Minutes locator may disagree. For the
    report, their union is the set of decision-level options a reviewer needs
    to inspect.
    """
    ambiguity = item.get("ambiguity") or {}
    target_keys = ("docket_targets", "caption_targets", "caption_fingerprint_targets", "minutes_targets", "surname_targets")
    targets: set[str] = set()
    for key in target_keys:
        targets.update(ambiguity.get(key, []))
    return sorted(targets)


def is_observed_ambiguity(item: dict[str, Any]) -> bool:
    """Whether an unresolved occurrence has competing evidence/options.

    A one-target surname shorthand is intentionally unresolved by policy, but
    it is not an ambiguity in the registry. A missing/unrecognized caption or
    docket is unresolved without being a competing-target ambiguity.

    Explicit lists such as ``Cases 92-7 and 92-8`` are kept out of this count
    when docket evidence is the only issue. They are compound references that
    need decomposition into multiple target occurrences, not a choice between
    competing identities. A compound list with conflicting caption or Minutes
    evidence remains an actual ambiguity.
    """
    match_type = item.get("match_type")
    if is_compound_docket_occurrence(item) and item.get("match_type") != "docket_caption_conflict":
        return False
    if match_type in {"caption_ambiguous", "minutes_ambiguous", "docket_caption_conflict"}:
        return True
    if match_type == "docket_unresolved":
        return len((item.get("ambiguity") or {}).get("docket_targets", [])) > 1
    if match_type == "short_alias":
        return len((item.get("ambiguity") or {}).get("surname_targets", [])) > 1
    return False


def is_compound_docket_occurrence(item: dict[str, Any]) -> bool:
    """Whether an unresolved record is an explicit multi-docket reference."""
    return (
        item.get("match_type") in {"docket_unresolved", "docket_caption_conflict"}
        and len((item.get("ambiguity") or {}).get("cited_dockets", [])) > 1
    )


def md_cell(value: Any) -> str:
    return " ".join(str(value).split()).replace("|", r"\|")


def ambiguity_options_text(item: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    ambiguity = item.get("ambiguity") or {}
    groups = (
        ("docket", "docket_targets"),
        ("caption", "caption_targets"),
        ("caption fingerprint", "caption_fingerprint_targets"),
        ("Minutes", "minutes_targets"),
        ("surname", "surname_targets"),
    )
    rendered: list[str] = []
    for label, key in groups:
        targets = ambiguity.get(key, [])
        if not targets:
            continue
        labels = "; ".join(f"`{target}` — {entry_label(target, by_id)}" for target in sorted(targets))
        rendered.append(f"{label}: {labels}")
    missing = ambiguity.get("missing_dockets", [])
    if missing:
        rendered.append("missing docket(s): " + ", ".join(f"`{docket}`" for docket in missing))
    return " / ".join(rendered) or "No registered target option"


def write_report(registry: list[dict[str, Any]], candidates: list[dict[str, Any]], unresolved: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    by_id = {entry["decision_id"]: entry for entry in registry}
    edges = graph_edges(candidates)
    total = len(candidates) + len(unresolved)
    resolved_docket = sum("docket" in x.get("signals", []) for x in candidates)
    resolved_caption = sum("caption" in x.get("signals", []) for x in candidates)
    resolved_minutes = sum("minutes" in x.get("signals", []) for x in candidates)
    self_refs = sum(x.get("self_reference", False) for x in candidates + unresolved)
    inbound_edges = collections.Counter(edge["target"] for edge in edges)
    outbound_edges = collections.Counter(edge["source"] for edge in edges)
    inbound_occurrences = collections.Counter()
    outbound_occurrences = collections.Counter()
    for edge in edges:
        inbound_occurrences[edge["target"]] += edge["occurrences"]
        outbound_occurrences[edge["source"]] += edge["occurrences"]
    collision_map: dict[str, set[str]] = collections.defaultdict(set)
    for entry in registry:
        for collision in entry.get("alias_collisions", []):
            collision_map[collision["key"]].update(collision["decision_ids"])
    collisions = [{"key": key, "decision_ids": sorted(decision_ids)} for key, decision_ids in sorted(collision_map.items())]
    unresolved_shapes = collections.Counter((x.get("match_type"), x.get("surface_text")) for x in unresolved)
    forms = collections.Counter(occurrence_form(x) for x in candidates + unresolved)
    observed_ambiguities = [x for x in unresolved if is_observed_ambiguity(x)]
    compound_docket_occurrences = [x for x in unresolved if is_compound_docket_occurrence(x)]
    unresolved_without_competing_options = [
        x for x in unresolved
        if not is_observed_ambiguity(x) and not is_compound_docket_occurrence(x)
    ]
    observed_ambiguity_types = collections.Counter(x.get("match_type", "") for x in observed_ambiguities)
    consolidated = [x for x in registry if x.get("consolidated")]
    docket_owners: dict[str, list[str]] = collections.defaultdict(list)
    for entry in registry:
        for docket in entry.get("docket_numbers", []):
            docket_owners[docket].append(entry["decision_id"])
    ambiguous_dockets = {docket: owners for docket, owners in docket_owners.items() if len(owners) > 1}

    lines = [
        "# Case-reference exploratory report",
        "",
        "Generated by `scripts/48_case_citation_inventory.py`. This is an audit report, not a source of authority.",
        "",
        "## Corpus and identity totals",
        "",
        f"- Case pages scanned: **{len(list(CASES_DIR.glob('*.md')))}**",
        f"- Existing `case_pages_map.json`: **{stats.get('case_map_docket_keys', 0)}** docket keys across **{stats.get('case_map_unique_files', 0)}** unique page files; pages outside the map: **{stats.get('case_pages_without_map_record', 0)}**",
        f"- Decision entities: **{len(registry)}**",
        f"- Unique normalized docket values (matching keys): **{len({d for e in registry for d in e['docket_numbers']})}**",
        f"- Unique observed docket spellings/aliases: **{len({d for e in registry for d in e['docket_aliases_observed']})}**",
        f"- Docket slots across entities: **{sum(len(e['docket_numbers']) for e in registry)}**",
        f"- Entities with multiple dockets (consolidated): **{len(consolidated)}**",
        f"- Entities with no docket number: **{sum(not e['docket_numbers'] for e in registry)}**",
        f"- Normalized docket values shared by multiple page entities (left ambiguous): **{len(ambiguous_dockets)}**",
        f"- Entities with a provisional caption: **{sum(bool(e['canonical_caption_provisional']) for e in registry)}**",
        f"- Entities with observed aliases: **{sum(bool(e['aliases_observed']) for e in registry)}**",
        f"- Digest roster rows loaded: **{stats.get('digest_roster_rows', 0)}** ({stats.get('digest_roster_unique_dockets', 0)} unique normalized docket values)",
        f"- Digest docket values appearing on multiple roster rows: **{stats.get('digest_roster_duplicate_dockets', 0)}**",
        f"- Digest roster rows matched to case pages: **{stats.get('digest_roster_rows_matched_to_pages', 0)}**; unmatched/ambiguous rows retained as provenance: **{stats.get('digest_roster_rows_unmatched_to_pages', 0)}**",
        "",
        "A `decision_id` is the case-page stem. `docket_numbers` are normalized comparison values; observed spellings are retained in `docket_aliases_observed` and provenance. The Digest roster is used as an identity aid and consolidated-docket enrichment only when its match is unambiguous; it does not replace verbatim Minutes text. The registry does not invent surname-only aliases.",
        "",
        "## Candidate resolution",
        "",
        f"- Candidate occurrences: **{total}**",
        f"- Resolved occurrences: **{len(candidates)}** ({pct(len(candidates), total)})",
        f"- Resolved by docket signal: **{resolved_docket}** ({pct(resolved_docket, total)})",
        f"- Resolved by caption signal: **{resolved_caption}** ({pct(resolved_caption, total)})",
        f"- Caption-only occurrences resolved from aliases learned in docket citations: **{stats.get('caption_resolved_from_learned_aliases', 0)}**",
        f"- Resolved by minutes signal: **{resolved_minutes}** ({pct(resolved_minutes, total)})",
        f"- Unresolved/ambiguous occurrences: **{len(unresolved)}** ({pct(len(unresolved), total)})",
        f"- Compound docket units decomposed into decision-level occurrences: **{stats.get('compound_docket_units_decomposed', 0)}**",
        f"- Self-reference occurrences retained for audit: **{self_refs}**",
        f"- Unique non-self directed decision edges: **{len(edges)}**",
        "",
        "Percentages use candidate occurrences as the denominator; a combined docket/caption/minutes occurrence contributes to each applicable signal count.",
        "",
        "## Reference forms observed",
        "",
        "| Form | Occurrences | Example |",
        "|---|---:|---|",
    ]
    for form in ["docket-only", "docket + caption", "docket + caption + minutes", "docket + minutes", "full/observed caption", "minutes-only", "shortened reference", "docket + caption conflict"]:
        lines.append(f"| {form} | {forms.get(form, 0)} | {display_example(candidates + unresolved, form) or '—'} |")
    lines += [
        "",
        "Docket-only includes explicit `Case`/`SJC` forms and known docket tokens whose surrounding prose is less explicit. Ordinary BCO references such as `BCO 31-2` are not in the docket map and are therefore not resolved as cases.",
        "",
        "### Match classifications",
        "",
        "| Classification | Occurrences |",
        "|---|---:|",
    ]
    for match_type, count in collections.Counter(x.get("match_type", "") for x in candidates).most_common():
        lines.append(f"| resolved `{match_type}` | {count} |")
    for match_type, count in collections.Counter(x.get("match_type", "") for x in unresolved).most_common():
        lines.append(f"| unresolved `{match_type}` | {count} |")
    lines += [
        "",
        "## High-value QA examples",
        "",
    ]
    qa_sources = [
        ("Evans (2023-07)", "ga51_2024__2023-07"),
        ("Bigelow (2024-08)", "ga52_2025__2024-08"),
        ("Ruff (2011-18)", "ga41_2013__2011-18"),
    ]
    for label, source in qa_sources:
        lines.append(f"### {label}")
        for item in candidates:
            if item["source_decision"] == source:
                lines.append(f"- `{item['surface_text']}` → `{item['target_decision']}` ({item['match_type']}, line {item['line']})")
        for item in unresolved:
            if item["source_decision"] == source:
                lines.append(f"- **Unresolved:** `{item['surface_text']}` ({item['match_type']}, line {item['line']})")
        if not any(x["source_decision"] == source for x in candidates + unresolved):
            lines.append("- No candidate occurrence recorded.")
        lines.append("")

    consolidated_label = next((e["decision_id"] for e in consolidated if set(e["docket_numbers"]) >= {"2019-10", "2019-12"}), "the consolidated Evans/Pitts decision")
    lines += [
        "## Consolidated decisions",
        "",
        f"The registry contains **{len(consolidated)}** consolidated decision entities. A cited docket resolves to the shared `decision_id`; the occurrence preserves the docket spelling/list actually used. For example, `2019-10` and `2019-12` map to `{consolidated_label}`.",
        "",
        "### Initial compound-reference triage",
        "",
        "The first compound-conflict review found a scanner-boundary problem in three Herron records: an explicit pending-case list was followed by a separate `Case 2022-10 PCA v. Herron` citation on the same line. The scanner now stops a docket-plus-caption unit at the next structured case citation. Those records now produce one decision-level occurrence for each uniquely mapped pending docket, while the later `Case 2022-10` occurrence resolves independently to `ga50_2023__2022-10`.",
        "",
        "The Wills footnote in `cases/ga46_2018__2017-01.md:L334` is now decomposed into two high-confidence decision-level occurrences. Its docket and caption evidence identify both `2015-12` and `2016-14`; the extracted `M45GA` page range also overlaps the registered `2016-12` Minutes range, and the surrounding source text continues with an `M46GA` locator. That locator overlap is retained as secondary evidence on both records rather than allowed to override the explicit docket/caption identity.",
        "",
        "## Ambiguity and false-positive audit",
        "",
        f"- **Observed ambiguous citation occurrences:** **{len(observed_ambiguities)}** of {len(unresolved)} unresolved occurrences ({pct(len(observed_ambiguities), total)} of all candidates). These have competing registered decision targets or explicitly conflicting docket/caption evidence.",
        f"- Compound/multi-docket occurrences still needing decomposition: **{len(compound_docket_occurrences)}**. **{sum(not is_observed_ambiguity(x) for x in compound_docket_occurrences)}** are explicit lists such as `Cases 92-7 and 92-8` and are not identity ambiguities.",
        f"- Unresolved occurrences without competing registered targets: **{len(unresolved_without_competing_options)}**. These are missing/unrecognized dockets or captions, or one-target shorthand withheld by policy.",
        f"- Unique normalized alias collision keys: **{len(collisions)}**",
        f"- Alias collision records across registry entries: **{sum(len(e.get('alias_collisions', [])) for e in registry)}**",
        f"- BCO-like non-case references observed and intentionally excluded: **{stats.get('bco_like_mentions', 0)}**",
        f"- Caption-like X-v-Y windows filtered because they did not look ecclesiastical and did not match an observed alias: **{stats.get('caption_like_filtered', 0)}**",
        f"- Caption-like filtered examples: {', '.join('`' + x + '`' for x in stats.get('caption_like_filtered_examples', [])[:8]) or '—'}",
        "",
        "The next section lists actual citation occurrences needing review. The identity-collision section below is broader: it records registry aliases shared by multiple decision entities even when no ambiguous citation occurrence was observed.",
        "",
        "### Observed ambiguous citation occurrences",
        "",
        "These are occurrence-level ambiguities found in `cases/*.md`, not merely names that happen to collide in the registry. Every row preserves the source line, surface text, context, and the competing evidence/options. The complete machine-readable records remain in `case_reference_unresolved.json`.",
        "",
        "| Ambiguity type | Occurrences |",
        "|---|---:|",
    ]
    for match_type, count in observed_ambiguity_types.most_common():
        lines.append(f"| `{match_type}` | {count} |")
    lines += [
        "",
        "| Source | Line | Match type | Surface text | Candidate options / conflicting evidence | Context |",
        "|---|---:|---|---|---|---|",
    ]
    for item in observed_ambiguities:
        lines.append(
            f"| `{md_cell(item['source_file'])}` | {item['line']} | `{md_cell(item['match_type'])}` | `{md_cell(item['surface_text'])}` | {md_cell(ambiguity_options_text(item, by_id))} | {md_cell(item.get('context', ''))} |"
        )
    if not observed_ambiguities:
        lines.append("| — | — | — | No observed competing-target ambiguity | — | — |")
    lines += [
        "",
        "### Identity-level alias collisions (not necessarily observed citation ambiguities)",
        "",
        "These records show matching keys shared by multiple decision entities. They are useful for explaining why a future caption-only occurrence may need review, but they are not themselves evidence that such a citation occurred in the corpus.",
        "",
        "### Ambiguous docket mappings",
        "",
        "These docket values are present on more than one page entity in the existing corpus indexes and therefore do not receive automatic docket resolution:",
        "",
        "| Docket | Page entities |",
        "|---|---|",
    ]
    for docket, owners in sorted(ambiguous_dockets.items()):
        lines.append(f"| `{docket}` | {', '.join(f'`{owner}`' for owner in owners)} |")
    lines += [
        "",
        "### Ambiguous alias collisions",
        "",
        "| Normalized matching key | Decision entities |",
        "|---|---|",
    ]
    for collision in sorted(collisions, key=lambda x: (-len(x["decision_ids"]), x["key"]))[:30]:
        labels = "; ".join(f"`{decision_id}` ({entry_label(decision_id, by_id)})" for decision_id in collision["decision_ids"])
        lines.append(f"| `{collision['key']}` | {labels} |")
    lines += [
        "### Common unresolved shapes",
        "",
        "| Shape | Count |",
        "|---|---:|",
    ]
    for (match_type, surface), count in unresolved_shapes.most_common(30):
        lines.append(f"| `{match_type}: {surface}` | {count} |")
    lines += ["", "### Unresolved high-value candidates", ""]
    high_value = [x for x in unresolved if x.get("match_type") in {"docket_caption_conflict", "docket_unresolved", "caption_ambiguous", "minutes_ambiguous", "short_alias"}]
    for item in high_value[:30]:
        lines.append(f"- `{item['surface_text']}` — {item['source_file']}:L{item['line']} ({item['match_type']}); ambiguity `{json.dumps(item.get('ambiguity', {}), ensure_ascii=False, sort_keys=True)}`")
    if not high_value:
        lines.append("- None recorded.")

    lines += [
        "",
        "## Most cited decisions",
        "",
        "| Decision | Caption | Distinct citing decisions | Occurrences |",
        "|---|---|---:|---:|",
    ]
    for target, count in inbound_edges.most_common(25):
        lines.append(f"| `{target}` | {entry_label(target, by_id)} | {count} | {inbound_occurrences[target]} |")
    lines += [
        "",
        "## Decisions with the most outgoing edges",
        "",
        "| Decision | Caption | Distinct targets | Occurrences |",
        "|---|---|---:|---:|",
    ]
    for source, count in outbound_edges.most_common(25):
        lines.append(f"| `{source}` | {entry_label(source, by_id)} | {count} | {outbound_occurrences[source]} |")
    lines += [
        "",
        "## Recommendations for inline linking",
        "",
        "1. Link explicit, uniquely mapped docket citations first; this is the most deterministic grammar and naturally handles consolidated decisions.",
        "2. Link full captions only when their normalized observed alias maps to one decision. Keep `v`/`v.`/`vs`/`versus` and role-prefix normalization as matching keys, not display rewrites.",
        "3. Use docket + caption + Minutes citations to learn aliases, but retain conflicts such as the Bigelow `2012-08`/Jackson citation for manual review.",
        "4. Leave surname-only forms (`the Ruff case`, `the prior Evans decision`) unresolved until a semantic/context pass proves them safe.",
        "5. Preserve occurrence context and later classify majority reasoning, dissent/concurrence, procedural history, and quoted party material before presenting citations as precedent.",
        "",
        "## Deterministic-resolution conclusion",
        "",
        f"Most high-confidence PCA case references are deterministically resolvable from docket numbers once docket normalization and BCO guards are applied: **{resolved_docket} of {total} candidate occurrences ({pct(resolved_docket, total)})** carry a resolved docket signal. Caption-only and shorthand references still require learned-alias collision checks and a modest manual/entity-resolution queue; the corpus should not treat the raw overall resolution percentage as permission to guess.",
        "",
        "The current foundation is therefore suitable for an exploratory graph and a first inline-linking pass limited to high-confidence docket/unique-caption matches, but not yet for automatic resolution of all textual mentions.",
        "",
    ]
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(registry: list[dict[str, Any]], candidates: list[dict[str, Any]], unresolved: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    OUT_REGISTRY.write_text(json.dumps({
        "version": 2,
        "status": "exploratory",
        "identity_unit": "one adjudicated decision/page; consolidated dockets share one node",
        "entries": registry,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_CANDIDATES.write_text(json.dumps({
        "version": 2,
        "status": "exploratory",
        "occurrences": candidates,
        "edges": graph_edges(candidates),
        "scan_stats": stats,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_UNRESOLVED.write_text(json.dumps({
        "version": 2,
        "status": "exploratory",
        "occurrences": unresolved,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    decision_ids = [entry["decision_id"] for entry in registry]
    OUT_CITATIONS.write_text(json.dumps(citation_graph(candidates, decision_ids), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(registry, candidates, unresolved, stats)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", help="Repository root; defaults to PCA_GA_ROOT or cwd")
    args = parser.parse_args()
    global ROOT, CASES_INDEX, CASE_MAP, ROSTER_PATH, CASES_DIR, OUT_REGISTRY, OUT_CANDIDATES, OUT_UNRESOLVED, OUT_CITATIONS, OUT_REPORT
    if args.root:
        ROOT = Path(args.root).resolve()
        CASES_INDEX = ROOT / "index" / "CASES.md"
        CASE_MAP = ROOT / "index" / "case_pages_map.json"
        ROSTER_PATH = ROOT / "index" / "sjc_official" / "roster.jsonl"
        CASES_DIR = ROOT / "cases"
        OUT_REGISTRY = ROOT / "index" / "case_identity_registry.json"
        OUT_CANDIDATES = ROOT / "index" / "case_reference_candidates.json"
        OUT_UNRESOLVED = ROOT / "index" / "case_reference_unresolved.json"
        OUT_CITATIONS = ROOT / "index" / "case_citations.json"
        OUT_REPORT = ROOT / "index" / "CASE-REFERENCE-REPORT.md"
    if not CASES_INDEX.exists():
        raise SystemExit(f"missing {CASES_INDEX}")
    if not CASES_DIR.is_dir():
        raise SystemExit(f"missing {CASES_DIR}")
    rows = parse_index(CASES_INDEX)
    case_map = load_case_map(CASE_MAP)
    digest_rows = load_digest_roster(ROSTER_PATH)
    registry = build_registry(rows, case_map, digest_rows)
    candidates, unresolved, stats = scan_references(registry)
    digest_row_keys = {json.dumps(row, sort_keys=True) for row in digest_rows}
    matched_digest_row_keys = {
        json.dumps(row, sort_keys=True)
        for entry in registry
        for row in entry.get("digest_roster", [])
    }
    digest_dockets = {docket for row in digest_rows for docket in roster_dockets(row)}
    stats.update({
        "index_rows": len(rows),
        "case_map_docket_keys": len(case_map),
        "case_map_unique_files": len({record.get("file") for record in case_map.values() if record.get("file")}),
        "case_pages_without_map_record": sum(not any(record.get("file") == entry["decision_id"] for record in case_map.values()) for entry in registry),
        "digest_roster_rows": len(digest_rows),
        "digest_roster_unique_dockets": len(digest_dockets),
        "digest_roster_duplicate_dockets": sum(1 for docket in digest_dockets if sum(docket in roster_dockets(row) for row in digest_rows) > 1),
        "digest_roster_rows_matched_to_pages": len(matched_digest_row_keys),
        "digest_roster_rows_unmatched_to_pages": len(digest_row_keys - matched_digest_row_keys),
    })
    write_outputs(registry, candidates, unresolved, stats)
    print(f"identity entities: {len(registry)}")
    print(f"docket aliases: {len({d for e in registry for d in e['docket_numbers']})}")
    print(f"resolved reference occurrences: {len(candidates)}")
    print(f"unresolved/ambiguous occurrences: {len(unresolved)}")
    print(f"graph edges: {len(graph_edges(candidates))}")
    print("wrote index/case_identity_registry.json")
    print("wrote index/case_reference_candidates.json")
    print("wrote index/case_reference_unresolved.json")
    print("wrote index/case_citations.json")
    print("wrote index/CASE-REFERENCE-REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
