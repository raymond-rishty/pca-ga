#!/usr/bin/env python3
"""Validate generated API data, rendered source links, constitution links, and Pagefind output."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Expected build output is missing: {path}")


def html_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(path.rglob("*.html"))


def has_text(paths: list[Path], needle: str) -> bool:
    for path in paths:
        if needle in path.read_text(encoding="utf-8"):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    site = args.site.resolve()

    # The schema-v3 BCO compatibility endpoint must match its canonical provision copy.
    bco_index = site / "api/bco/index.json"
    bco_manifest = site / "api/bco/38-1.json"
    provision_index = site / "api/provisions/index.json"
    provision_manifest = site / "api/provisions/bco/38-1.json"
    llms = site / "llms.txt"
    for path in (bco_index, bco_manifest, provision_index, provision_manifest, llms):
        require_file(path)
    if bco_manifest.read_bytes() != provision_manifest.read_bytes():
        raise SystemExit("The BCO compatibility manifest differs from the canonical provision manifest.")
    schema_v3 = re.compile(r'"schema_version"\s*:\s*3')
    if not schema_v3.search(bco_manifest.read_text(encoding="utf-8")):
        raise SystemExit("The generated BCO manifest is not schema version 3.")
    if not schema_v3.search(bco_index.read_text(encoding="utf-8")):
        raise SystemExit("The generated BCO index is not schema version 3.")
    if "/api/provisions/index.json" not in llms.read_text(encoding="utf-8"):
        raise SystemExit("llms.txt does not reference the canonical provision index.")

    # Extracted corpus pages need working source-PDF actions and a known judicial page link.
    extracted_dirs = ("cases", "inquiries", "overtures", "rpr", "studies")
    extracted_pages: list[Path] = []
    for directory in extracted_dirs:
        pages = html_files(site / directory)
        if not pages:
            raise SystemExit(f"No rendered HTML pages found under {directory}.")
        extracted_pages.extend(pages)
        if not has_text(pages, "data-source-pdf-actions"):
            raise SystemExit(f"No source-PDF page action rendered for {directory}.")
    if not has_text(extracted_pages, 'class="source-pdf-link"'):
        raise SystemExit("No rendered extracted page exposes a source PDF link.")
    if not has_text(html_files(site / "cases"), "51st_pcaga_2024.pdf#page=749"):
        raise SystemExit("Expected GA51 case source PDF page link was not rendered.")
    if not has_text(html_files(site / "cases"), 'data-source-id="case-pdf:'):
        raise SystemExit("No dedicated judicial source PDF was rendered.")
    if not has_text(html_files(site / "studies"), 'data-source-id="study-pdf:'):
        raise SystemExit("No dedicated study source PDF was rendered.")
    empty_link = re.compile(r'class="source-pdf-link" href=""')
    for path in extracted_pages:
        if empty_link.search(path.read_text(encoding="utf-8")):
            raise SystemExit(f"An extracted source PDF link has an empty href: {path}")

    # All 52 full Minutes volumes must expose the canonical PCA Historical Center PDF.
    volume_pattern = re.compile(r"ga\d{2}_\d{4}\.html$")
    volume_pages = [path for path in (site / "markdown").glob("*.html") if volume_pattern.fullmatch(path.name)]
    if len(volume_pages) != 52:
        raise SystemExit(f"Expected 52 rendered Minutes volumes, found {len(volume_pages)}.")
    canonical_pdf = re.compile(
        r'class="source-pdf-link" href="https://www\.pcahistory\.org/pca/ga/'
        r'[0-9]+(?:st|nd|rd|th)_pcaga_[0-9]{4}\.pdf"'
    )
    for path in volume_pages:
        if not canonical_pdf.search(path.read_text(encoding="utf-8")):
            raise SystemExit(f"Missing canonical source PDF link in {path.name}.")

    # Linker outputs and markers must exist after the whole-site transform.
    for relative in (
        "assets/constitution/bco-index.json",
        "assets/constitution/standards/wcf.json",
        "assets/constitution/standards/wlc.json",
        "assets/constitution/standards/wsc.json",
        "assets/constitution/packs/rao.json",
        "assets/minutes-pages.json",
        "assets/scripture-audit.json",
        "assets/scripture-audit-summary.json",
        "assets/scripture/bsb/John/3.json",
        "provisions/index.html",
        "provisions/bco/40-1/index.html",
        "provisions/wlc/q-62/index.html",
        "provisions/rao/1-1/index.html",
        "app/provision_search.json",
    ):
        require_file(site / relative)
    all_pages = html_files(site)
    for marker in (
        "data-bco-ref=",
        'class="constitution-ref"',
        'data-constitution-book="rao"',
        'class="minutes-ref"',
        'class="scripture-ref"',
    ):
        if not has_text(all_pages, marker):
            raise SystemExit(f"No rendered page contains the required constitutional marker {marker!r}.")

    # Pagefind must have indexed representative Minutes output.
    if not has_text(volume_pages, "data-pagefind-body"):
        raise SystemExit("The rendered Minutes pages have no Pagefind body markers.")
    if not has_text(volume_pages, 'content="General Assembly minutes"'):
        raise SystemExit("The rendered Minutes pages have no Pagefind title metadata.")
    pagefind = site / "pagefind"
    require_file(pagefind / "pagefind.js")
    if sum(1 for path in pagefind.rglob("*") if path.is_file()) <= 5:
        raise SystemExit("Pagefind produced an unexpectedly small index.")

    print(f"Validated rendered site at {site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
