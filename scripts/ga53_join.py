#!/usr/bin/env python3
"""ga53_join.py — deterministic provision-join SPINE for one GA53 overture.

Given an overture number (O<NN>), print every past action in the corpus that CITES one of the
overture's target BCO/RAO provisions — the complete, auditable hit-list a workflow agent then
enriches (semantic links, dedup of incidental hits) into the final per-overture page.

Sources (in /workspace/index):
  cases.jsonl              cases by `bco_cited_current` / `bco_cited_as`     (+ case_pages_map.json for links)
  INQUIRIES.md             constitutional inquiries, Provisions column
  CCB-OVERTURE-ADVICE.md   CCB advice on overtures/amendments, Provisions column
  OVERTURES.md             prior overtures (+ overture_bodies.jsonl to match by provision in body)
  RPR-BY-PROVISION.md      RPR exceptions grouped under `## <provision>` headers

Usage:  python3 ga53_join.py O37        # human-readable
        python3 ga53_join.py O37 --json # machine-readable
"""
from __future__ import annotations
import json, os, re, sys

IDX = "/workspace/index"
SRC = "/workspace/ga53"


def load_targets(num):
    for ln in open(os.path.join(SRC, "overtures_full.tsv"), encoding="utf-8"):
        p = ln.rstrip("\n").split("\t")
        if p and p[0] == num:
            return p[1], p[2], p[3], (p[4] if len(p) > 4 else "")
    raise SystemExit(f"{num} not found")


def parse_provisions(targets: str):
    """-> (sections, chapters) e.g. ({'BCO 9-3'}, {('BCO',9)}); handles ranges & lists."""
    secs, chaps = set(), set()
    kind = "BCO"
    # find typed runs: a BCO/RAO keyword sets context for following bare numbers
    toks = re.split(r"[,\s]+", targets)
    for t in toks:
        u = t.upper().strip("().")
        if u in ("BCO", "RAO"):
            kind = u
            continue
        m = re.match(r"(BCO|RAO)?(\d+)-(\d+)\.\.(\d+)", t, re.I)  # range 21-1..21-4
        if m:
            if m.group(1):
                kind = m.group(1).upper()
            ch = int(m.group(2))
            for s in range(int(m.group(3)), int(m.group(4)) + 1):
                secs.add(f"{kind} {ch}-{s}")
            chaps.add((kind, ch))
            continue
        m = re.match(r"(BCO|RAO)?(\d+)-(\d+[A-Za-z]?)", t, re.I)   # section X-Y(.letter)
        if m:
            if m.group(1):
                kind = m.group(1).upper()
            ch = int(m.group(2)); sec = re.sub(r"[A-Za-z.].*$", "", m.group(3))
            secs.add(f"{kind} {ch}-{sec}")
            chaps.add((kind, ch))
            continue
        m = re.match(r"(BCO|RAO)?(\d+)[A-Za-z]?$", t, re.I)        # bare chapter
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                kind = m.group(1).upper()
            chaps.add((kind, int(m.group(2))))
    return secs, chaps


def sec_bare(s):  # 'BCO 9-3' -> '9-3'
    return s.split(" ", 1)[1]


# ---------- cases ----------
def join_cases(secs, chaps):
    bare = {sec_bare(s) for s in secs if s.startswith("BCO")}
    chap_nums = {c for (k, c) in chaps if k == "BCO"}
    cmap = json.load(open(os.path.join(IDX, "case_pages_map.json")))
    by_num = {n: v for n, v in cmap.items()}
    out = []
    for r in (json.loads(l) for l in open(os.path.join(IDX, "cases.jsonl"))):
        cited = set(r.get("bco_cited_current") or []) | set(r.get("bco_cited_as") or [])
        exact = bare & cited
        if not exact:
            continue
        ga, yr = r.get("ga_ordinal"), r.get("year")
        page = r.get("pdf_page_start")
        vol = f"ga{ga:02d}_{yr}" if ga and yr else None
        anchor = f"{vol}.md#ga{ga}-p{page}" if vol and page else (vol + ".md" if vol else "")
        cn = r.get("case_number")
        cfile = by_num.get(cn, {}).get("file") if cn else None
        out.append({"num": cn, "title": r.get("title"), "disposition": r.get("disposition"),
                    "ga": ga, "year": yr, "provisions": sorted(exact),
                    "case_page": f"../cases/{cfile}.md" if cfile else None,
                    "minutes": f"../markdown/{anchor}" if anchor else None})
    out.sort(key=lambda x: (x["year"] or 0))
    return out


# ---------- rendered-catalogue table parsing ----------
def parse_table(path):
    """yield (current_ga_header, [cells]) for every data row of every pipe-table in the file."""
    ga = None
    for ln in open(os.path.join(IDX, path), encoding="utf-8"):
        h = re.match(r"##\s+(.*General Assembly.*)", ln)
        if h:
            ga = h.group(1).strip()
            continue
        if ln.startswith("|") and "---" not in ln:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells and cells[0].lower() not in ("inquiry", "overture", "presbytery", "provision"):
                yield ga, cells


def prov_in_cell(cell, secs):
    return any(re.search(r"(?<![\d-])" + re.escape(s) + r"(?![\d-])", cell) for s in secs)


def join_inquiries(path, secs):
    out = []
    for ga, c in parse_table(path):
        if len(c) >= 4 and prov_in_cell(c[3], secs):   # cols: id|subject|synopsis|provisions|...
            out.append({"ga": ga, "id": c[0], "subject": c[1], "provisions": c[3],
                        "outcome": c[4] if len(c) > 4 else "", "row": "| " + " | ".join(c) + " |"})
    return out


def join_overtures(secs, chaps):
    # match by provision appearing in the overture BODY, then attach the OVERTURES.md row
    sec_pat = [s for s in secs]
    bodies = {}
    for r in (json.loads(l) for l in open(os.path.join(IDX, "overture_bodies.jsonl"))):
        b = r.get("body", "")
        # strip markdown emphasis so "_RAO_ 4-21.d" still matches "RAO 4-21"
        bn = b.replace("_", "")
        if any(re.search(r"(?<![\d-])" + re.escape(s) + r"(?![\d-])", bn) for s in sec_pat):
            bodies[(r["ga_ordinal"], r["number"])] = r
    # NOTE: do NOT early-return on empty bodies — titles in OVERTURES.md (clean, no emphasis)
    # routinely name the provision even when the body uses _emphasis_; the title pass below catches them.
    # walk OVERTURES.md to get subject/outcome/link rows keyed by (ga_ordinal, number)
    rows = {}
    ga_ord = None
    for ln in open(os.path.join(IDX, "OVERTURES.md"), encoding="utf-8"):
        m = re.match(r"##\s+(\d+)(?:st|nd|rd|th) General Assembly \((\d+)\)", ln)
        if m:
            ga_ord = int(m.group(1)); continue
        if ln.startswith("|") and "---" not in ln and ga_ord:
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if c and c[0].isdigit():
                rows[(ga_ord, int(c[0]))] = c
    # ALSO match by OVERTURES.md subject cell (titles routinely name the provision, e.g.
    # "Amend BCO 32-19 to Expand Representation…") — catches recent overtures body-grep misses.
    keys = set(bodies)
    for (ga, n), c in rows.items():
        subj = c[1] if len(c) > 1 else ""
        if any(re.search(r"(?<![\d-])" + re.escape(s) + r"(?![\d-])", subj) for s in sec_pat):
            keys.add((ga, n))
    out = []
    for (ga, n) in sorted(keys):
        c = rows.get((ga, n))
        r = bodies.get((ga, n), {})
        out.append({"ga": ga, "number": n, "source": r.get("source") or (c[3] if c and len(c) > 3 else ""),
                    "subject": c[1] if c else "(see body)",
                    "outcome": c[2] if c else "",
                    "pages": c[4] if c and len(c) > 4 else "",
                    "matched_by": "body+title" if (ga, n) in bodies else "title",
                    "row": ("| " + " | ".join(c) + " |") if c else None})
    return out


def join_rpr(secs):
    text = open(os.path.join(IDX, "RPR-BY-PROVISION.md"), encoding="utf-8").read()
    blocks = re.split(r"\n## ", text)
    want = {sec_bare(s) for s in secs}  # rpr headers are "BCO 9-3" -> compare bare too
    full = set(secs)
    out = []
    for b in blocks:
        head = b.split("\n", 1)[0].strip()           # e.g. "BCO 9-3  ·  9 citation(s)"
        prov = head.split("·")[0].strip()
        if prov in full or prov.replace("BCO ", "").replace("RAO ", "") in want:
            rows = [l for l in b.splitlines() if l.startswith("|") and "---" not in l
                    and not l.lower().startswith("| presbytery")]
            out.append({"provision": prov, "n_rows": len(rows), "rows": rows})
    return out


def main():
    num = sys.argv[1]
    as_json = "--json" in sys.argv
    targets, title, source, url = load_targets(num)
    secs, chaps = parse_provisions(targets)
    res = {"overture": num, "title": title, "source": source, "url": url,
           "targets": targets, "provisions": sorted(secs), "chapters": sorted(map(list, chaps))}
    if secs:
        res["cases"] = join_cases(secs, chaps)
        res["inquiries"] = join_inquiries("INQUIRIES.md", secs)
        res["ccb_advice"] = join_inquiries("CCB-OVERTURE-ADVICE.md", secs)
        res["prior_overtures"] = join_overtures(secs, chaps)
        res["rpr"] = join_rpr(secs)
    else:
        res["note"] = "non-provision overture (boundaries/prayer/statement/committee) — topical search only"
    if as_json:
        print(json.dumps(res, indent=2)); return
    print(f"# {num} — {title}\nTargets: {targets}   provisions={sorted(secs)}\n")
    for key in ("cases", "inquiries", "ccb_advice", "prior_overtures", "rpr"):
        v = res.get(key, [])
        print(f"== {key}: {len(v)} ==")
        for x in v[:40]:
            print("  ", json.dumps(x)[:300])
        print()


if __name__ == "__main__":
    main()
