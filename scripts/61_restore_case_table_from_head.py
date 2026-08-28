#!/usr/bin/env python3
"""Restore a case body from HEAD while replacing one table from corrected minutes."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_file", type=Path)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--phrase", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    case_name = args.case_file.as_posix()
    baseline = subprocess.check_output(["git", "show", f"HEAD:{case_name}"], text=True, encoding="utf-8")
    minutes = Path("markdown/ga50_2023.md").read_text(encoding="utf-8")
    marker = f"<!-- PAGE ga=50 pdf_page={args.page}"
    start = minutes.find(marker)
    if start < 0:
        raise ValueError(f"Page {args.page} not found")
    phrase_at = minutes.rfind(args.phrase, 0, start)
    if phrase_at < 0:
        raise ValueError("Phrase not found before source page marker")
    source_match = re.search(r"<table><tbody>.*?</tbody></table>", minutes[phrase_at:], re.DOTALL)
    if not source_match:
        raise ValueError("No source table found")
    source_table = source_match.group(0)
    case_at = baseline.find(args.phrase)
    if case_at < 0:
        raise ValueError("Phrase not found in HEAD case body")
    target_match = re.search(r"<table><tbody>.*?</tbody></table>", baseline[case_at:], re.DOTALL)
    if not target_match:
        raise ValueError("No table found in HEAD case body")
    begin = case_at + target_match.start()
    end = case_at + target_match.end()
    updated = baseline[:begin] + source_table + baseline[end:]
    if args.apply:
        args.case_file.write_text(updated, encoding="utf-8")
    print(f"{args.case_file}: {'wrote' if args.apply else 'would write'} restored body with page {args.page} table")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
