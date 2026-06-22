#!/usr/bin/env python3
"""Link the OVERTURES.md catalogue's Overture-number cell to each overture's
individual page (overtures/<vol>__o<num>.md), where one exists — mirroring how
CASES.md links to case pages. The Pages column keeps its minutes deep-link.

Post-process (run AFTER 20_markdown_index.py, both trees) rather than baked into
the DB generator, so a re-render can't revert it and corpus text edits in the
catalogue aren't regenerated away. Idempotent.

Usage:  42_link_overture_catalogue.py [ROOT]
"""
import json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
CAT = os.path.join(ROOT, "index", "OVERTURES.md")
MAP = os.path.join(ROOT, "index", "overture_pages_map.json")

SEC = re.compile(r"`(ga\d+_\d+)`")
ROW = re.compile(r"^\| (\d+) \| ")          # data row: leftmost cell is the overture number

def main():
    if not (os.path.exists(CAT) and os.path.exists(MAP)):
        print(f"[{ROOT}] OVERTURES.md or map missing — skip"); return
    pmap = json.load(open(MAP))
    # (vol, num) -> "overtures/<file>.md"
    by_vol = {}
    for f in pmap.values():
        m = re.match(r"overtures/(ga\d+_\d+)__o(\d+)\.md$", f)
        if m:
            by_vol[(m.group(1), m.group(2))] = f

    vol = None; linked = 0
    out = []
    for line in open(CAT).read().split("\n"):
        s = SEC.search(line)
        if line.startswith("## ") and s:
            vol = s.group(1)
        m = ROW.match(line)
        if m and vol:
            num = m.group(1)
            page = by_vol.get((vol, num))
            if page:
                line = line.replace(f"| {num} | ", f"| [{num}](../{page}) | ", 1)
                linked += 1
        out.append(line)
    open(CAT, "w").write("\n".join(out))
    print(f"[{ROOT}] linked {linked} overture-catalogue rows to their pages")

if __name__ == "__main__":
    main()
