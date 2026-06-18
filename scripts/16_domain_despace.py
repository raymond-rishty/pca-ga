#!/usr/bin/env python3
"""
16_domain_despace.py — collapse ANY spacing of a curated set of high-frequency PCA terms
to their canonical form. Unlike the general de-spacer, this is exact-match against a known
vocabulary, so it is SAFE (no false merges): a token window whose letters (ignoring spaces
and punctuation) exactly equal a target's letters is replaced with the canonical term.

  "comm ittee" / "com mittee" / "committe e"            -> Committee / committee
  "presbyterian ch urchin america" / "pres by terian..." -> Presbyterian Church in America
  "pres by te ry"                                        -> Presbytery / presbytery

Common nouns keep the case of the first fragment (capitalized vs lowercase); multi-word
proper names use canonical casing.

CLI:  16_domain_despace.py --dry-run [vol...]
      16_domain_despace.py --apply  [vol...]   (backs up page_jsonl once to *_pre_domain)
"""
from __future__ import annotations
import glob, json, os, re, shutil, sys

ROOT = "/workspace"
PJ = os.path.join(ROOT, "build", "page_jsonl")
BACKUP = os.path.join(ROOT, "build", "page_jsonl_pre_domain")

# vocabulary (curated polity/denomination phrases + roster-derived presbytery names and party
# surnames + common church names) is generated into scripts/domain_terms.json
_DT = json.load(open(os.path.join(ROOT, "scripts", "domain_terms.json")))
KEYS = {}     # despaced-lowercase -> (canonical, kind)
for _p in _DT["proper_phrase"]:                # multi-word phrases: forced canonical casing
    KEYS[re.sub(r"[^a-z]", "", _p.lower())] = (_p, "phrase")
for _c in _DT["common"]:                       # common nouns: any case, case-preserved
    KEYS[_c.lower()] = (_c.lower(), "common")
for _s in _DT["proper_single"]:                # proper names: only when source Capitalized
    KEYS[_s.lower()] = (_s.lower(), "propers")
for _r in _DT.get("resplit", []):              # space-SHIFT fixes: "ch urchin" -> "church in"
    KEYS[re.sub(r"[^a-z]", "", _r.lower())] = (_r, "resplit")
PREFIXES = set()
for _k in KEYS:
    for _n in range(1, len(_k) + 1):
        PREFIXES.add(_k[:_n])
MAXW = 12
MAXLEN = max(len(k) for k in KEYS)

# character-level OCR fixups (misread token -> correct token, case-sensitive, word-boundary):
# e.g. "Wamor"->"Warrior". Applied before despacing; safe because keys are rare non-words.
_CORR = _DT.get("corrections", {})
_CORR_RE = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, _CORR))) if _CORR else None


def alpha(s):
    return re.sub(r"[^A-Za-z]", "", s)


def _is_initial(t):
    # a lone uppercase letter, optionally trailed by '.' or ')' — a person's middle initial
    return bool(re.fullmatch(r"[A-Za-z][.)]?", t)) and t[0].isupper()


def process(text):
    ncorr = 0
    if _CORR_RE:                               # fix character-level OCR misreads first
        text, ncorr = _CORR_RE.subn(lambda m: _CORR[m.group(0)], text)
    # whitespace-tokenize the WHOLE page (spaces AND newlines) so a shattered term/phrase can
    # span a line break ("presbyterian ch urchin\namerica" -> Presbyterian Church in America),
    # while layout elsewhere is preserved (each token keeps its trailing separator).
    parts = re.split(r"(\s+)", text)
    toks = parts[0::2]
    seps = parts[1::2]
    while len(seps) < len(toks):
        seps.append("")
    out, i, changed = [], 0, 0
    while i < len(toks):
        first_cap = bool(alpha(toks[i]) and alpha(toks[i])[0].isupper())
        acc, best = "", None
        for j in range(i, min(i + MAXW, len(toks))):
            if re.search(r"[^A-Za-z.,;:'\"()\-/&‘’“”]", toks[j]):
                break                          # never cross a token with a digit or junk symbol:
                                               # "car o 11na"=Carolina (li->11); "<N O^ Tt o"=table garbage
            core = alpha(toks[j])
            if not core:                       # pure punctuation/number breaks the run
                break
            acc += core
            al = acc.lower()
            if len(al) > MAXLEN:
                break
            if al in KEYS:
                canon, kind = KEYS[al]
                ok = not (kind == "propers" and not first_cap)   # proper names: only if Capitalized
                # never let a lone-capital MIDDLE INITIAL complete a surname ("Robert S."->Roberts),
                # but DO allow lone-capital word fragments in non-name terms ("JO URNA L"->JOURNAL)
                if ok and kind == "propers" and any(_is_initial(toks[k]) for k in range(i + 1, j + 1)):
                    ok = False
                # resplit fixes SHIFTED spacing ("ch urchin"->"church in")
                if ok and kind == "resplit":
                    # a leading single-letter+period/paren is a LIST MARKER or initial, not a
                    # shifted word ("i. San Francisco" is a list item, not "is an Francisco")
                    if re.fullmatch(r"[A-Za-z][.)]", toks[i]):
                        ok = False
                    # if the source tokens already spell the target ("church in" / "Church, in"),
                    # leave them untouched so punctuation and line breaks are preserved
                    elif [alpha(t).lower() for t in toks[i:j + 1] if alpha(t)] == canon.lower().split():
                        ok = False
                if ok:
                    best = (j, canon, kind)
            if al not in PREFIXES:
                break
        if best and best[0] > i:               # only multi-token (space-shattered) spans
            j, canon, kind = best
            lead = re.match(r"^[^A-Za-z]*", toks[i]).group()
            tail = re.search(r"[^A-Za-z]*$", toks[j]).group()
            src = "".join(alpha(t) for t in toks[i:j + 1])
            if kind == "phrase" or (kind == "resplit" and canon != canon.lower()):
                # canonical phrase OR a PROPER-noun resplit target ("Presbytery of Illiana") ->
                # keep the target's casing (UPPER if the source was all-caps)
                disp = canon.upper() if src.isupper() else canon
            elif kind == "propers":
                disp = canon.upper() if src.isupper() else canon.capitalize()
            else:                              # common nouns AND lowercase resplit (church in, order by)
                disp = (canon.upper() if src.isupper()
                        else canon.capitalize() if src[:1].isupper() else canon.lower())
            repl = lead + disp + tail
            orig = "".join(toks[k] + seps[k] for k in range(i, j)) + toks[j]
            if repl != orig:
                changed += 1
            out.append(repl + seps[j])         # internal separators collapsed; keep the one after
            i = j + 1
        else:
            out.append(toks[i] + seps[i]); i += 1
    return "".join(out), changed + ncorr


def main():
    apply = "--apply" in sys.argv
    vols = [a for a in sys.argv[1:] if not a.startswith("--")]
    paths = ([os.path.join(PJ, v + ".pages.jsonl") for v in vols] if vols
             else sorted(glob.glob(PJ + "/*.pages.jsonl")))
    # scanned era only — born-digital page_jsonl already holds clean markdown; de-spacing it
    # only risks mangling bold spans / merging "Robert S." names, with nothing to gain
    paths = [p for p in paths if int(re.search(r"_(\d{4})", os.path.basename(p)).group(1)) <= 2002]
    if apply and not os.path.exists(BACKUP):
        shutil.copytree(PJ, BACKUP); print(f"[backup] page_jsonl -> {BACKUP}")
    grand = 0
    for p in paths:
        vol = os.path.basename(p).split(".")[0]
        recs = [json.loads(l) for l in open(p)]
        vn = 0
        for r in recs:
            t = r.get("text", "")
            c = 0
            for _ in range(3):                 # iterate to a fixed point: a resplit ("or derby"->
                nt, ci = process(t)            # "order by") can re-form a canonical phrase ("Book of
                c += ci                        # Church Order") that the prior single pass overshot
                if nt == t:
                    break
                t = nt
            if c:
                vn += c; r["text"] = t; r["char_count"] = len(t)
        grand += vn
        if apply and vn:
            with open(p, "w") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if vn > 200 or vols:
            print(f"  {vol}: {vn} domain-term fixes")
    print(f"\nTOTAL domain-term fixes: {grand}  ({'APPLIED' if apply else 'DRY-RUN'})")


if __name__ == "__main__":
    main()
