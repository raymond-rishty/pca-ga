#!/usr/bin/env python3
"""34_llm_pack.py — generate the LLM-facing distribution so a presbyter can point any browsing LLM
(ChatGPT, Claude, Gemini, …) at the corpus and get grounded, cited answers — no install, no backend.

Writes (at <ROOT>/):
  llms.txt        the map for an AI: what's here, how to find it, citation format, URL patterns
  llms-full.txt   compact catalogues concatenated into ONE fetchable/uploadable file (cases, inquiries,
                  CCB advice, RPR hub + corpus index). Large catalogues (OVERTURES, RPR-BY-PROVISION)
                  are linked for fetch-on-demand rather than inlined.
  ASK.md          copy-paste prompt templates for non-technical users

Usage: 34_llm_pack.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
SITE = "https://raymond-rishty.github.io/pca-ga"
RAW = "https://raw.githubusercontent.com/raymond-rishty/pca-ga/main"

# catalogues compact enough to concatenate into the one-file pack (≈75k tokens total)
PACK = ["INDEX.md", "RPR.md", "CASES.md", "INQUIRIES.md", "CCB-OVERTURE-ADVICE.md", "GA53-OVERTURES.md"]
# large indexes: linked, fetched on demand
BIG = [("OVERTURES.md", "every overture + outcome (~104k tokens)"),
       ("RPR-BY-PROVISION.md", "RPR exceptions of substance by BCO/RAO/WCF provision (~308k tokens)")]

LLMS_TXT = f"""# PCA General Assembly Minutes & Constitutional Catalogues (1973–2025)

> Verbatim, OCR-corrected markdown of all 52 volumes of the Presbyterian Church in America (PCA)
> *Minutes of the General Assembly*, plus structured, cross-referenced catalogues of judicial cases
> (SJC/CJB), overtures, constitutional inquiries (CCB), and Review of Presbytery Records (RPR)
> exceptions of substance. Built for grounded research on the *Book of Church Order* (BCO) and PCA
> history: every catalogue entry deep-links to the verbatim minutes page it summarizes.

## How an AI assistant should use this

To answer a question about the BCO or PCA history, do NOT answer from memory — retrieve and cite:
1. Open the catalogue that matches the question (these are small, structured indexes):
   - Judicial cases (SJC/CJB) → {SITE}/index/CASES.md
   - RPR exceptions of substance, by BCO provision → {SITE}/index/RPR-BY-PROVISION.md
     (or by presbytery → {SITE}/index/RPR.md and the per-presbytery pages it links)
   - Constitutional inquiries answered by the CCB → {SITE}/index/INQUIRIES.md
   - CCB advice on proposed overtures/amendments → {SITE}/index/CCB-OVERTURE-ADVICE.md
   - Overtures (proposals) and BCO amendments → {SITE}/index/OVERTURES.md
2. Follow the deep link to the verbatim minutes page and quote the exact text.
3. Cite as `M<GA-ordinal>GA p.<printed page>` (e.g. M50GA p.517) plus the catalogue row.
4. The BCO is renumbered over time — a section cited in an old case may have a different number
   today; flag that rather than assuming the modern numbering.

## Catalogues (structured indexes — start here)
- [Corpus index]({SITE}/index/INDEX.md) — the map of all 52 volumes + every catalogue.
- [Judicial cases]({SITE}/index/CASES.md) — SJC/CJB cases: parties, disposition, BCO cited.
- [Constitutional inquiries]({SITE}/index/INQUIRIES.md) — CCB advice on what the Constitution means.
- [CCB advice on overtures/amendments]({SITE}/index/CCB-OVERTURE-ADVICE.md)
- [Review of Presbytery Records — by provision]({SITE}/index/RPR-BY-PROVISION.md) — which
  presbyteries were cited under each provision and whether it was resolved. [Hub]({SITE}/index/RPR.md)
- [Overtures]({SITE}/index/OVERTURES.md) — every overture + final outcome (incl. ratification).

## Verbatim minutes
- Pages: `markdown/ga<NN>_<YYYY>.md`, with deep-link anchors `#ga<ordinal>-p<printed-page>`.
- Cleanest for fetching is the raw markdown, e.g. {RAW}/markdown/ga50_2023.md

## One-file pack
- [llms-full.txt]({SITE}/llms-full.txt) — the corpus index + the compact catalogues (cases, inquiries,
  CCB advice, RPR hub) concatenated into ONE file you can fetch or upload in a single step. The two
  large indexes — OVERTURES.md and RPR-BY-PROVISION.md — are linked above; fetch them when needed.
"""

ASK_MD = f"""# Ask your AI about the PCA Constitution & history

You can use **any AI chat assistant that can browse the web** — ChatGPT, Claude, Gemini, Perplexity —
to search this corpus and get answers grounded in the actual *Minutes of the General Assembly*, with
citations. Nothing to install.

## Copy–paste this into your AI, then add your question

> Use the PCA General Assembly minutes corpus at {SITE} and its indexes — CASES.md (judicial cases),
> RPR-BY-PROVISION.md (Review of Presbytery Records exceptions by BCO provision), INQUIRIES.md
> (CCB constitutional inquiries), CCB-OVERTURE-ADVICE.md, and OVERTURES.md — to answer my question.
> Find the relevant entry, open the verbatim minutes page it links to, quote the text, and cite the
> volume and page (e.g. "M50GA p.517"). If the answer isn't in the corpus, say so. My question:
>
> **«your question here»**

## Tips
- **Specific beats broad.** "What did the SJC decide in case 2012-10?" or "RPR exceptions under BCO
  21-4" work better than "tell me about church discipline."
- **For the whole index in one shot,** point your AI at {SITE}/llms-full.txt (cases, inquiries, CCB
  advice, and the RPR hub in a single file) and ask your question.
- **Always ask for citations** so you can verify against the verbatim minutes.
- This corpus is the *record of what the General Assembly did* (cases, overtures, inquiries, records
  review) — for the current *Book of Church Order* text itself, see pcahistory.org.
"""


def main():
    open(os.path.join(ROOT, "llms.txt"), "w", encoding="utf-8").write(LLMS_TXT)
    open(os.path.join(ROOT, "ASK.md"), "w", encoding="utf-8").write(ASK_MD)

    parts = [
        "# PCA GA Minutes — LLM pack (compact catalogues, one file)\n",
        f"Generated index for AI ingestion. The corpus lives at {SITE} (raw markdown at {RAW}).",
        "This file concatenates the SMALL structured catalogues so you can load them in one fetch:",
        "the corpus index, the RPR hub, judicial cases, constitutional inquiries, and CCB advice.",
        "Each catalogue row deep-links to the verbatim minutes page; cite as `M<GA>GA p.<page>`.",
        "",
        "Two catalogues are too large to inline here — fetch them directly when a question needs them:",
    ] + [f"- {SITE}/index/{f} — {desc}" for f, desc in BIG] + [""]
    for f in PACK:
        p = os.path.join(IDX, f)
        if not os.path.exists(p):
            continue
        parts += [f"\n\n{'=' * 78}\n# {f}   (live: {SITE}/index/{f})\n{'=' * 78}\n",
                  open(p, encoding="utf-8").read()]
    open(os.path.join(ROOT, "llms-full.txt"), "w", encoding="utf-8").write("\n".join(parts))

    sz = os.path.getsize(os.path.join(ROOT, "llms-full.txt"))
    print(f"[{ROOT}] wrote llms.txt, ASK.md, llms-full.txt ({sz // 1024}KB ~{sz // 4000}k tokens)")


if __name__ == "__main__":
    main()
