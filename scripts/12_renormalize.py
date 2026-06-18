#!/usr/bin/env python3
"""
12_renormalize.py — second-pass cleanup of build/page_jsonl for the scanned era:

  (1) strip RUNNING HEADERS/FOOTERS that carry a page number (e.g. "116 MINUTES OF
      THE GENERAL ASSEMBLY") — missed by the first pass because the varying page
      number made each line textually unique AND tripped the protect-digits guard.
      We cluster on a number-stripped signature, then strip page-edge lines whose
      signature is a confirmed running header.

  (2) rejoin SPORADIC dictionary-confirmed intra-word splits ("G od"->God,
      "Confes sion"->Confession) that the shattered-run de-spacer skipped. A pair is
      joined ONLY when the concatenation is a dictionary word and the two pieces are
      not BOTH already words (so "a part", "view point", "in to" are left intact).

CLI:
  12_renormalize.py --dry-run [vol ...]   report changes, write nothing (default: all vols)
  12_renormalize.py --apply  [vol ...]    rewrite page_jsonl (backs up each to *.bak once)
"""
from __future__ import annotations
import collections, glob, importlib.util, json, os, re, sys

ROOT = "/workspace"
PJ = os.path.join(ROOT, "build", "page_jsonl")
_s = importlib.util.spec_from_file_location("normalize", os.path.join(ROOT, "scripts", "normalize.py"))
N = importlib.util.module_from_spec(_s); _s.loader.exec_module(N)
WORDS = N.load_dict()
# all dictionary-word prefixes, for the greedy single-word rebuild
PREFIXES = set()
for _w in WORDS:
    _wl = _w.lower()
    for _k in range(1, len(_wl) + 1):
        PREFIXES.add(_wl[:_k])

PUNCT = r"[.,;:'’?!\"\)]"
# never treat these as splittable left-fragments (church abbreviations / initialisms that
# would otherwise merge with the next token: "TE Ed"->teed, "REs in"->resin)
ABBR = {"te", "re", "res", "tes", "sjc", "ccb", "cjb", "bco", "pca", "rao", "ga", "wcf",
        "omsjc", "ne", "se", "nw", "sw", "jr", "sr", "mr", "mrs", "dr", "rev", "no", "op"}


def nsig(line):
    """Signature with leading/trailing non-alpha (page numbers, punctuation) stripped."""
    t = line.strip().lower()
    t = re.sub(r"^[^a-z]+", "", t)
    t = re.sub(r"[^a-z]+$", "", t)
    return re.sub(r"\s+", " ", t)


def detect_running(pages, top_n=2, bot_n=2, min_frac=0.3):
    top, bot = collections.Counter(), collections.Counter()
    for pg in pages:
        lines = [l for l in pg.split("\n") if l.strip()]
        for l in lines[:top_n]:
            sg = nsig(l)
            if len(sg) >= 8 and " " in sg:
                top[sg] += 1
        for l in lines[-bot_n:]:
            sg = nsig(l)
            if len(sg) >= 8 and " " in sg:
                bot[sg] += 1
    thr = max(3, int(min_frac * len(pages)))
    return {s for s, c in top.items() if c >= thr}, {s for s, c in bot.items() if c >= thr}


def strip_headers(text, heads, foots, top_n=3, bot_n=3):
    lines = text.split("\n")
    nb = [i for i, l in enumerate(lines) if l.strip()]
    topz = set(nb[:top_n]); botz = set(nb[-bot_n:]) if len(nb) >= bot_n else set(nb)
    out, removed = [], []
    for i, l in enumerate(lines):
        sg = nsig(l)
        if (i in topz and sg in heads) or (i in botz and sg in foots):
            removed.append(l); continue
        out.append(l)
    return "\n".join(out), removed


def rejoin(text):
    """Conservative dict-guided rejoin of sporadic intra-word splits. Returns
    (new_text, list_of_joins) for auditing."""
    joins, out_lines = [], []
    for line in text.split("\n"):
        toks = line.split(" ")
        res, i = [], 0
        while i < len(toks):
            a = toks[i]
            # allow leading opening punctuation on a ('"G od' -> '"God'); use acore for logic
            am = re.match(r"^([\"“‘'’(]*)([A-Za-z]+)$", a)
            if i + 1 < len(toks) and am:
                aprefix, acore = am.group(1), am.group(2)
                # b = a word, optional possessive/contraction (straight or curly apostrophe), punct
                m = re.match(r"^([A-Za-z]+)([’'][A-Za-z]+)?(%s*)$" % PUNCT, toks[i + 1])
                if m:
                    bcore, btail = m.group(1), (m.group(2) or "") + (m.group(3) or "")
                    joined = acore + bcore
                    jl, al, bl = joined.lower(), acore.lower(), bcore.lower()
                    a_is_frag = al not in WORDS or (len(acore) == 1 and acore.isupper())
                    # an all-caps multi-letter token only merges with another all-caps piece
                    # ("COM MITTEE"->COMMITTEE) — never with a mixed-case word ("TE Ed")
                    casing_ok = not (acore.isupper() and len(acore) >= 2 and not bcore.isupper())
                    ok = (jl in WORDS                       # concatenation is a real word
                          and a_is_frag                           # LEFT piece is a fragment, not a
                                                                  # whole word ("the Ses"!=theses)
                          and casing_ok
                          and al not in ABBR and bl not in ABBR   # not a church abbreviation
                          and acore not in ("I", "A", "O")        # genuine single-cap words
                          and len(bcore) >= 2                     # no trailing stray letter
                          and (len(acore) >= 2 or acore.isupper())     # single letter only if capital
                          and (len(joined) >= 4 or acore.isupper()))   # avoid tiny low-conf joins
                    if ok:
                        joins.append((a + " " + toks[i + 1], aprefix + joined + btail))
                        res.append(aprefix + joined + btail); i += 2; continue
            res.append(a); i += 1
        out_lines.append(" ".join(res))
    return "\n".join(out_lines), joins


RUNTOK = re.compile(r"^([A-Za-z]+)(%s*)$" % PUNCT)


def _recase(segwords, orig):
    j = "".join(orig)
    if j.isupper():
        return [w.upper() for w in segwords]
    if all(f[:1].isupper() for f in orig if f):
        return [w.capitalize() for w in segwords]
    if orig and orig[0][:1].isupper():
        r = list(segwords); r[0] = r[0].capitalize(); return r
    return segwords


# frequent function words: never START a word-rebuild window on one (so "the o logy"
# and "in a new" are not merged). Short real words the de-spacer must respect.
COMMON = set(("the of a to in is it as at be by or on an and for was not his her its our you "
              "are he she we they this that from with had has have were will would shall may "
              "can all any no nor so if but out up do did who whom which when then than them "
              "been being one two who his him had her our your their what where").split())


def rebuild_words(text):
    """Rebuild ONE shattered word from a window of consecutive SHORT fragments
    ("pres byte ry"->presbytery, "cu ltu re"->culture, "l au rel"->laurel). A window of
    2-4 tokens, each <=4 chars, whose concatenation is a SINGLE dictionary word of length
    >=5, is collapsed (longest window wins). This skips prose (multi-word runs don't form
    one long word), short false-merges ("and"/"into"/"soon" are <5), initials, and windows
    starting on a common function word — so "found in God" / "of the" are untouched."""
    def is_frag(tok):                          # a short token that is NOT a dictionary word
        mm = RUNTOK.match(tok)
        return bool(mm and len(mm.group(1)) <= 4 and mm.group(1).lower() not in WORDS)

    changes, out_lines = [], []
    for line in text.split("\n"):
        toks = line.split(" ")
        res, i = [], 0
        while i < len(toks):
            m0 = RUNTOK.match(toks[i])
            # a single letter followed by ) or . is a list-marker / initial ("B)", "N."),
            # never a word fragment
            MARKER = r"^[A-Za-z][).]"
            startable = (m0 and len(m0.group(1)) <= 4 and m0.group(1).lower() not in COMMON
                         and m0.group(1).lower() not in ABBR
                         and not re.match(MARKER, toks[i]))
            hit = None
            if startable:
                for k in (4, 3, 2):                       # longest window first
                    if i + k > len(toks):
                        continue
                    win = toks[i:i + k]
                    ms = [RUNTOK.match(t) for t in win]
                    if any(x is None or len(x.group(1)) > 4 or re.match(MARKER, t)
                           or x.group(1).lower() in ABBR
                           for x, t in zip(ms, win)):
                        continue
                    # mid-window trailing punctuation is a boundary, not a continuous
                    # shattered word (guards "exp. and"->expand, "coll. in"->collin)
                    if any(ms[j].group(2) for j in range(k - 1)):
                        continue
                    # the rebuild must RESOLVE the shatter: the next token can't be another
                    # short non-dict fragment (guards "past y[·]ea r"->"pasty ea r")
                    if i + k < len(toks) and is_frag(toks[i + k]):
                        continue
                    cores = [x.group(1) for x in ms]
                    # a single-letter start only leads a run of NON-word fragments
                    # ("G ra ce" ok; "S Park"/"s will"/"O King" -> the 2nd token is a real word)
                    if len(cores[0]) == 1 and cores[1].lower() in WORDS:
                        continue
                    concat = "".join(cores)
                    if (concat.lower() in WORDS and len(concat) >= 5
                            and concat.lower() not in ABBR
                            and sum(1 for c in cores if c.lower() not in WORDS) >= 1):
                        rec = _recase([concat], cores)[0] + ms[-1].group(2)
                        hit = (k, rec, " ".join(win)); break
            if hit:
                k, rec, orig = hit
                changes.append((orig, rec)); res.append(rec); i += k; continue
            res.append(toks[i]); i += 1
        out_lines.append(" ".join(res))
    return "\n".join(out_lines), changes


def process_vol(path, apply):
    recs = [json.loads(l) for l in open(path)]
    pages = [r.get("text", "") for r in recs]
    heads, foots = detect_running(pages)
    # rejoin only on the scanned era (<=2002 / GA<=30): born-digital text is clean, so a
    # rejoin there only manufactures false merges. Header-strip is harmless everywhere.
    yr = next((r.get("year") for r in recs if r.get("year")), None)
    if yr is None:
        m = re.search(r"_(\d{4})", os.path.basename(path)); yr = int(m.group(1)) if m else 0
    do_rejoin = yr <= 2002
    n_hdr, n_join, n_seg, sample_hdr, sample_join, sample_seg = 0, 0, 0, [], [], []
    for r in recs:
        t = r.get("text", "")
        t, removed = strip_headers(t, heads, foots)
        if removed:
            n_hdr += len(removed)
            for x in removed:
                if len(sample_hdr) < 4:
                    sample_hdr.append(x.strip())
        if do_rejoin:
            t, segs = rebuild_words(t)           # multi-fragment runs ("pres byte ry"->presbytery)
            n_seg += len(segs)
            for x in segs:
                if len(sample_seg) < 8:
                    sample_seg.append(x)
            t, joins = rejoin(t)                 # pairwise ("G od"->God, possessives/quotes)
            n_join += len(joins)
            for x in joins:
                if len(sample_join) < 8:
                    sample_join.append(x)
        r["text"] = t
        r["char_count"] = len(t)
    if apply:
        import shutil
        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy(path, bak)          # one-time backup of the pre-renorm page_jsonl
        with open(path, "w") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"heads": heads, "foots": foots, "n_hdr": n_hdr, "n_join": n_join, "n_seg": n_seg,
            "sample_hdr": sample_hdr, "sample_join": sample_join, "sample_seg": sample_seg}


def main():
    apply = "--apply" in sys.argv
    vols = [a for a in sys.argv[1:] if not a.startswith("--")]
    paths = ([os.path.join(PJ, v + ".pages.jsonl") for v in vols] if vols
             else sorted(glob.glob(PJ + "/*.pages.jsonl")))
    grand_h = grand_j = grand_s = 0
    for p in paths:
        v = os.path.basename(p).split(".")[0]
        r = process_vol(p, apply)
        grand_h += r["n_hdr"]; grand_j += r["n_join"]; grand_s += r["n_seg"]
        print(f"{v}: headers_removed={r['n_hdr']}  runs_desegmented={r['n_seg']}  "
              f"pairs_rejoined={r['n_join']}"
              + (f"  running={sorted(r['heads'])[:2]}" if r["heads"] else ""))
        if len(paths) <= 2:
            if r["sample_hdr"]:
                print("   sample headers:", r["sample_hdr"])
            if r["sample_seg"]:
                print("   sample desegments:", [f"{a!r}->{b!r}" for a, b in r["sample_seg"]])
            if r["sample_join"]:
                print("   sample rejoins:", [f"{a!r}->{b!r}" for a, b in r["sample_join"]])
    print(f"\nTOTAL: headers_removed={grand_h}  runs_desegmented={grand_s}  "
          f"pairs_rejoined={grand_j}  ({'APPLIED' if apply else 'DRY-RUN'})")


if __name__ == "__main__":
    main()
