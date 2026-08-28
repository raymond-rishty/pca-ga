#!/usr/bin/env python3
"""Back-propagate uniquely matched case heading-level repairs to minutes."""
from __future__ import annotations

import difflib
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^(#{1,6})(\s+)(.+)$")
SOURCE = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?")


def git_text(ref: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True, encoding="utf-8")


def key(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(c for c in value if c.isalnum())


def changed_headings(parent: str, commit: str, path: str) -> list[tuple[str, str, str]]:
    old = git_text(parent, path).splitlines()
    new = git_text(commit, path).splitlines()
    old_map: dict[str, set[str]] = {}
    new_map: dict[str, set[str]] = {}
    for line in old:
        m = HEADING.match(line)
        if m:
            old_map.setdefault(key(m.group(3)), set()).add(m.group(1))
    for line in new:
        m = HEADING.match(line)
        if m:
            new_map.setdefault(key(m.group(3)), set()).add(m.group(1))
    changes = []
    for content, old_levels in old_map.items():
        new_levels = new_map.get(content, set())
        if len(old_levels) == len(new_levels) == 1 and old_levels != new_levels:
            changes.append((content, next(iter(old_levels)), next(iter(new_levels))))
    return changes


def main() -> None:
    commit = "06d6db19"
    parent = f"{commit}^"
    paths = subprocess.check_output(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit, "--", "cases"],
        cwd=ROOT, text=True, encoding="utf-8",
    ).splitlines()
    changed = applied = skipped = 0
    for case_path in paths:
        case_text = git_text(commit, case_path)
        source = SOURCE.search(case_text)
        repairs = changed_headings(parent, commit, case_path)
        if not source or not repairs:
            continue
        minutes_path = ROOT / "markdown" / f"{source.group(1)}.md"
        text = minutes_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        for content, old_level, new_level in repairs:
            candidates = []
            for index, line in enumerate(lines):
                match = HEADING.match(line.rstrip("\r\n"))
                if match and key(match.group(3)) == content:
                    candidates.append(index)
            if len(candidates) != 1:
                skipped += 1
                continue
            index = candidates[0]
            line = lines[index]
            if not line.startswith(old_level):
                continue
            lines[index] = new_level + line[len(old_level):]
            applied += 1
        updated = "".join(lines)
        if updated != text:
            minutes_path.write_text(updated, encoding="utf-8")
            changed += 1
    print({"source_files_changed": changed, "heading_repairs_applied": applied, "ambiguous_or_missing": skipped})


if __name__ == "__main__":
    main()
