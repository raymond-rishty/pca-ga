#!/usr/bin/env python3
"""Restore GA9 Case 1 tables in the complete minutes source."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "markdown/ga09_1981.md"

FIRST_TABLE = '''| Elders | Deacons |
| --- | --- |
| A. H. Blackwell | E. A. Buchanan |
| J. W. Elmore | Robert A. Blackwell |
| Robert K. Taylor | Orval Windham |
|  | Cooke Lewis |

| Members | Deacons |
| --- | --- |
| Donna Blackwell | Frances A. Smith |
| Mrs. Robert K. Taylor | Wilton L. Smith |
| Lynn Taylor Thomas | Frances W. Lewis |
| Margaret Bridges | Mrs. John Ward |
| Perry Bridges | Mrs. Daisy Windham |
| Dana Bridges Smith | Lanen Windham |
| Ruth Kyzar | Cooke Lewis, Jr. |
| James O. Kyzar | Pauline P. Blackwell |
| Mrs. B. D. Red, Jr. | John F. Lewis (Deacon) |
| Cindy Red Wilson |  |'''

SECOND_TABLE = '''Members of the Commission who served:

| Teaching Elders | Ruling Elders |
| --- | --- |
| Charles Chase, Evangel | Robert Cato, Mississippi Valley |
| John Harrington, Mississippi Valley | A. H. Gibson, Evangel |
| Tommy Irby, Warrior | William Joseph, Sr., Evangel |
| George Mitchell, Evangel | Charles Miller, Warrior, Alt. |
| Robert Penny, Covenant |  |
| Carl Smith, Central Georgia |  |
| Henry Smith, Evangel, Covener |  |'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    first_pattern = r"(?s)- \*\*A\.\*\* H\. Blackwell.*?(?=\nAdjudicated \$9-76, p\. 150-151)"
    if re.search(first_pattern, text):
        text = re.sub(first_pattern, FIRST_TABLE, text, count=1)
    elif FIRST_TABLE not in text:
        raise ValueError("GA9 first table anchor not found")
    second_pattern = r"(?s)Members of the Commission who served:.*?(?=\n9-77 Judicial Commission)"
    if re.search(second_pattern, text):
        text = re.sub(second_pattern, SECOND_TABLE + "\n", text, count=1)
    elif SECOND_TABLE not in text:
        raise ValueError("GA9 commission table anchor not found")
    PATH.write_text(text, encoding="utf-8")
    print(PATH)


if __name__ == "__main__":
    main()
