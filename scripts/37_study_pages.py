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
"""
from __future__ import annotations
import json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def md_anchor_in_slice(src: dict) -> str:
    """Best available markdown anchor for a source slice."""
    if src.get("anchor_start"):
        return src["anchor_start"]
    vol = src.get("vol")
    if not vol or vol == "pcahistory":
        return ""
    try:
        for ln in md_lines(vol)[max(int(src.get("line_start", 1)) - 1, 0):int(src.get("line_end", 0))]:
            m = re.search(r'<a id="([^"]+)"', ln)
            if m:
                return m.group(1)
    except (FileNotFoundError, ValueError):
        return ""
    return ""


def page_range_label(pages: list[str] | None) -> str:
    pages = pages or []
    if not pages:
        return "printed page range unavailable"
    return f"printed pp. {pages[0]}–{pages[-1]}" if len(pages) > 1 else f"printed p. {pages[0]}"


def printed_pages_for_source(src: dict) -> list[str]:
    """Printed pages present inside a markdown source slice, when page comments expose them."""
    vol = src.get("vol")
    if not vol or vol == "pcahistory":
        return []
    pages = []
    anchor = src.get("anchor_start") or ""
    m_anchor = re.search(r"-p(\w+)$", anchor) if anchor else None
    if m_anchor:
        pages.append(m_anchor.group(1))
    try:
        source_lines = md_lines(vol)[max(int(src.get("line_start", 1)) - 1, 0):int(src.get("line_end", 0))]
    except (FileNotFoundError, ValueError):
        return []
    for ln in source_lines:
        m = re.search(r"printed_page=([^\s-]+)", ln)
        if m and m.group(1) != "null":
            pages.append(m.group(1))
    return sorted(set(pages), key=lambda x: (len(x), x))


def source_meta(src: dict, fallback_pages: list[str] | None = None) -> tuple[str, str]:
    """Return (markdown target, human metadata) for reproducible source-backed fields."""
    vol = src["vol"]
    anchor = md_anchor_in_slice(src)
    target = f"../markdown/{vol}.md" + (f"#{anchor}" if anchor else "")
    display = f"markdown/{vol}.md" + (f"#{anchor}" if anchor else "")
    pages = src.get("printed_pages") or printed_pages_for_source(src) or fallback_pages or []
    meta = f"{display}; lines {src['line_start']}–{src['line_end']}; {page_range_label(pages)}"
    return target, meta


def quote_block(text: str) -> str:
    return "> " + (text or "").replace("\n", "\n> ")


def digest_pdf_link(r: dict) -> str:
    return r.get("pcahistory_url") or r.get("external_url") or ""


def digest_pdf_section(r: dict) -> list[str]:
    url = digest_pdf_link(r)
    if not url:
        return []
    artifact = r.get("pdf_text_artifact")
    label = "PCA Historical Center digest PDF"
    parts = [f"📘 **[{label} →]({url})**"]
    if artifact:
        parts.append(f"PDF text artifact: [`{artifact}`](../{artifact}).")
    return parts + [""]


def recommendations_sections(r: dict) -> list[str]:
    """Render recommendations data added by 40_study_outcomes.py."""
    rec_excerpt = r.get("recommendations_excerpt")
    if rec_excerpt and r.get("recommendations_source"):
        src = r["recommendations_source"]
        link, meta = source_meta(src, r.get("printed_pages"))
        return [
            "## Recommendations", "",
            f"Source: [{meta}]({link}).", "",
            quote_block(rec_excerpt), "",
            "---", "",
        ]
    return ["## Recommendations", "", "*No recommendations slice has been located yet.*", "", "---", ""]


def disposition_sections(r: dict) -> list[str]:
    """Render the verbatim General Assembly disposition slice, if located."""
    if r.get("outcome_text") and r.get("outcome_source"):
        src = r["outcome_source"]
        link, meta = source_meta(src, r.get("printed_pages"))
        return [
            "## General Assembly disposition", "",
            f"Source: [{meta}]({link}).", "",
            quote_block(r["outcome_text"]), "",
            "---", "",
        ]
    return [
        "## General Assembly disposition", "",
        "*No final General Assembly disposition slice has been located yet.*", "",
        "---", "",
    ]


def outcome_classification_section(r: dict) -> list[str]:
    classification = r.get("outcome_classification") or "no final action located"
    confidence = r.get("outcome_confidence")
    parts = ["## Outcome classification", "", f"**Classification:** {classification}"]
    if confidence is not None:
        parts.append(f"**Confidence:** {confidence}")
    parts += ["", "---", ""]
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


def merge_digest_pdf_metadata(recs: list[dict]) -> None:
    """Retain PCA Historical Center digest PDF links on minutes-derived records."""
    manifest_path = os.path.join(IDX, "studies_pdf_manifest.json")
    if not os.path.exists(manifest_path):
        return
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    documents = manifest.get("documents", []) if isinstance(manifest, dict) else []
    by_range = {}
    by_title = {}
    for doc in documents:
        url = doc.get("pcahistory_url")
        if not url:
            continue
        for src in doc.get("ranges") or []:
            by_range[(src.get("vol"), src.get("line_start"), src.get("line_end"))] = doc
        for key in (doc.get("title"), doc.get("topic")):
            if key:
                by_title[re.sub(r"\s+", " ", key).strip().lower()] = doc
    for r in recs:
        doc = by_range.get((r.get("vol"), r.get("line_start"), r.get("line_end")))
        if not doc:
            doc = by_title.get(re.sub(r"\s+", " ", r.get("title", "")).strip().lower())
        if not doc:
            continue
        for src_key, dest_key in (("pcahistory_url", "pcahistory_url"),
                                  ("pcahistory_file", "pcahistory_file"),
                                  ("pdf_text_artifact", "pdf_text_artifact"),
                                  ("match_confidence", "pdf_match_confidence"),
                                  ("match_notes", "pdf_match_notes")):
            if doc.get(src_key) and not r.get(dest_key):
                r[dest_key] = doc[src_key]
        if doc.get("provenance_class") and not r.get("provenance_class"):
            r["provenance_class"] = doc["provenance_class"]


def main():
    recs = json.load(open(os.path.join(IDX, "studies_located.json"), encoding="utf-8"))
    # If 40_study_outcomes.py has already enriched studies_pages.json, preserve those
    # extracted recommendation/disposition fields when regenerating pages from located records.
    enriched_path = os.path.join(IDX, "studies_pages.json")
    if os.path.exists(enriched_path):
        enriched = json.load(open(enriched_path, encoding="utf-8"))
        keyed = {(r.get("vol"), r.get("line_start"), r.get("line_end"), r.get("title")): r for r in enriched}
        outcome_keys = {
            "recommendations_source", "recommendations_excerpt", "outcome_source",
            "outcome_text", "outcome_classification", "outcome_confidence",
            "roster_topic", "roster_paper_title", "pcahistory_url", "pcahistory_file",
            "pdf_text_artifact", "pdf_match_confidence", "pdf_match_notes",
        }
        for r in recs:
            old = keyed.get((r.get("vol"), r.get("line_start"), r.get("line_end"), r.get("title")))
            if old:
                for k in outcome_keys:
                    if k in old:
                        r[k] = old[k]
    merge_digest_pdf_metadata(recs)
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):  # clear stale pages so a rerun reflects exactly the current record set
        if f.endswith(".md"):
            os.remove(os.path.join(OUT, f))
    written = 0
    page_map = []  # record → rendered file + derived topic, for the index projection (38)
    KIND_LABEL = {"report": "Study committee report", "pastoral_letter": "Pastoral letter",
                  "declaration": "Declaration of conscience", "statement": "Statement",
                  "message": "Message to all churches", "resolution": "Resolution",
                  "address": "Address to the Assembly"}
    topics = {id(r): topic_of(r["title"]) for r in recs}
    related_by_topic = {}
    for r in recs:
        related_by_topic.setdefault(topics[id(r)].lower(), []).append(r)

    def related_sections(r: dict, current_file: str | None = None) -> list[str]:
        related = [x for x in related_by_topic.get(topics[id(r)].lower(), []) if x is not r]
        if not related:
            return []
        parts = ["## Related papers under this topic", ""]
        for x in sorted(related, key=lambda y: (y.get("year") or 9999, y.get("ga_ordinal") or 9999, y.get("title") or "")):
            label = f"{ordinal(x['ga_ordinal'])} ({x['year']})" if x.get("ga_ordinal") else (str(x.get("year")) if x.get("year") else "PCA Historical Center")
            # File names are deterministic and may be generated later in this same loop.
            x_anchor = x.get("anchor_start") or ""
            m = re.search(r"-p(\w+)$", x_anchor) if x_anchor else None
            tag = (m.group(1) if m else ((x.get("printed_pages") or [f"l{x.get('line_start', 0)}"])[0]))
            fn = f"{slugify(topics[id(x)])}__pcahistory.md" if x.get("external_url") else f"{slugify(topics[id(x)])}__ga{x['ga_ordinal']:02d}_{x['year']}_p{tag}.md"
            if fn == current_file:
                continue
            parts.append(f"- [{x.get('title')}]({fn}) — {label}")
        return parts + ([""] if len(parts) > 2 else [])

    for r in recs:
        topic = topics[id(r)]
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
            fn = f"{slugify(topic)}__pcahistory.md"
            body += related_sections(r, fn)
            body += ["[← Study reports](../index/STUDIES.md)", ""]
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
        full_src = {"vol": stem, "line_start": r["line_start"], "line_end": r["line_end"], "anchor_start": anchor, "printed_pages": pp_full}
        full_link, full_meta = source_meta(full_src, pp_full)
        preview_len = 45 if r["n_lines"] <= 250 else 20
        opening = preview(lines, r["line_start"], r["line_end"], n=preview_len)
        body = [
            f"# {topic}" + (" — minority report" if r["is_minority"] else ""),
            "",
            "## Identity metadata",
            "",
            f"- **Topic:** {topic}",
            f"- **Paper title:** {r['title']}",
            f"- **General Assembly / year:** {ordinal(r['ga_ordinal'])} General Assembly ({r['year']})",
            f"- **Provenance class:** {r.get('provenance_class') or 'minutes_located'}",
            f"- **Type:** {kind}",
            "",
            "---",
            "",
            "## Full report source",
            "",
            f"📄 **[Read the full report in the minutes →]({full_link})**",
            "",
            f"Source: [{full_meta}]({full_link}); {r['n_lines']:,} lines total.",
            "",
            *digest_pdf_section(r),
            "---",
            "",
            *recommendations_sections(r),
            *disposition_sections(r),
            *outcome_classification_section(r),
            "## Opening preview",
            "",
            quote_block(opening) if opening else "*No opening preview available.*",
            "",
            "---",
            "",
            *related_sections(r, fn),
            "[← Study reports](../index/STUDIES.md)",
            "",
        ]
        open(os.path.join(OUT, fn), "w", encoding="utf-8").write("\n".join(body))
        page_map.append({**r, "topic": topic, "file": fn, "kind_label": kind})
        written += 1
    json.dump(page_map, open(os.path.join(IDX, "studies_pages.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"wrote {written} study-report pages to {OUT}/ and index/studies_pages.json")


if __name__ == "__main__":
    main()
