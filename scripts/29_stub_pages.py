#!/usr/bin/env python3
"""
29_stub_pages.py — stub pages for judicial matters DISPOSED WITHOUT a published merits decision
(found administratively out of order, withdrawn, abandoned, dismissed in a roll-up sentence). These
have no full opinion to extract, but the minutes DO record how they were disposed — so per the
agreed design they still get a small page: the verbatim disposing sentence from the minutes + the
corrected disposition + a source link. Only created when such a sentence is actually found in the
case's own volume (otherwise there is genuinely nothing to show, and the index keeps its label).

Run AFTER 26/27/28 (skips any number that already has a full decision page). Emits:
  cases/<vol>__stub_<num>.md
  index/stub_pages.json   {normalized_number: {vol, file, disposition}}

CLI:  29_stub_pages.py
"""
from __future__ import annotations
import glob, json, os, re, sqlite3

ROOT = "/workspace"
OUT = f"{ROOT}/cases"
DB = f"{ROOT}/index/pca_minutes.db"
# the disposing phrase (also becomes the corrected disposition label)
_CUE = re.compile(r"(?i)(administratively\s+out\s+of\s+order|out\s+of\s+order|withdraw\w*|withdrew|"
                  r"abandoned|dismiss\w*|rendered?\s+moot|made\s+moot|moot|"
                  r"not\s+(?:administratively\s+)?in\s+order|prematurely\s+filed|premature)")
_ANCHOR = re.compile(r'<a id="[^"]*"></a>\s*')


def ordinal(n):
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def variants(raw):
    m = re.match(r"\D*(\d{2,4})-(\d{1,3})([A-Za-z]?)", str(raw or ""))
    if not m:
        return set(), None
    a, b, suf = m.group(1), int(m.group(2)), m.group(3)
    forms = {a}
    if len(a) == 2:
        forms.add(("19" if int(a) >= 70 else "20") + a)
    elif len(a) == 4:
        forms.add(a[-2:])
    out = set()
    for f in forms:
        out |= {f"{f}-{b}{suf}", f"{f}-{b:02d}{suf}"}
    norm = (("19" if int(a) >= 70 else "20") + a if len(a) == 2 else a) + f"-{b:02d}{suf.lower()}"
    return out, norm


def _disp_label(phrase):
    p = phrase.lower()
    if "out of order" in p or "not" in p and "in order" in p:
        return "Administratively Out of Order" if "administ" in p else "Out of Order"
    if "withdraw" in p or "withdrew" in p or "premature" in p:
        return "Withdrawn"
    if "abandon" in p:
        return "Abandoned"
    if "moot" in p:
        return "Rendered Moot"
    if "dismiss" in p:
        return "Dismissed"
    return phrase.strip().capitalize()


def find_disposition(lines, vset, region_lo):
    """Find the verbatim sentence where this case is disposed (number + a disposition cue). The
    cue may wrap across lines, so search the line joined with the next; prefer the longest in-region
    match. Returns (line_index, text, disposition_label)."""
    pat = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(v) for v in vset))
    best = None
    for i, ln in enumerate(lines):
        if not pat.search(ln):
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        combined = re.sub(r"\s+", " ", _ANCHOR.sub("", ln + " " + nxt)).strip()
        cue = _CUE.search(combined)                       # leftmost cue across the wrap
        if not cue:
            continue
        score = (1 if i >= region_lo else 0, len(ln))
        if best is None or score > best[0]:
            best = (score, i, combined, _disp_label(cue.group(0)))
    if best:
        return best[1], best[2], best[3]
    return None, None, None


def main():
    pmap = json.load(open(f"{ROOT}/index/case_pages_map.json"))
    cjb = {p["vol"] for p in json.load(open(f"{ROOT}/index/cjb_pages.json"))} if os.path.exists(f"{ROOT}/index/cjb_pages.json") else set()
    o2v = {str(json.load(open(p))["ga_ordinal"]): json.load(open(p))["volume"]
           for p in glob.glob(f"{ROOT}/index/structure/ga*.json")}
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    rows = list(c.execute("SELECT ga_ordinal, year, canonical_number, case_number, parties, title, "
                          "disposition FROM cases"))
    def lines_of(vol):
        if vol not in vol_lines:
            p = f"{ROOT}/markdown/{vol}.md"
            vol_lines[vol] = open(p).read().split("\n") if os.path.exists(p) else []
        return vol_lines[vol]

    vol_lines = {}
    stubs = {}
    n = 0
    for r in rows:
        ga = r["ga_ordinal"]
        if ga is None:
            continue
        ga = int(ga)
        vset, norm = variants(r["canonical_number"] or r["case_number"] or "")
        if not norm or norm in pmap or norm in stubs:  # already has a full decision/stub
            continue
        # The table's ga_ordinal is unreliable and a case is often DISPOSED a GA or two later than
        # it was filed/listed (deferred to a later SJC meeting). Search the table-GA volume and the
        # next two for the disposing sentence; use the volume where it's actually recorded.
        found = None
        for gg in (ga, ga + 1, ga + 2):
            vol = o2v.get(str(gg))
            if not vol or vol in cjb:
                continue
            lines = lines_of(vol)
            lo = next((i for i, l in enumerate(lines)
                       if re.search(r"(?i)standing judicial commission|judicial cases", l)), 0)
            idx, text, disp = find_disposition(lines, vset, lo)
            if text:
                yr = (re.search(r"_(\d{4})", vol) or [None, r["year"]])[1]
                found = (gg, vol, yr, text, disp); break
        if not found:
            continue                                  # genuinely nothing recorded -> no stub
        gg, vol, yr, text, disp = found
        who = (r["parties"] or r["title"] or "").strip()
        slug = f"{vol}__stub_{norm}"
        page = [f"# {norm} — {who or '(parties not given)'}", "",
                f"**Court:** Standing Judicial Commission  ·  **Assembly:** {ordinal(gg)} ({yr})"
                f"  ·  **Disposition:** {disp}", "",
                "*No separate merits opinion was published; the Assembly disposed of this matter as "
                "recorded below.*", "", "---", "",
                "> " + text.replace("\n", "\n> "), "",
                f"*Source: [{vol}](../markdown/{vol}.md)*", "", "---", "",
                "[← Judicial case index](../index/CASES.md)"]
        open(f"{OUT}/{slug}.md", "w").write("\n".join(page) + "\n")
        stubs[norm] = {"vol": vol, "file": slug, "disposition": disp, "ga": gg, "parties": who}
        n += 1
    json.dump(stubs, open(f"{ROOT}/index/stub_pages.json", "w"), indent=1)
    print(f"wrote {n} stub pages (disposed without a published opinion) -> cases/ + index/stub_pages.json")


if __name__ == "__main__":
    main()
