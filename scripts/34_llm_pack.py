#!/usr/bin/env python3
"""34_llm_pack.py — generate the LLM-facing distribution so a presbyter can point any browsing LLM
(ChatGPT, Claude, Gemini, …) at the corpus and get grounded, cited answers — no install, no backend.

Writes (at <ROOT>/):
  llms-full.txt   compact catalogues concatenated into ONE fetchable/uploadable file (cases, inquiries,
                  CCB advice, RPR hub + corpus index). Large catalogues (OVERTURES, RPR-BY-PROVISION)
                  are linked for fetch-on-demand rather than inlined.

ASK.md (the copy/paste research prompt) and llms.txt (the retrieval guide) are hand-maintained.
This script generates only the catalogue pack so builds preserve both authored guides.

Usage: 34_llm_pack.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import os, posixpath, re, sys
from urllib.parse import urlsplit, urlunsplit

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
SITE = "https://raymond-rishty.github.io/pca-ga"
RAW = "https://raw.githubusercontent.com/raymond-rishty/pca-ga/main"
BCO_API = f"{SITE}/api/bco/index.json"

# Catalogues compact enough to concatenate into the one-file pack; generated size varies with updates.
PACK = ["INDEX.md", "RPR.md", "CASES.md", "INQUIRIES.md", "CCB-OVERTURE-ADVICE.md"]
# large indexes: linked, fetched on demand
BIG = [("OVERTURES.md", "every overture + outcome (~104k tokens)"),
       ("RPR-BY-PROVISION.md", "RPR exceptions of substance by BCO/RAO/WCF provision (~308k tokens)")]

# The generated catalogue pack is intentionally limited to the GA1–GA52 corpus.
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


def main():
    parts = [
        "# PCA GA Minutes — LLM pack (compact catalogues, one file)\n",
        f"Generated index for AI ingestion. The corpus lives at {SITE} (raw markdown at {RAW}).",
        "This file concatenates the SMALL structured catalogues so you can load them in one fetch:",
        "the corpus index, the RPR hub, judicial cases, constitutional inquiries, and CCB advice.",
        f"The provision-scoped BCO authority manifests are available at {BCO_API}; use them for provision-first retrieval.",
        "Each catalogue row deep-links to the verbatim minutes page; cite as `M<GA>GA p.<page>`.",
        "User-facing links in this pack are canonical GitHub Pages URLs ending in `.html`; source `.md` paths are for raw/repository retrieval only.",
        "",
        "Use this pack only as a fallback for corpus-wide or cross-catalogue discovery when no narrower map applies; search it for candidate records, then open and cite the underlying pages.",
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
    print(f"[{ROOT}] wrote llms-full.txt ({sz // 1024}KB ~{sz // 4000}k tokens); ASK.md and llms.txt unchanged")


if __name__ == "__main__":
    main()
