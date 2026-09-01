import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class FootnoteFalsePositiveRegressionTests(unittest.TestCase):
    def test_ga48_p826_list_item_and_2000_are_not_footnotes(self) -> None:
        for relative_path in (
            "markdown/ga48_2021.md",
            "cases/ga48_2021__2020-04.md",
            "cases-rebuilt/ga48_2021__2020-04.md",
        ):
            text = read(relative_path)
            self.assertNotRegex(text, r"fn-ga48-p826-n2(?!\d)", relative_path)
            self.assertIn("An investigative committee might hear important testimony", text)
            self.assertIn("2,000 churches", text, relative_path)

    def test_ga26_p111_list_item_is_not_footnote_and_p112_definitions_are_split(self) -> None:
        for relative_path in (
            "markdown/ga26_1998.md",
            "cases/ga26_1998__1997-05.md",
        ):
            text = read(relative_path)
            self.assertNotIn("fn-ga26-p111-n1", text, relative_path)
            self.assertIn("2 Recused, 1 Absent.", text)
            self.assertIn("1. Why do the sun and moon not appear", text)
            for number in range(2, 9):
                footnote_id = f"fn-ga26-p112-n{number}"
                self.assertIn(f"[^{footnote_id}]", text, relative_path)
                self.assertRegex(text, rf"(?m)^\[\^{re.escape(footnote_id)}\]:")

    def test_ga39_contextual_numbers_are_not_footnotes(self) -> None:
        root = read("markdown/ga39_2011.md")
        case_2009 = read("cases/ga39_2011__2009-12_2009-21.md")
        for text in (root, case_2009):
            self.assertNotIn("23 concurring, [^fn-ga39-p533-n1]", text)
            self.assertIn("April 11, 2009[^fn-ga39-p533-n1]", text)

        for relative_path in (
            "markdown/ga39_2011.md",
            "cases/ga39_2011__2010-04.md",
            "cases-rebuilt/ga39_2011__2010-04.md",
        ):
            text = read(relative_path)
            self.assertNotIn("and [^fn-ga39-p589-n2]", text, relative_path)
            self.assertNotIn('Specifications" [^fn-ga39-p602-n9]', text, relative_path)
            self.assertIn("Standards", text)

        for relative_path in (
            "markdown/ga39_2011.md",
            "cases/ga39_2011__2010-16.md",
            "cases-rebuilt/ga39_2011__2010-16.md",
        ):
            text = read(relative_path)
            self.assertIn("Complaint[^fn-ga39-p602-n9]", text, relative_path)

    def test_ga40_roll_call_numbers_are_not_footnotes(self) -> None:
        for relative_path in (
            "markdown/ga40_2012.md",
            "cases/ga40_2012__2010-24.md",
        ):
            text = read(relative_path)
            self.assertIn("6 dissenting, 1 recused, and 1 absent", text, relative_path)
            self.assertNotIn("dissenting, [^fn-ga40-p530-n1]", text, relative_path)
            self.assertIn("accepted as just or Constitutional.[^fn-ga40-p530-n1]", text)


if __name__ == "__main__":
    unittest.main()
