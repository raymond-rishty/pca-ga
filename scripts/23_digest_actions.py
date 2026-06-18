#!/usr/bin/env python3
"""
23_digest_actions.py — PREP step for the PCA "Digest of Assembly Actions" (a curated, authoritative
topical record of GA actions). Downloads the three text-layer "Assembly Actions" PDFs and extracts
their text to index/digest/aa_v{1,3,4}.txt.

  v1 1973-1993  https://www.pcahistory.org/pca/digest/v1/assembly_actions.pdf
  v3 1994-1998  https://www.pcahistory.org/pca/digest/v3/Assembly%20Actions.pdf
  v4 1999-2018  https://www.pcahistory.org/pca/digest/v4/part01-actions.pdf

The STRUCTURED extraction (overture dispositions + BCO adoptions) is done by an LLM — the
`digest-mine` workflow — because the digest is verbose topical prose that regex parses unreliably.
Its outputs are index/digest_dispositions.jsonl and index/digest_adoptions.jsonl. Of those:
  - dispositions FILL gaps in the per-overture disposition layer (22_dispositions link).
  - adoptions are NOT used as a ratification source: they are LLM-extracted and proved unreliable
    (e.g. BCO 12-5 was labeled "adopted 2002" but is absent from the authoritative changes-list).
    Ratification rests solely on index/bco_changes.jsonl. The adoptions file is kept for reference.

CLI:  23_digest_actions.py prep      (download + pdftotext; needs network + pdftotext)
"""
from __future__ import annotations
import os, subprocess, sys, urllib.request

ROOT = "/workspace"
DIG = os.path.join(ROOT, "index", "digest")
SOURCES = {
    "aa_v1": "https://www.pcahistory.org/pca/digest/v1/assembly_actions.pdf",
    "aa_v3": "https://www.pcahistory.org/pca/digest/v3/Assembly%20Actions.pdf",
    "aa_v4": "https://www.pcahistory.org/pca/digest/v4/part01-actions.pdf",
}


def prep():
    os.makedirs(DIG, exist_ok=True)
    for stem, url in SOURCES.items():
        pdf = os.path.join(DIG, stem + ".pdf")
        txt = os.path.join(DIG, stem + ".txt")
        urllib.request.urlretrieve(url, pdf)
        subprocess.run(["pdftotext", pdf, txt], check=True)
        os.remove(pdf)
        print(f"{stem}: {sum(1 for _ in open(txt))} lines")
    print("\nNow run the `digest-mine` workflow to extract dispositions + adoptions.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "prep":
        prep()
    else:
        print(__doc__)
