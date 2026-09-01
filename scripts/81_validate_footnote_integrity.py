"""Validate that generated footnote references and definitions are paired.

The repository contains both Markdown-style footnotes and HTML footnotes.
This validator deliberately checks the generated ``fn-`` namespace only.  It
does not try to infer whether an unlinked bare number is a footnote; that is a
source/OCR adjudication problem handled before materialization.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORIES = ("markdown", "cases", "cases-rebuilt", "inquiries", "studies")
PAGE = re.compile(r"<!-- PAGE ga=(\d+) pdf_page=(\d+)\b[^>]*-->")
GENERATED_FOOTNOTE_ID = re.compile(r"fn-(?P<volume>ga\d{2})-p(?P<page>\d+)-n(?P<value>\d+)$")

MARKDOWN_REFERENCE = re.compile(r"\[\^(fn-[^\]]+)\](?!:)")
HTML_REFERENCE = re.compile(r'id="fnref-(fn-[^"]+)"')
HTML_HREF_REFERENCE = re.compile(r'href="#(fn-[^"]+)"')
MARKDOWN_DEFINITION = re.compile(r"\[\^(fn-[^\]]+)\]:")
HTML_DEFINITION = re.compile(r'<a id="(fn-[^"]+)"></a>')


@dataclass(frozen=True)
class FootnoteInventory:
    references: tuple[str, ...]
    definitions: tuple[str, ...]
    concatenated_definition_lines: tuple[int, ...]

    @property
    def reference_ids(self) -> set[str]:
        return set(self.references)

    @property
    def definition_ids(self) -> set[str]:
        return set(self.definitions)

    @property
    def missing_definitions(self) -> list[str]:
        return sorted(self.reference_ids - self.definition_ids)

    @property
    def orphan_definitions(self) -> list[str]:
        return sorted(self.definition_ids - self.reference_ids)

    @property
    def duplicate_definitions(self) -> list[str]:
        return sorted(
            footnote_id
            for footnote_id, count in Counter(self.definitions).items()
            if count > 1
        )

    @property
    def issues(self) -> list[str]:
        issues: list[str] = []
        if self.missing_definitions:
            issues.append("references without definitions: " + ", ".join(self.missing_definitions))
        if self.orphan_definitions:
            issues.append("definitions without references: " + ", ".join(self.orphan_definitions))
        if self.duplicate_definitions:
            issues.append("duplicate definitions: " + ", ".join(self.duplicate_definitions))
        if self.concatenated_definition_lines:
            lines = ", ".join(str(line) for line in self.concatenated_definition_lines)
            issues.append("multiple definitions on one line: " + lines)
        return issues


def inventory(text: str) -> FootnoteInventory:
    """Return all generated reference and definition IDs in ``text``."""

    references: list[str] = []
    for pattern in (MARKDOWN_REFERENCE, HTML_REFERENCE, HTML_HREF_REFERENCE):
        references.extend(match.group(1) for match in pattern.finditer(text))

    definitions: list[str] = []
    for pattern in (MARKDOWN_DEFINITION, HTML_DEFINITION):
        definitions.extend(match.group(1) for match in pattern.finditer(text))

    concatenated_lines = tuple(
        line_number
        for line_number, line in enumerate(text.splitlines(), start=1)
        if sum(len(pattern.findall(line)) for pattern in (MARKDOWN_DEFINITION, HTML_DEFINITION)) > 1
    )
    return FootnoteInventory(tuple(references), tuple(definitions), concatenated_lines)


def page_locality_issues(text: str) -> list[str]:
    """Check that generated definitions remain in their encoded PAGE chunk."""
    markers = list(PAGE.finditer(text))
    if not markers:
        return []

    def page_at(offset: int) -> int | None:
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            if marker.start() <= offset < end:
                return int(marker.group(2))
        return None

    issues: list[str] = []
    definition_patterns = (
        re.compile(r"\[\^(fn-[^\]\s]+)\]:"),
        re.compile(r'<a id="(fn-[^"]+)"></a>'),
    )
    seen: set[tuple[str, int]] = set()
    for pattern in definition_patterns:
        for match in pattern.finditer(text):
            footnote_id = match.group(1)
            parsed = GENERATED_FOOTNOTE_ID.fullmatch(footnote_id)
            if not parsed:
                continue
            page = page_at(match.start())
            if page is None:
                issues.append(f"definition outside a PAGE chunk: {footnote_id}")
                continue
            expected_page = int(parsed.group("page"))
            if page != expected_page and (footnote_id, page) not in seen:
                issues.append(
                    f"definition for {footnote_id} is in PAGE {page}, expected PAGE {expected_page}"
                )
                seen.add((footnote_id, page))
    return issues


def markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.md"))
    return sorted(set(files))


def validate_paths(paths: list[Path]) -> list[tuple[Path, list[str]]]:
    """Return ``(path, issues)`` for every Markdown file that fails."""

    failures: list[tuple[Path, list[str]]] = []
    for path in markdown_files(paths):
        text = path.read_text(encoding="utf-8")
        report = inventory(text)
        issues = report.issues + page_locality_issues(text)
        if issues:
            failures.append((path, issues))
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Markdown files or directories; defaults to all published document roots.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = args.paths or [ROOT / directory for directory in DEFAULT_DIRECTORIES]
    failures = validate_paths(paths)
    for path, issues in failures:
        print(f"{path.relative_to(ROOT)}")
        for issue in issues:
            print(f"  - {issue}")
    if failures:
        print(f"footnote integrity failed: {len(failures)} file(s)", file=sys.stderr)
        return 1
    print(f"footnote integrity passed: {len(markdown_files(paths))} Markdown file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
