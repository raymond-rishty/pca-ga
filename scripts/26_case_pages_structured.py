#!/usr/bin/env python3
"""
26_case_pages_structured.py — generate the LIVE cases/ pages from DOCUMENT STRUCTURE (via
25_case_extract) for the volumes that pass acceptance, replacing the old table-driven pages
(24_case_pages.py) for those volumes. Volumes that don't yet pass are left for the per-era profile
work and marked "extraction in progress" in CASES.md (this script writes no page for them).

A "passing" SJC volume = autotuned with junk==0, recall>=0.7, and >=3 blocks (per
index/sjc_strategy.json). Each structure block becomes one page (its full text incl. opinions),
titled from the cases table (authoritative identity). Emits:
  cases/<vol>__<nums>.md          one page per block
  index/case_pages_map.json       {normalized_number: {vol,file,numbers,title}} for CASES.md

CLI:  26_case_pages_structured.py
"""
from __future__ import annotations
import importlib.util, json, os, re

ROOT = "/workspace"
spec = importlib.util.spec_from_file_location("ce", f"{ROOT}/scripts/25_case_extract.py")
ce = importlib.util.module_from_spec(spec); spec.loader.exec_module(ce)

OUT = f"{ROOT}/cases"
_OPIN = re.compile(r"^\**\s*((?:CONCURRING|DISSENTING|MAJORITY|SEPARATE)\s+OPINION[^*\n]*|"
                   r"OPINION OF THE COURT|DECISION(?: ON [A-Z ]+)?)\s*\**\s*$", re.I)


def promote_opinions(s):
    return "\n".join((f"#### {_OPIN.match(ln.strip()).group(1).strip()}" if _OPIN.match(ln.strip()) else ln)
                     for ln in s.split("\n"))


def ordinal(n):
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def passing_volumes(cls):
    # A volume promotes when its autotuned extraction is CLEAN (no junk, no docket mega-block) AND
    # complete. Completeness is recall>=0.7 against the table OR — because the table's per-GA
    # ga_ordinal is noisy and inflates the recall denominator with mis-filed/reference cases — a
    # large clean extraction (>=15 real cases over >=8 blocks), which independently implies the
    # volume's docket was captured (verified on ga30: 20 substantial decision blocks, recall only
    # 0.69 purely from denominator inflation).
    s = json.load(open(f"{ROOT}/index/sjc_strategy.json"))
    out = {}
    for v, d in s.items():
        if not (d.get("junk") == 0 and d.get("overmerge", 9) <= 2 and d.get("blocks", 0) >= 3):
            continue
        if d.get("recall", 0) >= 0.7 or (d.get("real", 0) >= 15 and d.get("blocks", 0) >= 8):
            out[v] = cls[v]
    return out


def main():
    cls = json.load(open(f"{ROOT}/index/case_volume_class.json"))
    passing = passing_volumes(cls)
    os.makedirs(OUT, exist_ok=True)
    # clear any prior pages so cases/ contains ONLY verified structure pages
    for f in os.listdir(OUT):
        if f.endswith(".md"):
            os.remove(os.path.join(OUT, f))
    gtitles = ce.global_titles()
    pages_map = {}
    n = 0; dropped = 0
    for vol in sorted(passing):
        ga = cls[vol]["ga"]; year = int(cls[vol]["year"]); meta = ce.table_meta(ga)
        blocks = ce.extract_sjc(vol)
        # drop short, OLD blocks: a real case cited inside a later decision shows up as its own
        # header block (e.g. 1992-09b inside a 2025 opinion). A genuine decision is long; a citation
        # is short and its number predates this Assembly by years.
        kept = [b for b in blocks
                if not (len(b["text"]) < 1000 and all(int(x[:4]) < year - 5 for x in b["numbers"]))]
        dropped += len(blocks) - len(kept)
        # dedup by number-set slug: the same number can head two blocks (decision + cross-ref);
        # keep the longest (the real decision).
        best = {}
        for b in kept:
            key = "_".join(b["numbers"])
            if key not in best or b["chars"] > best[key]["chars"]:
                best[key] = b
        for b in best.values():
            nums = b["numbers"]; slug = f"{vol}__{'_'.join(nums)}"
            titles = [(meta[x]["title"] if meta.get(x) and meta[x]["title"] else gtitles.get(x, ""))
                      for x in nums]
            titles = [t for t in titles if t]
            title = " / ".join(dict.fromkeys(titles)) or b["parties"][:90] or "(untitled)"
            dispos = [meta[x]["disposition"] for x in nums if meta.get(x) and meta[x]["disposition"]]
            hdr = [f"**Court:** Standing Judicial Commission",
                   f"**Assembly:** {ordinal(ga)} ({year})"]
            if dispos:
                hdr.append(f"**Disposition:** {'; '.join(dict.fromkeys(dispos))}")
            body = promote_opinions(b["text"])
            page = [f"# {'/'.join(nums)} — {title}", "", "  ·  ".join(hdr), "",
                    f"*Source: [{vol} lines {b['lines'][0]}–{b['lines'][1]}](../markdown/{vol}.md)*",
                    "", "---", "", body, "", "---", "", "[← Judicial case index](../index/CASES.md)"]
            open(f"{OUT}/{slug}.md", "w").write("\n".join(page) + "\n")
            for x in nums:
                pages_map[x] = {"vol": vol, "file": slug, "numbers": nums, "title": title}
            n += 1
    json.dump(pages_map, open(f"{ROOT}/index/case_pages_map.json", "w"), indent=1)
    print(f"wrote {n} structure pages from {len(passing)} passing volumes "
          f"({len(pages_map)} case numbers mapped, {dropped} short/old cross-ref blocks dropped) "
          f"-> cases/ + index/case_pages_map.json")
    print("passing:", " ".join(sorted(passing)))


if __name__ == "__main__":
    main()
