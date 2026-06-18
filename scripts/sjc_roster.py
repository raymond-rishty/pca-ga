#!/usr/bin/env python3
"""
sjc_roster.py — parse the PCA Historical Center's authoritative SJC case index
(pcahistory.org/pca/sjc/<decade>.html, saved under index/sjc_official/) into a
canonical roster. This is the GROUND TRUTH list of every ecclesiastical judicial
case: we reconcile our corpus-derived case index against it for coverage.

Each roster row: case_number (normalized to our scheme), case_number_raw, year,
title (parties, as the Historical Center names it), citation_raw (M__GA p.X if
present), has_pdf + pdf_url (the subset with posted full opinions), decade_page.

CLI:  sjc_roster.py build         # parse the saved HTML -> index/sjc_official/roster.jsonl
      sjc_roster.py show 1990     # print roster rows for a year
"""
from __future__ import annotations
import glob, json, os, re, sys

ROOT = "/workspace"
SRC = os.path.join(ROOT, "index", "sjc_official")
OUT = os.path.join(SRC, "roster.jsonl")

DECADES = ["1975-1984", "1985-1994", "1995-2004", "2005-2014", "2015-2019", "2020-2024"]
# a case line: 1985-01 ... | 1992-09a ... | 1988-__ ... | 2017-06&-07 ...
CASE_LINE = re.compile(r"^(\d{4})-(\d{1,2}[ab]?(?:&-?\d{1,2}[ab]?)?|__)\b[\.\s]*(.*)$")
CITE = re.compile(r"M[\s_]*\d{1,2}[\s]*GA[,\.\s]*p+\.?\s*\d+", re.I)


def norm_caseno(raw):
    """Match 07_build_cases.norm_caseno: '1990-08'->'1990-8'. Keep a/b suffix;
    '__' (unknown) -> None for the numeric part. Combined '2017-06&-07' -> first."""
    m = re.match(r"^(\d{4})-(\d{1,2})([ab]?)", raw)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}"


def visible_text(path):
    h = open(path, encoding="utf-8", errors="replace").read()
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S | re.I)
    h = re.sub(r"(?i)</?(br|p|tr|li|h\d|div|td)[^>]*>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                 ("&#146;", "'"), ("&rsquo;", "'"), ("&#147;", '"'), ("&#148;", '"')]:
        h = h.replace(a, b)
    return [re.sub(r"[ \t]+", " ", l).strip() for l in h.split("\n")]


def slug_title(fname):
    """'1990-08_Bowen_v_EasternCarolina' -> 'Bowen v. Eastern Carolina'."""
    s = re.sub(r"^\d{4}-\d{2}[ab]?(?:&-?\d{2})?_?", "", fname)
    s = s.replace("_v_", " v. ").replace("_vs_", " v. ").replace("_", " ")
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)        # split CamelCase
    return re.sub(r"\s+", " ", s).strip()


def pdf_links(path):
    """map normalized case_number -> {url, raw, title} for posted opinions."""
    h = open(path, encoding="utf-8", errors="replace").read()
    out = {}
    for href in re.findall(r'href="(cases/((\d{4})-(\d{2}[ab]?)(?:&-?\d{2})?)([^"]*)\.pdf)"', h):
        url, num, yr, nn, rest = href
        cid = norm_caseno(num)
        if cid:
            out[cid] = {"url": "https://pcahistory.org/pca/sjc/" + url,
                        "raw": num, "year": int(yr), "title": slug_title(num + rest)}
    return out


def build():
    rows = []
    for dec in DECADES:
        path = os.path.join(SRC, dec + ".html")
        if not os.path.exists(path):
            print(f"  (missing {dec}.html — skipped)"); continue
        pdfs = pdf_links(path)
        lines = visible_text(path)
        case_idx = [i for i, l in enumerate(lines) if CASE_LINE.match(l)]
        seen_cids = set()
        # (a) cases listed in the page body
        for n, i in enumerate(case_idx):
            l = lines[i]
            m = CASE_LINE.match(l)
            raw = f"{m.group(1)}-{m.group(2)}"
            title = m.group(3).strip().rstrip(".").strip()
            if not title:                       # title sometimes wraps to next line
                title = (lines[i + 1].strip().rstrip(".") if i + 1 < len(lines) else "")
            # the 2005-2014 page gives a short heading + a "Summary:" paragraph on the
            # following lines (until the next case). Fold that detail into the title so the
            # presbytery / disposition it names is searchable and matchable.
            nxt = case_idx[n + 1] if n + 1 < len(case_idx) else len(lines)
            detail = " ".join(s.strip() for s in lines[i + 1:nxt]
                              if s.strip() and not s.lower().startswith(("jump links", "judicial cases"))
                              and "©" not in s and "copyright" not in s.lower())
            if detail and ("summary" in detail.lower() or len(title) < 18):
                title = (title + " — " + detail)[:300].strip()
            cid = norm_caseno(raw)
            cite = CITE.search(l)
            seen_cids.add(cid)
            rows.append({
                "case_number": cid,
                "case_number_raw": raw,
                "year": int(m.group(1)),
                "title": title,
                "citation_raw": cite.group(0) if cite else None,
                "has_pdf": cid in pdfs,
                "pdf_url": pdfs.get(cid, {}).get("url"),
                "decade_page": dec,
                "source": "body",
            })
        # (b) cases that ONLY appear as a posted-opinion PDF link (body omits them)
        for cid, info in pdfs.items():
            if cid in seen_cids:
                continue
            rows.append({
                "case_number": cid,
                "case_number_raw": info["raw"],
                "year": info["year"],
                "title": info["title"],
                "citation_raw": None,
                "has_pdf": True,
                "pdf_url": info["url"],
                "decade_page": dec,
                "source": "pdf_only",
            })
    # de-dup exact (case_number_raw,title) repeats
    seen, uniq = set(), []
    for r in rows:
        k = (r["case_number_raw"], r["title"][:40])
        if k in seen:
            continue
        seen.add(k); uniq.append(r)
    uniq.sort(key=lambda r: (r["year"], r["case_number_raw"]))
    with open(OUT, "w") as f:
        for r in uniq:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    by_dec = {}
    for r in uniq:
        by_dec[r["decade_page"]] = by_dec.get(r["decade_page"], 0) + 1
    print(f"[roster] {len(uniq)} official SJC cases -> {OUT}")
    for dec in DECADES:
        print(f"        {dec}: {by_dec.get(dec,0)} cases")
    print(f"        with posted PDF opinion: {sum(1 for r in uniq if r['has_pdf'])}")
    print(f"        unknown number (YYYY-__): {sum(1 for r in uniq if r['case_number'] is None)}")
    return uniq


def show(year):
    for l in open(OUT):
        r = json.loads(l)
        if r["year"] == int(year):
            tag = " [PDF]" if r["has_pdf"] else ""
            print(f"  {r['case_number_raw']:12} {r['title']}{tag}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "show":
        show(sys.argv[2])
    else:
        build()
