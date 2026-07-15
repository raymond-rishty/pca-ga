#!/usr/bin/env python3
"""37_study_pages.py — render one page per located study/position-paper document.

Per SPEC-STUDIES.md §1/§7: the document is the unit. Each page leads with the paper's identity,
a prominent deep link to the FULL verbatim report in the volume markdown (the report bodies are
long — 100s–15,000 lines — so they are linked, not transcribed), and an opening preview sliced
from the report. If 40_study_outcomes.py has enriched the records already, recommendations and
outcome slices are rendered as structured source-backed sections.

Reads:   <ROOT>/index/studies_located.json   (from 36_study_extract.py)
         <ROOT>/markdown/ga*.md              (verbatim source for the preview slice)
Writes:  <ROOT>/studies/<slug>__ga<NN>_<year>.md   one page per document

This step deliberately does NOT build the catalogue index (index/STUDIES.md) — that is a later
projection over the record set (§7). Usage:  37_study_pages.py [ROOT]

Partial full-text sample generation example:
  python3 scripts/37_study_pages.py --full-text --only-provenance minutes_located --max-lines 250 \
    --only-file divorce__ga07_1979_p59.md \
    --only-file theonomy__ga07_1979_p196.md \
    --only-file freemasonry__ga16_1988_p508.md \
    --only-file a-pastoral-letter-concerning-the-experience-of-the-holy-spir__ga02_1974_p173.md \
    --only-file the-number-of-offices-in-the-church__ga04_1976_p207.md \
    --only-file ruling-elders-administering-the-sacraments__ga05_1977_p240.md \
    --only-file theology-of-stewardship__ga09_1981_p274.md \
    --only-file questions-relating-to-the-validity-of-certain-baptisms__ga13_1985_p349.md \
    --only-file church-state-subcommittee-report-summary-positions__ga15_1987_p431.md \
    --only-file domestic-violence-and-sexual-assault__ga48_2021_p868.md
"""
from __future__ import annotations
import argparse, json, os, re

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = DEFAULT_ROOT
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")
OUT = os.path.join(ROOT, "studies")

# strip the boilerplate framing of a report heading down to its topic
LEAD = re.compile(r"^(APPENDIX\s+[A-Z]{1,3}\s+)?(\d{4}\s+)?", re.I)
STRIP = re.compile(
    r"^(THE\s+)?(INITIAL\s+|FINAL\s+|MAJORITY\s+|MINORITY\s+|PRELIMINARY\s+)?"
    r"REPORT\s+(OF|TO|ON|BY)\s+"
    r"(THE\s+PCA\s+|THE\s+|PCA\s+)?(GENERAL\s+ASSEMBLY\s+OF\s+(THE\s+)?)?"
    r"(AD[\s-]?INTERIM\s+|AD\s+HOC\s+)*"
    r"(THEOLOGICAL\s+|STUDY\s+|SUB)?(COMMITTEE\s+)?"
    r"(TO\s+STUDY\s+AND\s+MAKE\s+RECOMMENDATIONS\s+AS\s+TO\s+|"
    r"TO\s+STUDY\s+(THE\s+QUESTION\s+OF\s+)?|ON\s+|TO\s+DISCUSS\s+|BY\s+THE\s+COMMITTEE\s+TO\s+STUDY\s+)?",
    re.I,
)
# trailing "... TO THE <ordinal|NN-th> GENERAL ASSEMBLY ..." and "OF THE PRESBYTERIAN CHURCH ..."
TAIL = re.compile(
    r"\s+TO\s+THE\s+([A-Z-]+|\d+\s*(ST|ND|RD|TH))\s+GENERAL ASSEMBLY.*$|"
    r"\s+OF\s+THE\s+PRESBYTERIAN\s+CHURCH.*$",
    re.I,
)


def ordinal(n: int) -> str:
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def topic_of(title: str) -> str:
    t = LEAD.sub("", title)
    t = TAIL.sub("", t)
    t = STRIP.sub("", t).strip(" .,:-")
    t = re.sub(r"\s+", " ", t)
    if len(t) >= 4:
        return t
    # topic trails the heading ("… BY THE COMMITTEE TO STUDY FREEMASONRY",
    # "… AD INTERIM COMMITTEE ON STRATEGIC PLANNING") — grab the tail after the last such marker
    m = re.search(r"(?:COMMITTEE\s+(?:TO\s+STUDY|ON)|TO\s+STUDY)\s+(.+)$", title, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" .,:-")
    return re.sub(r"\s+", " ", LEAD.sub("", title)).strip(" .,:-")


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s.lower()).strip("-")
    return s[:60] or "report"


def md_lines(stem: str) -> list[str]:
    return open(os.path.join(MD, stem + ".md"), encoding="utf-8").read().split("\n")


def source_slice(src: dict) -> str:
    """Return a 1-based inclusive line slice from a source markdown volume."""
    lines = md_lines(src["vol"])
    return "\n".join(lines[src["line_start"] - 1:src["line_end"]]).strip()


def full_text_sections(r: dict) -> list[str]:
    """Render ingested full-text sections for PCA HC PDF fallbacks when pinned."""
    sections = []
    for src in r.get("full_text_sources", []):
        label = src.get("label") or f"{src['vol']} lines {src['line_start']}–{src['line_end']}"
        anchor = ""
        for ln in md_lines(src["vol"])[src["line_start"] - 1:src["line_end"]]:
            m = re.search(r'<a id="([^"]+)"', ln)
            if m:
                anchor = m.group(1)
                break
        link = f"../markdown/{src['vol']}.md" + (f"#{anchor}" if anchor else "")
        sections += [f"### {label}", "", f"Source slice: [{src['vol']} lines {src['line_start']}–{src['line_end']}]({link}).", "", source_slice(src), ""]
    return sections


def quote_block(text: str) -> str:
    return "\n".join("> " + ln if ln else ">" for ln in text.split("\n"))


def preview(lines: list[str], a: int, b: int, n: int = 45) -> str:
    """First n meaningful body lines after the heading (skip anchors/page comments/blank)."""
    out = []
    for ln in lines[a:b]:  # a is heading line (1-based) → lines[a] is the line after it
        s = ln.strip()
        if not s or s.startswith("<a id=") or s.startswith("<!-- PAGE"):
            continue
        out.append(ln)
        if len(out) >= n:
            break
    return "\n".join(out).strip()


def outcome_sections(r: dict) -> list[str]:
    """Render recommendations/outcome data added by 40_study_outcomes.py, or a clear placeholder."""
    parts = []
    rec_excerpt = r.get("recommendations_excerpt")
    if rec_excerpt and r.get("recommendations_source"):
        src = r["recommendations_source"]
        anchor = src.get("anchor_start") or ""
        link = f"../markdown/{src['vol']}.md" + (f"#{anchor}" if anchor else "")
        parts += [
            "## Recommendations", "",
            f"Source: [{src['vol']} lines {src['line_start']}–{src['line_end']}]({link}).", "",
            "> " + rec_excerpt.replace("\n", "\n> "), "",
            "---", "",
        ]
    else:
        parts += ["## Recommendations", "", "*No recommendations slice has been located yet.*", "", "---", ""]

    classification = r.get("outcome_classification") or "no final action located"
    confidence = r.get("outcome_confidence")
    parts += ["## General Assembly outcome", "", f"**Classification:** {classification}"]
    if confidence is not None:
        parts.append(f"**Confidence:** {confidence}")
    parts.append("")
    if r.get("outcome_text") and r.get("outcome_source"):
        src = r["outcome_source"]
        anchor = src.get("anchor_start") or ""
        link = f"../markdown/{src['vol']}.md" + (f"#{anchor}" if anchor else "")
        parts += [
            f"Source: [{src['vol']} lines {src['line_start']}–{src['line_end']}]({link}).", "",
            "> " + r["outcome_text"].replace("\n", "\n> "), "",
        ]
    else:
        parts += ["*No final General Assembly action has been located yet.*", ""]
    return parts



def pdf_text_artifact_section(r: dict) -> list[str]:
    artifact = r.get("pdf_text_artifact")
    if not artifact:
        return []
    path = os.path.join(ROOT, artifact)
    if not os.path.exists(path):
        raise FileNotFoundError(f"missing PDF text artifact: {artifact}")
    text = open(path, encoding="utf-8").read().strip()
    # Keep page files readable: include the artifact provenance and an opening excerpt,
    # while linking the auditable full artifact for detailed review.
    lines = text.splitlines()
    excerpt = "\n".join(lines[:80]).strip()
    match_notes = r.get("pdf_match_notes")
    return [
        "## PDF text artifact", "",
        f"PDF-only extraction artifact: [`{artifact}`](../{artifact}).", "",
        "The document has not been mapped to a reliable local GA-minutes range, so this "
        "page does not present it as minutes-derived text. The excerpt below is from "
        "the auditable PDF text artifact.", "",
        *((["**Mapping note:** " + match_notes, ""] if match_notes else [])),
        "```text", excerpt, "```", "",
    ]

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=DEFAULT_ROOT)
    parser.add_argument("--full-text", action="store_true",
                        help="For selected minutes-located records, render the full source range instead of the opening preview.")
    parser.add_argument("--only-provenance",
                        help="Only render records whose provenance_class matches this value, e.g. minutes_located.")
    parser.add_argument("--max-lines", type=int,
                        help="Only render records whose source range is at most this many lines.")
    parser.add_argument("--only-file", action="append", default=[],
                        help="Only render matching output filenames or topic slugs. May be repeated.")
    parser.add_argument("--limit", type=int,
                        help="Stop after rendering this many selected records; useful for small audit batches.")
    return parser.parse_args()


def matches_only_file(r: dict, topic: str, fn: str, only_files: list[str]) -> bool:
    if not only_files:
        return True
    topic_slug = slugify(topic)
    candidates = {fn, os.path.splitext(fn)[0], topic_slug}
    return any(item in candidates for item in only_files)


def replace_report_text_section(existing: str, heading: str, text: str) -> str:
    marker = "\n---\n\n## Recommendations"
    marker_at = existing.find(marker)
    if marker_at == -1:
        return existing
    opening_at = existing.find("\n## Opening of the report\n")
    full_at = existing.find("\n## Full text\n")
    starts = [pos for pos in (opening_at, full_at) if pos != -1 and pos < marker_at]
    if not starts:
        return existing
    start = min(starts)
    replacement = f"\n{heading}\n\n{quote_block(text)}\n"
    return existing[:start] + replacement + existing[marker_at:]


def selected_by_args(r: dict, args, topic: str, fn: str) -> bool:
    if args.only_provenance and r.get("provenance_class") != args.only_provenance:
        return False
    if args.max_lines is not None and r.get("n_lines", 0) > args.max_lines:
        return False
    return matches_only_file(r, topic, fn, args.only_file)


def main():
    global ROOT, MD, IDX, OUT
    args = parse_args()
    ROOT = args.root
    MD = os.path.join(ROOT, "markdown")
    IDX = os.path.join(ROOT, "index")
    OUT = os.path.join(ROOT, "studies")
    recs = json.load(open(os.path.join(IDX, "studies_located.json"), encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    partial_batch = bool(args.only_provenance or args.max_lines is not None or args.only_file or args.limit is not None)
    if not partial_batch:
        for f in os.listdir(OUT):  # clear stale pages so a rerun reflects exactly the current record set
            if f.endswith(".md"):
                os.remove(os.path.join(OUT, f))
    written = 0
    page_map = []  # record → rendered file + derived topic, for the index projection (38)
    KIND_LABEL = {"report": "Study committee report", "pastoral_letter": "Pastoral letter",
                  "declaration": "Declaration of conscience", "statement": "Statement",
                  "message": "Message to all churches", "resolution": "Resolution",
                  "address": "Address to the Assembly"}
    for r in recs:
        topic = topic_of(r["title"])
        kind = "Minority report" if r["is_minority"] else KIND_LABEL.get(r.get("kind"), "Position paper")

        if r.get("external_url"):
            # roster-gap document not in the minutes corpus — link to its PCA Historical Center copy
            asm = f"{ordinal(r['ga_ordinal'])} ({r['year']})" if r.get("ga_ordinal") else \
                  (str(r["year"]) if r.get("year") else "—")
            body = [
                f"# {topic}", "",
                f"*{r['title']}*", "",
                f"**Type:** {kind}  ·  **Assembly:** {asm}  ·  "
                f"**Source:** PCA Historical Center PDF", "",
                f"📄 **[Original PDF at the PCA Historical Center →]({r['external_url']})**", "",
                "---", "",
            ]
            if r.get("full_text_sources"):
                body += [
                    "## Full text", "",
                    "*Mapped from the PCA Historical Center roster/PDF to corresponding GA-minutes "
                    "text. Page anchors and source line ranges are preserved below for auditability.*", "",
                ]
                body += full_text_sections(r)
            elif (r.get("pdf_manifest_status") == "pdf_only"
                  and r.get("provenance_class") == "pcahistory_pdf_only"
                  and not r.get("full_text_sources")
                  and r.get("pdf_text_artifact")):
                body += [
                    "## PDF-only notice", "",
                    "*This record is not minutes-derived: no reliable GA-minutes range has been "
                    "located for it. The PDF text below is shown only as an external PCA Historical "
                    "Center artifact, not as a full verbatim GA-minutes extraction.*", "",
                ]
                body += pdf_text_artifact_section(r)
            else:
                body += [
                    "*This position paper is not located in the digitized GA minutes corpus; the link "
                    "above points to the copy hosted by the PCA Historical Center "
                    "([Studies & Reports](https://www.pcahistory.org/pca/digest/studies/)).*", "",
                ]
            body += ["[← Study reports](../index/STUDIES.md)", ""]
            fn = f"{slugify(topic)}__pcahistory.md"
            if partial_batch and not selected_by_args(r, args, topic, fn):
                continue
            if args.limit is not None and written >= args.limit:
                continue
            open(os.path.join(OUT, fn), "w", encoding="utf-8").write("\n".join(body))
            page_map.append({**r, "topic": topic, "file": fn, "kind_label": kind})
            written += 1
            continue

        stem = r["vol"]
        lines = md_lines(stem)
        pp = r["printed_pages"]
        anchor = r["anchor_start"] or ""
        link = f"../markdown/{stem}.md#{anchor}" if anchor else f"../markdown/{stem}.md"
        # Extract the page number embedded in the anchor_start ID (e.g. "ga21-p174" → "174").
        # Use it as the true first page of the document; printed_pages may start one page later
        # if the anchor falls just before line_start, and may exclude appendix-restart pages.
        m_anch = re.search(r"-p(\w+)$", anchor) if anchor else None
        anchor_page = m_anch.group(1) if m_anch else None
        pp_full = ([anchor_page] + pp) if (anchor_page and (not pp or anchor_page != pp[0])) else pp
        pages_str = (f"pp. {pp_full[0]}–{pp_full[-1]}" if len(pp_full) > 1
                     else f"p. {pp_full[0]}") if pp_full else f"lines {r['line_start']}–{r['line_end']}"

        # Filename tag: prefer anchor_start page (stable, reflects actual start page) over
        # printed_pages[0] (which may be an appendix page or miss the first page of the span).
        tag = anchor_page if anchor_page else (pp[0] if pp else f"l{r['line_start']}")
        fn = f"{slugify(topic)}__ga{r['ga_ordinal']:02d}_{r['year']}_p{tag}.md"
        selected = selected_by_args(r, args, topic, fn)
        if partial_batch and not selected:
            continue
        if args.limit is not None and written >= args.limit:
            continue

        if args.full_text and selected:
            text_heading = "## Full text"
            text_body = source_slice(r)
        else:
            text_heading = "## Opening of the report"
            text_body = preview(lines, r["line_start"], r["line_end"])

        body = [
            f"# {topic}" + (" — minority report" if r["is_minority"] else ""),
            "",
            f"*{r['title']}*",
            "",
            f"**Type:** {kind}  ·  **Assembly:** {ordinal(r['ga_ordinal'])} ({r['year']})  ·  "
            f"**In the minutes:** {stem} {pages_str}",
            "",
            f"📄 **[Read the full report in the minutes →]({link})**  "
            f"({r['n_lines']:,} lines, {stem} {pages_str})",
            "",
            "---",
            "",
            text_heading,
            "",
            quote_block(text_body),
            "",
            "---",
            "",
            *outcome_sections(r),
            "[← Study reports](../index/STUDIES.md)",
            "",
        ]
        output_path = os.path.join(OUT, fn)
        page_text = "\n".join(body)
        if partial_batch and args.full_text and os.path.exists(output_path):
            existing = open(output_path, encoding="utf-8").read()
            page_text = replace_report_text_section(existing, text_heading, text_body)
        open(output_path, "w", encoding="utf-8").write(page_text)
        page_map.append({**r, "topic": topic, "file": fn, "kind_label": kind})
        written += 1
    if not partial_batch:
        json.dump(page_map, open(os.path.join(IDX, "studies_pages.json"), "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        print(f"wrote {written} study-report pages to {OUT}/ and index/studies_pages.json")
    else:
        print(f"wrote {written} selected study-report pages to {OUT}/; left unrelated pages and index/studies_pages.json untouched")
    if args.full_text:
        print("full-text audit:")
        for item in page_map:
            print(f"- {item['file']}: {item.get('vol')} lines {item.get('line_start')}–{item.get('line_end')}")


if __name__ == "__main__":
    main()
