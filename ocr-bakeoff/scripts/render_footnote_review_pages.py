"""Render deterministic review pages selected from a corpus footnote scan."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import fitz


ROOT = Path(__file__).resolve().parents[2]


def pdf_by_volume() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in (ROOT / "minutes").glob("*.pdf"):
        match = re.match(r"(\d+)(?:st|nd|rd|th)_pcaga_(\d{4})\.pdf$", path.name, re.IGNORECASE)
        if match:
            result[f"ga{int(match.group(1)):02d}"] = path
    return result


def load_scan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_pages(scan: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    pages: dict[tuple[str, int], dict[str, Any]] = {}
    for report in scan.get("reports", []):
        volume = str(report.get("volume"))
        for item in report.get("review_queue", []):
            if mode == "note-only" and item.get("type") != "note_entry_without_marker_pair":
                continue
            if mode == "markers" and item.get("type") == "note_entry_without_marker_pair":
                continue
            key = (volume, int(item["page"]))
            record = pages.setdefault(
                key,
                {
                    "volume": volume,
                    "page": int(item["page"]),
                    "items": [],
                },
            )
            record["items"].append(item)
    return [pages[key] for key in sorted(pages)]


def render_pages(scan_path: Path, output_dir: Path, mode: str, dpi: int, limit: int | None) -> int:
    scan = load_scan(scan_path)
    pdfs = pdf_by_volume()
    records = selected_pages(scan, mode)
    if limit is not None:
        records = records[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    documents: dict[str, fitz.Document] = {}
    try:
        for record in records:
            volume = record["volume"]
            pdf = pdfs.get(volume)
            if pdf is None:
                raise FileNotFoundError(f"no PDF found for {volume}")
            document = documents.setdefault(volume, fitz.open(pdf))
            page_number = int(record["page"])
            if not 1 <= page_number <= len(document):
                raise ValueError(f"page {page_number} is outside {pdf.name}")
            image_path = output_dir / f"{volume}_p{page_number:04d}.png"
            pixmap = document[page_number - 1].get_pixmap(
                matrix=fitz.Matrix(dpi / 72, dpi / 72),
                alpha=False,
            )
            pixmap.save(image_path)
            manifest.append(
                {
                    "volume": volume,
                    "page": page_number,
                    "pdf": str(pdf),
                    "image": str(image_path),
                    "items": record["items"],
                }
            )
    finally:
        for document in documents.values():
            document.close()
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return len(manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("all", "note-only", "markers"), default="all")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    count = render_pages(args.scan, args.output_dir, args.mode, args.dpi, args.limit)
    print(json.dumps({"pages_rendered": count, "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
