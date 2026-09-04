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
CONSTITUTION_SITE = "https://raymond-rishty.github.io/pca-constitution-reader"
BCO_API = f"{SITE}/api/bco/index.json"

# Catalogues compact enough to concatenate into the one-file pack; generated size varies with updates.
PACK = ["INDEX.md", "RPR.md", "CASES.md", "INQUIRIES.md", "CCB-OVERTURE-ADVICE.md"]
# large indexes: linked, fetched on demand
BIG = [("OVERTURES.md", "every overture + outcome (~104k tokens)"),
       ("RPR-BY-PROVISION.md", "RPR exceptions of substance by BCO/RAO/WCF provision (~308k tokens)")]

# The public machine-facing map and pack are intentionally limited to the GA1–GA52 corpus.
# Keep later-Assembly material out even when an index contains a forward-looking catalogue link.
OUT_OF_SCOPE_LINE = re.compile(
    r"\b(?:GA\s*53|53rd\s+General\s+Assembly|2026\s+overtures)\b",
    re.IGNORECASE,
)


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


def keep_corpus_scope(text: str) -> str:
    """Remove whole catalogue lines that refer to material outside the GA1–GA52 pack."""
    lines = [line for line in text.splitlines() if not OUT_OF_SCOPE_LINE.search(line)]
    return "\n".join(lines) + ("\n" if lines else "")


LLMS_TXT = f"""# PCA General Assembly Records and Constitution

> Page-anchored, OCR-derived Markdown of the Presbyterian Church in America (PCA) General Assembly minutes, GA1–GA52 (1973–2025), with structured catalogues of cases, overtures, constitutional inquiries, Review of Presbytery Records exceptions, and study reports. The RPR catalogue covers GA18–GA52.

Use two sources together, but do not collapse their roles:

- The PCA General Assembly corpus is the evidence for what an Assembly, committee, court, or presbytery record did or said, including its procedural status and later action.
- The [PCA Constitution Reader](https://raymond-rishty.github.io/pca-constitution-reader/) is the constitutional-text source for the Westminster Confession, Larger and Shorter Catechisms, and BCO text and cross-references. Its [llms.txt](https://raymond-rishty.github.io/pca-constitution-reader/llms.txt) maps the reader's hash routes and machine-readable assets. Its text or editorial navigation is not itself an Assembly action.
- The [official current PCA Book of Church Order](https://www.pcaac.org/book-of-church-order/) controls questions about present BCO wording. Separate it from historical Minutes evidence.

When a question names a constitutional provision, do not stop at the text. Build a cross-corpus source plan: read the relevant BCO or Westminster text in the Constitution Reader, then search the PCA catalogues for cases, constitutional inquiries, overtures, RPR exceptions, study reports, and Assembly actions that interpret, apply, amend, or later resolve that provision.

Start with the narrowest relevant catalogue, then expand only when another record type, Assembly, historical provision number, or semantic variant could change the conclusion. Treat indexes and llms-full.txt as finding aids, but do not load the full pack unless the question needs broader discovery. For a material historical claim, prefer the underlying extracted record or page-anchored Minutes entry over an index or headnote. Before finalizing each material historical citation, verify the linked page's title or record identifier and disposition, then verify the claim in the cited passage. For a Minutes link, read its PAGE marker and derive the printed citation in the form M<GA>GA p.<page> from printed_page; keep URL fragments and PDF-page numbers as locators only. Use an external PDF only when the corpus record is unavailable or unclear. If any check fails, omit the citation or label the item unverified. Distinguish adopted Assembly actions, SJC/CJB judgments and dispositions, non-binding CCB advice, RPR exceptions and later responses, committee recommendations, minority reports, overtures, proposed amendments, and study-report reception or adoption status.

When a provision has been renumbered, search its current and predecessor numbers and check the BCO renumbering/change data below. For constitutional interpretation, search the relevant BCO and Westminster text in the Constitution Reader alongside the historical record.

For reader-facing links, use the published GitHub Pages `.html` URL. Raw Markdown is for machine retrieval. Derive the printed Minutes citation from the underlying `printed_page` marker; minutes URL fragments and PDF-page numbers are locators, not printed-page citations. Extracted cases, inquiries, overtures, RPR records, and studies often have no page anchor: use their base `.html` URL; use a fragment only when the page supplies it. If no direct record page is available, link the catalogue or Minutes page as a locator.

For a negative or incomplete result, say “Not found in this corpus,” state the relevant catalogues, date scope, and terminology variants searched, and do not infer that the PCA never addressed the subject.

## PCA General Assembly corpus

- [Corpus index]({SITE}/index/INDEX.html) — map of the 52 Minutes volumes, catalogues, and outlines.
- [BCO authority manifests]({BCO_API}) — machine-readable, provision-scoped manifests linking explicit BCO references to cases, constitutional inquiries, CCB advice, overtures, and RPR exceptions. Use a provision manifest to find source records; verify claims in those underlying records.
- [Judicial cases]({SITE}/index/CASES.html) — SJC/CJB cases, parties, cited provisions, and dispositions.
- [Judicial cases by provision]({SITE}/index/CASES-BY-PROVISION.html) — cases grouped by BCO, RAO, and Standards provision.
- [Constitutional inquiries]({SITE}/index/INQUIRIES.html) — CCB advice about constitutional meaning and application.
- [CCB overture advice]({SITE}/index/CCB-OVERTURE-ADVICE.html) — CCB review of proposed overtures and amendments.
- [Review of Presbytery Records]({SITE}/index/RPR.html) — exceptions and later statuses by presbytery.
- [RPR by provision]({SITE}/index/RPR-BY-PROVISION.html) — RPR exceptions grouped by provision.
- [Overtures and outcomes]({SITE}/index/OVERTURES.html) — proposals, Assembly actions, and ratification information.
- [Study reports and position papers]({SITE}/index/STUDIES.html) — reports, declarations, pastoral letters, and recorded reception or adoption status.

## PCA constitutional texts

- [PCA Constitution Reader](https://raymond-rishty.github.io/pca-constitution-reader/) — Westminster Standards and PCA BCO text, with constitutional cross-references; see its [llms.txt](https://raymond-rishty.github.io/pca-constitution-reader/llms.txt) for route syntax and data files.
- [Official current PCA Book of Church Order](https://www.pcaac.org/book-of-church-order/) — current BCO authority for present-law questions.

## Reference data

- [BCO renumberings]({RAW}/index/bco_renumberings.jsonl) — recorded historical-to-current provision mappings.
- [BCO changes]({RAW}/index/bco_changes.jsonl) — structured amendment-history references.

## Optional bulk retrieval

- [llms-full.txt]({SITE}/llms-full.txt) — generated catalogue pack and locator aid; verify material claims against the underlying records because the pack is a finding aid, not a substitute for record pages.
"""

def main():
    open(os.path.join(ROOT, "llms.txt"), "w", encoding="utf-8").write(LLMS_TXT)

    parts = [
        "# PCA GA Minutes — LLM pack (compact catalogues, one file)\n",
        f"Generated index for AI ingestion. The corpus lives at {SITE} (raw markdown at {RAW}).",
        "This file concatenates the SMALL structured catalogues so you can load them in one fetch:",
        "the corpus index, the RPR hub, judicial cases, constitutional inquiries, and CCB advice.",
        f"The provision-scoped BCO authority manifests are available at {BCO_API}; use them for provision-first retrieval.",
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
        source = keep_corpus_scope(open(p, encoding="utf-8").read())
        parts += [f"\n\n{'=' * 78}\n# {f}   (live: {live})\n{'=' * 78}\n",
                  canonicalize_pack_links(source, f"index/{f}")]
    open(os.path.join(ROOT, "llms-full.txt"), "w", encoding="utf-8").write("\n".join(parts))

    sz = os.path.getsize(os.path.join(ROOT, "llms-full.txt"))
    print(f"[{ROOT}] wrote llms.txt and llms-full.txt ({sz // 1024}KB ~{sz // 4000}k tokens); ASK.md unchanged")


if __name__ == "__main__":
    main()
