#!/usr/bin/env python3
"""30_inquiry_pages.py — render the Constitutional Inquiry layer to markdown.

Reads (from <ROOT>/index/):
  - inquiries_roster.json   : Digest Part II roster — identity + the Digest's summary prose (headnote)
  - inquiries_located.json  : per-GA verbatim line-ranges in the minutes (advice + posed; page anchors)

Slices the verbatim record from <ROOT>/markdown/ and writes, mirroring CASES.md / cases/*:
  - <ROOT>/inquiries/<stem>__ci<NN>.md  : one page per inquiry (Digest headnote + verbatim record + deep-links)
  - <ROOT>/index/INQUIRIES.md           : the catalogue, grouped by Assembly

Usage:  30_inquiry_pages.py [ROOT]      (ROOT defaults to /workspace)

Per SPEC-INQUIRIES.md: the headnote is an EDITORIAL summary (here, the PCA Digest's Part II text,
attributed and clearly separated) and is NOT bound to verbatim; it deep-links to the verbatim source
in the minutes, which is sliced unaltered below it.
"""
from __future__ import annotations
import json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")
OUT = os.path.join(ROOT, "inquiries")

_LOCATOR = re.compile(r"^\s*\d{4},\s*p\.\s*\d+[a-zA-Z]?,\s*\d+-\d+,?\s*[\w.]*\.?\s*")
_md_lines_cache: dict[str, list[str]] = {}


def ordinal(n: int) -> str:
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def md_escape(s) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def md_lines(stem: str) -> list[str]:
    if stem not in _md_lines_cache:
        p = os.path.join(MD, stem + ".md")
        _md_lines_cache[stem] = open(p, encoding="utf-8").read().split("\n") if os.path.exists(p) else []
    return _md_lines_cache[stem]


def slice_md(stem: str, a, b) -> str:
    """1-based inclusive slice of a volume's markdown."""
    if not (a and b):
        return ""
    lines = md_lines(stem)
    a = max(1, int(a)); b = min(len(lines), int(b))
    return "\n".join(lines[a - 1:b]).strip()


def clean_summary(s: str) -> str:
    return _LOCATOR.sub("", (s or "").strip()).strip()


def is_bare_provision(t: str) -> bool:
    return bool(re.fullmatch(r"(BCO|WCF|RAO)?\s*\d+[-.\d]*\s*", (t or "")))


def kind_of(e: dict) -> str:
    """Two buckets: the CCB's advice on a proposed overture/amendment, vs. a constitutional
    inquiry (a non-judicial reference asking what the Constitution means).

    The disposition is the primary signal: a CCB "in conflict / not in conflict" ruling is review
    of a PROPOSED change, never the answer to a question about meaning — so it overrides the
    source-based `kind` (a stated-clerk reference of a proposed amendment still gets a conflict
    ruling and belongs with overture advice)."""
    AMEND = "Overture/amendment advice"
    INQ = "Constitutional inquiry"
    disp = (e.get("disposition") or "").lower()
    if re.search(r"in conflict|conflict with the constitution|creates?\b[^.]*conflict", disp):
        return AMEND
    if e.get("kind") == "overture-advice":
        return AMEND
    if re.search(r"\boverture\s+\d", (e.get("source") or "").lower()):
        return AMEND
    if e.get("kind"):   # reference / communication / other, with no conflict ruling
        return INQ
    blob = f"{disp} {(e.get('summary','') or '')[:160]}".lower()
    if re.search(r"\bin conflict\b|\boverture\s+\d", blob):
        return AMEND
    return INQ


def deeplink(stem: str, anchor: str, printed) -> str:
    label = f"{stem} p.{printed}" if printed else stem
    frag = f"#{anchor}" if anchor else ""
    return f"[{label}](../markdown/{stem}.md{frag})"


def main():
    roster = json.load(open(os.path.join(IDX, "inquiries_roster.json")))
    located = json.load(open(os.path.join(IDX, "inquiries_located.json")))

    # roster lookup. The locate agents sometimes append a section to minute_para
    # ("App. O, section IV" vs the roster's "App. O"), so normalize it and also key by topic.
    def norm_mp(s):
        return (s or "").split(",")[0].strip()
    rmap, rmap_mp, rmap_topic = {}, {}, {}
    for e in roster:
        rmap[(e["ga_ordinal"], norm_mp(e.get("minute_para")), e.get("topic"))] = e
        rmap_mp.setdefault((e["ga_ordinal"], norm_mp(e.get("minute_para"))), e)
        rmap_topic.setdefault((e["ga_ordinal"], e.get("topic")), e)

    # group located results into one page per distinct verbatim passage (ord, advice_start, advice_end)
    groups: dict = {}
    for g in located:
        for r in g["results"]:
            key = (g["ga_ordinal"], r.get("advice_start"), r.get("advice_end"))
            grp = groups.setdefault(key, {"ord": g["ga_ordinal"], "stem": g["stem"], "results": []})
            grp["results"].append(r)

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".md"):
            os.remove(os.path.join(OUT, f))

    per_vol = {}
    inq_rows, adv_rows = {}, {}   # ord -> list of (year, stem, row), split by Type
    n_pages = 0

    for key in sorted(groups, key=lambda k: (k[0], k[1] or 0)):
        grp = groups[key]
        ordn, stem, results = grp["ord"], grp["stem"], grp["results"]
        rents = []
        for r in results:
            e = (rmap.get((ordn, norm_mp(r.get("minute_para")), r.get("topic")))
                 or rmap_topic.get((ordn, r.get("topic")))
                 or rmap_mp.get((ordn, norm_mp(r.get("minute_para")))) or {})
            rents.append((r, e))
        r0, e0 = rents[0]

        topics = [e.get("topic") for _, e in rents if e.get("topic")]
        provs = []
        for _, e in rents:
            for p in (e.get("provisions") or []):
                if p and p not in provs:
                    provs.append(p)
        summaries = []
        for _, e in rents:
            s = clean_summary(e.get("summary", ""))
            if s and s not in summaries:
                summaries.append(s)
        source = next((e.get("source") for _, e in rents if e.get("source")), "")
        disp = next((e.get("disposition") for _, e in rents if e.get("disposition")), "")
        gen_subject = next((e.get("gen_subject") for _, e in rents if e.get("gen_subject")), "")
        synopsis = next((e.get("synopsis") for _, e in rents if e.get("synopsis")), "")
        mtype = kind_of(next((e for _, e in rents if e), {}) or r0)
        ci = (r0.get("inquiry_number") or "").strip()
        year = e0.get("year")
        printed = e0.get("printed_page")
        anchor = (r0.get("page_anchor") or "").strip()
        ma = re.match(r"ga(\d+)-p(.+)$", anchor)   # markdown anchors zero-pad the ordinal (ga04, not ga4)
        if ma:
            anchor = f"ga{int(ma.group(1)):02d}-p{ma.group(2)}"
        sect = e0.get("ccb_section", "")

        # display subject
        subj = gen_subject or next((t for t in topics if not is_bare_provision(t)), "")
        if not subj:
            subj = (summaries[0][:80].rsplit(" ", 1)[0] + "…") if summaries else (topics[0] if topics else "Constitutional inquiry")
        label = ci or (f"{e0.get('minute_para','')} {sect}".strip()) or "Inquiry"

        n = per_vol.get(stem, 0) + 1
        per_vol[stem] = n
        slug = f"{stem}__ci{n:02d}"

        a, b = r0.get("advice_start"), r0.get("advice_end")
        body = slice_md(stem, a, b) or "_(verbatim passage not located in this volume)_"
        posed = ""
        if r0.get("posed_start") and r0.get("posed_end"):
            posed = slice_md(stem, r0["posed_start"], r0["posed_end"])
        ratified_only = (r0.get("answer_in_volume") is False)

        # ---- page ----
        hdr = ["**Body:** Committee on Constitutional Business (CCB)", f"**Type:** {mtype}",
               f"**Assembly:** {ordinal(ordn)} ({year})"]
        if provs:
            hdr.append("**Provisions:** " + ", ".join(provs))
        if disp:
            hdr.append("**Disposition:** " + md_escape(disp))
        srcline = (f"*Source: [{stem} lines {a}–{b}](../markdown/{stem}.md{'#' + anchor if anchor else ''})*"
                   if a and b else f"*Source: {stem}*")

        page = [f"# {label} — {subj}", ""]
        if synopsis:
            page += [f"*{md_escape(synopsis)}*", ""]
        page += ["  ·  ".join(hdr), "", srcline, "", "---", ""]
        if summaries:
            page += ["## Digest headnote",
                     "*Editorial summary from the PCA Digest, Part II (Interpretations of the Constitution) — "
                     "this is the Digest's wording, not the verbatim minutes. The authoritative text is the "
                     "verbatim record below / linked above.*", ""]
            if len(summaries) == 1:
                page += [summaries[0], ""]
            else:
                page += [f"- {s}" for s in summaries] + [""]
            if provs:
                page += ["**Key words:** " + ", ".join(provs), ""]
            if source:
                page += ["**Inquiry from:** " + md_escape(source), ""]
            page += ["**In the minutes:** " + deeplink(stem, anchor, printed), "", "---", ""]
        page += ["## Verbatim record", ""]
        if ratified_only:
            page += ["*The General Assembly ratified this advice by reference; the substantive answer "
                     "is not printed as a separate passage in this volume. The ratifying action is quoted "
                     "below.*", ""]
        if posed:
            page += ["### As referred / posed", "", posed, "", "### CCB advice", "", body, ""]
        else:
            page += [body, ""]
        is_inq = (mtype == "Constitutional inquiry")
        back = ("[← Constitutional inquiry index](../index/INQUIRIES.md)" if is_inq
                else "[← Overture/amendment advice index](../index/CCB-OVERTURE-ADVICE.md)")
        page += ["---", "", back]
        open(os.path.join(OUT, slug + ".md"), "w", encoding="utf-8").write("\n".join(page) + "\n")
        n_pages += 1

        row = (f"| {md_escape(label)} | [{md_escape(subj)}](../inquiries/{slug}.md) | "
               f"{md_escape(synopsis)} | {md_escape(', '.join(provs))} | {md_escape(disp)} | "
               f"{md_escape(source)} | {deeplink(stem, anchor, printed)} |")
        (inq_rows if is_inq else adv_rows).setdefault(ordn, []).append((year, stem, row))

    common = ("Each entry pairs a **Digest-level headnote** (the PCA Digest's editorial summary, Part II) "
              "with the **verbatim record** sliced from the minutes; the **Minutes** column deep-links to "
              "the source page. **Subject** and **Synopsis** are distilled from the Digest's own text. The "
              "roster is drawn from the PCA Digest, Part II (1973–2018); later Assemblies are extracted "
              "directly from each volume's CCB report.")

    def write_catalogue(path, title, blurb, rows_by_ord, crosslink):
        L = [f"# {title}", "", blurb, "", common, "", crosslink, ""]
        total = 0
        for ordn in sorted(rows_by_ord):
            rows = rows_by_ord[ordn]
            year, stem = rows[0][0], rows[0][1]
            L += ["", f"## {ordinal(ordn)} General Assembly ({year})  ·  `{stem}`", "",
                  "| Inquiry | Subject | Synopsis | Provisions | Outcome | From | Minutes |",
                  "|---|---|---|---|---|---|---|"]
            for _, _, row in rows:
                L.append(row)
                total += 1
        open(os.path.join(IDX, path), "w", encoding="utf-8").write("\n".join(L) + "\n")
        return total

    n_inq = write_catalogue(
        "INQUIRIES.md", "Constitutional Inquiry Catalogue",
        "Questions of *constitutional interpretation* (Westminster Standards, *Book of Church Order*, "
        "*Rules of Assembly Operations*) referred to the **Committee on Constitutional Business (CCB)** — "
        "and, before the 18th General Assembly, the Committee on Judicial Business — answered with "
        "**non-binding advice**. Grouped by Assembly.",
        inq_rows,
        "*The CCB's advice on whether proposed overtures/amendments conflict with the Constitution is "
        "catalogued separately in **[Overture & amendment advice](CCB-OVERTURE-ADVICE.md)**.*")

    n_adv = write_catalogue(
        "CCB-OVERTURE-ADVICE.md", "CCB Advice on Overtures & Proposed Amendments",
        "The **Committee on Constitutional Business (CCB)**'s advice on whether a proposed overture or "
        "amendment is *in conflict* with the Constitution (its constitutional review of proposed changes, "
        "distinct from answering questions about what the Constitution means). Grouped by Assembly.",
        adv_rows,
        "*Genuine constitutional inquiries / non-judicial references (questions about the Constitution's "
        "meaning) are catalogued separately in **[Constitutional inquiries](INQUIRIES.md)**.*")

    print(f"[{ROOT}] wrote {n_pages} pages; INQUIRIES.md ({n_inq} inquiries across {len(inq_rows)} GAs), "
          f"CCB-OVERTURE-ADVICE.md ({n_adv} advices across {len(adv_rows)} GAs)")


if __name__ == "__main__":
    main()
