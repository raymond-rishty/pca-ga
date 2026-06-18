#!/usr/bin/env python3
"""
normalize.py — text cleanup for PCA GA minutes extraction (Phase 0 deliverable).

Two responsibilities, both with a hard content-safety guard:

  1. De-boilerplating  (strip NON-content furniture, per-volume):
       - running headers   (repeated top-of-page title lines)
       - running footers   (repeated bottom-of-page lines)
       - page numbers      (bare numeric / "Page N" lines)
       - line-number gutters (a column of bare, increasing integers, e.g. on
                              line-numbered overtures / BCO amendments)
  2. Text normalization:
       - soft-hyphen (U+00AD) removal
       - line-end dehyphenation (lowercase-only)
       - conservative intra-word DE-SPACING of OCR "shattered" text
         ("M INUTES o f the C h u rc h" -> "minutes of the church"), used both
         to repair text and to let the QC scorer decide despace-vs-reocr.

Content-safety guard (non-negotiable): a line is NEVER removed if it contains a
digit-hyphen-digit token (BCO 34-1, case 2017-01), a GA-item id, an alphabetic
word, or a vote/roster value — UNLESS it matches a *known repeated* header/footer
signature. A line-number-gutter token is removed only when the line is solely
that integer AND it belongs to the gutter's running sequence.

Shared helpers (load_dict, tokenize, resegment) are imported by 02_qc_score.py.
"""
from __future__ import annotations
import os
import re
import sys
from collections import Counter
from functools import lru_cache

SOFT_HYPHEN = "­"
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DICT = os.path.join(_HERE, "words.txt")

# A token that must never be destroyed by de-boilerplating: NN-NN (GA item / BCO
# / case number), times, scripture refs, etc.
PROTECTED_DIGIT = re.compile(r"\d+\s*[-:]\s*\d+")
ALPHA_WORD = re.compile(r"[A-Za-z]{2,}")
INT_ONLY_LINE = re.compile(r"^\s*(\d{1,4})\s*$")
PAGE_WORD_LINE = re.compile(r"^\s*(?:page|p\.)\s*\d{1,4}\s*$", re.I)
ROMAN_ONLY_LINE = re.compile(r"^\s*[ivxlcdm]{1,7}\s*$", re.I)


# ----------------------------------------------------------------------------- dict
@lru_cache(maxsize=1)
def load_dict(path: str = DEFAULT_DICT) -> frozenset:
    with open(path, encoding="utf-8") as fh:
        words = set(w.strip() for w in fh if w.strip())
    # merge domain/roster vocabulary the base wordlist lacks (presbytery, "a", presbytery
    # names, church-polity terms) so de-spacing can reassemble them
    extra = os.path.join(_HERE, "dict_extra.txt")
    if os.path.exists(extra):
        with open(extra, encoding="utf-8") as fh:
            words |= set(w.strip().lower() for w in fh if w.strip())
    return frozenset(words)


def tokenize(text: str):
    """Canonical tokenizer used everywhere: lowercase alpha tokens len>=2.
    Mirrors how words.txt was built so hitrate is self-consistent."""
    text = text.replace(SOFT_HYPHEN, "")
    text = re.sub(r"([a-z])-\n([a-z])", r"\1\2", text)  # line-end dehyphenation
    return re.findall(r"[a-z]{2,}", text.lower())


# ----------------------------------------------------------------------------- de-space
def resegment(s: str, words: frozenset, max_word: int = 24):
    """Max-coverage DP segmentation of a space-free string into dictionary words.
    Returns (segmented_string, covered_fraction). Unknown spans are kept verbatim
    as single chunks so proper nouns survive; coverage = dict chars / total chars."""
    n = len(s)
    if n == 0:
        return "", 0.0
    # best[i] = (score, covered, tokens) for prefix s[:i]
    NEG = float("-inf")
    best = [(NEG, 0, None)] * (n + 1)
    best[0] = (0.0, 0, [])
    for i in range(1, n + 1):
        # option A: extend by a dictionary word ending at i
        for j in range(max(0, i - max_word), i):
            ps, pc, pt = best[j]
            if pt is None:
                continue
            w = s[j:i]
            if w in words:
                score = ps + len(w) * len(w)  # reward longer words
                if score > best[i][0]:
                    best[i] = (score, pc + len(w), pt + [w])
        # option B: consume one char as "unknown" (small penalty, no coverage)
        ps, pc, pt = best[i - 1]
        if pt is not None:
            score = ps - 0.5
            if score > best[i][0]:
                # merge consecutive unknown chars into the last unknown chunk
                toks = list(pt)
                if toks and toks[-1].startswith("\x00"):
                    toks[-1] = toks[-1] + s[i - 1]
                else:
                    toks = toks + ["\x00" + s[i - 1]]
                best[i] = (score, pc, toks)
    _, covered, toks = best[n]
    if toks is None:
        return s, 0.0
    out = " ".join(t[1:] if t.startswith("\x00") else t for t in toks)
    return out, covered / n


def _is_shattered_run(frags) -> bool:
    """A whitespace run of alpha fragments is 'shattered' if it has >=2 single
    letters, OR (>=4 fragments that are predominantly <=2 chars). Guards against
    a legitimate stray 'a'/'I' or a couple of short function words triggering it;
    re-segmentation is additionally gated on dict-coverage by the caller."""
    if len(frags) < 2:
        return False
    singles = sum(1 for f in frags if len(f) == 1 and f.isalpha())
    if singles >= 2:
        return True
    if len(frags) >= 4:
        short = sum(1 for f in frags if len(f) <= 2)
        return short / len(frags) >= 0.6
    return False


def despace(text: str, words: frozenset | None = None) -> str:
    """Repair OCR intra-word shattering, line by line, only on shattered runs.
    Clean text and digit tokens are left untouched."""
    if words is None:
        words = load_dict()
    out_lines = []
    for line in text.split("\n"):
        # NOTE: digit tokens are inherently safe — re-segmentation runs only over
        # maximal PURE-ALPHA fragment runs, so tokens like "23-1" or "3/4" are
        # never inside a run and are copied through verbatim. No line-level skip
        # is needed (and a line-level skip would wrongly leave shattered words on
        # any line that happens to contain a citation).
        toks = line.split(" ")
        # find maximal runs of alpha-ish fragments and repair shattered ones
        result, i = [], 0
        while i < len(toks):
            t = toks[i]
            if t.isalpha():
                j = i
                while j < len(toks) and toks[j].isalpha():
                    j += 1
                run = toks[i:j]
                if _is_shattered_run(run):
                    joined = "".join(run).lower()
                    seg, cov = resegment(joined, words)
                    result.append(seg if cov >= 0.6 else " ".join(run))
                else:
                    result.append(" ".join(run))
                i = j
            else:
                result.append(t)
                i += 1
        out_lines.append(" ".join(x for x in result if x != ""))
    return "\n".join(out_lines)


def normalize_text(text: str, words: frozenset | None = None) -> str:
    """Full normalization for an already-de-boilerplated page/section."""
    text = text.replace(SOFT_HYPHEN, "")
    text = re.sub(r"([a-z])-\n([a-z])", r"\1\2", text)  # dehyphenate
    text = despace(text, words)
    text = re.sub(r"[ \t]+", " ", text)                  # collapse runs of spaces
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


# ----------------------------------------------------------------------------- de-boilerplate
def _sig(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().lower())


def detect_boilerplate(pages, top_n: int = 2, bot_n: int = 2, min_frac: float = 0.5):
    """Detect per-volume running headers/footers from page-edge lines that recur
    across >= min_frac of pages. `pages` is a list of page texts."""
    npages = len(pages)
    if npages < 4:
        min_frac = 0.6
    top, bot = Counter(), Counter()
    for pg in pages:
        lines = [ln for ln in pg.split("\n") if ln.strip()]
        for ln in lines[:top_n]:
            top[_sig(ln)] += 1
        for ln in lines[-bot_n:]:
            bot[_sig(ln)] += 1
    thresh = max(2, int(min_frac * npages))

    def keep(sig, cnt):
        # only treat as boilerplate if it recurs AND is not itself a content line
        # carrying protected digits (a recurring real line would be unusual, but guard anyway)
        return cnt >= thresh and not PROTECTED_DIGIT.search(sig)

    headers = {s for s, c in top.items() if keep(s, c) and s}
    footers = {s for s, c in bot.items() if keep(s, c) and s}
    return {"headers": headers, "footers": footers}


def _gutter_lineset(page: str, min_run: int = 4, max_gap: int = 12):
    """Return the set of line indices that form a line-number gutter: a run of
    integer-only lines whose values are monotonically non-decreasing with small
    gaps. Returns indices to drop (empty if no gutter)."""
    lines = page.split("\n")
    ints = []  # (idx, value)
    for idx, ln in enumerate(lines):
        m = INT_ONLY_LINE.match(ln)
        if m:
            ints.append((idx, int(m.group(1))))
    if len(ints) < min_run:
        return set()
    # find the longest non-decreasing small-step subsequence (contiguous in ints order)
    best, cur = [], [ints[0]]
    for k in range(1, len(ints)):
        prev_v = ints[k - 1][1]
        v = ints[k][1]
        if 0 <= v - prev_v <= max_gap:
            cur.append(ints[k])
        else:
            if len(cur) > len(best):
                best = cur
            cur = [ints[k]]
    if len(cur) > len(best):
        best = cur
    if len(best) >= min_run:
        return {idx for idx, _ in best}
    return set()


def is_page_number_line(line: str) -> bool:
    return bool(PAGE_WORD_LINE.match(line) or ROMAN_ONLY_LINE.match(line)
                or INT_ONLY_LINE.match(line))


def strip_page(page: str, boilerplate: dict, drop_gutter: bool = True,
               drop_page_numbers: bool = True):
    """Strip furniture from a single page. Returns (clean_text, removed_lines)."""
    headers = boilerplate.get("headers", set())
    footers = boilerplate.get("footers", set())
    lines = page.split("\n")
    gutter = _gutter_lineset(page) if drop_gutter else set()
    out, removed = [], []
    n = len(lines)
    # locate first/last non-blank indices to scope header/footer removal to edges
    nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
    top_zone = set(nonblank[:2])
    bot_zone = set(nonblank[-2:]) if len(nonblank) >= 2 else set(nonblank)
    for i, ln in enumerate(lines):
        sig = _sig(ln)
        # CONTENT-SAFETY GUARD: keep any line with protected digits unless it is a
        # known repeated header/footer signature.
        is_known_boiler = (i in top_zone and sig in headers) or (i in bot_zone and sig in footers)
        if PROTECTED_DIGIT.search(ln) and not is_known_boiler:
            out.append(ln)
            continue
        if is_known_boiler:
            removed.append(ln); continue
        if i in gutter:                      # integer-only gutter line in a run
            removed.append(ln); continue
        if drop_page_numbers and i in (top_zone | bot_zone) and is_page_number_line(ln) \
                and not ALPHA_WORD.search(ln):
            removed.append(ln); continue
        out.append(ln)
    return "\n".join(out), removed


# ----------------------------------------------------------------------------- self-test
def _selftest():
    words = load_dict()
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # 1) de-space recovers shattered-but-correct text
    shattered = "M inutes o f the G eneral A ssembly o f the C h u rc h"
    fixed = despace(shattered, words)
    toks = tokenize(fixed)
    hit = sum(t in words for t in toks) / max(1, len(toks))
    print(f"    despace -> {fixed!r}  (hitrate {hit:.2f})")
    check("despace recovers shattered text (hitrate >= 0.9)", hit >= 0.9)

    # 2) de-space leaves clean text essentially unchanged
    clean = "Minutes of the General Assembly of the Presbyterian Church"
    check("despace leaves clean text unchanged", despace(clean, words) == clean)

    # 3) de-space NEVER touches protected digit tokens
    digitline = "The complaint cited BCO 34-1 in SJC Case 2017-01 by a 12-9 vote"
    check("despace preserves BCO 34-1 / 2017-01 / 12-9", despace(digitline, words) == digitline)

    # 4) running header + footer detection and removal
    pages = []
    for p in range(1, 9):
        pages.append(f"MINUTES OF THE GENERAL ASSEMBLY\n34-{p} Some real content line here\n{p}\nPCA Stated Clerk")
    bp = detect_boilerplate(pages)
    print(f"    headers={bp['headers']}  footers={bp['footers']}")
    check("detects running header", "minutes of the general assembly" in bp["headers"])
    check("detects running footer", "pca stated clerk" in bp["footers"])
    clean_pg, removed = strip_page(pages[2], bp)
    check("header+footer+pagenum removed", "MINUTES OF THE GENERAL ASSEMBLY" not in clean_pg
          and "PCA Stated Clerk" not in clean_pg)
    check("content line with GA-item 34-3 survives de-boilerplating", "34-3 Some real content" in clean_pg)

    # 5) line-number gutter (line-numbered overture) stripped; content kept
    overture = ("Overture 5 amend BCO 8-3 as follows\n"
                "5\nThat the word shall be inserted\n"
                "10\nand the section renumbered accordingly\n"
                "15\nso that the chapter reads\n"
                "20\nin its entirety as amended\n"
                "25\nbefore the vote was taken")
    clean_ov, removed_ov = strip_page(overture, {"headers": set(), "footers": set()})
    print(f"    gutter removed lines: {removed_ov}")
    check("gutter integers 5/10/15/20/25 stripped", all(x not in clean_ov.split("\n") for x in ["5","10","15","20","25"]))
    check("overture content + BCO 8-3 kept", "BCO 8-3" in clean_ov and "inserted" in clean_ov and "renumbered" in clean_ov)

    print(f"\nnormalize.py self-test: {'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
