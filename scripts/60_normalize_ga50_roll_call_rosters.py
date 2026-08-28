#!/usr/bin/env python3
"""Restore GA50 SJC roll-call rosters to their three-column page layout.

The re-OCR text preserves the names and votes but the semantic renderer can
flatten a roster (and mistake ``M. Duncan`` / ``S. Duncan`` for list items).
This normalizer is deliberately narrow: it only handles a block immediately
following ``Ruling Elders indicated by ... R.`` in the 50th GA minutes.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
from pathlib import Path


MEMBERS = (
    "M. Duncan", "S. Duncan", "Bankson", "Eggert", "Neikirk", "Bise",
    "Cannata", "Carrell", "Coffin", "Donahoe", "Dowling", "Ellis",
    "Garner", "Greco", "Kooistra", "Lee", "Lucas", "McGowan", "Nusbaum",
    "Pickering", "Ross", "Sartorius", "Terrell", "Waters", "White", "Wilson",
    "-- vacant", "vacant",
)
NAME_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(name) for name in MEMBERS) + r")(R)?(?=\s|$)",
    re.IGNORECASE,
)
OUTCOME_RE = re.compile(
    r"(Not Qual\.|Disqualified|Recused|Abstain|Absent|Concur|Dissent)",
    re.IGNORECASE,
)
PAGE_MARKER_RE = re.compile(r"(?:<a id=\"ga50-p\d+\"></a>\n)?<!-- PAGE ga=50 pdf_page=\d+.*?-->\n?", re.DOTALL)
ROSTER_INTRO_RE = re.compile(r"Ruling Elders indicated by (?:an )?R\.", re.IGNORECASE)


def parse_entries(source: str) -> list[tuple[str, str]]:
    """Return normalized (member, outcome) pairs from layout-flattened text."""
    source = re.sub(r"<[^>]+>", " ", source)
    source = re.sub(r"[*_]+", "", source)
    source = re.sub(r"\s+", " ", source).strip()
    matches = list(NAME_RE.finditer(source))
    entries: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        name = match.group(1).replace("-- ", "").strip()
        suffix_r = bool(match.group(2))
        detail = source[match.end():next_start].strip(" -")
        bracket_r = detail.startswith("[R]")
        if bracket_r:
            detail = detail[3:].strip()
        detail = re.sub(r"^R(?=Not Qual\.|Disqualified|Recused|Abstain|Absent|Concur|Dissent)", "R ", detail, flags=re.IGNORECASE)
        prefix_r = bool(re.match(r"^R(?=\s|Not Qual\.|Disqualified|Recused|Abstain|Absent|Concur|Dissent|$)", detail, re.IGNORECASE))
        outcome_match = OUTCOME_RE.search(detail)
        outcome = outcome_match.group(1).title() if outcome_match else ""
        if name.lower() == "vacant":
            outcome = ""
        if suffix_r or prefix_r or bracket_r:
            name += " [R]"
        entries.append((name, outcome))
    return entries


def table(entries: list[tuple[str, str]], *, context: str = "") -> str:
    if not entries:
        raise ValueError(f"Expected roster entries in {context}")
    rows = []
    for offset in range(0, len(entries), 3):
        cells = []
        row_entries = entries[offset:offset + 3]
        for name, outcome in row_entries:
            cells.extend((f"<td>{html.escape(name)}</td>", f"<td>{html.escape(outcome)}</td>"))
        cells.extend("<td></td>" for _ in range((3 - len(row_entries)) * 2))
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table><tbody>" + "".join(rows) + "</tbody></table>"


def roster_end(text: str, start: int) -> int:
    """Find the end of roster-only lines while retaining page markers outside it."""
    position = start
    saw_roster = False
    while position < len(text):
        line_end = text.find("\n", position)
        if line_end < 0:
            line_end = len(text)
        line = text[position:line_end]
        stripped = line.strip()
        if saw_roster and re.match(r"(?:TE|RE|SJC)\s", re.sub(r"<[^>]+>", " ", stripped)):
            return position
        if not stripped or PAGE_MARKER_RE.fullmatch(line + "\n") or stripped.startswith("<a id=\"ga50-p") or stripped.startswith("<!-- PAGE ga=50"):
            position = min(line_end + 1, len(text))
            continue
        plain = re.sub(r"<[^>]+>", " ", line)
        if NAME_RE.search(plain) and (OUTCOME_RE.search(plain) or "vacant" in plain.lower()):
            saw_roster = True
            position = min(line_end + 1, len(text))
            continue
        return position if saw_roster else start
    return position


def normalize(text: str) -> tuple[str, int]:
    cursor = 0
    replacements = 0
    output: list[str] = []
    for intro in ROSTER_INTRO_RE.finditer(text):
        start = intro.end()
        end = roster_end(text, start)
        if end == start:
            continue
        raw = text[start:end]
        # Keep page provenance; normalize each page fragment independently.
        parts = re.split(f"({PAGE_MARKER_RE.pattern})", raw)
        rendered: list[str] = []
        for part in parts:
            if not part:
                continue
            if PAGE_MARKER_RE.fullmatch(part):
                rendered.append(part)
                continue
            entries = parse_entries(part)
            if entries:
                rendered.append("\n\n" + table(entries, context=part[:120]) + "\n")
            else:
                rendered.append(part)
        output.append(text[cursor:start])
        output.append("".join(rendered))
        cursor = end
        replacements += 1
    output.append(text[cursor:])
    return repair_known_layout_omissions("".join(output)), replacements


def repair_known_layout_omissions(text: str) -> str:
    """Restore roster rows omitted by the pre-layout Markdown renderer.

    These two rows sets come from the positioned Paddle OCR records for pages
    833 and 844.  The original Markdown had retained only their final rows.
    """
    klett_entries = [
        ("Bankson", "Concur"), ("Eggert [R]", "Concur"), ("Neikirk [R]", "Concur"),
        ("Bise [R]", "Concur"), ("Ellis", "Concur"), ("Pickering [R]", "Concur"),
        ("Carrell [R]", "Concur"), ("Garner", "Absent"), ("Ross", "Concur"),
        ("Coffin", "Concur"), ("Greco", "Concur"), ("Sartorius", "Concur"),
        ("Donahoe [R]", "Concur"), ("Kooistra", "Concur"), ("Terrell [R]", "Concur"),
        ("Dowling [R]", "Concur"), ("Lee", "Concur"), ("Waters", "Concur"),
        ("M. Duncan [R]", "Concur"), ("Lucas", "Concur"), ("White [R]", "Absent"),
        ("S. Duncan [R]", "Concur"), ("McGowan", "Concur"), ("Wilson [R]", "Concur"),
    ]
    sheppard_tail = [
        ("Donahoe [R]", "Dissent"), ("Kooistra", "Recused"), ("Terrell [R]", "Recused"),
        ("Dowling [R]", "Concur"), ("Lee", "Concur"), ("Waters", "Recused"),
        ("M. Duncan [R]", "Concur"), ("Lucas", "Concur"), ("White [R]", "Concur"),
        ("S. Duncan [R]", "Dissent"), ("McGowan", "Concur"), ("Wilson [R]", "Dissent"),
    ]
    michelson_entries = [
        ("Bankson", "Concur"), ("Eggert [R]", "Concur"), ("Neikirk [R]", "Concur"),
        ("Bise [R]", "Concur"), ("Ellis", "Concur"), ("Pickering [R]", "Concur"),
        ("Carrell [R]", "Concur"), ("Garner", "Concur"), ("Ross", "Concur"),
        ("Coffin", "Concur"), ("Greco", "Concur"), ("Sartorius", "Concur"),
        ("Donahoe [R]", "Concur"), ("Kooistra", "Concur"), ("Terrell [R]", "Concur"),
        ("Dowling [R]", "Concur"), ("Lee", "Concur"), ("Waters", "Concur"),
        ("M. Duncan [R]", "Concur"), ("Lucas", "Absent"), ("White [R]", "Concur"),
        ("S. Duncan [R]", "Concur"), ("McGowan", "Concur"), ("Wilson [R]", "Concur"),
    ]
    klett_pattern = re.compile(
        r"(The Panel's Proposed Decision was written by RE Frederick \(Jay\) Neikirk.*?Ruling Elders indicated by R\.\n\n)<table><tbody>.*?</tbody></table>",
        re.DOTALL,
    )
    text, count = klett_pattern.subn(r"\1" + table(klett_entries), text, count=1)
    if count != 1:
        raise ValueError("Could not locate the Klett roster for layout recovery")
    sheppard_pattern = re.compile(
        r"(<a id=\"ga50-p844\"></a>\n<!-- PAGE ga=50 pdf_page=844 printed_page=836 -->\n\n)\s*<table><tbody>.*?</tbody></table>",
        re.DOTALL,
    )
    text, count = sheppard_pattern.subn(r"\1" + table(sheppard_tail), text, count=1)
    if count != 1:
        raise ValueError("Could not locate the Sheppard roster continuation for layout recovery")
    michelson_pattern = re.compile(
        r"(This Decision was recommended by the SJC Officers and the SJC approved the Decision by vote of 23-0 on the following roll call vote\. Ruling Elders indicated by R\.)\n\n.*?"
        r"(<a id=\"ga50-p860\"></a>\n<!-- PAGE ga=50 pdf_page=860 printed_page=852 -->)\n\n- \*\*M\.\*\* Duncan R Concur Lucas Absent WhiteR Concur\n- \*\*S\.\*\* Duncan R Concur McGowan Concur WilsonR Concur\n",
        re.DOTALL,
    )
    text, count = michelson_pattern.subn(r"\1\n\n\2\n\n\n" + table(michelson_entries), text, count=1)
    if count not in (0, 1):
        raise ValueError("Found multiple Michelson roster candidates for layout recovery")
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--file", type=Path, default=Path("markdown/ga50_2023.md"))
    parser.add_argument("--from-git-ref", help="Regenerate from this Git revision, e.g. HEAD")
    args = parser.parse_args()
    if args.from_git_ref:
        original = subprocess.check_output(
            ["git", "show", f"{args.from_git_ref}:{args.file.as_posix()}"], text=True, encoding="utf-8"
        )
    else:
        original = args.file.read_text(encoding="utf-8")
    updated, count = normalize(original)
    if not count:
        raise SystemExit("No GA50 roll-call rosters found")
    print(f"Would normalize {count} GA50 roll-call roster(s).")
    if args.apply:
        args.file.write_text(updated, encoding="utf-8")
        print(f"Updated {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
