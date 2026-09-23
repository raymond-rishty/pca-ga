#!/usr/bin/env python3
"""Synchronize visible case-page cards from the canonical judicial catalogue.

The case catalogue is one row per docket, while ``cases/*.md`` is one page per
decision.  Several docket rows can therefore point at the same page.  This
stage groups those rows before writing the page heading and metadata line so a
consolidated decision does not inherit whichever docket happened to be listed
first.

Only the card preamble is changed.  The verbatim decision body, source line,
and any extra reviewed metadata (for example a vote or decision date) remain
untouched.

Usage::

    python scripts/84_sync_case_page_metadata.py [ROOT]
    python scripts/84_sync_case_page_metadata.py [ROOT] --check
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path


FINAL_DISPOSITION_LABELS = {
    "sustained": "Sustained",
    "partially_sustained": "Partially sustained",
    "not_sustained": "Not sustained",
    "denied": "Denied",
    "granted": "Granted",
    "guilty": "Guilty",
    "not_guilty": "Not guilty",
    "administratively_out_of_order": "Administratively out of order",
    "judicially_out_of_order": "Judicially out of order",
    "out_of_order": "Out of order (type not stated)",
    "dismissed": "Dismissed",
    "withdrawn": "Withdrawn",
    "abandoned": "Abandoned",
    "moot": "Moot",
    "affirmed": "Affirmed",
    "reversed": "Reversed",
    "vacated": "Vacated",
    "annulled": "Annulled",
    "remanded": "Remanded",
    "referred": "Referred",
    "in_order": "In order",
    "no_final_disposition": "No final disposition in available record",
    "other": "Other",
}

COURT_LABELS = {
    "SJC": "Standing Judicial Commission",
    "CJB": "Committee on Judicial Business (CJB)",
}

CARD_SEPARATOR = "  ·  "
FIELD_RE = re.compile(r"^\*\*(?P<key>[^*]+):\*\*\s*(?P<value>.*)$")
DOCKET_RE = re.compile(r"^(\d{4})-(\d+)([A-Za-z]?)$")


def ordinal(value: int) -> str:
    suffix = "th" if 10 <= value % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def docket_key(value: str) -> tuple:
    match = DOCKET_RE.match(str(value or ""))
    if not match:
        return (10**9, 10**9, str(value or ""))
    return (int(match.group(1)), int(match.group(2)), match.group(3).lower())


def unique(values):
    return list(OrderedDict.fromkeys(value for value in values if value))


def load_groups(root: Path) -> dict[str, list[dict]]:
    source = root / "index" / "judicial_cases.jsonl"
    groups: dict[str, list[dict]] = defaultdict(list)
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            page = row.get("case_page")
            if page:
                groups[page].append(row)
    return dict(groups)


def merged_metadata(rows: list[dict], page: str) -> dict[str, object]:
    rows = sorted(rows, key=lambda row: docket_key(row.get("case_id") or row.get("roster_id")))
    dockets = unique(row.get("case_id") or row.get("roster_id") for row in rows)
    titles = unique(row.get("title") for row in rows)
    courts = unique(COURT_LABELS.get(row.get("body"), row.get("body")) for row in rows)
    assemblies = unique(
        f"{ordinal(int(row['assembly']))} ({row['decision_year']})"
        for row in rows
        if row.get("assembly") is not None and row.get("decision_year") is not None
    )
    if not assemblies:
        volume = re.match(r"^ga(\d+)_([0-9]{4})", page)
        if volume:
            assemblies = [f"{ordinal(int(volume.group(1)))} ({volume.group(2)})"]
    dispositions = unique(
        FINAL_DISPOSITION_LABELS.get(value, value)
        for row in rows
        for value in (row.get("final_dispositions") or [])
    )
    return {
        "dockets": dockets,
        # A shared decision can have different captions. Keep each canonical caption visible.
        "title": "; ".join(titles),
        "court": "; ".join(courts),
        "assembly": "; ".join(assemblies),
        "disposition": "; ".join(dispositions) or "—",
        "dissent": any(row.get("dissent") is True for row in rows),
    }


def parse_card_fields(line: str) -> list[tuple[str, str]]:
    fields = []
    for part in line.split(CARD_SEPARATOR):
        match = FIELD_RE.match(part.strip())
        if match:
            fields.append((match.group("key"), match.group("value")))
    return fields


def card_line(existing: str, metadata: dict[str, object]) -> str:
    current = OrderedDict(parse_card_fields(existing))
    replacements = OrderedDict(
        [
            ("Court", str(metadata["court"])),
            ("Assembly", str(metadata["assembly"])),
            ("Disposition", str(metadata["disposition"])),
        ]
    )
    for key, value in replacements.items():
        current[key] = value

    # Dissent is part of the canonical card metadata. Preserve unrelated reviewed fields such as
    # Vote, Concurrence, and Decision, but remove an obsolete dissent marker when the canonical
    # record no longer has one.
    if metadata["dissent"]:
        current["Dissent"] = "yes"
    else:
        current.pop("Dissent", None)

    order = []
    for preferred in ("Court", "Assembly", "Disposition", "Vote", "Dissent", "Concurrence", "Decision"):
        if preferred in current:
            order.append(preferred)
    order.extend(key for key in current if key not in order)
    return CARD_SEPARATOR.join(f"**{key}:** {current[key]}" for key in order)


def render_page(text: str, metadata: dict[str, object]) -> str:
    lines = text.splitlines()
    content_start = 0
    if lines and lines[0].strip() == "---":
        front_matter_end = next(
            (i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
            None,
        )
        if front_matter_end is not None:
            content_start = front_matter_end + 1
    heading_index = next(
        (
            i
            for i, line in enumerate(lines[content_start : content_start + 40], start=content_start)
            if line.startswith("# ")
        ),
        None,
    )
    if heading_index is None:
        raise ValueError("case page has no leading H1")
    lines[heading_index] = f"# {'/'.join(metadata['dockets'])} — {metadata['title']}"

    card_index = next((i for i, line in enumerate(lines[heading_index + 1:heading_index + 12], heading_index + 1) if "**Court:**" in line), None)
    if card_index is None:
        raise ValueError("case page has no card metadata line")
    newline = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + newline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--check", action="store_true", help="report stale pages without writing")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    groups = load_groups(root)
    stale = []
    missing = []
    for page, rows in sorted(groups.items()):
        target = root / "cases" / f"{page}.md"
        if not target.exists():
            missing.append(page)
            continue
        old = target.read_text(encoding="utf-8")
        try:
            new = render_page(old, merged_metadata(rows, page))
        except ValueError as exc:
            raise SystemExit(f"{target}: {exc}") from exc
        if old != new:
            stale.append(target)
            if not args.check:
                target.write_text(new, encoding="utf-8", newline="\n")

    mode = "would update" if args.check else "updated"
    print(f"{mode} {len(stale)} case-page cards from {len(groups)} canonical page groups")
    if missing:
        print(f"missing {len(missing)} canonical case pages: {' '.join(missing)}", file=sys.stderr)
    if args.check and stale:
        print("stale:", " ".join(path.relative_to(root).as_posix() for path in stale))
    return 1 if missing or (args.check and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
