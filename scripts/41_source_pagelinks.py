#!/usr/bin/env python3
"""Rewrite case/inquiry page Source lines from LINE numbers to PDF PAGE numbers
+ a deep-link anchor to the section.  Self-consistent: the displayed page == the
anchor target (#ga<NN>-p<page>), so clicking the page number lands at that page.

Maps line spans -> pages via the markdown's own per-page anchors (<a id="ga50-pN">).
No regeneration (avoids the 26-29 header-corruption bug); pure line rewrite.
"""
import os, re, sys, bisect, glob

ROOT = sys.argv[1].rstrip("/")
SRC_RE = re.compile(r'^\*Source: \[(ga\d+_\d+) lines (.+?)\]\(\.\./markdown/\1\.md(?:#[\w-]+)?\)\*$')
ANCHOR_RE = re.compile(r'<a id="(ga\d+)-p(\d+)"')

_cache = {}
def anchors(vol):
    """sorted [(line_no, page)] for vol's markdown; line_no is 1-based."""
    if vol not in _cache:
        path = f"{ROOT}/markdown/{vol}.md"
        pts = []
        if os.path.exists(path):
            for i, line in enumerate(open(path), 1):
                m = ANCHOR_RE.search(line)
                if m:
                    pts.append((i, int(m.group(2))))
        _cache[vol] = pts
    return _cache[vol]

def line_to_page(vol, ln):
    pts = anchors(vol)
    if not pts:
        return None
    lines = [p[0] for p in pts]
    j = bisect.bisect_right(lines, ln) - 1   # largest anchor line <= ln
    if j < 0:
        j = 0
    return pts[j][1]

def rewrite(vol, spans_str):
    prefix = vol.split("_")[0]            # ga50_2023 -> ga50  (matches anchor ids)
    pages = []
    for span in spans_str.split(";"):
        span = span.strip()
        m = re.match(r'(\d+)[–\-](\d+)$', span)
        if not m:
            return None
        a = line_to_page(vol, int(m.group(1)))
        b = line_to_page(vol, int(m.group(2)))
        if a is None or b is None:
            return None
        pages += [a, b]
    if not pages:
        return None
    lo, hi = min(pages), max(pages)
    label = f"p. {lo}" if lo == hi else f"pp. {lo}–{hi}"
    return f"*Source: [{vol} {label}](../markdown/{vol}.md#{prefix}-p{lo})*"

def main():
    changed = unmatched = 0
    samples = []
    for d in ("cases", "inquiries"):
        for fp in glob.glob(f"{ROOT}/{d}/*.md"):
            txt = open(fp).read()
            out = []
            hit = False
            for line in txt.split("\n"):
                m = SRC_RE.match(line)
                if m:
                    new = rewrite(m.group(1), m.group(2))
                    if new and new != line:
                        if len(samples) < 4:
                            samples.append((os.path.basename(fp), line, new))
                        out.append(new); hit = True; continue
                    elif not new:
                        unmatched += 1
                out.append(line)
            if hit:
                open(fp, "w").write("\n".join(out))
                changed += 1
    print(f"[{ROOT}] rewrote {changed} pages, {unmatched} source lines unmapped")
    for f, a, b in samples:
        print(f"  {f}\n    - {a}\n    + {b}")

if __name__ == "__main__":
    main()
