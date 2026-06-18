#!/usr/bin/env python3
"""
15_strip_headers.py — remove running headers/footers that survived (section headers like
"APPENDICES 215" / "JOURNAL 37" never cleared because they're below a volume-wide
clustering threshold) or were REINTRODUCED by the Mistral re-OCR (which transcribes the
whole page image, header included, e.g. "54\nMINUTES OF THE GENERAL ASSEMBLY").

Precise by design (frequency-based clustering wrongly flags content like "adopted" /
"respectfully submitted,"). We strip ONLY:
  (1) a standalone line that is a curated running-header keyword, optionally wrapped by a
      page number and/or leading markdown '#', ANYWHERE on the page (handles page-break
      splices that land mid-text, e.g. "148 MINUTES OF THE GENERAL ASSEMBLY");
  (2) a bare page-number line, but only in the top/bottom edge zone.

A real sentence containing the phrase ("the Minutes of the General Assembly were approved")
is never a whole-line match, so it is untouched.

CLI:  15_strip_headers.py --dry-run [vol...]
      15_strip_headers.py --apply  [vol...]   (backs up page_jsonl once to *_pre_hdrstrip)
"""
from __future__ import annotations
import glob, json, os, re, sys, shutil

ROOT = "/workspace"
PJ = os.path.join(ROOT, "build", "page_jsonl")
BACKUP = os.path.join(ROOT, "build", "page_jsonl_pre_hdrstrip")

HDR_KW = r"MINUTES OF THE GENERAL ASSEMBLY|APPENDICES|APPENDIX|JOURNAL|INDEX"
HDR_LINE = re.compile(r"^\s*#*\s*\d{0,4}\s*(?:%s)\s*\d{0,4}\s*$" % HDR_KW, re.I)
# all-caps "APPENDIX Q" running header (appendix letter). Case-SENSITIVE so the title-case
# markdown heading "# Appendix A" (the real appendix title) is preserved.
APPX_LETTER = re.compile(r"^\s*#*\s*(?:APPENDIX|APPENDICES)\s+[A-Z]\s*$")
BARE_NUM = re.compile(r"^\s*#*\s*\d{1,4}\s*$")


def strip_page(text):
    lines = text.split("\n")
    nb = [i for i, l in enumerate(lines) if l.strip()]
    edge = set(nb[:3] + nb[-3:])
    out, removed = [], []
    for i, l in enumerate(lines):
        s = l.strip()
        if HDR_LINE.match(s) or APPX_LETTER.match(s):
            removed.append(s); continue
        if i in edge and BARE_NUM.match(s):
            removed.append(s); continue
        out.append(l)
    txt = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")
    return txt, removed


def main():
    apply = "--apply" in sys.argv
    vols = [a for a in sys.argv[1:] if not a.startswith("--")]
    paths = ([os.path.join(PJ, v + ".pages.jsonl") for v in vols] if vols
             else sorted(glob.glob(PJ + "/*.pages.jsonl")))
    if apply and not os.path.exists(BACKUP):
        shutil.copytree(PJ, BACKUP); print(f"[backup] page_jsonl -> {BACKUP}")
    grand, sample = 0, []
    for p in paths:
        vol = os.path.basename(p).split(".")[0]
        recs = [json.loads(l) for l in open(p)]
        vremoved = 0
        for r in recs:
            t, removed = strip_page(r.get("text", ""))
            if removed:
                vremoved += len(removed)
                if len(sample) < 12:
                    sample.append((vol, r["pdf_page"], removed[0]))
                r["text"] = t; r["char_count"] = len(t)
        grand += vremoved
        if apply and vremoved:
            with open(p, "w") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if vremoved and (vols or vremoved > 100):
            print(f"  {vol}: removed {vremoved} header/number lines")
    print(f"\nTOTAL removed: {grand}  ({'APPLIED' if apply else 'DRY-RUN'})")
    if sample:
        print("samples:", [f"{v} p{pg}: {ln!r}" for v, pg, ln in sample[:8]])


if __name__ == "__main__":
    main()
