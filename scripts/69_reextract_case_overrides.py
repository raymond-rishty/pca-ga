#!/usr/bin/env python3
"""Rebuild audited case pages from pinned spans in the source minutes.

This narrowly scoped layer repairs case boundaries that the historical bulk
extractors cannot reproduce reliably.  It refuses to run when a source hash or
an expected case-specific phrase has changed.  Dry-run validation is the
default; pass ``--apply`` to write the listed case pages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES = ROOT / "index" / "case_extraction_overrides.json"
ANCHOR = re.compile(r'<a id="[^"]*"></a>\s*')


def load_overrides(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Extraction overrides must be a JSON array")
    return rows


def source_text(row: dict) -> tuple[Path, list[str]]:
    path = ROOT / "markdown" / f"{row['vol']}.md"
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != row["source_sha256"]:
        raise ValueError(f"Source hash changed for {row['vol']}: {actual}")
    return path, data.decode("utf-8").splitlines()


def extract(row: dict) -> tuple[str, str]:
    source, lines = source_text(row)
    parts = []
    labels = []
    for start, end in row["spans"]:
        if start < 1 or end < start or end > len(lines):
            raise ValueError(f"Invalid span {start}-{end} for {row['file']}")
        parts.append("\n".join(lines[start - 1:end]).strip())
        labels.append(f"{start}–{end}")
    body = ANCHOR.sub("", "\n\n*— — —*\n\n".join(parts)).strip()
    for phrase in row.get("assertions", []):
        if phrase not in body:
            raise ValueError(f"Expected phrase missing from {row['file']}: {phrase}")
    return body, "; ".join(labels)


def render(row: dict) -> str:
    body, spans = extract(row)
    header = f"**Court:** {row['court']}  ·  **Assembly:** {row['assembly']}"
    if row.get("disposition"):
        header += f"  ·  **Disposition:** {row['disposition']}"
    if row.get("dissent"):
        header += "  ·  **Dissent:** yes"
    lead = []
    if row.get("sparse"):
        lead = [
            "*No separate merits opinion was published; the Assembly disposed of this matter as recorded below.*",
            "",
        ]
    content = [
        f"# {row['title']}", "", header, "",
        f"*Source: [{row['vol']} lines {spans}](../markdown/{row['vol']}.md)*", "",
        *lead, "---", "", body, "", "---", "",
        "[← Judicial case index](../index/CASES.md)", "",
    ]
    return "\n".join(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = load_overrides(args.overrides)
    seen = set()
    changed = 0
    for row in rows:
        if row["file"] in seen:
            raise ValueError("Duplicate target file: " + row["file"])
        seen.add(row["file"])
        rendered = render(row)
        target = ROOT / "cases" / f"{row['file']}.md"
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current != rendered:
            changed += 1
            if args.apply:
                target.write_text(rendered, encoding="utf-8", newline="\n")
    print(json.dumps({
        "validated": len(rows), "changed": changed, "applied": changed if args.apply else 0,
    }, indent=2))


if __name__ == "__main__":
    main()
