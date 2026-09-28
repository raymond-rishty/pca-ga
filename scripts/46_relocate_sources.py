#!/usr/bin/env python3
"""
46_relocate_sources.py - relocate line-based source spans after a minutes re-OCR.

The canonical inquiry, study, and RPR indexes contain locators into the previous
Markdown text.  A re-OCR changes line numbers even when the underlying PDF page is
unchanged.  This script uses the old span as a fingerprint, searches the new
Markdown only in the old page (plus a small page window), and writes an auditable
proposal.  It never replaces a source locator unless --apply is explicitly used.

Examples:

  python scripts/46_relocate_sources.py --kind inquiries --old-ref HEAD
  python scripts/46_relocate_sources.py --kind studies --old-ref HEAD
  python scripts/46_relocate_sources.py --kind rpr --old-ref HEAD

Outputs default to build/relocation/*.json (ignored scratch output).  A proposal
contains the original locator, the old text fingerprint, the candidate page/span,
score, margin, and the method used.  The old Git ref is deliberately recorded so
the result remains reproducible and reviewable.

--apply updates only high-confidence located records and stores the old locator
under `legacy_locator`; it does not delete or rewrite records that are ambiguous.
For RPR, apply updates index/rpr_exceptions.json only; its derived projections still
need to be rebuilt by the normal RPR pipeline after review.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(os.environ.get("PCA_GA_ROOT", Path(__file__).resolve().parents[1]))
MD_ROOT = ROOT / "markdown"
PAGE_RE = re.compile(r"<!--\s*PAGE\s+ga=(?P<ga>\d+)\s+pdf_page=(?P<pdf>\d+)(?:\s+printed_page=(?P<printed>[^\s>]+))?[^>]*-->", re.I)
ANCHOR_RE = re.compile(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', re.I)
PAGE_HINT_RE = re.compile(r"-p(\d+)$", re.I)
TAG_RE = re.compile(r"<[^>]+>")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

STOP = {
    "about", "after", "again", "against", "assembly", "because", "before", "being",
    "between", "book", "church", "committee", "could", "from", "general", "given",
    "have", "into", "minutes", "more", "other", "paragraph", "presbytery", "report",
    "section", "shall", "should", "some", "such", "than", "that", "their", "there",
    "these", "they", "this", "through", "under", "upon", "were", "which", "with",
    "would", "your", "response", "following", "question", "answer", "advice", "adopted",
}


@dataclass
class Page:
    pdf: int
    printed: str | None
    anchor: str
    start: int  # one-based inclusive
    end: int    # one-based inclusive


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_markdown(ref: str, vol: str) -> list[str]:
    rel = f"markdown/{vol}.md"
    try:
        raw = subprocess.check_output(["git", "show", f"{ref}:{rel}"], cwd=ROOT)
    except (OSError, subprocess.CalledProcessError):
        return []
    return raw.decode("utf-8", errors="replace").splitlines()


def current_markdown(vol: str) -> list[str]:
    path = MD_ROOT / f"{vol}.md"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def parse_pages(lines: list[str]) -> list[Page]:
    starts: list[tuple[int, re.Match[str]]] = []
    for n, line in enumerate(lines, 1):
        m = PAGE_RE.search(line)
        if m:
            starts.append((n, m))
    pages: list[Page] = []
    for i, (start, m) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else len(lines)
        anchor = f"ga{int(m.group('ga')):02d}-p{int(m.group('pdf'))}"
        for line in lines[start - 1:min(end, start + 8)]:
            a = ANCHOR_RE.search(line)
            if a:
                anchor = a.group(1)
                break
        pages.append(Page(int(m.group("pdf")), m.group("printed"), anchor, start, end))
    return pages


def norm_tokens(value: str) -> list[str]:
    value = COMMENT_RE.sub(" ", value or "")
    value = TAG_RE.sub(" ", html.unescape(value))
    value = unicodedata.normalize("NFKC", value).lower()
    return re.findall(r"[a-z0-9]{2,}", value)


def informative(tokens: Iterable[str]) -> list[str]:
    return [t for t in tokens if len(t) >= 4 and t not in STOP]


def fingerprint_score(old: list[str], candidate: list[str]) -> float:
    """Score token coverage plus ordered common subsequence, without dependencies."""
    old_i = informative(old)
    cand_i = informative(candidate)
    if not old_i or not cand_i:
        return 0.0
    old_set = set(old_i)
    cand_set = set(cand_i)
    coverage = len(old_set & cand_set) / len(old_set)
    # Keep the comparison bounded for very long study spans.
    a = old_i[:1200]
    b = cand_i[:5000]
    match = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    ordered = match.size / len(a)
    return 0.76 * coverage + 0.24 * ordered


def quick_coverage(old: list[str], candidate: list[str]) -> float:
    """Cheap first-pass score used before the smaller set of fuzzy comparisons."""
    old_i = set(informative(old))
    cand_i = set(informative(candidate))
    return len(old_i & cand_i) / len(old_i) if old_i else 0.0


def span_text(lines: list[str], start: Any, end: Any) -> str:
    try:
        a, b = int(start), int(end)
    except (TypeError, ValueError):
        return ""
    if a < 1 or b < a or a > len(lines):
        return ""
    return "\n".join(lines[a - 1:min(b, len(lines))])


def page_for_line(pages: list[Page], line_no: int) -> Page | None:
    return next((p for p in pages if p.start <= line_no <= p.end), None)


def page_by_pdf(pages: list[Page], pdf: int) -> Page | None:
    return next((p for p in pages if p.pdf == pdf), None)


def hinted_pdf(anchor: str | None) -> int | None:
    if not anchor:
        return None
    m = PAGE_HINT_RE.search(str(anchor))
    return int(m.group(1)) if m else None


def candidate_page_starts(new_pages: list[Page], old_pages: list[Page], old_start: int,
                          old_anchor: str | None, window: int, page_hint: int | None = None,
                          page_hint_kind: str = "pdf") -> list[int]:
    hint = page_hint if page_hint is not None else hinted_pdf(old_anchor)
    old_page = page_for_line(old_pages, old_start)
    target = hint or (old_page.pdf if old_page else None)
    if page_hint_kind == "printed" and target is not None:
        center = next((i for i, p in enumerate(new_pages) if p.printed == str(target)), None)
        if center is not None:
            return [center]
    if target is None:
        return [0]
    center = next((i for i, p in enumerate(new_pages) if p.pdf == target), None)
    if center is None:
        return [0]
    # The source records already carry a PDF-page anchor.  Use that page first;
    # nearby pages are only a fallback when its fingerprint is too weak.
    if hint is not None:
        return [center]
    return list(range(max(0, center - window), min(len(new_pages), center + window + 1)))


def page_block(lines: list[str], pages: list[Page], start_i: int, page_count: int) -> tuple[list[str], int, int]:
    selected = pages[start_i:min(len(pages), start_i + page_count)]
    if not selected:
        return [], 1, 0
    return lines[selected[0].start - 1:selected[-1].end], selected[0].start, selected[-1].end


def locate_span(old_lines: list[str], old_pages: list[Page], new_lines: list[str], new_pages: list[Page],
                start: Any, end: Any, anchor: str | None, window: int,
                text_override: str | None = None, page_hint: int | None = None,
                page_hint_kind: str = "pdf", strict: bool = False) -> dict[str, Any]:
    try:
        old_start, old_end = int(start), int(end)
    except (TypeError, ValueError):
        return {"status": "not_applicable", "reason": "missing_old_span"}
    old_text = text_override if text_override is not None else span_text(old_lines, old_start, old_end)
    if text_override is not None:
        old_page_hint = page_hint if page_hint is not None else hinted_pdf(anchor)
        if page_hint_kind == "printed" and old_page_hint is not None:
            old_page = next((p for p in old_pages if p.printed == str(old_page_hint)), None)
        else:
            old_page = next((p for p in old_pages if p.pdf == old_page_hint), None) if old_page_hint else None
        old_start = old_page.start if old_page else 1
        old_end = old_start + max(0, old_text.count("\n"))
    old_tok = norm_tokens(old_text)
    if not old_text.strip() or not old_tok:
        return {"status": "not_applicable", "reason": "empty_old_span", "old_text": old_text}
    old_page = page_for_line(old_pages, old_start)
    old_end_page = page_for_line(old_pages, old_end) or old_page
    page_count = max(1, (old_pages.index(old_end_page) - old_pages.index(old_page) + 1)
                     if old_page and old_end_page else 1)
    candidates: list[tuple[float, int, int, int]] = []
    for start_i in candidate_page_starts(new_pages, old_pages, old_start, anchor, window,
                                         page_hint, page_hint_kind):
        block, block_start, block_end = page_block(new_lines, new_pages, start_i, page_count)
        # Page selection is deliberately cheap.  The precise LCS score is reserved for
        # the small set of line windows below; otherwise RPR's thousands of short spans
        # repeatedly compare against whole pages.
        score = quick_coverage(old_tok, norm_tokens("\n".join(block)))
        candidates.append((score, start_i, block_start, block_end))
    if not candidates:
        return {"status": "not_found", "old_text": old_text, "reason": "no_new_pages"}
    candidates.sort(reverse=True)
    page_score, page_i, block_start, block_end = candidates[0]
    block = new_lines[block_start - 1:block_end]
    block_line_tokens = [norm_tokens(line) for line in block]

    # Preserve the old within-page offset as a search hint, but allow substantial line drift.
    old_page_start = old_page.start if old_page else old_start
    expected = max(0, old_start - old_page_start)
    old_count = max(1, old_end - old_start + 1)
    slack = max(18, min(70, old_count // 2 + 12))
    lo = max(0, expected - slack)
    hi = min(len(block), expected + slack + 1)
    if hi <= lo:
        lo, hi = 0, len(block)
    if old_count <= 6:
        lengths = range(1, min(5, len(block) - lo) + 1)
    else:
        delta = max(8, min(35, old_count // 4))
        lengths = range(max(1, old_count - delta), min(len(block) - lo, old_count + delta) + 1)

    windows: list[tuple[float, int, int]] = []
    for rel_start in range(lo, hi):
        for length in lengths:
            rel_end = rel_start + length
            if rel_end > len(block):
                continue
            candidate_tokens: list[str] = []
            for line_tokens in block_line_tokens[rel_start:rel_end]:
                candidate_tokens.extend(line_tokens)
            score = quick_coverage(old_tok, candidate_tokens)
            # A size tie-break avoids choosing a one-line fragment of a longer study.
            size_fit = min(old_count / length, length / old_count)
            windows.append((0.94 * score + 0.06 * size_fit, rel_start, rel_end))
    if not windows:
        return {"status": "review", "old_text": old_text, "page_score": round(page_score, 4),
                "reason": "no_line_windows"}
    windows.sort(reverse=True)
    # Re-rank only the best cheap candidates with the ordered fuzzy score.
    precise: list[tuple[float, int, int]] = []
    for _, rel_start0, rel_end0 in windows[:12]:
        candidate_tokens: list[str] = []
        for line_tokens in block_line_tokens[rel_start0:rel_end0]:
            candidate_tokens.extend(line_tokens)
        size_fit = min(old_count / (rel_end0 - rel_start0),
                       (rel_end0 - rel_start0) / old_count)
        precise.append((0.94 * fingerprint_score(old_tok, candidate_tokens) + 0.06 * size_fit,
                        rel_start0, rel_end0))
    precise.sort(reverse=True)
    best, rel_start, rel_end = precise[0]
    second = precise[1][0] if len(precise) > 1 else 0.0
    new_start = block_start + rel_start
    new_end = block_start + rel_end - 1
    new_page_start = page_for_line(new_pages, new_start)
    new_page_end = page_for_line(new_pages, new_end) or new_page_start
    margin = best - second
    # A high token score can stand on its own for a page-bounded unique span; otherwise
    # require a meaningful margin so repeated RPR boilerplate is sent to review.
    if best >= 0.95 and (not strict or margin >= 0.015):
        status = "located"
    elif best >= 0.70 and margin >= 0.015:
        status = "located"
    elif best >= 0.42 and margin >= 0.035:
        status = "located"
    elif best >= 0.25:
        status = "review"
    else:
        status = "not_found"
    return {
        "status": status,
        "old_text": old_text,
        "old_line_start": old_start,
        "old_line_end": old_end,
        "old_page_anchor": anchor,
        "new_line_start": new_start,
        "new_line_end": new_end,
        "new_page_anchor": new_page_start.anchor if new_page_start else None,
        "new_pdf_page_start": new_page_start.pdf if new_page_start else None,
        "new_pdf_page_end": new_page_end.pdf if new_page_end else None,
        "new_text": "\n".join(new_lines[new_start - 1:new_end]),
        "score": round(best, 4),
        "page_score": round(page_score, 4),
        "margin": round(margin, 4),
        "method": "page_bounded_token_lcs",
    }


def locate_inquiries(old_ref: str, window: int) -> dict[str, Any]:
    path = ROOT / "index/inquiries_located.json"
    data = read_json(path)
    roster = read_json(ROOT / "index/inquiries_roster.json")
    roster_by_key = {(x.get("ga_ordinal"), x.get("minute_para"), x.get("topic")): x
                     for x in roster}
    roster_by_para = {(x.get("ga_ordinal"), x.get("minute_para")): x
                      for x in roster}
    records: list[dict[str, Any]] = []
    cache: dict[str, tuple[list[str], list[Page], list[str], list[Page]]] = {}
    for volume in data:
        stem = volume.get("stem")
        if not stem:
            continue
        def corpus() -> tuple[list[str], list[Page], list[str], list[Page]]:
            if stem not in cache:
                old = git_markdown(old_ref, stem)
                new = current_markdown(stem)
                cache[stem] = (old, parse_pages(old), new, parse_pages(new))
            return cache[stem]
        old_lines, old_pages, new_lines, new_pages = corpus()
        for i, item in enumerate(volume.get("results", [])):
            key = f"{stem}:{i}:{item.get('minute_para','')}:{item.get('topic','')}"
            ga = volume.get("ga_ordinal")
            roster_item = (roster_by_key.get((ga, item.get("minute_para"), item.get("topic"))) or
                           roster_by_para.get((ga, item.get("minute_para"))))
            roster_text = ((roster_item or {}).get("summary") or
                           (roster_item or {}).get("synopsis"))
            advice = locate_span(old_lines, old_pages, new_lines, new_pages,
                                 item.get("advice_start"), item.get("advice_end"),
                                 item.get("page_anchor"), window,
                                 text_override=roster_text,
                                 page_hint=(roster_item or {}).get("printed_page"),
                                 page_hint_kind="printed")
            posed = locate_span(old_lines, old_pages, new_lines, new_pages,
                                item.get("posed_start"), item.get("posed_end"),
                                item.get("page_anchor"), window)
            records.append({"key": key, "vol": stem, "minute_para": item.get("minute_para"),
                            "topic": item.get("topic"), "old": {k: item.get(k) for k in
                            ("advice_start", "advice_end", "posed_start", "posed_end", "page_anchor")},
                            "roster": {k: (roster_item or {}).get(k) for k in
                            ("ga_ordinal", "minute_para", "printed_page", "summary", "synopsis")},
                            "advice": advice, "posed": posed})
    return {"schema": "pca.source_relocation.v1", "kind": "inquiries", "old_ref": old_ref,
            "page_window": window, "records": records}


def locate_studies(old_ref: str, window: int) -> dict[str, Any]:
    path = ROOT / "index/studies_located.json"
    data = read_json(path)
    records: list[dict[str, Any]] = []
    cache: dict[str, tuple[list[str], list[Page], list[str], list[Page]]] = {}
    for i, item in enumerate(data):
        vol = item.get("vol")
        if not vol or not item.get("line_start") or not item.get("line_end"):
            records.append({"key": f"study:{i}", "vol": vol, "title": item.get("title"),
                            "status": "not_applicable", "reason": "not_minutes_span"})
            continue
        if vol not in cache:
            old = git_markdown(old_ref, vol)
            new = current_markdown(vol)
            cache[vol] = (old, parse_pages(old), new, parse_pages(new))
        old_lines, old_pages, new_lines, new_pages = cache[vol]
        match = locate_span(old_lines, old_pages, new_lines, new_pages,
                            item.get("line_start"), item.get("line_end"),
                            None, window)
        records.append({"key": f"study:{i}", "vol": vol, "title": item.get("title"),
                        "kind": item.get("kind"), "old": {k: item.get(k) for k in
                        ("line_start", "line_end", "anchor_start", "anchor_end")},
                        "match": match})
    return {"schema": "pca.source_relocation.v1", "kind": "studies", "old_ref": old_ref,
            "page_window": window, "records": records}


def locate_rpr(old_ref: str, window: int) -> dict[str, Any]:
    path = ROOT / "index/rpr_exceptions.json"
    data = read_json(path)
    records: list[dict[str, Any]] = []
    cache: dict[str, tuple[list[str], list[Page], list[str], list[Page]]] = {}
    for i, item in enumerate(data):
        vol = item.get("vol")
        if not vol or not item.get("line_start") or not item.get("line_end"):
            records.append({"key": f"rpr:{i}", "vol": vol, "id": item.get("id"),
                            "status": "not_applicable", "reason": "not_minutes_span"})
            continue
        if vol not in cache:
            old = git_markdown(old_ref, vol)
            new = current_markdown(vol)
            cache[vol] = (old, parse_pages(old), new, parse_pages(new))
        old_lines, old_pages, new_lines, new_pages = cache[vol]
        match = locate_span(old_lines, old_pages, new_lines, new_pages,
                            item.get("line_start"), item.get("line_end"),
                            item.get("page_anchor"), window,
                            text_override=item.get("description") or None,
                            page_hint=hinted_pdf(item.get("page_anchor")),
                            page_hint_kind="printed", strict=True)
        records.append({"key": f"rpr:{i}", "vol": vol, "id": item.get("id"),
                        "presbytery": item.get("presbytery"), "description": item.get("description"),
                        "old": {k: item.get(k) for k in ("line_start", "line_end", "page_anchor")},
                        "match": match})
    return {"schema": "pca.source_relocation.v1", "kind": "rpr", "old_ref": old_ref,
            "page_window": window, "records": records}


def counts(proposal: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in proposal["records"]:
        status = r.get("status") or r.get("match", {}).get("status") or "unknown"
        if proposal["kind"] == "inquiries":
            status = r.get("advice", {}).get("status", "unknown")
        out[status] = out.get(status, 0) + 1
    return out


def applyable(match: dict[str, Any]) -> bool:
    """Only exact/high-score matches may mutate canonical locator files."""
    return match.get("status") == "located" and float(match.get("score") or 0) >= 0.90


def apply_inquiries(proposal: dict[str, Any]) -> int:
    path = ROOT / "index/inquiries_located.json"
    data = read_json(path)
    changed = 0
    by_key = {f"{v.get('stem')}:{i}:{x.get('minute_para','')}:{x.get('topic','')}": x
              for v in data for i, x in enumerate(v.get("results", []))}
    for rec in proposal["records"]:
        item = by_key.get(rec["key"])
        advice = rec.get("advice", {})
        posed = rec.get("posed", {})
        if not item or not applyable(advice):
            continue
        if "legacy_locator" not in item:
            item["legacy_locator"] = {k: item.get(k) for k in
                                       ("advice_start", "advice_end", "posed_start", "posed_end", "page_anchor")}
        item["advice_start"] = advice["new_line_start"]
        item["advice_end"] = advice["new_line_end"]
        if posed.get("status") == "located":
            item["posed_start"] = posed["new_line_start"]
            item["posed_end"] = posed["new_line_end"]
        item["page_anchor"] = advice.get("new_page_anchor") or item.get("page_anchor")
        item["relocation"] = {"script": "46_relocate_sources.py", "old_ref": proposal["old_ref"],
                              "method": advice.get("method"), "score": advice.get("score")}
        changed += 1
    write_json(path, data)
    return changed


def apply_studies(proposal: dict[str, Any]) -> int:
    paths = [ROOT / "index/studies_located.json", ROOT / "index/studies_pages.json"]
    changed = 0
    for path in paths:
        data = read_json(path)
        for rec in proposal["records"]:
            match = rec.get("match", {})
            if not applyable(match):
                continue
            for item in data:
                if item.get("vol") != rec.get("vol") or item.get("title") != rec.get("title"):
                    continue
                if item.get("line_start") != rec.get("old", {}).get("line_start"):
                    continue
                if "legacy_locator" not in item:
                    item["legacy_locator"] = {k: item.get(k) for k in
                                               ("line_start", "line_end", "anchor_start", "anchor_end")}
                item["line_start"] = match["new_line_start"]
                item["line_end"] = match["new_line_end"]
                item["anchor_start"] = match.get("new_page_anchor")
                item["anchor_end"] = match.get("new_page_anchor")
                item["relocation"] = {"script": "46_relocate_sources.py", "old_ref": proposal["old_ref"],
                                       "method": match.get("method"), "score": match.get("score")}
                changed += 1
                break
        write_json(path, data)
    return changed


def apply_rpr(proposal: dict[str, Any]) -> int:
    path = ROOT / "index/rpr_exceptions.json"
    data = read_json(path)
    changed = 0
    for i, rec in enumerate(proposal["records"]):
        match = rec.get("match", {})
        if i >= len(data) or not applyable(match):
            continue
        item = data[i]
        if "legacy_locator" not in item:
            item["legacy_locator"] = {k: item.get(k) for k in ("line_start", "line_end", "page_anchor")}
        item["line_start"] = match["new_line_start"]
        item["line_end"] = match["new_line_end"]
        item["page_anchor"] = match.get("new_page_anchor") or item.get("page_anchor")
        item["relocation"] = {"script": "46_relocate_sources.py", "old_ref": proposal["old_ref"],
                               "method": match.get("method"), "score": match.get("score")}
        changed += 1
    write_json(path, data)
    return changed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=("inquiries", "studies", "rpr", "all"), default="all")
    ap.add_argument("--old-ref", default="HEAD", help="Git ref containing the pre-re-OCR Markdown")
    ap.add_argument("--page-window", type=int, default=2, help="pages on either side of old page")
    ap.add_argument("--output-dir", default=str(ROOT / "build" / "relocation"))
    ap.add_argument("--apply", action="store_true", help="apply only high-confidence located spans")
    args = ap.parse_args()
    funcs = {"inquiries": locate_inquiries, "studies": locate_studies, "rpr": locate_rpr}
    kinds = list(funcs) if args.kind == "all" else [args.kind]
    for kind in kinds:
        proposal = funcs[kind](args.old_ref, max(0, args.page_window))
        out = Path(args.output_dir) / f"{kind}.json"
        write_json(out, proposal)
        applied = 0
        if args.apply:
            applied = {"inquiries": apply_inquiries, "studies": apply_studies,
                       "rpr": apply_rpr}[kind](proposal)
        print(f"[{kind}] records={len(proposal['records'])} statuses={counts(proposal)} "
              f"output={out} applied={applied}")


if __name__ == "__main__":
    main()
