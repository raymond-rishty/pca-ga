#!/usr/bin/env python3
"""
25_case_extract.py — re-derive judicial cases from DOCUMENT STRUCTURE (not the unreliable cases
table), per the volume classification in index/case_volume_class.json.

Prototype phase: two class extractors.
  SJC (GA19-52): the SJC report is a sequence of "**CASE YYYY-NN**" decision blocks (parties as
    "COMPLAINT/APPEAL OF X VS Y", then I. Summary of Facts ... opinions). A case = one block, from
    its header to the next NEW case number; same-number reruns (opinions) and AND-consolidated
    sibling numbers stay in the block. References to other cases (e.g. "Case 2007-13" cited inside
    a 2009-25 opinion) are NOT headers, so they never become phantom cases.
  CJB (GA4-18): TODO (complaint summaries + §10-79 reports, matched by parties).

CLI:  25_case_extract.py sjc <vol>     # prototype: print the cases a volume yields
"""
from __future__ import annotations
import re, sys

ROOT = "/workspace"
_HDR = re.compile(r"^\s*(?:#{1,4}\s*)?\*{0,2}\s*CASE\s+(?:No\.?\s*)?(\d{2,4}-\d{1,3}[A-Za-z]?)\b", re.I)
_PARTY = re.compile(r"^\s*\*{0,2}\s*((?:COMPLAINT|APPEAL|PETITION|REVIEW)\s+OF\s+.+|VS?\.?|AND|.+\bPRESBYTERY\b.*)\*{0,2}\s*$", re.I)
_REPORT_END = re.compile(r"(?i)^\s*#*\s*\**\s*(respectfully submitted|appendix\s+[A-Z]\b|index\b)")
_GAP = 45


def norm_num(n):
    m = re.match(r"(\d{2,4})-(\d+)([A-Za-z]?)", n)
    a, b, c = m.group(1), int(m.group(2)), m.group(3).lower()
    if len(a) == 2:
        a = ("19" if int(a) >= 70 else "20") + a
    return f"{a}-{b:02d}{c}"


def extract_sjc(vol):
    lines = open(f"{ROOT}/markdown/{vol}.md").read().split("\n")
    hdrs = [(i, norm_num(_HDR.match(l.strip()).group(1))) for i, l in enumerate(lines)
            if _HDR.match(l.strip())]
    if not hdrs:
        return []
    first = hdrs[0][0]
    # report end = first section-ender after the last header
    end = len(lines)
    for i in range(hdrs[-1][0] + 1, len(lines)):
        if _REPORT_END.match(lines[i]):
            end = i; break
    hdrs = [(ln, num) for ln, num in hdrs if ln < end]
    # segment into blocks
    blocks = []
    for ln, num in hdrs:
        if blocks and (num in blocks[-1]["nums"] or ln - blocks[-1]["last"] <= _GAP):
            blocks[-1]["nums"].add(num); blocks[-1]["last"] = ln
        else:
            if blocks:
                blocks[-1]["end"] = ln
            blocks.append({"start": ln, "nums": {num}, "last": ln})
    blocks[-1]["end"] = end
    out = []
    for b in blocks:
        body = "\n".join(lines[b["start"]:b["end"]])
        body = re.sub(r'<a id="[^"]*"></a>\s*', "", body)
        # parties: the bold lines right after the first header
        parties = []
        for l in lines[b["start"] + 1:b["start"] + 8]:
            s = re.sub(r"[*_]", "", l).strip()
            if not s:
                continue
            if _HDR.match(l.strip()) or re.match(r"(?i)^(I\.|SUMMARY|STATEMENT|DECISION|\d)", s):
                break
            parties.append(s)
        out.append({"vol": vol, "numbers": sorted(b["nums"]), "parties": " ".join(parties)[:120],
                    "lines": (b["start"] + 1, b["end"]), "chars": len(body), "text": body})
    return out


_STOP = set("the of and against complaint appeal report commission judicial case to hear adjudicate "
            "presbytery session moderator church first et al teaching elder ruling mr mrs ms dr rev "
            "north south east west carolina georgia".split())


def _names(s):
    return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", re.sub(r"[*_#]", "", s or ""))
            if w.lower() not in _STOP}


def extract_cjb(vol):
    lines = open(f"{ROOT}/markdown/{vol}.md").read().split("\n")
    # 1) complaint summaries in "F. JUDICIAL CASES—COMPLAINTS"
    cs = next((i for i, l in enumerate(lines) if re.search(r"(?i)JUDICIAL CASES.{0,3}COMPLAINTS", l)), None)
    rep0 = next((i for i, l in enumerate(lines) if re.search(r"(?i)reports? of (the )?judicial commission", l)), None)
    complaints = []
    if cs is not None:
        cur = None
        for i in range(cs + 1, rep0 or len(lines)):
            m = re.match(r"^\s*Case\s+(\d+):\s*(.+)", lines[i], re.I)
            if m:
                if cur:
                    complaints.append(cur)
                cur = {"num": int(m.group(1)), "head": re.sub(r"[*_]", "", m.group(2)).strip(), "lines": [i], "body": []}
            elif cur is not None:
                cur["body"].append(lines[i])
                if re.search(r"(?i)adjudicated", lines[i]):
                    complaints.append(cur); cur = None
        if cur:
            complaints.append(cur)
    # 2) §10-79 adjudication reports
    reports = []
    if rep0 is not None:
        hdr = re.compile(r"(?i)(report of .*commission|CASE\s*#\s*\d)")
        starts = [i for i in range(rep0 + 1, len(lines)) if hdr.search(lines[i]) and "complaint" in lines[i].lower() or re.match(r"(?i)^\s*#*\s*CASE\s*#\s*\d", lines[i])]
        for j, s in enumerate(starts):
            e = starts[j + 1] if j + 1 < len(starts) else min(rep0 + 4000, len(lines))
            head = " ".join(re.sub(r"[*_#]", "", lines[k]).strip() for k in range(s, min(s + 3, e)))
            reports.append({"head": head[:120], "lines": (s, e), "names": _names(head)})
    # 3) match each complaint to a report by party names
    for c in complaints:
        cn = _names(c["head"])
        best = max(reports, key=lambda r: len(cn & r["names"]), default=None)
        c["match"] = best if best and len(cn & best["names"]) >= 1 else None
    return complaints, reports


def render(vols, outdir, cls):
    import os
    os.makedirs(outdir, exist_ok=True)
    idx = ["# Structure‑extracted cases — REVIEW SAMPLE", "",
           "Prototype output of `25_case_extract.py` (structure‑based re‑extraction). This is for "
           "review only — it is **not** the live `cases/` pages.", ""]
    for vol in vols:
        cl = cls.get(vol, {}).get("class", "?")
        idx += ["", f"## {vol}  _({cl})_", ""]
        if cl == "SJC-decision":
            for c in extract_sjc(vol):
                slug = f"{vol}__{'_'.join(c['numbers'])}"
                pg = [f"# {'/'.join(c['numbers'])} — {c['parties'][:90]}", "",
                      f"*{vol}, source lines {c['lines'][0]}–{c['lines'][1]} · {c['chars']} chars*",
                      "", "---", "", c["text"]]
                open(f"{outdir}/{slug}.md", "w").write("\n".join(pg) + "\n")
                idx.append(f"- [{'/'.join(c['numbers'])}]({os.path.basename(outdir)}/{slug}.md) — {c['parties'][:65]}")
        elif cl == "CJB-split":
            lines = open(f"{ROOT}/markdown/{vol}.md").read().split("\n")
            comps, reps = extract_cjb(vol)
            for c in comps:
                slug = f"{vol}__case{c['num']}"
                comp = c["head"] + "\n\n" + "\n".join(c["body"])
                if c["match"]:
                    s, e = c["match"]["lines"]
                    adj = "\n".join(lines[s:e])
                    adjnote = ""
                else:
                    adj = "_(no §10‑79 adjudication report matched by parties)_"
                    adjnote = "  ⚠ no adjudication matched"
                pg = [f"# {vol} Case {c['num']} — {c['head'][:80]}", "", "## Complaint", "", comp,
                      "", "## Adjudication (§10‑79)", "", adj]
                open(f"{outdir}/{slug}.md", "w").write("\n".join(re.sub(r'<a id="[^"]*"></a>', "", x) for x in pg) + "\n")
                idx.append(f"- [Case {c['num']}]({os.path.basename(outdir)}/{slug}.md) — {c['head'][:55]}{adjnote}")
    open(f"{ROOT}/REBUILD-INDEX.md", "w").write("\n".join(idx) + "\n")
    print(f"rendered review sample for {vols} -> {outdir} + REBUILD-INDEX.md")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "render":
        import json
        render(sys.argv[2:], f"{ROOT}/cases-rebuilt", json.load(open(f"{ROOT}/index/case_volume_class.json")))
    elif len(sys.argv) >= 3 and sys.argv[1] == "cjb":
        comps, reps = extract_cjb(sys.argv[2])
        print(f"{len(comps)} complaint summaries, {len(reps)} §10-79 reports in {sys.argv[2]}\n")
        for c in comps:
            mt = c["match"]["head"][:55] if c["match"] else "** NO MATCH **"
            print(f"  Case {c['num']}: {c['head'][:48]}")
            print(f"      -> report: {mt}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "sjc":
        cs = extract_sjc(sys.argv[2])
        print(f"{len(cs)} case blocks in {sys.argv[2]}:")
        for c in cs:
            print(f"  {'/'.join(c['numbers']):16} L{c['lines'][0]}-{c['lines'][1]} {c['chars']:>6}c  {c['parties'][:60]}")
    else:
        print(__doc__)
