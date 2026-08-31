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
import importlib.util, json, os, re, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_links import line_to_pdf_page, source_entries_for_record, source_front_matter

ROOT = os.environ.get("PCA_GA_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("ce", f"{ROOT}/scripts/25_case_extract.py")
ce = importlib.util.module_from_spec(spec); spec.loader.exec_module(ce)

OUT = f"{ROOT}/cases"
TITLE_OVERRIDES = json.load(open(f"{ROOT}/index/case_title_overrides.json"))
_OPIN = re.compile(r"^\**\s*((?:CONCURRING|DISSENTING|MAJORITY|SEPARATE)\s+OPINION[^*\n]*|"
                   r"OPINION OF THE COURT|DECISION(?: ON [A-Z ]+)?)\s*\**\s*$", re.I)
# A consolidated decision may be printed under only one case-number header even though its holding
# expressly disposes of sibling cases too.  Treat those expressly decided numbers as belonging to
# the same block.  This is intentionally narrower than collecting every case citation in the text:
# a sentence must contain both a case number and a disposition verb (e.g. "Case No. 2020-07 is
# sustained" / "Case Nos. 2020-08 and 2020-09 are sustained and answered by reference...").
_DECIDED = re.compile(r"(?i)\b(?:be|is|are|was|were)\s+(?:partially\s+|in\s+part\s+)?"
                      r"(?:sustained|denied|dismissed|granted|affirmed|reversed|annulled|"
                      r"out\s+of\s+order|not\s+sustained)\b")
_CASE_NUM = re.compile(r"\b\d{4}-\d{1,3}[A-Za-z]?\b")


def promote_opinions(s):
    return "\n".join((f"#### {_OPIN.match(ln.strip()).group(1).strip()}" if _OPIN.match(ln.strip()) else ln)
                     for ln in s.split("\n"))


def decided_siblings(text, meta):
    """Return case numbers explicitly disposed of in this decision block.

    Do not infer siblings from narrative citations.  We inspect sentence-ish chunks containing a
    disposition verb and keep only numbers that are real cases in this Assembly's case table.
    """
    out = []
    # Paragraphs in the Minutes often wrap a holding over several physical lines; normalize those
    # lines first, then split conservatively on sentence punctuation.
    flat = re.sub(r"\s+", " ", text)
    for sent in re.split(r"(?<=[.!?])\s+", flat):
        if not _DECIDED.search(sent):
            continue
        for raw in _CASE_NUM.findall(sent):
            n = ce.norm_num(raw)
            if n in meta and n not in out:
                out.append(n)
    return out


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
    # Preserve existing pages by default.  `--clear` remains available for a deliberate
    # full regeneration, but a re-OCR refresh must not remove pages whose source was not
    # re-located in this run.
    if "--clear" in sys.argv:
        for f in os.listdir(OUT):
            if f.endswith(".md"):
                os.remove(os.path.join(OUT, f))
    gtitles = ce.global_titles()
    pages_map = {}
    n = 0; dropped = 0
    for vol in sorted(passing):
        ga = cls[vol]["ga"]; year = int(cls[vol]["year"]); meta = ce.table_meta(ga)
        blocks = ce.extract_sjc(vol)
        # A decision can be captioned under only one case number while expressly deciding related
        # complaints in the same holding.  Add only those sibling numbers the block itself says it
        # disposes of; ordinary citations to other decisions are left alone.  Normalized docket
        # numbers sort lexically, so a block printed under 2020-09 still renders as 07/08/09.
        for b in blocks:
            nums = list(b["numbers"])
            for x in decided_siblings(b["text"], meta):
                if x not in nums:
                    nums.append(x)
            b["numbers"] = sorted(nums)
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
            tablet = " / ".join(dict.fromkeys(t for t in titles if t))
            override = next((TITLE_OVERRIDES[x] for x in nums if x in TITLE_OVERRIDES), None)
            # trust the table title only if its parties actually appear in THIS decision; otherwise
            # the table mis-mapped the number (e.g. 91-5 'Stringer' on the Gunter page) — use the
            # case's own caption from the text.
            cap = b.get("caption") or ce.caption(b["text"])
            if tablet and ce.title_matches(tablet, b["text"]):
                title = override or tablet
            elif cap:                       # table title rejected (parties not in the decision)
                title = override or cap
            else:
                title = override or tablet or b["parties"][:90] or "(untitled)"
            dispos = [meta[x]["disposition"] for x in nums if meta.get(x) and meta[x]["disposition"]]
            hdr = [f"**Court:** Standing Judicial Commission",
                   f"**Assembly:** {ordinal(ga)} ({year})"]
            if dispos:
                hdr.append(f"**Disposition:** {'; '.join(dict.fromkeys(dispos))}")
            body = promote_opinions(b["text"])
            source_page = line_to_pdf_page(Path(ROOT), vol, int(b["lines"][0]))
            source_meta = source_front_matter(source_entries_for_record(
                Path(ROOT), "case", nums[0] if nums else slug, vol, source_page
            ))
            page = source_meta + [f"# {'/'.join(nums)} — {title}", "", "  ·  ".join(hdr), "",
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
