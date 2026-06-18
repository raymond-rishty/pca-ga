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
# a CASE-START header line ("APPEAL OF X VS Y", "CASE No. 2022-23", "JUDICIAL CASE 98-9") —
# headers may be plain text (no #/bold) and case titles REPEAT as running page headers, so the
# reliable cut signal is the NEXT case's number/parties (never in the current case's own headers).
_CASEHDR = re.compile(r"(?i)^\s*#{0,4}\s*[*_]*\s*"
                      r"((APPEAL|COMPLAINT|PETITION|REVIEW)\s+OF\b"
                      r"|(?:JUDICIAL\s+)?CASE\s+(NO\.?\s*)?\d)")


def _num_variants(*labels):
    # "1998-9" / "98-9" -> {"1998-9","1998-09","98-9","98-09"} so the next case's number matches
    # however the minutes wrote it
    out = set()
    for lab in labels:
        m = re.match(r"\D*(\d{2,4})-(\d{1,3})\b", str(lab or ""))
        if not m:
            continue
        a, n = m.group(1), int(m.group(2))
        forms = {a}
        if len(a) == 2:
            forms.add(("19" if int(a) >= 70 else "20") + a)
        elif len(a) == 4:
            forms.add(a[-2:])
        for f in forms:
            out |= {f"{f}-{n}", f"{f}-{n:02d}"}
    return {o for o in out if o}
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
    return re.sub(r'<a id="[^"]*"></a>\s*', "", s).strip()


def trim_to_case(s, next_variants, next_parties):
    # keep from THIS case's header to just before the NEXT case begins. The next case is found by
    # its own number (e.g. "JUDICIAL CASE 98-9") or party surname — neither appears in the current
    # case's running headers, so this is robust to repeated titles.
    lines = s.split("\n")
    hdr = [i for i, ln in enumerate(lines) if len(ln.strip()) < 95 and _CASEHDR.match(ln.strip())]
    start_i = hdr[0] if hdr else 0
    numpat = (re.compile(r"\b(?:%s)\b" % "|".join(re.escape(v) for v in next_variants))
              if next_variants else None)
    nps = [w for w in re.findall(r"[A-Za-z]{4,}", next_parties or "")
           if w.lower() not in ("presbytery", "appeal", "complaint", "petition", "review",
                                "case", "judicial", "session", "church", "the", "and")][:2]
    end_i = len(lines)
    for i in range(start_i + 1, len(lines)):
        ln = lines[i].strip()
        if len(ln) > 95:
            continue
        ishdr = bool(_CASEHDR.match(ln))
        if numpat and numpat.search(ln) and (ishdr or "case" in ln.lower()):
            end_i = i; break
        if ishdr and nps and all(p.lower() in ln.lower() for p in nps):
            end_i = i; break
    body = "\n".join(lines[start_i:end_i]).strip()
    return body if len(body) >= 40 else s.strip()


def promote_opinions(s):
    return "\n".join((f"#### {_OPIN.match(ln).group(1).strip()}" if _OPIN.match(ln.strip()) else ln)
                     for ln in s.split("\n"))


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
    rows = list(c.execute("SELECT rowid, * FROM cases"))
    # within each volume, order cases by page so we know what the NEXT case is
    byvol = {}
    for r in rows:
        v = vol_of(r)
        if v and r["pdf_page_start"]:
            byvol.setdefault(v, []).append(r)
    nextof = {}
    for v, rs in byvol.items():
        rs.sort(key=lambda r: (int(r["pdf_page_start"]), int(r["pdf_page_end"] or r["pdf_page_start"]), r["rowid"]))
        for i, r in enumerate(rs):
            nextof[r["rowid"]] = rs[i + 1] if i + 1 < len(rs) else None
    n = 0; skipped = 0
    for r in rows:
        vol = vol_of(r)
        start, end = r["pdf_page_start"], r["pdf_page_end"]
        if not vol or not start:
            skipped += 1; continue
        nx = nextof.get(r["rowid"])
        nvars = _num_variants(nx["canonical_number"], nx["case_number"]) if nx else set()
        nparties = (nx["parties"] or nx["title"] or "") if nx else ""
        body = promote_opinions(trim_to_case(page_text(vol, int(start), int(end or start)), nvars, nparties))
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
