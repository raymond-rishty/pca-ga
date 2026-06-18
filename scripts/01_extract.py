#!/usr/bin/env python3
"""
01_extract.py — Phase 1 born-digital extraction (GAs 31-52, year>=2003).

page_jsonl is the SOURCE OF TRUTH; markdown is RENDERED from it, so a later
re-OCR pass can update one page row and re-render without touching this code.

Pipeline per volume:
  1. pymupdf4llm.to_markdown(doc, page_chunks=True, write_images=False)  — one
     entry per page, pulling the clean born-digital text layer (force_text=True
     is the default; this pymupdf4llm build has no use_ocr/force_ocr kwargs and
     does NOT re-render pixels for a page that already has text).
  2. De-boilerplate: detect this volume's running header/footer signatures with
     normalize.detect_boilerplate, then normalize.strip_page each page (also
     strips page-number lines + line-number gutters under the content-safety
     guard), then normalize.normalize_text.
  3. Write build/page_jsonl/ga<NN>_<year>.pages.jsonl — ONE ROW PER PAGE.
  4. render(vol): build markdown/ga<NN>_<year>.md from the jsonl rows + YAML
     front-matter, with a greppable per-page anchor + HTML provenance comment.

CLI:
  01_extract.py extract --era born-digital [--force] [--only ga52_2025 ...] [--workers N]
  01_extract.py render <vol-or-all> [--force]

Idempotent: a volume whose .md AND .jsonl already exist is skipped unless --force.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed

import fitz  # PyMuPDF
import pymupdf4llm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MINUTES = os.path.join(ROOT, "minutes")
PAGE_JSONL = os.path.join(ROOT, "build", "page_jsonl")
MARKDOWN = os.path.join(ROOT, "markdown")
MANIFEST = os.path.join(ROOT, "build", "source_manifest.csv")

sys.path.insert(0, HERE)
normalize = importlib.import_module("normalize")
qc = importlib.import_module("02_qc_score")  # numeric-prefixed -> importlib
format_md = importlib.import_module("format_md")  # render-time markdown structure (presentation)

SCHEMA_VERSION = 1
TABLE_STRATEGY = "lines_strict"  # born-digital tables are vector-ruled
# Alternating recto/verso running headers ("MINUTES OF THE GENERAL ASSEMBLY" /
# "JOURNAL") each land on ~25-47% of pages, so the default 0.5 frac misses them.
# 0.2 catches both alternating headers without catching real recurring content
# (e.g. "Appendix C" recurs on <10% of pages).
HEADER_MIN_FRAC = 0.2

# bare integer page-number line (footer/header), possibly markdown-bolded
_PAGENUM = re.compile(r"^\s*\**\s*(\d{1,4})\s*\**\s*$")
_PAGEWORD = re.compile(r"^\s*\**\s*(?:page|p\.)\s*(\d{1,4})\s*\**\s*$", re.I)
_ROMAN = re.compile(r"^\s*\**\s*([ivxlcdm]{1,7})\s*\**\s*$", re.I)
_ROMAN_VALS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


# --------------------------------------------------------------------------- volume discovery
def parse_name(fn: str):
    m = re.match(r"(\d+)(?:st|nd|rd|th)_pcaga_(\d{4})\.pdf$", fn)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))  # (ga_ordinal, year)


def born_digital_volumes():
    """Return [(ga_ordinal, year, filename, vol_id)] for year>=2003, sorted by ordinal."""
    out = []
    for fn in sorted(os.listdir(MINUTES)):
        if not fn.endswith(".pdf"):
            continue
        parsed = parse_name(fn)
        if not parsed:
            continue
        ordn, year = parsed
        if year >= 2003:
            out.append((ordn, year, fn, f"ga{ordn:02d}_{year}"))
    out.sort()
    return out


def scanned_volumes():
    """Return [(ga_ordinal, year, filename, vol_id)] for year<2003 (GAs 1-30):
    full-page image scans WITH an embedded OCR text layer, sorted by ordinal."""
    out = []
    for fn in sorted(os.listdir(MINUTES)):
        if not fn.endswith(".pdf"):
            continue
        parsed = parse_name(fn)
        if not parsed:
            continue
        ordn, year = parsed
        if year < 2003:
            out.append((ordn, year, fn, f"ga{ordn:02d}_{year}"))
    out.sort()
    return out


ORDINAL_WORDS = {
    1: "First", 2: "Second", 3: "Third", 4: "Fourth", 5: "Fifth", 6: "Sixth",
    7: "Seventh", 8: "Eighth", 9: "Ninth", 10: "Tenth", 11: "Eleventh",
    12: "Twelfth", 13: "Thirteenth", 14: "Fourteenth", 15: "Fifteenth",
    16: "Sixteenth", 17: "Seventeenth", 18: "Eighteenth", 19: "Nineteenth",
    20: "Twentieth", 21: "Twenty-First", 22: "Twenty-Second", 23: "Twenty-Third",
    24: "Twenty-Fourth", 25: "Twenty-Fifth", 26: "Twenty-Sixth", 27: "Twenty-Seventh",
    28: "Twenty-Eighth", 29: "Twenty-Ninth", 30: "Thirtieth",
    31: "Thirty-First", 32: "Thirty-Second", 33: "Thirty-Third", 34: "Thirty-Fourth",
    35: "Thirty-Fifth", 36: "Thirty-Sixth", 37: "Thirty-Seventh", 38: "Thirty-Eighth",
    39: "Thirty-Ninth", 40: "Fortieth", 41: "Forty-First", 42: "Forty-Second",
    43: "Forty-Third", 44: "Forty-Fourth", 45: "Forty-Fifth", 46: "Forty-Sixth",
    47: "Forty-Seventh", 48: "Forty-Eighth", 49: "Forty-Ninth", 50: "Fiftieth",
    51: "Fifty-First", 52: "Fifty-Second",
}


def load_manifest():
    by_file = {}
    with open(MANIFEST, newline="") as fh:
        for row in csv.DictReader(fh):
            by_file[row["file"]] = row
    return by_file


# --------------------------------------------------------------------------- printed page
def _roman_to_int(s: str):
    s = s.lower()
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN_VALS.get(ch, 0)
        if v == 0:
            return None
        total += -v if v < prev else v
        prev = max(prev, v)
    return total or None


def _plausible_folio(val: int, pdf_page: int, page_count: int) -> bool:
    """A printed folio is a sequential book page, so it must not exceed the volume's
    total page count by much, and must be near its pdf position (printed = pdf minus a
    small front-matter offset, never wildly ahead). This rejects a stray standalone
    year like '2003' on a title page being read as printed page 2003 of a 611p book."""
    if val < 1:
        return False
    if val > page_count + 5:
        return False
    # printed folio is at/behind the pdf index by the front-matter offset; allow a
    # small lead (a few pages) for odd numbering, but reject large forward jumps.
    if val > pdf_page + 5:
        return False
    return True


def parse_printed_page(raw_text: str, pdf_page: int, page_count: int):
    """Best-effort printed folio: scan the first 2 and last 2 non-blank lines for a
    bare page-number line (arabic, 'Page N', or roman). Done BEFORE stripping so the
    folio survives as metadata even though the line is removed. A numeric candidate is
    only accepted if it is a plausible sequential folio for this pdf position. Roman
    numerals (front matter) are accepted as-is. Returns str or None."""
    lines = [ln for ln in raw_text.split("\n") if ln.strip()]
    if not lines:
        return None
    candidates = lines[:2] + lines[-2:]
    # prefer the bottom edge (footer folio is the convention in this corpus)
    for ln in reversed(candidates):
        m = _PAGEWORD.match(ln)
        if m and _plausible_folio(int(m.group(1)), pdf_page, page_count):
            return m.group(1)
        m = _PAGENUM.match(ln)
        if m and _plausible_folio(int(m.group(1)), pdf_page, page_count):
            return m.group(1)
    # roman folio: front-matter only (early pdf pages). Single ambiguous letters
    # (i/v/x/l/c/d/m as list markers/initials) are rejected unless the value is a
    # small plausible front-matter folio AND we are in the front-matter zone.
    if pdf_page <= 30:
        for ln in reversed(candidates):
            m = _ROMAN.match(ln)
            if not m:
                continue
            val = _roman_to_int(m.group(1))
            if val and val <= pdf_page + 3 and val <= 40:
                return m.group(1).lower()
    return None


# --------------------------------------------------------------------------- GA-item tokens
def _demphasize(text: str) -> str:
    """Drop markdown emphasis markers (* and _) that pymupdf4llm wraps around tokens.
    A leading '_' in '_52-2-0_' is a word char and would suppress the \\b before the
    digit, hiding a token that is in fact present and human-readable. Strip them so
    GA-item detection (and the token-survival gate) sees the real text."""
    return text.replace("*", "").replace("_", "")


def ga_item_tokens(text: str, ordinal: int):
    """\\b\\d{1,2}-\\d{1,3}\\b restricted to left-group == this GA ordinal, so a
    BCO 34-1 cite in the 36th GA is not mistaken for a journal item, while genuine
    items like 36-47 are captured. De-duplicated, order preserved."""
    text = _demphasize(text)
    seen, out = set(), []
    for m in re.finditer(r"\b(\d{1,2})-(\d{1,3})\b", text):
        if int(m.group(1)) == ordinal:
            tok = m.group(0)
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
    return out


# --------------------------------------------------------------------------- extract one volume
def _chunks_by_page(doc, strategy):
    """Return {pdf_page(1-based): markdown_text}. In a full-document page_chunks
    call this pymupdf4llm build sets metadata['page'] to the 1-BASED pdf page
    number (chunk page 1 == fitz index 0), so it is used directly."""
    chunks = pymupdf4llm.to_markdown(
        doc, page_chunks=True, write_images=False, embed_images=False,
        table_strategy=strategy, show_progress=False,
    )
    return {c["metadata"]["page"]: c["text"] for c in chunks}


def _chunks_for_pages(doc, strategy, zero_based_pages):
    """Re-extract only the given pages (passed 0-based, as pymupdf4llm's pages=
    expects) with `strategy`. Returns {pdf_page(1-based): text}. This pymupdf4llm
    build reports metadata['page'] as the 1-BASED pdf page number even for a
    pages= call (verified: pages=[0,2,4] -> metadata.page 1,3,5), so it is used
    directly, with positional order as a fallback."""
    if not zero_based_pages:
        return {}
    requested = list(zero_based_pages)
    chunks = pymupdf4llm.to_markdown(
        doc, pages=requested, page_chunks=True, write_images=False,
        embed_images=False, table_strategy=strategy, show_progress=False,
    )
    one_based = {p + 1 for p in requested}
    out = {}
    for i, c in enumerate(chunks):
        mp = c["metadata"].get("page")
        if mp in one_based:
            out[mp] = c["text"]
        elif i < len(requested):
            out[requested[i] + 1] = c["text"]
    return out


def _pick_page_text(strict_md, text_md, raw_fitz):
    """Per-page rescue for born-digital pages whose ruled financial/scanned
    appendices make table_strategy='lines_strict' absorb (and drop) the text.

    Default is 'lines_strict' (it preserves real table structure and matches the
    pdftotext baseline at ~1.0 char-parity / 1.0 token-survival on ordinary pages).
    Only OVERRIDE when lines_strict catastrophically loses the genuine text layer:
      - if strict kept >=50% of the raw text-layer chars, keep strict (no override);
      - else prefer the 'text' strategy if it recovered the content;
      - else fall back to the verbatim born-digital text layer (raw fitz get_text).
    Returns (chosen_text, source_tag)."""
    raw_len = len(raw_fitz.strip())
    s_len = len(strict_md.strip())
    t_len = len(text_md.strip())
    # ordinary page: strict captured the bulk of the text layer -> keep it as-is.
    # (lines_strict gives clean, correctly-associated roster/vote tables; the 'text'
    #  strategy mangles them into <br>-riddled fake cells and splits words across
    #  columns, so strict is the fidelity choice for the common case.)
    if raw_len <= 200 or s_len >= 0.5 * raw_len:
        return strict_md, "pymupdf4llm_lines_strict"
    # strict lost >50% of a real text layer (ruled / embedded-scan financial
    # appendices). The verbatim text layer (raw fitz) preserves line-by-line reading
    # order; the 'text' strategy fabricates a broken table here. Prefer raw unless
    # the text strategy recovered clearly more characters AND raw is itself thin.
    if t_len > max(s_len, raw_len) * 1.3:
        return text_md, "pymupdf4llm_text"
    return raw_fitz, "raw_textlayer"


def extract_volume(ordn: int, year: int, fn: str, vol_id: str, manifest_row: dict):
    """Produce the page_jsonl rows for one born-digital volume. Returns (rows, stats)."""
    pdf = os.path.join(MINUTES, fn)
    doc = fitz.open(pdf)
    n = doc.page_count
    # one full pass with the structure-preserving strategy (the common case)...
    strict = _chunks_by_page(doc, "lines_strict")
    # ...then find pages where lines_strict catastrophically lost the genuine text
    # layer (ruled financial/scanned appendices) and rescue ONLY those with the
    # cheaper 'text' strategy applied to just those pages. A full second pass over
    # every volume is far too slow; ~5% of pages need rescue.
    raw_fitz_cache = {pp: doc[pp - 1].get_text() for pp in range(1, n + 1)}
    deficient = [pp for pp in range(1, n + 1)
                 if len(raw_fitz_cache[pp].strip()) > 200
                 and len(strict.get(pp, "").strip()) < 0.5 * len(raw_fitz_cache[pp].strip())]
    text_strat = {}
    if deficient:
        text_strat = _chunks_for_pages(doc, "text", [p - 1 for p in deficient])

    # assemble per-page chosen source text (1-based pdf pages 1..n)
    chosen = {}
    sources = Counter()
    for pp in range(1, n + 1):
        s_md = strict.get(pp, "")
        t_md = text_strat.get(pp, "")
        raw_fitz = raw_fitz_cache[pp]
        ctext, src = _pick_page_text(s_md, t_md, raw_fitz)
        chosen[pp] = ctext
        sources[src] += 1

    raw_pages = [chosen[pp] for pp in range(1, n + 1)]
    boiler = normalize.detect_boilerplate(raw_pages, min_frac=HEADER_MIN_FRAC)

    rows = []
    for pp in range(1, n + 1):
        raw = chosen[pp]
        printed = parse_printed_page(raw, pp, n)
        clean, _removed = normalize.strip_page(raw, boiler)
        text = normalize.normalize_text(clean)
        cls = qc.classify(text)
        qc_fields = {
            "verdict": cls["verdict"],
            "dict_hitrate": cls["dict_hitrate"],
            "whitespace_frag": cls["whitespace_frag"],
            "digit_flag": cls["digit_flag"],
            "digit_present": cls["digit_present"],
        }
        rows.append({
            "vol": vol_id,
            "ga_ordinal": ordn,
            "year": year,
            "pdf_page": pp,
            "printed_page": printed,
            "text": text,
            "char_count": len(text),
            "ga_item_tokens": ga_item_tokens(text, ordn),
            "qc": qc_fields,
            "engine": "born_digital",
        })
    doc.close()

    stats = {
        "vol": vol_id, "pages": len(rows),
        "boiler_headers": sorted(boiler["headers"]),
        "boiler_footers": sorted(boiler["footers"]),
        "total_chars": sum(r["char_count"] for r in rows),
        "empty_pages": sum(1 for r in rows if r["char_count"] == 0),
        "page_sources": dict(sources),
    }
    return rows, stats


# --------------------------------------------------------------------------- scanned volumes
def _pdftotext_layout_pages(pdf: str, page_count: int) -> dict:
    """Extract the EMBEDDED OCR text layer for every page of a scanned volume with
    `pdftotext -layout` (one subprocess for the whole file; pages are separated by
    the form-feed \\f that pdftotext emits per page). Returns {pdf_page(1-based): text}.

    `pdftotext -layout` is chosen over pymupdf4llm for the scanned era because the
    embedded OCR layer carries NO vector ruling lines, so pymupdf4llm's table
    detection fabricates broken `|Col1|...|<br>|` grids that split words across fake
    cells (verified on 14th p200 / 8th p100). `-layout` preserves the column structure
    of rosters (Presbytery/City/Date/Name) and the reading order of prose, which is
    what the de-spacer and QC scorer need. use_ocr is irrelevant here: we never
    rasterize — we read the layer already in the PDF (do NOT re-OCR in this phase)."""
    out = subprocess.run(
        ["pdftotext", "-q", "-layout", pdf, "-"],
        capture_output=True, text=True,
    ).stdout
    parts = out.split("\f")
    # pdftotext emits one \f per page; a trailing \f yields an empty tail part.
    if parts and parts[-1] == "":
        parts = parts[:-1]
    pages = {}
    for i, txt in enumerate(parts, start=1):
        pages[i] = txt
    # robustness: if the form-feed split disagrees with the PDF page count (rare:
    # a page can legitimately be empty and contribute no \f boundary on some builds),
    # fall back to a per-page extraction so pdf_page stays aligned to the real index.
    if len(pages) != page_count:
        pages = {}
        for pp in range(1, page_count + 1):
            pages[pp] = subprocess.run(
                ["pdftotext", "-q", "-layout", "-f", str(pp), "-l", str(pp), pdf, "-"],
                capture_output=True, text=True,
            ).stdout
    return pages


def _routing_text(deboilered: str) -> str:
    """The text handed to qc.classify for the ROUTING verdict: soft-hyphen removal +
    lowercase line-end dehyphenation, but NOT yet de-spaced. classify() despaces
    internally to compute despaced_hitrate and decide despace-vs-reocr, so it must
    see the still-shattered text to detect a 'despace' page; if we de-spaced first,
    every recoverable page would look 'good' and the despace workload would vanish
    from the stats."""
    t = deboilered.replace(normalize.SOFT_HYPHEN, "")
    t = re.sub(r"([a-z])-\n([a-z])", r"\1\2", t)
    return t


def extract_scanned_volume(ordn: int, year: int, fn: str, vol_id: str, manifest_row: dict):
    """Produce page_jsonl rows for one scanned (embedded-OCR) volume.

    Pipeline: pdftotext -layout (embedded layer) -> de-boilerplate -> classify the
    pre-despace routing text for the verdict -> store the fully de-spaced/normalized
    text. engine='embedded'. Returns (rows, stats)."""
    pdf = os.path.join(MINUTES, fn)
    doc = fitz.open(pdf)
    n = doc.page_count
    doc.close()
    layout = _pdftotext_layout_pages(pdf, n)

    raw_pages = [layout.get(pp, "") for pp in range(1, n + 1)]
    # scanned running headers ("MINUTES OF THE GENERAL ASSEMBLY") sit on nearly every
    # page; the default 0.5 frac is the right threshold here (no recto/verso alternation
    # like the born-digital JOURNAL header), but keep 0.2 to also catch a verso variant.
    boiler = normalize.detect_boilerplate(raw_pages, min_frac=HEADER_MIN_FRAC)

    rows, verdicts = [], Counter()
    for pp in range(1, n + 1):
        raw = raw_pages[pp - 1]
        printed = parse_printed_page(raw, pp, n)
        clean, _removed = normalize.strip_page(raw, boiler)
        # routing verdict from the pre-despace (still-shattered) text
        cls = qc.classify(_routing_text(clean))
        # stored text is the fully de-spaced / normalized rendering
        text = normalize.normalize_text(clean)
        qc_fields = {
            "verdict": cls["verdict"],
            "dict_hitrate": cls["dict_hitrate"],
            "whitespace_frag": cls["whitespace_frag"],
            "despaced_hitrate": cls["despaced_hitrate"],
            "digit_flag": cls["digit_flag"],
            "digit_present": cls["digit_present"],
        }
        verdicts[cls["verdict"]] += 1
        rows.append({
            "vol": vol_id,
            "ga_ordinal": ordn,
            "year": year,
            "pdf_page": pp,
            "printed_page": printed,
            "text": text,
            "char_count": len(text),
            "ga_item_tokens": ga_item_tokens(text, ordn),
            "qc": qc_fields,
            "engine": "embedded",
        })

    stats = {
        "vol": vol_id, "pages": len(rows),
        "boiler_headers": sorted(boiler["headers"]),
        "boiler_footers": sorted(boiler["footers"]),
        "total_chars": sum(r["char_count"] for r in rows),
        "empty_pages": sum(1 for r in rows if r["char_count"] == 0),
        "verdicts": dict(verdicts),
        "digit_flag_pages": sum(1 for r in rows if r["qc"]["digit_flag"]),
    }
    return rows, stats


def write_jsonl(vol_id: str, rows: list):
    os.makedirs(PAGE_JSONL, exist_ok=True)
    path = os.path.join(PAGE_JSONL, f"{vol_id}.pages.jsonl")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return path


def read_jsonl(vol_id: str):
    path = os.path.join(PAGE_JSONL, f"{vol_id}.pages.jsonl")
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# --------------------------------------------------------------------------- render markdown
def _yaml_escape(s):
    s = str(s)
    if re.search(r'[:#\[\]{}",&*?|<>=!%@`]', s) or s != s.strip():
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


def render(vol_id: str, manifest_by_file: dict, force: bool = False):
    rows = read_jsonl(vol_id)
    if rows is None:
        raise SystemExit(f"render: no page_jsonl for {vol_id} (run extract first)")
    m = re.match(r"ga(\d+)_(\d+)$", vol_id)
    ordn, year = int(m.group(1)), int(m.group(2))
    # locate source file from manifest
    fn = None
    for f in manifest_by_file:
        p = parse_name(f)
        if p and p[0] == ordn and p[1] == year:
            fn = f
            break
    if fn is None:
        raise SystemExit(f"render: cannot find source pdf for {vol_id}")
    src = manifest_by_file[fn]

    out_path = os.path.join(MARKDOWN, f"{vol_id}.md")
    if os.path.exists(out_path) and not force:
        return out_path, False

    page_count = len(rows)
    fm = []
    fm.append("---")
    fm.append("doc_type: ga_minutes")
    fm.append(f"ga_ordinal: {ordn}")
    fm.append(f"ga_ordinal_token: {_yaml_escape(ORDINAL_WORDS.get(ordn, str(ordn)))}")
    fm.append(f"year: {year}")
    fm.append(f"page_count: {page_count}")
    fm.append("source_pdf:")
    fm.append(f"  file: {_yaml_escape(fn)}")
    fm.append(f"  sha256: {src['sha256']}")
    # engine is per-page in the jsonl; a volume is uniformly one engine in P1/P2.
    engine = rows[0].get("engine", "born_digital") if rows else "born_digital"
    if engine == "embedded":
        method, ocr = "pdftotext_layout", "embedded"
    else:
        method, ocr = "pymupdf4llm", "born_digital"
    fm.append("extraction:")
    fm.append(f"  method: {method}")
    fm.append(f"  ocr: {ocr}")
    fm.append("  deboilerplated: true")
    fm.append("  stripped: [headers, footers, page_numbers, line_numbers]")
    fm.append(f"schema_version: {SCHEMA_VERSION}")
    fm.append("---")
    fm.append("")

    body = []
    for r in rows:
        printed = r.get("printed_page")
        anchor_id = f"ga{ordn:02d}-p{printed if printed not in (None, '') else r['pdf_page']}"
        body.append(f'<a id="{anchor_id}"></a>')
        body.append(
            f"<!-- PAGE ga={ordn} pdf_page={r['pdf_page']} "
            f"printed_page={printed if printed is not None else 'null'} -->"
        )
        body.append("")
        if r["text"]:
            body.append(format_md.format_text(r["text"]))   # presentation-only structure
        body.append("")

    os.makedirs(MARKDOWN, exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(fm))
        fh.write("\n".join(body))
        fh.write("\n")
    os.replace(tmp, out_path)
    return out_path, True


# --------------------------------------------------------------------------- QC gates
def pdftotext_layout(pdf: str) -> str:
    return subprocess.run(
        ["pdftotext", "-q", "-layout", pdf, "-"],
        capture_output=True, text=True,
    ).stdout


def count_ga_items_in_text(text: str, ordinal: int) -> int:
    """Count (with multiplicity) GA-item tokens left-group==ordinal in a blob.
    Emphasis markers are stripped first so markdown-wrapped tokens (_52-2-0_) are
    counted the same way in the final text and the pdftotext baseline."""
    text = _demphasize(text)
    return sum(1 for m in re.finditer(r"\b(\d{1,2})-(\d{1,3})\b", text)
               if int(m.group(1)) == ordinal)


def qc_gates(vol_id: str, ordn: int, fn: str, rows: list) -> dict:
    """Compute the Phase-1 QC gates for one volume against a pdftotext -layout baseline."""
    pdf = os.path.join(MINUTES, fn)
    base = pdftotext_layout(pdf)
    base_items = count_ga_items_in_text(base, ordn)
    final_text = "\n".join(r["text"] for r in rows)
    final_items = sum(len(r["ga_item_tokens"]) for r in rows)
    # token survival uses multiplicity in final markdown too (re-derive on the joined text
    # so we count occurrences, not unique-per-page sets)
    final_items_mult = count_ga_items_in_text(final_text, ordn)

    base_chars = len(re.sub(r"[ \t]+", " ", base))
    final_chars = sum(r["char_count"] for r in rows)

    # content parity ignores markdown furniture (* _ | # > ` and <br>): pymupdf4llm
    # renders dense roll-call/vote tables as markdown grids whose pipes/<br>/emphasis
    # inflate the raw char count even though no content was added, and it legitimately
    # CAPTURES MORE table text than `pdftotext -layout` (which collapses those grids).
    # The content-parity ratio is the honest loss/duplication signal.
    def _alnum(t):
        return len(re.sub(r"[^0-9A-Za-z]", "", t))
    base_alnum = _alnum(base)
    final_alnum = _alnum(final_text)

    token_survival = (final_items_mult / base_items) if base_items else 1.0
    char_parity = (final_chars / base_chars) if base_chars else 0.0
    content_parity = (final_alnum / base_alnum) if base_alnum else 0.0

    md_path = os.path.join(MARKDOWN, f"{vol_id}.md")
    md_bytes = os.path.getsize(md_path) if os.path.exists(md_path) else 0

    return {
        "vol": vol_id,
        "pages": len(rows),
        "base_ga_items": base_items,
        "final_ga_items_unique": final_items,
        "final_ga_items_mult": final_items_mult,
        "token_survival": round(token_survival, 4),
        "base_chars": base_chars,
        "final_chars": final_chars,
        "char_parity": round(char_parity, 4),
        "base_alnum": base_alnum,
        "final_alnum": final_alnum,
        "content_parity": round(content_parity, 4),
        "md_bytes": md_bytes,
        "empty_pages": sum(1 for r in rows if r["char_count"] == 0),
        "tiny": md_bytes < 2000,
    }


def gate_failures(g: dict) -> list:
    fails = []
    # (a) GA-item token survival ~1.0  (allow tiny shortfall; layout baseline can
    # double-count across page-split tokens, so >1.0 is fine, <0.98 is a fail)
    if g["base_ga_items"] >= 5 and g["token_survival"] < 0.98:
        fails.append(f"GA-item token survival {g['token_survival']:.3f} < 0.98 "
                     f"({g['final_ga_items_mult']}/{g['base_ga_items']})")
    # (b) char-count parity vs pdftotext baseline (after de-boilerplating), judged on
    # CONTENT chars (markdown furniture stripped). de-boilerplating legitimately drops
    # a little furniture (content_parity slightly <1.0 is fine) and pymupdf4llm
    # legitimately captures more dense-table text than pdftotext -layout (content_parity
    # >1.0 is fine and expected on vote-table-heavy volumes). A real fault is content
    # LOSS (<0.90) or gross duplication (content_parity > 1.6 with no table explanation).
    if g["content_parity"] < 0.90:
        fails.append(f"content loss: parity {g['content_parity']:.3f} "
                     f"(final {g['final_alnum']} vs base {g['base_alnum']} alnum chars)")
    if g["content_parity"] > 1.60:
        fails.append(f"content inflation {g['content_parity']:.3f} (possible duplication)")
    # (c) no empty/tiny .md
    if g["tiny"]:
        fails.append(f"markdown too small ({g['md_bytes']} bytes)")
    if g["empty_pages"] > max(3, int(0.05 * g["pages"])):
        fails.append(f"{g['empty_pages']} empty pages (>5%)")
    return fails


# --------------------------------------------------------------------------- workers
def _extract_one(args):
    ordn, year, fn, vol_id, manifest_row = args
    rows, stats = extract_volume(ordn, year, fn, vol_id, manifest_row)
    write_jsonl(vol_id, rows)
    return vol_id, stats


def _extract_one_scanned(args):
    ordn, year, fn, vol_id, manifest_row = args
    rows, stats = extract_scanned_volume(ordn, year, fn, vol_id, manifest_row)
    write_jsonl(vol_id, rows)
    return vol_id, stats


# --------------------------------------------------------------------------- re-OCR queue
REOCR_DIR = os.path.join(ROOT, "build", "reocr")
REOCR_QUEUE = os.path.join(REOCR_DIR, "reocr_queue.csv")


def build_reocr_queue():
    """Write build/reocr/reocr_queue.csv from EVERY scanned volume's page_jsonl.

    A page is queued iff it is genuinely beyond cheap recovery:
      - qc.verdict == 'reocr'  (low dict-hitrate that de-spacing cannot recover —
        truly character-corrupt), OR
      - qc.digit_flag == True AND qc.digit_present  (an implausible citation/BCO/
        case token on a page that actually carries citations — a roster/citation
        page whose digit channel failed; digit_flag is independent of the text
        verdict, so a 'good'/'despace' page with a corrupt case number still queues).
    Pages that merely need de-spacing are NOT queued (de-spacing is deterministic
    and already applied). Columns: file,pdf_page,dict_hitrate,despaced_hitrate,
    verdict,digit_flag. Idempotent: fully rewritten from the jsonl source of truth."""
    os.makedirs(REOCR_DIR, exist_ok=True)
    rows_out = []
    for ordn, year, fn, vol_id in scanned_volumes():
        rows = read_jsonl(vol_id)
        if rows is None:
            continue
        for r in rows:
            q = r["qc"]
            verdict = q.get("verdict")
            digit_flag = bool(q.get("digit_flag"))
            digit_present = bool(q.get("digit_present"))
            if verdict == "reocr" or (digit_flag and digit_present):
                rows_out.append({
                    "file": fn,
                    "pdf_page": r["pdf_page"],
                    "dict_hitrate": q.get("dict_hitrate"),
                    "despaced_hitrate": q.get("despaced_hitrate"),
                    "verdict": verdict,
                    "digit_flag": digit_flag,
                })
    tmp = REOCR_QUEUE + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "file", "pdf_page", "dict_hitrate", "despaced_hitrate", "verdict", "digit_flag"])
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    os.replace(tmp, REOCR_QUEUE)
    return REOCR_QUEUE, len(rows_out)


# --------------------------------------------------------------------------- CLI
def cmd_extract(a):
    manifest = load_manifest()
    if a.era == "born-digital":
        vols = born_digital_volumes()
        worker = _extract_one
    else:  # scanned
        vols = scanned_volumes()
        worker = _extract_one_scanned
    if a.only:
        wanted = set(a.only)
        vols = [v for v in vols if v[3] in wanted]
    todo = []
    for ordn, year, fn, vol_id in vols:
        jpath = os.path.join(PAGE_JSONL, f"{vol_id}.pages.jsonl")
        mpath = os.path.join(MARKDOWN, f"{vol_id}.md")
        if not a.force and os.path.exists(jpath) and os.path.exists(mpath):
            print(f"[skip] {vol_id} (jsonl+md exist)")
            continue
        todo.append((ordn, year, fn, vol_id, manifest.get(fn, {})))

    results = {}
    if a.workers > 1 and len(todo) > 1:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            futs = {ex.submit(worker, t): t[3] for t in todo}
            for fut in as_completed(futs):
                vol_id, stats = fut.result()
                results[vol_id] = stats
                _print_extract_line(stats)
    else:
        for t in todo:
            vol_id, stats = worker(t)
            results[vol_id] = stats
            _print_extract_line(stats)

    # render markdown for every volume we just (re)built (results = extracted OK).
    for ordn, year, fn, vol_id in vols:
        if vol_id in results:
            render(vol_id, manifest, force=True)
    print(f"[extract] done; rebuilt {len(results)} volume(s), rendered markdown")

    # the scanned era owns the re-OCR queue; rebuild it from the full jsonl set so it
    # reflects every scanned volume on disk (not just the ones touched this run).
    if a.era == "scanned":
        path, nq = build_reocr_queue()
        print(f"[reocr] wrote {path}: {nq} queued page(s)")


def _print_extract_line(stats):
    extra = ""
    if "verdicts" in stats:
        extra = (f" verdicts={stats['verdicts']} digit_flag={stats['digit_flag_pages']}"
                 f" empty={stats['empty_pages']}")
    print(f"[extract] {stats['vol']}: {stats['pages']}p, "
          f"{stats['total_chars']} chars, headers={stats['boiler_headers']}{extra}")


def cmd_reocr_queue(a):
    path, nq = build_reocr_queue()
    print(f"[reocr] wrote {path}: {nq} queued page(s)")


def cmd_render(a):
    manifest = load_manifest()
    if a.vol == "all":
        vols = [v[3] for v in born_digital_volumes() + scanned_volumes()]
    elif a.vol == "scanned":
        vols = [v[3] for v in scanned_volumes()]
    elif a.vol == "born-digital":
        vols = [v[3] for v in born_digital_volumes()]
    else:
        vols = [a.vol]
    for vol_id in vols:
        path, did = render(vol_id, manifest, force=a.force)
        print(f"[render] {vol_id}: {'wrote' if did else 'skip (exists)'} {path}")


def cmd_qc(a):
    vols = born_digital_volumes() if a.era == "born-digital" else scanned_volumes()
    if a.only:
        wanted = set(a.only)
        vols = [v for v in vols if v[3] in wanted]
    all_gates = []
    for ordn, year, fn, vol_id in vols:
        rows = read_jsonl(vol_id)
        if rows is None:
            print(f"[qc] {vol_id}: NO JSONL")
            continue
        g = qc_gates(vol_id, ordn, fn, rows)
        fails = gate_failures(g)
        g["fails"] = fails
        all_gates.append(g)
        status = "OK" if not fails else "FAIL"
        print(f"[qc:{status}] {vol_id} pages={g['pages']} tok_surv={g['token_survival']:.3f} "
              f"({g['final_ga_items_mult']}/{g['base_ga_items']}) content_parity={g['content_parity']:.3f} "
              f"char_parity={g['char_parity']:.3f} md={g['md_bytes']}B empty={g['empty_pages']}"
              + ("" if not fails else "  <<< " + "; ".join(fails)))
    if a.json:
        print(json.dumps(all_gates, indent=2))


def main():
    ap = argparse.ArgumentParser(
        description="Phase 1/2 extraction: born-digital (pymupdf4llm) + scanned (embedded OCR)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract")
    pe.add_argument("--era", default="born-digital", choices=["born-digital", "scanned"])
    pe.add_argument("--force", action="store_true")
    pe.add_argument("--only", nargs="*", help="vol ids e.g. ga14_1986 ga08_1980")
    pe.add_argument("--workers", type=int, default=3)
    pe.set_defaults(func=cmd_extract)

    pr = sub.add_parser("render")
    pr.add_argument("vol", help="vol id e.g. ga14_1986, or 'all' / 'scanned' / 'born-digital'")
    pr.add_argument("--force", action="store_true")
    pr.set_defaults(func=cmd_render)

    pq = sub.add_parser("qc")
    pq.add_argument("--era", default="born-digital", choices=["born-digital", "scanned"])
    pq.add_argument("--only", nargs="*")
    pq.add_argument("--json", action="store_true")
    pq.set_defaults(func=cmd_qc)

    prq = sub.add_parser("reocr-queue", help="(re)build build/reocr/reocr_queue.csv from jsonl")
    prq.set_defaults(func=cmd_reocr_queue)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
