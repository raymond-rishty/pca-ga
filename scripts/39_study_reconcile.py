#!/usr/bin/env python3
"""39_study_reconcile.py — reconcile the located study-paper records against the pcahistory roster.

Per SPEC-STUDIES.md §4/§8.5: the PCA Historical Center "Studies & Reports" index is the completeness
checklist. Every rostered topic must map to a located document, or be reported as a precise gap —
the catalogue reconciles to the roster, and documents found but absent from the roster are surfaced
(no silent drops).

Reads:   index/studies_roster.json   (the checklist; topic + alias keywords)
         index/studies_pages.json    (located documents, from 37)
Writes:  index/studies_reconciliation.md   (covered / not-located / extra)
         index/studies_pages.json    (annotated in place with roster_topic where matched)
Usage:   39_study_reconcile.py [ROOT]
"""
from __future__ import annotations
import json, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, "index")


def ordinal(n):
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def hay(r):
    return f"{r.get('topic','')} {r.get('title','')}".lower()


def main():
    roster = json.load(open(os.path.join(IDX, "studies_roster.json"), encoding="utf-8"))
    recs = json.load(open(os.path.join(IDX, "studies_pages.json"), encoding="utf-8"))

    matched_recs = set()           # ids of located docs matched to some roster topic
    coverage = []                  # (roster_topic, [matched docs])
    for entry in roster:
        hits = []
        for i, r in enumerate(recs):
            if any(a.lower() in hay(r) for a in entry["aliases"]):
                hits.append(i)
                matched_recs.add(i)
                r["roster_topic"] = entry["topic"]   # annotate canonical topic in place
        coverage.append((entry, hits))

    located = [e for e, h in coverage if h]
    notloc = [e for e, h in coverage if not h]
    extra = [r for i, r in enumerate(recs) if i not in matched_recs]

    # write annotated records back so the index (38) can prefer the canonical roster_topic
    json.dump(recs, open(os.path.join(IDX, "studies_pages.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    L = [
        "# Study Papers — roster reconciliation",
        "",
        f"Located documents reconciled against the PCA Historical Center "
        f"[Studies & Reports](https://www.pcahistory.org/pca/digest/studies/) roster "
        f"({len(roster)} topics).",
        "",
        f"- **{len(located)}/{len(roster)}** roster topics have ≥1 located document",
        f"- **{len(notloc)}** roster topics **not located** (gaps)",
        f"- **{len(extra)}** located documents not yet matched to a roster topic",
        "",
        "## Covered roster topics",
        "",
        "| Roster topic | Documents located |",
        "|---|---|",
    ]
    for e, h in coverage:
        if not h:
            continue
        docs = "; ".join(
            f"[{ordinal(recs[i]['ga_ordinal']) if recs[i].get('ga_ordinal') else 'PCA HC'}]"
            f"(../studies/{recs[i]['file']})" for i in h)
        L.append(f"| {e['topic']} | {docs} |")

    L += ["", "## Not located (roster gaps)", "",
          "*In the pcahistory roster but no document located in the corpus yet — the honest gap "
          "(SPEC-STUDIES.md §8.5). Many are floor resolutions, RPCES-era documents, or topics "
          "filed under a committee report not yet split out.*", "",
          "| Roster topic | Era / citation |", "|---|---|"]
    for e in notloc:
        hint = e.get("era", "") or e.get("citation", "") or "—"
        L.append(f"| {e['topic']} | {hint} |")

    if extra:
        L += ["", "## Located but not in roster", "",
              "*Documents detected in the corpus that don't match a roster topic — candidate "
              "additions to the roster, or finer-grained sub-reports.*", ""]
        for r in extra:
            L.append(f"- {ordinal(r['ga_ordinal'])} ({r['year']}) — "
                     f"[{r['topic']}](../studies/{r['file']})")

    L.append("")
    open(os.path.join(IDX, "studies_reconciliation.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"roster: {len(roster)} topics | located: {len(located)} | not-located: {len(notloc)} | "
          f"extra docs: {len(extra)}")
    print("not located:", ", ".join(e["topic"] for e in notloc))


if __name__ == "__main__":
    main()
