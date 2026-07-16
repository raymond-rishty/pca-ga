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
import argparse, bisect, json, os, re, glob

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = DEFAULT_ROOT
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")

HEADING = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")
ANCHOR = re.compile(r'<a id="(ga\d+-p[0-9A-Za-z]+)"></a>')
PAGE_COMMENT = re.compile(r"<!-- PAGE ga=\d+ pdf_page=(\d+) printed_page=(\w+) -->")
APPENDIX = re.compile(r"\bAPPENDIX\s+[A-Z]{1,3}\b", re.I)
ROMAN_SECTION = re.compile(r"^[IVXLC]+\.\s")  # "IV. AD-INTERIM COMMITTEES"
# Non-document headings that terminate a paper span (supplemental administrative material)
STOP_HEADING = re.compile(
    r"\bRULES FOR ASSEMBLY OPERATIONS\b"
    r"|\bPART\s+[IVX]+\s+INDEX\b",
    re.I)

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
BARE_GENERIC_HEADING = re.compile(r"^(COMMITTEE|TO STUDY|THE GENERAL ASSEMBLY)$", re.I)
INCOMPLETE_HEADING_TAIL = re.compile(
    r"\b(AD[\s-]?INTERIM COMMITTEE|AD HOC COMMITTEE|COMMITTEE|TO STUDY|QUESTION OF|ON|OF)$",
    re.I)
ADMIN_BODY_SIGNAL = re.compile(
    r"\b(recommend(?:s|ed|ation)?|adopt(?:ed|ion)?|overture|resolution|amend(?:ed|ment)?|"
    r"therefore|conclusion|respectfully submitted)\b",
    re.I)



# --- repeatable PCAHC PDF → minutes locator workflow ---
WORD = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "have", "has", "had", "are", "was",
    "were", "not", "but", "you", "your", "our", "their", "shall", "will", "may", "page",
    "report", "committee", "assembly", "presbyterian", "church", "america", "general",
}
GA_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
GA_CITATION = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+General\s+Assembly\b", re.I)


def normalize_text(text: str) -> str:
    """Normalize OCR/markdown text for repeatable fuzzy matching."""
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def informative_words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text) if w.lower() not in STOPWORDS and len(w) >= 4]


def phrase_fingerprints(pdf_text: str, limit: int = 10) -> list[str]:
    """Extract stable phrase fingerprints from a PDF text artifact.

    The phrases are intentionally mid-length prose snippets: long enough to be distinctive in a
    GA volume, short enough to survive line wrapping and minor OCR punctuation differences.
    """
    cleaned = re.sub(r"\s+", " ", pdf_text.replace("\x0c", " ")).strip()
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    scored = []
    seen = set()
    for sent in sentences:
        sent = sent.strip(" -•\t\n")
        words = informative_words(sent)
        if not (8 <= len(words) <= 45):
            continue
        if re.search(r"copyright|pcahistory|www\.|http|presbyterian church in america", sent, re.I):
            continue
        phrase = " ".join(sent.split())
        norm = normalize_text(phrase)
        if norm in seen:
            continue
        seen.add(norm)
        rarity = len(set(words))
        scored.append((rarity, len(words), phrase))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [p for _rarity, _n, p in scored[:limit]]


def candidate_volumes(doc: dict, pdf_text: str) -> list[str]:
    """Choose candidate markdown/ga*.md volumes by year, title, GA citation, and filename hints."""
    metadata = " ".join(str(doc.get(k, "")) for k in ("title", "topic", "pcahistory_file", "match_notes"))
    years = {int(y) for y in GA_YEAR.findall(metadata + " " + pdf_text[:4000])}
    ordinals = {int(m.group(1)) for m in GA_CITATION.finditer(pdf_text[:8000] + " " + str(doc.get("match_notes", "")))}
    m = re.search(r"ga(\d{1,2})_(\d{4})", str(doc.get("pcahistory_file", "")), re.I)
    if m:
        ordinals.add(int(m.group(1))); years.add(int(m.group(2)))
    vols = []
    for path in sorted(glob.glob(os.path.join(MD, "ga*.md"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        vm = re.match(r"ga(\d+)_(\d+)", stem)
        ga, yr = (int(vm.group(1)), int(vm.group(2))) if vm else (None, None)
        if years or ordinals:
            if yr in years or ga in ordinals or (years and any(abs(yr - y) <= 1 for y in years)):
                vols.append(stem)
        else:
            vols.append(stem)
    return vols or [os.path.splitext(os.path.basename(p))[0] for p in sorted(glob.glob(os.path.join(MD, "ga*.md")))]


def normalized_line_index(lines: list[str]) -> tuple[str, list[int]]:
    """Return normalized volume text plus 0-based line start offsets in that text."""
    parts = []
    starts = []
    pos = 0
    for ln in lines:
        starts.append(pos)
        part = normalize_text(ln)
        parts.append(part)
        pos += len(part) + 1
    return " ".join(parts), starts


def locate_phrase_in_text(norm_text: str, line_starts: list[int], phrase: str) -> int | None:
    """Locate a normalized PDF phrase in normalized minutes text and return a 1-based line."""
    needle_words = normalize_text(phrase).split()
    if len(set(needle_words)) < 6:
        return None
    needle = " ".join(needle_words)
    pos = norm_text.find(needle)
    if pos == -1:
        return None
    return bisect.bisect_right(line_starts, pos)


def propose_range_from_hits(lines: list[str], hits: list[int]) -> tuple[int, int]:
    """Return a minutes-only line range around fingerprint hits, expanded to nearby headings."""
    a, b = max(1, min(hits)), min(len(lines), max(hits))
    for i in range(a, 0, -1):
        if HEADING.match(lines[i - 1]) or ANCHOR.search(lines[i - 1]):
            a = i
            break
    for i in range(b + 1, len(lines) + 1):
        if i > b + 25 and (HEADING.match(lines[i - 1]) or re.match(r"^\s*\d{1,2}-\d+\b", lines[i - 1])):
            b = i - 1
            break
    return a, max(a, b)


def locate_pdf_manifest(root: str, refresh_existing: bool = False) -> None:
    """Update index/studies_pdf_manifest.json with repeatable PDF-text fingerprints and ranges.

    PDF text is used only as locator/audit material. Proposed ranges always point into
    markdown/ga*.md minutes volumes; generated study pages consume those slices via
    full_text_sources rather than copying from the PDF text artifact.
    """
    global ROOT, MD, IDX
    ROOT = root
    MD = os.path.join(ROOT, "markdown")
    IDX = os.path.join(ROOT, "index")
    manifest_path = os.path.join(IDX, "studies_pdf_manifest.json")
    blob = json.load(open(manifest_path, encoding="utf-8"))
    for doc in blob.get("documents", []):
        artifact = doc.get("pdf_text_artifact")
        if not artifact:
            continue
        artifact_path = os.path.join(ROOT, artifact)
        if not os.path.exists(artifact_path):
            continue
        pdf_text = open(artifact_path, encoding="utf-8", errors="ignore").read()
        fps = phrase_fingerprints(pdf_text)
        doc["fingerprints"] = fps
        if doc.get("ranges") and not refresh_existing:
            doc["locator_status"] = "existing_mapping_preserved"
            doc["provenance_class"] = "pcahistory_mapped_to_minutes"
            continue
        best = None
        for vol in candidate_volumes(doc, pdf_text):
            path = os.path.join(MD, vol + ".md")
            if not os.path.exists(path):
                continue
            lines = open(path, encoding="utf-8").read().split("\n")
            norm_text, line_starts = normalized_line_index(lines)
            hits = [(fp, locate_phrase_in_text(norm_text, line_starts, fp)) for fp in fps]
            hits = [(fp, lno) for fp, lno in hits if lno]
            title_words = set(informative_words(doc.get("title", "")))
            title_score = 0
            if title_words:
                head_text = "\n".join(lines[:1200]).lower()
                title_score = sum(1 for w in title_words if w in head_text)
            score = len(hits) * 10 + title_score
            if hits and (best is None or score > best[0]):
                best = (score, vol, lines, hits)
        if best and len(best[3]) >= 2:
            _score, vol, lines, hits = best
            a, b = propose_range_from_hits(lines, [lno for _fp, lno in hits])
            confidence = "high" if len(hits) >= 4 else "medium"
            doc["status"] = "mapped"
            doc["match_confidence"] = confidence
            doc["ranges"] = [{
                "vol": vol, "line_start": a, "line_end": b,
                "label": f"{vol} lines {a}–{b}",
                "match_method": "repeatable pdf fingerprint locator",
                "match_confidence": confidence,
                "fingerprints": [fp for fp, _lno in hits[:8]],
            }]
            doc["match_notes"] = (
                f"Repeatable locator matched {len(hits)} PDF-text fingerprint phrase(s) in "
                f"markdown/{vol}.md and proposed minutes-only range {a}-{b}. "
                "PDF text remains an audit artifact only."
            )
        elif fps:
            doc.setdefault("ranges", [])
            doc["status"] = "pdf_only"
            doc["match_confidence"] = doc.get("match_confidence") or "low"
            no_match_note = "Repeatable locator found no reliable minutes range; PDF text remains audit-only."
            existing_notes = doc.get("match_notes", "")
            if no_match_note not in existing_notes:
                doc["match_notes"] = (existing_notes + " " + no_match_note).strip()
        doc["provenance_class"] = (
            "pcahistory_mapped_to_minutes"
            if doc.get("status") == "mapped" and doc.get("ranges")
            else "pcahistory_pdf_only"
        )
    blob["generated_from"] = "repeatable PDF fingerprint locator; PDF text audit-only"
    json.dump(blob, open(manifest_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"updated {manifest_path}")

def clean_heading(raw: str) -> str:
    """Strip markdown emphasis/markers from a heading's text for matching/display."""
    t = raw.replace("**", "").replace("__", "").replace("`", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def join_continued_heading(lines: list[str], start_idx: int, text: str, level: int) -> tuple[str, int]:
    """Join split markdown headings that together form one report title.

    Early minutes often OCR/render long titles as adjacent ``##`` lines.  If only the first
    physical line is classified, the downstream topic stripper can emit generic page titles such
    as ``COMMITTEE`` or ``TO STUDY``.  Keep the source span anchored to the first line while
    carrying the full logical heading text into classification/rendering.
    """
    parts = [text]
    j = start_idx + 1
    while j < len(lines):
        hm = HEADING.match(lines[j])
        if not hm or heading_level(lines[j]) != level:
            break
        nxt = clean_heading(hm.group(1))
        current = " ".join(parts)
        if (
            BARE_GENERIC_HEADING.match(nxt)
            or BARE_GENERIC_HEADING.match(current)
            or INCOMPLETE_HEADING_TAIL.search(current)
            or re.match(r"^(THE\s+)?PRESBYTERIAN CHURCH IN AMERICA$", nxt, re.I)
            or re.match(r"^TO THE \w+ GENERAL ASSEMBLY", nxt, re.I)
        ):
            parts.append(nxt)
            j += 1
            continue
        break
    return re.sub(r"\s+", " ", " ".join(parts)).strip(), j - start_idx - 1


def classify_doc(text: str, is_md_heading: bool):
    """Return the document kind for a candidate line, or None if it is not a position paper.

    `text` is the cleaned (emphasis-stripped) line; `is_md_heading` is True for `#`-headings
    (vs. whole-line-bold lead lines, which carry the pastoral letters / declarations)."""
    if ROMAN_SECTION.match(text):
        return None  # journal/section header
    if BARE_GENERIC_HEADING.match(text):
        return None  # incomplete split heading fragment, not a paper title by itself
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
    """Collect printed page values within [a, b], filtering pagination restarts.

    Appendices sometimes reset page numbering (e.g. appendix page 111 appears after
    journal page 176). Detect these by watching for a printed-page number that is
    numerically less than the previous one — skip those appendix-restart pages so the
    returned range stays within a single consistent pagination series."""
    out, prev_num = [], None
    for lno, _aid, pp in pages:
        if a <= lno <= b and pp:
            try:
                n = int(pp)
                if prev_num is not None and n < prev_num:
                    continue  # pagination restart (e.g. appendix page) — skip
                prev_num = n
            except ValueError:
                pass  # non-numeric (roman numerals etc.) — always include
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
    skip_to = 0
    for i, ln in enumerate(lines, 1):
        if i <= skip_to:
            continue
        hm = HEADING.match(ln)
        if hm:
            text = clean_heading(hm.group(1))
            text, consumed = join_continued_heading(lines, i - 1, text, heading_level(ln))
            skip_to = i + consumed
            headings.append((i, heading_level(ln), text, classify_doc(text, True),
                             is_appendix_heading(text), bool(STOP_HEADING.search(text))))
        elif WHOLE_BOLD.match(ln.strip()):
            text = clean_heading(ln)
            kind = classify_doc(text, False)
            if kind:  # only keep bold lines that are actually position documents
                headings.append((i, 7, text, kind, False, False))

    journal_resume = re.compile(rf"^\s*{ga_ordinal}-\d+\b") if ga_ordinal else None

    records = []
    for idx, (lno, level, text, kind, _is_app, _is_stop) in enumerate(headings):
        if not kind:
            continue
        # End = first of: next document, next appendix/stop heading, journal resume, EOF.
        end = len(lines)
        end_reason = "eof"
        for (lno2, _lv2, _t2, kind2, is_app2, is_stop2) in headings[idx + 1:]:
            if kind2 or is_app2 or is_stop2:
                end = lno2 - 1
                end_reason = "next_document" if kind2 else "next_appendix"
                break
        for j in range(lno, end):
            raw = lines[j] if j < len(lines) else ""
            if journal_resume and journal_resume.match(raw):
                if j < end:
                    end = j
                    end_reason = "journal_resume"
                break
            if STOP_HEADING.search(raw):
                if j < end:
                    end = j
                    end_reason = "next_appendix"
                break
        a_start = anchor_for_line(pages, lno)
        a_end = anchor_for_line(pages, end)
        pp = printed_pages_in_span(pages, lno, end)
        body = "\n".join(lines[lno:end])
        if end - lno + 1 < 30 and not ADMIN_BODY_SIGNAL.search(body):
            continue
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
            "provenance_class": "minutes_located",
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
    computed here so supplement and detected records are identical in shape.

    Entries with "override": true apply line_end / title corrections to already-detected records
    (keyed by vol + line_start) rather than adding a new record."""
    supp_path = os.path.join(IDX, "studies_supplement.json")
    if not os.path.exists(supp_path):
        return out
    existing_by_key = {(r["vol"], r["line_start"]): i for i, r in enumerate(out)}
    for s in json.load(open(supp_path, encoding="utf-8")):
        key = (s["vol"], s["line_start"])
        if key in existing_by_key:
            if s.get("override"):
                idx = existing_by_key[key]
                path = os.path.join(MD, s["vol"] + ".md")
                lines_v = open(path, encoding="utf-8").read().split("\n")
                pages_v = build_anchor_map(lines_v)
                a = out[idx]["line_start"]
                if "line_end" in s:
                    b = s["line_end"]
                    out[idx]["line_end"] = b
                    out[idx]["n_lines"] = b - a + 1
                    out[idx]["anchor_end"] = anchor_for_line(pages_v, b)
                    out[idx]["printed_pages"] = sorted(
                        printed_pages_in_span(pages_v, a, b),
                        key=lambda x: (len(x), x))
                if "title" in s:
                    out[idx]["title"] = s["title"]
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
            "printed_pages": sorted(printed_pages_in_span(pages, a, b), key=lambda x: (len(x), x)),
            "n_lines": b - a + 1, "is_minority": False,
            "end_reason": "supplement", "needs_locate": False, "source": "roster_supplement",
            "provenance_class": "minutes_located",
            "note": s.get("note", ""),
        })
    return out


def validate_pdf_manifest(blob: dict, manifest_path: str) -> None:
    """Validate the study-PDF manifest before merging it into generated records.

    The manifest is an auditable bridge between PCA Historical Center PDFs,
    extracted PDF text artifacts, and mapped GA-minutes ranges. Keep these
    checks close to the existing integration so bad manifest rows fail the
    generator before they can produce stale or misleading study pages.
    """
    errors = []
    required_doc_fields = (
        "pcahistory_file",
        "pcahistory_url",
        "status",
        "match_confidence",
        "pdf_text_artifact",
    )
    text_dir = os.path.abspath(os.path.join(IDX, "studies_pdf_text"))
    repo_root = os.path.abspath(ROOT)
    documents = blob.get("documents")
    if not isinstance(documents, list):
        errors.append("manifest must contain a documents list")
        documents = []

    for i, doc in enumerate(documents, 1):
        label = doc.get("pcahistory_file") or doc.get("title") or f"document #{i}"
        for field in required_doc_fields:
            if field not in doc:
                errors.append(f"{label}: missing required field {field}")

        artifact = doc.get("pdf_text_artifact")
        if not isinstance(artifact, str) or not artifact.strip():
            errors.append(f"{label}: pdf_text_artifact must be a non-empty string")
        else:
            artifact_path = os.path.abspath(os.path.join(ROOT, artifact))
            if os.path.isabs(artifact):
                errors.append(f"{label}: pdf_text_artifact must be repo-relative: {artifact}")
            elif os.path.commonpath([text_dir, artifact_path]) != text_dir:
                errors.append(f"{label}: pdf_text_artifact must live under index/studies_pdf_text/: {artifact}")
            elif not os.path.isfile(artifact_path):
                errors.append(f"{label}: missing pdf_text_artifact {artifact}")

        expected_provenance = (
            "pcahistory_mapped_to_minutes"
            if doc.get("status") == "mapped" and doc.get("ranges")
            else "pcahistory_pdf_only"
        )
        if doc.get("provenance_class") and doc.get("provenance_class") != expected_provenance:
            errors.append(
                f"{label}: provenance_class {doc.get('provenance_class')} does not match "
                f"status/ranges-derived {expected_provenance}")

        if doc.get("status") != "mapped":
            continue

        ranges = doc.get("ranges")
        if not isinstance(ranges, list) or not ranges:
            errors.append(f"{label}: mapped document must include at least one range")
            continue
        for j, source_range in enumerate(ranges, 1):
            rlabel = f"{label} range #{j}"
            for field in ("vol", "line_start", "line_end"):
                if field not in source_range:
                    errors.append(f"{rlabel}: missing required field {field}")
            vol = source_range.get("vol")
            line_start = source_range.get("line_start")
            line_end = source_range.get("line_end")
            if not isinstance(vol, str) or not vol.strip():
                errors.append(f"{rlabel}: vol must be a non-empty string")
                continue
            source_path = os.path.abspath(os.path.join(MD, vol + ".md"))
            if os.path.commonpath([repo_root, source_path]) != repo_root:
                errors.append(f"{rlabel}: vol escapes repository root: {vol}")
                continue
            if not os.path.isfile(source_path):
                errors.append(f"{rlabel}: missing source file markdown/{vol}.md")
                continue
            if not isinstance(line_start, int) or not isinstance(line_end, int):
                errors.append(f"{rlabel}: line_start and line_end must be integers")
                continue
            lines = open(source_path, encoding="utf-8").read().split("\n")
            if line_start < 1 or line_end < line_start or line_end > len(lines):
                errors.append(
                    f"{rlabel}: invalid line range {line_start}-{line_end} for markdown/{vol}.md "
                    f"with {len(lines)} lines")
                continue
            if not "\n".join(lines[line_start - 1:line_end]).strip():
                errors.append(f"{rlabel}: sliced source text is empty")

    if errors:
        joined = "\n  - ".join(errors)
        raise SystemExit(f"Invalid PDF manifest {manifest_path}:\n  - {joined}")

def load_pdf_manifest() -> dict[str, dict]:
    """Return PCA HC PDF manifest records keyed by pcahistory PDF filename.

    index/studies_pdf_manifest.json is the source of truth for PCA
    Historical Center PDF-to-minutes mappings. In particular, mapped
    ``ranges`` from this manifest are the only authoritative source for
    generated ``full_text_sources`` on pcahistory records.
    """
    p = os.path.join(IDX, "studies_pdf_manifest.json")
    if not os.path.exists(p):
        return {}
    blob = json.load(open(p, encoding="utf-8"))
    validate_pdf_manifest(blob, p)
    docs = {}
    for d in blob.get("documents", []):
        key = d.get("pcahistory_file")
        if key:
            docs[key] = d
    return docs


def merge_pcahistory(out):
    """Fold in PCA Historical Center documents, adding manifest metadata when available.

    ``index/studies_pdf_manifest.json`` is the source of truth for PCA Historical Center
    PDF-to-minutes mappings. The legacy ``studies_pcahistory.json`` list is only a roster
    of PCA HC PDFs that should appear in the generated study catalog; its embedded
    ``full_text_sources`` field, if ever present from older data, is a migration fallback
    used only when the manifest has no usable ranges for that PDF.
    """
    p = os.path.join(IDX, "studies_pcahistory.json")
    if not os.path.exists(p):
        return out
    blob = json.load(open(p, encoding="utf-8"))
    base = blob["base"]
    manifest = load_pdf_manifest()
    for d in blob["docs"]:
        rec = {
            "vol": "pcahistory", "ga_ordinal": None, "year": d.get("year"),
            "title": d["title"], "kind": d["kind"], "level": 0,
            "line_start": 0, "line_end": 0, "anchor_start": None, "anchor_end": None,
            "printed_pages": [], "n_lines": 0, "is_minority": False,
            "end_reason": "pcahistory", "needs_locate": False,
            "source": "pcahistory", "external_url": base + d["file"],
        }
        manifest_doc = manifest.get(d["file"], {})
        if manifest_doc:
            rec["pdf_manifest_status"] = manifest_doc.get("status")
            rec["pdf_match_confidence"] = manifest_doc.get("match_confidence")
            rec["pdf_match_notes"] = manifest_doc.get("match_notes")
            if manifest_doc.get("pdf_text_artifact"):
                rec["pdf_text_artifact"] = manifest_doc.get("pdf_text_artifact")
        manifest_status = manifest_doc.get("status") if manifest_doc else None
        manifest_ranges = manifest_doc.get("ranges") if manifest_doc else None

        # PCA Historical Center roster/PDF text is locator/fingerprint material by default.
        # Only an explicit, reliable manifest mapping promotes a roster PDF to minutes-derived
        # generated text. Unmapped PDFs remain external/PDF-only catalogue records.
        if manifest_status == "mapped" and manifest_ranges:
            rec["full_text_sources"] = manifest_ranges
            rec["provenance_class"] = "pcahistory_mapped_to_minutes"
        elif not manifest_doc and d.get("full_text_sources"):
            # Migration fallback only: keep old hand-maintained ranges usable for
            # pre-manifest entries, but never let them override (or silently repair)
            # the authoritative PDF manifest mappings.
            rec["full_text_sources"] = d["full_text_sources"]
            rec["provenance_class"] = "pcahistory_mapped_to_minutes"
        else:
            rec["provenance_class"] = "pcahistory_pdf_only"
        out.append(rec)
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
                    printed_pages_in_span(pages, rs[i]["line_start"], rs[i]["line_end"]),
                    key=lambda x: (len(x), x))
    return out


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=DEFAULT_ROOT)
    parser.add_argument("--locate-pdfs", action="store_true",
                        help=("Update index/studies_pdf_manifest.json by matching PDF text "
                              "fingerprints to markdown/ga*.md minutes ranges."))
    parser.add_argument("--refresh-existing-pdf-ranges", action="store_true",
                        help=("Allow --locate-pdfs to replace existing manifest ranges; by "
                              "default existing mappings are fingerprinted but preserved."))
    return parser.parse_args()


def main():
    global ROOT, MD, IDX
    args = parse_args()
    ROOT = args.root
    MD = os.path.join(ROOT, "markdown")
    IDX = os.path.join(ROOT, "index")
    if args.locate_pdfs:
        locate_pdf_manifest(ROOT, refresh_existing=args.refresh_existing_pdf_ranges)
        return
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
