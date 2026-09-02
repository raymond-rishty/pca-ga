"""Re-extract high-confidence case pages from layout-formatted minutes.

Unlike the earlier fuzzy writer, this uses fuzzy matching only to *locate* the
first and final source blocks.  It then snaps to whole Markdown blocks and
copies complete intervening pages, preventing character loss or a boundary
that runs into the next case.
"""

from __future__ import annotations

import argparse
import io
import importlib.util
import json
import re
import subprocess
from pathlib import Path

from rapidfuzz import fuzz


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("case_matcher", ROOT / "scripts" / "50_match_case_text_in_reocr.py")
matcher = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(matcher)
PAGE = re.compile(r"(?s)(<!-- PAGE ga=(\d+) pdf_page=(\d+)\b[^>]*-->)(.*?)(?=<!-- PAGE ga=|\Z)")
ANCHOR = re.compile(r'^<a id="[^"]+"></a>\s*', re.M)
SOURCE = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?")
ADDRESS_SIGNAL = re.compile(
    r"(?i)(^\s*(?:\d{1,6}\s+.*\b(?:road|street|lane|drive|avenue|boulevard|highway)|route\s+\d)\b"
    r"|\b(?:p\.?\s*o\.?\s+box|post office box|box)\s+\d"
    r"|\b(?:phone|fax|telephone)\b\s*:?(?=\s*[+(\d])"
    r"|\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\s+\d{5}(?:-\d{4})?\b)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--ga-from", type=int, default=3)
    parser.add_argument("--ga-to", type=int, default=52)
    parser.add_argument("--threshold", type=float, default=0.80, help="Minimum whole-body normalized similarity.")
    parser.add_argument(
        "--anchor-threshold",
        type=float,
        default=0.80,
        help="Minimum fuzzy locator score; whole-body similarity remains the extraction decision.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "formatted_case_reextract.json")
    return parser.parse_args()


def soft_wrap_case_text(text: str) -> str:
    """Remove accidental hard breaks while preserving short address blocks."""
    lines = text.splitlines(keepends=True)
    contents = [line.rstrip("\r\n") for line in lines]
    address_lines: set[int] = set()
    position = 0
    while position < len(contents):
        if not contents[position].strip():
            position += 1
            continue
        start = position
        while position < len(contents) and contents[position].strip():
            position += 1
        block = contents[start:position]
        if (
            len(block) >= 2
            and max(map(lambda line: len(line.rstrip()), block), default=0) <= 80
            and any(ADDRESS_SIGNAL.search(line) for line in block)
        ):
            address_lines.update(range(start, position))

    result = []
    for index, line in enumerate(lines):
        if index in address_lines:
            result.append(line)
        else:
            content = line.rstrip("\r\n")
            result.append(re.sub(r"[ \t]+$", "", content) + line[len(content) :])
    return "".join(result)


def source_pages(vol: str) -> dict[int, dict]:
    path = ROOT / "markdown" / f"{vol}.md"
    text = path.read_text(encoding="utf-8")
    result = {}
    for found in PAGE.finditer(text):
        marker, _ga, page, body = found.groups()
        # The source-minute Markdown preserves physical OCR line wraps with
        # Markdown's two-space hard-break syntax. Case pages are prose views,
        # so carry over those wraps as ordinary soft breaks instead.
        prose = ANCHOR.sub("", body).strip()
        prose = soft_wrap_case_text(prose)
        result[int(page)] = {"marker": marker, "text": prose}
    return result


def fingerprint_rows(ref: str) -> dict[int, list[dict]]:
    """Load all main-branch case fingerprints through one Git batch process."""
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", "cases"], cwd=ROOT, text=True, encoding="utf-8"
    ).splitlines()
    markdown = [path for path in paths if path.endswith(".md")]
    process = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        input="".join(f"{ref}:{path}\n" for path in markdown).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    output = io.BytesIO(process.stdout)
    texts: dict[str, str] = {}
    for path in markdown:
        header = output.readline().decode("utf-8").strip().split()
        if len(header) != 3:
            raise RuntimeError(f"Unexpected git cat-file header for {path}: {header}")
        size = int(header[2])
        texts[path] = output.read(size).decode("utf-8")
        output.read(1)  # newline after the object payload
    grouped: dict[int, list[dict]] = {}
    for path, text in texts.items():
        source = SOURCE.search(text)
        ga_match = re.match(r"cases/ga(\d+)_", path)
        if not source or not ga_match:
            continue
        ga = int(ga_match.group(1))
        grouped.setdefault(ga, []).append({
            "case_id": Path(path).stem,
            "title": next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")), Path(path).stem),
            "path": path,
            "old_body": matcher.case_body(text),
            "vol": source.group(1),
            "start": int(source.group(2)),
            "end": int(source.group(3) or source.group(2)),
        })
    return grouped


def anchor_location(reference: str, target: str, leading: bool) -> tuple[float, int] | None:
    reference_normalized = matcher.normalize(reference)
    target_normalized, offsets = matcher.normalized_with_offsets(target)
    if len(reference_normalized) < 40 or not target_normalized:
        return None
    size = min(260, len(reference_normalized))
    needle = reference_normalized[:size] if leading else reference_normalized[-size:]
    alignment = fuzz.partial_ratio_alignment(needle, target_normalized)
    if not offsets or alignment.score <= 0:
        return None
    position = alignment.dest_start if leading else alignment.dest_end - 1
    if position < 0 or position >= len(offsets):
        return None
    return alignment.score / 100, offsets[position] + (0 if leading else 1)


def block_start(text: str, position: int) -> int:
    boundary = text.rfind("\n\n", 0, position)
    return 0 if boundary < 0 else boundary + 2


def block_end(text: str, position: int) -> int:
    boundary = text.find("\n\n", position)
    return len(text) if boundary < 0 else boundary


def replace_body(page: str, body: str) -> str:
    pieces = page.split("\n---\n")
    if len(pieces) < 3:
        raise ValueError("case page has no replaceable body delimiters")
    return "\n---\n".join([pieces[0], "\n" + body.strip() + "\n", *pieces[2:]]).rstrip() + "\n"


def candidate(row: dict, anchor_threshold: float, pages_cache: dict[str, dict[int, dict]]) -> tuple[dict, str | None]:
    segments = matcher.old_segments(row["old_body"], row["start"])
    if not segments:
        return {"case_file": row["path"], "status": "missing_source_segments"}, None
    first_page, first_reference = segments[0]
    last_page, last_reference = segments[-1]
    # Embedded page markers are stronger evidence than the displayed source
    # link, which can be stale or omit continuation pages.
    if row["vol"] not in pages_cache:
        pages_cache[row["vol"]] = source_pages(row["vol"])
    pages = pages_cache[row["vol"]]
    if any(page not in pages for page in range(first_page, last_page + 1)):
        return {"case_file": row["path"], "status": "missing_minutes_page", "span": [first_page, last_page]}, None
    start = anchor_location(first_reference, pages[first_page]["text"], leading=True)
    end = anchor_location(last_reference, pages[last_page]["text"], leading=False)
    if not start or not end:
        return {"case_file": row["path"], "status": "unlocated_boundary", "span": [first_page, last_page]}, None
    start_score, start_offset = start
    end_score, end_offset = end
    if start_score < anchor_threshold or end_score < anchor_threshold:
        return {
            "case_file": row["path"], "status": "weak_boundary", "span": [first_page, last_page],
            "start_anchor_similarity": round(start_score, 4), "end_anchor_similarity": round(end_score, 4),
        }, None
    first = pages[first_page]["text"]
    last = pages[last_page]["text"]
    start_offset = block_start(first, start_offset)
    end_offset = block_end(last, end_offset)
    if first_page == last_page and start_offset >= end_offset:
        return {"case_file": row["path"], "status": "reversed_boundary", "span": [first_page, last_page]}, None
    first_body = first[start_offset:] if first_page != last_page else first[start_offset:end_offset]
    # Preserve the first embedded source-page marker just as we do every
    # continuation page.  Case files use these markers for provenance and
    # downstream page-aware formatting checks.
    output = [f"{pages[first_page]['marker']}\n\n{first_body}".strip()]
    for page in range(first_page + 1, last_page + 1):
        text = pages[page]["text"] if page != last_page else pages[page]["text"][:end_offset]
        output.append(f"{pages[page]['marker']}\n\n{text}".strip())
    body = "\n\n".join(part.strip() for part in output if part.strip())
    score = matcher.whole_score(row["old_body"], body)
    return {
        "case_file": row["path"], "case_id": row["case_id"], "title": row["title"],
        "status": "candidate", "span": [first_page, last_page],
        "start_anchor_similarity": round(start_score, 4), "end_anchor_similarity": round(end_score, 4),
        "whole_body_similarity": round(score, 4), "candidate_chars": len(body),
    }, body


def main() -> None:
    args = parse_args()
    results = []
    pages_cache: dict[str, dict[int, dict]] = {}
    rows_by_ga = fingerprint_rows(args.ref)
    for ga in range(args.ga_from, args.ga_to + 1):
        for row in rows_by_ga.get(ga, []):
            result, body = candidate(row, args.anchor_threshold, pages_cache)
            selected = bool(body) and result.get("whole_body_similarity", 0) >= args.threshold
            result["selected"] = selected
            result["written"] = False
            if args.apply and selected:
                target = ROOT / row["path"]
                template = target.read_text(encoding="utf-8") if target.exists() else matcher.git_text(args.ref, row["path"])
                updated = replace_body(template, body)
                if updated != template:
                    target.write_text(updated, encoding="utf-8")
                    result["written"] = True
            results.append(result)
    payload = {"ref": args.ref, "threshold": args.threshold, "anchor_threshold": args.anchor_threshold, "apply": args.apply, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    selected = sum(item["selected"] for item in results)
    written = sum(item["written"] for item in results)
    print(json.dumps({"cases": len(results), "selected": selected, "written": written}, indent=2))


if __name__ == "__main__":
    main()
