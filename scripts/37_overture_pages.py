#!/usr/bin/env python3
"""37_overture_pages.py — render an individual page per overture, like cases/ + inquiries/.

Reads (from <ROOT>/index/):
  - overture_bodies.jsonl        : {vol, ga_ordinal, number, pdf_page, source, body}
  - overture_titles.jsonl        : {vol, number, pdf_page, title}
  - overture_dispositions.jsonl  : {vol, number, ..., disposition, final_disposition, ratified, bco, ratification_note}
  - overture_events.jsonl        : optional curated action histories keyed by (vol, number)

Writes, mirroring cases/* and inquiries/*:
  - <ROOT>/overtures/<vol>__o<number>.md   : one page per overture (metadata + verbatim body + deep-link to minutes)
  - <ROOT>/index/overture_pages_map.json   : "GA<ord> O<num>" -> "overtures/<vol>__o<number>.md"

An overture can be extracted at several pages (as filed + as reported); we keep the LONGEST body per
(vol, number) and skip empties.  The body is the verbatim slice already captured in overture_bodies;
this page only frames it and deep-links to the page in the volume minutes (the same anchor the
OVERTURES.md catalogue uses).

Usage:  37_overture_pages.py [ROOT]      (ROOT defaults to /workspace)
"""
from __future__ import annotations
import json, os, re, sys, glob
from html import escape
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_links import source_entries_for_record, source_front_matter

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
OUT = os.path.join(ROOT, "overtures")
MIN_BODY = 40   # skip near-empty extractions; the finding keeps its minutes link instead


_OPENER = (r"\*{0,2}(?:Whereas|"
           r"(?:Now,?\s+therefore,?\s+)?(?:Therefore,?\s+)?[Bb]e\s+it\s+(?:further\s+)?resolved|"
           r"Now,?\s+therefore|Resolved,|RESOLVED)\b")


def para_clauses(text: str) -> str:
    """Put each Whereas / resolution clause of an overture on its own paragraph (the bodies arrive as
    one run-on block). Breaks before each clause opener; clause connectors ("; and") stay at the end
    of the preceding clause, the way recital/resolution text reads."""
    text = re.sub(r"\s+(" + _OPENER + ")", r"\n\n\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def ordinal(n: int) -> str:
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def load_jsonl(name):
    p = os.path.join(IDX, name)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "*.md")):
        os.remove(f)

    titles = {(r["vol"], str(r["number"])): (r.get("title") or "").strip()
              for r in load_jsonl("overture_titles.jsonl")}
    disps = {(r["vol"], str(r["number"])): r for r in load_jsonl("overture_dispositions.jsonl")}
    events = {(r["vol"], str(r["number"])): r.get("events", [])
              for r in load_jsonl("overture_events.jsonl")}

    # Pick the best body per (vol, number): PREFER one that reads like an overture (has Whereas /
    # resolution language) over the longest, because an overture number can also appear in the
    # volume's table of contents or back-of-book INDEX — those entries are longer but are just page
    # references (e.g. ga33_2005 O15 matched both the real overture and a "PART V INDEX" listing).
    _OVERTUREY = re.compile(r"\b(whereas|be it (further )?resolved|therefore|resolved,?\s+that|now,?\s+therefore)\b", re.I)
    def _score(r):
        b = r.get("body") or ""
        return (1 if _OVERTUREY.search(b) else 0, len(b))
    best: dict[tuple, dict] = {}
    for r in load_jsonl("overture_bodies.jsonl"):
        key = (r["vol"], str(r["number"]))
        if key not in best or _score(r) > _score(best[key]):
            best[key] = r

    pages_map = {}
    n = skipped = 0
    for (vol, number), r in sorted(best.items()):
        body = (r.get("body") or "").strip()
        if len(body) < MIN_BODY:
            skipped += 1
            continue
        ga = r["ga_ordinal"]
        ym = re.search(r"_(\d{4})$", vol)
        year = ym.group(1) if ym else ""
        prefix = vol.split("_")[0]                      # ga51_2024 -> ga51 (anchor id)
        page = r.get("pdf_page")
        title = titles.get((vol, number)) or "(untitled overture)"
        source = (r.get("source") or "").strip()

        hdr = [f"**Assembly:** {ordinal(ga)} ({year})" if year else f"**Assembly:** {ordinal(ga)}"]
        if source:
            hdr.append(f"**Source:** {source}")
        d = disps.get((vol, number)) or {}
        disp = (d.get("final_disposition") or d.get("disposition") or "").strip()
        if disp:
            hdr.append(f"**Disposition:** {disp}")
        if d.get("ratified"):
            hdr.append("**Ratified**")
        bco = d.get("bco")
        bco = ", ".join(str(b) for b in bco) if isinstance(bco, list) else (str(bco).strip() if bco else "")
        if bco:
            hdr.append(f"**BCO:** {bco}")

        anchor = f"#{prefix}-p{page}" if page else ""
        src = (f"*Source: [{vol} p. {page}](../markdown/{vol}.md{anchor})*" if page
               else f"*Source: [{vol}](../markdown/{vol}.md)*")
        rn = d.get("ratification_note")
        ratnote = [f"> *{rn.strip()}*", ""] if (rn or "").strip() else []

        source_meta = source_front_matter(source_entries_for_record(
            Path(ROOT), "overture", f"{vol}:{number}", vol, int(page) if page else None
        ))
        # The helper's trailing blank line is useful at other insertion points, but
        # overture pages already add a blank after the heading metadata below.
        if source_meta and source_meta[-1] == "":
            source_meta = source_meta[:-1]
        page_md = source_meta + [f"# GA{ga} O{number} — {title}", "", "  ·  ".join(hdr), "", src, "", "---", ""]
        record_events = events.get((vol, number), [])
        if record_events:
            page_md += ratnote
            page_md += ["## Submitted overture", "", para_clauses(body), "",
                        "## Action history", ""]
            for event in record_events:
                heading = (event.get("heading") or "Overture action").strip()
                action_text = (event.get("action_text") or "").strip()
                source_volume = (event.get("source_volume") or vol).strip()
                source_page = event.get("source_pdf_page")
                source_label = event.get("source_label") or (
                    f"{source_volume} PDF p. {source_page}" if source_page else source_volume
                )
                source_match = re.search(r"ga(\d+)", source_volume)
                source_anchor = (f"#ga{int(source_match.group(1))}-p{source_page}"
                                 if source_page and source_match else "")
                page_md += [f'<h3 class="overture-action-heading">{escape(heading)}</h3>', ""]
                if action_text:
                    # Curated event text is transcribed from the cited minutes, rather than
                    # editorially summarized. Emit escaped HTML so Kramdown cannot reinterpret
                    # recorded paragraph numbering or lettered clauses as Markdown lists.
                    quoted = "<br>\n".join(escape(line) for line in action_text.splitlines())
                    page_md += ['<blockquote class="overture-action-text">', quoted,
                                "</blockquote>", ""]
                page_md += [f"*Source: [{source_label}](../markdown/{source_volume}.md{source_anchor})*", ""]
                related_page = (event.get("related_page") or "").strip()
                if related_page:
                    related_label = (event.get("related_label") or "Related overture").strip()
                    page_md += [f"*Related record: [{related_label}]({related_page})*", ""]
            page_md += ["---", "", "[← Overture catalogue](../index/OVERTURES.md)"]
        else:
            page_md += ratnote
            page_md += [para_clauses(body), "", "---", "", "[← Overture catalogue](../index/OVERTURES.md)"]
        slug = f"{vol}__o{number}"
        open(os.path.join(OUT, f"{slug}.md"), "w", encoding="utf-8").write("\n".join(page_md) + "\n")
        pages_map[f"GA{ga} O{number}"] = f"overtures/{slug}.md"
        n += 1

    json.dump(pages_map, open(os.path.join(IDX, "overture_pages_map.json"), "w"), indent=1)
    print(f"[{ROOT}] wrote {n} overture pages ({skipped} skipped: body < {MIN_BODY} chars) "
          f"-> overtures/ + index/overture_pages_map.json")


if __name__ == "__main__":
    main()
