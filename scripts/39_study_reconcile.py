#!/usr/bin/env python3
"""39_study_reconcile.py — reconcile located study-paper records against document-level roster rows.

The PCA Historical Center roster is a completeness checklist, but one roster topic can contain
multiple papers. This pass therefore matches *documents*, not loose topic aliases.

Reads:   index/studies_roster.json   (document checklist; topic + paper title + hints)
         index/studies_pages.json    (located documents, from 37)
Writes:  index/studies_reconciliation.md
         index/studies_pages.json    (annotated with roster_topic / roster_paper_title when matched)
Usage:   39_study_reconcile.py [ROOT]
"""
from __future__ import annotations
import json, os, re, sys
from difflib import SequenceMatcher

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, "index")
EXACT_THRESHOLD = 80
TENTATIVE_THRESHOLD = 45


def ordinal(n):
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def tokens(s):
    return set(norm(s).split())


def numbers(s):
    return {int(x) for x in re.findall(r"\d+", str(s or ""))}


def expected(entry):
    return entry.get("expected") or entry.get("hints") or {}


def rec_pages(rec):
    vals = set()
    for p in rec.get("printed_pages") or []:
        if isinstance(p, int): vals.add(p)
        else: vals |= numbers(p)
    vals |= numbers(rec.get("file"))
    return vals


def doc_label(rec):
    asm = f"{ordinal(rec['ga_ordinal'])} ({rec.get('year')})" if rec.get("ga_ordinal") else "PCA HC"
    return f"{asm} — [{rec.get('topic') or rec.get('title')}](../studies/{rec['file']})"


def row_label(e):
    title = e.get("paper_title") or e.get("topic")
    return f"{e.get('topic')} — {title}" if title != e.get("topic") else title


def score(entry, rec):
    """Return (score, reasons). Hints outrank names; topic-only is intentionally weak."""
    exp = expected(entry)
    reasons, s = [], 0
    ega = exp.get("ga_ordinal") or entry.get("ga_ordinal")
    eyear = entry.get("year") or exp.get("year")
    epages = set(exp.get("pages") or exp.get("page") or []) if isinstance(exp.get("pages") or exp.get("page") or [], list) else numbers(exp.get("pages") or exp.get("page"))
    if ega and rec.get("ga_ordinal") == ega:
        s += 35; reasons.append(f"GA {ega}")
    elif ega and rec.get("ga_ordinal"):
        s -= 35; reasons.append(f"GA mismatch {ega}!={rec.get('ga_ordinal')}")
    if eyear and rec.get("year") == eyear:
        s += 20; reasons.append(f"year {eyear}")
    elif eyear and rec.get("year"):
        s -= 20; reasons.append(f"year mismatch {eyear}!={rec.get('year')}")
    if epages:
        overlap = epages & rec_pages(rec)
        if overlap:
            s += 35; reasons.append("page " + ",".join(map(str, sorted(overlap))))
        else:
            s -= 10; reasons.append("page hint missed")
    ecit = norm(entry.get("citation"))
    if ecit and (ecit in norm(rec.get("title")) or ecit in norm(rec.get("topic"))):
        s += 15; reasons.append("citation text")

    rhay = norm(" ".join(str(rec.get(k) or "") for k in ("topic", "title", "file")))
    title = norm(entry.get("paper_title") or "")
    if title:
        ratio = SequenceMatcher(None, title, rhay).ratio()
        common = tokens(title) & tokens(rhay)
        if title in rhay or (len(common) >= max(2, min(5, len(tokens(title)) // 2))):
            pts = 30
        else:
            pts = int(25 * ratio)
        s += pts; reasons.append(f"title {pts}")
    alias_hits = [a for a in entry.get("aliases", []) if norm(a) and norm(a) in rhay]
    if alias_hits:
        s += min(25, 10 * len(alias_hits)); reasons.append("alias " + ", ".join(alias_hits[:3]))
    if norm(entry.get("topic")) and norm(entry.get("topic")) in rhay:
        s += 15; reasons.append("topic fallback")
    elif tokens(entry.get("topic")) & tokens(rhay):
        s += 5; reasons.append("weak topic fallback")
    return s, reasons


def main():
    roster = json.load(open(os.path.join(IDX, "studies_roster.json"), encoding="utf-8"))
    recs = json.load(open(os.path.join(IDX, "studies_pages.json"), encoding="utf-8"))
    for r in recs:
        r.pop("roster_topic", None); r.pop("roster_paper_title", None)

    candidates = []
    for ei, e in enumerate(roster):
        for ri, r in enumerate(recs):
            s, why = score(e, r)
            if s >= TENTATIVE_THRESHOLD:
                candidates.append((s, ei, ri, why))
    candidates.sort(reverse=True)

    matched_entries, matched_recs, exact, tentative, rejected = set(), set(), [], [], []
    for s, ei, ri, why in candidates:
        e, r = roster[ei], recs[ri]
        if ei in matched_entries or ri in matched_recs:
            if s >= TENTATIVE_THRESHOLD:
                rejected.append((e, r, s, why, "lower-scoring duplicate candidate"))
            continue
        topic_only = all("topic fallback" in w or "weak topic fallback" in w for w in why)
        if s >= EXACT_THRESHOLD and not topic_only:
            exact.append((e, r, s, why)); matched_entries.add(ei); matched_recs.add(ri)
            r["roster_topic"] = e["topic"]; r["roster_paper_title"] = e.get("paper_title") or e["topic"]
        elif s >= TENTATIVE_THRESHOLD:
            tentative.append((e, r, s, why)); matched_entries.add(ei); matched_recs.add(ri)
            r["roster_topic"] = e["topic"]; r["roster_paper_title"] = e.get("paper_title") or e["topic"]
    unmatched = [e for i, e in enumerate(roster) if i not in matched_entries]
    absent = [r for i, r in enumerate(recs) if i not in matched_recs]

    json.dump(recs, open(os.path.join(IDX, "studies_pages.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    L = ["# Study Papers — document-level roster reconciliation", "",
         f"Matched located documents against {len(roster)} document rows from the PCA Historical Center roster.", "",
         f"- **{len(exact)}** exact document matches", f"- **{len(tentative)}** topic-only tentative matches",
         f"- **{len(unmatched)}** unmatched roster documents", f"- **{len(rejected)}** located documents rejected as false positives",
         f"- **{len(absent)}** located documents real but absent from pcahistory", ""]
    def table(title, rows):
        L.extend([f"## {title}", "", "| Roster document | Located document | Score / basis |", "|---|---|---|"])
        for e, r, s, why in rows:
            L.append(f"| {row_label(e)} | {doc_label(r)} | {s}: {'; '.join(why)} |")
        L.append("")
    table("Exact document matches", exact)
    table("Topic-only tentative matches", tentative)
    L.extend(["## Unmatched roster documents", "", "| Roster document | Expected hints |", "|---|---|"])
    for e in unmatched:
        L.append(f"| {row_label(e)} | {json.dumps(expected(e), ensure_ascii=False) if expected(e) else e.get('citation') or e.get('year') or '—'} |")
    L.extend(["", "## Located documents rejected as false positives", "", "| Roster candidate | Located document | Score / reason |", "|---|---|---|"])
    for e, r, s, why, reason in rejected:
        L.append(f"| {row_label(e)} | {doc_label(r)} | {s}: {reason}; {'; '.join(why)} |")
    L.extend(["", "## Located documents that are real but absent from pcahistory", ""])
    for r in absent:
        L.append(f"- {doc_label(r)}")
    L.append("")
    open(os.path.join(IDX, "studies_reconciliation.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"roster docs: {len(roster)} | exact: {len(exact)} | tentative: {len(tentative)} | unmatched: {len(unmatched)} | rejected: {len(rejected)} | absent: {len(absent)}")


if __name__ == "__main__": main()
