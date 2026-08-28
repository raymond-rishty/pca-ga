#!/usr/bin/env python3
"""Apply reviewed, deterministic repairs to the first early-GA case files."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(path: str, fn) -> None:
    p = ROOT / path
    old = p.read_text(encoding="utf-8")
    new = fn(old)
    p.write_text(new, encoding="utf-8")
    print(path)


def between(text: str, start: str, end: str) -> str:
    a = text.find(start)
    if a < 0:
        return text
    b = text.find(end, a)
    if b < 0:
        raise ValueError(f"missing end anchor after {start!r}")
    return text[:a] + text[b:]


def main() -> None:
    edit("cases/ga03_1975__case1.md", lambda s: s.replace("Comp! aint", "Complaint"))
    edit(
        "cases/ga04_1976__case1.md",
        lambda s: between(s, "### 4-13 Complaint of Eastland Church against Covenant Presbytery", "<!-- PAGE ga=4 pdf_page=72"),
    )
    def repair_ga4_case2(s: str) -> str:
        s = between(s, "<!-- PAGE ga=4 pdf_page=54", "<!-- PAGE ga=4 pdf_page=71")
        marker = "<!-- PAGE ga=4 pdf_page=71"
        a = s.find(marker)
        b = s.find("### 4-64 Complaint of Eastland Church versus Covenant Presbytery", max(a, 0))
        if b < 0:
            raise ValueError("GA4 case 2 judgment anchors not found")
        if a < 0:
            return s[:b] + "<!-- PAGE ga=4 pdf_page=71 printed_page=69 -->\n\n" + s[b:]
        line_end = s.find("\n", a)
        return s[:a] + s[a:line_end + 1] + s[b:]

    edit("cases/ga04_1976__case2.md", repair_ga4_case2)
    edit(
        "cases/ga05_1977__case1.md",
        lambda s: between(s, "### 5-14 Complaint No. 2 of the Texas.", "<!-- PAGE ga=5 pdf_page=92"),
    )

    def repair_ga5_case2(s: str) -> str:
        # The first table is a two-column comparison; PP-Structure/main
        # confirm that each row has a multi-line right-hand cell.
        start = s.find("| **| **Power of the Presbytery**")
        if start < 0:
            start = s.find("| **Power of the Presbytery**")
        if start >= 0:
            start = s.rfind("\n", 0, start) + 1
        end = s.find("What our BCO emphasizes", start)
        if start >= 0 and end >= 0:
            table = '''| **Power of the Presbytery** | **How to exercise the power** |
| --- | --- |
| The Presbytery has power to form a new church" (BCO, p. 18) | by "receiving and approving a petition subscribed to by those persons seeking to be organized into a congregation" (BCO, p. 6). |
| "The Presbytery has power to receive candidates" (BCO, p. 18) | by "the filing their applications... with the dates" (BCO, p. 24). |
| "The Presbytery has power to dissolve pastoral relation" (BCO), p. 18) | "at the request of one or both parties". "But whether the minister or the church initiate the proceedings for the dissolution there shall always a meeting of the congregation called and conducted in the same manner as the call of a pastor" (BCO, pp. 18, 36) |
| "The Presbytery has power to dissolve churches" (BCO, p. 18) | only "at the request of the congregation" (BCO), p. 42). |

'''
            s = s[:start] + table + s[end:]
        if "| **Power of the Presbytery** |" not in s:
            raise ValueError("first GA5 case 2 table not repaired")
        old = "Date Pastor The power Exercise of power Result 4/76 Rev. Pyles dissolved at the request of both constitutional 4/77 Rev. Tiggret dissolved at the request of pastor constitutional 4/77 Rev. Bulkeley dissolved at the request of both parties constitutional 10/76 Rev. Kim dissolved no request unconstitutional"
        new = '''| Date | Pastor | The power | Exercise of power | Result |
| --- | --- | --- | --- | --- |
| 4/76 | Rev. Pyles | dissolved | at the request of both | constitutional |
| 4/77 | Rev. Tiggret | dissolved | at the request of pastor | constitutional |
| 4/77 | Rev. Bulkeley | dissolved | at the request of both parties | constitutional |
| 10/76 | Rev. Kim | dissolved | no request | unconstitutional |'''
        if old in s:
            s = s.replace(old, new, 1)
        if "| Date | Pastor | The power |" not in s:
            raise ValueError("second GA5 case 2 table not repaired")
        return s

    edit("cases/ga05_1977__case2.md", repair_ga5_case2)


if __name__ == "__main__":
    main()
