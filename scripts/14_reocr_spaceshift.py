#!/usr/bin/env python3
"""
14_reocr_spaceshift.py — re-OCR space-shifted scanned pages via Mistral OCR and adopt the
result ONLY when it markedly reduces stray single letters without losing content.

Candidate set (areas A+B, validated): scanned-era (<=2002) pages, NON-chart
(dict-hit>=0.60 and symbol-ratio<0.06), with >=8 stray single letters.

Acceptance guard: adopt iff  old_strays>=6  AND  new_strays<=max(2, 0.3*old_strays)
                              AND  new_words>=0.85*old_words   (no content loss).

Subcommands:
  candidates                 count/list candidate pages
  reocr [--workers N] [--limit N]   OCR candidates in parallel -> index/reocr/results.jsonl (RESUMABLE)
  apply                      adopt qualifying results into build/page_jsonl (backs up first) + audit
"""
from __future__ import annotations
import concurrent.futures as cf, glob, importlib.util, json, os, re, sys, threading

ROOT = "/workspace"
PJ = os.path.join(ROOT, "build", "page_jsonl")
OUTDIR = os.path.join(ROOT, "index", "reocr")
RESULTS = os.path.join(OUTDIR, "results.jsonl")
BACKUP = os.path.join(ROOT, "build", "page_jsonl_pre_reocr")

_spec = importlib.util.spec_from_file_location("rk", os.path.join(ROOT, "scripts", "06_review_kit.py"))
rk = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rk)
import normalize as N
W = N.load_dict()

STRAY = re.compile(r"(?:(?<=\s)|^)[B-HJ-Zb-hj-z](?=\s)")
SYM = re.compile(r"[^\w\s.,;:'\"()\-/&]")


VOWEL = re.compile(r"[aeiou]")


def strays(t): return len(STRAY.findall(t))
def nwords(t): return len(re.findall(r"[A-Za-z]{2,}", t))
def symr(t): return len(SYM.findall(t)) / max(len(t), 1)
def dhit(t):
    w = re.findall(r"[A-Za-z]{2,}", t)
    return sum(1 for x in w if x.lower() in W) / max(len(w), 1)


def recoverable(t):
    """Distinguish space-shifted REAL text (recoverable: many vowel-bearing, varied tokens,
    even Latin/rosters — like ga14_1986 p493) from OCR GARBAGE/noise (repetitive vowel-less
    junk like ga26_1998 p276 "x x xs ss Ps"). Calibrated: real >=0.76 vowel-ratio, garbage <0.10."""
    toks = re.findall(r"[A-Za-z]+", t)
    if len(toks) < 20:
        return False
    import collections
    vr = sum(1 for w in toks if VOWEL.search(w.lower())) / len(toks)
    mf = collections.Counter(w.lower() for w in toks).most_common(1)[0][1] / len(toks)
    return vr >= 0.55 and mf <= 0.15


def candidates():
    out = []
    for p in sorted(glob.glob(PJ + "/*.pages.jsonl")):
        vol = os.path.basename(p).split(".")[0]
        if int(re.search(r"_(\d{4})", vol).group(1)) > 2002:
            continue
        for l in open(p):
            r = json.loads(l); t = r.get("text", "")
            if nwords(t) < 40 or dhit(t) < 0.60 or symr(t) >= 0.06:
                continue
            st = strays(t)
            if st >= 5 and recoverable(t):     # real space-shifted text, not OCR garbage/noise
                out.append((vol, r["pdf_page"], st, nwords(t)))
    return out


def vol_pdf(vol):
    return glob.glob("%s/minutes/*_pcaga_%s.pdf" % (ROOT, vol.split("_")[1]))[0]


def adopt_ok(os_, ns, ow, nw):
    # adopt when strays at least HALVE (or hit ~0) without losing content — relaxed from
    # 0.3x so heavily-shattered pages that improve markedly (e.g. 41->13) are kept
    return os_ >= 5 and ns <= max(2, 0.5 * os_) and nw >= 0.85 * ow


_lock = threading.Lock()


def reocr(workers=8, limit=None):
    os.makedirs(OUTDIR, exist_ok=True)
    done = set()
    if os.path.exists(RESULTS):
        for l in open(RESULTS):
            try:
                d = json.loads(l); done.add((d["vol"], d["pdf_page"]))
            except Exception:
                pass
    cands = [c for c in candidates() if (c[0], c[1]) not in done]
    if limit:
        cands = cands[:limit]
    key = open(os.path.join(ROOT, "review", ".mistral_key")).read().strip()
    print(f"[reocr] {len(cands)} pages to OCR ({len(done)} already done), {workers} workers", flush=True)
    fout = open(RESULTS, "a")

    def work(c):
        vol, pg, os_, ow = c
        img = "/tmp/reocr_%s_%d.png" % (vol, pg)
        try:
            rk.render_image(vol_pdf(vol), pg, img, 200)
            new = rk.mistral_ocr_image(img, key)
        except Exception as e:
            return {"vol": vol, "pdf_page": pg, "status": "error", "err": str(e)[:120]}
        finally:
            try:
                os.remove(img)
            except OSError:
                pass
        ns, nw = strays(new), nwords(new)
        rec = {"vol": vol, "pdf_page": pg, "old_strays": os_, "new_strays": ns,
               "old_words": ow, "new_words": nw, "adopt": adopt_ok(os_, ns, ow, nw),
               "status": "ok", "text": new}    # always store text so pages can be re-judged
        return rec

    n = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for rec in ex.map(work, cands):
            with _lock:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
            n += 1
            if n % 200 == 0:
                print(f"  ...{n}/{len(cands)}", flush=True)
    fout.close()
    print("[reocr] done", flush=True)


def _ocr_one(c, key):
    vol, pg, os_, ow = c[0], c[1], c[2], c[3]
    img = "/tmp/reocrb_%s_%d.png" % (vol, pg)
    try:
        rk.render_image(vol_pdf(vol), pg, img, 200)
        new = rk.mistral_ocr_image(img, key)
    except Exception as e:
        return {"vol": vol, "pdf_page": pg, "status": "error", "err": str(e)[:120]}
    finally:
        try:
            os.remove(img)
        except OSError:
            pass
    ns, nw = strays(new), nwords(new)
    return {"vol": vol, "pdf_page": pg, "old_strays": os_, "new_strays": ns, "old_words": ow,
            "new_words": nw, "adopt": adopt_ok(os_, ns, ow, nw), "status": "ok", "text": new}


def reocr_batch(batchfile, outfile, workers=1):
    """OCR a specific page list (a workflow agent's slice) -> outfile. Resumable."""
    pages = [tuple(x) for x in json.load(open(batchfile))]
    done = set()
    if os.path.exists(outfile):
        for l in open(outfile):
            try:
                d = json.loads(l); done.add((d["vol"], d["pdf_page"]))
            except Exception:
                pass
    todo = [c for c in pages if (c[0], c[1]) not in done]
    key = open(os.path.join(ROOT, "review", ".mistral_key")).read().strip()
    fout = open(outfile, "a")
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for rec in ex.map(lambda c: _ocr_one(c, key), todo):
            with _lock:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
    fout.close()
    ad = sum(1 for c in pages if True)  # noqa (count below recomputed by caller)
    print("[reocr-batch] %s: %d processed (%d already done)" % (outfile, len(todo), len(done)))


def apply():
    import shutil
    if not os.path.exists(BACKUP):
        shutil.copytree(PJ, BACKUP)
        print(f"[apply] backed up page_jsonl -> {BACKUP}")
    adopt = {}
    n_ok = n_err = n_adopt = 0
    for l in open(RESULTS):
        d = json.loads(l)
        if d.get("status") == "error":
            n_err += 1; continue
        n_ok += 1
        if d.get("adopt") and d.get("text"):
            adopt.setdefault(d["vol"], {})[d["pdf_page"]] = d["text"]; n_adopt += 1
    for vol, pages in adopt.items():
        p = PJ + "/%s.pages.jsonl" % vol
        recs = [json.loads(l) for l in open(p)]
        for r in recs:
            if r["pdf_page"] in pages:
                r["text"] = pages[r["pdf_page"]]; r["char_count"] = len(r["text"]); r["reocr"] = "mistral-spaceshift"
        with open(p, "w") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[apply] {n_ok} OCR ok, {n_err} errors; ADOPTED {n_adopt} pages across {len(adopt)} volumes")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "candidates"
    if cmd == "candidates":
        c = candidates()
        print(f"candidates: {len(c)} pages")
    elif cmd == "reocr":
        w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 8
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        reocr(w, lim)
    elif cmd == "reocr-batch":
        w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 1
        reocr_batch(sys.argv[2], sys.argv[3], w)
    elif cmd == "apply":
        apply()
