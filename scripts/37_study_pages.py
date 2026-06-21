#!/usr/bin/env python3
"""37_study_pages.py — render one page per located study/position-paper document.

Per SPEC-STUDIES.md §1/§7: the document is the unit. Each page leads with the paper's identity,
a prominent deep link to the FULL verbatim report in the volume markdown (the report bodies are
long — 100s–15,000 lines — so they are linked, not transcribed), and an opening preview sliced
from the report. Recommendations/outcome slicing is a later (locate) pass.

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


def main():
    recs = json.load(open(os.path.join(IDX, "studies_located.json"), encoding="utf-8"))
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
                f"**Source:** PCA Historical Center (not in the GA minutes corpus)", "",
                f"📄 **[Read the full document at the PCA Historical Center →]({r['external_url']})**", "",
                "---", "",
                "*This position paper is not located in the digitized GA minutes corpus; the link "
                "above points to the verbatim copy hosted by the PCA Historical Center "
                "([Studies & Reports](https://www.pcahistory.org/pca/digest/studies/)).*", "",
                "[← Study reports](../index/STUDIES.md)", "",
            ]
            fn = f"{slugify(topic)}__pcahistory.md"
            open(os.path.join(OUT, fn), "w", encoding="utf-8").write("\n".join(body))
            page_map.append({**r, "topic": topic, "file": fn, "kind_label": kind})
            written += 1
            continue

        stem = r["vol"]
        lines = md_lines(stem)
        pp = r["printed_pages"]
        pages_str = (f"pp. {pp[0]}–{pp[-1]}" if len(pp) > 1 else f"p. {pp[0]}") if pp else \
            f"lines {r['line_start']}–{r['line_end']}"
        anchor = r["anchor_start"] or ""
        link = f"../markdown/{stem}.md#{anchor}" if anchor else f"../markdown/{stem}.md"

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
            "## Opening of the report",
            "",
            "> " + preview(lines, r["line_start"], r["line_end"]).replace("\n", "\n> "),
            "",
            "---",
            "",
            "*Recommendations and the General Assembly's disposition are captured in a later pass "
            "(SPEC-STUDIES.md §5–6). This page links the full verbatim report above.*",
            "",
            "[← Study reports](../index/STUDIES.md)",
            "",
        ]
        # disambiguate same-topic reprints within a volume by start page/line
        tag = (r["printed_pages"][0] if r["printed_pages"] else f"l{r['line_start']}")
        fn = f"{slugify(topic)}__ga{r['ga_ordinal']:02d}_{r['year']}_p{tag}.md"
        open(os.path.join(OUT, fn), "w", encoding="utf-8").write("\n".join(body))
        page_map.append({**r, "topic": topic, "file": fn, "kind_label": kind})
        written += 1
    json.dump(page_map, open(os.path.join(IDX, "studies_pages.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"wrote {written} study-report pages to {OUT}/ and index/studies_pages.json")


if __name__ == "__main__":
    main()
