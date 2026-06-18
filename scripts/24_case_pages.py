#!/usr/bin/env python3
"""
24_case_pages.py — give every SJC/CJB judicial case its own markdown page (full text, including
the majority/concurring/dissenting opinions), so the case index can link straight to the decision.

For each row in the `cases` table, extract the verbatim text of its page range
(pdf_page_start..pdf_page_end) from the volume markdown, add a metadata header (court, GA, parties,
disposition, vote, BCO cited, dissent) + a back-link to the source volume, promote inline opinion
labels to headings, and write cases/<case_id>.md. 20_markdown_index then links CASES.md to these.

CLI:  24_case_pages.py
"""
from __future__ import annotations
import glob, json, os, re, sqlite3

ROOT = "/workspace"
DB = os.path.join(ROOT, "index", "pca_minutes.db")
MD = os.path.join(ROOT, "markdown")
OUT = os.path.join(ROOT, "cases")

_O2V = {str(json.load(open(p))["ga_ordinal"]): json.load(open(p))["volume"]
        for p in glob.glob(os.path.join(ROOT, "index", "structure", "ga*.json"))}
# promote a standalone inline opinion label ("**DISSENTING OPINION ...**") to a navigable heading
_OPIN = re.compile(r"^\**\s*((?:CONCURRING|DISSENTING|MAJORITY|SEPARATE)\s+OPINION[^*\n]*|"
                   r"OPINION OF THE COURT|DECISION(?: ON [A-Z ]+)?)\s*\**\s*$", re.I)
# a CASE-START header line ("### APPEAL OF X VS Y", "**CASE No. 2022-23**", "JUDICIAL CASE NO ...")
# — used to trim each page to a SINGLE case (from its own header to the next case's header)
_CASEHDR = re.compile(r"(?i)^\s*#{0,4}\s*[*_]*\s*"
                      r"((APPEAL|COMPLAINT|PETITION|REVIEW)\s+OF\s+.+?\bvs?\.?\s"
                      r"|CASE\s+(NO\.?\s*)?\d"
                      r"|JUDICIAL\s+CASE\s+NO)")
_vol_cache = {}


def _pages(vol):
    if vol not in _vol_cache:
        p = os.path.join(MD, f"{vol}.md")
        _vol_cache[vol] = open(p).read() if os.path.exists(p) else None
    return _vol_cache[vol]


def page_text(vol, start, end):
    txt = _pages(vol)
    if not txt:
        return ""
    parts = re.split(r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\w+)[^>]*-->", txt)
    out = []
    for i in range(1, len(parts), 2):
        pg = parts[i]
        if pg.isdigit() and start <= int(pg) <= end:
            out.append(parts[i + 1] if i + 1 < len(parts) else "")
    s = "\n".join(out)
    s = re.sub(r'<a id="[^"]*"></a>\s*', "", s)
    # trim to a SINGLE case: keep from this case's header to just before the next case's header
    # (the page range can include the tail of the previous case and the start of the next one)
    lines = s.split("\n")
    hdr = [i for i, ln in enumerate(lines) if _CASEHDR.match(ln.strip())]
    if hdr:
        start_i = hdr[0]
        # the next case's header must be a real distance away — a case's own header can span 2-3
        # lines ("CASE No. 1999-2" then "TE Aureliano Tan v. South Texas"), which is NOT a boundary
        nxt = next((i for i in hdr if i - start_i >= 6), None)
        trimmed = lines[start_i:nxt] if nxt else lines[start_i:]
        if len("\n".join(trimmed).strip()) >= 40:    # only trim if it leaves real content
            lines = trimmed
    # promote opinion labels to headings for navigation
    s = "\n".join((f"#### {_OPIN.match(ln).group(1).strip()}" if _OPIN.match(ln.strip()) else ln)
                  for ln in lines)
    return s.strip()


def vol_of(r):
    cid = r["case_id"] or ""
    return cid.split(":")[0] if cid.split(":")[0].startswith("ga") else _O2V.get(str(r["ga_ordinal"]))


def fname(case_id):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", case_id)


def ordinal(n):
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def main():
    os.makedirs(OUT, exist_ok=True)
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    n = 0; skipped = 0
    for r in c.execute("SELECT * FROM cases"):
        vol = vol_of(r)
        start, end = r["pdf_page_start"], r["pdf_page_end"]
        if not vol or not start:
            skipped += 1; continue
        body = page_text(vol, int(start), int(end or start))
        if len(body) < 40:
            skipped += 1; continue
        num = r["canonical_number"] or r["case_number"] or f"p{start}"
        who = (r["parties"] or r["title"] or "").strip()
        bits = [f"**Court:** {r['body'] or '—'}",
                f"**Assembly:** {ordinal(r['ga_ordinal'])} ({r['year']})",
                f"**Disposition:** {r['disposition'] or '—'}"]
        if r["vote"]:
            bits.append(f"**Vote:** {r['vote']}")
        if r["has_dissent"] in (1, "1"):
            bits.append("**Dissent:** yes")
        if (r["bco_cited_as_s"] or "").strip():
            bits.append(f"**BCO cited:** {r['bco_cited_as_s'][:120]}")
        pr = f"pp. {start}–{end}" if end and int(end) != int(start) else f"p. {start}"
        title = f"# Case {num}" + (f" — {who}" if who else "")
        page = [title, "", "  ·  ".join(bits), "",
                f"*Source: [{vol} {pr}](../markdown/{vol}.md)*", "", "---", "", body, "", "---", "",
                f"[← Judicial case index](../index/CASES.md)"]
        open(os.path.join(OUT, fname(r["case_id"]) + ".md"), "w").write("\n".join(page) + "\n")
        n += 1
    print(f"wrote {n} case pages to cases/  (skipped {skipped} with no text/page)")


if __name__ == "__main__":
    main()
