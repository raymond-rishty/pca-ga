#!/usr/bin/env python3
"""
06_review_kit.py — human-in-the-loop kit for the re-OCR / human-review floor.

The pages that automated OCR could not clean live in build/reocr/human_review.csv.
Each one needs EITHER cloud OCR or a human. This kit lets you do both:

  export   -> review/manifest.csv      (machine list: id,file,pdf_page,reason,... — feed to cloud OCR)
              review/worksheet.md       (human-fillable: one section per page, scan image + current text
                                         + a `corrected` block to type into)
              review/images/<id>.png    (the rendered scan of each page, for transcription)
  ingest   -> read the filled worksheet; for every page with corrected text, write it back into the
              page_jsonl source of truth (engine="human"), re-score it, re-render the affected
              markdown volumes, and rebuild the search index. (--dry-run to preview.)
  status   -> how many reviewed vs. remaining.

Usage:
  06_review_kit.py export [--no-images] [--dpi 200]
  06_review_kit.py ingest [--dry-run]
  06_review_kit.py status
"""
from __future__ import annotations
import argparse, base64, csv, glob, importlib, json, os, re, shutil, subprocess, sys, tempfile, time

ROOT = "/workspace"
PY = os.path.join(ROOT, ".venv/bin/python")
REVIEW = os.path.join(ROOT, "review")
IMAGES = os.path.join(REVIEW, "images")
HR_CSV = os.path.join(ROOT, "build/reocr/human_review.csv")
PAGE_JSONL = os.path.join(ROOT, "build/page_jsonl")
MINUTES = os.path.join(ROOT, "minutes")
WORKSHEET = os.path.join(REVIEW, "worksheet.md")
MANIFEST = os.path.join(REVIEW, "manifest.csv")
INGEST_LOG = os.path.join(REVIEW, "ingest_log.csv")
EMPTY = "<<EMPTY — type the corrected page text here, then run: 06_review_kit.py ingest>>"
CLOUD_LOG = os.path.join(REVIEW, "cloud_log.csv")
ACCEPTED = os.path.join(REVIEW, "accepted_as_is.csv")
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/ocr"
MISTRAL_MODEL = "mistral-ocr-latest"  # Mistral OCR 3 (latest production OCR model)
# The API call is made via curl (see mistral_ocr_image): in this Zscaler-intercepted
# sandbox curl completes standard, full TLS verification against the system CA bundle
# (verified working), so no Python ssl-strictness changes are needed.

KEY_FILE = os.path.join(REVIEW, ".mistral_key")  # persisted Mistral key (mode 600)


def _key_from_file():
    """Fallback key source so cloud OCR works without re-exporting the env var each session."""
    try:
        if os.path.exists(KEY_FILE):
            return open(KEY_FILE).read().strip() or None
    except OSError:
        return None
    return None


sys.path.insert(0, os.path.join(ROOT, "scripts"))
import normalize  # noqa
qc = importlib.import_module("02_qc_score")


def load_rows():
    with open(HR_CSV, newline="") as fh:
        return list(csv.DictReader(fh))


def _page_jsonl_path(vol):
    return os.path.join(PAGE_JSONL, f"{vol}.pages.jsonl")


def load_pages(vol):
    rows = {}
    with open(_page_jsonl_path(vol)) as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[int(r["pdf_page"])] = r
    return rows


def item_id(r):
    return f"{r['vol']}-p{r['pdf_page']}"


# ----------------------------------------------------------------- export
def render_image(src_pdf, page, out_png, dpi):
    with tempfile.TemporaryDirectory() as td:
        pre = os.path.join(td, "p")
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi),
                        "-png", src_pdf, pre], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pngs = glob.glob(pre + "*.png")
        if pngs:
            shutil.move(pngs[0], out_png)
            return True
    return False


def export(images=True, dpi=200, prefill=False):
    os.makedirs(IMAGES, exist_ok=True)
    rows = load_rows()
    page_cache = {}
    man = []
    sections = []
    by_reason = {}
    for r in rows:
        vol, pg = r["vol"], int(r["pdf_page"])
        by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1
        if vol not in page_cache:
            page_cache[vol] = load_pages(vol)
        cur = (page_cache[vol].get(pg) or {}).get("text", "") or ""
        iid = item_id(r)
        img_rel = f"review/images/{iid}.png"
        if images:
            ok = render_image(os.path.join(MINUTES, r["file"]), pg,
                              os.path.join(IMAGES, f"{iid}.png"), dpi)
            if not ok:
                img_rel = "(image render failed)"
        man.append({"id": iid, "file": r["file"], "pdf_page": pg, "vol": vol,
                    "reason": r["reason"], "digit_flag": r.get("digit_flag", ""),
                    "p5_conf": r.get("p5_conf", ""), "hitrate": r.get("chosen_hitrate", ""),
                    "image": img_rel})
        cur_safe = cur.replace("~~~", "~ ~ ~")
        corrected_init = cur_safe if prefill else EMPTY
        instr = ("edit in place — pre-filled with the current text; fix the wrong characters "
                 "(use accept for pages that are already correct)") if prefill else \
                ("replace the placeholder, or leave it to skip this page")
        sections.append(
            f"<!-- ITEM id={iid} vol={vol} pdf_page={pg} reason={r['reason']} "
            f"digit_flag={r.get('digit_flag','')} -->\n"
            f"## {iid}  ·  reason: {r['reason']}  ·  digit_flag: {r.get('digit_flag','')}  "
            f"·  OCR hitrate: {r.get('chosen_hitrate','?')}\n"
            f"**Source:** `{r['file']}` page {pg}  ·  **Scan:** `{img_rel}`\n\n"
            f"**Current best OCR text:**\n~~~text\n{cur_safe}\n~~~\n\n"
            f"**Corrected text** — {instr}:\n"
            f"~~~corrected\n{corrected_init}\n~~~\n"
            f"<!-- END id={iid} -->\n")

    os.makedirs(REVIEW, exist_ok=True)
    with open(MANIFEST, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(man[0].keys()))
        w.writeheader(); w.writerows(man)
    digit = sum(1 for r in rows if str(r.get("digit_flag", "")).lower() == "true")
    header = (
        "# PCA minutes — human review worksheet\n\n"
        f"{len(rows)} pages where automated OCR is exhausted (the genuine floor). "
        f"{digit} are `digit_flag` (vote tallies / case numbers — verify these even if they look OK).\n\n"
        "**How to use:** for each page below, open the linked scan image, and type the correct page "
        "text into the `~~~corrected` block (replacing the placeholder). Save, then run "
        "`./.venv/bin/python scripts/06_review_kit.py ingest` to fold your corrections into the corpus "
        "and rebuild the index. You can do a few at a time — ingest is incremental.\n\n"
        "Reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(by_reason.items())) + "\n\n---\n\n")
    with open(WORKSHEET, "w") as fh:
        fh.write(header + "\n".join(sections))
    print(f"[export] {len(rows)} pages -> {MANIFEST}, {WORKSHEET}"
          + (f", {len(man)} images in {IMAGES}/" if images else " (no images)"))
    print("  reasons:", by_reason)
    print(f"  digit_flag (citation-integrity, verify regardless): {digit}")


# ----------------------------------------------------------------- ingest
ITEM_RE = re.compile(
    r"<!-- ITEM id=(?P<id>\S+) vol=(?P<vol>\S+) pdf_page=(?P<pg>\d+).*?-->.*?"
    r"~~~corrected\n(?P<corr>.*?)\n~~~", re.S)


def ingest(dry_run=False):
    if not os.path.exists(WORKSHEET):
        sys.exit("no worksheet — run `export` first")
    text = open(WORKSHEET).read()
    filled = []
    _pc = {}
    for m in ITEM_RE.finditer(text):
        corr = m.group("corr").strip()
        if not corr or corr.startswith("<<EMPTY"):
            continue
        vol, pg = m.group("vol"), int(m.group("pg"))
        if vol not in _pc:
            _pc[vol] = load_pages(vol)
        cur = ((_pc[vol].get(pg) or {}).get("text", "") or "").strip()
        if corr == cur:
            continue  # block left unchanged (e.g. --prefill, not edited) — not a correction
        filled.append((m.group("id"), vol, pg, corr))
    if not filled:
        print("[ingest] no corrected pages found (every `corrected` block is still the placeholder).")
        return
    print(f"[ingest] {len(filled)} corrected page(s) found"
          + (" — DRY RUN, no writes" if dry_run else ""))
    touched_vols = set()
    log = []
    words = normalize.load_dict()
    for iid, vol, pg, corr in filled:
        clean = normalize.normalize_text(corr, words)
        score = qc.classify(clean, words)
        log.append({"id": iid, "vol": vol, "pdf_page": pg, "new_chars": len(clean),
                    "new_verdict": score["verdict"], "new_hitrate": score["dict_hitrate"],
                    "digit_flag": score["digit_flag"]})
        print(f"  {iid}: {len(clean)} chars, verdict={score['verdict']}, "
              f"hitrate={score['dict_hitrate']}, digit_flag={score['digit_flag']}")
        if dry_run:
            continue
        path = _page_jsonl_path(vol)
        rows = [json.loads(l) for l in open(path) if l.strip()]
        for r in rows:
            if int(r["pdf_page"]) == pg:
                r["text"] = clean
                r["char_count"] = len(clean)
                r["engine"] = "human"
                r["qc"] = {k: score[k] for k in ("verdict", "dict_hitrate",
                           "whitespace_frag", "digit_flag", "digit_present")}
                r["ga_item_tokens"] = re.findall(r"\b\d{1,2}-\d{1,3}\b", clean)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        touched_vols.add(vol)
    if dry_run:
        print("[ingest] dry run complete — re-run without --dry-run to apply.")
        return
    # log
    new = not os.path.exists(INGEST_LOG)
    with open(INGEST_LOG, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(log[0].keys()))
        if new:
            w.writeheader()
        w.writerows(log)
    # re-render affected volumes + reindex
    for vol in sorted(touched_vols):
        print(f"[ingest] re-rendering {vol} ...")
        subprocess.run([PY, "scripts/01_extract.py", "render", vol], cwd=ROOT, check=False)
    print("[ingest] rebuilding index ...")
    subprocess.run([PY, "scripts/05_index.py", "build", "--force"], cwd=ROOT, check=False)
    # drop ingested rows from human_review.csv -> completed.csv
    rows = load_rows()
    done_ids = {iid for iid, *_ in filled}
    keep = [r for r in rows if item_id(r) not in done_ids]
    done = [r for r in rows if item_id(r) in done_ids]
    _rewrite_csv(HR_CSV, rows, keep)
    _rewrite_csv(os.path.join(REVIEW, "completed.csv"), rows, done, append=True)
    print(f"[ingest] done. {len(done)} page(s) moved to review/completed.csv; "
          f"{len(keep)} remain in human_review.csv.")


def _rewrite_csv(path, all_rows, subset, append=False):
    if not subset and not append:
        return
    fields = list(all_rows[0].keys())
    mode = "a" if append and os.path.exists(path) else "w"
    with open(path, mode, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if mode == "w":
            w.writeheader()
        w.writerows(subset)


def _update_page(vol, pdf_page, text, engine, score):
    """Write new text for one page into the page_jsonl source of truth."""
    path = _page_jsonl_path(vol)
    rows = [json.loads(l) for l in open(path) if l.strip()]
    for r in rows:
        if int(r["pdf_page"]) == pdf_page:
            r["text"] = text
            r["char_count"] = len(text)
            r["engine"] = engine
            r["qc"] = {k: score[k] for k in ("verdict", "dict_hitrate",
                       "whitespace_frag", "digit_flag", "digit_present")}
            r["ga_item_tokens"] = re.findall(r"\b\d{1,2}-\d{1,3}\b", text)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def mistral_ocr_image(png_path, api_key, model=MISTRAL_MODEL, timeout=120, retries=4):
    """Transcribe one page image via the Mistral OCR API -> markdown string.
    Uses curl (full standard TLS verification in this environment). The API key is
    passed via a mode-600 temp curl config file, never on the argv/process list."""
    data = base64.b64encode(open(png_path, "rb").read()).decode()
    body = json.dumps({
        "model": model,
        "document": {"type": "image_url", "image_url": f"data:image/png;base64,{data}"},
    })
    last = None
    for attempt in range(retries):
        bf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        bf.write(body); bf.close()
        cf = tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False)
        os.chmod(cf.name, 0o600)
        cf.write(f'url = "{MISTRAL_ENDPOINT}"\nrequest = "POST"\n')
        cf.write(f'header = "Authorization: Bearer {api_key}"\n')
        cf.write('header = "Content-Type: application/json"\n')
        cf.write(f'data = "@{bf.name}"\n')
        cf.close()
        try:
            p = subprocess.run(
                ["curl", "-sS", "--config", cf.name, "-w", "\n%{http_code}", "--max-time", str(timeout)],
                capture_output=True, text=True)
        finally:
            os.unlink(bf.name); os.unlink(cf.name)
        if p.returncode != 0:
            last = f"curl rc={p.returncode}: {p.stderr.strip()[:200]}"; time.sleep(2 * (attempt + 1)); continue
        out = p.stdout
        nl = out.rfind("\n")
        http, payload = out[nl + 1:].strip(), out[:nl]
        if http in ("429", "500", "502", "503", "529"):
            last = f"HTTP {http}: {payload[:160]}"; time.sleep(2 * (attempt + 1)); continue
        if http != "200":
            raise RuntimeError(f"Mistral OCR HTTP {http}: {payload[:200]}")  # 401/400 fatal
        obj = json.loads(payload)
        pages = obj.get("pages") or []
        return "\n\n".join(pg.get("markdown", "") for pg in pages).strip()
    raise RuntimeError(f"Mistral OCR failed after {retries} attempts: {last}")


def cloud(limit=None, only=None, include_digit_flag=False, dpi=200, dry_run=False):
    """Re-OCR the review floor via Mistral OCR 3; keep-better-of-two, never regress.
    Reads MISTRAL_API_KEY from the environment. digit_flag pages are skipped by
    default (route them to human review unless --include-digit-flag)."""
    key = os.environ.get("MISTRAL_API_KEY") or _key_from_file()
    if not key:
        sys.exit("MISTRAL_API_KEY not set (env) and review/.mistral_key missing — set one and retry.")
    words = normalize.load_dict()
    rows = load_rows()
    only = set(only) if only else None
    targets = []
    for r in rows:
        iid = item_id(r)
        if only and iid not in only:
            continue
        if not include_digit_flag and str(r.get("digit_flag", "")).lower() == "true":
            continue
        targets.append(r)
    if limit:
        targets = targets[:limit]
    print(f"[cloud] {len(targets)} target page(s) via {MISTRAL_MODEL} "
          f"(digit_flag {'INCLUDED' if include_digit_flag else 'excluded'})"
          + (" — DRY RUN (calls API, no writes)" if dry_run else ""))
    os.makedirs(IMAGES, exist_ok=True)
    page_cache, touched, done_ids, log = {}, set(), set(), []
    for r in targets:
        vol, pg, iid = r["vol"], int(r["pdf_page"]), item_id(r)
        if vol not in page_cache:
            page_cache[vol] = load_pages(vol)
        cur = (page_cache[vol].get(pg) or {}).get("text", "") or ""
        cur_s = qc.classify(cur, words)
        cur_eff = max(cur_s["dict_hitrate"], cur_s["despaced_hitrate"]); cur_n = cur_s["n_tokens"]
        img = os.path.join(IMAGES, f"{iid}.png")
        if not os.path.exists(img):
            render_image(os.path.join(MINUTES, r["file"]), pg, img, dpi)
        try:
            raw = mistral_ocr_image(img, key)
        except Exception as e:
            print(f"  {iid}: API ERROR — {e}")
            log.append({"id": iid, "vol": vol, "pdf_page": pg, "status": "api_error",
                        "cur_eff": round(cur_eff, 3), "new_eff": "", "chosen": "current"})
            continue
        new = normalize.normalize_text(raw, words)
        s = qc.classify(new, words)
        new_eff = max(s["dict_hitrate"], s["despaced_hitrate"])
        # keep-better-of-two + content-preservation + never introduce a new digit_flag
        improved = (new_eff >= cur_eff + 0.02
                    and s["n_tokens"] >= 0.6 * max(1, cur_n)
                    and not (s["digit_flag"] and not cur_s["digit_flag"]))
        print(f"  {iid}: cur_eff={cur_eff:.2f} -> new_eff={new_eff:.2f}  "
              f"{'KEEP-CLOUD' if improved else 'keep-current'}")
        log.append({"id": iid, "vol": vol, "pdf_page": pg, "status": "ok",
                    "cur_eff": round(cur_eff, 3), "new_eff": round(new_eff, 3),
                    "chosen": "cloud" if improved else "current"})
        if dry_run or not improved:
            continue
        _update_page(vol, pg, new, "cloud:mistral-ocr", s)
        touched.add(vol); done_ids.add(iid)
    # append cloud log
    if log:
        new_file = not os.path.exists(CLOUD_LOG)
        with open(CLOUD_LOG, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(log[0].keys()))
            if new_file:
                w.writeheader()
            w.writerows(log)
    if dry_run:
        print("[cloud] dry run complete — no writes."); return
    for vol in sorted(touched):
        print(f"[cloud] re-rendering {vol} ...")
        subprocess.run([PY, "scripts/01_extract.py", "render", vol], cwd=ROOT, check=False)
    if touched:
        print("[cloud] rebuilding index ...")
        subprocess.run([PY, "scripts/05_index.py", "build", "--force"], cwd=ROOT, check=False)
    keep = [r for r in rows if item_id(r) not in done_ids]
    done = [r for r in rows if item_id(r) in done_ids]
    _rewrite_csv(HR_CSV, rows, keep)
    if done:
        _rewrite_csv(os.path.join(REVIEW, "completed.csv"), rows, done, append=True)
    print(f"[cloud] improved {len(done_ids)} page(s); {len(keep)} remain in human_review.csv "
          f"(audit: {CLOUD_LOG})")


def accept(only=None, vol=None, pages=None, note=""):
    """Mark pages as reviewed-and-left-as-is: move them out of the pending
    human_review floor into review/accepted_as_is.csv (an explicit won't-fix
    ledger), so they stop showing as pending without being claimed as fixed."""
    rows = load_rows()
    sel = set(only or [])
    if vol and pages:
        sel |= {f"{vol}-p{int(p)}" for p in pages}
    if not sel:
        sys.exit("specify --only <ids> or --vol <vol> --pages 1,2,3")
    keep = [r for r in rows if item_id(r) not in sel]
    moved = [{**r, "accepted_note": note} for r in rows if item_id(r) in sel]
    missing = sel - {item_id(r) for r in rows}
    _rewrite_csv(HR_CSV, rows, keep)
    if moved:
        new_file = not os.path.exists(ACCEPTED)
        with open(ACCEPTED, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) + ["accepted_note"])
            if new_file:
                w.writeheader()
            w.writerows(moved)
    print(f"[accept] {len(moved)} page(s) -> {ACCEPTED} (note: {note!r}); "
          f"{len(keep)} remain in human_review.csv")
    if missing:
        print("  not found (already resolved/accepted?):", sorted(missing))


def status():
    n = len(load_rows())
    done = 0
    cpath = os.path.join(REVIEW, "completed.csv")
    if os.path.exists(cpath):
        done = sum(1 for _ in open(cpath)) - 1
    print(f"[status] remaining in human_review.csv: {n}; completed (ingested): {done}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("--no-images", action="store_true"); e.add_argument("--dpi", type=int, default=200)
    e.add_argument("--prefill", action="store_true", help="pre-fill corrected blocks with current text (edit in place)")
    g = sub.add_parser("ingest"); g.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("cloud")
    c.add_argument("--limit", type=int)
    c.add_argument("--only", nargs="*")
    c.add_argument("--include-digit-flag", action="store_true",
                   help="also re-OCR citation-integrity pages (default: skip them for human review)")
    c.add_argument("--dpi", type=int, default=200)
    c.add_argument("--dry-run", action="store_true", help="call the API + score, but write nothing")
    ac = sub.add_parser("accept", help="mark pages reviewed-and-left-as-is (won't-fix ledger)")
    ac.add_argument("--only", nargs="*"); ac.add_argument("--vol"); ac.add_argument("--pages")
    ac.add_argument("--note", default="")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "export":
        export(images=not a.no_images, dpi=a.dpi, prefill=a.prefill)
    elif a.cmd == "ingest":
        ingest(dry_run=a.dry_run)
    elif a.cmd == "cloud":
        cloud(limit=a.limit, only=a.only, include_digit_flag=a.include_digit_flag,
              dpi=a.dpi, dry_run=a.dry_run)
    elif a.cmd == "accept":
        pages = [p for p in re.split(r"[,\s]+", a.pages) if p] if a.pages else None
        accept(only=a.only, vol=a.vol, pages=pages, note=a.note)
    elif a.cmd == "status":
        status()


if __name__ == "__main__":
    main()
