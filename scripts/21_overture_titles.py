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
_NOISE = re.compile(r"^\s*(<a id=|<!--\s*PAGE)")


def extract():
    recs = []
    for p in sorted(glob.glob(os.path.join(MD, "ga*_*.md"))):
        vol = os.path.basename(p).split(".")[0]
        ordn = int(re.match(r"ga(\d+)", vol).group(1))
        lines = open(p).read().split("\n")
        cur_page = None
        cur = None            # active overture being accumulated
        for ln in lines:
            mp = _PAGE.search(ln)
            if mp:
                cur_page = None if mp.group(1) in ("null", "None") else int(mp.group(1))
            mo = _OV.match(ln)
            if mo:                                   # start a new overture body
                if cur:
                    recs.append(cur)
                src = re.sub(r"^#{1,6}\s*Overture\s+\d+\b[.:,\s]*", "", ln).strip(" *_#")
                src = re.sub(r"(?i)^from\s+", "", src)
                cur = {"vol": vol, "ga_ordinal": ordn, "number": int(mo.group(1)),
                       "pdf_page": cur_page, "source": src, "_lines": []}
                continue
            if cur is not None:
                if _HEAD.match(ln):                  # next heading ends the body
                    recs.append(cur); cur = None
                elif not _NOISE.match(ln):
                    cur["_lines"].append(ln)
        if cur:
            recs.append(cur)
    with open(OUT, "w") as f:
        for r in recs:
            body = re.sub(r"\s+", " ", " ".join(r.pop("_lines"))).strip()
            r["body"] = body[:1600]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(recs)} overture bodies -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        extract()
    else:
        print(__doc__)
