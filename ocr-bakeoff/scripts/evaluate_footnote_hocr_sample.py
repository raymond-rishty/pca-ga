"""Run the footnote detector with targeted Tesseract geometry sidecars.

This is a diagnostic slice, not a replacement corpus scan.  It keeps the
same PP-Structure, PDF-native, and scope inputs while adding hOCR/box files
for the visually adjudicated marker pages.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("footnote_evidence.py")
SPEC = importlib.util.spec_from_file_location("footnote_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
footnote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(footnote)
SCAN_SPEC = importlib.util.spec_from_file_location("scan_footnote_corpus", Path(__file__).with_name("scan_footnote_corpus.py"))
assert SCAN_SPEC and SCAN_SPEC.loader
scan_module = importlib.util.module_from_spec(SCAN_SPEC)
SCAN_SPEC.loader.exec_module(scan_module)


def pdf_by_volume() -> dict[str, Path]:
    result = {}
    for path in (ROOT / "minutes").glob("*.pdf"):
        match = re.match(r"(\d+)(?:st|nd|rd|th)_pcaga_(\d{4})\.pdf$", path.name, re.IGNORECASE)
        if match:
            result[f"ga{int(match.group(1)):02d}"] = path
    return result


def main() -> None:
    gold = json.loads((ROOT / "ocr-bakeoff" / "benchmark" / "footnote_gold_marker_sample.json").read_text(encoding="utf-8"))
    hocr_dir = ROOT / "tmp" / "footnote_hocr_marker_sample"
    reports = []
    grouped = defaultdict(list)
    for item in gold["pages"]:
        grouped[str(item["volume"])].append(item)

    for volume, items in sorted(grouped.items()):
        pdf = pdf_by_volume()[volume]
        document = fitz.open(pdf)
        pages = []
        try:
            for item in items:
                number = int(item["page"])
                ocr_path = ROOT / "ocr-bakeoff" / "corpus" / volume / "paddle_ocr_json" / f"page_{number:04d}.json"
                layout_path = ROOT / "ocr-bakeoff" / "corpus" / volume / "paddle_layout_json" / f"page_{number:04d}.json"
                stem = f"{volume}_p{number:04d}"
                hocr_path = hocr_dir / f"{stem}.hocr"
                box_path = hocr_dir / f"{stem}.box"
                hocr = footnote.hocr_page_evidence(hocr_path, 150.0, box_path=box_path)
                evidence = footnote.analyze_page(
                    document[number - 1],
                    footnote.load_json(ocr_path),
                    footnote.load_json(layout_path),
                    hocr=hocr,
                )
                pages.append({"page": number, "has_hocr": bool(hocr), **evidence})
        finally:
            document.close()

        scope_path = next((ROOT / "tmp").glob(f"footnote_scopes_{volume}_*_derived.json"), None)
        scopes = None
        if scope_path:
            scopes = footnote.load_scope_records(json.loads(scope_path.read_text(encoding="utf-8")))
        footnote.resolve_document(pages, scopes=scopes)
        compact = [scan_module.compact_page(page) for page in pages]
        reports.append(
            {
                "volume": volume,
                "pdf": str(pdf),
                "selection": "marker gold sample with hOCR character geometry",
                "scope_source": str(scope_path) if scope_path else None,
                "scope_policy": "unique_equal_scope_required" if scopes is not None else "same_page_only",
                "pages": compact,
                "note_pages": [page for page in compact if page["note_block_count"] > 0],
            }
        )

    output = ROOT / "ocr-bakeoff" / "reports" / "footnote_hocr_marker_sample_scan.json"
    output.write_text(json.dumps({"schema": "pca-ga.footnote-hocr-marker-sample.v1", "reports": reports}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "volumes": len(reports), "pages": sum(len(report["pages"]) for report in reports)}))


if __name__ == "__main__":
    main()
