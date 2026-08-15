#!/usr/bin/env python3
"""Refresh legacy case pages by matching their existing printed-page provenance.

This is deliberately format-agnostic.  It reads the source page range already
recorded in each case page, finds the case start and the next-case boundary in
the current minutes, and preserves the existing metadata preamble.  Use
``--apply`` to write only high-confidence matches.
"""
from __future__ import annotations

import difflib
import importlib.util
import json
import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("PCA_GA_ROOT", Path(__file__).resolve().parents[1]))
CASES = ROOT / "cases"
MD = ROOT / "markdown"
BUILD = ROOT / "build" / "legacy_case_refresh"

spec = importlib.util.spec_from_file_location("case_pages", ROOT / "scripts" / "24_case_pages.py")
case_pages = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(case_pages)

SOURCE_RE = re.compile(
    r"\*Source:\s+\[([^\]]+)\]\([^)]*#(ga\d+)-p(\d+)\)", re.I
)
RANGE_RE = re.compile(r"\bpp?\.\s*(\d+)\s*(?:[-–—]|â€“)\s*(\d+)", re.I)
SINGLE_RE = re.compile(r"\bp\.\s*(\d+)\b", re.I)
PAGE_RE = re.compile(
    r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\w+)\s+printed_page=([^\s]+)[^>]*-->"
)
TOKEN_RE = re.compile(r"[a-z0-9]{3,}", re.I)
ADJ_RE = re.compile(r"\badjudication\s+of\s+case\s*#?\s*(\d+)\b", re.I)
STOP = set(
    "the and for from against presbytery church session committee complaint appeal"
    " judicial case report general assembly of in on to vs versus et al no"
    " standing commission counsel matter question concerning regarding".split()
)


def norm(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower().replace("â€“", "-")))


def tokens(text: str) -> set[str]:
    return {t for t in TOKEN_RE.findall(text.lower()) if t not in STOP}


def source_range(text: str):
    source = next((line for line in text.splitlines() if line.startswith("*Source:")), "")
    match = SOURCE_RE.search(source)
    if not match:
        return None
    label, anchor_vol, anchor_start = match.groups()
    vol_match = re.search(r"\bga\d+_\d{4}\b", label, re.I)
    vol = vol_match.group(0) if vol_match else anchor_vol
    range_match = RANGE_RE.search(label)
    if range_match:
        start, end = map(int, range_match.groups())
    else:
        single = SINGLE_RE.search(label)
        if not single:
            return None
        start = end = int(single.group(1))
    return vol, start, end, int(anchor_start)


def printed_pages(vol: str, start: int, end: int) -> str:
    path = MD / f"{vol}.md"
    text = path.read_text(encoding="utf-8")
    parts = PAGE_RE.split(text)
    out = []
    for i in range(1, len(parts), 3):
        pdf_page, printed, body = parts[i : i + 3]
        if printed.isdigit() and start <= int(printed) <= end:
            out.append(body)
    return "\n".join(out).strip()


def preamble(text: str) -> str:
    marker = "\n---\n"
    return text.split(marker, 1)[0] if marker in text else text.split("\n---", 1)[0]


def old_body(text: str) -> str:
    parts = text.split("\n---\n", 1)
    body = parts[1] if len(parts) == 2 else text
    body = body.rsplit("\n---\n", 1)[0]
    return body.replace("[← Judicial case index](../index/CASES.md)", "")


def case_signals(text: str):
    heading = next((line for line in text.splitlines() if line.startswith("# ")), "")
    numbers = set(case_pages._num_variants(*re.findall(r"\b\d{2,4}-\d{1,3}\b", text[:5000])))
    heading_tokens = tokens(heading)
    body_tokens = tokens(text[:8000])
    distinctive = (heading_tokens | body_tokens) - {"source", "court", "assembly", "disposition"}
    labels = set(ADJ_RE.findall(text[:8000]))
    return numbers, set(list(distinctive)[:20]), labels


def next_signals(text: str):
    return case_signals(text)


def trim_candidate(candidate: str, own_numbers: set[str], own_tokens: set[str],
                   own_labels: set[str], next_numbers: set[str], next_tokens: set[str],
                   next_labels: set[str]) -> tuple[str, bool]:
    lines = candidate.splitlines()
    start = 0
    best = (-1, 0)
    for i, line in enumerate(lines):
        clean = line.strip()
        score = 0
        if case_pages._CASEHDR.match(clean):
            score += 3
        label_match = ADJ_RE.search(clean)
        if label_match:
            score += 4
            if label_match.group(1) in own_labels:
                score += 3
        if any(number in clean for number in own_numbers):
            score += 5
        score += min(3, sum(1 for token in own_tokens if token in norm(clean)))
        if score > best[0]:
            best = (score, i)
    if best[0] >= 5:
        start = best[1]

    end = len(lines)
    boundary_found = False
    for i in range(start + 1, len(lines)):
        clean = lines[i].strip()
        if not case_pages._CASEHDR.match(clean):
            if not ADJ_RE.search(clean):
                continue
        number_hit = any(number in clean for number in next_numbers)
        title_hit = sum(1 for token in next_tokens if token in norm(clean)) >= 2
        label_hit = bool((match := ADJ_RE.search(clean)) and match.group(1) in next_labels)
        if number_hit or title_hit or label_hit:
            end = i
            boundary_found = True
            break
    return "\n".join(lines[start:end]).strip(), boundary_found


def fuzzy_trim(old: str, candidate: str):
    """Find the old body's distinctive beginning/end inside a broad page range."""
    old_tokens = TOKEN_RE.findall(old.lower())
    if len(old_tokens) < 20:
        return candidate, False, (0.0, 0.0)
    start_target = set(old_tokens[:50])
    end_target = set(old_tokens[-50:])
    lines = candidate.splitlines()

    def best(target):
        best_score, best_i = 0.0, 0
        for i in range(len(lines)):
            window = set(TOKEN_RE.findall(" ".join(lines[i : i + 5]).lower()))
            value = len(target & window) / max(1, len(target))
            if value > best_score:
                best_score, best_i = value, i
        return best_score, best_i

    start_score, start = best(start_target)
    end_score, end = best(end_target)
    if start_score < 0.45 or end_score < 0.45 or end < start:
        return candidate, False, (start_score, end_score)
    return "\n".join(lines[start : end + 5]).strip(), True, (start_score, end_score)


def fuzzy_end_trim(old: str, candidate: str):
    """Refine only the end; the explicit case header remains the start anchor."""
    old_tokens = TOKEN_RE.findall(old.lower())
    if len(old_tokens) < 20:
        return candidate, False, 0.0
    target = set(old_tokens[-50:])
    lines = candidate.splitlines()
    best_score, best_i = 0.0, 0
    for i in range(len(lines)):
        window = set(TOKEN_RE.findall(" ".join(lines[i : i + 5]).lower()))
        value = len(target & window) / max(1, len(target))
        if value > best_score:
            best_score, best_i = value, i
    if best_score < 0.45:
        return candidate, False, best_score
    return "\n".join(lines[: best_i + 5]).strip(), True, best_score


def score(old: str, new: str, own_numbers: set[str], own_tokens: set[str]) -> tuple[float, list[str]]:
    old_norm = norm(old)
    new_norm = norm(new)
    reasons = []
    if not new_norm:
        return 0.0, ["empty candidate"]
    ratio = difflib.SequenceMatcher(None, old_norm[:6000], new_norm[:6000]).ratio()
    old_tokens = tokens(old)
    new_tokens = tokens(new)
    overlap = len(old_tokens & new_tokens) / max(1, len(old_tokens))
    number_hit = bool(own_numbers and any(number in new_norm for number in own_numbers))
    title_overlap = len(own_tokens & new_tokens) / max(1, len(own_tokens))
    length_ratio = min(len(old_norm), len(new_norm)) / max(1, max(len(old_norm), len(new_norm)))
    value = (0.30 * ratio + 0.25 * overlap + 0.15 * title_overlap
             + 0.20 * length_ratio + (0.10 if number_hit else 0.0))
    if ratio >= 0.45:
        reasons.append(f"sequence={ratio:.2f}")
    if overlap >= 0.35:
        reasons.append(f"token_overlap={overlap:.2f}")
    if title_overlap >= 0.35:
        reasons.append(f"title_overlap={title_overlap:.2f}")
    reasons.append(f"length_ratio={length_ratio:.2f}")
    if number_hit:
        reasons.append("case-number-hit")
    return round(value, 3), reasons


def main() -> None:
    apply = "--apply" in os.sys.argv[1:]
    legacy_only = "--legacy-only" in os.sys.argv[1:]
    threshold = 0.48
    for arg in os.sys.argv[1:]:
        if arg.startswith("--threshold="):
            threshold = float(arg.split("=", 1)[1])
    files = sorted(CASES.glob("ga*.md"))
    records = []
    by_vol = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        located = source_range(text)
        if not located:
            continue
        vol, start, end, _ = located
        if legacy_only and int(vol[2:4]) >= 19:
            continue
        records.append({"path": path, "text": text, "vol": vol, "start": start, "end": end})
        by_vol.setdefault(vol, []).append(records[-1])

    results = []
    for vol_records in by_vol.values():
        vol_records.sort(key=lambda item: (item["start"], item["end"], item["path"].name))
        for index, item in enumerate(vol_records):
            next_item = vol_records[index + 1] if index + 1 < len(vol_records) else None
            candidate_pages = printed_pages(item["vol"], item["start"], item["end"])
            own_numbers, own_tokens, own_labels = case_signals(item["text"])
            next_numbers, next_tokens, next_labels = (
                next_signals(next_item["text"]) if next_item else (set(), set(), set())
            )
            candidate, boundary_found = trim_candidate(
                candidate_pages, own_numbers, own_tokens, own_labels,
                next_numbers, next_tokens, next_labels
            )
            old = old_body(item["text"])
            if boundary_found:
                fuzzy_candidate, fuzzy_found, end_score = fuzzy_end_trim(old, candidate)
                anchor_scores = (1.0, end_score)
                if fuzzy_found:
                    candidate = fuzzy_candidate
            else:
                fuzzy_candidate, fuzzy_found, anchor_scores = fuzzy_trim(old, candidate_pages)
                if fuzzy_found:
                    candidate = fuzzy_candidate
                    boundary_found = True
            value, reasons = score(old_body(item["text"]), candidate, own_numbers, own_tokens)
            if fuzzy_found:
                reasons.append(f"anchors={anchor_scores[0]:.2f}/{anchor_scores[1]:.2f}")
            old_length = len(norm(old_body(item["text"])))
            new_length = len(norm(candidate))
            length_ratio = min(old_length, new_length) / max(1, max(old_length, new_length))
            status = ("located" if boundary_found and value >= threshold
                      and length_ratio >= 0.45 and len(candidate) >= 80 else "review")
            result = {
                "file": str(item["path"].relative_to(ROOT)).replace("\\", "/"),
                "vol": item["vol"], "printed_start": item["start"], "printed_end": item["end"],
                "score": value, "status": status, "reasons": reasons,
                "candidate_chars": len(candidate), "boundary_found": boundary_found,
            }
            if apply and status == "located":
                body = case_pages.promote_opinions(candidate)
                item["path"].write_text(
                    "\n".join([preamble(item["text"]), "", "---", "", body, "", "---", "",
                               "[← Judicial case index](../index/CASES.md)", ""]),
                    encoding="utf-8",
                )
                result["applied"] = True
            results.append(result)

    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "proposals.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    counts = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    print(f"examined {len(results)} page-bounded case pages: " + ", ".join(
        f"{key}={value}" for key, value in sorted(counts.items())
    ))
    if apply:
        print(f"applied {sum(1 for result in results if result.get('applied'))}; proposals: {BUILD / 'proposals.json'}")
    else:
        print(f"dry run; proposals: {BUILD / 'proposals.json'}")


if __name__ == "__main__":
    main()
