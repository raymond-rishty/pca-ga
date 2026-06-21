#!/usr/bin/env python3
"""36_study_extract.py — locate ad-interim / study-committee report DOCUMENTS in the corpus.

Per SPEC-STUDIES.md §5 (step 1: detect & region the document). This is the first build step —
"grab the pages/reports before building the index". It does NOT build the index (that is a later
projection, §7); it produces the located-report dataset the pages and index are rendered from.

Reads:   <ROOT>/markdown/ga*.md          (the verbatim corpus; the only content source)
Writes:  <ROOT>/index/studies_located.json   one record per located report document:
         {vol, ga_ordinal, year, title, level, line_start, line_end, anchor_start, anchor_end,
          printed_pages:[...], n_lines, is_minority, end_reason}

Detection is heading-based (the report headings, §2/§3), guarded against the three non-document
forms the corpus shows: roman-numeral journal/section headers ("IV. AD-INTERIM COMMITTEES"),
Part-I committee-directory member lists (bare "AD-INTERIM COMMITTEE TO STUDY X", no "REPORT"),
and communications addressed *to* a committee ("TO THE AD INTERIM COMMITTEE ON X").

Bounding: a report runs from its heading to the first of — the next report heading, the next
"APPENDIX <Letter>" heading, or the journal resuming (`^<ga_ordinal>-N`) — else EOF.

Usage:  36_study_extract.py [ROOT]      (ROOT defaults to the repo root containing markdown/)
"""
from __future__ import annotations
import json, os, re, sys, glob

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")

HEADING = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")
ANCHOR = re.compile(r'<a id="(ga\d+-p[0-9A-Za-z]+)"></a>')
PAGE_COMMENT = re.compile(r"<!-- PAGE ga=\d+ pdf_page=(\d+) printed_page=(\w+) -->")
APPENDIX = re.compile(r"\bAPPENDIX\s+[A-Z]{1,3}\b")
ROMAN_SECTION = re.compile(r"^[IVXLC]+\.\s")  # "IV. AD-INTERIM COMMITTEES"

# --- document KINDS (SPEC-STUDIES.md §1: position papers include pastoral letters / declarations /
# statements / messages absent a study committee, not only ad-interim committee reports) ---
STUDY_MARKER = re.compile(r"AD[\s-]?INTERIM|STUDY COMMITTEE|COMMITTEE TO STUDY|AD HOC COMMITTEE", re.I)
REPORT_WORD = re.compile(r"\bREPORT\b", re.I)
MINORITY = re.compile(r"M\s*I\s*N\s*O\s*R\s*I\s*T\s*Y\s+R\s*E\s*P\s*O\s*R\s*T", re.I)  # OCR space-tolerant
JOURNAL_HEADING = re.compile(r"^\d+-\d+\b")  # "13-28 Report of …" = a GA action paragraph, not the document

# anchored at line start (title form) so section sub-headings and prose mentioning the phrase
# mid-sentence are not mistaken for a new document
PASTORAL = re.compile(r"^(A\s+|THE\s+)?PASTORAL LETTER\b", re.I)
DECLARATION = re.compile(r"^(A\s+|THE\s+)?DECLARATION OF CONSCIENCE\b", re.I)
STATEMENT = re.compile(r"^(A\s+|THE\s+)?STATEMENT OF CONSCIENCE\b", re.I)
MESSAGE = re.compile(r"^(A\s+)?MESSAGE TO ALL (THE )?CHURCHES\b", re.I)
RESOLUTION = re.compile(r"^RESOLUTION\s+(ON|REGARDING|CONCERNING)\b", re.I)
# whole-line bold (born-digital splits emphasis per word: "**A** **DECLARATION** …")
WHOLE_BOLD = re.compile(r"^(\*\*[^*]*\*\*\s*)+$")
# a bold-lead report candidate must look like a title (start with one of these), not prose
REPORT_TITLE_START = re.compile(
    r"^(APPENDIX\s+[A-Z]{1,3}\s+)?(THE\s+|A\s+)?(\d{4}\s+)?"
    r"(INITIAL|FINAL|MAJORITY|MINORITY|PRELIMINARY|REPORT|STUDY COMMITTEE|AD[\s-]?INTERIM|AD HOC)\b", re.I)


def clean_heading(raw: str) -> str:
    """Strip markdown emphasis/markers from a heading's text for matching/display."""
    t = raw.replace("**", "").replace("__", "").replace("`", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def classify_doc(text: str, is_md_heading: bool):
    """Return the document kind for a candidate line, or None if it is not a position paper.

    `text` is the cleaned (emphasis-stripped) line; `is_md_heading` is True for `#`-headings
    (vs. whole-line-bold lead lines, which carry the pastoral letters / declarations)."""
    if ROMAN_SECTION.match(text):
        return None  # journal/section header
    if JOURNAL_HEADING.match(text):
        return None  # "<ga>-NN …" — a GA action paragraph (the outcome, §6), not the paper
    if re.match(r"^\d+\.\s", text):
        return None  # "1. The Structure of …" — a numbered sub-item/recommendation, not a document title
    # committee reports (heading or bold lead)
    if STUDY_MARKER.search(text) and REPORT_WORD.search(text):
        if re.match(r"^TO THE AD[\s-]?INTERIM", text, re.I):
            return None  # a communication addressed to the committee
        if re.search(r"APPOINTMENT AND FINANCING|REASONS FOR RECORDING A NEGATIVE VOTE", text, re.I):
            return None
        if re.search(r"\b(will|shall|was|were|to be)\s+(report|submitted|recommitted|presented)", text, re.I):
            return None  # prose about a report ("…will report to the 35th GA"), not a report title
        # bold-lead candidates must be TITLE-form (markdown headings are trusted as-is) so prose
        # lines like "This report was recommitted …" / "NOTE: The Study Committee adopted …" are not docs
        if not is_md_heading and not REPORT_TITLE_START.match(text):
            return None
        return "report"
    # pastoral letters / declarations / statements / messages — distinctive enough on the keyword
    if PASTORAL.search(text):
        return "pastoral_letter"
    if DECLARATION.search(text):
        return "declaration"
    if STATEMENT.search(text):
        return "statement"
    if MESSAGE.search(text):
        return "message"
    # position resolutions: only as a `#` heading (floor-action resolutions are inline NN-NN paras)
    if is_md_heading and RESOLUTION.match(text):
        return "resolution"
    return None


def heading_level(line: str) -> int:
    m = re.match(r"^\s*(#{1,6})\s", line)
    return len(m.group(1)) if m else 0


def is_appendix_heading(text: str) -> bool:
    return bool(APPENDIX.search(text))


def build_anchor_map(lines: list[str]):
    """Return a list of (line_no, anchor_id, printed_page) for each page marker, in order."""
    pages = []
    for i, ln in enumerate(lines, 1):
        m = ANCHOR.search(ln)
        if m:
            pages.append([i, m.group(1), None])
    # attach printed page from the following PAGE comment when present
    for j, (lno, _aid, _pp) in enumerate(pages):
        for k in range(lno, min(lno + 2, len(lines))):
            pc = PAGE_COMMENT.search(lines[k] if k < len(lines) else "")
            if pc:
                pages[j][2] = None if pc.group(2) == "null" else pc.group(2)
                break
    return pages


def anchor_for_line(pages, line_no: str):
    """Nearest preceding <a id> for a 1-based line number."""
    best = None
    for lno, aid, _pp in pages:
        if lno <= line_no:
            best = aid
        else:
            break
    return best


def printed_pages_in_span(pages, a: int, b: int):
    out = []
    for lno, _aid, pp in pages:
        if a <= lno <= b and pp:
            out.append(pp)
    return out


def extract_volume(path: str):
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"ga(\d+)_(\d+)", stem)
    ga_ordinal, year = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    lines = open(path, encoding="utf-8").read().split("\n")
    pages = build_anchor_map(lines)

    # Pass 1: candidate document headings — `#` headings AND whole-line-bold lead lines (the
    # pastoral letters / declarations are bold, not `#`). Each carries its kind (None = not a doc).
    headings = []  # (line_no, level, text, kind, is_appendix)
    for i, ln in enumerate(lines, 1):
        hm = HEADING.match(ln)
        if hm:
            text = clean_heading(hm.group(1))
            headings.append((i, heading_level(ln), text, classify_doc(text, True), is_appendix_heading(text)))
        elif WHOLE_BOLD.match(ln.strip()):
            text = clean_heading(ln)
            kind = classify_doc(text, False)
            if kind:  # only keep bold lines that are actually position documents
                headings.append((i, 7, text, kind, False))

    journal_resume = re.compile(rf"^\s*{ga_ordinal}-\d+\b") if ga_ordinal else None

    records = []
    for idx, (lno, level, text, kind, _is_app) in enumerate(headings):
        if not kind:
            continue
        # End = first of: next document, next appendix heading, journal resume, EOF.
        end = len(lines)
        end_reason = "eof"
        for (lno2, _lv2, _t2, kind2, is_app2) in headings[idx + 1:]:
            if kind2 or is_app2:
                end = lno2 - 1
                end_reason = "next_document" if kind2 else "next_appendix"
                break
        if journal_resume:
            for j in range(lno, end):
                if journal_resume.match(lines[j] if j < len(lines) else ""):
                    if j < end:
                        end = j
                        end_reason = "journal_resume"
                    break
        a_start = anchor_for_line(pages, lno)
        a_end = anchor_for_line(pages, end)
        pp = printed_pages_in_span(pages, lno, end)
        records.append({
            "vol": stem, "ga_ordinal": ga_ordinal, "year": year,
            "title": text, "kind": kind, "level": level,
            "line_start": lno, "line_end": end,
            "anchor_start": a_start, "anchor_end": a_end,
            "printed_pages": sorted(set(pp), key=lambda x: (len(x), x)),
            "n_lines": end - lno + 1,
            "is_minority": bool(MINORITY.search(text)),
            "end_reason": end_reason,
            "needs_locate": (end - lno + 1) < 30,  # too thin to hold a report body — locate the text
        })

    # Dedup within a volume: same normalized title → keep the longest span.
    by_title = {}
    for r in records:
        key = re.sub(r"[^A-Z0-9 ]", "", r["title"].upper())
        if key not in by_title or r["n_lines"] > by_title[key]["n_lines"]:
            by_title[key] = r
    return list(by_title.values())


def merge_supplement(out):
    """Fold in curated, roster-located documents the heading sweep can't catch (OCR-mangled
    headings, bare-topic sections, floor resolutions) — the analogue of sjc_located.json.
    Each supplement entry gives {vol, title, kind, line_start, line_end}; anchors/pages are
    computed here so supplement and detected records are identical in shape."""
    supp_path = os.path.join(IDX, "studies_supplement.json")
    if not os.path.exists(supp_path):
        return out
    existing = {(r["vol"], r["line_start"]) for r in out}
    for s in json.load(open(supp_path, encoding="utf-8")):
        if (s["vol"], s["line_start"]) in existing:
            continue
        lines = open(os.path.join(MD, s["vol"] + ".md"), encoding="utf-8").read().split("\n")
        pages = build_anchor_map(lines)
        a, b = s["line_start"], s["line_end"]
        m = re.match(r"ga(\d+)_(\d+)", s["vol"])
        out.append({
            "vol": s["vol"], "ga_ordinal": int(m.group(1)), "year": int(m.group(2)),
            "title": s["title"], "kind": s["kind"], "level": 0,
            "line_start": a, "line_end": b,
            "anchor_start": anchor_for_line(pages, a), "anchor_end": anchor_for_line(pages, b),
            "printed_pages": sorted({p for ln, _ai, p in pages if a <= ln <= b and p}, key=lambda x: (len(x), x)),
            "n_lines": b - a + 1, "is_minority": False,
            "end_reason": "supplement", "needs_locate": False, "source": "roster_supplement",
            "note": s.get("note", ""),
        })
    return out


def merge_pcahistory(out):
    """Fold in roster-gap documents that aren't in the minutes corpus, linked to their PCA
    Historical Center copies. These carry an external_url and NO minutes anchor — they are tagged
    source=pcahistory and labeled (the verbatim text lives at pcahistory, not the minutes)."""
    p = os.path.join(IDX, "studies_pcahistory.json")
    if not os.path.exists(p):
        return out
    blob = json.load(open(p, encoding="utf-8"))
    base = blob["base"]
    for d in blob["docs"]:
        out.append({
            "vol": "pcahistory", "ga_ordinal": None, "year": d.get("year"),
            "title": d["title"], "kind": d["kind"], "level": 0,
            "line_start": 0, "line_end": 0, "anchor_start": None, "anchor_end": None,
            "printed_pages": [], "n_lines": 0, "is_minority": False,
            "end_reason": "pcahistory", "needs_locate": False,
            "source": "pcahistory", "external_url": base + d["file"],
        })
    return out


def clamp_overlaps(out):
    """No record's span may swallow a later-starting catalogued document in the same volume
    (e.g. a long appendix report whose end-bound runs over a nested position paper). Clamp the
    earlier record's end to just before the next one's start and recompute its derived fields, so
    spans/page-counts stay honest. Deep links are unaffected (each keeps its own start anchor)."""
    from collections import defaultdict
    byv = defaultdict(list)
    for r in out:
        if r["vol"] != "pcahistory" and r.get("line_start"):
            byv[r["vol"]].append(r)
    for vol, rs in byv.items():
        rs.sort(key=lambda r: r["line_start"])
        lines = open(os.path.join(MD, vol + ".md"), encoding="utf-8").read().split("\n")
        pages = build_anchor_map(lines)
        for i in range(len(rs) - 1):
            if rs[i]["line_end"] >= rs[i + 1]["line_start"]:
                rs[i]["line_end"] = rs[i + 1]["line_start"] - 1
                rs[i]["n_lines"] = rs[i]["line_end"] - rs[i]["line_start"] + 1
                rs[i]["anchor_end"] = anchor_for_line(pages, rs[i]["line_end"])
                rs[i]["printed_pages"] = sorted(
                    {p for ln, _a, p in pages if rs[i]["line_start"] <= ln <= rs[i]["line_end"] and p},
                    key=lambda x: (len(x), x))
    return out


def main():
    out = []
    for path in sorted(glob.glob(os.path.join(MD, "ga*.md"))):
        out.extend(extract_volume(path))
    out = merge_supplement(out)
    out = merge_pcahistory(out)
    out = clamp_overlaps(out)
    out.sort(key=lambda r: (r["ga_ordinal"] or 0, r["line_start"]))
    os.makedirs(IDX, exist_ok=True)
    dest = os.path.join(IDX, "studies_located.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"located {len(out)} documents across {len({r['vol'] for r in out})} volumes")
    print(f"wrote {dest}")
    from collections import Counter
    print("by kind:", dict(Counter(r["kind"] for r in out)))


if __name__ == "__main__":
    main()
