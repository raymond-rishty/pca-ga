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
import os, re, sys

ROOT = "/workspace"
# Header recognizers, chosen per-volume by autotune (the case-header format drifts 1973-2025).
#  STRICT (P1): a "[JUDICIAL] CASE [No.] NN" line — "**CASE 2009-25**", "JUDICIAL CASE 91-1".
#  BROAD: P2 (the extended keyword family — SJC NN / STANDING JUDICIAL COMMISSION CASE NN /
#    JUDICIAL MATTER NN / CASE NUMBER NN / CASE Nos. NN, optionally led by COMPLAINT/APPEAL/...
#    /MAJORITY REPORT ON) ∪ P3 (a disposition-led or bare bold number "**APPEAL 2005-1**" /
#    "**2010-18 Gulfstream –**"). P2 is a superset of P1.
#  BARE (P4): a standalone number line "### 99-1" / "**2017-01**" — high false-positive, so only
#    ever used together with the decision-marker gate.
def _st(*words):
    """Space-tolerant keyword(s): OCR space-shattering can split a word ("COM PLAINT", "C ASE",
    "JUDI CIAL") — allow an optional space between every letter so a shattered keyword in a case
    HEADER still matches and the case isn't silently dropped. Multiple words joined by \\s+."""
    return r"\s+".join(r"\s?".join(map(re.escape, w)) for w in words)
_NUM = r"(\d{2,4}-\d{1,3}[A-Za-z]?)"
# disposition words that may lead a header (also space-tolerant)
_DISP = "(?:" + "|".join(_st(w) for w in
        ("COMPLAINT", "APPEAL", "PETITION", "REVISION", "REVIEW", "REFERENCE", "DECISION")) + r")"
_P1 = rf"\*{{0,2}}\s*(?:{_st('JUDICIAL')}\s+)?{_st('CASE')}\s+(?:{_st('No')}\.?\s*)?{_NUM}"
_P2 = (rf"\*{{0,2}}\s*(?:\d+\.\s*)?(?:(?:{_st('MAJORITY')}|{_st('MINORITY')})\s+{_st('REPORT')}\s+{_st('ON')}\s+)?"
       rf"(?:{_DISP}\s*,?\s+)?(?:{_st('STANDING','JUDICIAL','COMMISSION')}\s+)?"
       rf"(?:{_st('SJC')}|(?:{_st('JUDICIAL')}\s+)?(?:{_st('CASE')}(?:\s?S)?|{_st('MATTER')}))"
       rf"\s+(?:{_st('No')}(?:\s?[sS])?\s*\.?\s*|{_st('NUMBER')}\s+)?{_NUM}")
# disposition-led ("**APPEAL 2005-1**") or bare ("**2010-18 ...**") bold number
_P3 = rf"\*\*\s*(?:{_DISP}\s+)?(\d{{4}}-\d{{1,3}})\b"
_HDR_STRICT = re.compile(r"^\s*(?:#{1,4}\s*)?" + _P1, re.I)
_HDR_BROAD = re.compile(r"^\s*(?:#{1,4}\s*)?(?:" + _P2 + r"|" + _P3 + r")", re.I)
_HDR_BARE = re.compile(r"^\s*(?:#{1,4}\s*)?\*{0,2}\s*(\d{2,4}-\d{1,3}[A-Za-z]?)\*{0,2}\s*$")
# sibling case-numbers consolidated on the SAME header line ("... AND CASE 2019-12", "and 2009-26")
_SIB = re.compile(r"(?:\bAND\b|&|,|/)\s*(?:" + _st("CASE") + r"\s+|" + _st("No") + r"\.?\s*)?"
                  r"(\d{2,4}-\d{1,3}[A-Za-z]?)", re.I)
# an inline CITATION, not a header: "Case 2021-15: _Barber et al. v. CIP._" — the case number is
# followed by a colon + parties on the same line (how cases are cited inside another's reasoning).
# Real SJC headers put the number standalone (parties on later lines), never "NUMBER: parties".
_CITE = re.compile(r"^\s*(?:#{1,4}\s*)?\*{0,2}\s*(?:(?:" + _st("JUDICIAL") + r"\s+)?" + _st("CASE")
                   + r"\s+(?:" + _st("No") + r"\.?\s*)?)?\d{2,4}-\d{1,3}[A-Za-z]?\s*:\s*\S", re.I)
# a back-reference to where a case was decided ("... (M21GA, 1993, p. 223)") — only ever appears in
# a CITATION to a prior case inside another decision's reasoning, never in a real header line.
_GAREF = re.compile(r"\(\s*M\.?\s*\d+\s*GA\b|\bM\d+GA\b", re.I)
# a "this is a real decision, not a docket row" marker, expected within a few lines of a true header
_MARK = re.compile(r"(?i)summary of (the )?facts|statement of the (issue|facts|case)|"
                   r"nature of the case|^\s*\**\s*(?:I|1)\.\s|the following decision|"
                   r"^\s*\**\s*decision\b|recommendation|on the merits|judgment|"
                   r"reasoning and opinion|out of order|the (standing judicial )?commission finds|"
                   r"the case is dismiss|the (complaint|appeal) is (dismiss|denied|sustain)|"
                   r"roll call vote")


def _hdrnum(line, broad=True, bare=False):
    s = line.strip()
    m = (_HDR_BROAD if broad else _HDR_STRICT).match(s)
    if m:
        return next((g for g in m.groups() if g), None)
    if bare:
        m = _HDR_BARE.match(s)
        if m:
            return m.group(1)
    return None
_PARTY = re.compile(r"^\s*\*{0,2}\s*((?:COMPLAINT|APPEAL|PETITION|REVIEW)\s+OF\s+.+|VS?\.?|AND|.+\bPRESBYTERY\b.*)\*{0,2}\s*$", re.I)
_REPORT_END = re.compile(r"(?i)^\s*#*\s*\**\s*(respectfully submitted|appendix\s+[A-Z]\b|index\b)")
_GAP = 45


def norm_num(n):
    m = re.match(r"(\d{2,4})-(\d+)([A-Za-z]?)", n)
    a, b, c = m.group(1), int(m.group(2)), m.group(3).lower()
    if len(a) == 2:
        a = ("19" if int(a) >= 70 else "20") + a
    return f"{a}-{b:02d}{c}"


def table_meta(ga):
    """Authoritative case IDENTITY (parties/title/disposition/dissent) from the cases table, keyed
    by normalized case number, for one GA. The table's LOCATIONS are unreliable, but its metadata
    is good — so structure extraction owns the text/boundaries and the table owns the title."""
    import sqlite3
    c = sqlite3.connect(f"{ROOT}/index/pca_minutes.db"); c.row_factory = sqlite3.Row
    out = {}
    for r in c.execute("SELECT canonical_number, case_number, parties, title, disposition, "
                       "has_dissent FROM cases WHERE ga_ordinal=?", (ga,)):
        raw = r["canonical_number"] or r["case_number"] or ""
        if not re.match(r"\d{2,4}-\d", raw):
            continue
        # prefer a clean "X v. Y" title; fall back to parties; reject journal-sentence titles
        t = (r["title"] or "").strip()
        if len(t) > 70 or re.search(r"(?i)was withdrawn|completed its work|does not (require|involve)", t):
            t = (r["parties"] or "").strip()
        out[norm_num(raw)] = {"title": t, "parties": (r["parties"] or "").strip(),
                              "disposition": (r["disposition"] or "").strip(),
                              "dissent": r["has_dissent"] in (1, "1")}
    c.close()
    return out


def _strategy(vol):
    """The autotuned (broad, marker, bare) knobs for a volume, if recorded; else the default."""
    import json, os
    p = f"{ROOT}/index/sjc_strategy.json"
    if os.path.exists(p):
        s = json.load(open(p)).get(vol)
        if s:
            return bool(s["broad"]), bool(s["marker"]), bool(s.get("bare"))
    return True, False, False


def extract_sjc(vol, broad=None, marker=None, bare=None):
    if broad is None:
        broad, marker, bare = _strategy(vol)
    lines = open(f"{ROOT}/markdown/{vol}.md").read().split("\n")
    # a header counts only if it parses AND (if marker required) a decision-marker follows within
    # 15 lines — this rejects docket/index rows (consecutive numbers with no decision text).
    hdrs = []
    for i, l in enumerate(lines):
        n = _hdrnum(l, broad, bare)
        if not n:
            continue
        if _CITE.match(l) or _GAREF.search(l):   # inline citation to a prior case, not a header
            continue
        if marker:
            raw = "\n".join(lines[i + 1:i + 16])
            # also test a whitespace-collapsed copy: a disposition marker ("...Out of\nOrder") is
            # often split by a line wrap, which would defeat the literal-spaced patterns.
            if not (_MARK.search(raw) or _MARK.search(re.sub(r"\s+", " ", raw))):
                continue
        # capture ALL case numbers on a consolidated header line, not just the first — e.g.
        # "**CASE 2019-10 AND CASE 2019-12**" or "2009-25 and 2009-26" decide several together.
        nums = [norm_num(n)]
        for sm in _SIB.finditer(l):
            nums.append(norm_num(sm.group(1)))
        hdrs.append((i, nums))
    if not hdrs:
        return []
    # report end = first section-ender after the last header
    end = len(lines)
    for i in range(hdrs[-1][0] + 1, len(lines)):
        if _REPORT_END.match(lines[i]):
            end = i; break
    hdrs = [(ln, nums) for ln, nums in hdrs if ln < end]
    # segment into blocks. A header joins the previous block only if it's the same number (an
    # opinion re-run) OR a near, SAME-YEAR sibling with NO decision of its own in between. Genuine
    # consolidations (2010-18..23 citations, 2015-01..04) are bare headers sharing ONE later
    # decision — nothing decisional sits between them. Two adjacent SEPARATE decisions each carry
    # their own decision body (e.g. ga50 2022-09 Benyola then 2022-10 Herron, 32 lines apart), so a
    # decision marker BETWEEN the headers means they must stay separate.
    blocks = []
    for ln, nums in hdrs:
        first = nums[0]
        prev = blocks[-1] if blocks else None
        same_year = prev and any(n[:4] == first[:4] for n in prev["nums"])
        between = "\n".join(lines[prev["last"] + 1:ln]) if prev else ""
        own_decision = bool(_MARK.search(between) or _MARK.search(re.sub(r"\s+", " ", between)))
        if prev and (first in prev["nums"]
                     or (ln - prev["last"] <= _GAP and same_year and not own_decision)):
            prev["nums"].update(nums); prev["last"] = ln
        else:
            if prev:
                prev["end"] = ln
            blocks.append({"start": ln, "nums": set(nums), "last": ln})
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
            if _HDR_BROAD.match(l.strip()) or re.match(r"(?i)^(I\.|SUMMARY|STATEMENT|DECISION|\d)", s):
                break
            parties.append(s)
        out.append({"vol": vol, "numbers": sorted(b["nums"]), "parties": " ".join(parties)[:120],
                    "lines": (b["start"] + 1, b["end"]), "chars": len(body), "text": body})
    return out


def _all_table_nums():
    """Every case number anywhere in the table — a block number found here is a REAL case (even if
    the table filed it under a neighbouring GA); one found nowhere is true junk (listing/OCR noise)."""
    import sqlite3
    c = sqlite3.connect(f"{ROOT}/index/pca_minutes.db")
    out = set()
    for (cn, cnu) in c.execute("SELECT canonical_number, case_number FROM cases"):
        for raw in (cn, cnu):
            if raw and re.match(r"\d{2,4}-\d", raw):
                out.add(norm_num(raw))
    c.close()
    return out


def global_titles():
    """number -> best title across the WHOLE table (year-prefixed numbers are ~globally unique), so
    a block in a volume whose GA the table mis-files still gets a title."""
    import sqlite3
    c = sqlite3.connect(f"{ROOT}/index/pca_minutes.db")
    out = {}
    for cn, cnu, ti, pa in c.execute("SELECT canonical_number, case_number, title, parties FROM cases"):
        raw = cn or cnu or ""
        if not re.match(r"\d{2,4}-\d", raw):
            continue
        t = (ti or "").strip()
        if len(t) > 70 or re.search(r"(?i)was withdrawn|completed its work|does not (require|involve)", t):
            t = (pa or "").strip()
        k = norm_num(raw)
        if t and (k not in out or len(t) < len(out[k])):   # prefer a concise "X v. Y" title
            out[k] = t
    c.close()
    return out


def autotune_sjc(vol, ga, ga_year, universe=None):
    """Try each (broad, marker, bare) combo and score block-numbers against the cases table. Returns
    (best_params, score, blocks, detail). Junk is measured against the WHOLE-table universe (robust
    to the table's noisy ga_ordinal); recall against the cases plausibly decided in THIS volume."""
    import statistics
    universe = universe if universe is not None else _all_table_nums()
    T = set(table_meta(ga))                       # numbers the table files under THIS GA
    expected = {n for n in T if int(n[:4]) >= ga_year - 3}   # plausibly decided here (not old refs)
    # (broad, marker) x4; plus the dangerous BARE recognizer only WITH the marker gate.
    combos = [(b, m, False) for b in (False, True) for m in (False, True)]
    combos += [(False, True, True), (True, True, True)]
    best = None
    for broad, marker, bare in combos:
        blocks = extract_sjc(vol, broad, marker, bare)
        S = {n for b in blocks for n in b["numbers"]}
        real = len(S & universe)                  # block numbers that are real cases somewhere
        junk = len(S - universe)                  # block numbers found nowhere = listing/OCR noise
        # over-merge: numbers crammed past a generous AND-consolidation (~6) into one block — the
        # docket mega-block failure mode. Threshold is high so legitimate consolidated citations
        # (e.g. GA39's 2010-18..23, six siblings under one decision) aren't penalised.
        overmerge = sum(max(0, len(b["numbers"]) - 6) for b in blocks)
        med = statistics.median([b["chars"] for b in blocks]) if blocks else 0
        giant = sum(1 for b in blocks if med and b["chars"] > 6 * med and len(b["numbers"]) <= 1)
        # giant = a single-number block much longer than the volume median. This was a swallow proxy,
        # but now that own-decision splitting prevents merged decisions, a long single-number block is
        # usually just a long opinion (e.g. a 25k-char trial) — so only a MILD penalty, else it makes
        # autotune prefer a marker-gated strategy that drops real long decisions (regressed ga50).
        score = real - 3 * junk - 2 * overmerge - 1 * giant
        detail = {"blocks": len(blocks), "real": real, "matched": len(S & T), "junk": junk,
                  "overmerge": overmerge, "giant": giant,
                  "recall": round(len(S & expected) / max(1, len(expected)), 2)}
        # prefer higher score, then more real coverage, then fewer blocks (cleaner segmentation)
        key = (score, real, -len(blocks))
        if best is None or key > (best[1], best[3]["real"], -best[3]["blocks"]):
            best = ((broad, marker, bare), score, blocks, detail)
    return best


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
    # 2) §10-79 adjudication reports. Each report ends at the next report OR the next minute-
    # paragraph section header (e.g. "## 10-80 Special Prayer and Recess") — NOT a fixed window,
    # which made the LAST report swallow §10-80/§10-81/§10-85 (the post-§10-79 business).
    reports = []
    if rep0 is not None:
        hdr = re.compile(r"(?i)(report of .*commission|CASE\s*#\s*\d)")
        sec = re.compile(r"^\s*#{1,4}\s*\**\s*10-\d{2}\b")   # a numbered minute-paragraph heading
        starts = [i for i in range(rep0 + 1, len(lines)) if hdr.search(lines[i]) and "complaint" in lines[i].lower() or re.match(r"(?i)^\s*#*\s*CASE\s*#\s*\d", lines[i])]
        for j, s in enumerate(starts):
            e_next = starts[j + 1] if j + 1 < len(starts) else len(lines)
            # first minute-paragraph section header after this report (that isn't itself a report)
            e_sec = next((k for k in range(s + 1, e_next) if sec.match(lines[k]) and not hdr.search(lines[k])), e_next)
            e = min(e_next, e_sec)
            head = " ".join(re.sub(r"[*_#]", "", lines[k]).strip() for k in range(s, min(s + 3, e)))
            reports.append({"head": head[:120], "lines": (s, e), "names": _names(head)})
    # 3) match each complaint to a report by party names
    for c in complaints:
        cn = _names(c["head"])
        best = max(reports, key=lambda r: len(cn & r["names"]), default=None)
        c["match"] = best if best and len(cn & best["names"]) >= 1 else None
    return complaints, reports


def _yr(num):
    return int(num[:4])


def validate_sjc(vol, ga, ga_year):
    """Acceptance harness for one SJC volume. Cross-checks structure blocks (authoritative for
    text/boundaries) against the cases table (authoritative for identity), and runs per-block
    structural checks. Emits PASS / a list of flags — so review is driven by flags, not eyeballing.

    Returns (blocks, flags, recon) where recon classifies every number in S∪T."""
    blocks = extract_sjc(vol)
    meta = table_meta(ga)
    S = {n for b in blocks for n in b["numbers"]}
    T = set(meta)
    import statistics
    med = statistics.median([b["chars"] for b in blocks]) if blocks else 0
    flags = []
    for b in blocks:
        nums = b["numbers"]; lab = "/".join(nums)
        top = b["text"][:400]
        # 1) block names its own number near the top
        if not any(re.search(re.escape(n.split("-")[1].lstrip("0")) , top) and n[:4] in top for n in nums) \
           and not any(re.search(r"\b%s\b" % re.escape(n[2:].lstrip("0").replace("-0", "-")), top) for n in nums):
            if not any(n[:4] in top for n in nums):
                flags.append(f"{lab}: own case-number not found near top (possible mis-start)")
        # 2) identity resolvable
        if not any(meta.get(n, {}).get("title") for n in nums):
            flags.append(f"{lab}: no title — not in cases table (S-only) or table title empty")
        # 3) length sanity
        if b["chars"] < 400:
            flags.append(f"{lab}: very short ({b['chars']}c) — likely a fragment")
        if med and b["chars"] > 6 * med and len(nums) <= 1:
            flags.append(f"{lab}: very long ({b['chars']}c vs median {int(med)}c) — possible swallowed sibling/listing")
        # 4) forward-bleed: a LATER case number appears as a standalone header inside the block
        for ln in b["text"].split("\n")[3:]:
            hn = _hdrnum(ln)
            if hn and norm_num(hn) not in nums and norm_num(hn) in T and _yr(norm_num(hn)) >= _yr(nums[0]):
                flags.append(f"{lab}: contains header for {norm_num(hn)} (forward-bleed?)"); break
    # 5) dissent completeness
    for b in blocks:
        if any(meta.get(n, {}).get("dissent") for n in b["numbers"]) and \
           not re.search(r"(?i)dissent", b["text"]):
            flags.append(f"{'/'.join(b['numbers'])}: table flags a dissent but text has no 'dissent'")
    # reconciliation S vs T
    recon = {"matched": sorted(S & T), "structure_only": sorted(S - T), "table_only": []}
    for n in sorted(T - S):
        if _yr(n) < ga_year - 2:
            why = "reference to earlier GA (cited, not decided here)"
        elif re.search(r"(?i)withdrew|withdrawn|completed its work", meta[n]["title"] or ""):
            why = "journal/withdrawn (no decision text)"
        else:
            why = "table case with NO decision block — investigate (missed? consolidated? journal-only?)"
        recon["table_only"].append((n, why))
    return blocks, flags, recon


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
            meta = table_meta(cls.get(vol, {}).get("ga"))
            for c in extract_sjc(vol):
                slug = f"{vol}__{'_'.join(c['numbers'])}"
                # title from the cases table (authoritative identity); join on the block's numbers
                titles = [meta[n]["title"] for n in c["numbers"] if meta.get(n) and meta[n]["title"]]
                title = " / ".join(dict.fromkeys(titles)) or c["parties"][:90] or "_(untitled)_"
                dispos = [meta[n]["disposition"] for n in c["numbers"]
                          if meta.get(n) and meta[n]["disposition"]]
                head = f"*{vol}, source lines {c['lines'][0]}–{c['lines'][1]} · {c['chars']} chars*"
                if dispos:
                    head += "  ·  **Disposition:** " + "; ".join(dict.fromkeys(dispos))
                pg = [f"# {'/'.join(c['numbers'])} — {title}", "", head, "", "---", "", c["text"]]
                open(f"{outdir}/{slug}.md", "w").write("\n".join(pg) + "\n")
                idx.append(f"- [{'/'.join(c['numbers'])}]({os.path.basename(outdir)}/{slug}.md) — {title[:80]}")
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
    elif len(sys.argv) >= 2 and sys.argv[1] == "autotune":
        import json
        cls = json.load(open(f"{ROOT}/index/case_volume_class.json"))
        sjc = sorted([(v["ga"], k) for k, v in cls.items() if v.get("class") == "SJC-decision"])
        vols = sys.argv[2:] or [k for _, k in sjc]
        chosen = {}
        if os.path.exists(f"{ROOT}/index/sjc_strategy.json"):
            chosen = json.load(open(f"{ROOT}/index/sjc_strategy.json"))
        universe = _all_table_nums()
        for vol in vols:
            ga = cls[vol]["ga"]; yr = int(cls[vol]["year"])
            (broad, marker, bare), score, blocks, d = autotune_sjc(vol, ga, yr, universe)
            chosen[vol] = {"broad": broad, "marker": marker, "bare": bare, "score": score, **d}
            print(f"{vol:14} b={int(broad)} m={int(marker)} bare={int(bare)} score={score:>4}  "
                  f"blocks={d['blocks']:>3} real={d['real']:>3} matched={d['matched']:>3} "
                  f"junk={d['junk']:>3} overmerge={d['overmerge']:>3} giant={d['giant']} recall={d['recall']}")
        if len(sys.argv) == 2:  # full run -> persist
            json.dump(chosen, open(f"{ROOT}/index/sjc_strategy.json", "w"), indent=1)
            print(f"\nwrote index/sjc_strategy.json ({len(chosen)} volumes)")
    elif len(sys.argv) >= 3 and sys.argv[1] == "validate":
        import json
        cls = json.load(open(f"{ROOT}/index/case_volume_class.json"))
        vol = sys.argv[2]; ga = cls[vol]["ga"]; yr = int(cls[vol]["year"])
        blocks, flags, recon = validate_sjc(vol, ga, yr)
        print(f"== {vol} (GA{ga}, {yr}) ==  {len(blocks)} blocks")
        print(f"matched (block+table): {len(recon['matched'])}  {recon['matched']}")
        if recon["structure_only"]:
            print(f"STRUCTURE-ONLY (block but no table row): {recon['structure_only']}")
        for n, why in recon["table_only"]:
            print(f"  table-only {n}: {why}")
        print(f"\n{len(flags)} block flags:" if flags else "\nno block flags — PASS")
        for f in flags:
            print("  ⚠ " + f)
    elif len(sys.argv) >= 3 and sys.argv[1] == "sjc":
        cs = extract_sjc(sys.argv[2])
        print(f"{len(cs)} case blocks in {sys.argv[2]}:")
        for c in cs:
            print(f"  {'/'.join(c['numbers']):16} L{c['lines'][0]}-{c['lines'][1]} {c['chars']:>6}c  {c['parties'][:60]}")
    else:
        print(__doc__)
