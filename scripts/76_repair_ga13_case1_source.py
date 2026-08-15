#!/usr/bin/env python3
"""Restore GA13 Case 1 commission tables in the minutes source."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "markdown/ga13_1985.md"

MEMBERS = '''| **Teaching Elders** | **Ruling Elders** |
| --- | --- |
| Robert Auffarth, Delmarva, Chairman | Clark Breeding, North Texas |
| David Brown, Pacific | Donald Comer, Central Georgia |
| Stephen Bostrom, Calvary | Gary Flye, Southwest |
| Robert (Ric) Cannada, Covenant | Eugene Friedline, James River |
| Fred Marsh, Miss. Valley, Secretary | Robert Hezlep, Evangel |
| Henry Mueller, Gulf Coast | Charles LeSuer, Ascension |
| A. Randy Nabors, Tennessee Valley | Jerry Neas, Westminster |
| John Pickett, Pacific Northwest | Robert Swierzb, Great Lakes |'''

COMMISSIONERS = '''| **Presbytery** | **Commissioner** |
| --- | --- |
| Ascension | RE Charles LeSuer |
| Calvary | TE Stephen Bostrom |
| Central Georgia | RE Donald Comer |
<!-- PAGE ga=13 pdf_page=132 printed_page=130 printed_page_source=inferred -->

| Central Georgia | TE John Pickett |
| --- | --- |
| Covenant | TE Robert (Ric) Cannada |
| Delmarva | TE Robert Auffarth, Chairman |
| Evangel | RE Robert Hezlep |
| Great Lakes | RE Robert Swierzb |
| Gulf Coast | TE Henry Mueller |
| Mississippi Valley | TE Frederick Marsh, Secretary |
| North Texas | RE Clark Breeding |
| Southwest | RE Gary Flye |
| Tennessee Valley | RE Randy Nabors |
| Westminster | RE Jerry Neas |
| **Alternates** |  |
| James River | RE Eugene Friedline |
| Pacific | TE David Brown |
| Philadelphia | TE Carl Derk |'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    members = r"(?s)### Members of the Commission:\s+Teaching Elders Ruling Elders.*?(?=\nThe following requested)"
    commissioners = r"(?s)The following Commissioners were present:\s+Presbytery Ascension.*?(?=\nRobert Auffarth was elected)"
    if re.search(members, text):
        text = re.sub(members, "### Members of the Commission:\n\n" + MEMBERS, text, count=1)
    if re.search(commissioners, text):
        text = re.sub(commissioners, "The following Commissioners were present:\n\n" + COMMISSIONERS + "\n", text, count=1)
    if MEMBERS not in text or COMMISSIONERS not in text:
        raise ValueError("GA13 Case 1 table anchors not repaired")
    PATH.write_text(text, encoding="utf-8")
    print(PATH)


if __name__ == "__main__":
    main()
