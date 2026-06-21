#!/usr/bin/env python3
"""38_study_index.py — build the catalogue index from the located study-paper record set.

Per SPEC-STUDIES.md §7: the index is a PROJECTION over the records (capture once, project freely).
Primary view = alphabetical by topic (matching pcahistory's "Studies & Reports"); a compact
chronological view follows. Both are generated from index/studies_pages.json (written by 37).

Writes:  <ROOT>/index/STUDIES.md
Usage:   38_study_index.py [ROOT]
"""
from __future__ import annotations
import json, os, re, sys
from collections import defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, "index")

ACRONYMS = {"Pca": "PCA", "Bco": "BCO", "Aids": "AIDS", "Rpces": "RPCES", "Mna": "MNA",
            "Opc": "OPC", "Rpcna": "RPCNA", "Naparc": "NAPARC", "Nae": "NAE", "Wic": "WIC"}


def ordinal(n: int) -> str:
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def md_escape(s) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def topic_key(topic: str) -> str:
    """Grouping/sort key: leading articles, reprints, majority-minority pairs, year/part variants
    collapse to one topic."""
    k = topic.upper()
    k = re.sub(r"^(THE|A|AN)\s+", "", k)
    k = re.sub(r"\b(MAJORITY|MINORITY|INITIAL|FINAL|PRELIMINARY)\s+REPORT\b", "", k)
    k = re.sub(r"\bPARTS?\s+[IVX]+(\s*[-–]\s*[IVX]+)?\b", "", k)
    k = re.sub(r"[^A-Z0-9 ]", " ", k)
    return re.sub(r"\s+", " ", k).strip()


def display_topic(topic: str) -> str:
    t = topic.title() if topic.isupper() or topic.islower() else topic
    return " ".join(ACRONYMS.get(w, w) for w in t.split())


def minutes_link(r) -> str:
    if r.get("external_url"):
        return f"[PCA Historical Center]({r['external_url']})"
    pp = r["printed_pages"]
    label = (f"pp. {pp[0]}–{pp[-1]}" if len(pp) > 1 else f"p. {pp[0]}") if pp else "see report"
    anchor = r["anchor_start"] or ""
    return f"[{r['vol']} {label}](../markdown/{r['vol']}.md#{anchor})"


def assembly_cell(r) -> str:
    if r.get("ga_ordinal"):
        return f"{ordinal(r['ga_ordinal'])} ({r['year']})"
    return str(r["year"]) if r.get("year") else "—"


def main():
    recs = json.load(open(os.path.join(IDX, "studies_pages.json"), encoding="utf-8"))

    # prefer the canonical roster topic (set by 39_study_reconcile) over the raw heading topic
    for r in recs:
        r['_topic'] = r.get("roster_topic") or r["topic"]

    groups = defaultdict(list)
    for r in recs:
        groups[topic_key(r['_topic'])].append(r)

    lines = [
        "# PCA Position Papers & Study Committee Reports",
        "",
        "The denomination's **position papers** — study committee reports, reports of ad-interim "
        "committees, pastoral letters, declarations and statements of conscience, messages to the "
        "churches, and adopted position resolutions. Each links to the **full verbatim report** in "
        "the minutes. The roster follows the PCA Historical Center's "
        "[Studies & Reports](https://www.pcahistory.org/pca/digest/studies/) index.",
        "",
        f"*{len(recs)} documents across {len({r['ga_ordinal'] for r in recs if r.get('ga_ordinal')})} "
        "Assemblies. Most link to the **full verbatim report in the minutes**; roster topics not in "
        "the digitized corpus link to the **PCA Historical Center** copy (labeled on the page).*",
        "",
        "## By topic",
        "",
    ]

    for key in sorted(groups):
        members = sorted(groups[key], key=lambda r: (r["ga_ordinal"] or 99, r["line_start"]))
        lines.append(f"### {display_topic(members[0]['_topic'])}")
        lines.append("")
        lines.append("| Document | Type | Assembly | Source |")
        lines.append("|---|---|---|---|")
        for r in members:
            doc = f"[{md_escape(display_topic(r['_topic']))}](../studies/{r['file']})"
            lines.append(f"| {doc} | {r['kind_label']} | {assembly_cell(r)} | {minutes_link(r)} |")
        lines.append("")

    # compact chronological projection (externally-hosted, GA-less docs grouped at the end)
    lines += ["## Chronological", ""]
    by_ga = defaultdict(list)
    external = []
    for r in recs:
        (external if not r.get("ga_ordinal") else by_ga[(r["ga_ordinal"], r["year"])]).append(r)
    for (ga, yr) in sorted(by_ga):
        items = "; ".join(f"[{md_escape(display_topic(r['_topic']))}](../studies/{r['file']})"
                          for r in sorted(by_ga[(ga, yr)], key=lambda r: r["line_start"]))
        lines.append(f"- **{ordinal(ga)} GA ({yr})** — {items}")
    if external:
        items = "; ".join(f"[{md_escape(display_topic(r['_topic']))}](../studies/{r['file']})"
                          for r in sorted(external, key=lambda r: r['_topic']))
        lines.append(f"- **PCA Historical Center** (not in the digitized minutes corpus) — {items}")
    lines.append("")

    dest = os.path.join(IDX, "STUDIES.md")
    open(dest, "w", encoding="utf-8").write("\n".join(lines))
    print(f"wrote {dest} — {len(recs)} documents in {len(groups)} topic groups")


if __name__ == "__main__":
    main()
