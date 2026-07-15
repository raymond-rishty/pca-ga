#!/usr/bin/env python3
"""40_study_outcomes.py — extract recommendations and GA outcomes for study records.

Runs after 37_study_pages.py and before 38_study_index.py. It enriches
index/studies_pages.json with source-backed recommendations/outcome fields and rewrites
rendered study pages so the catalogue exposes those fields.

Reads:   index/studies_pages.json
         markdown/ga*.md
Writes:  index/studies_pages.json
         index/studies_outcomes_audit.md
         studies/*.md (replaces the old later-pass notice when possible)
Usage:   40_study_outcomes.py [ROOT]
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Iterable

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")
STUDIES = os.path.join(ROOT, "studies")

NO_FINAL = "no final action located"
CLASSES = [
    "adopted as PCA position",
    "recommendations adopted",
    "received/commended for study",
    "recommitted/continued",
    "postponed",
    "answered by reference/declined",
    NO_FINAL,
]

RECOMMEND_RE = re.compile(r"\b(recommendation|recommendations|recommend\s+that|therefore\s+recommend|committee\s+recommends)\b", re.I)
OUTCOME_RE = re.compile(
    r"\b(adopted|approved|received|commended|recommitted|referred|continued|postponed|answered\s+by\s+reference|declined|not\s+adopted|was\s+lost)\b",
    re.I,
)
ACTION_CONTEXT_RE = re.compile(r"\b(report|recommendation|pastoral\s+letter|position|paper|committee|assembly)\b", re.I)
GA_ACTION_RE = re.compile(r"\b(assembly|general assembly|report as a whole|recommendations? (?:be )?adopted|was adopted|were adopted|be adopted|referred to|recommitted to|postponed)\b", re.I)
ANCHOR_RE = re.compile(r'<a id="([^"]+)"')


def md_lines(stem: str) -> list[str]:
    return open(os.path.join(MD, stem + ".md"), encoding="utf-8").read().split("\n")


def source_for(vol: str, start: int, end: int) -> dict:
    lines = md_lines(vol)
    anchor_start = None
    anchor_end = None
    for i in range(max(1, start) - 1, min(len(lines), end)):
        m = ANCHOR_RE.search(lines[i])
        if m and not anchor_start:
            anchor_start = m.group(1)
        if m:
            anchor_end = m.group(1)
    if not anchor_start:
        for i in range(max(0, start - 2), -1, -1):
            m = ANCHOR_RE.search(lines[i])
            if m:
                anchor_start = m.group(1)
                break
    if not anchor_end:
        anchor_end = anchor_start
    return {"vol": vol, "line_start": start, "line_end": end, "anchor_start": anchor_start, "anchor_end": anchor_end}


def clean_slice(lines: list[str], start: int, end: int, max_lines: int = 80) -> str:
    out = []
    for ln in lines[start - 1:end]:
        s = ln.strip()
        if not s or s.startswith("<a id=") or s.startswith("<!-- PAGE"):
            continue
        out.append(ln.rstrip())
        if len(out) >= max_lines:
            break
    return "\n".join(out).strip()


def paragraph_around(lines: list[str], idx0: int, lo: int, hi: int) -> tuple[int, int]:
    start = idx0
    while start > lo and lines[start - 1].strip() and not lines[start - 1].startswith("<a id="):
        start -= 1
    end = idx0
    while end + 1 < hi and lines[end + 1].strip() and not lines[end + 1].startswith("<a id="):
        end += 1
    return start + 1, end + 1


def find_recommendations(r: dict) -> tuple[dict | None, str | None]:
    if r.get("external_url") and not r.get("full_text_sources"):
        return None, None
    src = (r.get("full_text_sources") or [r])[0]
    vol = src["vol"]
    lines = md_lines(vol)
    lo, hi = int(src["line_start"]), int(src["line_end"])
    hits = [i for i in range(max(1, lo) - 1, min(len(lines), hi)) if RECOMMEND_RE.search(lines[i])]
    if not hits:
        return None, None
    # Prefer a recommendations heading/list toward the end of the report.
    idx = hits[-1]
    for h in reversed(hits):
        if re.search(r"^#{1,6}\s+.*recommend|^\**\s*(recommendation|recommendations)\b", lines[h].strip(), re.I):
            idx = h
            break
    end = min(hi, idx + 80)
    # Stop at the next major heading after at least a few lines.
    for j in range(idx + 5, min(len(lines), end)):
        if re.match(r"^#{1,4}\s+", lines[j]):
            end = j
            break
    return source_for(vol, idx + 1, end), clean_slice(lines, idx + 1, end)


def classify(text: str) -> tuple[str, float]:
    t = text.lower()
    if "postpon" in t:
        return "postponed", 0.86
    if "answered by reference" in t or "declined" in t or "not adopted" in t or "was lost" in t:
        return "answered by reference/declined", 0.84
    if "recommit" in t or "referred" in t or "continue" in t:
        return "recommitted/continued", 0.80
    if "received" in t or "commended" in t:
        return "received/commended for study", 0.78
    if "pastoral letter" in t and "adopt" in t:
        return "adopted as PCA position", 0.90
    if "position" in t and "adopt" in t:
        return "adopted as PCA position", 0.85
    if "recommend" in t and "adopt" in t:
        return "recommendations adopted", 0.86
    if "report" in t and "adopt" in t:
        return "recommendations adopted", 0.76
    return NO_FINAL, 0.0


def find_outcome(r: dict) -> tuple[dict | None, str | None, str, float]:
    if r.get("external_url") and not r.get("full_text_sources"):
        return None, None, NO_FINAL, 0.0
    src = (r.get("full_text_sources") or [r])[0]
    vol = src["vol"]
    lines = md_lines(vol)
    lo = min(len(lines), int(src["line_end"]))
    hi = min(len(lines), lo + 900)
    candidates = []
    for i in range(lo, hi):
        line = lines[i].strip()
        low = line.lower()
        if "majority of the committee" in low or "minority report" in low:
            continue
        if OUTCOME_RE.search(line) and ACTION_CONTEXT_RE.search(line) and GA_ACTION_RE.search(line):
            cls, conf = classify(line)
            if cls != NO_FINAL:
                score = (0 if "assembly" in low or "general assembly" in low else 1, i)
                candidates.append((score, i, cls, conf))
    if not candidates:
        return None, None, NO_FINAL, 0.0
    _score, i, cls, conf = sorted(candidates)[0]
    start, end = paragraph_around(lines, i, max(0, i - 3), min(len(lines), i + 4))
    return source_for(vol, start, end), clean_slice(lines, start, end, max_lines=20), cls, round(max(0.0, min(conf, 0.99)), 2)


def render_sections(r: dict) -> str:
    parts = []
    if r.get("recommendations_excerpt"):
        src = r["recommendations_source"]
        anchor = src.get("anchor_start") or ""
        link = f"../markdown/{src['vol']}.md" + (f"#{anchor}" if anchor else "")
        parts += [
            "## Recommendations", "",
            f"Source: [{src['vol']} lines {src['line_start']}–{src['line_end']}]({link}).", "",
            "> " + r["recommendations_excerpt"].replace("\n", "\n> "), "", "---", "",
        ]
    else:
        parts += ["## Recommendations", "", "*No recommendations slice was located by the extraction pass.*", "", "---", ""]
    parts += ["## General Assembly outcome", ""]
    parts += [f"**Classification:** {r.get('outcome_classification', NO_FINAL)}"]
    if r.get("outcome_confidence") is not None:
        parts += [f"**Confidence:** {r.get('outcome_confidence')}"]
    parts += [""]
    if r.get("outcome_text"):
        src = r["outcome_source"]
        anchor = src.get("anchor_start") or ""
        link = f"../markdown/{src['vol']}.md" + (f"#{anchor}" if anchor else "")
        parts += [f"Source: [{src['vol']} lines {src['line_start']}–{src['line_end']}]({link}).", "", "> " + r["outcome_text"].replace("\n", "\n> "), ""]
    else:
        parts += ["*No final General Assembly action was located by the extraction pass.*", ""]
    return "\n".join(parts)


def patch_page(r: dict) -> None:
    fn = r.get("file")
    if not fn:
        return
    path = os.path.join(STUDIES, fn)
    if not os.path.exists(path):
        return
    text = open(path, encoding="utf-8").read()
    marker = "*Recommendations and the General Assembly's disposition are captured in a later pass"
    if marker in text:
        text = re.sub(r"\*Recommendations and the General Assembly's disposition are captured in a later pass.*?\n\n", render_sections(r) + "\n", text, flags=re.S)
    elif "\n## Recommendations\n" in text and "\n[← Study reports]" in text:
        text = re.sub(
            r"\n## Recommendations\n.*?\n(?=\[← Study reports\])",
            "\n" + render_sections(r) + "\n",
            text,
            flags=re.S,
        )
    open(path, "w", encoding="utf-8").write(text)


def main() -> None:
    path = os.path.join(IDX, "studies_pages.json")
    recs = json.load(open(path, encoding="utf-8"))
    for r in recs:
        rec_src, rec_excerpt = find_recommendations(r)
        out_src, out_text, cls, conf = find_outcome(r)
        r["recommendations_source"] = rec_src
        r["recommendations_excerpt"] = rec_excerpt
        r["outcome_source"] = out_src
        r["outcome_text"] = out_text
        r["outcome_classification"] = cls
        r["outcome_confidence"] = conf
        patch_page(r)
    json.dump(recs, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    missing = [r for r in recs if r.get("outcome_classification") == NO_FINAL]
    audit = ["# Study outcome extraction audit", "", f"Records with `{NO_FINAL}`: {len(missing)}", ""]
    for r in missing:
        audit.append(f"- {r.get('topic') or r.get('title')} — {r.get('vol')} {r.get('line_start')}–{r.get('line_end')} ({r.get('file')})")
    open(os.path.join(IDX, "studies_outcomes_audit.md"), "w", encoding="utf-8").write("\n".join(audit) + "\n")
    print(f"enriched {len(recs)} study records; {len(missing)} with no final action located")


if __name__ == "__main__":
    main()
