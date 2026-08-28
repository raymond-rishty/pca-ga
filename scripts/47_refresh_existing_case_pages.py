#!/usr/bin/env python3
"""
Refresh only existing structured SJC case pages from the current Markdown.

`index/case_pages_map.json` is the allow-list: a page is written only when its
mapped case block is found again in the current document structure and the target
file already exists.  No page is deleted and no new page is created.  This makes
the command safe for a re-OCR branch where some cases still need review.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(os.environ.get("PCA_GA_ROOT", Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location("case_extract", ROOT / "scripts" / "25_case_extract.py")
ce = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(ce)
OPIN = re.compile(r"^\**\s*((?:CONCURRING|DISSENTING|MAJORITY|SEPARATE)\s+OPINION[^*\n]*|"
                 r"OPINION OF THE COURT|DECISION(?: ON [A-Z ]+)?)\s*\**$", re.I)


def ordinal(n: int) -> str:
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def promote_opinions(text: str) -> str:
    return "\n".join(
        (f"#### {OPIN.match(line.strip()).group(1).strip()}"
         if OPIN.match(line.strip()) else line)
        for line in text.split("\n")
    )


def reviewed_preamble(existing: str, target: Path) -> str | None:
    marker = "\n---\n"
    preamble = existing.split(marker, 1)[0] if marker in existing else None
    page_link = re.compile(r"\*Source: .*\bpp?\. .*#ga\d+-p", re.I)
    if preamble and page_link.search(preamble):
        return preamble
    if preamble and " lines " in preamble:
        rel = target.relative_to(ROOT).as_posix()
        try:
            prior = subprocess.check_output(
                ["git", "show", f"HEAD^:{rel}"],
                cwd=ROOT, text=True, encoding="utf-8", stderr=subprocess.DEVNULL,
            )
            if marker in prior:
                prior_preamble = prior.split(marker, 1)[0]
                if page_link.search(prior_preamble):
                    return prior_preamble
        except (subprocess.CalledProcessError, OSError):
            pass
    return preamble


def page_for(block: dict, vol: str, meta: dict, titles: dict, overrides: dict,
             existing: str | None = None, target: Path | None = None) -> str:
    numbers = list(block["numbers"])
    table_titles = [(meta[x]["title"] if meta.get(x) and meta[x]["title"] else titles.get(x, ""))
                    for x in numbers]
    table_title = " / ".join(dict.fromkeys(t for t in table_titles if t))
    override = next((overrides[x] for x in numbers if x in overrides), None)
    caption = block.get("caption") or ce.caption(block["text"])
    if table_title and ce.title_matches(table_title, block["text"]):
        title = override or table_title
    elif caption:
        title = override or caption
    else:
        title = override or table_title or block.get("parties", "")[:90] or "(untitled)"
    dispositions = [meta[x]["disposition"] for x in numbers
                    if meta.get(x) and meta[x]["disposition"]]
    ga = int(vol[2:4])
    year = int(vol[-4:])
    # The existing page's preamble is authoritative presentation metadata.  In
    # particular, it carries the reviewed title, dissent/provenance fields, and
    # the printed-page minutes link.  The re-OCR block supplies only the body.
    preamble = reviewed_preamble(existing, target) if existing and target else None
    if preamble:
        prefix = preamble
    else:
        header = ["**Court:** Standing Judicial Commission",
                  f"**Assembly:** {ordinal(ga)} ({year})"]
        if dispositions:
            header.append(f"**Disposition:** {'; '.join(dict.fromkeys(dispositions))}")
        prefix = "\n".join([f"# {'/'.join(numbers)} — {title}", "", "  ·  ".join(header)])
    body = promote_opinions(block["text"])
    return "\n".join([
        prefix,
        "", "---", "", body, "", "---", "", "[← Judicial case index](../index/CASES.md)", ""
    ])


def main() -> None:
    page_map = json.loads((ROOT / "index" / "case_pages_map.json").read_text(encoding="utf-8"))
    overrides = json.loads((ROOT / "index" / "case_title_overrides.json").read_text(encoding="utf-8"))
    titles = ce.global_titles()
    by_file: dict[str, dict] = {}
    for number, entry in page_map.items():
        by_file.setdefault(entry["file"], entry)
    extracted: dict[str, list[dict]] = {}
    refreshed = 0
    missing_block = 0
    for file_name, entry in sorted(by_file.items()):
        vol = entry["vol"]
        if vol not in extracted:
            extracted[vol] = ce.extract_sjc(vol)
        wanted = {ce.norm_num(n) for n in entry.get("numbers", [])}
        blocks = extracted[vol]
        candidates = [b for b in blocks
                      if {ce.norm_num(n) for n in b["numbers"]} == wanted]
        if not candidates:
            candidates = [b for b in blocks
                          if wanted <= {ce.norm_num(n) for n in b["numbers"]}]
        # A docket/list row can have the same case number as the later full decision.
        # Require a decision marker for short blocks, then keep the longest candidate.
        markers = re.compile(r"(?i)summary of (the )?facts|statement of the (issue|facts|case)|"
                             r"decision|opinion|judgment|recommendation|complaint is|appeal is")
        candidates = [b for b in candidates if len(b.get("text", "")) >= 1000 or
                      markers.search(b.get("text", ""))]
        block = max(candidates, key=lambda b: b.get("chars", len(b.get("text", ""))),
                    default=None)
        target = ROOT / "cases" / f"{file_name}.md"
        if block is None or not target.exists():
            missing_block += 1
            continue
        meta = ce.table_meta(int(vol[2:4]))
        existing = target.read_text(encoding="utf-8")
        target.write_text(page_for(block, vol, meta, titles, overrides, existing, target), encoding="utf-8")
        refreshed += 1
    print(f"refreshed {refreshed} existing structured case pages; "
          f"left {missing_block} mapped pages untouched; created 0; deleted 0")


if __name__ == "__main__":
    main()
