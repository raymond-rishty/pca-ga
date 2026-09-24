"""Shared normalization for BCO Preliminary Principle citations."""
from __future__ import annotations

import re

ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
    "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13,
    "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18,
    "xix": 19, "xx": 20, "xxi": 21, "xxii": 22, "xxiii": 23,
    "xxiv": 24, "xxv": 25, "xxvi": 26, "xxvii": 27, "xxviii": 28,
    "xxix": 29, "xxx": 30, "xxxi": 31, "xxxii": 32, "xxxiii": 33,
}
WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8,
}

PRELIM_RE = re.compile(
    r"\b(?:BCO\s+)?Preliminary Principles?\s+"
    r"(?:(?:II|2)\s*(?:[-.(]\s*|\s+))?"
    r"(?P<first>[A-Za-z]+|[IVX]+|\d+)"
    r"(?:\s*(?:,|and|&)\s*(?P<second>[A-Za-z]+|[IVX]+|\d+))?",
    re.I,
)
# Uppercase PP is common in RPR headings ("PP 6", "PP II.6"). Keep this
# case-sensitive so ordinary lowercase "pp. 6" page references stay excluded.
PP_RE = re.compile(
    r"\bPP\s+(?:(?:II|2)\s*(?:[-.(]\s*|\s+))?"
    r"(?P<first>[A-Za-z]+|[IVX]+|\d+)"
    r"(?:\s*(?:,|and|&)\s*(?P<second>[A-Za-z]+|[IVX]+|\d+))?"
)
PRELIM_ORDINAL_RE = re.compile(
    r"\b(?P<first>first|second|third|fourth|fifth|sixth|seventh|eighth)"
    r"(?:\s*(?:,|and|&)\s*(?P<second>first|second|third|fourth|fifth|sixth|seventh|eighth))?"
    r"\s+preliminary principles?\b",
    re.I,
)


def number_value(token: str | None) -> int | None:
    if not token:
        return None
    value = token.strip().lower().strip(".,;:()[]")
    if value.isdigit():
        return int(value)
    return WORD_NUM.get(value) or ROMAN.get(value)


def norm_prelim(match: re.Match[str]) -> list[str]:
    values = [number_value(match.group("first")), number_value(match.group("second"))]
    return [f"BCO Preliminary Principle {value}" for value in values if value]


def preliminary_matches(text: str):
    """Yield normalized provision, character start/end, and source match."""
    for pattern in (PRELIM_RE, PP_RE, PRELIM_ORDINAL_RE):
        for match in pattern.finditer(text):
            for provision in norm_prelim(match):
                yield provision, match.start(), match.end(), match


def preliminary_references(text: str) -> list[str]:
    return sorted({provision for provision, *_ in preliminary_matches(text)})
