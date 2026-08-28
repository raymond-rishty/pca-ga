#!/usr/bin/env python3
"""Apply narrow, sticky OCR/layout repairs to the complete minutes sources."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(path: str, fn) -> None:
    p = ROOT / path
    old = p.read_text(encoding="utf-8")
    new = fn(old)
    p.write_text(new, encoding="utf-8")
    print(path)


def repair_ga5_table(text: str) -> str:
    start = text.find("Power of the Presbytery")
    end = text.find("What our BCO emphasizes", start)
    if start >= 0 and end >= 0:
        line_start = text.rfind("\n", 0, start) + 1
        table = '''| **Power of the Presbytery** | **How to exercise the power** |
| --- | --- |
| The Presbytery has power to form a new church" (BCO, p. 18) | by "receiving and approving a petition subscribed to by those persons seeking to be organized into a congregation" (BCO, p. 6). |
| "The Presbytery has power to receive candidates" (BCO, p. 18) | by "the filing their applications... with the dates" (BCO, p. 24). |
| "The Presbytery has power to dissolve pastoral relation" (BCO), p. 18) | "at the request of one or both parties". "But whether the minister or the church initiate the proceedings for the dissolution there shall always a meeting of the congregation called and conducted in the same manner as the call of a pastor" (BCO, pp. 18, 36) |
| "The Presbytery has power to dissolve churches" (BCO, p. 18) | only "at the request of the congregation" (BCO), p. 42). |

'''
        text = text[:line_start] + table + text[end:]
    start = text.find("Date Pastor The power Exercise of power Result")
    if start >= 0:
        table = '''| Date | Pastor | The power | Exercise of power | Result |
| --- | --- | --- | --- | --- |
| 4/76 | Rev. Pyles | dissolved | at the request of both | constitutional |
| 4/77 | Rev. Tiggret | dissolved | at the request of pastor | constitutional |
| 4/77 | Rev. Bulkeley | dissolved | at the request of both parties | constitutional |
| 10/76 | Rev. Kim | dissolved | no request | unconstitutional |'''
        text = text[:start] + table + text[start + len("Date Pastor The power Exercise of power Result"):]
    return text


def main() -> None:
    edit(
        "markdown/ga03_1975.md",
        lambda s: s.replace(
            "Relating to Comp! aint of Messrs Harold L. Webb and Thomas Miller",
            "Relating to Complaint of Messrs Harold L. Webb and Thomas Miller",
        ),
    )
    edit("markdown/ga05_1977.md", repair_ga5_table)


if __name__ == "__main__":
    main()
