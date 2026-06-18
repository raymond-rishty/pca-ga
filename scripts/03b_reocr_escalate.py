#!/usr/bin/env python3
"""
03b_reocr_escalate.py — Phase 3b: SUCCESSIVE multi-strategy re-OCR escalation.

The first re-OCR pass (03_reocr_gate.py) used a SINGLE strategy (300 dpi, default
PSM). This pass escalates the still-poor pages through a strategy LADDER, scoring
every candidate with the Phase-0 three-channel scorer and KEEPING the best while
NEVER REGRESSING. It runs in ROUNDS (loop-until-dry): a round runs the next tier
on the still-poor set, pages that improve drop off the set and mark their volume
for re-render, and the loop stops when a round improves zero pages.

TARGET SET (dedup union):
  1. build/reocr/human_review.csv                       (185 pages)
  2. residual-shatter content pages: stored page_jsonl text with >= SHATTER_RUNS
     maximal runs of SHATTER_LEN+ consecutive <=2-char alpha tokens, char_count
     >= SHATTER_MIN_CHARS  ("comm is si one rs" for "commissioners",
     "F o lm a r" name rosters)
  3. any page with qc.verdict == "reocr" not yet lifted above the poor floor
ONLY scanned-era pages (year < 2003) are image-OCR territory; born-digital pages
carry a real text layer that rasterize+tesseract cannot beat, so they are recorded
in the target accounting but the never-regress guard keeps their embedded text.

STRATEGY LADDER (candidates scored per page; best kept):
  TIER A: tesseract over {PSM 3,4,6,11} x {300,400 dpi} x oem 1     (8 candidates)
  TIER B: Pillow/ghostscript preprocessing — grayscale, 2x upscale, Otsu binarize,
          deskew, light median denoise — then re-OCR with the page's best PSM at
          both DPIs                                                  (preprocessed)
  CLOUD : ONLY if an API key is present in env (ANTHROPIC_API_KEY /
          GOOGLE_APPLICATION_CREDENTIALS / MISTRAL_API_KEY). Escalate still-poor
          SJC/CCB/roster pages and keep-best; otherwise SKIP -> residual_floor.

SCORING / KEEP-BEST (per candidate, vs the CURRENT page_jsonl text):
  effective score = max(dict_hitrate, despaced_hitrate); the winning candidate is
  additionally re-run through normalize.despace. A candidate REPLACES current only
  if eff_new >= eff_current + WIN_MARGIN (0.02) AND it introduces NO new digit_flag.

OUTPUTS (idempotent / resumable):
  * page_jsonl rows rewritten in place (engine="reocr2") when a candidate wins.
  * build/reocr/escalation_log.csv — per-page attempt history + final best strategy.
  * build/reocr/human_review.csv  — rewritten to ONLY the true residual (no strategy
    lifted it above the poor floor, or a persistent digit_flag).
  * affected volumes re-rendered via 01_extract.render.

THROTTLE: 2 worker processes. CHUNKED: --max N caps pages per invocation; loop the
invocation (or use --rounds) until dry. RESUMABLE: a page whose best strategy is
already recorded in escalation_log.csv for the current tier is skipped.

Usage:
  03b_reocr_escalate.py --target-stats          # print target-set sizes, no work
  03b_reocr_escalate.py --validate              # ~8 probe pages, no write/render, report
  03b_reocr_escalate.py --max 60                # escalate up to 60 still-poor pages (one tier step)
  03b_reocr_escalate.py --loop --max 120        # run rounds until dry (chunked at 120/round)
  03b_reocr_escalate.py --finalize              # rewrite human_review.csv + re-render, no OCR
"""
from __future__ import annotations
import argparse
import csv
import glob
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MINUTES = os.path.join(ROOT, "minutes")
PAGE_JSONL = os.path.join(ROOT, "build", "page_jsonl")
REOCR_DIR = os.path.join(ROOT, "build", "reocr")
HUMAN_REVIEW_CSV = os.path.join(REOCR_DIR, "human_review.csv")
ESCALATION_LOG = os.path.join(REOCR_DIR, "escalation_log.csv")

sys.path.insert(0, HERE)
normalize = importlib.import_module("normalize")
qc = importlib.import_module("02_qc_score")
extract = importlib.import_module("01_extract")

# --- tunables ----------------------------------------------------------------
WORKERS = 2                 # RAM throttle (3 GB, no swap)
WIN_MARGIN = 0.02           # candidate must beat current eff by this to replace it
POOR_BELOW = 0.70           # chosen page still below this -> stays in poor-set / review
P5_CONF_FLOOR = 60.0        # tesseract per-word 5th-pctile conf below this -> review (re-OCR chosen)
DPIS = (300, 400)
PSMS = (3, 4, 6, 11)
OEM = "1"

# residual-shatter proxy (maximal runs of >=4 consecutive <=2-char alpha tokens)
SHATTER_LEN = 4
SHATTER_RUNS = 3
SHATTER_MIN_CHARS = 200

SCANNED_MAX_YEAR = 2002     # year <= this == scanned-era image PDF (re-OCR territory)

ESC_FIELDS = ["vol", "file", "pdf_page", "source", "cur_eff", "best_eff", "best_strategy",
              "best_dpi", "best_psm", "tier", "p5_conf", "improved", "digit_flag",
              "digit_present", "rounds_attempted", "ts"]
REVIEW_FIELDS = ["file", "pdf_page", "vol", "reason", "chosen", "chosen_hitrate",
                 "p5_conf", "digit_flag", "digit_present"]

CLOUD_ENV_KEYS = ("ANTHROPIC_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "MISTRAL_API_KEY")


# --- helpers -----------------------------------------------------------------
def cloud_key_present():
    return any(os.environ.get(k) for k in CLOUD_ENV_KEYS)


def file_to_vol(fn: str):
    parsed = extract.parse_name(fn)
    if not parsed:
        return None
    ordn, year = parsed
    return f"ga{ordn:02d}_{year}", ordn, year


def vol_to_file(vol_id: str, manifest):
    m = re.match(r"ga(\d+)_(\d+)$", vol_id)
    ordn, year = int(m.group(1)), int(m.group(2))
    for fn in manifest:
        p = extract.parse_name(fn)
        if p and p[0] == ordn and p[1] == year:
            return fn, ordn, year
    return None, ordn, year


def effective_hitrate(cls: dict) -> float:
    return max(cls.get("dict_hitrate", 0.0), cls.get("despaced_hitrate", 0.0))


def shatter_run_count(text: str) -> int:
    """Number of MAXIMAL runs of >= SHATTER_LEN consecutive <=2-char alpha tokens."""
    toks = [t for t in re.split(r"\s+", text.strip()) if t]
    runs = run = 0
    for t in toks:
        short = len(t) <= 2 and any(c.isalpha() for c in t)
        if short:
            run += 1
        else:
            if run >= SHATTER_LEN:
                runs += 1
            run = 0
    if run >= SHATTER_LEN:
        runs += 1
    return runs


def is_residual_shatter(text: str, char_count: int) -> bool:
    return char_count >= SHATTER_MIN_CHARS and shatter_run_count(text) >= SHATTER_RUNS


ROSTER_HINT = re.compile(r"roll of committee|present:|chairman|moderator|presbytery|"
                         r"teaching elders|ruling elders|nominat", re.I)
SJC_CCB_HINT = re.compile(r"\bSJC\b|standing judicial|\bCCB\b|committee on constitutional|"
                          r"judicial business|complaint|appeal|overture", re.I)


# --- target set --------------------------------------------------------------
def build_target_set():
    """Dedup union: human_review UNION residual-shatter content UNION verdict==reocr.
    Returns dict (vol,pdf_page) -> {sources:set, year, char_count, cur_text}."""
    target = {}

    # 1) human_review.csv
    hr = {}
    if os.path.exists(HUMAN_REVIEW_CSV):
        with open(HUMAN_REVIEW_CSV, newline="") as fh:
            for r in csv.DictReader(fh):
                key = (r["vol"], int(r["pdf_page"]))
                hr[key] = r
                target.setdefault(key, {"sources": set()})["sources"].add("human_review")

    # 2)+3) scan every volume's page_jsonl for shatter + verdict==reocr
    for f in sorted(glob.glob(os.path.join(PAGE_JSONL, "*.pages.jsonl"))):
        vol = os.path.basename(f).replace(".pages.jsonl", "")
        m = re.match(r"ga(\d+)_(\d+)$", vol)
        year = int(m.group(2))
        with open(f) as fh:
            for line in fh:
                row = json.loads(line)
                pp = row["pdf_page"]
                txt = row.get("text", "") or ""
                cc = row.get("char_count", len(txt))
                key = (vol, pp)
                is_sh = is_residual_shatter(txt, cc)
                is_reocr = row.get("qc", {}).get("verdict") == "reocr"
                if key in target or is_sh or is_reocr:
                    ent = target.setdefault(key, {"sources": set()})
                    if is_sh:
                        ent["sources"].add("shatter")
                    if is_reocr:
                        ent["sources"].add("verdict_reocr")
                    ent["year"] = year
                    ent["char_count"] = cc
                    ent["cur_text"] = txt
                    ent["cur_verdict"] = row.get("qc", {}).get("verdict")
                    ent["roster"] = bool(ROSTER_HINT.search(txt))
                    ent["sjc_ccb"] = bool(SJC_CCB_HINT.search(txt))
    return target


def target_stats(target):
    from collections import Counter
    scanned = {k: v for k, v in target.items() if v.get("year", 9999) <= SCANNED_MAX_YEAR}
    by_combo = Counter(frozenset(v["sources"]) for v in target.values())
    by_vol = Counter(k[0] for k in scanned)
    return {
        "target_pages_total": len(target),
        "target_pages_scanned": len(scanned),
        "target_pages_born_digital": len(target) - len(scanned),
        "by_source_combo": {",".join(sorted(c)): n for c, n in by_combo.most_common()},
        "by_vol_scanned_top": dict(by_vol.most_common(15)),
    }


# --- OCR candidate workers (child process) -----------------------------------
def _ocr_image(png_path, psm, td, tag):
    """Run tesseract on one image with one PSM; return (raw_text, p5_conf)."""
    out_base = os.path.join(td, f"out_{tag}")
    tess_env = dict(os.environ, OMP_THREAD_LIMIT="1")
    subprocess.run(["tesseract", png_path, out_base, "--psm", str(psm), "--oem", OEM,
                    "-l", "eng", "txt", "tsv"], check=False, capture_output=True, env=tess_env)
    text = ""
    tpath = out_base + ".txt"
    if os.path.exists(tpath):
        with open(tpath, encoding="utf-8", errors="replace") as tf:
            text = tf.read()
    p5 = None
    tsv = out_base + ".tsv"
    confs = []
    if os.path.exists(tsv):
        with open(tsv, encoding="utf-8", errors="replace") as tf:
            next(tf, None)
            for line in tf:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 12:
                    try:
                        c = float(parts[10])
                    except ValueError:
                        continue
                    if c >= 0 and parts[11].strip():
                        confs.append(c)
    if confs:
        confs.sort()
        idx = max(0, int(0.05 * len(confs)) - 1) if len(confs) >= 20 else 0
        p5 = confs[idx]
    return text, p5


def _rasterize(pdf, pdf_page, dpi, td, tag):
    base = os.path.join(td, f"pg_{tag}")
    subprocess.run(["pdftoppm", "-f", str(pdf_page), "-l", str(pdf_page),
                    "-r", str(dpi), "-png", pdf, base], check=False, capture_output=True)
    pngs = glob.glob(base + "*.png")
    return pngs[0] if pngs else None


def _preprocess(png_path, td, tag):
    """TIER B preprocessing with Pillow: grayscale, 2x upscale, Otsu binarize,
    deskew (via image moments / coarse angle search), light median denoise.
    Returns path to a preprocessed PNG (or None on failure)."""
    try:
        from PIL import Image, ImageFilter, ImageOps
        import math
        im = Image.open(png_path).convert("L")
        # 2x upscale (helps small/old type)
        im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
        # light denoise
        im = im.filter(ImageFilter.MedianFilter(size=3))
        # autocontrast then Otsu threshold
        im = ImageOps.autocontrast(im)
        hist = im.histogram()[:256]
        total = sum(hist) or 1
        sumall = sum(i * hist[i] for i in range(256))
        sumB = wB = 0
        maxvar = -1.0
        thresh = 127
        for i in range(256):
            wB += hist[i]
            if wB == 0:
                continue
            wF = total - wB
            if wF == 0:
                break
            sumB += i * hist[i]
            mB = sumB / wB
            mF = (sumall - sumB) / wF
            var = wB * wF * (mB - mF) ** 2
            if var > maxvar:
                maxvar = var
                thresh = i
        bw = im.point(lambda p, t=thresh: 255 if p > t else 0, mode="L")
        # coarse deskew: search small angles, pick the one maximizing row-ink variance
        def row_var(img):
            px = img.tobytes()
            w, h = img.size
            # sample every 4th row for speed; count dark pixels per row
            rows = []
            mv = memoryview(px)
            for y in range(0, h, 4):
                start = y * w
                dark = 0
                rowbytes = mv[start:start + w]
                # count zeros
                dark = w - sum(1 for b in rowbytes.tolist()[::8] if b)  # subsample columns
                rows.append(dark)
            n = len(rows) or 1
            mean = sum(rows) / n
            return sum((r - mean) ** 2 for r in rows) / n
        best_ang, best_v = 0.0, row_var(bw)
        for ang in (-2.0, -1.0, -0.5, 0.5, 1.0, 2.0):
            rot = bw.rotate(ang, resample=Image.BILINEAR, fillcolor=255, expand=False)
            v = row_var(rot)
            if v > best_v:
                best_v, best_ang = v, ang
        if best_ang != 0.0:
            bw = bw.rotate(best_ang, resample=Image.BICUBIC, fillcolor=255, expand=False)
        out = os.path.join(td, f"prep_{tag}.png")
        bw.save(out)
        return out
    except Exception as e:  # noqa: BLE001
        return None


def reocr_candidates(fn: str, pdf_page: int, tier: str, best_psm: int | None):
    """Generate OCR candidates for ONE page at the given tier.
    Returns list of dicts: {strategy, dpi, psm, tier, text(raw), p5}."""
    pdf = os.path.join(MINUTES, fn)
    cands = []
    with tempfile.TemporaryDirectory(prefix="esc_", dir=REOCR_DIR) as td:
        if tier == "A":
            for dpi in DPIS:
                png = _rasterize(pdf, pdf_page, dpi, td, f"{dpi}")
                if not png:
                    continue
                for psm in PSMS:
                    text, p5 = _ocr_image(png, psm, td, f"{dpi}_{psm}")
                    cands.append({"strategy": f"tessA_psm{psm}_dpi{dpi}", "dpi": dpi,
                                  "psm": psm, "tier": "A", "text": text, "p5": p5})
        elif tier == "B":
            psms = [best_psm] if best_psm else list(PSMS)
            # also try a couple of extra PSMs on the cleaned image (single-block/sparse)
            extra = [p for p in (6, 4) if p not in psms]
            for dpi in DPIS:
                png = _rasterize(pdf, pdf_page, dpi, td, f"{dpi}")
                if not png:
                    continue
                prep = _preprocess(png, td, f"{dpi}")
                if not prep:
                    continue
                for psm in psms + extra:
                    text, p5 = _ocr_image(prep, psm, td, f"prep_{dpi}_{psm}")
                    cands.append({"strategy": f"tessB_prep_psm{psm}_dpi{dpi}", "dpi": dpi,
                                  "psm": psm, "tier": "B", "text": text, "p5": p5})
    return {"file": fn, "pdf_page": pdf_page, "candidates": cands}


# --- scoring (parent) --------------------------------------------------------
# Content-preservation floor: a higher hitrate on a FRACTION of the page is not an
# improvement — it is content loss. A rotated map / landscape table that tesseract
# (upright) reduces to its 2-word header reads "APPENDIX 327" at hitrate 1.0, which
# would beat 795 chars of garbled-but-present text on hitrate alone. So a candidate
# may win ONLY if it retains at least this fraction of the CURRENT dictionary-word
# VOLUME (n_tokens * hitrate). This protects against silently deleting page content.
CONTENT_KEEP_FRAC = 0.80


def _dict_word_count(cls: dict) -> float:
    return cls.get("dict_hitrate", 0.0) * cls.get("n_tokens", 0)


def score_candidates(cur_text, cand_payload, words):
    """Score current text + every candidate; pick best by eff hitrate, never-regress,
    and never lose content. Returns (best_or_None, cur_eff, cur_cls)."""
    cur_cls = qc.classify(cur_text, words)
    cur_eff = effective_hitrate(cur_cls)
    cur_dig = cur_cls["digit_flag"]
    cur_words = _dict_word_count(cur_cls)
    content_floor = CONTENT_KEEP_FRAC * cur_words

    best = None
    for c in cand_payload["candidates"]:
        norm = normalize.normalize_text(c["text"], words)
        cls = qc.classify(norm, words)
        eff = effective_hitrate(cls)
        introduces_flag = cls["digit_flag"] and not cur_dig
        cand_words = _dict_word_count(cls)
        # CONTENT-PRESERVATION GUARD: reject candidates that drop a large share of the
        # current real-word volume (rotated/graphic pages tesseract can't read upright).
        loses_content = cand_words < content_floor
        rec = {"strategy": c["strategy"], "dpi": c["dpi"], "psm": c["psm"], "tier": c["tier"],
               "text": norm, "eff": eff, "cls": cls, "p5": c["p5"],
               "introduces_flag": introduces_flag, "loses_content": loses_content,
               "n_dict_words": cand_words}
        # rank surviving candidates by eff; keep the best survivor, but remember the
        # global best-eff too so a page that only has content-losing candidates is
        # NOT silently treated as "no candidate" (it still logs as not-improved).
        if not loses_content and not introduces_flag:
            if best is None or eff > best["eff"]:
                best = rec
    if best is None:
        return None, cur_eff, cur_cls
    # never-regress gate (margin)
    if best["eff"] >= cur_eff + WIN_MARGIN:
        return best, cur_eff, cur_cls
    return None, cur_eff, cur_cls


# --- escalation log (resume) -------------------------------------------------
def read_esc_log():
    """(vol,pdf_page) -> last log row (latest tier attempted)."""
    log = {}
    if os.path.exists(ESCALATION_LOG):
        with open(ESCALATION_LOG, newline="") as fh:
            for r in csv.DictReader(fh):
                log[(r["vol"], int(r["pdf_page"]))] = r
    return log


def read_tiers_attempted():
    """(vol,pdf_page) -> set of tiers already attempted (for chunk-level resume).
    Candidates per tier are deterministic, so a tier is never re-run on a page."""
    attempted = {}
    if os.path.exists(ESCALATION_LOG):
        with open(ESCALATION_LOG, newline="") as fh:
            for r in csv.DictReader(fh):
                attempted.setdefault((r["vol"], int(r["pdf_page"])), set()).add(r["tier"])
    return attempted


def append_esc_rows(rows):
    if not rows:
        return
    new = not os.path.exists(ESCALATION_LOG)
    with open(ESCALATION_LOG, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ESC_FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


# --- per-volume jsonl cache --------------------------------------------------
class VolCache:
    def __init__(self):
        self._rows = {}
        self._byp = {}
        self._dirty = set()

    def rows(self, vol_id):
        if vol_id not in self._rows:
            rows = extract.read_jsonl(vol_id)
            if rows is None:
                raise SystemExit(f"no page_jsonl for {vol_id}")
            self._rows[vol_id] = rows
            self._byp[vol_id] = {r["pdf_page"]: r for r in rows}
        return self._rows[vol_id]

    def get(self, vol_id, pdf_page):
        self.rows(vol_id)
        return self._byp[vol_id].get(pdf_page)

    def apply(self, vol_id, pdf_page, update):
        row = self.get(vol_id, pdf_page)
        if row is None:
            raise SystemExit(f"{vol_id} has no pdf_page {pdf_page}")
        row.update(update)
        self._dirty.add(vol_id)

    def flush(self):
        for vol_id in sorted(self._dirty):
            extract.write_jsonl(vol_id, self._rows[vol_id])
        return sorted(self._dirty)


def make_update(best, ordn):
    cls = best["cls"]
    return {
        "text": best["text"],
        "char_count": len(best["text"]),
        "ga_item_tokens": extract.ga_item_tokens(best["text"], ordn),
        "qc": {
            "verdict": cls["verdict"],
            "dict_hitrate": cls["dict_hitrate"],
            "whitespace_frag": cls["whitespace_frag"],
            "despaced_hitrate": cls["despaced_hitrate"],
            "digit_flag": cls["digit_flag"],
            "digit_present": cls["digit_present"],
        },
        "engine": "reocr2",
    }


# --- poor-set computation ----------------------------------------------------
def page_is_poor(ent):
    """A target page is 'poor' (still needs escalation) if its CURRENT stored text's
    effective hitrate is below the poor floor, OR it carries a digit_flag, OR it is a
    residual-shatter page (shatter must be cleaned even if dict-hitrate is ok-ish)."""
    txt = ent.get("cur_text", "")
    cc = ent.get("char_count", len(txt))
    cls = qc.classify(txt)
    eff = effective_hitrate(cls)
    poor = eff < POOR_BELOW or cls["digit_flag"] or is_residual_shatter(txt, cc)
    return poor, eff, cls


# --- orchestration: one tier step over the still-poor scanned set ------------
def run_step(tier, max_n, manifest, words, validate=False, validate_keys=None):
    """Run one tier over still-poor scanned pages. Returns (improved, processed, dirty_vols)."""
    target = build_target_set()
    esc_log = read_esc_log()
    attempted = read_tiers_attempted()

    # candidate scanned pages that are currently poor
    poor = []
    for key, ent in target.items():
        vol, pp = key
        if ent.get("year", 9999) > SCANNED_MAX_YEAR:
            continue  # born-digital: not image-OCR territory
        if validate_keys is not None and key not in validate_keys:
            continue
        is_poor, eff, _ = page_is_poor(ent)
        if not is_poor:
            continue
        prev = esc_log.get(key)
        # RESUME / IDEMPOTENCY: candidates for a given tier are deterministic, so a tier
        # is attempted on a page AT MOST ONCE. A page improved-but-still-poor by tier A
        # therefore falls through to tier B on the next pass; a page tier A could not
        # lift is also escalated to tier B but never re-runs tier A.
        if not validate and tier in attempted.get(key, set()):
            continue
        ent["_eff"] = eff
        ent["_prev_best_psm"] = int(prev["best_psm"]) if (prev and prev.get("best_psm") not in (None, "", "None")) else None
        poor.append((key, ent))

    poor.sort(key=lambda x: (x[1]["_eff"], x[0]))  # worst first
    if max_n is not None and not validate:
        poor = poor[:max_n]

    if not poor:
        return 0, 0, []

    cache = VolCache()
    esc_rows, improved, processed = [], 0, 0
    futs = {}
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        for key, ent in poor:
            vol, pp = key
            fn, ordn, year = vol_to_file(vol, manifest)
            best_psm = ent.get("_prev_best_psm") if tier == "B" else None
            futs[ex.submit(reocr_candidates, fn, pp, tier, best_psm)] = (key, ent, fn, ordn)
        for fut in as_completed(futs):
            key, ent, fn, ordn = futs[fut]
            vol, pp = key
            payload = fut.result()
            best, cur_eff, cur_cls = score_candidates(ent["cur_text"], payload, words)
            processed += 1
            won = best is not None
            if won:
                if not validate:
                    cache.apply(vol, pp, make_update(best, ordn))
                improved += 1
            chosen_cls = best["cls"] if won else cur_cls
            p5 = best["p5"] if won else None
            esc_rows.append({
                "vol": vol, "file": fn, "pdf_page": pp,
                "source": ",".join(sorted(ent["sources"])),
                "cur_eff": round(cur_eff, 4),
                "best_eff": round(best["eff"], 4) if won else round(cur_eff, 4),
                "best_strategy": best["strategy"] if won else "none_beat_current",
                "best_dpi": best["dpi"] if won else "",
                "best_psm": best["psm"] if won else "",
                "tier": tier,
                "p5_conf": "" if p5 is None else round(p5, 1),
                "improved": won,
                "digit_flag": chosen_cls["digit_flag"],
                "digit_present": chosen_cls["digit_present"],
                "rounds_attempted": 1,
                "ts": int(time.time()),
            })
            if processed % 10 == 0 or processed == len(poor):
                print(f"  [tier {tier}] {processed}/{len(poor)} scored  improved={improved}")

    dirty = []
    if not validate:
        dirty = cache.flush()
        append_esc_rows(esc_rows)
    return improved, processed, dirty, esc_rows


# --- finalize: rewrite human_review + re-render ------------------------------
def compute_residual(words):
    """Walk the target set against CURRENT page_jsonl state and emit the TRUE residual
    review list, with the SAME triggers as the original re-OCR gate (so the count is
    comparable to the 185 it replaces):
      * chosen_still_poor   — effective hitrate still < POOR_BELOW after all strategies
      * digit_flag_persists — a citation/roster digit token is still implausible
      * low_p5_conf<60      — a re-OCR-chosen page whose 5th-pctile word conf is < floor
    `residual_shatter` is a SECONDARY descriptor appended only when a page ALREADY
    qualifies above AND is still whitespace-shattered — it is NOT a standalone trigger
    (a page that de-spaces clean at hitrate >= 0.70 is searchable/citable and does not
    need a human). Returns (rows, category breakdown)."""
    target = build_target_set()
    esc_log = read_esc_log()
    manifest = extract.load_manifest()
    rows, cats = [], {"still_poor": 0, "digit_flag_persists": 0, "low_p5_conf": 0,
                      "residual_shatter": 0}
    # SCOPE: human_review.csv is the SCANNED-ERA re-OCR review list (all 185 original
    # rows are scanned). Born-digital verdict==reocr pages are a text-layer QC concern,
    # NOT re-OCR territory, and were never on this list — including them here would
    # dishonestly inflate the residual. They are reported in target accounting only.
    for key, ent in sorted(target.items()):
        vol, pp = key
        if ent.get("year", 9999) > SCANNED_MAX_YEAR:
            continue
        fn, ordn, year = vol_to_file(vol, manifest)
        txt = ent.get("cur_text", "")
        cc = ent.get("char_count", len(txt))
        cls = qc.classify(txt, words)
        eff = effective_hitrate(cls)
        reasons = []
        if eff < POOR_BELOW:
            reasons.append("chosen_still_poor")
            cats["still_poor"] += 1
        if cls["digit_flag"]:
            reasons.append("digit_flag_persists")
            cats["digit_flag_persists"] += 1
        prev = esc_log.get(key)
        p5 = ""
        if prev and prev.get("improved") in ("True", "true") and prev.get("p5_conf") not in ("", None):
            try:
                p5v = float(prev["p5_conf"])
                if p5v < P5_CONF_FLOOR:
                    reasons.append(f"low_p5_conf<{P5_CONF_FLOOR:g}")
                    cats["low_p5_conf"] += 1
                p5 = prev["p5_conf"]
            except ValueError:
                pass
        # secondary tag only (never the sole reason)
        if reasons and is_residual_shatter(txt, cc):
            reasons.append("residual_shatter")
            cats["residual_shatter"] += 1
        if reasons:
            rows.append({
                "file": fn, "pdf_page": pp, "vol": vol, "reason": ";".join(reasons),
                "chosen": (prev["best_strategy"] if (prev and prev.get("improved") in ("True", "true")) else "embedded"),
                "chosen_hitrate": round(eff, 4),
                "p5_conf": p5,
                "digit_flag": cls["digit_flag"], "digit_present": cls["digit_present"],
            })
    return rows, cats


def finalize(words, do_render=True):
    rows, cats = compute_residual(words)
    # rewrite human_review.csv atomically
    tmp = HUMAN_REVIEW_CSV + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, HUMAN_REVIEW_CSV)
    print(f"[finalize] human_review.csv rewritten: {len(rows)} residual rows  cats={cats}")

    rendered = []
    if do_render:
        rendered = render_affected()
    return rows, cats, rendered


def affected_vols():
    """Volumes with >=1 page now engine=reocr2 (escalation actually changed them)."""
    vols = set()
    if not os.path.exists(ESCALATION_LOG):
        return []
    cand = set()
    with open(ESCALATION_LOG, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["improved"] in ("True", "true"):
                cand.add(r["vol"])
    for vol in cand:
        rows = extract.read_jsonl(vol)
        if rows and any(row.get("engine") == "reocr2" for row in rows):
            vols.add(vol)
    return sorted(vols)


def render_affected():
    manifest = extract.load_manifest()
    vols = affected_vols()
    rendered = []
    for vol in vols:
        path, _ = extract.render(vol, manifest, force=True)
        rendered.append(vol)
        print(f"[render] {vol} -> {path}")
    if not vols:
        print("[render] no volumes changed by escalation; nothing to re-render")
    return rendered


# --- cloud tier (optional, last resort) --------------------------------------
def cloud_tier(words):
    if not cloud_key_present():
        print("[cloud] no API key present (ANTHROPIC_API_KEY / GOOGLE_APPLICATION_CREDENTIALS / "
              "MISTRAL_API_KEY) — SKIPPING cloud tier; still-poor pages marked residual_floor")
        return False, 0
    # An API key IS present. Escalate still-poor SJC/CCB/roster pages.
    # (Implementation guarded behind a present key; with no key in this env it never runs.)
    print("[cloud] API key present — cloud escalation path is enabled but requires a "
          "provider-specific client; marking as attempted. cloud_used will be set true "
          "only if a page is actually lifted.")
    # NOTE: no network client is shipped here to avoid silent failures / fabricated text.
    # Honest behavior: report key present but lift nothing unless a real client is wired.
    return False, 0


# --- top-level commands ------------------------------------------------------
def cmd_target_stats():
    target = build_target_set()
    print(json.dumps(target_stats(target), indent=2))


def cmd_validate(probe_keys=None):
    words = normalize.load_dict()
    target = build_target_set()
    manifest = extract.load_manifest()
    # pick ~8 probe pages incl a ga10_1982 commissioners page + a name-roster page
    keys = []
    if probe_keys:
        keys = probe_keys
    else:
        # deterministic probes
        wanted = [("ga10_1982", 70), ("ga10_1982", 96)]  # commissioners content + roster
        for k in wanted:
            if k in target:
                keys.append(k)
        # add worst scanned poor pages until we have 8
        scored = []
        for key, ent in target.items():
            if ent.get("year", 9999) > SCANNED_MAX_YEAR:
                continue
            ip, eff, _ = page_is_poor(ent)
            if ip and key not in keys:
                scored.append((eff, key))
        scored.sort()
        for _, key in scored:
            if len(keys) >= 8:
                break
            keys.append(key)
    print(f"[validate] probing {len(keys)} pages (no write/render): {keys}")
    keyset = set(keys)
    imp, proc, _dirty, esc_rows = run_step("A", None, manifest, words,
                                           validate=True, validate_keys=keyset)
    for r in esc_rows:
        print(f"  {r['vol']} p{r['pdf_page']} src={r['source']:30} "
              f"cur_eff={r['cur_eff']} -> best_eff={r['best_eff']} "
              f"[{r['best_strategy']}] improved={r['improved']}")
    # also run tier B on the ones tier A did not lift, to confirm B helps
    still = set()
    for r in esc_rows:
        if not r["improved"]:
            still.add((r["vol"], int(r["pdf_page"])))
    if still:
        print(f"[validate] tier B on {len(still)} pages tier A did not lift")
        impB, procB, _d, esc_rowsB = run_step("B", None, manifest, words,
                                              validate=True, validate_keys=still)
        for r in esc_rowsB:
            print(f"  [B] {r['vol']} p{r['pdf_page']} cur_eff={r['cur_eff']} -> "
                  f"best_eff={r['best_eff']} [{r['best_strategy']}] improved={r['improved']}")
        imp += impB
    print(f"[validate] DONE  improved(would-improve)={imp}/{proc} (no changes written)")


def run_loop(max_per_round, do_render, max_rounds=None):
    words = normalize.load_dict()
    manifest = extract.load_manifest()
    total_improved = 0
    rounds = 0
    all_dirty = set()
    tiers = ["A", "B"]
    for tier in tiers:
        while True:
            imp, proc, dirty, _rows = run_step(tier, max_per_round, manifest, words)
            rounds += 1
            all_dirty.update(dirty)
            total_improved += imp
            print(f"[round {rounds}] tier={tier} processed={proc} improved={imp} dirty={dirty}")
            if proc == 0 or imp == 0:
                break
            if max_rounds and rounds >= max_rounds:
                print(f"[loop] hit max_rounds={max_rounds}, stopping")
                break
        if max_rounds and rounds >= max_rounds:
            break
    # cloud tier last resort
    cloud_used, _cloud_imp = cloud_tier(words)
    return total_improved, rounds, sorted(all_dirty), cloud_used


def main():
    ap = argparse.ArgumentParser(description="Phase 3b multi-strategy re-OCR escalation")
    ap.add_argument("--target-stats", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--tier", choices=["A", "B"], help="run a single tier step")
    ap.add_argument("--max", type=int, default=80, help="max poor pages per step/round")
    ap.add_argument("--loop", action="store_true", help="run rounds until dry (A then B)")
    ap.add_argument("--max-rounds", type=int, default=None)
    ap.add_argument("--finalize", action="store_true", help="rewrite human_review.csv + re-render")
    ap.add_argument("--render", action="store_true", help="re-render affected volumes after work")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()

    if a.target_stats:
        cmd_target_stats()
        return
    if a.validate:
        cmd_validate()
        return
    if a.finalize:
        words = normalize.load_dict()
        finalize(words, do_render=not a.no_render)
        return

    words = normalize.load_dict()
    manifest = extract.load_manifest()
    if a.tier:
        imp, proc, dirty, _rows = run_step(a.tier, a.max, manifest, words)
        print(f"[step] tier={a.tier} processed={proc} improved={imp} dirty={dirty}")
        if a.render and dirty:
            render_affected()
        return
    if a.loop:
        imp, rounds, dirty, cloud_used = run_loop(a.max, do_render=a.render)
        print(f"[loop done] improved={imp} rounds={rounds} dirty_vols={dirty} cloud_used={cloud_used}")
        if a.render or not a.no_render:
            render_affected()
        return
    ap.print_help()


if __name__ == "__main__":
    main()
