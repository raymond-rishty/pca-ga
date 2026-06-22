#!/usr/bin/env python3
"""37_overture_pages.py — render an individual page per overture, like cases/ + inquiries/.

Reads (from <ROOT>/index/):
  - overture_bodies.jsonl        : {vol, ga_ordinal, number, pdf_page, source, body}
  - overture_titles.jsonl        : {vol, number, pdf_page, title}
  - overture_dispositions.jsonl  : {vol, number, ..., disposition, final_disposition, ratified, bco, ratification_note}

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

    # keep the longest body per (vol, number)
    best: dict[tuple, dict] = {}
    for r in load_jsonl("overture_bodies.jsonl"):
        key = (r["vol"], str(r["number"]))
        if key not in best or len(r.get("body") or "") > len(best[key].get("body") or ""):
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

        page_md = [f"# GA{ga} O{number} — {title}", "", "  ·  ".join(hdr), "", src, "", "---", ""]
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
