"""Propose or apply conservative paragraph breaks to corrected minutes.

The main-branch case corpus is a structural reference only.  This script
aligns each old source-page segment to its corrected counterpart, then carries
over only a blank-line paragraph boundary when the paragraph's opening text
has an unambiguous high-similarity location in the corrected page.  It never
copies old words, removes corrected words, or changes case pages.

Run without ``--apply`` to produce a reviewable JSON report.  Applying is
deliberately opt-in and limited to the reported high-confidence insertions.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz


ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"<!--\s*PAGE\s+ga=(\d+)\s+pdf_page=(\d+)[^>]*-->")
SOURCE_START = re.compile(r"\*Source:.*?\bpp?\.\s*(\d+)", re.I)
SEPARATOR = "\n---\n"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="Structural reference git ref.")
    parser.add_argument("--ga", default="1-18", help="Assemblies, e.g. 1-18,20.")
    parser.add_argument("--threshold", type=float, default=94.0, help="Minimum anchor partial-ratio score (0-100).")
    parser.add_argument("--report", type=Path, default=ROOT / "build" / "case_paragraph_break_audit.json")
    parser.add_argument("--apply", action="store_true", help="Insert only high-confidence blank paragraph breaks.")
    return parser.parse_args()


def ga_numbers(value: str) -> set[int]:
    result: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first, last = map(int, part.split("-", 1))
            result.update(range(first, last + 1))
        else:
            result.add(int(part))
    return result


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True, encoding="utf-8", capture_output=True
    ).stdout


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for index, char in enumerate(text.casefold()):
        if char.isalnum():
            if pending_space and chars:
                chars.append(" ")
                offsets.append(index)
            chars.append(char)
            offsets.append(index)
            pending_space = False
        elif chars:
            pending_space = True
    return "".join(chars), offsets


def page_chunks(text: str) -> dict[tuple[int, int], tuple[int, int, str]]:
    markers = list(PAGE.finditer(text))
    result: dict[tuple[int, int], tuple[int, int, str]] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        result[(int(marker.group(1)), int(marker.group(2)))] = (marker.end(), end, text[marker.end() : end])
    return result


def old_segments(text: str) -> dict[tuple[int, int], str]:
    body = text.split(SEPARATOR, 1)[1] if SEPARATOR in text else text
    result = {key: value[2] for key, value in page_chunks(body).items()}
    markers = list(PAGE.finditer(body))
    source = SOURCE_START.search(text)
    # Existing case pages commonly begin directly with their source text and
    # do not place a PAGE marker until the first page break.  Their source
    # locator supplies the otherwise implicit first PDF page.
    if source and markers:
        first = markers[0]
        prefix = body[: first.start()].strip()
        if prefix:
            result[(int(first.group(1)), int(source.group(1)))] = prefix
    elif source and body.strip():
        ga_match = PAGE.search(text)
        if ga_match:
            result[(int(ga_match.group(1)), int(source.group(1)))] = body.strip()
    return result


def paragraph_starts(text: str) -> list[str]:
    """Return substantial starts of paragraphs that are blank-line separated."""
    starts: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        clean = re.sub(r"\s+", " ", paragraph).strip()
        normalized, _ = normalize_with_offsets(clean)
        if len(normalized) >= 60:
            starts.append(normalized[:180])
    return starts[1:]  # The first paragraph needs no preceding inserted break.


def candidate_offset(anchor: str, corrected: str, threshold: float) -> tuple[float, int] | None:
    normalized, offsets = normalize_with_offsets(corrected)
    if not normalized or not offsets:
        return None
    alignment = fuzz.partial_ratio_alignment(anchor, normalized)
    if alignment.score < threshold or alignment.dest_start >= len(offsets):
        return None
    raw = offsets[alignment.dest_start]
    # A transferred break must replace ordinary inline whitespace, rather than
    # be placed inside a word or duplicate a structural break already present.
    if raw == 0 or not corrected[raw - 1].isspace() or "\n\n" in corrected[max(0, raw - 3) : raw + 1]:
        return None
    # Do not split a Markdown heading token (for example, turn ``### CASE``
    # into an empty ``###`` heading followed by a paragraph).
    line_prefix = corrected[:raw].rsplit("\n", 1)[-1]
    if re.fullmatch(r"#{1,6}\s+", line_prefix):
        return None
    return alignment.score, raw


def main() -> None:
    args = arguments()
    selected_ga = ga_numbers(args.ga)
    candidates: dict[Path, list[dict]] = defaultdict(list)
    case_files = git("ls-tree", "-r", "--name-only", args.ref, "--", "cases").splitlines()
    for case_file in case_files:
        ga_match = re.match(r"cases/ga(\d+)_", case_file)
        if not ga_match or int(ga_match.group(1)) not in selected_ga:
            continue
        old = git("show", f"{args.ref}:{case_file}")
        for (ga, page), segment in old_segments(old).items():
            # File names encode the year, but a page marker is sufficient to
            # identify GA; resolve the one local minutes Markdown for that GA.
            matches = sorted((ROOT / "markdown").glob(f"ga{ga:02d}_*.md"))
            if len(matches) != 1:
                continue
            markdown = matches[0]
            corrected_pages = page_chunks(markdown.read_text(encoding="utf-8"))
            corrected = corrected_pages.get((ga, page))
            if not corrected:
                continue
            page_start, _page_end, page_text = corrected
            source_normalized, _ = normalize_with_offsets(segment)
            target_normalized, _ = normalize_with_offsets(page_text)
            if len(source_normalized) < 80 or fuzz.partial_ratio(source_normalized, target_normalized) < 80:
                continue
            for anchor in paragraph_starts(segment):
                found = candidate_offset(anchor, page_text, args.threshold)
                if found is None:
                    continue
                score, offset = found
                candidates[markdown].append({
                    "case": case_file,
                    "ga": ga,
                    "pdf_page": page,
                    "offset": page_start + offset,
                    "anchor_score": round(score, 2),
                    "anchor": anchor[:90],
                })

    report_items = []
    changed_files = []
    for path, raw in sorted(candidates.items()):
        by_offset: dict[int, list[dict]] = defaultdict(list)
        for item in raw:
            by_offset[item["offset"]].append(item)
        selected = [max(group, key=lambda item: item["anchor_score"]) for _, group in sorted(by_offset.items())]
        report_items.append({"path": str(path.relative_to(ROOT)), "insertions": selected})
        if args.apply and selected:
            content = path.read_text(encoding="utf-8")
            for item in sorted(selected, key=lambda item: item["offset"], reverse=True):
                offset = item["offset"]
                left = offset - 1
                while left >= 0 and content[left] in " \t\r\n":
                    left -= 1
                content = content[: left + 1] + "\n\n" + content[offset:]
            path.write_text(content, encoding="utf-8")
            changed_files.append(str(path.relative_to(ROOT)))

    report = {
        "ref": args.ref,
        "assemblies": sorted(selected_ga),
        "threshold": args.threshold,
        "apply": args.apply,
        "files": report_items,
        "candidate_insertions": sum(len(item["insertions"]) for item in report_items),
        "changed_files": changed_files,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(report_items), "candidate_insertions": report["candidate_insertions"], "changed_files": len(changed_files)}, indent=2))


if __name__ == "__main__":
    main()
