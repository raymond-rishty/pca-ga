#!/usr/bin/env python3
"""
04_structure_tag.py — Phase 4: era-parameterized structural tagging of the PCA
GA minutes corpus into citable sections.

INPUT  (source of truth):  build/page_jsonl/<vol>.pages.jsonl  (one row/page)
OUTPUT (deliverable):      index/chunks.jsonl                  (one row/section)
       per-volume appendix tables: build/appendix_tables/<vol>.appendix.json

DESIGN (obey PLAN.md Phase 4):
  * Nothing assumes a fixed appendix letter. The per-volume appendix table is
    extracted from THAT volume's own TOC (letter -> title -> start page).
  * Journal items use \\b(\\d{1,2})-(\\d{1,3})\\b VALIDATED so the left group ==
    this volume's ga_ordinal, so a `BCO 34-1` cite is never mistaken for item 34-1.
  * SJC decisions segment on the party-vs-court / CASE NO. caption; sub-chunk on
    Roman headers (I. SUMMARY ... III. JUDGMENT ... IV. REASONING) when present;
    extract case number, disposition, roll-call vote, dissent/concur, precedent
    cites (M<NN>GA ... p.<n>). Pre-SJC eras (no SJC structure) are labeled by
    heading + page gracefully.
  * CCB responses: the Committee-on-Constitutional-Business report; RAO-style
    minute-review exceptions; per-overture advice verdicts.
  * Shared citation extraction (dual index): BCO NN-NN(.word)* AND bare BCO NN
    (both stored, so a search for "BCO 34" catches 34, 34-1, 34-3); RAO, WCF,
    WLC/WSC, scripture, normalized OVERTURE ids.

ERA MODEL (from golden labels + corpus inspection):
  early-scanned-no-item-id  year<=1976 (GAs 1-4)   no SJC/CCB; committee analogs
  mid-scanned               1977-2002, no SJC yet  per-case judicial commissions;
                                                    Committee on Judicial Business
  early-digital             2003-~2011             SJC/CCB inline in the Journal
  modern-digital            ~2012+                 SJC/CCB are lettered appendices
  (era is derived per volume from text signals, not hardcoded by year alone:
   has_sjc / has_ccb are detected from the actual presence of the report.)

All scripts: /workspace/.venv/bin/python, idempotent (skip done work unless
--force), resumable. Render anchors are injected into markdown only with
--inject-anchors (off by default; chunks.jsonl is the primary deliverable).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGE_JSONL_DIR = os.path.join(ROOT, "build", "page_jsonl")
APPENDIX_DIR = os.path.join(ROOT, "build", "appendix_tables")
INDEX_DIR = os.path.join(ROOT, "index")
GOLDEN_DIR = os.path.join(ROOT, "golden", "labels")
OUT_CHUNKS = os.path.join(INDEX_DIR, "chunks.jsonl")

sys.path.insert(0, HERE)
import normalize  # noqa: E402  shared dict/tokenizer/de-space


# ===========================================================================
# de-emphasis: strip markdown bold/italic/heading markers so regex sees plain
# text (born-digital pages are full of **...** and _.._; OCR pages are plain).
# ===========================================================================
def deemph(text: str) -> str:
    t = text.replace("­", "")
    t = re.sub(r"\*+", "", t)
    # markdown italics underscores: strip when adjacent to a non-word boundary on
    # at least one side (so '_BCO_ 34-1', 'RAO_ 16-3', '_See_' all normalize), but
    # keep genuine intra-token underscores (rare in this corpus).
    t = re.sub(r"(?<!\w)_+", "", t)             # leading italic markers
    t = re.sub(r"_+(?!\w)", "", t)              # trailing italic markers (RAO_ )
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    return t


def collapse_caps_spacing(s: str) -> str:
    """Tolerate space-shattered ALL-CAPS Roman headers: 'I . S U M M A R Y'.
    Collapses internal single-spaces between solitary capitals/letters."""
    # join sequences like 'S U M M A R Y' -> 'SUMMARY'
    return re.sub(r"(?:\b[A-Z]\b ?){3,}", lambda m: m.group(0).replace(" ", ""), s)


# ===========================================================================
# SHARED CITATION EXTRACTION  (dual-index)
# ===========================================================================
# BCO chapter range: FoG 1-25, RoD 31-46, DfW 47-63  (+ a little slack)
BCO_FULL_RE = re.compile(r"\bBCO\s*0*(\d{1,2})-(\d{1,2})(?:[.-](\w{1,4}))?", re.I)
BCO_BARE_RE = re.compile(r"\bBCO\s*0*(\d{1,2})\b", re.I)
# RAO chapter must end at a boundary (not be the prefix of a longer number like a
# hyphen-dropped 'RAO 146' = RAO 14-6); allow an optional -section and .subsection.
RAO_RE = re.compile(r"\bRAO[ \t]*0*(\d{1,2})(?!\d)(?:-(\d{1,2}))?(?:\.(\w{1,3}))?", re.I)
WCF_RE = re.compile(r"\bWCF\s*([IVXLCDM]+|\d{1,2})(?:[.:]\s*(\d{1,2}))?", re.I)
WLC_RE = re.compile(r"\b(?:WLC|WSC|Larger Catechism|Shorter Catechism|Q\.?\s*\d{1,3})\b", re.I)
# scripture: Book Chapter:Verse  (book = capitalized word, possibly with leading digit)
SCRIPTURE_RE = re.compile(
    r"\b((?:[1-3]\s?)?[A-Z][a-z]+)\.?\s+(\d{1,3}):(\d{1,3}(?:-\d{1,3})?)")
SCRIPTURE_BOOKS = frozenset("""
genesis exodus leviticus numbers deuteronomy joshua judges ruth samuel kings
chronicles ezra nehemiah esther job psalm psalms proverbs ecclesiastes song
isaiah jeremiah lamentations ezekiel daniel hosea joel amos obadiah jonah micah
nahum habakkuk zephaniah haggai zechariah malachi matthew mark luke john acts
romans corinthians galatians ephesians philippians colossians thessalonians
timothy titus philemon hebrews james peter jude revelation tim cor thess
""".split())
OVERTURE_RE = re.compile(r"\bOverture\s+(?:No\.?\s*)?(\d{1,3})\b", re.I)
# precedent cite: M<NN>GA ... p. <n>  (e.g. "M30GA, 30-50, III,1, p. 213")
PRECEDENT_RE = re.compile(
    r"\bM\s*(\d{1,2})\s*GA\b(?:[^.\n]{0,60}?p+\.\s*(\d{1,4}))?", re.I)


def extract_citations(text: str) -> dict:
    """Returns bco_citations (full NN-NN[.w]), bco_chapters (bare ints, dual-index),
    rao_citations, wcf_citations, wlc_refs(bool/list), scripture_refs, overtures,
    precedent_cites."""
    bco_full, bco_chapters = [], set()
    for m in BCO_FULL_RE.finditer(text):
        ch = int(m.group(1)); sec = int(m.group(2))
        if 1 <= ch <= 66:
            tail = f".{m.group(3)}" if m.group(3) else ""
            bco_full.append(f"{ch}-{sec}{tail}")
            bco_chapters.add(ch)
    for m in BCO_BARE_RE.finditer(text):
        ch = int(m.group(1))
        if 1 <= ch <= 66:
            bco_chapters.add(ch)        # dual-index: bare chapter catches "BCO 34"
    rao = []
    for m in RAO_RE.finditer(text):
        a = int(m.group(1))
        if 1 <= a <= 20:
            cite = f"RAO {a}"
            if m.group(2):
                cite += f"-{int(m.group(2))}"
            if m.group(3):
                cite += f".{m.group(3)}"
            rao.append(cite)
    wcf = []
    for m in WCF_RE.finditer(text):
        wcf.append(m.group(0).upper().replace("  ", " ").strip())
    scripture = []
    for m in SCRIPTURE_RE.finditer(text):
        book = re.sub(r"\s+", "", m.group(1)).lower()
        bare = re.sub(r"^[1-3]", "", book)
        if bare in SCRIPTURE_BOOKS or book in SCRIPTURE_BOOKS:
            scripture.append(f"{m.group(1).strip()} {m.group(2)}:{m.group(3)}")
    overtures = sorted({m.group(1) for m in OVERTURE_RE.finditer(text)}, key=int)
    precedents = []
    for m in PRECEDENT_RE.finditer(text):
        pg = m.group(2)
        precedents.append(f"M{m.group(1)}GA" + (f" p.{pg}" if pg else ""))
    wlc = bool(WLC_RE.search(text))
    return {
        "bco_citations": _dedup(bco_full),
        "bco_chapters": sorted(bco_chapters),
        "rao_citations": _dedup(rao),
        "wcf_citations": _dedup(wcf),
        "wlc_wsc_refs": wlc,
        "scripture_refs": _dedup(scripture),
        "overtures": overtures,
        "precedent_cites": _dedup(precedents),
    }


def _dedup(seq):
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


# ===========================================================================
# APPENDIX TABLE — extract from each volume's own TOC (letter -> title -> page)
# ===========================================================================
# Tolerate: 'APPENDIX O Title 419', 'appendix i — judicial business ... 329',
#           'A ppend ixO — Theological Examining 424' (OCR despacing of "Appendix").
APPENDIX_LINE_RE = re.compile(
    r"""^\s*
        A\s?p\s?p\s?e\s?n\s?d\s?i\s?x        # APPENDIX, possibly OCR-spaced
        \s*[-:—]?\s*
        ([A-Z])\b                            # the letter
        \s*[-:—.]?\s*
        (.+?)                                # title
        \s*[.…\s]{2,}\s*                 # dotted leaders / spaces
        (\d{1,4})\s*$                         # start page
    """, re.I | re.X)
# Fallback for lines without strong leaders (title then trailing page number)
APPENDIX_LINE_RE2 = re.compile(
    r"^\s*A\s?p\s?p\s?e\s?n\s?d\s?i\s?x\s*[-:—]?\s*([A-Z])\b[ \t]+(.+?)[ \t]+(\d{1,4})\s*$",
    re.I)


def extract_appendix_table(pages: list[dict]) -> list[dict]:
    """Scan the front-matter TOC pages for appendix letter/title/start-page rows.
    Returns ordered list of {letter,title,start_page}. De-duplicates by letter,
    keeping the first plausible occurrence (the TOC), tolerant of OCR spacing."""
    table = OrderedDict()
    # TOC is in front matter: scan first ~12 pages (and any page mentioning
    # 'APPENDICES' + multiple appendix lines).
    scan = pages[:14]
    for pg in scan:
        text = deemph(pg["text"])
        for line in text.split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            m = APPENDIX_LINE_RE.match(line) or APPENDIX_LINE_RE2.match(line)
            if not m:
                continue
            letter = m.group(1).upper()
            title = m.group(2).strip(" .-—…")
            try:
                start = int(m.group(3))
            except ValueError:
                continue
            # title sanity: must contain a letter, not be absurdly long
            if not re.search(r"[A-Za-z]", title) or len(title) > 80:
                continue
            if letter not in table:
                table[letter] = {"letter": letter, "title": title,
                                 "start_page": start}
    return list(table.values())


# ===========================================================================
# ERA DETECTION
# ===========================================================================
def detect_era(ga_ordinal: int, year: int, full_text: str) -> str:
    if year <= 1976:
        return "early-scanned-no-item-id"
    if year < 2003:
        return "mid-scanned"
    # 2003+: digital. Modern era keeps SJC/CCB as lettered appendices;
    # early-digital keeps them inline. Decide by whether the SJC report is an
    # APPENDIX header anywhere.
    if re.search(r"APPENDIX\s+[A-Z]\b[^\n]{0,40}STANDING JUDICIAL", full_text, re.I):
        return "modern-digital"
    return "early-digital"


def has_report(full_text: str, pattern: str) -> bool:
    return bool(re.search(pattern, full_text, re.I))


# ===========================================================================
# JOURNAL ITEM segmentation
# ===========================================================================
def journal_item_spans(text: str, ordinal: int):
    """Find journal-item header positions in a page's de-emphasized text.
    A header is a line beginning with NN-N where NN == this GA ordinal.
    Returns [(start_idx, item_id, header_line)]."""
    spans = []
    for m in re.finditer(r"(?m)^\s*(\d{1,2})-(\d{1,3})\b(.*)$", text):
        if int(m.group(1)) == ordinal:
            item = f"{m.group(1)}-{m.group(2)}"
            spans.append((m.start(), item, m.group(0).strip()))
    return spans


def all_item_ids(text: str, ordinal: int):
    out, seen = [], set()
    for m in re.finditer(r"\b(\d{1,2})-(\d{1,3})\b", text):
        if int(m.group(1)) == ordinal:
            tok = f"{m.group(1)}-{m.group(2)}"
            if tok not in seen:
                seen.add(tok); out.append(tok)
    return out


# ===========================================================================
# SJC DECISION matchers (era-parameterized)
# ===========================================================================
CASE_NO_RE = re.compile(r"\bCASE\s*(?:NO\.?)?\s*((?:19|20)\d{2}-\d{1,3})", re.I)
CASE_INLINE_RE = re.compile(r"\bCase\s+((?:19|20)\d{2}-\d{1,3})\b")
# party v court caption (modern uses 'V.' on its own line; inline uses 'vs.')
VS_RE = re.compile(r"\bv[s]?\.\s", re.I)

DISPOSITION_PATTERNS = [
    (r"complaint(?:s)?\s+(?:is|are|was|were)?\s*sustained", "sustained"),
    (r"appeal\s+(?:is|was)?\s*sustained", "sustained"),
    (r"(?:is|are|was|were)\s+sustained", "sustained"),
    (r"sustained in part|partially sustained|sustained.{0,30}in part", "partially_sustained"),
    (r"complaint(?:s)?\s+(?:is|are|was|were)?\s*denied", "denied"),
    (r"appeal\s+(?:is|was)?\s*denied", "denied"),
    (r"(?:is|are|was|were)\s+denied", "denied"),
    (r"not\s+(?:judicially\s+)?in order|found\s+out of order|out of order", "out_of_order"),
    (r"dismiss(?:ed)?|abandoned|withdrawn", "dismissed"),
    (r"appeal\s+(?:is|was)?\s*granted|granted in part", "granted"),
    (r"reference\s+not acceded", "referred"),
]
DISPOSITION_COMPILED = [(re.compile(p, re.I), v) for p, v in DISPOSITION_PATTERNS]

ROMAN_HEADERS = [
    ("summary", re.compile(r"\b(?:SUMMARY OF THE (?:FACTS|CASE)|STATEMENT OF (?:THE )?FACTS)\b", re.I)),
    ("issues", re.compile(r"\bSTATEMENT OF (?:THE )?ISSUES?\b", re.I)),
    ("judgment", re.compile(r"\bJUDGMENT\b", re.I)),
    ("reasoning", re.compile(r"\bREASONING(?:\s+AND OPINION)?\b|\bOPINION\b", re.I)),
]
VOTE_RE = re.compile(
    r"(\d{1,3})\s*(?:concur|to|in favor)[^\n]{0,40}?(\d{1,3})\s*(?:dissent|against|oppose|opposed)",
    re.I)
VOTE_TALLY_RE = re.compile(r"\bvote[:\s]+(\d{1,3})\s*[-/to]+\s*(\d{1,3})(?:\s*[-/]\s*(\d{1,3}))?", re.I)
DISSENT_RE = re.compile(r"\b(dissent|dissenting opinion|negative vote.{0,30}recorded)\b", re.I)
CONCUR_OP_RE = re.compile(r"\bconcurring opinion\b", re.I)


def find_disposition(text: str) -> str | None:
    low = text
    found = None
    for rx, verdict in DISPOSITION_COMPILED:
        if rx.search(low):
            # prefer partially_sustained / granted specificity
            if verdict in ("partially_sustained",):
                return verdict
            if found is None:
                found = verdict
    return found


ROLLCALL_MARK_RE = re.compile(r"\b(?:Roll[\s-]*call vote|approved.{0,30}roll[\s-]*call|"
                              r"following roll[\s-]*call vote)\b", re.I)


def find_vote(text: str) -> str | None:
    """Extract the SJC/commission DECISION vote, normalized as 'NC-ND-NA[-NR]'
    (Concur/Dissent/Absent/Recused counts), preferring a roll-call block keyed to
    the decision. Avoids narrated lower-court votes ('Presbytery ... (vote 38-17)')
    by scoping roll-call counts to text AFTER a roll-call marker."""
    # 1) roll-call block: count Concur/Dissent/Absent/Recused AFTER the marker.
    mk = ROLLCALL_MARK_RE.search(text)
    scope = text[mk.start():] if mk else text
    concur = len(re.findall(r"\bConcur\b", scope))
    dissent = len(re.findall(r"\bDissent\b", scope))
    absent = len(re.findall(r"\bAbsent\b", scope))
    recused = len(re.findall(r"\b(?:Recused|Disqualified)\b", scope, re.I))
    if concur >= 3:
        out = f"{concur}C"
        if dissent:
            out += f"-{dissent}D"
        if absent:
            out += f"-{absent}A"
        if recused:
            out += f"-{recused}R"
        return out
    # 2) explicit labeled SJC/commission tally (not a narrated lower-court vote):
    #    require it to sit next to a decision verb.
    m = re.search(r"(?:adopted|approved|sustained|denied|carried)[^\n]{0,40}?"
                  r"\b(\d{1,3})\s*[-/to]+\s*(\d{1,3})\b", text, re.I)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


# ===========================================================================
# CCB matchers
# ===========================================================================
CCB_VERDICT_PATTERNS = [
    (re.compile(r"\bcreates?\s+(?:a\s+)?conflict\b", re.I), "creates_conflict"),
    (re.compile(r"\b(?:is\s+)?not\s+in\s+conflict\b", re.I), "not_in_conflict"),
    (re.compile(r"\b(?:is\s+)?in\s+conflict\b", re.I), "in_conflict"),
    (re.compile(r"\bno\s+conflict\b", re.I), "no_conflict"),
    (re.compile(r"\bambiguous\b", re.I), "ambiguous"),
]
CCB_EXCEPTION_RE = re.compile(r"\bexception(?:s)?\b", re.I)
CCB_NOEXCEPTION_RE = re.compile(r"\b(?:no exceptions?|without exception|found.{0,20}in order)\b", re.I)
MINUTE_REVIEW_RE = re.compile(
    r"\bMinutes of the Standing Judicial Commission\b|\breview(?:ed)? .{0,30}minutes\b", re.I)


def ccb_verdicts(text: str) -> list[str]:
    out = []
    for rx, v in CCB_VERDICT_PATTERNS:
        if rx.search(text):
            out.append(v)
    return _dedup(out)


# ===========================================================================
# SECTION BUILDERS
# ===========================================================================
def page_range_str(p0, p1):
    return f"{p0}" if p0 == p1 else f"{p0}-{p1}"


# Unified judicial-body facet: every judicial chunk (pre-SJC CJB or modern SJC)
# carries judicial_body so a single query spans the full 1973-2025 history.
SJC_SECTION_TYPES = frozenset({"sjc_decision", "sjc_dissent", "sjc_concurrence"})
CJB_SECTION_TYPES = frozenset({"cjb_report", "cjb_decision"})


def judicial_body_for(section_type):
    if section_type in SJC_SECTION_TYPES:
        return "SJC"
    if section_type in CJB_SECTION_TYPES:
        return "CJB"
    return None


def make_chunk(vol_meta, section_type, title, pages_slice, **extra):
    """Build a chunk dict from a slice of page rows. Collects citations across
    the joined text, item ids, page range, printed range, confidence."""
    text = "\n".join(p["text"] for p in pages_slice)
    de = deemph(text)
    cites = extract_citations(de)
    pdf0 = pages_slice[0]["pdf_page"]
    pdf1 = pages_slice[-1]["pdf_page"]
    printed = [p.get("printed_page") for p in pages_slice if p.get("printed_page") is not None]
    item_ids = all_item_ids(de, vol_meta["ga_ordinal"])
    chunk = {
        "chunk_id": f"{vol_meta['vol']}-{section_type}-{pdf0}",
        "parent_doc": vol_meta["vol"],
        "source_pdf": vol_meta.get("source_pdf"),
        "ga_ordinal": vol_meta["ga_ordinal"],
        "year": vol_meta["year"],
        "era": vol_meta["era"],
        "section_type": section_type,
        "judicial_body": judicial_body_for(section_type),
        "title": title[:300] if title else None,
        "appendix": extra.pop("appendix", None),
        "pdf_page_start": pdf0,
        "pdf_page_end": pdf1,
        "printed_page_start": printed[0] if printed else None,
        "printed_page_end": printed[-1] if printed else None,
        "page_range": page_range_str(pdf0, pdf1),
        "ga_item_ids": item_ids,
        "bco_citations": cites["bco_citations"],
        "bco_chapters": cites["bco_chapters"],
        "rao_citations": cites["rao_citations"],
        "wcf_citations": cites["wcf_citations"],
        "scripture_refs": cites["scripture_refs"],
        "overtures": cites["overtures"],
        "cross_refs": extra.pop("cross_refs", []),
        "sjc": extra.pop("sjc", None),
        "ccb": extra.pop("ccb", None),
        "char_count": sum(p["char_count"] for p in pages_slice),
        "qc_verdicts": _dedup([p["qc"]["verdict"] for p in pages_slice]),
        "confidence": extra.pop("confidence", 0.7),
    }
    chunk.update(extra)
    return chunk


# Cross-reference resolver: "see Appendix T, p. 685" -> appendix section
CROSSREF_RE = re.compile(
    r"(?:see\s+)?Appendix\s+([A-Z])\b(?:[,\s]+p+\.\s*(\d{1,4}))?", re.I)
CROSSREF_ITEM_RE = re.compile(r"see\s+(\d{1,2}-\d{1,3})(?:[,\s]+p+\.\s*(\d{1,4}))?", re.I)


def resolve_cross_refs(text: str, appendix_lookup: dict, ordinal: int) -> list[dict]:
    refs = []
    for m in CROSSREF_RE.finditer(text):
        letter = m.group(1).upper()
        ref = {"kind": "appendix", "letter": letter, "page": m.group(2)}
        if letter in appendix_lookup:
            ref["resolved_title"] = appendix_lookup[letter]["title"]
            ref["resolved_start_page"] = appendix_lookup[letter]["start_page"]
        refs.append(ref)
    for m in CROSSREF_ITEM_RE.finditer(text):
        a = m.group(1)
        if int(a.split("-")[0]) == ordinal:
            refs.append({"kind": "journal_item", "item": a, "page": m.group(2)})
    return _dedup_dicts(refs)


def _dedup_dicts(seq):
    out, seen = [], set()
    for d in seq:
        key = json.dumps(d, sort_keys=True)
        if key not in seen:
            seen.add(key); out.append(d)
    return out


# ===========================================================================
# SJC region detection + case segmentation
# ===========================================================================
# STRONG report-start headers: the actual "REPORT OF THE <committee>" title,
# possibly appendix-prefixed. This is what anchors a region's START.
SJC_REPORT_HEAD_RE = re.compile(
    r"REPORT OF THE\s+STANDING JUDICIAL COMMISSION|"
    r"APPENDIX\s+[A-Z]\b[^\n]{0,40}\bSTANDING JUDICIAL COMMISSION\b", re.I)
CCB_REPORT_HEAD_RE = re.compile(
    r"REPORT OF THE\s+COMMITTEE ON CONSTITUTIONAL BUSINESS|"
    r"APPENDIX\s+[A-Z]\b[^\n]{0,40}\bCONSTITUTIONAL BUSINESS\b", re.I)


TOC_LEADER_RE = re.compile(r"\.{4,}\s*\d{1,4}\s*$")  # dotted-leader TOC line


def _is_toc_match(page_text, head_re):
    """True if head_re matches ONLY inside dotted-leader TOC lines (front matter)
    rather than a genuine report header. Guards against latching the TOC entry
    'APPENDIX T Standing Judicial Commission .... 685'. A match that spans
    multiple lines (e.g. 'REPORT OF THE\\nSTANDING JUDICIAL COMMISSION') is a
    genuine header, never a TOC leader line."""
    single_line_matches = 0
    for line in page_text.split("\n"):
        if head_re.search(line):
            single_line_matches += 1
            if not TOC_LEADER_RE.search(line.rstrip()):
                return False  # a non-TOC single-line match -> genuine header
    if single_line_matches == 0:
        return False          # match only spans lines -> genuine multi-line header
    return True               # every single-line match was a TOC leader line


def _header_score(page_text, head_re):
    """Score a page as a report-START header. Higher = stronger.
    -1  => not a genuine header (only TOC leader lines, or no match)
     1  => the report title appears somewhere on the page (weak)
     2  => the canonical 'REPORT OF THE ...' title appears AND is followed by an
           'I. Introduction'-style report opening (the real report body start)
     3  => 'REPORT OF THE ...' heading in the top lines of the page
     5  => appendix-prefixed 'APPENDIX X ... REPORT OF THE ...' top-of-page header
    """
    lines = page_text.split("\n")
    nonblank = [ln for ln in lines if ln.strip()]
    if not head_re.search(page_text) or _is_toc_match(page_text, head_re):
        return -1
    head = "\n".join(nonblank[:5])
    # 5: canonical appendix report header — APPENDIX <L> ... REPORT OF THE <body>.
    #    Born-digital may split this across 2-3 markdown header lines, so test the
    #    joined top-of-page block as well as individual lines.
    head_joined = re.sub(r"\s+", " ", " ".join(nonblank[:5]))
    if re.match(r"\s*(?:#{0,6}\s*)?(?:\*{0,3}\s*)?APPENDIX\s+[A-Z]\b", head_joined, re.I) \
       and re.search(r"\bREPORT OF THE\b", head_joined, re.I) and head_re.search(head_joined):
        return 5
    for ln in nonblank[:5]:
        if re.match(r"\s*(?:#{0,6}\s*)?(?:\*{0,3}\s*)?APPENDIX\s+[A-Z]\b", ln, re.I) \
           and re.search(r"\bREPORT OF THE\b", ln, re.I) and head_re.search(ln):
            return 5
    # A SUPPLEMENTAL/AMENDED report header attaches to the main report; it must
    # never START a region ahead of the main report (which may score lower
    # because its title sits below a session/item header). Demote it.
    is_supplemental = bool(re.search(r"\b(?:SUPPLEMENTAL|AMENDED|ADDENDUM)\b",
                                     head_joined, re.I))
    # 3: 'REPORT OF THE <body>' is itself the heading near the top (possibly split).
    if re.search(r"\bREPORT OF THE\b", head_joined, re.I) and head_re.search(head_joined) \
       and not re.match(r"\s*(?:#{0,6}\s*)?\d{1,2}-\d{1,3}\b", nonblank[0]):
        return 1 if is_supplemental else 3
    # 2: canonical title anywhere + a report OPENING on the page (inline body
    #    start): 'I. Introduction', a 'Judicial Cases' docket, or 'Report of the
    #    Cases'. This catches early-digital inline reports whose title sits below
    #    a session/journal-item header (e.g. '32-31 Report of the SJC ...').
    if re.search(r"\bREPORT OF THE\b", page_text, re.I) and head_re.search(page_text) \
       and re.search(r"\bI\.\s*Introduction\b|\bJUDICIAL CASES\b|\bReport of the Cases\b|"
                     r"\bII\.\s*Judicial Cases\b", page_text, re.I) \
       and not is_supplemental:
        return 2
    return 1


def find_region(pages, head_re, max_pages=260, skip_front=6):
    """Return (start_idx, end_idx) page-row indices bounding a report region.
    Picks the STRONGEST report-start header (an appendix-prefixed 'REPORT OF THE'
    header beats an in-journal incidental mention), not merely the first match;
    excludes front-matter TOC dotted-leader lines. Region runs to the next
    appendix header (modern) or until the report content fades (inline eras)."""
    best = None  # (score, idx)
    for i, p in enumerate(pages):
        if i < skip_front:
            continue
        dt = deemph(p["text"])
        sc = _header_score(dt, head_re)
        if sc < 0:
            continue
        if best is None or sc > best[0]:
            best = (sc, i)
    if best is None:
        return None
    start = best[1]
    start_text = deemph(pages[start]["text"])
    m = re.search(r"APPENDIX\s+([A-Z])\b", "\n".join(start_text.split("\n")[:4]), re.I)
    start_letter = m.group(1).upper() if m else None
    end = start + 1
    # Stop at a DIFFERENT appendix letter header (so an SJC report's own
    # 'APPENDIX T' continuation running-head doesn't truncate it), or at any
    # appendix header when the region is inline (no start letter), or when the
    # inline report content clearly fades for several consecutive pages.
    diff_app = re.compile(r"^\s*#{0,6}\s*\*{0,3}APPENDIX\s+([A-Z])\b", re.I)
    fade = 0
    while end < len(pages) and end - start < max_pages:
        t = deemph(pages[end]["text"])
        head = "\n".join(t.split("\n")[:3])
        ma = diff_app.search(head)
        if ma:
            this_letter = ma.group(1).upper()
            if start_letter is None or this_letter != start_letter:
                break
        if start_letter is None:
            # inline (early-digital): the report ends when content shifts away
            # from judicial/constitutional matter for a SUSTAINED run of pages.
            # STRONG continuation cues only (bare 'Presbytery'/'Overture' recur
            # throughout the Journal and would never let an inline region end).
            cont = (head_re.search(t) or CASE_NO_RE.search(t) or CASE_INLINE_RE.search(t)
                    or re.search(r"\b(Roll call vote|III\.\s*Judgment|Reasoning and Opinion|"
                                 r"Concur\b.{0,40}\bConcur|Dissent|ROC\b|Record of the Case|"
                                 r"creates? conflict|in conflict|no conflict|"
                                 r"Constitutional Inquir|Supplemental Report|"
                                 r"Standing Judicial Commission|Committee on Constitutional "
                                 r"Business|opinion of the CCB)\b", t, re.I))
            if not cont:
                fade += 1
                if fade >= 3:                     # 3 consecutive off-topic pages
                    end -= (fade - 1)
                    break
            else:
                fade = 0
        end += 1
    return (start, max(end, start + 1))


def segment_sjc(pages, region, vol_meta, appendix_lookup, appendix_letter):
    """Segment the SJC report region into per-case decision chunks + sub-chunks.
    Returns list of chunks."""
    s, e = region
    chunks = []
    # Build a flat list of (page_idx, case_no, caption_text) from CASE NO. headers.
    case_marks = []
    for i in range(s, e):
        t = deemph(pages[i]["text"])
        for m in CASE_NO_RE.finditer(t):
            case_marks.append((i, m.group(1), _caption_after(t, m.end())))
        # early-digital inline "Case 2001-06" as a decision header (bold line)
        if not CASE_NO_RE.search(t):
            for m in re.finditer(r"(?m)^\s*Case\s+((?:19|20)\d{2}-\d{1,3})\b", t):
                case_marks.append((i, m.group(1), _caption_after(t, m.end())))
    # Deduplicate consecutive identical case numbers that are docket-list entries
    # (the report's section II lists ALL cases; we only want decided ones in
    # section III). Heuristic: a case is a DECISION anchor if its page also has a
    # disposition or a Roman JUDGMENT header within +/- 2 pages.
    # A case mark is a DECISION anchor only if it is a section-III decision
    # header (CASE NO. caption or a standalone bold 'Case <cno>' header) AND its
    # block carries a Roman JUDGMENT/DECISION header. Section-II docket entries
    # ('2002-06 Appeal ... vs. ...' / narrated 'Case 2002-06 was found out of
    # order') mention dispositions but never carry their own JUDGMENT header, so
    # this filters them out (matches the golden 'decided units' set).
    JUDG_HDR = re.compile(r"\b(?:III\.\s*)?JUDGMENT\b|\bDECISION ON (?:THE )?(?:COMPLAINT|APPEAL|CASE)", re.I)
    # order case_marks by page then position; build windows between consecutive marks
    case_marks.sort(key=lambda x: x[0])
    decided = []
    seen = set()
    for k, (i, cno, cap) in enumerate(case_marks):
        if cno in seen:
            continue
        nxt = case_marks[k + 1][0] if k + 1 < len(case_marks) else e
        win_end = min(e, max(i + 1, min(nxt + 1, i + 8)))
        window = collapse_caps_spacing(deemph("\n".join(
            pages[j]["text"] for j in range(i, win_end))))
        if JUDG_HDR.search(window):
            decided.append((i, cno, cap))
            seen.add(cno)
    # Build a region-level header chunk (the SJC report intro / docket).
    head_chunk = make_chunk(
        vol_meta, "committee_report",
        f"Report of the Standing Judicial Commission (GA {vol_meta['ga_ordinal']})",
        pages[s:e], appendix=appendix_letter,
        cross_refs=resolve_cross_refs(deemph(pages[s]["text"]), appendix_lookup, vol_meta["ga_ordinal"]),
        confidence=0.9)
    chunks.append(head_chunk)
    # Per-decision chunks
    for k, (i, cno, cap) in enumerate(decided):
        j_end = decided[k + 1][0] if k + 1 < len(decided) else e
        j_end = max(j_end, i + 1)
        sl = pages[i:j_end]
        body = deemph("\n".join(p["text"] for p in sl))
        body_c = collapse_caps_spacing(body)
        disp = find_disposition(body_c)
        vote = find_vote(body)
        has_diss = bool(DISSENT_RE.search(body))
        has_concur = bool(CONCUR_OP_RE.search(body))
        cites = extract_citations(body_c)
        roman = [name for name, rx in ROMAN_HEADERS if rx.search(body_c)]
        sjc_meta = {
            "case_numbers": [cno],
            "disposition": disp,
            "vote": vote,
            "has_dissent": has_diss,
            "has_concurrence": has_concur,
            "precedent_cites": cites["precedent_cites"],
            "roman_sections": roman,
        }
        title = cap or f"Case {cno}"
        ch = make_chunk(vol_meta, "sjc_decision", f"Case {cno}: {title}", sl,
                        appendix=appendix_letter, sjc=sjc_meta,
                        confidence=0.85 if disp else 0.6)
        ch["sjc"]["case_numbers"] = [cno]
        chunks.append(ch)
        # sub-chunk: dissent
        if has_diss:
            chunks.append(make_chunk(
                vol_meta, "sjc_dissent", f"Dissent in Case {cno}", sl,
                appendix=appendix_letter, sjc={"case_numbers": [cno]}, confidence=0.6))
        if has_concur:
            chunks.append(make_chunk(
                vol_meta, "sjc_concurrence", f"Concurrence in Case {cno}", sl,
                appendix=appendix_letter, sjc={"case_numbers": [cno]}, confidence=0.6))
    return chunks


def _caption_after(text, pos):
    """Grab the party-vs-court caption following a CASE NO. marker."""
    tail = text[pos:pos + 240]
    tail = re.sub(r"\s+", " ", tail).strip(" .:-")
    # caption ends at the next 'CASE NO' or a Roman header or 'DECISION'
    m = re.search(r"(CASE\s*NO|DECISION|SUMMARY|STATEMENT|I\.\s)", tail, re.I)
    if m and m.start() > 5:
        tail = tail[:m.start()]
    return tail.strip(" .:-")[:200]


def segment_ccb(pages, region, vol_meta, appendix_lookup, appendix_letter):
    """Segment the CCB report region: the report itself + per-overture advice
    + minute-review exception chunks."""
    s, e = region
    chunks = []
    head_text = deemph(pages[s]["text"])
    head_chunk = make_chunk(
        vol_meta, "committee_report",
        f"Report of the Committee on Constitutional Business (GA {vol_meta['ga_ordinal']})",
        pages[s:e], appendix=appendix_letter,
        cross_refs=resolve_cross_refs(head_text, appendix_lookup, vol_meta["ga_ordinal"]),
        confidence=0.9)
    full = deemph("\n".join(p["text"] for p in pages[s:e]))
    head_chunk["ccb"] = {
        "verdicts": ccb_verdicts(full),
        "exceptions_found": bool(CCB_EXCEPTION_RE.search(full) and not
                                 (CCB_NOEXCEPTION_RE.search(full) and not
                                  re.search(r"\bexcept(?:ion)?\b(?!.{0,20}without)", full, re.I))),
    }
    chunks.append(head_chunk)
    # Per-overture advice chunks (one per page that carries an overture + verdict).
    for i in range(s, e):
        t = deemph(pages[i]["text"])
        ov = sorted({m.group(1) for m in OVERTURE_RE.finditer(t)}, key=int)
        verds = ccb_verdicts(t)
        if ov and verds and re.search(r"\b(?:opinion of the CCB|in the opinion)\b", t, re.I):
            ch = make_chunk(
                vol_meta, "ccb_overture_advice",
                f"CCB advice on Overture(s) {', '.join(ov)} (GA {vol_meta['ga_ordinal']})",
                pages[i:i + 1], appendix=appendix_letter,
                ccb={"verdicts": verds, "exceptions_found": False, "overtures": ov},
                confidence=0.75)
            chunks.append(ch)
        # minute-review exception chunk
        if MINUTE_REVIEW_RE.search(t):
            exc = bool(CCB_EXCEPTION_RE.search(t)) and not bool(CCB_NOEXCEPTION_RE.search(t))
            ch = make_chunk(
                vol_meta, "ccb_minute_review",
                f"CCB review of SJC minutes (GA {vol_meta['ga_ordinal']})",
                pages[i:i + 1], appendix=appendix_letter,
                ccb={"verdicts": [], "exceptions_found": exc}, confidence=0.7)
            chunks.append(ch)
    return chunks


# ===========================================================================
# PRE-SJC era-parameterized CJB matcher  (GAs 1-17, 1973-1989)
# ---------------------------------------------------------------------------
# Pre-SJC the General Assembly itself acted as the court via the Committee on
# Judicial Business (CJB) and per-Assembly Committees of Commissioners that the
# GA constituted as ad hoc Judicial Commissions. The body appears under many
# naming variants and the earliest volumes are OCR-shattered scans, so all
# matchers run over despaced + caps-collapsed text and tolerate loose spacing.
# Emits section_type "cjb_report" (the CJB committee report) and "cjb_decision"
# (an individual numbered case / complaint / appeal / reference unit). Both
# carry judicial_body="CJB" via make_chunk.
# ===========================================================================
# All CJB naming variants (golden labels): (Permanent )?(Sub-)?Committee (of
# Commissioners )?(on|of) Judicial Business, Judicial Business Committee, and the
# earliest 'Committee on Judicial Procedures'. Loose internal whitespace so OCR
# splits ('com mittee on judicial business') still match after caps-collapse.
CJB_BODY_RE = re.compile(
    r"(?:Permanent\s+)?(?:Sub[-\s]?)?Committee\s+(?:of\s+Commissioners\s+)?"
    r"(?:on|of)\s+Judicial\s+Business"
    r"|Judicial\s+Business\s+Committee"
    r"|Committee\s+on\s+Judicial\s+Procedures",
    re.I)
# A genuine CJB REPORT header (anchors a report region START): the report title,
# possibly appendix-prefixed and OCR-spaced. Matches 'REPORT OF THE (PERMANENT)
# (SUB-)COMMITTEE ... ON JUDICIAL BUSINESS' and 'APPENDIX X ... JUDICIAL BUSINESS'.
CJB_REPORT_HEAD_RE = re.compile(
    r"REPORT\s+OF\s+(?:THE\s+)?(?:PERMANENT\s+)?(?:SUB[-\s]?)?COMMITTEE\s+"
    r"(?:OF\s+COMMISSIONERS\s+)?(?:ON|OF)\s+JUDICIAL\s+BUSINESS"
    r"|APPENDIX\s+[A-Z]\b[^\n]{0,40}\bJUDICIAL\s+BUSINESS\b",
    re.I)
# Numbered-case captions (pre-SJC): 'Case 4', 'Case #4', 'Case No. 4',
# 'Complaint No. 2'. Numbers are small (1..~30), distinct from BCO NN-N cites.
CJB_CASE_N_RE = re.compile(r"\bCase\s*(?:No\.?|#)?\s*(\d{1,2})\b(?!\s*-)", re.I)
CJB_COMPLAINT_N_RE = re.compile(r"\bComplaint\s+No\.?\s*(\d{1,2})\b", re.I)
# party-vs-court caption ('X vs. Y Presbytery', 'Appeal of X vs. Y Presbytery',
# and the floor-report 'Complaint of X ... against Y Presbytery' form).
CJB_VS_RE = re.compile(
    r"\b([A-Z][A-Za-z.\-'’\s]{1,55}?)\s+(?:vs?\.?|against)\s+"
    r"(?:the\s+)?([A-Z][A-Za-z.\-'’\s]{1,55}?(?:Presbytery|Church\s+in\s+America|Assembly))",
    re.I)
# Inline numbered-case caption used in floor reports & adjudication recaps:
# 'Case 1: Complaint of X against Y Presbytery', 'Case #4 - Appeal of ...',
# 'Case 5: Item 13-61 — Preg et al. vs. Missouri Presbytery'. Captures the case
# number; the rest of the line is the caption. Tolerant of OCR spacing.
CJB_CASE_CAPTION_RE = re.compile(
    r"(?m)^\s*Case\s*(?:No\.?|#)?\s*(\d{1,2})\s*[:.\-—]\s*(.{0,160}?)\s*$", re.I)
# complaint/appeal/reference 'of/from/by' opener (filing units).
CJB_FILING_RE = re.compile(
    r"\b(Complaint|Appeal|Judicial\s+Reference|Reference)\b"
    r"[^\n]{0,18}?\b(?:of|from|by|No\.?)\b", re.I)
# Judicial-Commission disposition report header (the adjudication unit).
CJB_COMMISSION_RE = re.compile(
    r"\b(?:Report\s+of\s+the\s+)?Judicial\s+Commission\b"
    r"|\bCommittee\s+of\s+Commissioners\s+on\s+Judicial\s+Business\b"
    r"|\bInvestigative\s+Commission\b", re.I)
# pre-SJC dispositions (golden phrasing): sustained / not sustained / denied /
# granted / referred / abandoned / in/out of order / sustained specification N.
CJB_DISPOSITION_PATTERNS = [
    (r"sustain(?:ed)?\s+specification|specification\s+\d+\s+sustained", "sustained_specification"),
    (r"\bnot\s+(?:be\s+)?sustain(?:ed)?\b", "not_sustained"),
    (r"\b(?:complaint|appeal|reference)\b[^\n]{0,40}?\bsustain(?:ed)?\b", "sustained"),
    (r"\b(?:be\s+|was\s+|is\s+|were\s+|are\s+)sustain(?:ed)?\b", "sustained"),
    (r"\bsustain(?:ed)?\b", "sustained"),
    (r"\bdenied\b", "denied"),
    (r"\bgranted\b", "granted"),
    (r"\b(?:deemed\s+)?abandon(?:ed)?\b|\bwithdrawn\b", "abandoned"),
    (r"\bnot\s+in\s+order\b|\bout\s+of\s+order\b|\bnot\s+(?:be\s+)?received\b", "out_of_order"),
    (r"\bfound\s+in\s+order\b|\bin\s+order\b", "in_order"),
    (r"\breferred\b|\brefer\s+the\b|\bcommitted\s+to\b", "referred"),
    (r"\brescind(?:ed)?\b|\bdisestablish(?:ed)?\b", "rescinded"),
]
CJB_DISPOSITION_COMPILED = [(re.compile(p, re.I), v) for p, v in CJB_DISPOSITION_PATTERNS]


def _cjb_text(page):
    """Pre-SJC pages are OCR-shattered scans; normalize aggressively: despace
    intra-word splits, then collapse spaced-out ALL-CAPS Roman headers."""
    try:
        ds = normalize.despace(page["text"], _CJB_WORDS)
    except Exception:
        ds = page["text"]
    return collapse_caps_spacing(deemph(ds))


try:
    _CJB_WORDS = normalize.load_dict()
except Exception:
    _CJB_WORDS = None


def find_cjb_disposition(text):
    for rx, verdict in CJB_DISPOSITION_COMPILED:
        if rx.search(text):
            return verdict
    return None


def cjb_chunks(pages, vol_meta, claimed, emit_decisions=True):
    """Era-parameterized pre-SJC CJB matcher.

    Always emits the CJB committee report region(s) as section_type 'cjb_report'.
    When emit_decisions (GAs 1-13, the pure pre-SJC era), also segments the
    individual numbered judicial units as 'cjb_decision' (numbered cases,
    complaints/appeals/references, and Judicial-Commission disposition reports).
    In the GA 14-17 CJB/SJC overlap emit_decisions is False: the SJC paths own
    the per-case decisions there, so CJB contributes only the report (additive,
    no regression to SJC counts).

    Returns chunks. Claims report-region pages so the journal/appendix passes
    don't double-emit them; never claims case pages it does not itself emit.
    """
    chunks = []
    ordinal = vol_meta["ga_ordinal"]
    cjb_text = {p["pdf_page"]: _cjb_text(p) for p in pages}

    # ---- CJB report(s). A volume typically has TWO CJB bodies reporting:
    #   * the standing/permanent committee report, printed as an APPENDIX — a
    #     multi-page region bounded by the next appendix header / a content fade;
    #   * the floor 'Committee of Commissioners on Judicial Business' report(s),
    #     which are JOURNAL ITEMS ('N-NNN Report of the Committee ... on Judicial
    #     Business') — each a single journal-item-sized chunk (header -> next
    #     item), NOT a 40-page sweep (the floor report is interleaved with other
    #     Assembly business, so sweeping would wrongly claim the whole Journal).
    diff_app = re.compile(r"^\s*#{0,6}\s*\*{0,3}APPENDIX\s+([A-Z])\b", re.I)
    report_claimed = set()

    def emit_report(s, e, letter):
        e = max(e, s + 1)
        sl = pages[s:e]
        ch = make_chunk(
            vol_meta, "cjb_report",
            f"Report of the Committee on Judicial Business (GA {ordinal})",
            sl, appendix=letter, confidence=0.7)
        ch["committee"] = "judicial_business"
        chunks.append(ch)
        for j in range(s, e):
            report_claimed.add(pages[j]["pdf_page"])

    # (1) appendix-style standing-committee report regions
    for i, p in enumerate(pages):
        if p["pdf_page"] in claimed or p["pdf_page"] in report_claimed:
            continue
        t = cjb_text[p["pdf_page"]]
        head = "\n".join(t.split("\n")[:6])
        if not CJB_REPORT_HEAD_RE.search(head):
            continue
        ma0 = diff_app.search("\n".join(t.split("\n")[:3]))
        start_letter = ma0.group(1).upper() if ma0 else None
        m = re.search(r"APPENDIX\s+([A-Z])\b", "\n".join(t.split("\n")[:4]), re.I)
        letter = m.group(1).upper() if m else None
        e = i + 1
        fade = 0
        while e < len(pages) and e - i < 40:
            if pages[e]["pdf_page"] in claimed or pages[e]["pdf_page"] in report_claimed:
                break
            te = cjb_text[pages[e]["pdf_page"]]
            head3 = "\n".join(te.split("\n")[:3])
            ma = diff_app.search(head3)
            if ma and (start_letter is None or ma.group(1).upper() != start_letter):
                break
            # tighter fade: require an actual CJB / judicial-business cue (a bare
            # 'presbytery' recurs throughout and must not extend the region).
            cont = CJB_BODY_RE.search(te) or re.search(
                r"\bjudicial\b|\bcomplaint\b|\brecommendation\b|\bcommission\b|"
                r"\bconstitutional\b|\boverture\b", te, re.I)
            if not cont:
                fade += 1
                if fade >= 2:
                    e -= (fade - 1)
                    break
            else:
                fade = 0
            e += 1
        emit_report(i, max(e, i + 1), letter)

    # (2) floor Committee-of-Commissioners report journal items (single-item)
    floor_marks = []
    for pi, p in enumerate(pages):
        pp = p["pdf_page"]
        if pp in claimed or pp in report_claimed:
            continue
        t = cjb_text[pp]
        for off, item, hdr in journal_item_spans(t, ordinal):
            tail = re.sub(r"\s+", " ", hdr)[len(item):]
            if re.search(r"report\s+of\s+the\b", tail, re.I) and CJB_BODY_RE.search(tail):
                floor_marks.append((pi, item))
                break
    # bound each floor report from its page to the next journal-item header page
    all_item_pages = sorted({pi for pi, p in enumerate(pages)
                             for _ in journal_item_spans(cjb_text[p["pdf_page"]], ordinal)})
    for pi, item in floor_marks:
        if pages[pi]["pdf_page"] in report_claimed or pages[pi]["pdf_page"] in claimed:
            continue
        nxts = [q for q in all_item_pages if q > pi]
        end_pi = min(len(pages), min(nxts) if nxts else pi + 1, pi + 4)
        end_pi = max(end_pi, pi + 1)
        while end_pi > pi + 1 and (pages[end_pi - 1]["pdf_page"] in claimed
                                   or pages[end_pi - 1]["pdf_page"] in report_claimed):
            end_pi -= 1
        emit_report(pi, end_pi, None)

    if not emit_decisions:
        for pp in report_claimed:
            claimed.add(pp)
        return chunks

    # ---- per-case CJB decisions. Three complementary passes, all over despaced
    # + caps-collapsed OCR text (early volumes are shattered scans):
    #   (A) judicial JOURNAL-ITEM headers ('N-NNN Complaint No. 2 ...', 'N-NNN
    #       Judicial Commission to Adjudicate ...') — the canonical pre-SJC unit;
    #   (B) inline numbered-case captions ('Case 1: Complaint of X against Y
    #       Presbytery') used in the F.-Judicial-Cases filing section & recaps;
    #   (C) judicial case-LIST pages (>=2 party-vs-court captions under a
    #       'Judicial Cases'/'Recommendations' header) used by the floor report.
    # A unit is required to carry a real judicial signal (case number / party-vs-
    # court / commission), never a bare 'Presbytery', to avoid over-segmentation.
    JUD_HEAD_RE = re.compile(
        r"Complaint\s+No\.?\s*\d"
        r"|\bCase\s*(?:No\.?|#)?\s*\d"
        r"|Judicial\s+Commission\b"
        r"|Investigative\s+Commission\b"
        r"|\b(?:Appeal|Judicial\s+Reference|Reference)\s+(?:No\.?\s*\d+\s+)?(?:of|from|by)\b"
        r"|\b(?:Complaint)\s+(?:No\.?\s*\d+\s+)?(?:of|from|by)\b",
        re.I)

    # ----- pass (A): judicial journal-item headers -----
    jmarks = []  # (page_idx, item_id, header_line, vs_match)
    for pi, p in enumerate(pages):
        pp = p["pdf_page"]
        if pp in claimed or pp in report_claimed:
            continue
        t = cjb_text[pp]
        for off, item, header in journal_item_spans(t, ordinal):
            hl = re.sub(r"\s+", " ", header)
            tail = hl[len(item):][:120]   # text AFTER the 'N-NNN' id
            if JUD_HEAD_RE.search(tail):
                jmarks.append((pi, item, hl, CJB_VS_RE.search(t)))
    jmarks.sort(key=lambda x: x[0])
    for k, (pi, item, header, vs_m) in enumerate(jmarks):
        pp = pages[pi]["pdf_page"]
        if pp in claimed:
            continue
        nxt = jmarks[k + 1][0] if k + 1 < len(jmarks) else pi + 1
        end_pi = min(len(pages), max(pi + 1, min(nxt, pi + 3)))
        while end_pi > pi + 1 and (pages[end_pi - 1]["pdf_page"] in claimed
                                   or pages[end_pi - 1]["pdf_page"] in report_claimed):
            end_pi -= 1
        sl = pages[pi:end_pi]
        body = "\n".join(_cjb_text(p) for p in sl)
        comp_ns = sorted({mm.group(1) for mm in CJB_COMPLAINT_N_RE.finditer(header)}, key=int)
        case_ns = sorted({mm.group(1) for mm in CJB_CASE_N_RE.finditer(header)}, key=int)
        disp = find_cjb_disposition(body)
        cap = re.sub(r"\s+", " ", f"{vs_m.group(1).strip()} v. {vs_m.group(2).strip()}")[:120] \
            if vs_m else None
        commission = bool(CJB_COMMISSION_RE.search(header))
        title = re.sub(r"\s+", " ", header)[:160] or f"Pre-SJC judicial case (GA {ordinal}, p.{pp})"
        cites = extract_citations(body)
        cjb_meta = {
            "case_numbers": (["Complaint No. " + n for n in comp_ns] if comp_ns
                             else ["Case " + n for n in case_ns] if case_ns else []),
            "disposition": disp, "parties": cap, "is_commission_report": commission,
            "vote": find_vote(body), "bco_citations": cites["bco_citations"],
        }
        ch = make_chunk(vol_meta, "cjb_decision", title, sl,
                        cjb_case=cjb_meta, confidence=0.6 if disp else 0.45)
        if item and item not in ch["ga_item_ids"]:
            ch["ga_item_ids"] = [item] + ch["ga_item_ids"]
        chunks.append(ch)
        for j in range(pi, end_pi):
            claimed.add(pages[j]["pdf_page"])

    # ----- pass (B): inline 'Case N: ...' captions naming a court -----
    for pi, p in enumerate(pages):
        pp = p["pdf_page"]
        if pp in claimed:
            continue
        t = cjb_text[pp]
        cap_hits = []
        for mm in CJB_CASE_CAPTION_RE.finditer(t):
            line = mm.group(2)
            if re.search(r"Presbytery|Church\s+in\s+America|Complaint|Appeal|Reference",
                         line, re.I):
                cap_hits.append((mm.group(1), line))
        if not cap_hits:
            continue
        case_ns = sorted({n for n, _ in cap_hits}, key=int)
        vs_m = CJB_VS_RE.search(t)
        cap = re.sub(r"\s+", " ", cap_hits[0][1])[:120]
        disp = find_cjb_disposition(t)
        cites = extract_citations(t)
        title = ("Case " + "/".join(case_ns) + ": " + cap)[:160]
        cjb_meta = {
            "case_numbers": ["Case " + n for n in case_ns],
            "disposition": disp, "parties": cap if vs_m else None,
            "is_commission_report": bool(CJB_COMMISSION_RE.search(t)),
            "vote": find_vote(t), "bco_citations": cites["bco_citations"],
        }
        ch = make_chunk(vol_meta, "cjb_decision", title, pages[pi:pi + 1],
                        cjb_case=cjb_meta, confidence=0.55 if disp else 0.4)
        chunks.append(ch)
        claimed.add(pp)

    # ----- pass (C): judicial case-LIST pages (>=2 distinct party-vs-court
    # captions under a Judicial-Cases / Recommendations header) -----
    for pi, p in enumerate(pages):
        pp = p["pdf_page"]
        if pp in claimed:
            continue
        t = cjb_text[pp]
        vs_caps = [(mm.group(1).strip(), mm.group(2).strip())
                   for mm in CJB_VS_RE.finditer(t)]
        courts = {re.sub(r"\s+", " ", b).lower() for _, b in vs_caps}
        if len(vs_caps) >= 2 and len(courts) >= 2 and \
           re.search(r"Judicial\s+Cas|Recommendation|Complaint|Appeal|Reference|"
                     r"Commission|in\s+order", t, re.I):
            disp = find_cjb_disposition(t)
            cites = extract_citations(t)
            cap = re.sub(r"\s+", " ", "; ".join(f"{a} v. {b}" for a, b in vs_caps[:4]))[:150]
            ch = make_chunk(
                vol_meta, "cjb_decision",
                f"Pre-SJC judicial cases (GA {ordinal}): {cap}", pages[pi:pi + 1],
                cjb_case={"case_numbers": [], "disposition": disp, "parties": cap,
                          "is_commission_report": bool(CJB_COMMISSION_RE.search(t)),
                          "vote": find_vote(t), "bco_citations": cites["bco_citations"]},
                confidence=0.5 if disp else 0.4)
            chunks.append(ch)
            claimed.add(pp)

    for pp in report_claimed:
        claimed.add(pp)
    return chunks


# ===========================================================================
# pre-SJC judicial / constitutional committee detection (graceful fallback)
# ===========================================================================
PRE_SJC_JUDICIAL_RE = re.compile(
    r"Committee on Judicial Business|Judicial Business Committee|"
    r"REPORT OF THE COMMITTEE\s+ON JUDIC", re.I)
PRE_SJC_CONST_RE = re.compile(
    r"Constitutional Documents Committee|Committee on (?:the )?Constitution\b", re.I)
JUDICIAL_CASE_CAP_RE = re.compile(
    r"\b(Complaint|Appeal)\b[^\n]{0,80}?\bv[s]?\.\s+[A-Z][^\n]{0,60}?Presbytery", re.I)


# ===========================================================================
# APPENDIX chunking (generic, non-SJC/CCB appendices)
# ===========================================================================
# Body appendix header: 'APPENDIX <L>' at the START OF A LINE (re.M), so a
# running-head prefix on the same page ('258 minutes of the general assembly\n
# APPENDIX A', 'APPENDICES 263\nAPPENDIX B') still matches — the older un-anchored
# .search missed exactly these shattered-scan headers and emitted ZERO appendix
# chunks for whole volumes (GA14/15/16).
APP_BODY_HEAD_RE = re.compile(r"(?m)^\s*#{0,6}\s*\*{0,3}APPENDIX\s+([A-Z])\b", re.I)


def appendix_chunks(pages, appendix_table, vol_meta, claimed_pdf_pages):
    """Emit appendix section chunks, bracketed from THIS volume's own appendix
    table (letter -> title -> printed start_page).

    Robustness over the old header-only scan: the extracted appendix_table is the
    authoritative ordering and source of letter+title. Each appendix is bracketed
    [start_page, next_appendix_start_page - 1] (the last appendix runs to the end
    of the volume). The pdf start of each appendix is resolved by, in order:
      (1) a body 'APPENDIX <L>' header detected on a page (now line-anchored so a
          running head before it doesn't hide it), else
      (2) mapping the table's printed start_page through a per-volume printed->pdf
          offset derived from the headers we DID detect (median), so appendices
          whose body header is OCR-mangled or missing are still bracketed.
    Pages already claimed by a more specific chunk (sjc/ccb/cjb/journal_item) are
    excluded: the appendix chunk(s) cover only the contiguous UNCLAIMED runs in
    each bracket, so we never double-claim and never drop the specific chunks.
    Falls back to the legacy header-only behavior when the volume has no extracted
    appendix table (so volumes that already worked are unaffected)."""
    chunks = []
    tl = {a["letter"]: a["title"] for a in appendix_table}

    # ---- detect body 'APPENDIX <L>' headers (first detected page wins/letter) ----
    pp_by_idx = [p["pdf_page"] for p in pages]
    header_idx = {}  # letter -> page index of its body header
    for i, p in enumerate(pages):
        head = "\n".join(deemph(p["text"]).split("\n")[:4])
        m = APP_BODY_HEAD_RE.search(head)
        if m:
            header_idx.setdefault(m.group(1).upper(), i)

    if not appendix_table:
        # No extracted table: legacy header-only behavior (bracket header->header).
        ordered = sorted(header_idx.items(), key=lambda kv: kv[1])
        for k, (letter, i) in enumerate(ordered):
            j_end = ordered[k + 1][1] if k + 1 < len(ordered) else len(pages)
            if pages[i]["pdf_page"] in claimed_pdf_pages:
                continue
            ch = make_chunk(vol_meta, "appendix",
                            f"Appendix {letter}: {tl.get(letter, letter)}",
                            pages[i:j_end], appendix=letter, confidence=0.8)
            chunks.append(ch)
        return chunks

    # ---- derive per-volume printed_start -> pdf offset from detected headers ----
    offsets = []
    for a in appendix_table:
        L = a["letter"]
        if L in header_idx and isinstance(a.get("start_page"), int):
            offsets.append(pp_by_idx[header_idx[L]] - a["start_page"])
    offsets.sort()
    pdf_offset = offsets[len(offsets) // 2] if offsets else 0  # median

    def idx_for_pdf(target_pdf):
        """First page index whose pdf_page >= target_pdf (clamped)."""
        for i, pp in enumerate(pp_by_idx):
            if pp >= target_pdf:
                return i
        return len(pages) - 1

    # ---- resolve each appendix's start page index, in table order ----
    resolved = []  # (start_idx, letter, title)
    for a in appendix_table:
        L = a["letter"]
        if L in header_idx:
            si = header_idx[L]
        elif isinstance(a.get("start_page"), int):
            si = idx_for_pdf(a["start_page"] + pdf_offset)
        else:
            continue
        resolved.append((si, L, tl.get(L, L)))
    # keep table order but ensure start indices are monotonic non-decreasing
    resolved.sort(key=lambda r: (r[0],))
    if not resolved:
        return chunks

    # ---- bracket [start, next_start) and emit over unclaimed contiguous runs ----
    for k, (si, letter, title) in enumerate(resolved):
        end_idx = resolved[k + 1][0] if k + 1 < len(resolved) else len(pages)
        end_idx = max(end_idx, si + 1)
        # collect contiguous runs of pages in [si, end_idx) not already claimed
        run = []
        for i in range(si, end_idx):
            if pages[i]["pdf_page"] in claimed_pdf_pages:
                if run:
                    _emit_appendix_run(chunks, pages, run, letter, title, vol_meta)
                    run = []
            else:
                run.append(i)
        if run:
            _emit_appendix_run(chunks, pages, run, letter, title, vol_meta)
    return chunks


def _emit_appendix_run(chunks, pages, run, letter, title, vol_meta):
    """Emit one appendix chunk over a contiguous run of page indices."""
    sl = [pages[i] for i in run]
    ch = make_chunk(vol_meta, "appendix", f"Appendix {letter}: {title}",
                    sl, appendix=letter, confidence=0.8)
    chunks.append(ch)


# ===========================================================================
# JOURNAL chunking — one chunk per journal item (born-digital/early-digital)
# or per page-group with item headers (scanned).
# ===========================================================================
def journal_chunks(pages, vol_meta, claimed_pdf_pages):
    """Emit one chunk per journal item, spanning from its header to the next
    item header (possibly across pages). Pages without any item header in
    eras lacking item-ids are emitted as journal_item chunks per page."""
    chunks = []
    ordinal = vol_meta["ga_ordinal"]
    # collect (global_char_pos as (page_idx, char_off), item_id)
    flat = []  # (page_idx, start_off, item_id, header)
    for pi, p in enumerate(pages):
        if p["pdf_page"] in claimed_pdf_pages:
            continue
        t = deemph(p["text"])
        for (off, item, header) in journal_item_spans(t, ordinal):
            flat.append((pi, off, item, header))
    if not flat:
        return chunks
    # Build item chunks: each runs from its position to the next item's position.
    for k, (pi, off, item, header) in enumerate(flat):
        if k + 1 < len(flat):
            npi = flat[k + 1][0]
            end_pi = npi if npi > pi else pi + 1
        else:
            end_pi = pi + 1
        end_pi = min(end_pi, len(pages))
        if end_pi <= pi:
            end_pi = pi + 1
        sl = pages[pi:end_pi]
        title = re.sub(r"\s+", " ", header)[:160]
        ch = make_chunk(vol_meta, "journal_item", title, sl, confidence=0.8)
        # narrow ga_item_ids to the leading item plus any cited
        if item not in ch["ga_item_ids"]:
            ch["ga_item_ids"] = [item] + ch["ga_item_ids"]
        ch["primary_item"] = item
        ch["anchor"] = f"item-{item}"
        chunks.append(ch)
    return chunks


# ===========================================================================
# Per-volume driver
# ===========================================================================
def load_pages(vol):
    path = os.path.join(PAGE_JSONL_DIR, f"{vol}.pages.jsonl")
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["pdf_page"])
    return rows


def process_volume(vol, source_manifest):
    pages = load_pages(vol)
    ga_ordinal = pages[0]["ga_ordinal"]
    year = pages[0]["year"]
    full_text = "\n".join(deemph(p["text"]) for p in pages)
    era = detect_era(ga_ordinal, year, full_text)
    has_sjc = has_report(full_text, r"\bStanding Judicial Commission\b") and \
        bool(SJC_REPORT_HEAD_RE.search(full_text))
    has_ccb = bool(CCB_REPORT_HEAD_RE.search(full_text))

    appendix_table = extract_appendix_table(pages)
    appendix_lookup = {a["letter"]: a for a in appendix_table}
    # persist appendix table
    os.makedirs(APPENDIX_DIR, exist_ok=True)
    with open(os.path.join(APPENDIX_DIR, f"{vol}.appendix.json"), "w") as fh:
        json.dump({"vol": vol, "ga_ordinal": ga_ordinal, "year": year,
                   "era": era, "appendix_table": appendix_table}, fh, indent=2)

    vol_meta = {
        "vol": vol, "ga_ordinal": ga_ordinal, "year": year, "era": era,
        "source_pdf": source_manifest.get(vol),
    }

    chunks = []
    claimed = set()  # pdf pages claimed by SJC/CCB so journal/appendix don't double-emit

    # ----- SJC region -----
    sjc_region = find_region(pages, SJC_REPORT_HEAD_RE) if has_sjc else None
    sjc_letter = None
    if sjc_region:
        # determine appendix letter if region begins on an appendix header
        head = "\n".join(deemph(pages[sjc_region[0]]["text"]).split("\n")[:3])
        m = re.search(r"APPENDIX\s+([A-Z])\b", head, re.I)
        sjc_letter = m.group(1).upper() if m else None
        sjc_chunks = segment_sjc(pages, sjc_region, vol_meta, appendix_lookup, sjc_letter)
        chunks.extend(sjc_chunks)
        for i in range(sjc_region[0], sjc_region[1]):
            claimed.add(pages[i]["pdf_page"])

    # ----- CCB region -----
    ccb_region = find_region(pages, CCB_REPORT_HEAD_RE) if has_ccb else None
    ccb_letter = None
    if ccb_region:
        head = "\n".join(deemph(pages[ccb_region[0]]["text"]).split("\n")[:3])
        m = re.search(r"APPENDIX\s+([A-Z])\b", head, re.I)
        ccb_letter = m.group(1).upper() if m else None
        ccb_chunks = segment_ccb(pages, ccb_region, vol_meta, appendix_lookup, ccb_letter)
        chunks.extend(ccb_chunks)
        for i in range(ccb_region[0], ccb_region[1]):
            claimed.add(pages[i]["pdf_page"])

    # ----- pre-SJC CJB judicial body (GAs 1-17, 1973-1989) -----
    # The General Assembly itself acted as the court via the Committee on
    # Judicial Business. Emit cjb_report + (pure pre-SJC era only) cjb_decision.
    # GAs 14-17 are a CJB/SJC overlap: the SJC paths own per-case decisions
    # there, so CJB contributes only the report (additive — SJC counts unchanged).
    cjb_active = ga_ordinal <= 17
    if cjb_active:
        chunks.extend(cjb_chunks(pages, vol_meta, claimed,
                                 emit_decisions=(ga_ordinal <= 13)))

    # ----- pre-SJC graceful constitutional handling + (overlap) SJC per-case
    #       adjudications. The CJB report is now owned by the cjb_report pass, so
    #       skip re-emitting it here; pages it claimed are skipped automatically.
    if not has_sjc and era in ("early-scanned-no-item-id", "mid-scanned"):
        chunks.extend(pre_sjc_chunks(pages, vol_meta, claimed,
                                     skip_judicial_report=cjb_active))

    # ----- inline judicial decisions (mid-scanned SJC era: cases live in the
    #       Journal as 'III. (The) Judgment' blocks, often with YY-N docket
    #       numbers, not in a structured SJC appendix). Run when the structured
    #       SJC segmentation yielded no per-case decisions. -----
    n_sjc_dec = sum(1 for c in chunks if c["section_type"] == "sjc_decision")
    if n_sjc_dec == 0 and era in ("mid-scanned", "early-digital", "modern-digital") and \
            re.search(r"Standing Judicial Commission", full_text, re.I):
        chunks.extend(inline_judicial_chunks(pages, vol_meta, claimed))

    # ----- generic appendices -----
    chunks.extend(appendix_chunks(pages, appendix_table, vol_meta, claimed))
    for ch in chunks:
        if ch["section_type"] == "appendix":
            for pp in range(ch["pdf_page_start"], ch["pdf_page_end"] + 1):
                claimed.add(pp)

    # ----- journal items -----
    chunks.extend(journal_chunks(pages, vol_meta, claimed))

    # ----- front matter (pages 1..first-journal not otherwise claimed) -----
    fm_end = min(6, len(pages))
    fm_pages = [p for p in pages[:fm_end] if p["pdf_page"] not in claimed]
    if fm_pages:
        chunks.append(make_chunk(vol_meta, "front_matter",
                                 f"Front matter (GA {ga_ordinal}, {year})",
                                 fm_pages, confidence=0.6))

    meta = {
        "vol": vol, "ga_ordinal": ga_ordinal, "year": year, "era": era,
        "has_sjc": has_sjc, "has_ccb": has_ccb,
        "n_appendices": len(appendix_table),
        "sjc_region": [pages[sjc_region[0]]["pdf_page"],
                       pages[min(sjc_region[1], len(pages)) - 1]["pdf_page"]] if sjc_region else None,
        "ccb_region": [pages[ccb_region[0]]["pdf_page"],
                       pages[min(ccb_region[1], len(pages)) - 1]["pdf_page"]] if ccb_region else None,
        "n_chunks": len(chunks),
    }
    return chunks, meta


INLINE_JUDG_RE = re.compile(r"\b(?:III\.\s*)?(?:The\s+)?JUDGMENT\b|"
                            r"\bDECISION ON (?:THE )?(?:COMPLAINT|APPEAL|CASE)\b", re.I)
# mid-scanned docket numbers: YY-N (e.g. 93-6, 75-7). Anchored to 'Case'/'Complaint'
# /'docket' context to avoid colliding with BCO NN-N or other numerics.
MIDCASE_RE = re.compile(
    r"\b(?:Judicial\s+)?(?:Case|Complaint|Appeal|docket(?:\s+number)?s?)\b[^\n]{0,30}?"
    r"\b([89]\d|[0-7]\d)-(\d{1,2})\b", re.I)


def inline_judicial_chunks(pages, vol_meta, claimed):
    """Detect inline SJC judicial decisions in the mid-scanned era: a page with a
    Roman JUDGMENT header in judicial/SJC context starts a decision block that
    runs to the next JUDGMENT header or a short fade. Extracts disposition, vote,
    dissent, parties, and any YY-N docket number."""
    chunks = []
    ordinal = vol_meta["ga_ordinal"]
    marks = []  # page indices that open a judicial decision block
    for i, p in enumerate(pages):
        if p["pdf_page"] in claimed:
            continue
        t = collapse_caps_spacing(deemph(p["text"]))
        head = "\n".join(t.split("\n")[:6])
        # digital eras: a 'CASE NO. <yyyy-n>' caption opens a decision block.
        if CASE_NO_RE.search(head):
            marks.append(i)
            continue
        if INLINE_JUDG_RE.search(head) and \
           re.search(r"Standing Judicial Commission|judicial commission|"
                     r"complaint|appeal|presbytery", t, re.I):
            marks.append(i)
    # merge consecutive marks into single blocks (a multi-page decision can carry
    # JUDGMENT then continuation pages)
    blocks = []
    for i in marks:
        if blocks and i - blocks[-1][-1] <= 1:
            blocks[-1].append(i)
        else:
            blocks.append([i])
    for blk in blocks:
        s = blk[0]
        # extend a couple pages forward to capture the roll-call/vote
        e = min(len(pages), blk[-1] + 2)
        # don't cross into a claimed page
        while e > s + 1 and pages[e - 1]["pdf_page"] in claimed:
            e -= 1
        sl = pages[s:e]
        body = collapse_caps_spacing(deemph("\n".join(pp["text"] for pp in sl)))
        disp = find_disposition(body)
        cno = None
        # Prefer a 4-digit-year CASE NO. caption (digital eras). Only fall back to
        # the mid-scanned YY-N docket pattern for the mid-scanned era, to avoid
        # mistaking a BCO 34-1 / RAO 15-3 citation for a case number.
        m4 = CASE_NO_RE.search(body) or CASE_INLINE_RE.search(body)
        if m4:
            cno = m4.group(1)
        elif vol_meta["era"] == "mid-scanned":
            m = MIDCASE_RE.search(body)
            if m:
                cno = f"{m.group(1)}-{m.group(2)}"
        # party-vs-court caption
        capm = JUDICIAL_CASE_CAP_RE.search(body)
        cap = re.sub(r"\s+", " ", capm.group(0))[:160] if capm else None
        sjc_meta = {
            "case_numbers": [cno] if cno else [],
            "disposition": disp,
            "vote": find_vote(body),
            "has_dissent": bool(DISSENT_RE.search(body)),
            "has_concurrence": bool(CONCUR_OP_RE.search(body)),
            "precedent_cites": extract_citations(body)["precedent_cites"],
            "roman_sections": [n for n, rx in ROMAN_HEADERS if rx.search(body)],
        }
        title = cap or (f"Judicial Case {cno}" if cno else
                        f"SJC judicial decision (GA {ordinal}, p.{pages[s]['pdf_page']})")
        ch = make_chunk(vol_meta, "sjc_decision", title, sl,
                        sjc=sjc_meta, confidence=0.6 if disp else 0.45)
        chunks.append(ch)
        for pp in range(ch["pdf_page_start"], ch["pdf_page_end"] + 1):
            claimed.add(pp)
        if sjc_meta["has_dissent"]:
            chunks.append(make_chunk(vol_meta, "sjc_dissent",
                                     f"Dissent: {title}", sl,
                                     sjc={"case_numbers": sjc_meta["case_numbers"]},
                                     confidence=0.45))
    return chunks


def pre_sjc_chunks(pages, vol_meta, claimed, skip_judicial_report=False):
    """Graceful pre-SJC judicial/constitutional labeling by heading + page.

    When skip_judicial_report (GA 14-17 overlap, where the dedicated CJB matcher
    has already emitted the Committee-on-Judicial-Business report as a cjb_report
    and claimed its pages), the judicial-business committee_report is not
    re-emitted here. Per-case adjudications still emit sjc_decision (the SJC owns
    decisions in the overlap), skipping any page already claimed by the CJB pass.
    """
    chunks = []
    ordinal = vol_meta["ga_ordinal"]
    # Judicial Business committee report region
    if not skip_judicial_report:
        reg = find_region(pages, PRE_SJC_JUDICIAL_RE, max_pages=40)
        if reg:
            s, e = reg
            ch = make_chunk(vol_meta, "committee_report",
                            f"Report of the Committee on Judicial Business (GA {ordinal})",
                            pages[s:e], confidence=0.7)
            ch["committee"] = "judicial_business"
            chunks.append(ch)
    # Constitutional documents committee
    reg2 = find_region(pages, PRE_SJC_CONST_RE, max_pages=20)
    if reg2:
        s, e = reg2
        ch = make_chunk(vol_meta, "committee_report",
                        f"Constitutional committee report (GA {ordinal})",
                        pages[s:e], confidence=0.6)
        ch["committee"] = "constitutional_documents"
        chunks.append(ch)
    # Per-case judicial commission adjudications (mid-scanned): pages with a
    # party-vs-court caption OR a 'roll of commissioners' + judgment.
    for i, p in enumerate(pages):
        if p["pdf_page"] in claimed:
            continue
        t = collapse_caps_spacing(deemph(p["text"]))
        if JUDICIAL_CASE_CAP_RE.search(t) or \
           (re.search(r"roll of commission", t, re.I) and find_disposition(t)):
            disp = find_disposition(t)
            ch = make_chunk(vol_meta, "sjc_decision",
                            f"Judicial case (GA {ordinal}, p.{p['pdf_page']})",
                            pages[i:i + 1],
                            sjc={"case_numbers": [], "disposition": disp,
                                 "vote": find_vote(t), "has_dissent": bool(DISSENT_RE.search(t)),
                                 "has_concurrence": False, "precedent_cites": [],
                                 "roman_sections": []},
                            confidence=0.5)
            chunks.append(ch)
            # claim the page so the later appendix pass treats this more-specific
            # judicial decision as the owner and does not double-cover it.
            claimed.add(p["pdf_page"])
    return chunks


# ===========================================================================
# source manifest
# ===========================================================================
def load_source_manifest():
    path = os.path.join(ROOT, "build", "source_manifest.csv")
    out = {}
    if not os.path.exists(path):
        return out
    import csv
    with open(path) as fh:
        for row in csv.DictReader(fh):
            f = row.get("file", "")
            m = re.match(r"(\d+)\w*_pcaga_(\d{4})", f)
            if m:
                vol = f"ga{int(m.group(1)):02d}_{m.group(2)}"
                out[vol] = {"file": f, "sha256": row.get("sha256"),
                            "bytes": row.get("bytes"), "pages": row.get("pages")}
    return out


# ===========================================================================
# VALIDATION against golden labels (per-era recall)
# ===========================================================================
GOLDEN_VOL = {
    "1st_pcaga_1973.json": "ga01_1973",
    "14th_pcaga_1986.json": "ga14_1986",
    "31st_pcaga_2003.json": "ga31_2003",
    "49th_pcaga_2022.json": "ga49_2022",
}


def golden_pdf_page(unit, era):
    """Golden labels store page_start in printed pages; convert to pdf page
    using the documented per-era offsets so we can match against chunk pdf ranges.
    Returns (pdf_lo, pdf_hi) best estimate, OR None."""
    if "pdf_page_start" in unit and unit["pdf_page_start"]:
        ps = unit["pdf_page_start"]
        return (ps, ps)
    ps = unit.get("page_start")
    pe = unit.get("page_end", ps)
    if ps is None:
        return None
    # offsets documented in label notes: 1st: pdf==printed; 14th: pdf=printed+2;
    # 31st: pdf=printed+2 (journal); 49th: ~printed+3..+17 (use printed value too)
    off = {"early-scanned-no-item-id": 0, "mid-scanned": 2,
           "early-digital": 2, "modern-digital": 3}.get(era, 0)
    return (ps + off, pe + off)


def chunk_covers(chunk, lo, hi, slack=3):
    """Does the chunk's pdf page range overlap [lo,hi] (with slack)?"""
    cs, ce = chunk["pdf_page_start"], chunk["pdf_page_end"]
    return not (ce < lo - slack or cs > hi + slack)


def validate(all_chunks_by_vol):
    """Compute per-era SJC and CCB recall vs golden labels."""
    results = []
    for fname, vol in GOLDEN_VOL.items():
        gpath = os.path.join(GOLDEN_DIR, fname)
        if not os.path.exists(gpath) or vol not in all_chunks_by_vol:
            continue
        g = json.load(open(gpath))
        era = g.get("era", "?")
        chunks = all_chunks_by_vol[vol]
        sjc_chunks = [c for c in chunks if c["section_type"] in
                      ("sjc_decision", "sjc_dissent", "sjc_concurrence")]
        # SJC recall: each golden sjc_unit must be covered by some sjc chunk
        # (for pre-SJC eras the analog is committee_report + sjc_decision)
        sjc_units = g.get("sjc_units", [])
        ccb_units = g.get("ccb_units", [])
        # In PRE-SJC eras the era-analog judicial/constitutional actions are
        # recorded as JOURNAL ITEMS (e.g. 1-51, 1-81) and committee reports, so
        # those chunk types are legitimate cover for the golden analog units.
        pre_sjc = not g.get("has_sjc", False)
        journal = [c for c in chunks if c["section_type"] == "journal_item"]
        committee = [c for c in chunks if c["section_type"] == "committee_report"]
        # In PRE-SJC eras the judicial/constitutional analog units are printed as
        # lettered APPENDICES (e.g. Appendix I 'Judicial Business'); an appendix
        # chunk bracketed over that region is legitimate cover (and is where these
        # pages now land once the appendix bracketing claims them ahead of the
        # journal pass), so include appendix chunks in the pre-SJC cover pools.
        appendix = [c for c in chunks if c["section_type"] == "appendix"]
        pre_sjc_extra = (journal + appendix) if pre_sjc else []
        sjc_cover_pool = sjc_chunks + committee + pre_sjc_extra
        ccb_cover_pool = [c for c in chunks if c["section_type"] in
                          ("ccb_overture_advice", "ccb_minute_review")] + committee \
            + pre_sjc_extra

        item_re = re.compile(r"\b(\d{1,2}-\d{1,3})\b")

        def golden_item_ids(u):
            """Journal-item ids embedded in a golden unit's title (pre-SJC analog)."""
            return {m.group(1) for m in item_re.finditer(u.get("title", ""))
                    if int(m.group(1).split("-")[0]) == g.get("ga_ordinal", -1)}

        def recall(units, pool):
            if not units:
                return None, 0, 0, []
            hit = 0
            misses = []
            for u in units:
                cno = u.get("case_no")
                gitems = golden_item_ids(u)
                covered = False
                # 1) case-number match anywhere in the pool
                if cno and any(cno in (c.get("sjc") or {}).get("case_numbers", [])
                               for c in pool):
                    covered = True
                # 2) journal-item-id match (pre-SJC analog units)
                if not covered and gitems:
                    pool_items = set()
                    for c in pool:
                        pool_items.update(c.get("ga_item_ids", []))
                    if gitems & pool_items:
                        covered = True
                # 3) page-range overlap
                if not covered:
                    rng = golden_pdf_page(u, era)
                    if rng is not None:
                        lo, hi = rng
                        covered = any(chunk_covers(c, lo, hi) for c in pool)
                if covered:
                    hit += 1
                else:
                    misses.append((cno or u.get("title", "")[:40],
                                   golden_pdf_page(u, era)))
            return hit / len(units), hit, len(units), misses

        sjc_r, sjc_hit, sjc_tot, sjc_miss = recall(sjc_units, sjc_cover_pool)
        ccb_r, ccb_hit, ccb_tot, ccb_miss = recall(ccb_units, ccb_cover_pool)
        results.append({
            "era": era, "vol": vol,
            "has_sjc": g.get("has_sjc"), "has_ccb": g.get("has_ccb"),
            "sjc_recall": sjc_r, "sjc_hit": sjc_hit, "sjc_total": sjc_tot,
            "ccb_recall": ccb_r, "ccb_hit": ccb_hit, "ccb_total": ccb_tot,
            "sjc_misses": sjc_miss[:6], "ccb_misses": ccb_miss[:6],
        })
    return results


def validate_cjb(all_chunks_by_vol):
    """Per-volume pre-SJC CJB recall vs golden/labels/*_cjb.json.

    Each golden judicial_unit (kind cjb_report | judicial_case) is COVERED iff
    some CJB chunk (cjb_report / cjb_decision) overlaps its pdf page range. The
    early volumes are OCR-shattered scans, so recall is reported honestly per
    volume and split by unit kind (report vs case). Cover pool is CJB chunks plus
    journal_item / committee_report as a fallback so a unit captured under the
    journal segmentation still counts (the unit IS recorded in the minutes)."""
    results = []
    for gpath in sorted(__import__("glob").glob(os.path.join(GOLDEN_DIR, "*_cjb.json"))):
        g = json.load(open(gpath))
        vol = g["vol"]
        if vol not in all_chunks_by_vol:
            continue
        chunks = all_chunks_by_vol[vol]
        cjb_chunks_l = [c for c in chunks if c["section_type"] in CJB_SECTION_TYPES]
        fallback = [c for c in chunks if c["section_type"] in
                    ("journal_item", "committee_report")]
        units = g.get("judicial_units", [])

        def cover(unit, primary_only):
            ps = unit.get("page_start")
            pe = unit.get("page_end", ps)
            if ps is None:
                return False
            pool = cjb_chunks_l if primary_only else (cjb_chunks_l + fallback)
            return any(chunk_covers(c, ps, pe, slack=2) for c in pool)

        def tally(kinds, primary_only):
            us = [u for u in units if u.get("kind") in kinds]
            if not us:
                return None, 0, 0, []
            hit = 0
            miss = []
            for u in us:
                if cover(u, primary_only):
                    hit += 1
                else:
                    miss.append({"kind": u.get("kind"),
                                 "case_no": u.get("case_no"),
                                 "pages": [u.get("page_start"), u.get("page_end")],
                                 "title": (u.get("title") or "")[:60]})
            return hit / len(us), hit, len(us), miss

        # primary CJB-typed recall (cjb_report/cjb_decision only)
        rep_r, rep_h, rep_t, rep_m = tally({"cjb_report"}, True)
        case_r, case_h, case_t, case_m = tally({"judicial_case"}, True)
        all_r, all_h, all_t, all_m = tally({"cjb_report", "judicial_case"}, True)
        # with-fallback recall (counts units captured under journal_item too)
        _, fb_h, fb_t, _ = tally({"cjb_report", "judicial_case"}, False)
        results.append({
            "vol": vol,
            "cjb_report_recall": rep_r, "cjb_report_hit": rep_h, "cjb_report_total": rep_t,
            "cjb_case_recall": case_r, "cjb_case_hit": case_h, "cjb_case_total": case_t,
            "cjb_overall_recall": all_r, "cjb_overall_hit": all_h, "cjb_overall_total": all_t,
            "cjb_overall_recall_with_journal_fallback":
                (fb_h / fb_t) if fb_t else None,
            "n_cjb_report_chunks": sum(1 for c in cjb_chunks_l
                                       if c["section_type"] == "cjb_report"),
            "n_cjb_decision_chunks": sum(1 for c in cjb_chunks_l
                                         if c["section_type"] == "cjb_decision"),
            "misses": all_m,
        })
    return results


def spot_check_citations(all_chunks_by_vol, n=50):
    """Sample BCO citations from chunks and verify they appear verbatim in the
    page text they came from. Returns precision estimate."""
    import random
    rng = random.Random(42)
    samples = []
    pool = []
    for vol, chunks in all_chunks_by_vol.items():
        for c in chunks:
            for b in c.get("bco_citations", []):
                pool.append((vol, c, "bco", b))
            for r in c.get("rao_citations", []):
                pool.append((vol, c, "rao", r))
    rng.shuffle(pool)
    pool = pool[:n]
    page_cache = {}
    good = 0
    for vol, c, kind, cite in pool:
        if vol not in page_cache:
            page_cache[vol] = {p["pdf_page"]: deemph(p["text"])
                               for p in load_pages(vol)}
        text = "\n".join(page_cache[vol].get(pp, "")
                         for pp in range(c["pdf_page_start"], c["pdf_page_end"] + 1))
        ok = False
        if kind == "bco":
            ch, _, sec = cite.partition("-")
            sec = sec.split(".")[0]
            # verify BCO + chapter + section co-occur
            if re.search(rf"BCO\s*0*{ch}-0*{sec}\b", text, re.I) or \
               re.search(rf"BCO\s*0*{ch}\b.{{0,12}}{sec}", text, re.I):
                ok = True
        else:
            # cite like 'RAO 16', 'RAO 16-3', 'RAO 16.3' -> verify chapter present
            mch = re.search(r"(\d{1,2})", cite)
            base = mch.group(1) if mch else None
            if base and re.search(rf"RAO[ \t]*0*{base}\b", text, re.I):
                ok = True
        if ok:
            good += 1
        samples.append({"vol": vol, "kind": kind, "cite": cite, "ok": ok,
                        "page_range": c["page_range"]})
    precision = good / len(pool) if pool else 1.0
    return precision, samples


# ===========================================================================
# main
# ===========================================================================
def all_vols():
    vols = []
    for f in sorted(os.listdir(PAGE_JSONL_DIR)):
        m = re.match(r"(ga\d{2}_\d{4})\.pages\.jsonl$", f)
        if m:
            vols.append(m.group(1))
    return vols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vols", nargs="*", help="subset of vol ids (default all)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--validate-only", action="store_true",
                    help="re-read existing chunks.jsonl and just run validation")
    ap.add_argument("--out", default=OUT_CHUNKS)
    a = ap.parse_args()

    os.makedirs(INDEX_DIR, exist_ok=True)
    source_manifest = load_source_manifest()
    vols = a.vols or all_vols()

    if a.validate_only and os.path.exists(a.out):
        by_vol = {}
        for line in open(a.out):
            c = json.loads(line)
            by_vol.setdefault(c["parent_doc"], []).append(c)
    else:
        if os.path.exists(a.out) and not a.force and not a.vols:
            print(f"[skip] {a.out} exists; use --force to rebuild", file=sys.stderr)
            by_vol = {}
            for line in open(a.out):
                c = json.loads(line)
                by_vol.setdefault(c["parent_doc"], []).append(c)
        else:
            by_vol = {}
            all_meta = []
            for vol in vols:
                chunks, meta = process_volume(vol, source_manifest)
                by_vol[vol] = chunks
                all_meta.append(meta)
                print(f"[{vol}] era={meta['era']:26} has_sjc={str(meta['has_sjc']):5} "
                      f"has_ccb={str(meta['has_ccb']):5} appendices={meta['n_appendices']:2} "
                      f"chunks={meta['n_chunks']}", file=sys.stderr)
            # write atomically; preserve volumes not rebuilt if --vols subset
            existing = {}
            if a.vols and os.path.exists(a.out):
                for line in open(a.out):
                    c = json.loads(line)
                    if c["parent_doc"] not in by_vol:
                        existing.setdefault(c["parent_doc"], []).append(c)
            tmp = a.out + ".tmp"
            with open(tmp, "w") as fh:
                for vol, chunks in {**existing, **by_vol}.items():
                    for c in chunks:
                        fh.write(json.dumps(c, ensure_ascii=False) + "\n")
            os.replace(tmp, a.out)
            # re-read full set for validation
            by_vol = {}
            for line in open(a.out):
                c = json.loads(line)
                by_vol.setdefault(c["parent_doc"], []).append(c)

    # validation
    results = validate(by_vol)
    print("\n=== PER-ERA RECALL (vs golden labels) ===", file=sys.stderr)
    for r in results:
        print(json.dumps(r), file=sys.stderr)
    cjb_results = validate_cjb(by_vol)
    print("\n=== PRE-SJC CJB RECALL (vs golden/*_cjb.json) ===", file=sys.stderr)
    for r in cjb_results:
        print(json.dumps(r), file=sys.stderr)
    prec, _samples = spot_check_citations(by_vol, n=50)
    print(f"\nCitation precision (50-sample): {prec:.3f}", file=sys.stderr)

    total = sum(len(v) for v in by_vol.values())
    st = sum(1 for v in by_vol.values() for c in v if c["section_type"] == "sjc_decision")
    ct = sum(1 for v in by_vol.values() for c in v
             if c["section_type"] in ("ccb_overture_advice", "ccb_minute_review"))
    cjb_rep = sum(1 for v in by_vol.values() for c in v if c["section_type"] == "cjb_report")
    cjb_dec = sum(1 for v in by_vol.values() for c in v if c["section_type"] == "cjb_decision")
    by_body = {}
    for v in by_vol.values():
        for c in v:
            jb = c.get("judicial_body")
            if jb:
                by_body[jb] = by_body.get(jb, 0) + 1
    print(f"\nTotal chunks: {total} across {len(by_vol)} vols; "
          f"sjc_decision={st} ccb_advice/review={ct} "
          f"cjb_report={cjb_rep} cjb_decision={cjb_dec} judicial_by_body={by_body}",
          file=sys.stderr)

    # emit machine-readable summary on stdout
    print(json.dumps({
        "chunks_written": total, "volumes": len(by_vol),
        "citation_precision": prec, "per_era_recall": results,
        "cjb_recall": cjb_results,
        "sjc_decision_chunks": st, "ccb_chunks": ct,
        "cjb_report_chunks": cjb_rep, "cjb_decision_chunks": cjb_dec,
        "judicial_by_body": by_body,
    }))


if __name__ == "__main__":
    main()
