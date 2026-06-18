#!/usr/bin/env python3
"""
hunt_read.py <case_number_raw> — print everything a hunt agent needs for ONE missing
case: its roster identity + locator, plus the full text of the top candidate pages
(a window around each), so the agent just reads and extracts. Keeps workflow args tiny.
"""
import json, sys

ROOT = "/workspace"
LOCATED = ROOT + "/index/hunt/located.jsonl"


def main():
    cn = sys.argv[1]
    row = None
    for l in open(LOCATED):
        r = json.loads(l)
        if r["case_number_raw"] == cn:
            row = r
            break
    if not row:
        print("NO_SUCH_CASE", cn)
        return
    print(f"CASE {cn} | {row['title']} | docket year {row['year']}")
    loc = row.get("locator")
    if loc:
        print(f"ROSTER LOCATOR: {loc['ga']}th GA minutes, printed pp.{loc['printed_page_start']}-"
              f"{loc['printed_page_end']} (printed page + small offset ~= pdf page)")
    if row.get("relink_case_id"):
        print(f"NOTE: may already be in our index as case_id {row['relink_case_id']}")
    seen = set()
    for c in (row.get("candidates") or [])[:3]:
        vol, pg = c["vol"], c["pdf_page"]
        lo, hi = pg - 1, pg + 7
        try:
            pages = {}
            for l in open(f"{ROOT}/build/page_jsonl/{vol}.pages.jsonl"):
                rr = json.loads(l)
                if lo <= rr["pdf_page"] <= hi:
                    pages[rr["pdf_page"]] = rr["text"]
        except FileNotFoundError:
            continue
        for p in sorted(pages):
            if (vol, p) in seen:
                continue
            seen.add((vol, p))
            print(f"\n===== {vol} pdf-p{p} =====\n{pages[p]}")


if __name__ == "__main__":
    main()
