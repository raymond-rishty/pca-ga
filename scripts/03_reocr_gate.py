#!/usr/bin/env python3
"""
03_reocr_gate.py — Phase 3: selective, page-level re-OCR, keep-better-of-two.

Re-OCRs ONLY the pages listed in build/reocr/reocr_queue.csv (the scanned-era
character-corrupt + digit-flagged pages produced by Phase 2). For each page:

  1. Rasterize the single source page with `pdftoppm -f P -l P -r 300 -png`
     (GLOB the output — pdftoppm zero-pads to the document's digit width), run
     `tesseract <png> stdout -l eng` for text and `tesseract <png> <base> tsv`
     for per-word confidence, then DELETE the PNG.
  2. Score the fresh re-OCR text AND the existing embedded text with the
     Phase-0 three-channel scorer (02_qc_score.classify). The embedded text is
     the SOURCE OF TRUTH row in build/page_jsonl/<vol>.pages.jsonl, already
     de-boilerplated + de-spaced. Re-OCR text is run through the same
     normalize.normalize_text before scoring so the comparison is apples-to-apples.
  3. KEEP-BETTER-OF-TWO, NEVER REGRESS: re-OCR wins only if its effective hitrate
     beats embedded by a margin AND it does not introduce a NEW digit_flag. When
     re-OCR wins, the page's jsonl row is updated in place (text + char_count +
     ga_item_tokens + qc + engine="reocr") and the volume is marked for re-render.
  4. Every page is logged to build/reocr/reocr_decisions.csv
       file,pdf_page,embedded_hitrate,reocr_hitrate,chosen,p5_conf
     Pages where the CHOSEN text still scores poor, OR a digit_flag persists on a
     citation/roster page, are appended to build/reocr/human_review.csv
     (never silently passed).
  5. After the queue is exhausted, the affected volumes' markdown is re-rendered
     from the updated page_jsonl via 01_extract.render.

THROTTLE: 2 worker processes (RAM ~3 GB, no swap; 300-dpi rasterization +
tesseract working set fits ~2x). PNGs deleted immediately after scoring.

RESUMABLE / IDEMPOTENT: a (file,pdf_page) already present in reocr_decisions.csv
is skipped. CHUNKED: --max N processes at most N undecided pages this run; loop
the script (e.g. --max 80) until the queue is exhausted. A queue larger than
4000 pages processes 4000 and records `capped_remainder` explicitly — no silent
truncation.

Usage:
  03_reocr_gate.py --validate           # process ~5 pages, do NOT re-render, report
  03_reocr_gate.py --max 80             # process up to 80 undecided pages
  03_reocr_gate.py --max 80 --render    # ... and re-render affected volumes after
  03_reocr_gate.py --render-only        # just re-render volumes touched per decisions
  03_reocr_gate.py --stats              # print queue/decision/kept/review counts, no work
"""
from __future__ import annotations
import argparse
import csv
import glob
import importlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MINUTES = os.path.join(ROOT, "minutes")
PAGE_JSONL = os.path.join(ROOT, "build", "page_jsonl")
REOCR_DIR = os.path.join(ROOT, "build", "reocr")
QUEUE_CSV = os.path.join(REOCR_DIR, "reocr_queue.csv")
DECISIONS_CSV = os.path.join(REOCR_DIR, "reocr_decisions.csv")
HUMAN_REVIEW_CSV = os.path.join(REOCR_DIR, "human_review.csv")

sys.path.insert(0, HERE)
normalize = importlib.import_module("normalize")
qc = importlib.import_module("02_qc_score")
extract = importlib.import_module("01_extract")

# --- gate tunables -----------------------------------------------------------
WORKERS = 2                 # RAM throttle (3 GB, no swap)
RASTER_DPI = 300
QUEUE_CAP = 4000            # process at most this many; record the rest as capped_remainder
WIN_MARGIN = 0.02           # re-OCR must beat embedded by this on effective hitrate to win
POOR_BELOW = 0.70           # chosen page still poor -> human review
P5_CONF_FLOOR = 60.0        # tesseract per-word 5th-pctile conf below this -> review (when re-OCR chosen)

DECISION_FIELDS = ["file", "pdf_page", "embedded_hitrate", "reocr_hitrate", "chosen", "p5_conf"]
REVIEW_FIELDS = ["file", "pdf_page", "vol", "reason", "chosen", "chosen_hitrate",
                 "p5_conf", "digit_flag", "digit_present"]


# --- helpers -----------------------------------------------------------------
def file_to_vol(fn: str):
    """'11th_pcaga_1983.pdf' -> ('ga11_1983', ordinal, year). Reuses the canonical parser."""
    parsed = extract.parse_name(fn)
    if not parsed:
        return None
    ordn, year = parsed
    return f"ga{ordn:02d}_{year}", ordn, year


def effective_hitrate(cls: dict) -> float:
    """The embedded pipeline always de-spaces, so a page's honest lexical quality is
    the better of its raw and de-spaced hitrate. Used as the keep-better-of-two metric."""
    return max(cls.get("dict_hitrate", 0.0), cls.get("despaced_hitrate", 0.0))


def read_queue():
    rows = []
    with open(QUEUE_CSV, newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    return rows


def read_decisions_keys():
    """Set of (file, pdf_page-str) already decided -> for resume/idempotency."""
    done = set()
    if os.path.exists(DECISIONS_CSV):
        with open(DECISIONS_CSV, newline="") as fh:
            for r in csv.DictReader(fh):
                done.add((r["file"], str(r["pdf_page"])))
    return done


def append_rows(path, fields, rows):
    if not rows:
        return
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


# --- the re-OCR worker (runs in a child process) -----------------------------
def reocr_page(fn: str, pdf_page: int) -> dict:
    """Rasterize ONE page, run tesseract for text + TSV confidence, delete the PNG,
    and return raw OCR text + 5th-percentile word confidence. No scoring here (the
    parent scores so the dictionary/thresholds stay in one place)."""
    pdf = os.path.join(MINUTES, fn)
    text, p5 = "", None
    with tempfile.TemporaryDirectory(prefix="reocr_", dir=REOCR_DIR) as td:
        base = os.path.join(td, "pg")
        # 1) rasterize the single page at 300 dpi; pdftoppm zero-pads the page suffix
        subprocess.run(
            ["pdftoppm", "-f", str(pdf_page), "-l", str(pdf_page),
             "-r", str(RASTER_DPI), "-png", pdf, base],
            check=False, capture_output=True,
        )
        pngs = glob.glob(base + "*.png")  # GLOB: suffix is zero-padded to doc digit width
        if not pngs:
            return {"file": fn, "pdf_page": pdf_page, "ok": False,
                    "text": "", "p5_conf": None, "err": "no_png"}
        png = pngs[0]
        # ONE tesseract pass emits BOTH the text and the per-word TSV config outputs
        # (base.txt + base.tsv) — identical OCR result to two passes, half the cost.
        # 300-dpi full-page scan OCR is the throughput bottleneck, so this matters.
        out_base = os.path.join(td, "out")
        # Pin tesseract to ONE OpenMP thread: with 2 parallel workers on a
        # 4-core/3 GB box, multi-threaded tesseract oversubscribes the CPU
        # (load avg ~7) and thrashes, hurting total throughput. Single-thread
        # per worker keeps the 2-worker throttle honest and cuts memory.
        tess_env = dict(os.environ, OMP_THREAD_LIMIT="1")
        subprocess.run(["tesseract", png, out_base, "-l", "eng", "txt", "tsv"],
                       check=False, capture_output=True, env=tess_env)
        txt_path = out_base + ".txt"
        if os.path.exists(txt_path):
            with open(txt_path, encoding="utf-8", errors="replace") as tf:
                text = tf.read()
        # per-word confidence via TSV (5th percentile — one mangled roster word
        # must not be hidden by a high mean)
        tsv_path = out_base + ".tsv"
        confs = []
        if os.path.exists(tsv_path):
            with open(tsv_path, encoding="utf-8", errors="replace") as tf:
                next(tf, None)  # header
                for line in tf:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 12:
                        try:
                            c = float(parts[10]); wtext = parts[11]
                        except ValueError:
                            continue
                        if c >= 0 and wtext.strip():
                            confs.append(c)
        if confs:
            confs.sort()
            idx = max(0, int(0.05 * len(confs)) - 1) if len(confs) >= 20 else 0
            p5 = confs[idx]
        # PNG + TSV deleted with the TemporaryDirectory on context exit
    return {"file": fn, "pdf_page": pdf_page, "ok": True, "text": text, "p5_conf": p5}


# --- scoring / decision (parent process) -------------------------------------
def score_and_decide(qrow: dict, ocr: dict, vol_id: str, ordn: int, embedded_text: str):
    """Score embedded vs re-OCR text, keep-better-of-two (never regress), and
    produce (decision_row, review_row_or_None, updated_jsonl_fields_or_None)."""
    fn = qrow["file"]
    pp = int(qrow["pdf_page"])

    emb_cls = qc.classify(embedded_text)
    emb_hit = effective_hitrate(emb_cls)

    if not ocr["ok"]:
        # rasterization failed -> keep embedded, flag for review
        chosen = "embedded"
        reocr_hit = 0.0
        dec = {"file": fn, "pdf_page": pp, "embedded_hitrate": round(emb_hit, 4),
               "reocr_hitrate": round(reocr_hit, 4), "chosen": chosen,
               "p5_conf": ""}
        review = {"file": fn, "pdf_page": pp, "vol": vol_id, "reason": "reocr_failed_no_png",
                  "chosen": chosen, "chosen_hitrate": round(emb_hit, 4), "p5_conf": "",
                  "digit_flag": emb_cls["digit_flag"], "digit_present": emb_cls["digit_present"]}
        return dec, review, None

    reocr_text = normalize.normalize_text(ocr["text"])
    re_cls = qc.classify(reocr_text)
    reocr_hit = effective_hitrate(re_cls)
    p5 = ocr["p5_conf"]

    # KEEP-BETTER-OF-TWO, NEVER REGRESS:
    #  - re-OCR must beat embedded by WIN_MARGIN on effective hitrate, AND
    #  - re-OCR must NOT introduce a digit_flag the embedded text didn't have
    #    (protecting citation integrity is the whole point of the corpus).
    introduces_digit_flag = re_cls["digit_flag"] and not emb_cls["digit_flag"]
    reocr_wins = (reocr_hit >= emb_hit + WIN_MARGIN) and not introduces_digit_flag

    chosen = "reocr" if reocr_wins else "embedded"
    chosen_cls = re_cls if reocr_wins else emb_cls
    chosen_hit = reocr_hit if reocr_wins else emb_hit
    chosen_text = reocr_text if reocr_wins else embedded_text

    dec = {"file": fn, "pdf_page": pp, "embedded_hitrate": round(emb_hit, 4),
           "reocr_hitrate": round(reocr_hit, 4), "chosen": chosen,
           "p5_conf": "" if p5 is None else round(p5, 1)}

    # --- human-review triggers (never silently pass) -------------------------
    reasons = []
    if chosen_hit < POOR_BELOW:
        reasons.append("chosen_still_poor")
    if chosen_cls["digit_flag"]:
        # a digit_flag persisting on a citation/roster page is exactly the
        # dangerous case the digit channel exists to catch
        reasons.append("digit_flag_persists")
    if chosen == "reocr" and p5 is not None and p5 < P5_CONF_FLOOR:
        reasons.append(f"low_p5_conf<{P5_CONF_FLOOR:g}")
    review = None
    if reasons:
        review = {"file": fn, "pdf_page": pp, "vol": vol_id, "reason": ";".join(reasons),
                  "chosen": chosen, "chosen_hitrate": round(chosen_hit, 4),
                  "p5_conf": "" if p5 is None else round(p5, 1),
                  "digit_flag": chosen_cls["digit_flag"],
                  "digit_present": chosen_cls["digit_present"]}

    update = None
    if reocr_wins:
        update = {
            "text": chosen_text,
            "char_count": len(chosen_text),
            "ga_item_tokens": extract.ga_item_tokens(chosen_text, ordn),
            "qc": {
                "verdict": re_cls["verdict"],
                "dict_hitrate": re_cls["dict_hitrate"],
                "whitespace_frag": re_cls["whitespace_frag"],
                "despaced_hitrate": re_cls["despaced_hitrate"],
                "digit_flag": re_cls["digit_flag"],
                "digit_present": re_cls["digit_present"],
            },
            "engine": "reocr",
        }
    return dec, review, update


# --- per-volume jsonl cache (load once, patch, write once) -------------------
class VolCache:
    """Loads each affected volume's page_jsonl once, indexes rows by pdf_page, and
    writes back only volumes that actually changed (so re-render is scoped)."""
    def __init__(self):
        self._rows = {}     # vol_id -> [rows]
        self._byp = {}      # vol_id -> {pdf_page: row}
        self._dirty = set()

    def rows(self, vol_id):
        if vol_id not in self._rows:
            rows = extract.read_jsonl(vol_id)
            if rows is None:
                raise SystemExit(f"no page_jsonl for {vol_id} (run Phase 2 extract first)")
            self._rows[vol_id] = rows
            self._byp[vol_id] = {r["pdf_page"]: r for r in rows}
        return self._rows[vol_id]

    def get(self, vol_id, pdf_page):
        self.rows(vol_id)
        return self._byp[vol_id].get(pdf_page)

    def apply(self, vol_id, pdf_page, update):
        row = self.get(vol_id, pdf_page)
        if row is None:
            raise SystemExit(f"{vol_id} has no pdf_page {pdf_page} in page_jsonl")
        row.update(update)
        self._dirty.add(vol_id)

    def flush(self):
        for vol_id in sorted(self._dirty):
            extract.write_jsonl(vol_id, self._rows[vol_id])
        return sorted(self._dirty)


# --- orchestration -----------------------------------------------------------
def run(max_n, validate=False, do_render=False):
    os.makedirs(REOCR_DIR, exist_ok=True)
    queue = read_queue()
    queue_size = len(queue)

    capped_remainder = 0
    if queue_size > QUEUE_CAP:
        capped_remainder = queue_size - QUEUE_CAP
        print(f"[cap] queue {queue_size} > {QUEUE_CAP}; processing {QUEUE_CAP}, "
              f"capped_remainder={capped_remainder} (NOT silently dropped)")
        queue = queue[:QUEUE_CAP]

    done = read_decisions_keys()
    todo = [q for q in queue if (q["file"], str(q["pdf_page"])) not in done]

    if validate:
        # validate on the first ~5 undecided pages spanning distinct volumes if possible
        seen_files, picked = set(), []
        for q in todo:
            if q["file"] not in seen_files or len(picked) < 5:
                picked.append(q); seen_files.add(q["file"])
            if len(picked) >= 5:
                break
        todo = picked[:5]
        print(f"[validate] queue_size={queue_size} already_done={len(done)} "
              f"validating {len(todo)} pages (no re-render)")
    else:
        if max_n is not None:
            todo = todo[:max_n]
        print(f"[chunk] queue_size={queue_size} already_done={len(done)} "
              f"remaining_undecided={len([q for q in queue if (q['file'], str(q['pdf_page'])) not in done])} "
              f"processing_this_run={len(todo)}")

    if not todo:
        rendered = []
        if do_render and not validate:
            rendered = render_affected()
        return summarize(queue_size, capped_remainder, rendered)

    cache = VolCache()
    dec_rows, review_rows = [], []
    kept_reocr = kept_embedded = 0

    # Submit raster+tesseract to the pool (throttled to WORKERS); score in the parent.
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = {}
        for q in todo:
            fn = q["file"]; pp = int(q["pdf_page"])
            futs[ex.submit(reocr_page, fn, pp)] = q
        n = 0
        for fut in as_completed(futs):
            q = futs[fut]
            fn = q["file"]; pp = int(q["pdf_page"])
            vol_id, ordn, _year = file_to_vol(fn)
            ocr = fut.result()
            row = cache.get(vol_id, pp)
            embedded_text = row["text"] if row else ""
            dec, review, update = score_and_decide(q, ocr, vol_id, ordn, embedded_text)
            dec_rows.append(dec)
            if review:
                review_rows.append(review)
            if update is not None:
                cache.apply(vol_id, pp, update)
                kept_reocr += 1
            else:
                kept_embedded += 1
            n += 1
            if n % 20 == 0 or n == len(todo):
                print(f"  ...{n}/{len(todo)} scored "
                      f"(reocr_kept={kept_reocr} embedded_kept={kept_embedded} "
                      f"review={len(review_rows)})")

    # Persist: jsonl first (source of truth), then append the audit logs.
    changed_vols = cache.flush()
    append_rows(DECISIONS_CSV, DECISION_FIELDS, dec_rows)
    append_rows(HUMAN_REVIEW_CSV, REVIEW_FIELDS, review_rows)

    print(f"[chunk done] scored={len(dec_rows)} reocr_kept={kept_reocr} "
          f"embedded_kept={kept_embedded} review+={len(review_rows)} "
          f"volumes_updated={len(changed_vols)} {changed_vols}")

    rendered = []
    if do_render and not validate:
        rendered = render_affected()

    return summarize(queue_size, capped_remainder, rendered)


def affected_vols_from_decisions():
    """Volumes that re-OCR actually changed (engine flipped to reocr on >=1 page):
    derived from the page_jsonl source of truth, scoped by the decision log."""
    vols = set()
    if not os.path.exists(DECISIONS_CSV):
        return []
    seen_files = set()
    with open(DECISIONS_CSV, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["chosen"] == "reocr":
                vid = file_to_vol(r["file"])
                if vid:
                    seen_files.add(vid[0])
    # confirm against the jsonl (a vol is re-rendered only if a row really carries engine=reocr)
    for vol_id in seen_files:
        rows = extract.read_jsonl(vol_id)
        if rows and any(row.get("engine") == "reocr" for row in rows):
            vols.add(vol_id)
    return sorted(vols)


def render_affected():
    manifest = extract.load_manifest()
    vols = affected_vols_from_decisions()
    rendered = []
    for vol_id in vols:
        path, _did = extract.render(vol_id, manifest, force=True)
        rendered.append(vol_id)
        print(f"[render] {vol_id} -> {path}")
    if not vols:
        print("[render] no volumes changed by re-OCR; nothing to re-render")
    return rendered


def summarize(queue_size, capped_remainder, rendered):
    decided = 0
    chosen_counts = {"reocr": 0, "embedded": 0}
    if os.path.exists(DECISIONS_CSV):
        with open(DECISIONS_CSV, newline="") as fh:
            for r in csv.DictReader(fh):
                decided += 1
                chosen_counts[r["chosen"]] = chosen_counts.get(r["chosen"], 0) + 1
    review = 0
    if os.path.exists(HUMAN_REVIEW_CSV):
        with open(HUMAN_REVIEW_CSV, newline="") as fh:
            review = sum(1 for _ in csv.DictReader(fh))
    out = {
        "queue_size": queue_size,
        "pages_processed": decided,
        "reocr_kept": chosen_counts.get("reocr", 0),
        "embedded_kept": chosen_counts.get("embedded", 0),
        "human_review_pages": review,
        "capped_remainder": capped_remainder,
        "rendered_volumes": rendered,
    }
    print("[summary] " + json.dumps(out))
    return out


def main():
    ap = argparse.ArgumentParser(description="Phase 3 selective re-OCR gate (keep-better-of-two)")
    ap.add_argument("--max", type=int, default=80, help="max undecided pages this run (chunk size)")
    ap.add_argument("--validate", action="store_true", help="process ~5 pages, no re-render")
    ap.add_argument("--render", action="store_true", help="re-render affected volumes after this chunk")
    ap.add_argument("--render-only", action="store_true", help="only re-render touched volumes, no OCR")
    ap.add_argument("--stats", action="store_true", help="print counts only, no work")
    a = ap.parse_args()

    if a.stats:
        queue = read_queue()
        cap = max(0, len(queue) - QUEUE_CAP)
        summarize(len(queue), cap, [])
        return
    if a.render_only:
        rendered = render_affected()
        queue = read_queue()
        summarize(len(queue), max(0, len(queue) - QUEUE_CAP), rendered)
        return
    run(max_n=a.max, validate=a.validate, do_render=a.render)


if __name__ == "__main__":
    main()
