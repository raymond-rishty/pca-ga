#!/usr/bin/env python3
"""Maintain verified printed-page runs for the scanned GA minutes.

The first sixteen volumes are image scans.  Their embedded OCR occasionally reads a
number near a margin as a folio, but does not reliably preserve the book's printed
page number.  A pagination run records the stable relationship inside a continuous
printed sequence::

    printed_page = pdf_page - offset

``sample`` renders only the outer header bands of selected PDF pages and asks
Tesseract for a proposed folio.  It is an audit aid: a human must review the
proposed readings before they are added to ``index/pagination_runs.json``.  ``apply``
then projects approved runs onto the rendered Markdown page comments, preserving
the original PDF page and recording that the folio was inferred from a verified run.

The source scans are intentionally not committed.  Download them separately from
the PCA Historical Center before using ``sample``.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = ROOT / "index" / "pagination_runs.json"
PAGE_COMMENT = re.compile(
    r"<!-- PAGE ga=(?P<ga>\d+) pdf_page=(?P<pdf>\d+) printed_page=(?P<printed>[^\s]+)"
    r"(?: printed_page_source=(?P<source>[^\s]+))? -->"
)
PAGE_ANCHOR = re.compile(
    r'<a id="ga(?P<anchor_ga>\d+)-p(?P<page>\d+)"></a>(?P<gap>\s*)'
    r'(?P<comment><!-- PAGE ga=(?P<ga>\d+) pdf_page=(?P<pdf>\d+) printed_page=[^\s]+'
    r'(?: printed_page_source=[^\s]+)? -->)'
)


def load_map(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported pagination-map schema: {data.get('schema_version')!r}")
    return data


def runs_by_ga(data: dict) -> dict[int, list[dict]]:
    result = {}
    for volume in data.get("volumes", []):
        ga = int(volume["ga"])
        runs = volume.get("runs", [])
        previous_end = 0
        for run in runs:
            start, end = int(run["pdf_start"]), int(run["pdf_end"])
            if start > end:
                raise ValueError(f"GA{ga}: run starts after it ends ({start}>{end})")
            if start <= previous_end:
                raise ValueError(f"GA{ga}: runs overlap or are out of order at PDF p. {start}")
            if run.get("numbering") != "arabic":
                raise ValueError(f"GA{ga}: only arabic runs can be projected automatically")
            if "offset" not in run:
                raise ValueError(f"GA{ga}: run beginning PDF p. {start} lacks an offset")
            previous_end = end
        result[ga] = runs
    return result


def resolve(runs: list[dict], pdf_page: int) -> tuple[str | None, str | None]:
    for run in runs:
        if int(run["pdf_start"]) <= pdf_page <= int(run["pdf_end"]):
            return str(pdf_page - int(run["offset"])), "inferred"
    return None, None


def apply_map(content_root: Path, map_path: Path, check: bool = False) -> int:
    runs = runs_by_ga(load_map(map_path))
    changed = 0
    # Page comments are also copied into case, inquiry, and study extracts.  Keep
    # those citations synchronized with the full minutes, not merely the source
    # volume under markdown/.
    content_dirs = ("markdown", "cases", "cases-rebuilt", "inquiries", "rpr", "overtures", "studies")
    paths = [
        path for directory in content_dirs
        for path in (content_root / directory).rglob("*.md")
        if path.is_file()
    ]
    for path in sorted(paths):
        text = path.read_text()

        def replace(match: re.Match) -> str:
            nonlocal changed
            ga, pdf = int(match["ga"]), int(match["pdf"])
            if ga not in runs:
                return match.group(0)
            printed, source = resolve(runs.get(ga, []), pdf)
            if printed is None:
                # The legacy edge-line OCR is especially unreliable in these scans.
                # Do not let an isolated number near a page edge outrank the audited
                # map; outside a verified run the UI must say "PDF p." explicitly.
                replacement = f"<!-- PAGE ga={ga} pdf_page={pdf} printed_page=null -->"
                if replacement != match.group(0):
                    changed += 1
                return replacement
            replacement = (
                f"<!-- PAGE ga={ga} pdf_page={pdf} printed_page={printed} "
                f"printed_page_source={source} -->"
            )
            if replacement != match.group(0):
                changed += 1
            return replacement

        updated = PAGE_COMMENT.sub(replace, text)

        # The static anchor directly preceding a page marker is the fallback for
        # deep links before the client-side marker enhancement runs.  It must
        # follow the same inferred folio as the comment; otherwise a printed-page
        # link can land two pages early and later markers can duplicate its id.
        def replace_anchor(match: re.Match) -> str:
            nonlocal changed
            ga, pdf = int(match["ga"]), int(match["pdf"])
            if ga != int(match["anchor_ga"]) or ga not in runs:
                return match.group(0)
            printed, _ = resolve(runs[ga], pdf)
            target = printed if printed is not None else str(pdf)
            replacement = (
                f'<a id="ga{ga:02d}-p{target}"></a>{match["gap"]}{match["comment"]}'
            )
            if replacement != match.group(0):
                changed += 1
            return replacement

        updated = PAGE_ANCHOR.sub(replace_anchor, updated)
        if updated != text and not check:
            path.write_text(updated)
    return changed


def _ocr_band(pdf: Path, page: int, side: str) -> str:
    """Return OCR for the outer 38% of a page's top 20% header band."""
    import fitz  # PyMuPDF is already a corpus extraction dependency.

    doc = fitz.open(pdf)
    rect = doc[page - 1].rect
    width, height = rect.width * 0.38, rect.height * 0.20
    x0 = rect.x0 if side == "left" else rect.x1 - width
    clip = fitz.Rect(x0, rect.y0, x0 + width, rect.y0 + height)
    pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), clip=clip, alpha=False)
    doc.close()
    with tempfile.NamedTemporaryFile(suffix=".png") as fh:
        pix.save(fh.name)
        return subprocess.check_output(
            ["tesseract", fh.name, "stdout", "--psm", "6"], text=True, stderr=subprocess.DEVNULL
        ).strip()


def sample(pdf: Path, pages: list[int]) -> None:
    for page in pages:
        # Recto/verso folios conventionally alternate right/left.  A single outer
        # header band is both faster and less likely to confuse a section number
        # with the folio; reviewers can rerun a particular page by hand if needed.
        side = "right" if page % 2 else "left"
        print(json.dumps({"pdf_page": page, "folio_side": side, "header_ocr": _ocr_band(pdf, page, side)}))


def contact_sheet(pdf: Path, output: Path, pages: list[int]) -> None:
    """Make a compact visual-review sheet of the expected outer header folios."""
    import fitz
    from PIL import Image, ImageDraw

    doc = fitz.open(pdf)
    tiles = []
    for page in pages:
        if not 1 <= page <= len(doc):
            raise ValueError(f"PDF p. {page} is outside {pdf.name} ({len(doc)} pages)")
        source = doc[page - 1]
        rect = source.rect
        width, height = rect.width * 0.42, rect.height * 0.22
        x0 = rect.x0 if page % 2 == 0 else rect.x1 - width
        pix = source.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), clip=fitz.Rect(x0, rect.y0, x0 + width, rect.y0 + height), alpha=False)
        tile = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).resize((360, 186))
        labelled = Image.new("RGB", (360, 212), "white")
        labelled.paste(tile, (0, 0))
        ImageDraw.Draw(labelled).text((8, 190), f"PDF {page} ({'left' if page % 2 == 0 else 'right'} header)", fill="black")
        tiles.append(labelled)
    doc.close()
    columns, rows = 4, (len(tiles) + 3) // 4
    sheet = Image.new("RGB", (columns * 368 + 8, rows * 220 + 8), "#dddddd")
    for index, tile in enumerate(tiles):
        x, y = 8 + (index % columns) * 368, 8 + (index // columns) * 220
        sheet.paste(tile, (x, y))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_apply = sub.add_parser("apply", help="project approved runs onto Markdown page comments")
    p_apply.add_argument("--map", type=Path, default=DEFAULT_MAP)
    p_apply.add_argument("--content-root", type=Path, default=ROOT)
    p_apply.add_argument("--check", action="store_true", help="fail if applying the map would change Markdown")
    p_sample = sub.add_parser("sample", help="OCR outer header bands from a source PDF")
    p_sample.add_argument("pdf", type=Path)
    p_sample.add_argument("pages", nargs="+", type=int)
    p_sheet = sub.add_parser("contact-sheet", help="make a visual-review sheet of outer header bands")
    p_sheet.add_argument("pdf", type=Path)
    p_sheet.add_argument("output", type=Path)
    p_sheet.add_argument("pages", nargs="+", type=int)
    args = parser.parse_args()

    if args.command == "apply":
        changes = apply_map(args.content_root, args.map, args.check)
        print(f"pagination map {'would update' if args.check else 'updated'} {changes} page markers")
        if args.check and changes:
            raise SystemExit(1)
    elif args.command == "sample":
        sample(args.pdf, args.pages)
    else:
        contact_sheet(args.pdf, args.output, args.pages)


if __name__ == "__main__":
    main()
