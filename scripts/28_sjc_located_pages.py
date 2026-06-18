#!/usr/bin/env python3
"""
28_sjc_located_pages.py — render per-case pages for the SJC-era straggler volumes from
index/sjc_located.json (agent-LOCATED decision spans for the volumes the regex autotuner couldn't
segment cleanly). Like the CJB renderer, the agents only LOCATED line ranges; here we slice the
volume markdown VERBATIM and MERGE the pages into index/case_pages_map.json so CASES.md links them
through the existing SJC path. Run AFTER 26 (which clears cases/ and writes the regex-promoted SJC
pages) and 27 (CJB).

CLI:  28_sjc_located_pages.py
"""
from __future__ import annotations
import importlib.util, json, os, re

ROOT = "/workspace"
OUT = f"{ROOT}/cases"
spec = importlib.util.spec_from_file_location("ce", f"{ROOT}/scripts/25_case_extract.py")
ce = importlib.util.module_from_spec(spec); spec.loader.exec_module(ce)
_ANCHOR = re.compile(r'<a id="[^"]*"></a>\s*')
_OPIN = re.compile(r"^\**\s*((?:CONCURRING|DISSENTING|MAJORITY|SEPARATE)\s+OPINION[^*\n]*|"
                   r"OPINION OF THE COURT|DECISION(?: ON [A-Z ]+)?)\s*\**\s*$", re.I)


def ordinal(n):
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def render(lines, spans):
    parts = []
    for s in spans or []:
        if s and len(s) == 2 and 1 <= int(s[0]) <= int(s[1]):
            parts.append("\n".join(lines[int(s[0]) - 1:int(s[1])]))
    txt = _ANCHOR.sub("", "\n\n*— — —*\n\n".join(p for p in parts if p.strip())).strip()
    return "\n".join((f"#### {_OPIN.match(l.strip()).group(1).strip()}" if _OPIN.match(l.strip()) else l)
                     for l in txt.split("\n"))


def main():
    data = json.load(open(f"{ROOT}/index/sjc_located.json"))
    pmap = json.load(open(f"{ROOT}/index/case_pages_map.json")) if os.path.exists(f"{ROOT}/index/case_pages_map.json") else {}
    gt = ce.global_titles()
    n = 0
    for entry in data:
        vol = entry["vol"]; m = re.match(r"ga(\d+)_(\d+)", vol)
        ga, year = int(m.group(1)), m.group(2)
        meta = ce.table_meta(ga)
        lines = open(f"{ROOT}/markdown/{vol}.md").read().split("\n")
        for c in entry.get("cases", []):
            nums = [ce.norm_num(x) for x in c.get("numbers", []) if re.match(r"\d{2,4}-\d", x or "")]
            if not nums:
                continue
            body = render(lines, c.get("spans"))
            if len(body) < 120:
                continue
            slug = f"{vol}__{'_'.join(nums)}"
            # title: for a SINGLE case prefer the table's canonical "X v. Y"; for a CONSOLIDATED
            # decision prefer the agent's single clean parties string (joining N table titles is
            # messy, e.g. Hahn's four numbers) — the numbers themselves are already in the H1.
            tablet = next((meta[x]["title"] if meta.get(x) and meta[x]["title"] else gt.get(x, "")
                           for x in nums if (meta.get(x) and meta[x]["title"]) or gt.get(x)), "")
            parties = (c.get("parties") or "").strip()
            title = (tablet if len(nums) == 1 and tablet else (parties or tablet)) or "(untitled)"
            hdr = ["**Court:** Standing Judicial Commission", f"**Assembly:** {ordinal(ga)} ({year})"]
            if c.get("disposition"):
                hdr.append(f"**Disposition:** {c['disposition']}")
            if c.get("has_dissent"):
                hdr.append("**Dissent:** yes")
            spans = "; ".join(f"{s[0]}–{s[1]}" for s in c.get("spans", []) if len(s) == 2)
            page = [f"# {'/'.join(nums)} — {title}", "", "  ·  ".join(hdr), "",
                    f"*Source: [{vol} lines {spans}](../markdown/{vol}.md)*", "",
                    "---", "", body, "", "---", "", "[← Judicial case index](../index/CASES.md)"]
            open(f"{OUT}/{slug}.md", "w").write("\n".join(page) + "\n")
            for x in nums:
                pmap[x] = {"vol": vol, "file": slug, "numbers": nums, "title": title}
            n += 1

    # Cross-volume dedup over the FILES ON DISK (26 + 28 output): one case number can be rendered
    # from two volumes (its real decision AND a cross-reference in a later volume). Scan disk (not the
    # map, which only keeps the last writer per number and so hides the other file), keep per number
    # the LONGEST page (the real decision; cross-refs are short), delete the losers, and rebuild the
    # map — so cases/ has exactly one page per number and the index has no orphans.
    import glob
    title_of = {e["file"]: e.get("title", "") for e in pmap.values()}
    info = {}                                          # file -> (numbers, length, vol)
    for path in glob.glob(f"{OUT}/*.md"):
        f = os.path.basename(path)[:-3]
        tail = f.split("__", 1)[1] if "__" in f else ""
        nums = [x for x in tail.split("_") if re.match(r"\d{2,4}-\d", x)]
        if not nums:                                   # CJB "caseN" pages — handled separately
            continue
        info[f] = (nums, os.path.getsize(path), f.split("__")[0])
    home = {}
    for f, (nums, length, vol) in info.items():
        for num in nums:
            if num not in home or length > info[home[num]][1]:
                home[num] = f
    keep = set(home.values())
    removed = 0
    for f in info:
        if f not in keep:
            os.remove(f"{OUT}/{f}.md"); removed += 1
    pmap = {}
    for num, f in home.items():
        nums, _, vol = info[f]
        t = title_of.get(f, "")
        if not t and os.path.exists(f"{OUT}/{f}.md"):
            h1 = open(f"{OUT}/{f}.md").readline()
            t = h1.split(" — ", 1)[1].strip() if " — " in h1 else ""
        pmap[num] = {"vol": vol, "file": f, "numbers": nums, "title": t}
    json.dump(pmap, open(f"{ROOT}/index/case_pages_map.json", "w"), indent=1)
    print(f"wrote {n} SJC-located straggler pages; deduped {removed} duplicate-number pages; "
          f"case_pages_map now {len(pmap)} numbers")


if __name__ == "__main__":
    main()
