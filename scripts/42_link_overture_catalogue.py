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
def main():
    if not (os.path.exists(CAT) and os.path.exists(MAP)):
        print(f"[{ROOT}] OVERTURES.md or map missing — skip"); return
    pmap = json.load(open(MAP))
    vol = None; linked = 0
    out = []
    for line in open(CAT).read().split("\n"):
        s = SEC.search(line)
        if line.startswith("## ") and s:
            vol = s.group(1)
        m = re.match(r"^\|\s*(?:\[(\d+)\]\([^)]+\)|(\d+))\s*\|", line)
        if m and vol:
            num = m.group(1) or m.group(2)
            cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
            page_refs = re.findall(r"\[p\.(\d+)\]\([^)]*#ga\d+-p(\d+)\)", cells[4]) if len(cells) == 5 else []
            source_page = int(page_refs[0][1]) if page_refs else None
            record_id = f"overture:{vol}:{num}:p{source_page}" if source_page else None
            page = pmap.get(record_id) if record_id else None
            if page:
                replacement = f"[{num}](../{page})"
                first_cell = m.group(0)
                line = line.replace(first_cell, f"| {replacement} |", 1)
                linked += 1
        out.append(line)
    open(CAT, "w").write("\n".join(out))
    print(f"[{ROOT}] linked {linked} overture-catalogue rows to their pages")

if __name__ == "__main__":
    main()
