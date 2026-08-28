#!/usr/bin/env python3
"""Restore the GA16 Case 2 commission roster table in the minutes source."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "markdown/ga16_1988.md"

TABLE = '''| Presbytery | Commissioner |
| --- | --- |
| Ascension | RE Leroy Maham |
| Calvary | RE Jimmy Knight |
| Central Georgia | RE John Bailie |
| Covenant | RE John Graves |
| Delmarva | RE John Jardine, Jr. |
| Evangel | RE Thomas Barker |
| Grace | TE James Watson |
| Great Lakes | TE L. Corbett Heimburger |
| Gulf Coast | RE Bill Denton |
| James River | RE Thomas Taylor, Jr. |
| James River | TE Wallace Sherbon |
| Korean Eastern | TE I. Kott |
| Missouri | TE Albert Moginot, Convener |
| Mississippi Valley | TE Daniel Gilchrist |
| Warrior | TE James Reedy |'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    pattern = r"(?s)Members of the Commission: Presbytery Ascension.*?(?=\n### MINUTES OF JUDICIAL COMMISSION #3)"
    if re.search(pattern, text):
        text = re.sub(pattern, TABLE + "\n", text, count=1)
    elif TABLE not in text:
        raise ValueError("GA16 Case 2 roster anchor not found")
    text = text.replace(
        "\n### MINUTES OF JUDICIAL COMMISSION #3",
        "\n<!-- PAGE ga=16 pdf_page=192 printed_page=190 printed_page_source=inferred -->\n\n### MINUTES OF JUDICIAL COMMISSION #3",
        1,
    )
    PATH.write_text(text, encoding="utf-8")
    print(PATH)


if __name__ == "__main__":
    main()
