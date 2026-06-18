#!/usr/bin/env python3
"""
27_cjb_pages.py — render per-case pages for the CJB era (GA1-18) from index/cjb_cases.json, the
agent-LOCATED case spans (complaint + §10-79 adjudication line ranges). The agents only LOCATED
ranges; here we slice the volume markdown VERBATIM by those ranges, so the page text is the real
minutes, never model-generated. A CJB case is usually split (complaint summary + a later commission
report), so a case has 1+ spans that we concatenate.

Emits:
  cases/<vol>__caseN.md       one page per located case (complaint + adjudication, verbatim)
  index/cjb_pages.json        [{vol, ga, year, file, number, parties, disposition, has_dissent}]

CLI:  27_cjb_pages.py
"""
from __future__ import annotations
import json, os, re

ROOT = "/workspace"
OUT = f"{ROOT}/cases"
_ANCHOR = re.compile(r'<a id="[^"]*"></a>\s*')


def ordinal(n):
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def slice_spans(lines, spans):
    parts = []
    for s in spans or []:
        if not s or len(s) != 2:
            continue
        a, b = int(s[0]), int(s[1])
        if a < 1 or b < a:
            continue
        parts.append("\n".join(lines[a - 1:b]))            # 1-based inclusive
    txt = "\n\n*— — —*\n\n".join(p for p in parts if p.strip())
    return _ANCHOR.sub("", txt).strip()


def main():
    data = json.load(open(f"{ROOT}/index/cjb_cases.json"))
    os.makedirs(OUT, exist_ok=True)
    pages = []
    n = 0
    for vol_entry in data:
        vol = vol_entry["vol"]
        m = re.match(r"ga(\d+)_(\d+)", vol)
        ga, year = int(m.group(1)), m.group(2)
        lines = open(f"{ROOT}/markdown/{vol}.md").read().split("\n")
        for i, c in enumerate(vol_entry.get("cases", []), 1):
            body = slice_spans(lines, c.get("spans"))
            if len(body) < 80:                              # nothing real located
                continue
            slug = f"{vol}__case{i}"
            num = (c.get("number") or "").strip()
            parties = (c.get("parties") or "").strip() or "(parties not given)"
            hdr = ["**Court:** Committee on Judicial Business (CJB)",
                   f"**Assembly:** {ordinal(ga)} ({year})"]
            if c.get("disposition"):
                hdr.append(f"**Disposition:** {c['disposition']}")
            if c.get("has_dissent"):
                hdr.append("**Dissent:** yes")
            title = f"# {num + ' — ' if num else ''}{parties}"
            spans = "; ".join(f"{s[0]}–{s[1]}" for s in c.get("spans", []) if len(s) == 2)
            page = [title, "", "  ·  ".join(hdr), "",
                    f"*Source: [{vol} lines {spans}](../markdown/{vol}.md)*", "",
                    "---", "", body, "", "---", "", "[← Judicial case index](../index/CASES.md)"]
            open(f"{OUT}/{slug}.md", "w").write("\n".join(page) + "\n")
            pages.append({"vol": vol, "ga": ga, "year": year, "file": slug, "number": num,
                          "parties": parties, "disposition": c.get("disposition", ""),
                          "has_dissent": bool(c.get("has_dissent"))})
            n += 1
    json.dump(pages, open(f"{ROOT}/index/cjb_pages.json", "w"), indent=1)
    print(f"wrote {n} CJB case pages -> cases/ + index/cjb_pages.json")


if __name__ == "__main__":
    main()
