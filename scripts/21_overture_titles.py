#!/usr/bin/env python3
"""
21_overture_titles.py — give each overture a short subject title (e.g. "Establish a theological
library at Ridge Haven"), so the catalogue answers "has the PCA considered X before?" by subject,
not just by number/presbytery.

  extract : pull each overture's body text from the rendered markdown (header -> next heading),
            keyed by (vol, number, pdf_page) to join the structure index / DB overtures.
            -> index/overture_bodies.jsonl   {vol, ga_ordinal, number, pdf_page, source, body}

Titles themselves are generated (by an LLM, from the body) into index/overture_titles.jsonl
  {vol, number, pdf_page, title}
which 19_export folds into the DB `overtures.title` column and 20_markdown_index renders as a
"Subject" column. Generation is decoupled from extraction so it can be batched/re-run cheaply.

CLI:  21_overture_titles.py extract
"""
from __future__ import annotations
import glob, json, os, re, sys

ROOT = "/workspace"
MD = os.path.join(ROOT, "markdown")
OUT = os.path.join(ROOT, "index", "overture_bodies.jsonl")

_HEAD = re.compile(r"^#{1,6}\s")
_OV = re.compile(r"^#{1,6}\s*Overture\s+(\d+)\b", re.I)
_PAGE = re.compile(r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\w+)")
_NOISE = re.compile(r"^\s*(<a id=|<!--\s*PAGE|#*\s*\d*\s*MINUTES OF THE GENERAL ASSE|JOURNAL OF THE)")


def extract():
    # agent-located true end lines for the over-long bodies (see overture-end-finder workflow):
    # {"<vol>__o<number>@<start_line>": <1-based end line>} — keyed by the occurrence's start line
    # because an overture number can recur in a volume (as filed + in a committee report).
    ends_path = os.path.join(ROOT, "index", "overture_body_ends.json")
    ENDS = json.load(open(ends_path)) if os.path.exists(ends_path) else {}
    recs = []
    for p in sorted(glob.glob(os.path.join(MD, "ga*_*.md"))):
        vol = os.path.basename(p).split(".")[0]
        ordn = int(re.match(r"ga(\d+)", vol).group(1))
        lines = open(p).read().split("\n")
        cur_page = None
        cur = None            # active overture being accumulated
        for i, ln in enumerate(lines, 1):
            mp = _PAGE.search(ln)
            if mp:
                cur_page = None if mp.group(1) in ("null", "None") else int(mp.group(1))
            mo = _OV.match(ln)
            if mo:                                   # start a new overture body
                if cur:
                    recs.append(cur)
                src = re.sub(r"^#{1,6}\s*Overture\s+\d+\b[.:,\s]*", "", ln).strip(" *_#")
                src = re.sub(r"(?i)^from\s+", "", src)
                num = int(mo.group(1))
                cur = {"vol": vol, "ga_ordinal": ordn, "number": num,
                       "pdf_page": cur_page, "source": src, "_lines": [],
                       "_end": ENDS.get(f"{vol}__o{num}@{i}")}
                continue
            if cur is not None:
                if _HEAD.match(ln):                  # next heading ends the body
                    recs.append(cur); cur = None
                elif not _NOISE.match(ln):
                    if cur["_end"] and i > cur["_end"]:   # past the agent-located true end
                        continue
                    cur["_lines"].append(ln)
        if cur:
            recs.append(cur)
    with open(OUT, "w") as f:
        for r in recs:
            had_end = r.pop("_end", None)
            body = re.sub(r"\s+", " ", " ".join(r.pop("_lines"))).strip()
            # A located true end is trusted (just a generous safety ceiling); otherwise bound runaway
            # over-extraction at 6000. Either way cut on a word boundary with an ellipsis, never
            # mid-word — and the full text is always one click away at the page's deep-link.
            cap = 12000 if had_end else 6000
            if len(body) > cap:
                body = body[:cap].rsplit(" ", 1)[0].rstrip(" ,;") + " …"
            r["body"] = body
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(recs)} overture bodies -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        extract()
    else:
        print(__doc__)
