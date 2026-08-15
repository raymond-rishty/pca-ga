#!/usr/bin/env python3
"""Build the page_jsonl source layer from the re-OCR Markdown corpus.

The re-OCR workflow produces two complementary artifacts:

* ``markdown/gaNN_YYYY.md`` is the authoritative, semantically formatted text
  published by this repository.  Its PAGE comments define the PDF-page and
  printed-page boundaries.
* ``ocr-bakeoff/corpus/gaNN/paddle_ocr_json/page_NNNN.json`` is Paddle's
  machine-readable evidence for that page (confidence, line count, source PDF
  hash, and runtime).  It is not used to replace Markdown text.

This adapter joins those artifacts into the page_jsonl contract consumed by
the structure, indexing, and case-extraction stages.  It is deliberately
re-runnable and supports Markdown-only operation when the Paddle corpus is not
available.

Usage:
  00_build_page_jsonl.py [--only ga01_1973 ...]
  00_build_page_jsonl.py --paddle-root ocr-bakeoff/corpus --require-paddle

Output:
  build/page_jsonl/gaNN_YYYY.pages.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKDOWN = ROOT / "markdown"
DEFAULT_OUTPUT = ROOT / "build" / "page_jsonl"
DEFAULT_PADDLE = ROOT / "ocr-bakeoff" / "corpus"

PAGE_START = re.compile(
    r"(?m)^(?:<a id=\"(?P<anchor>[^\"]+)\"></a>\r?\n)?"
    r"<!-- PAGE ga=(?P<ga>\d+) pdf_page=(?P<pdf>\d+) "
    r"printed_page=(?P<printed>[^\s>]+)(?: printed_page_source=(?P<source>[^\s>]+))? -->[ \t]*$"
)
VOLUME = re.compile(r"^ga(?P<ga>\d{2})_(?P<year>\d{4})$")
GA_ITEM = re.compile(r"\b(?P<ga>\d{1,2})-(?P<item>\d{1,3})\b")


def parse_scalar(value: str):
    if value == "null":
        return None
    if re.fullmatch(r"\d+", value):
        return int(value)
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    result = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            result[key.strip()] = value.strip().strip('"')
    return result


def parse_markdown(path: Path) -> tuple[dict, list[dict]]:
    text = path.read_text(encoding="utf-8")
    meta = parse_front_matter(text)
    matches = list(PAGE_START.finditer(text))
    if not matches:
        raise ValueError(f"{path}: no PAGE comments found")

    rows = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():next_start].strip()
        ga = int(match.group("ga"))
        pdf_page = int(match.group("pdf"))
        printed = parse_scalar(match.group("printed"))
        tokens = []
        seen = set()
        for token in GA_ITEM.findall(body):
            if int(token[0]) == ga and token[0] + "-" + token[1] not in seen:
                value = token[0] + "-" + token[1]
                seen.add(value)
                tokens.append(value)
        rows.append({
            "vol": path.stem,
            "ga_ordinal": ga,
            "year": int(meta.get("year") or re.search(r"_(\d{4})$", path.stem).group(1)),
            "pdf_page": pdf_page,
            "printed_page": printed,
            "text": body,
            "char_count": len(body),
            "ga_item_tokens": tokens,
            "engine": "paddle_markdown",
            # Keep the page_jsonl contract used by 04_structure_tag and the
            # review tools.  Paddle's recognition score is preserved under
            # `paddle`; it is not a substitute for the legacy dictionary QC
            # metrics, so those fields intentionally remain null.
            "qc": {
                "verdict": "paddle_external",
                "dict_hitrate": None,
                "despaced_hitrate": None,
                "whitespace_frag": None,
                "digit_flag": False,
                "digit_present": False,
            },
            "source_anchor": match.group("anchor"),
            "printed_page_source": match.group("source"),
        })

    pages = [r["pdf_page"] for r in rows]
    expected = list(range(1, len(rows) + 1))
    if pages != expected:
        raise ValueError(f"{path}: PAGE comments are not contiguous 1..N: {pages[:5]}...")
    return meta, rows


def paddle_dir(root: Path, assembly: str) -> Path | None:
    candidates = [root / assembly / "paddle_ocr_json"]
    if root.name == assembly:
        candidates.append(root / "paddle_ocr_json")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_paddle(root: Path, assembly: str, page: int) -> tuple[dict | None, dict | None]:
    directory = paddle_dir(root, assembly)
    if directory is None:
        return None, None
    evidence_path = directory / f"page_{page:04d}.json"
    evidence = load_json(evidence_path) if evidence_path.exists() else None
    manifest_path = directory / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else None
    page_manifest = next(
        (item for item in (manifest or {}).get("pages", []) if item.get("page") == page),
        {},
    )
    return evidence, page_manifest


def evidence_fields(evidence: dict | None, page_manifest: dict | None, paddle_root: Path) -> dict:
    if not evidence:
        return {}
    fields = {
        "schema": evidence.get("schema"),
        "status": evidence.get("status"),
        "source_pdf_sha256": evidence.get("source_pdf_sha256"),
        "line_count": evidence.get("line_count"),
        "raw_chars": evidence.get("raw_chars"),
        "mean_rec_score": evidence.get("mean_rec_score"),
        "runtime_seconds": evidence.get("runtime_seconds"),
        "ocr_source": (page_manifest or {}).get("ocr_source"),
        "layout_source": (page_manifest or {}).get("layout_source"),
        "blocks": (page_manifest or {}).get("blocks"),
    }
    return {key: value for key, value in fields.items() if value is not None}


def build_one(path: Path, output: Path, paddle_root: Path | None, require_paddle: bool) -> tuple[int, int, int]:
    meta, rows = parse_markdown(path)
    assembly = path.stem.split("_")[0]
    evidence_count = 0
    missing = []
    for row in rows:
        evidence, page_manifest = load_paddle(paddle_root, assembly, row["pdf_page"]) if paddle_root else (None, None)
        if evidence and evidence.get("status") == "success":
            evidence_count += 1
            row["paddle"] = evidence_fields(evidence, page_manifest, paddle_root)
            row["engine"] = "paddle_markdown"
        else:
            missing.append(row["pdf_page"])
            row["engine"] = "markdown_only"
        if row.get("source_anchor") is None:
            raise ValueError(f"{path}: page {row['pdf_page']} has no anchor")

    if require_paddle and missing:
        raise ValueError(f"{path}: missing Paddle evidence for {len(missing)} pages, e.g. {missing[:8]}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(output)
    if missing:
        print(f"[warn] {path.stem}: Markdown-only pages={len(missing)}", file=sys.stderr)
    return len(rows), evidence_count, len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markdown-root", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--paddle-root", type=Path, default=DEFAULT_PADDLE)
    parser.add_argument("--only", nargs="*", help="volume ids such as ga01_1973")
    parser.add_argument("--require-paddle", action="store_true")
    args = parser.parse_args()

    files = sorted(args.markdown_root.glob("ga*.md"))
    if args.only:
        wanted = set(args.only)
        files = [path for path in files if path.stem in wanted]
    if not files:
        parser.error(f"no Markdown volumes found under {args.markdown_root}")

    total_pages = total_evidence = total_missing = 0
    for path in files:
        output = args.output_root / f"{path.stem}.pages.jsonl"
        pages, evidence, missing = build_one(path, output, args.paddle_root, args.require_paddle)
        total_pages += pages
        total_evidence += evidence
        total_missing += missing
        print(f"[{path.stem}] pages={pages} paddle_evidence={evidence} markdown_only={missing} -> {output}")
    print(f"[page_jsonl] volumes={len(files)} pages={total_pages} paddle_evidence={total_evidence} markdown_only={total_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
