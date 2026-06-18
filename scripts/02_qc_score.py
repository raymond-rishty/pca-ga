#!/usr/bin/env python3
"""
02_qc_score.py — three-channel OCR quality scorer (Phase 0 deliverable).

The original single metric (dictionary hit-rate) is blind to the two failure
modes that matter for this corpus, both verified on disk:
  * WHITESPACE SHATTERING — "m inutes o f the c h u rc h" is 100% character-
    correct but scores 0.286 on dict-hitrate -> would trigger needless re-OCR.
  * DIGIT CORRUPTION — a correct "Case 2017-01 / BCO 8-3" and a mangled
    "Case 2099-01 / BCO 99-12" score IDENTICALLY on dict-hitrate (it cannot see
    digits at all) -> a corrupted case number / vote tally passes as "good".

So quality is judged on three orthogonal channels:
  1. dict_hitrate          — lexical correctness of the words
  2. whitespace_frag       — shattering (routes to de-spacing, NOT re-OCR)
  3. digit_channel         — structural plausibility of case#/BCO/vote tokens
                             (the ONLY signal protecting citation integrity)

Routing verdict (text channel): good | despace | reocr   (digit_flag is orthogonal)
  - high frag + recoverable after de-space -> 'despace' (normalize.py, no re-OCR)
  - low hitrate, not recoverable           -> 'reocr'
  - otherwise                              -> 'good'
  - any implausible digit token            -> digit_flag=True (review/re-OCR,
                                              independent of the text verdict)

Usage:
  02_qc_score.py --selftest
  02_qc_score.py --text "some text"
  02_qc_score.py --pdf minutes/11th_pcaga_1983.pdf --page 100   (needs pdftotext)
"""
from __future__ import annotations
import argparse
import hashlib
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import normalize  # noqa: E402  (shared dict/tokenizer/de-space)

# ---- tunable thresholds (documented; revisit with full-corpus data in Phase 2)
FRAG_TRIGGER = 0.25        # >= this share of single-letter tokens => shattered
RECOVER_OK = 0.85         # de-spaced hitrate at/above this => recoverable
REOCR_BELOW = 0.80        # hitrate below this (and not recoverable) => re-OCR
CASE_YEAR_MIN, CASE_YEAR_MAX = 1973, 2026
BCO_CHAPTER_MAX = 63       # BCO runs FoG 1-25, RoD 31-46, DfW 47-63

# PCA structural acronyms/abbreviations this corpus is saturated with; counting
# them as valid stops dict-hitrate from falsely penalizing real, correct text.
DOMAIN_TERMS = frozenset(
    "sjc ccb bco rao pca opc arp epc wcf wlc wsc te re ga gas msc msa mtw mna "
    "ac cmc rpr byfc ruf pcus pcusa nae".split()
)

CASE_RE = re.compile(r"\b((?:19|20)\d{2})-(\d{1,3})\b")
BCO_RE = re.compile(r"\bBCO\s*0*(\d{1,3})(?:-(\d{1,3}))?\b", re.I)
VOTE_RE = re.compile(r"\b\d{1,3}-\d{1,3}(?:-\d{1,3})?\b")


def check_dict_pin(dict_path=normalize.DEFAULT_DICT,
                   pin_path=os.path.join(os.path.dirname(normalize.DEFAULT_DICT), "words.sha256")):
    """Fail loud if the vendored dictionary drifts from its pinned hash."""
    if not os.path.exists(pin_path):
        return None
    have = hashlib.sha256(open(dict_path, "rb").read()).hexdigest()
    want = open(pin_path).read().strip()
    if have != want:
        raise SystemExit(f"words.txt sha256 {have} != pinned {want} — refusing to score on a drifted dictionary")
    return have


# ----------------------------------------------------------------- channels
def dict_hitrate(text: str, words=None) -> tuple[float, int]:
    words = words or normalize.load_dict()
    toks = normalize.tokenize(text)
    if not toks:
        return 1.0, 0
    return sum(t in words or t in DOMAIN_TERMS for t in toks) / len(toks), len(toks)


def whitespace_frag(text: str) -> float:
    """Fraction of whitespace-split alpha tokens that are a single letter."""
    raw = [t for t in re.split(r"\s+", text.strip()) if t and t.isalpha()]
    if not raw:
        return 0.0
    singles = sum(1 for t in raw if len(t) == 1)
    return singles / len(raw)


def digit_channel(text: str) -> dict:
    """Surface citation-critical digit tokens and check structural plausibility."""
    present, implausible = [], []
    for m in CASE_RE.finditer(text):
        tok = m.group(0); yr = int(m.group(1))
        present.append(("case", tok))
        if not (CASE_YEAR_MIN <= yr <= CASE_YEAR_MAX):
            implausible.append(tok)
    for m in BCO_RE.finditer(text):
        ch = int(m.group(1))
        present.append(("bco", m.group(0)))
        if ch < 1 or ch > BCO_CHAPTER_MAX:
            implausible.append(m.group(0))
    return {"present": [t for _, t in present],
            "kinds": sorted({k for k, _ in present}),
            "implausible": implausible,
            "has_citation": bool(present)}


def classify(text: str, words=None) -> dict:
    words = words or normalize.load_dict()
    hit, ntok = dict_hitrate(text, words)
    frag = whitespace_frag(text)
    despaced_hit = hit
    if frag >= FRAG_TRIGGER:
        despaced_hit, _ = dict_hitrate(normalize.despace(text, words), words)
    dig = digit_channel(text)

    if frag >= FRAG_TRIGGER and despaced_hit >= RECOVER_OK:
        verdict = "despace"
    elif hit < REOCR_BELOW and despaced_hit < RECOVER_OK:
        verdict = "reocr"
    else:
        verdict = "good"
    return {
        "verdict": verdict,
        "dict_hitrate": round(hit, 4),
        "whitespace_frag": round(frag, 4),
        "despaced_hitrate": round(despaced_hit, 4),
        "n_tokens": ntok,
        "digit_flag": bool(dig["implausible"]),
        "digit_present": dig["has_citation"],
        "digit_kinds": dig["kinds"],
        "digit_implausible": dig["implausible"],
    }


def score_pdf_page(pdf: str, page: int) -> dict:
    txt = subprocess.run(["pdftotext", "-q", "-f", str(page), "-l", str(page), pdf, "-"],
                         capture_output=True, text=True).stdout
    out = classify(txt)
    out["pdf"], out["page"] = pdf, page
    return out


# ----------------------------------------------------------------- self-test
PROBES = {
    "clean":         "Minutes of the General Assembly of the Presbyterian Church in America",
    "shattered":     "M inutes o f the G eneral A ssembly o f the P resbyterian C h u rc h",
    "char_corrupt":  "Mlnntes 0f tlie Geueral Assernbly 0f tbe Presbyteriau Cliurcb iu Arnerica",
    "digit_ok":      "Complaint sustained in SJC Case 2017-01 citing BCO 8-3 by a 12-9 vote",
    "digit_corrupt": "Complaint sustained in SJC Case 2099-01 citing BCO 99-12 by a 12-9 vote",
}


def _selftest() -> int:
    check_dict_pin()
    words = normalize.load_dict()
    fails = []
    print(f"{'probe':14} {'verdict':9} {'hit':>5} {'frag':>5} {'desp':>5} {'digflag':>7}")
    res = {}
    for name, text in PROBES.items():
        r = classify(text, words); res[name] = r
        print(f"{name:14} {r['verdict']:9} {r['dict_hitrate']:.2f} {r['whitespace_frag']:.2f} "
              f"{r['despaced_hitrate']:.2f}  {str(r['digit_flag']):>6}")

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    check("clean -> good",                       res["clean"]["verdict"] == "good")
    check("shattered -> despace (NOT reocr)",     res["shattered"]["verdict"] == "despace")
    check("char_corrupt -> reocr",                res["char_corrupt"]["verdict"] == "reocr")
    check("digit_ok: text good, no digit flag",   res["digit_ok"]["verdict"] == "good" and not res["digit_ok"]["digit_flag"])
    check("digit_corrupt: digit_flag raised",     res["digit_corrupt"]["digit_flag"] is True)
    check("digit channel sees what dict-hitrate cannot "
          "(ok vs corrupt hitrate ~equal, flag differs)",
          abs(res["digit_ok"]["dict_hitrate"] - res["digit_corrupt"]["dict_hitrate"]) < 0.05
          and res["digit_ok"]["digit_flag"] != res["digit_corrupt"]["digit_flag"])

    print(f"\n02_qc_score.py self-test: {'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--text")
    ap.add_argument("--pdf")
    ap.add_argument("--page", type=int)
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    if a.text is not None:
        import json; print(json.dumps(classify(a.text), indent=2)); return
    if a.pdf and a.page:
        import json; print(json.dumps(score_pdf_page(a.pdf, a.page), indent=2)); return
    ap.print_help()


if __name__ == "__main__":
    main()
