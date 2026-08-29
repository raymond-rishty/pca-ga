#!/usr/bin/env python3
"""34_llm_pack.py — generate the LLM-facing distribution so a presbyter can point any browsing LLM
(ChatGPT, Claude, Gemini, …) at the corpus and get grounded, cited answers — no install, no backend.

Writes (at <ROOT>/):
  llms.txt        the map for an AI: what's here, how to find it, citation format, URL patterns
  llms-full.txt   compact catalogues concatenated into ONE fetchable/uploadable file (cases, inquiries,
                  CCB advice, RPR hub + corpus index). Large catalogues (OVERTURES, RPR-BY-PROVISION)
                  are linked for fetch-on-demand rather than inlined.

ASK.md is the richer, hand-maintained copy/paste research prompt and is intentionally not generated
here, so running this script cannot replace it with a stale prompt template.

Usage: 34_llm_pack.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import os, posixpath, re, sys
from urllib.parse import urlsplit, urlunsplit

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
SITE = "https://raymond-rishty.github.io/pca-ga"
RAW = "https://raw.githubusercontent.com/raymond-rishty/pca-ga/main"

# catalogues compact enough to concatenate into the one-file pack (≈75k tokens total)
PACK = ["INDEX.md", "RPR.md", "CASES.md", "INQUIRIES.md", "CCB-OVERTURE-ADVICE.md"]
# large indexes: linked, fetched on demand
BIG = [("OVERTURES.md", "every overture + outcome (~104k tokens)"),
       ("RPR-BY-PROVISION.md", "RPR exceptions of substance by BCO/RAO/WCF provision (~308k tokens)")]


def published_url(repo_path: str) -> str:
    """Return the canonical GitHub Pages URL for a repository Markdown path."""
    path = posixpath.normpath(repo_path).lstrip("/")
    if path.endswith(".md"):
        path = path[:-3] + ".html"
    return f"{SITE}/{path}"


def canonicalize_pack_links(text: str, source_path: str) -> str:
    """Make links in llms-full.txt absolute, canonical public Pages URLs.

    Source catalogue Markdown deliberately keeps repository-relative ``.md`` links so Jekyll can
    render it normally. The LLM pack is consumed as raw text, so those links must not be left for a
    model to guess how to publish. Relative repository links are resolved against the source
    catalogue and converted from ``.md`` to their public ``.html`` Pages URL. External URLs
    (including raw.githubusercontent.com) and fragment-only links are left alone.
    """
    source_dir = posixpath.dirname(source_path)

    def canonicalize_target(url: str) -> str:
        if url.startswith("#"):
            return url

        parts = urlsplit(url)
        if parts.scheme:
            # Only canonicalize URLs that already point at this GitHub Pages site.
            if f"{parts.scheme}://{parts.netloc}" != "https://raymond-rishty.github.io":
                return url
            if not parts.path.startswith("/pca-ga/"):
                return url
            path = parts.path
            if path.endswith(".md"):
                path = path[:-3] + ".html"
            return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

        # Root-relative URLs are already site paths; repo-relative URLs need rebasing.
        if parts.path.startswith("/"):
            repo_path = parts.path.lstrip("/")
            if repo_path.startswith("pca-ga/"):
                repo_path = repo_path[len("pca-ga/"):]
        else:
            repo_path = posixpath.normpath(posixpath.join(source_dir, parts.path))

        if parts.path.endswith("/"):
            public = f"{SITE}/{repo_path.rstrip('/')}/"
        else:
            public = published_url(repo_path)
        if parts.query:
            public += "?" + parts.query
        if parts.fragment:
            public += "#" + parts.fragment
        return public

    def repl(m):
        label, url = m.group(1), m.group(2)
        return f"[{label}]({canonicalize_target(url)})"

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", repl, text)


LLMS_TXT = f"""# PCA General Assembly Minutes & Constitutional Catalogues (1973–2025)

> Verbatim, OCR-corrected markdown of all 52 volumes of the Presbyterian Church in America (PCA)
> *Minutes of the General Assembly*, plus structured, cross-referenced catalogues of judicial cases
> (SJC/CJB), overtures, constitutional inquiries (CCB), Review of Presbytery Records (RPR)
> exceptions of substance, and the denomination's position papers / study committee reports. Built for grounded research on the *Book of Church Order* (BCO) and PCA
> history: every catalogue entry deep-links to the verbatim minutes page it summarizes.

## How an AI assistant should use this

To answer a question about the BCO or PCA history, do NOT answer from memory — retrieve and cite:
1. Open the catalogue that matches the question (these are small, structured indexes):
   - Judicial cases (SJC/CJB) → {SITE}/index/CASES.html
   - Judicial cases by constitutional provision → {SITE}/index/CASES-BY-PROVISION.html
   - RPR exceptions of substance, by BCO provision → {SITE}/index/RPR-BY-PROVISION.html
     (or by presbytery → {SITE}/index/RPR.html and the per-presbytery pages it links)
   - Constitutional inquiries answered by the CCB → {SITE}/index/INQUIRIES.html
   - CCB advice on proposed overtures/amendments → {SITE}/index/CCB-OVERTURE-ADVICE.html
   - Overtures (proposals) and BCO amendments → {SITE}/index/OVERTURES.html
   - Position papers / study committee reports (incl. pastoral letters, declarations) → {SITE}/index/STUDIES.html
2. Follow the deep link to the verbatim minutes page and quote the exact text.
3. Cite as `M<GA-ordinal>GA p.<printed page>` (e.g. M50GA p.517) plus the catalogue row.
4. The BCO is renumbered over time — a section cited in an old case may have a different number
   today; flag that rather than assuming the modern numbering.

## URL conventions — important
- For a user-facing link, use the published GitHub Pages URL ending in `.html`, not a repository-source `.md` URL.
- Repository Markdown deliberately uses relative `.md` links because Jekyll translates them during the site build. When reading raw catalogue source, convert a linked repository path such as `cases/ga10_1982__case5.md` to `{SITE}/cases/ga10_1982__case5.html` before presenting it to a user.
- For machine retrieval of source Markdown, use `{RAW}/...` and keep the `.md` suffix.
- Example: public page `{SITE}/cases/ga10_1982__case5.html`; raw source `{RAW}/cases/ga10_1982__case5.md`.

## Catalogues (structured indexes — start here)
- [Corpus index]({SITE}/index/INDEX.html) — the map of all 52 volumes + every catalogue.
- [Judicial cases]({SITE}/index/CASES.html) — SJC/CJB cases: parties, disposition, BCO cited.
- [Judicial cases by constitutional provision]({SITE}/index/CASES-BY-PROVISION.html) — cases grouped under the BCO/WCF/RAO provisions they cite.
- [Constitutional inquiries]({SITE}/index/INQUIRIES.html) — CCB advice on what the Constitution means.
- [CCB advice on overtures/amendments]({SITE}/index/CCB-OVERTURE-ADVICE.html)
- [Review of Presbytery Records — by provision]({SITE}/index/RPR-BY-PROVISION.html) — which
  presbyteries were cited under each provision and whether it was resolved. [Hub]({SITE}/index/RPR.html)
- [Overtures]({SITE}/index/OVERTURES.html) — every overture + final outcome (incl. ratification).
- [Position papers & study committee reports]({SITE}/index/STUDIES.html) — study-committee / ad-interim reports, pastoral letters, declarations, statements, and adopted resolutions, grouped by topic; each links to the full verbatim report in the minutes.

## Verbatim minutes
- Source files: `markdown/ga<NN>_<YYYY>.md`, with deep-link anchors `#ga<ordinal>-p<printed-page>`.
- Published pages use the corresponding `.html` URL, e.g. {SITE}/markdown/ga50_2023.html#ga50-p517.
- Cleanest for machine fetching is the raw markdown, e.g. {RAW}/markdown/ga50_2023.md

## One-file pack
- [llms-full.txt]({SITE}/llms-full.txt) — the corpus index + the compact catalogues (cases, inquiries,
  CCB advice, RPR hub) concatenated into ONE file you can fetch or upload in a single step. Links in
  this pack are canonical absolute public `.html` URLs. The two large indexes — OVERTURES and
  RPR-BY-PROVISION — are linked above; fetch them when needed.
"""


def main():
    open(os.path.join(ROOT, "llms.txt"), "w", encoding="utf-8").write(LLMS_TXT)

    parts = [
        "# PCA GA Minutes — LLM pack (compact catalogues, one file)\n",
        f"Generated index for AI ingestion. The corpus lives at {SITE} (raw markdown at {RAW}).",
        "This file concatenates the SMALL structured catalogues so you can load them in one fetch:",
        "the corpus index, the RPR hub, judicial cases, constitutional inquiries, and CCB advice.",
        "Each catalogue row deep-links to the verbatim minutes page; cite as `M<GA>GA p.<page>`.",
        "User-facing links in this pack are canonical GitHub Pages URLs ending in `.html`; source `.md` paths are for raw/repository retrieval only.",
        "",
        "Two catalogues are too large to inline here — fetch them directly when a question needs them:",
    ] + [f"- {published_url('index/' + f)} — {desc}" for f, desc in BIG] + [""]
    for f in PACK:
        p = os.path.join(IDX, f)
        if not os.path.exists(p):
            continue
        live = published_url("index/" + f)
        parts += [f"\n\n{'=' * 78}\n# {f}   (live: {live})\n{'=' * 78}\n",
                  canonicalize_pack_links(open(p, encoding="utf-8").read(), f"index/{f}")]
    open(os.path.join(ROOT, "llms-full.txt"), "w", encoding="utf-8").write("\n".join(parts))

    sz = os.path.getsize(os.path.join(ROOT, "llms-full.txt"))
    print(f"[{ROOT}] wrote llms.txt and llms-full.txt ({sz // 1024}KB ~{sz // 4000}k tokens); ASK.md unchanged")


if __name__ == "__main__":
    main()
