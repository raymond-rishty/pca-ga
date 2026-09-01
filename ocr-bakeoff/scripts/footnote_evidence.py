"""Deterministic footnote evidence extraction from PDF, OCR, and layout artifacts.

This is deliberately an evidence collector rather than a renderer.  It keeps
the observations that support a marker/note association and leaves the final
rendering decision to a later, auditable stage.

The native-PDF path is strongest for born-digital pages.  The Paddle path is a
high-recall fallback for scans: Paddle often merges an inline marker into a
word, so the reported marker box is approximate unless a character-level OCR
source is supplied later.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

import pymupdf


SCHEMA = "pca-ga.footnote-evidence.v1"
SUPERSCRIPT_DIGITS = {
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁰": "0",
}
SUPERSCRIPT_TRANSLATION = str.maketrans(SUPERSCRIPT_DIGITS)
INLINE_DIGITS = re.compile(r"(?<![A-Za-z0-9])([0-9]{1,3})(?![A-Za-z0-9])")
# Paddle often transcribes a raised call as part of the preceding word:
# ``Warfield2``, ``Salary1``, or ``MSP5``.  This is only a lexical witness;
# it is not typography evidence and is promoted only when the value also
# resolves to an explicit note entry.
TRAILING_WORD_DIGITS = re.compile(r"(?<=[A-Za-z])([0-9]{1,3})(?=$|[^A-Za-z0-9])")
SUPERSCRIPT_RUN = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
NOTE_HEADING = re.compile(r"^\s*footnotes?\b", re.IGNORECASE)
EXPLICIT_NOTE_HEADING = re.compile(r"^\s*footnotes?\s*[:.]?\s*$", re.IGNORECASE)
NOTE_SECTION_HEADING = re.compile(r"^\s*notes?\s*[:.]?\s*$", re.IGNORECASE)
SINGULAR_NOTE_HEADING = re.compile(r"^\s*footnote\s+[0-9]{1,3}[.)]?\s*$", re.IGNORECASE)
NOTE_LABEL = re.compile(r"^\s*(?:footnote\s*)?([0-9]{1,3})(?=[.)\s]|$)[.)]?\s*", re.IGNORECASE)
# Scanned footnote columns sometimes lose the separator after the label:
# ``1Review of ...`` / ``2The expense ...``.  Keep this fallback restricted to
# the beginning of a line and to a capitalized note sentence so it cannot turn
# years or ordinary prose digits into note entries.
COLLAPSED_NOTE_LABEL = re.compile(r'^\s*([0-9]{1,3})(?=\s*[A-Z"\'])')
LETTER_NOTE_LABEL = re.compile(r"^\s*([a-z])[.)](?:\s+|$)", re.IGNORECASE)
NUMBERED_LINE = re.compile(r"^\s*([0-9]{1,3})[.)]\s+\S")
COMMA_NOTE_LABEL = re.compile(r'^\s*([0-9]{1,3})(?=,\s*[A-Z"\'])')
PARENTHESIZED_NOTE_LABEL = re.compile(r'^\s*\(([0-9]{1,3})\)(?=\s*[A-Z0-9"\']|$)\s*')
VISION_NOTE_MOTION = re.compile(
    r"^\s*(?:[0-9]{1,3}[.)]?\s*)?"
    r"(?:that\b|the\s+proposed\b|each\s+church\b|add\b|delete\b|"
    r"approve\b|approved\b|adopted\b|appointed\b|be\s+amended\b|"
    r"directed\b|encouraged\b|received\b|recommended\b|reported\b|"
    r"requested\b|resolved\b|noted\b)",
    re.IGNORECASE,
)
PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")
PAGE_MARKER = re.compile(r"^\s*<!--\s*PAGE\s+.*?pdf_page=(\d+)\b.*?-->\s*$", re.IGNORECASE)
SCRIPTURE_CITATION = re.compile(
    r"\b(?:cor|matt|john|heb|rom|gal|eph|phil|col|thess|tim|titus|pet|jude|rev|isa|ps|gen|ex|lev|num|deut|acts)\.\s*"
    r"(?:[ivxlcdm]+|[0-9]+)(?:\.[0-9]+)?\.\s*$",
    re.IGNORECASE,
)
SCRIPTURE_BOOK_PREFIX = re.compile(
    r"\b(?:genesis|exodus|leviticus|numbers|deuteronomy|joshua|judges|ruth|"
    r"samuel|kings|chronicles|ezra|nehemiah|esther|job|psalms?|proverbs|"
    r"ecclesiastes|song|isaiah|jeremiah|lamentations|ezekiel|daniel|hosea|"
    r"joel|amos|obadiah|jonah|micah|nahum|habakkuk|zephaniah|haggai|"
    r"zechariah|malachi|matthew|mark|luke|john|acts|romans|corinthians|"
    r"galatians|ephesians|philippians|colossians|thessalonians|timothy|"
    r"titus|philemon|hebrews|james|peter|jude|revelation)\s*$",
    re.IGNORECASE,
)
SENTENCE_TERMINAL = re.compile(r"[.!?][\"'”’»)\]}]*$")
HEADER_FOOTER_LABELS = {"header", "footer", "page-header", "page-footer", "number"}
FOOTNOTE_LABELS = {"footnote", "vision_footnote"}
NON_TEXT_LAYOUT_LABELS = HEADER_FOOTER_LABELS | {
    "table",
    "table_caption",
    "figure",
    "figure_title",
    "chart",
    "formula",
    "seal",
    "image",
}


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def median(values: Iterable[float], default: float = 0.0) -> float:
    cleaned = [float(value) for value in values if finite(value)]
    return float(statistics.median(cleaned)) if cleaned else default


def as_box(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        values = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if len(values) != 4 or not all(finite(v) for v in values):
        return None
    x0, y0, x1, y1 = values
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def union_box(boxes: Iterable[list[float] | None]) -> list[float] | None:
    valid = [box for box in boxes if box]
    if not valid:
        return None
    return [
        min(box[0] for box in valid),
        min(box[1] for box in valid),
        max(box[2] for box in valid),
        max(box[3] for box in valid),
    ]


def box_height(box: list[float] | None) -> float:
    return max(0.0, (box[3] - box[1])) if box else 0.0


def box_center_y(box: list[float] | None) -> float:
    return (box[1] + box[3]) / 2 if box else 0.0


def coordinate_transform(metadata: dict[str, Any]) -> tuple[float, float]:
    """Return (pixels_per_pdf_point, padding_pixels) for OCR/layout boxes."""
    render = metadata.get("render", {}) if isinstance(metadata, dict) else {}
    dpi = float(render.get("dpi", 0) or 0)
    scale = float(render.get("scale_from_pdf_points", 0) or 0)
    if scale <= 0 and dpi > 0:
        scale = dpi / 72.0
    if scale <= 0:
        scale = 1.0
    return scale, float(render.get("padding_pixels", 0) or 0)


def to_pdf_box(box: Any, metadata: dict[str, Any]) -> list[float] | None:
    value = as_box(box)
    if not value:
        return None
    scale, padding = coordinate_transform(metadata)
    return [
        (value[0] - padding) / scale,
        (value[1] - padding) / scale,
        (value[2] - padding) / scale,
        (value[3] - padding) / scale,
    ]


def inside(inner: list[float] | None, outer: list[float] | None, tolerance: float = 1.5) -> bool:
    if not inner or not outer:
        return False
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def clean_text(text: str) -> str:
    return str(text or "").replace("\u00a0", " ").strip()


def numeric_note_label(text: str) -> re.Match[str] | None:
    """Return a numeric note-label match when the line begins with a number."""
    text = clean_text(text)
    match = (
        NOTE_LABEL.match(text)
        or NUMBERED_LINE.match(text)
        or COMMA_NOTE_LABEL.match(text)
        or PARENTHESIZED_NOTE_LABEL.match(text)
    )
    return match


def note_label_match(text: str) -> re.Match[str] | None:
    """Recognize normal and separator-collapsed labels at a note-line start."""
    return numeric_note_label(text) or COLLAPSED_NOTE_LABEL.match(clean_text(text))


def credible_vision_note_block(block: dict[str, Any]) -> bool:
    """Reject common PP-Structure ``vision_footnote`` mislabels.

    ``vision_footnote`` is a visual layout prediction, not a semantic proof:
    in the corpus it also labels table descriptors and ordinary numbered
    resolutions.  Keep it when it has a leading note label or explicit
    footnote heading, but reject the clearly non-note forms.  Stronger
    ``footnote`` blocks are retained because some long scanned notes begin on
    a continuation line without a visible label.
    """
    if str(block.get("label", "")).lower() != "vision_footnote":
        return True
    text = clean_text(block.get("content", ""))
    if not text:
        return False
    if NOTE_HEADING.match(text):
        return True
    leading = numeric_note_label(text) or COLLAPSED_NOTE_LABEL.match(text)
    if not leading:
        return False
    return not bool(VISION_NOTE_MOTION.match(text))


def numeric_only_parenthesized_reference(text: str) -> bool:
    """Reject wrapped citation tails such as ``582).`` as note labels."""
    return bool(
        re.fullmatch(r"\s*[0-9]{2,3}\)\s*[.;:,)]*\s*", text)
        or re.match(r"\s*[0-9]{2,3}\)\s*(?=[a-z])", text)
    )


def citation_like_context(before: str, after: str = "") -> bool:
    """Recognize common references that resemble an inline footnote number."""
    before = str(before or "")
    after = str(after or "")
    recent = before[-120:]
    if SCRIPTURE_CITATION.search(before):
        return True
    # Full book names are common in scanned prose where the abbreviated
    # ``Gen. 1.`` form is not used.  A bare chapter number after a book name
    # is reference context, not a marker, unless independent superscript or
    # checkpoint evidence later overrides this weak classification.
    if SCRIPTURE_BOOK_PREFIX.search(recent):
        return True
    if re.search(
        r"(?:\b(?:pp?|vol|case|section|fig|art|part|item|question|q)\.?\s*|\b(?:m\d{1,2}|wcf|bco|rao)\s*\.?\s*|[-/:])$",
        before,
        re.IGNORECASE,
    ):
        return True
    # A day in a written date is a frequent false marker: e.g. ``February
    # 1, 2002``.  Treat both the month-before and year-after signals as
    # citation/date context, while leaving a genuine superscript marker after
    # a sentence eligible for the independent typography rule.
    if re.search(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\s*$",
        before,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"^\s*,?\s*(?:1[5-9]\d{2}|20\d{2})\b", after):
        return True
    # Percentages are ordinary prose quantities, not footnote calls.  Paddle
    # often gives the digit an inline approximate box, so the following
    # symbol must be part of the context guard rather than a typography rule.
    if re.match(r"^\s*%", after):
        return True
    if re.search(
        r"\b(?:catechism|confession|westminster|scripture|bco|rao|vote|roll\s+call|appendix|table|figure)\b",
        recent,
        re.IGNORECASE,
    ) and not re.search(r"[.!?][\"'”’»)\]}]*$", before.rstrip()):
        # A flattened scan can place a true footnote call immediately after
        # the period ending a sentence that mentions BCO/Westminster.  Keep
        # the broad keyword guard for numbers inside the sentence, but do not
        # let it hide this narrow sentence-terminal witness.
        return True
    return after.startswith(("-", "/", ":"))


def inline_after_word_context(prefix: str) -> bool:
    """Allow a marker after closing quotes/punctuation attached to a word."""
    text = str(prefix or "").rstrip()
    if not text:
        return False
    if text[-1].isalnum():
        return True
    punctuation = "'\".,;:)]}!?“”‘’"
    if text[-1] not in punctuation:
        return False
    cursor = len(text) - 1
    while cursor >= 0 and (text[cursor] in punctuation or text[cursor].isspace()):
        cursor -= 1
    return cursor >= 0 and text[cursor].isalnum()


def sentence_terminal_context(prefix: str) -> bool:
    """Recognize a marker immediately following a sentence terminator."""
    return bool(SENTENCE_TERMINAL.search(str(prefix or "").rstrip()))


EXPLICIT_NOTE_SOURCES = {"ppstructure", "ppstructure_heading", "ocr_heading"}


def explicit_note_pair(candidate: dict[str, Any], paired: bool) -> bool:
    """Return whether a pair points to a structurally explicit note block."""
    if not paired:
        return False
    for entry in candidate.get("paired_note_entries", []) or []:
        sources = {
            str(entry.get(key, "")).lower()
            for key in ("source", "block_source")
        }
        if sources.intersection(EXPLICIT_NOTE_SOURCES):
            return True
    return False


def terminal_explicit_ocr_marker(candidate: dict[str, Any], paired: bool) -> bool:
    """Recognize an OCR marker at a sentence boundary with an explicit note."""
    return bool(
        candidate.get("source") in {"paddle_ocr", "tesseract_hocr"}
        and explicit_note_pair(candidate, paired)
        and candidate.get("inline_after_word")
        and (
            candidate.get("marker_at_line_end")
            or candidate.get("sentence_terminal_before")
        )
        and not candidate.get("superscript")
        and not candidate.get("citation_like")
    )


def likely_page_number(lines: list[dict[str, Any]], index: int) -> bool:
    """Recognize a centered trailing page number, not a left note label."""
    if index < 0 or index >= len(lines) or not PAGE_NUMBER.fullmatch(clean_text(lines[index].get("text", ""))):
        return False
    # Page numbers are normally the final OCR line and centered.  Numeric-only
    # note labels such as ``124`` and ``128`` are left-indented instead.
    if index != len(lines) - 1:
        return False
    boxes = [line.get("box") for line in lines if line.get("box")]
    box = lines[index].get("box")
    if not boxes or not box:
        return True
    page_left = min(value[0] for value in boxes)
    page_right = max(value[2] for value in boxes)
    page_center = (page_left + page_right) / 2
    line_center = (box[0] + box[2]) / 2
    return abs(line_center - page_center) <= (page_right - page_left) * 0.18


def native_page_evidence(page: pymupdf.Page) -> dict[str, Any]:
    """Extract raw character/span evidence from a PDF page."""
    raw = page.get_text("rawdict")
    lines: list[dict[str, Any]] = []
    all_chars: list[dict[str, Any]] = []
    for block_index, block in enumerate(raw.get("blocks", [])):
        for line_index, line in enumerate(block.get("lines", [])):
            chars: list[dict[str, Any]] = []
            for span_index, span in enumerate(line.get("spans", [])):
                flags = int(span.get("flags", 0) or 0)
                size = float(span.get("size", 0) or 0)
                font = str(span.get("font", ""))
                for char_index, char in enumerate(span.get("chars", [])):
                    text = str(char.get("c", ""))
                    if not text:
                        continue
                    item = {
                        "text": text,
                        "bbox": as_box(char.get("bbox")),
                        "origin": list(char.get("origin", [])) if char.get("origin") else None,
                        "size": size,
                        "flags": flags,
                        "font": font,
                        "superscript": bool(flags & 1) or text in SUPERSCRIPT_DIGITS,
                        "block_index": block_index,
                        "line_index": line_index,
                        "span_index": span_index,
                        "char_index": char_index,
                    }
                    chars.append(item)
                    all_chars.append(item)
            if chars:
                lines.append(
                    {
                        "block_index": block_index,
                        "line_index": line_index,
                        "text": "".join(char["text"] for char in chars),
                        "bbox": as_box(line.get("bbox")),
                        "chars": chars,
                    }
                )

    body_sizes = [
        char["size"]
        for char in all_chars
        if char["text"].strip() and not char["superscript"] and char["size"] > 0
    ]
    body_size = median(body_sizes, 0.0)
    return {
        "lines": lines,
        "char_count": len(all_chars),
        "body_font_size": body_size,
        "superscript_char_count": sum(char["superscript"] for char in all_chars),
        "font_sizes": sorted({round(char["size"], 3) for char in all_chars if char["size"] > 0}),
    }


def native_digit_word_suffix(chars: list[dict[str, Any]], start: int, end: int) -> bool:
    """Recognize a digit run attached to a preceding word in native text."""
    if start <= 0 or end < len(chars) and str(chars[end].get("text", "")).isalnum():
        return False
    cursor = start - 1
    punctuation = "'\".,;:)]}!?’\u201c\u201d\u2018\u2019"
    while cursor >= 0 and str(chars[cursor].get("text", "")) in punctuation:
        cursor -= 1
    if cursor < 0 or not str(chars[cursor].get("text", "")).isalpha():
        return False
    stem_start = cursor
    while stem_start >= 0 and str(chars[stem_start].get("text", "")).isalpha():
        stem_start -= 1
    return cursor - stem_start >= 2


def native_marker_candidates(
    native: dict[str, Any],
    note_boxes: list[list[float]],
    word_suffix_values: set[str] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    body_size = float(native.get("body_font_size", 0) or 0)
    for line in native.get("lines", []):
        chars = line.get("chars", [])
        index = 0
        while index < len(chars):
            char = chars[index]
            normalized = SUPERSCRIPT_DIGITS.get(char["text"], char["text"])
            if len(normalized) != 1 or not normalized.isdigit():
                index += 1
                continue
            run = [char]
            cursor = index + 1
            while cursor < len(chars):
                next_char = chars[cursor]
                next_normalized = SUPERSCRIPT_DIGITS.get(next_char["text"], next_char["text"])
                if len(next_normalized) != 1 or not next_normalized.isdigit():
                    break
                previous_box = as_box(run[-1].get("bbox"))
                next_box = as_box(next_char.get("bbox"))
                if bool(next_char.get("superscript")) != bool(run[-1].get("superscript")):
                    break
                if previous_box and next_box and next_box[0] - previous_box[2] > max(box_height(previous_box), 1.0):
                    break
                run.append(next_char)
                cursor += 1

            bbox = union_box([char.get("bbox") for char in run])
            if any(inside(bbox, note_box) for note_box in note_boxes):
                index = cursor
                continue
            before = "".join(char["text"] for char in chars[:index])
            after = "".join(char["text"] for char in chars[cursor:])
            prefix = before.rstrip()
            previous = prefix[-1:] if prefix else ""
            previous_previous = prefix[-2:-1] if len(prefix) > 1 else ""
            line_start = not prefix
            inline_after_word = inline_after_word_context(before)
            elevated = any(char.get("superscript") for char in run)
            size = median([char.get("size", 0) for char in run], 0.0)
            size_ratio = size / body_size if body_size else None
            candidate = {
                "value": "".join(SUPERSCRIPT_DIGITS.get(char["text"], char["text"]) for char in run),
                "bbox": bbox,
                "source": "pymupdf",
                "line_index": line.get("line_index"),
                "line_text": line.get("text", ""),
                "line_bbox": line.get("bbox"),
                "before_text": before,
                "after_text": after,
                "line_start": line_start,
                "inline_after_word": inline_after_word,
                "attached": bool(previous and not previous.isspace()),
                "sentence_terminal_before": sentence_terminal_context(before),
                "superscript": elevated,
                "citation_like": citation_like_context(before, after),
                "font_size": size,
                "body_font_size": body_size,
                "size_ratio": round(size_ratio, 4) if size_ratio is not None else None,
                "baseline": median([char.get("origin", [0, 0])[1] for char in run], 0.0),
                "flags": sorted({int(char.get("flags", 0)) for char in run}),
                "marker_at_line_end": not any(char.isalnum() for char in after),
            }
            if (
                word_suffix_values
                and candidate["value"] in word_suffix_values
                and native_digit_word_suffix(chars, index, cursor)
            ):
                candidate["word_suffix"] = True
                # Keep real typography in the main evidence stream.  The
                # native_word_suffix flag is reserved for digits that are
                # otherwise ordinary text and therefore need sequence
                # corroboration before admission.
                if not elevated and not (
                    size_ratio is not None and size_ratio <= 0.88
                ):
                    candidate["native_word_suffix"] = True
            # Native digits with no typography/context signal are ordinary text,
            # not useful marker evidence.  An exact attached suffix is a
            # lexical witness only when the caller supplies the values of an
            # explicit note block; sequence corroboration is applied by the
            # page analyzer before it is admitted to the candidate stream.
            if not line_start and (
                elevated
                or (size_ratio is not None and size_ratio <= 0.88)
                or candidate.get("native_word_suffix")
            ):
                candidates.append(candidate)
            index = cursor
    return candidates


def line_words(raw_line: dict[str, Any], evidence: dict[str, Any], index: int, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    words = evidence.get("text_word", []) if isinstance(evidence, dict) else []
    word_boxes = evidence.get("text_word_boxes", []) if isinstance(evidence, dict) else []
    if index >= len(words) or index >= len(word_boxes):
        return []
    result = []
    for token_index, (token, box) in enumerate(zip(words[index], word_boxes[index])):
        result.append({"text": str(token), "bbox": to_pdf_box(box, metadata), "token_index": token_index})
    return result


def approximate_subbox(token_box: list[float] | None, token_text: str, start: int, end: int) -> list[float] | None:
    if not token_box or not token_text:
        return token_box
    length = max(1, len(token_text))
    x0 = token_box[0] + (token_box[2] - token_box[0]) * start / length
    x1 = token_box[0] + (token_box[2] - token_box[0]) * end / length
    return [x0, token_box[1], max(x0, x1), token_box[3]]


def hocr_properties(title: str) -> dict[str, Any]:
    """Parse the small hOCR property vocabulary needed for geometry."""
    result: dict[str, Any] = {}
    for part in str(title or "").split(";"):
        tokens = part.strip().split()
        if not tokens:
            continue
        key = tokens[0]
        if key in {"bbox", "x_bboxes"} and len(tokens) >= 5:
            try:
                result[key] = [float(value) for value in tokens[1:5]]
            except ValueError:
                continue
        elif key == "baseline" and len(tokens) >= 3:
            try:
                result[key] = [float(tokens[1]), float(tokens[2])]
            except ValueError:
                continue
        elif key in {"x_fsize", "x_size", "x_ascenders", "x_descenders"} and len(tokens) >= 2:
            try:
                result[key] = float(tokens[1])
            except ValueError:
                continue
    return result


class HocrParser(HTMLParser):
    """Read hOCR line/word/character spans without requiring an HTML package."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[dict[str, Any]] = []
        self.page_bbox: list[float] | None = None
        self.line: dict[str, Any] | None = None
        self.word: dict[str, Any] | None = None
        self.char: dict[str, Any] | None = None
        self.stack: list[tuple[str, set[str], dict[str, Any] | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set(str(attributes.get("class") or "").split())
        title = str(attributes.get("title") or "")
        props = hocr_properties(title)
        obj: dict[str, Any] | None = None
        if "ocr_page" in classes:
            self.page_bbox = props.get("bbox")
        elif "ocr_line" in classes:
            self.line = {"bbox": props.get("bbox"), "props": props, "words": []}
            obj = self.line
        elif "ocrx_word" in classes and self.line is not None:
            self.word = {"bbox": props.get("bbox") or props.get("x_bboxes"), "props": props, "chars": [], "parts": []}
            obj = self.word
        elif "ocrx_cinfo" in classes and self.word is not None:
            self.char = {"bbox": props.get("bbox") or props.get("x_bboxes"), "props": props, "parts": []}
            obj = self.char
        self.stack.append((tag, classes, obj))

    def handle_data(self, data: str) -> None:
        if self.char is not None:
            self.char.setdefault("parts", []).append(data)
        elif self.word is not None:
            self.word.setdefault("parts", []).append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        _, classes, obj = self.stack.pop()
        if "ocrx_cinfo" in classes and self.char is obj and self.word is not None:
            self.char["text"] = "".join(self.char.get("parts", []))
            self.word.setdefault("chars", []).append(self.char)
            self.char = None
        elif "ocrx_word" in classes and self.word is obj and self.line is not None:
            self.word["text"] = "".join(self.word.get("parts", [])) or "".join(
                str(char.get("text", "")) for char in self.word.get("chars", [])
            )
            self.line.setdefault("words", []).append(self.word)
            self.word = None
        elif "ocr_line" in classes and self.line is obj:
            self.line["text"] = " ".join(
                str(word.get("text", "")) for word in self.line.get("words", []) if word.get("text")
            )
            self.lines.append(self.line)
            self.line = None


def hocr_to_pdf_box(box: Any, dpi: float) -> list[float] | None:
    value = as_box(box)
    scale = float(dpi or 0) / 72.0
    if not value or scale <= 0:
        return None
    return [coordinate / scale for coordinate in value]


def tesseract_box_characters(path: Path, image_height: float, dpi: float) -> list[dict[str, Any]]:
    """Read Tesseract's bottom-left-origin box output as top-left boxes."""
    characters = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        text = fields[0]
        if text in {"", "\\n", "\\r"}:
            continue
        try:
            left, bottom, right, top = (float(value) for value in fields[1:5])
        except ValueError:
            continue
        # Tesseract box coordinates use an origin at the lower-left of the
        # image; hOCR and the rest of this module use an origin at the
        # upper-left.
        box = hocr_to_pdf_box([left, image_height - top, right, image_height - bottom], dpi)
        if box:
            characters.append({"text": text, "bbox": box, "font_size": None, "baseline": None})
    return characters


def attach_box_characters(lines: list[dict[str, Any]], characters: list[dict[str, Any]]) -> None:
    """Attach box-file characters to their nearest hOCR line."""
    for character in characters:
        if not lines:
            break
        box = character.get("bbox")
        if not box:
            continue
        containing = [
            line
            for line in lines
            if line.get("box")
            and min(box[3], line["box"][3]) - max(box[1], line["box"][1]) > -1.0
        ]
        line = min(containing or lines, key=lambda item: abs(box_center_y(box) - box_center_y(item.get("box"))))
        line.setdefault("chars", []).append(character)
    for line in lines:
        line.setdefault("chars", []).sort(key=lambda item: (item.get("bbox", [0, 0, 0, 0])[0], item.get("bbox", [0, 0, 0, 0])[1]))


def hocr_page_evidence(
    path: Path, dpi: float = 300.0, box_path: Path | None = None
) -> dict[str, Any] | None:
    """Load hOCR and optional Tesseract box-file character geometry."""
    if not path.exists():
        return None
    parser = HocrParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    lines: list[dict[str, Any]] = []
    all_char_heights = []
    for raw_line in parser.lines:
        line_box = hocr_to_pdf_box(raw_line.get("bbox"), dpi)
        words = []
        chars = []
        for raw_word in raw_line.get("words", []):
            word_box = hocr_to_pdf_box(raw_word.get("bbox"), dpi)
            word_chars = []
            for raw_char in raw_word.get("chars", []):
                char_box = hocr_to_pdf_box(raw_char.get("bbox"), dpi)
                text = str(raw_char.get("text", ""))
                if not text or not char_box:
                    continue
                item = {
                    "text": text,
                    "bbox": char_box,
                    "font_size": raw_char.get("props", {}).get("x_fsize") or raw_word.get("props", {}).get("x_fsize"),
                    "baseline": raw_line.get("props", {}).get("baseline"),
                }
                word_chars.append(item)
                chars.append(item)
                if not text.isspace():
                    all_char_heights.append(box_height(char_box))
            words.append({"text": str(raw_word.get("text", "")), "bbox": word_box, "chars": word_chars})
        lines.append({"text": str(raw_line.get("text", "")), "box": line_box, "words": words, "chars": chars})
    box_characters = []
    if box_path and box_path.exists() and parser.page_bbox:
        box_characters = tesseract_box_characters(box_path, parser.page_bbox[3], dpi)
        attach_box_characters(lines, box_characters)
        all_char_heights.extend(
            box_height(character.get("bbox"))
            for character in box_characters
            if character.get("text", "").strip() and character.get("bbox")
        )
    return {
        "dpi": float(dpi),
        "lines": lines,
        "body_char_height": median(all_char_heights, 0.0),
        "character_box_count": sum(len(line.get("chars", [])) for line in lines),
        "box_character_count": len(box_characters),
    }


def hocr_marker_candidates(hocr: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract digit runs from hOCR character boxes and estimate elevation/size."""
    lines = []
    candidates = []
    body_height = float(hocr.get("body_char_height", 0) or 0)
    for index, raw_line in enumerate(hocr.get("lines", [])):
        chars = raw_line.get("chars", [])
        line = {"index": index, "text": raw_line.get("text", ""), "box": raw_line.get("box"), "score": None, "words": raw_line.get("words", [])}
        lines.append(line)
        normal_bottoms = [
            char["bbox"][3]
            for char in chars
            if char.get("text", "").strip() and not char.get("text", "").isdigit() and char.get("bbox")
        ]
        baseline_y = median(normal_bottoms, raw_line.get("box", [0, 0, 0, 0])[3] if raw_line.get("box") else 0.0)
        position = 0
        while position < len(chars):
            char = chars[position]
            text = str(char.get("text", ""))
            normalized = SUPERSCRIPT_DIGITS.get(text, text)
            if len(normalized) != 1 or not normalized.isdigit():
                position += 1
                continue
            run = [char]
            cursor = position + 1
            while cursor < len(chars):
                next_char = chars[cursor]
                next_text = str(next_char.get("text", ""))
                next_normalized = SUPERSCRIPT_DIGITS.get(next_text, next_text)
                previous_box = run[-1].get("bbox")
                next_box = next_char.get("bbox")
                if len(next_normalized) != 1 or not next_normalized.isdigit() or (
                    previous_box and next_box and next_box[0] - previous_box[2] > max(box_height(previous_box), 1.0)
                ):
                    break
                run.append(next_char)
                cursor += 1
            bbox = union_box([char.get("bbox") for char in run])
            before = "".join(str(char.get("text", "")) for char in chars[:position])
            after = "".join(str(char.get("text", "")) for char in chars[cursor:])
            previous = before.rstrip()[-1:] if before.rstrip() else ""
            previous_previous = before.rstrip()[-2:-1] if len(before.rstrip()) > 1 else ""
            inline_after_word = inline_after_word_context(before)
            run_height = median([box_height(char.get("bbox")) for char in run], 0.0)
            elevated = any(
                char.get("text") in SUPERSCRIPT_DIGITS
                or (char.get("bbox") and char["bbox"][3] < baseline_y - max(1.0, body_height * 0.12))
                for char in run
            )
            candidate = {
                "value": "".join(SUPERSCRIPT_DIGITS.get(str(char.get("text")), str(char.get("text"))) for char in run),
                "bbox": bbox,
                "source": "tesseract_hocr",
                "line_index": index,
                "line_text": line["text"],
                "line_bbox": line["box"],
                "before_text": before,
                "after_text": after,
                "line_start": not before.strip(),
                "inline_after_word": inline_after_word,
                "attached": inline_after_word,
                "superscript": elevated,
                "font_size": run_height,
                "body_font_size": body_height,
                "size_ratio": round(run_height / body_height, 4) if body_height else None,
                "baseline": baseline_y,
                "character_box_approximate": False,
                "citation_like": citation_like_context(before, after),
                "marker_at_line_end": not any(char.isalnum() for char in after),
            }
            # Box output supplies every ordinary digit too.  Without a
            # reduced/elevated glyph signal, a digit inside a normal word,
            # date, vote total, or citation is not a marker merely because it
            # has a character box.
            if not candidate["line_start"] and (
                candidate["superscript"]
                or (candidate["size_ratio"] is not None and candidate["size_ratio"] <= 0.88)
            ):
                candidates.append(candidate)
            position = cursor
    return lines, candidates


def ocr_marker_candidates(page_json: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metadata = page_json
    evidence = page_json.get("evidence", {})
    lines = []
    candidates = []
    for index, raw_line in enumerate(page_json.get("structured_lines", [])):
        text = str(raw_line.get("text", ""))
        box = to_pdf_box(raw_line.get("box"), metadata)
        words = line_words(raw_line, evidence, index, metadata)
        line = {"index": index, "text": text, "box": box, "score": raw_line.get("score"), "words": words}
        lines.append(line)
        for match in SUPERSCRIPT_RUN.finditer(text):
            value = match.group(0).translate(SUPERSCRIPT_TRANSLATION)
            candidates.append(make_ocr_candidate(line, value, match.start(), match.end(), True))
        for match in INLINE_DIGITS.finditer(text):
            value = match.group(1)
            start, end = match.span(1)
            prefix = text[:start]
            stripped_prefix = prefix.strip()
            line_start = not stripped_prefix
            # A number in a year, hyphenated reference, or colon-delimited
            # citation is retained as weak evidence but explicitly marked.
            before = text[max(0, start - 40):start]
            after = text[end:min(len(text), end + 8)]
            citation_like = citation_like_context(before, after)
            if line_start and not any(char in prefix for char in "([{\"'"):
                # This is more likely a note/list label than an inline marker.
                continue
            token_box = None
            token_text = ""
            char_offset = 0
            for word in words:
                next_offset = char_offset + len(word["text"])
                if char_offset <= start < next_offset or (start == end and char_offset < end <= next_offset):
                    token_box = word.get("bbox")
                    token_text = word.get("text", "")
                    local_start = max(0, start - char_offset)
                    local_end = max(local_start, end - char_offset)
                    token_box = approximate_subbox(token_box, token_text, local_start, local_end)
                    break
                char_offset = next_offset
            candidates.append(
                make_ocr_candidate(
                    line,
                    value,
                    start,
                    end,
                    False,
                    token_box=token_box,
                    citation_like=citation_like,
                )
            )
        for match in TRAILING_WORD_DIGITS.finditer(text):
            value = match.group(1)
            start, end = match.span(1)
            word_prefix = re.search(r"[A-Za-z]+$", text[:start])
            # Single-letter codes such as C1 are common in ordinary body
            # text.  Requiring a two-letter word stem removes that cheap
            # lookalike while preserving names, labels, and abbreviations
            # such as MSP5.
            if not word_prefix or len(word_prefix.group(0)) < 2:
                continue
            before = text[max(0, start - 40):start]
            after = text[end:min(len(text), end + 8)]
            citation_like = citation_like_context(before, after)
            token_box = None
            char_offset = 0
            for word in words:
                next_offset = char_offset + len(word["text"])
                if char_offset <= start < next_offset:
                    token_box = word.get("bbox")
                    token_text = word.get("text", "")
                    local_start = max(0, start - char_offset)
                    local_end = max(local_start, end - char_offset)
                    token_box = approximate_subbox(token_box, token_text, local_start, local_end)
                    break
                char_offset = next_offset
            candidate = make_ocr_candidate(
                line,
                value,
                start,
                end,
                False,
                token_box=token_box,
                citation_like=citation_like,
                word_suffix=True,
            )
            candidates.append(candidate)
    # OCR occasionally detaches a raised call at the right edge of a body
    # line and emits it as a short numeric-only line.  Retain that very
    # narrow continuation shape only when the numeric box overlaps the
    # preceding line's right edge and the preceding line ends a sentence.
    for index, line in enumerate(lines):
        if index == 0:
            continue
        match = re.fullmatch(r"\s*([0-9]{1,3})[.)]?\s*", line["text"])
        previous = lines[index - 1]
        previous_text = str(previous.get("text", "")).rstrip()
        current_box = line.get("box")
        previous_box = previous.get("box")
        if not match or not current_box or not previous_box:
            continue
        horizontal_gap = max(0.0, current_box[0] - previous_box[2])
        horizontal_near = (
            current_box[0] <= previous_box[2] + 14.0
            and current_box[0] >= previous_box[2] - 32.0
        )
        vertical_overlap = min(current_box[3], previous_box[3]) - max(
            current_box[1], previous_box[1]
        )
        if (
            not sentence_terminal_context(previous_text)
            or not horizontal_near
            or horizontal_gap > 14.0
            or vertical_overlap < -2.0
        ):
            continue
        value = match.group(1)
        candidate = make_ocr_candidate(
            line,
            value,
            match.start(1),
            match.end(1),
            False,
            citation_like=citation_like_context(previous_text, ""),
        )
        candidate["split_line_continuation"] = True
        candidate["split_from_line_index"] = previous.get("index")
        candidate["split_from_line_text"] = previous_text
        candidate["inline_after_word"] = True
        candidate["attached"] = True
        candidate["sentence_terminal_before"] = True
        candidates.append(candidate)
    return lines, candidates


def make_ocr_candidate(
    line: dict[str, Any],
    value: str,
    start: int,
    end: int,
    unicode_superscript: bool,
    token_box: list[float] | None = None,
    citation_like: bool = False,
    word_suffix: bool = False,
) -> dict[str, Any]:
    text = line["text"]
    prefix = text[:start]
    previous = prefix[-1:] if prefix else ""
    previous_previous = prefix[-2:-1] if len(prefix) > 1 else ""
    line_start = not prefix.strip()
    inline_after_word = inline_after_word_context(prefix)
    parenthesized_token = bool(
        re.fullmatch(r"\s*\(\s*[0-9]{1,3}\s*\)\s*", text)
    )
    return {
        "value": value,
        "bbox": token_box or line.get("box"),
        "source": "paddle_ocr",
        "line_index": line.get("index"),
        "line_text": text,
        "line_bbox": line.get("box"),
        "before_text": prefix,
        "ocr_score": line.get("score"),
        "line_start": line_start,
        "inline_after_word": inline_after_word,
        "attached": inline_after_word,
        "sentence_terminal_before": sentence_terminal_context(prefix),
        "superscript": unicode_superscript,
        "word_suffix": word_suffix,
        "parenthesized_token": parenthesized_token,
        "citation_like": citation_like,
        "character_box_approximate": token_box is not None,
        "after_text": text[end:],
        "marker_at_line_end": not any(char.isalnum() for char in text[end:]),
    }


def layout_note_blocks(layout_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not layout_json:
        return []
    source_blocks = list(layout_json.get("blocks", []))
    result = []
    for block in source_blocks:
        label = str(block.get("label", "")).lower()
        if label not in FOOTNOTE_LABELS:
            continue
        if not credible_vision_note_block(block):
            continue
        result.append(
            {
                "source": "ppstructure",
                "label": label,
                "order": block.get("order"),
                "bbox": to_pdf_box(block.get("bbox"), layout_json),
                "content": clean_text(block.get("content", "")),
            }
        )
    # PP-Structure sometimes labels a table's explanatory ``NOTES:`` heading
    # as ``vision_footnote`` but leaves the parenthesized note definitions as
    # separate generic text blocks.  Rejoin those physically adjacent blocks
    # only when the heading and labels are both present; this does not reopen
    # ordinary table rows or a standalone ``GENERAL NOTE`` paragraph.
    for heading in source_blocks:
        if str(heading.get("label", "")).lower() != "vision_footnote":
            continue
        heading_text = clean_text(heading.get("content", ""))
        heading_box = as_box(heading.get("bbox"))
        if not heading_box or not NOTE_SECTION_HEADING.match(heading_text):
            continue
        children = []
        for child in source_blocks:
            child_label = str(child.get("label", "")).lower()
            child_text = clean_text(child.get("content", ""))
            child_box = as_box(child.get("bbox"))
            if child is heading or child_label not in {"text", "paragraph", "list_item"}:
                continue
            if not child_box or child_box[1] < heading_box[1] - 4:
                continue
            if child_box[1] > heading_box[1] + 260:
                continue
            if not note_label_match(child_text):
                continue
            children.append(child)
        if not children:
            continue
        ordered_children = sorted(
            children,
            key=lambda child: (
                float((as_box(child.get("bbox")) or [0, 0, 0, 0])[1]),
                float((as_box(child.get("bbox")) or [0, 0, 0, 0])[0]),
            ),
        )
        collected = [heading, *ordered_children]
        result.append(
            {
                "source": "ppstructure_heading",
                "label": "footnote",
                "order": heading.get("order"),
                "bbox": to_pdf_box(union_box([as_box(item.get("bbox")) for item in collected]), layout_json),
                "content": " ".join(clean_text(item.get("content", "")) for item in collected),
            }
        )
    # Some PP-Structure versions call a real numbered note section a generic
    # paragraph title (for example ``SPECIFIC COMMITTEE AND AGENCY NOTES``)
    # rather than assigning the footnote label.  Promote such a heading only
    # when following text blocks actually begin with numeric note labels; a
    # standalone title such as ``GENERAL NOTE`` is not enough.
    ordered = sorted(
        enumerate(source_blocks),
        key=lambda item: (
            float(item[1].get("order", item[0]) or item[0]),
            float((item[1].get("bbox") or [0, 0, 0, 0])[1]),
        ),
    )
    for position, (source_index, block) in enumerate(ordered):
        label = str(block.get("label", "")).lower()
        title = clean_text(block.get("content", ""))
        if label not in {"paragraph_title", "title", "section_header"} or not re.search(r"\bnotes?\b", title, re.IGNORECASE):
            continue
        collected = [block]
        note_blocks = []
        for _, following in ordered[position + 1 :]:
            following_label = str(following.get("label", "")).lower()
            following_text = clean_text(following.get("content", ""))
            if following_label in {"header", "footer", "number", "paragraph_title", "title", "section_header"}:
                break
            if following_label not in {"text", "list_item", "paragraph"}:
                break
            # A generic heading can be followed by an explicit note list and
            # then ordinary minutes actions.  Once note definitions have
            # started, an action-style line such as ``26. That ...`` marks
            # the semantic boundary; do not absorb the action list into the
            # footnote block.
            if note_blocks and VISION_NOTE_MOTION.match(following_text):
                break
            if numeric_note_label(following_text):
                note_blocks.append(following)
                collected.append(following)
                continue
            # A wrapped continuation belongs to the note only after at least
            # one labeled note has been collected.  Stop before unrelated body
            # text when the title has no numeric definitions.
            if note_blocks:
                collected.append(following)
                continue
            break
        if note_blocks:
            result.append(
                {
                    "source": "ppstructure_heading",
                    "label": "footnote",
                    "order": block.get("order"),
                    "bbox": to_pdf_box(union_box([as_box(item.get("bbox")) for item in collected]), layout_json),
                    "content": " ".join(clean_text(item.get("content", "")) for item in collected),
                }
            )
    return result


def layout_trailing_suffixes(layout_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Find sentence-terminal numeric suffixes preserved in text blocks."""
    if not layout_json:
        return []
    result = []
    for index, block in enumerate(layout_json.get("blocks", [])):
        label = str(block.get("label", "")).lower()
        if label not in {"text", "paragraph", "list_item"}:
            continue
        content = clean_text(block.get("content", ""))
        match = re.search(r"([.!?])([0-9]{1,3})\s*$", content)
        if not match or not re.search(r"[A-Za-z]$", content[:match.start(1)].rstrip()):
            continue
        box = to_pdf_box(block.get("bbox"), layout_json)
        if not box:
            continue
        result.append(
            {
                "block_index": index,
                "label": label,
                "value": match.group(2),
                "bbox": box,
                "content": content,
            }
        )
    return result


def layout_inline_value_witness(
    layout_json: dict[str, Any] | None,
    value: str,
    line_box: list[float] | None,
) -> dict[str, Any] | None:
    """Find an explicit body-block occurrence of a wrapped marker value.

    PP-Structure's assembled text can retain a marker after the preceding
    word even when the native text layer starts the marker on the next line.
    Accept only body blocks and require a non-numeric boundary after the
    value; hyphenated/legal numeric codes therefore do not qualify.
    """
    if not layout_json or not line_box:
        return None
    escaped = re.escape(str(value))
    for index, block in enumerate(layout_json.get("blocks", [])):
        label = str(block.get("label", "")).lower()
        if label not in {"text", "paragraph", "abstract"}:
            continue
        block_box = to_pdf_box(block.get("bbox"), layout_json)
        if not block_box or not inside(line_box, block_box, tolerance=5.0):
            continue
        content = clean_text(block.get("content", ""))
        for match in re.finditer(escaped, content):
            before = content[: match.start()]
            after = content[match.end() :]
            if not re.search(r"[A-Za-z.!?\"”’»)\]}]\s*$", before):
                continue
            if after and not re.match(r"(?:\s|[,.;:!?\"”’»)\]}]|[A-Za-z])", after):
                continue
            return {
                "block_index": index,
                "block_label": label,
                "block_bbox": block_box,
                "content": content,
                "before_context": before[-80:],
                "after_context": after[:80],
            }
    return None


def native_line_start_layout_candidates(
    native: dict[str, Any],
    layout_json: dict[str, Any] | None,
    note_boxes: list[list[float]],
    explicit_note_values: set[str],
) -> list[dict[str, Any]]:
    """Recover a native marker wrapped onto the next paragraph line.

    This is deliberately a candidate generator.  Confirmation is deferred to
    ``classify`` and requires a same-page explicit note pair plus sequence
    support from neighboring marker values.
    """
    if not layout_json or not explicit_note_values:
        return []
    body_size = float(native.get("body_font_size", 0) or 0)
    by_block: dict[int, list[dict[str, Any]]] = {}
    for line in native.get("lines", []):
        by_block.setdefault(int(line.get("block_index", 0)), []).append(line)
    candidates: list[dict[str, Any]] = []
    for block_lines in by_block.values():
        block_lines.sort(key=lambda line: int(line.get("line_index", 0)))
        for position, line in enumerate(block_lines):
            chars = line.get("chars", [])
            start = 0
            while start < len(chars) and not str(chars[start].get("text", "")).strip():
                start += 1
            if start >= len(chars):
                continue
            first = SUPERSCRIPT_DIGITS.get(str(chars[start].get("text", "")), str(chars[start].get("text", "")))
            if len(first) != 1 or not first.isdigit():
                continue
            run = [chars[start]]
            cursor = start + 1
            while cursor < len(chars):
                normalized = SUPERSCRIPT_DIGITS.get(
                    str(chars[cursor].get("text", "")), str(chars[cursor].get("text", ""))
                )
                if len(normalized) != 1 or not normalized.isdigit():
                    break
                run.append(chars[cursor])
                cursor += 1
            value = "".join(
                SUPERSCRIPT_DIGITS.get(str(char.get("text", "")), str(char.get("text", "")))
                for char in run
            )
            if value not in explicit_note_values:
                continue
            if cursor < len(chars) and str(chars[cursor].get("text", "")).isalnum():
                continue
            bbox = union_box([char.get("bbox") for char in run])
            line_box = as_box(line.get("bbox"))
            if not bbox or not line_box or any(inside(bbox, box, tolerance=3.0) for box in note_boxes):
                continue
            if position == 0:
                continue
            previous = block_lines[position - 1]
            previous_box = as_box(previous.get("bbox"))
            if not previous_box:
                continue
            vertical_gap = line_box[1] - previous_box[3]
            if vertical_gap < -2.0 or vertical_gap > max(12.0, box_height(previous_box) * 1.5):
                continue
            if abs(line_box[0] - previous_box[0]) > max(24.0, box_height(previous_box) * 2.0):
                continue
            layout_witness = layout_inline_value_witness(layout_json, value, line_box)
            if not layout_witness:
                continue
            size = median([char.get("size", 0) for char in run], 0.0)
            size_ratio = size / body_size if body_size else None
            previous_text = str(previous.get("text", ""))
            candidates.append(
                {
                    "value": value,
                    "bbox": bbox,
                    "source": "pymupdf",
                    "line_text": line.get("text", ""),
                    "line_bbox": line_box,
                    "line_start": True,
                    "inline_after_word": True,
                    "attached": True,
                    "sentence_terminal_before": sentence_terminal_context(previous_text),
                    "superscript": any(char.get("superscript") for char in run),
                    "citation_like": False,
                    "font_size": size,
                    "body_font_size": body_size,
                    "size_ratio": round(size_ratio, 4) if size_ratio is not None else None,
                    "baseline": median([char.get("origin", [0, 0])[1] for char in run], 0.0),
                    "flags": sorted({int(char.get("flags", 0)) for char in run}),
                    "marker_at_line_end": not any(
                        str(char.get("text", "")).isalnum() for char in chars[cursor:]
                    ),
                    "line_start_layout_suffix": True,
                    "layout_suffix_block_index": layout_witness["block_index"],
                    "layout_suffix_content": layout_witness["content"],
                    "line_start_previous_text": previous_text,
                }
            )
    return candidates


def native_visual_continuation_candidates(
    native: dict[str, Any],
    note_boxes: list[list[float]],
    explicit_note_values: set[str],
) -> list[dict[str, Any]]:
    """Recover a raised native marker split into a neighboring text block.

    Some PDFs preserve a superscript/reduced-size call in a separate native
    text block while placing it on the same visual line as the preceding body
    text.  Treat that as a marker witness only when the glyph is immediately
    adjacent to the previous line's right edge, the two line boxes overlap
    vertically, and its value is an explicit note label.  Sequence support is
    still required at classification time.
    """
    if not explicit_note_values:
        return []
    body_size = float(native.get("body_font_size", 0) or 0)
    lines = list(native.get("lines", []))
    candidates: list[dict[str, Any]] = []
    for line in lines:
        chars = line.get("chars", [])
        start = 0
        while start < len(chars) and not str(chars[start].get("text", "")).strip():
            start += 1
        if start >= len(chars):
            continue
        first = SUPERSCRIPT_DIGITS.get(str(chars[start].get("text", "")), str(chars[start].get("text", "")))
        if len(first) != 1 or not first.isdigit():
            continue
        run = [chars[start]]
        cursor = start + 1
        while cursor < len(chars):
            normalized = SUPERSCRIPT_DIGITS.get(
                str(chars[cursor].get("text", "")), str(chars[cursor].get("text", ""))
            )
            if len(normalized) != 1 or not normalized.isdigit():
                break
            previous_box = as_box(run[-1].get("bbox"))
            next_box = as_box(chars[cursor].get("bbox"))
            if bool(chars[cursor].get("superscript")) != bool(run[-1].get("superscript")):
                break
            if previous_box and next_box and next_box[0] - previous_box[2] > max(box_height(previous_box), 1.0):
                break
            run.append(chars[cursor])
            cursor += 1
        value = "".join(
            SUPERSCRIPT_DIGITS.get(str(char.get("text", "")), str(char.get("text", "")))
            for char in run
        )
        if value not in explicit_note_values:
            continue
        if cursor < len(chars) and str(chars[cursor].get("text", "")).isalnum():
            continue
        marker_box = union_box([char.get("bbox") for char in run])
        line_box = as_box(line.get("bbox"))
        if not marker_box or not line_box or any(inside(marker_box, box) for box in note_boxes):
            continue
        size = median([char.get("size", 0) for char in run], 0.0)
        size_ratio = size / body_size if body_size else None
        elevated = any(char.get("superscript") for char in run)
        if not elevated and not (size_ratio is not None and size_ratio <= 0.88):
            continue
        previous_options = []
        for previous in lines:
            if previous is line:
                continue
            previous_box = as_box(previous.get("bbox"))
            if not previous_box or any(inside(previous_box, box) for box in note_boxes):
                continue
            vertical_overlap = min(line_box[3], previous_box[3]) - max(line_box[1], previous_box[1])
            if vertical_overlap < min(box_height(line_box), box_height(previous_box)) * 0.45:
                continue
            horizontal_gap = line_box[0] - previous_box[2]
            if horizontal_gap < -2.0 or horizontal_gap > 14.0:
                continue
            previous_text = str(previous.get("text", "")).rstrip()
            if not previous_text or not inline_after_word_context(previous_text):
                continue
            previous_options.append(
                (
                    abs(box_center_y(line_box) - box_center_y(previous_box)),
                    -previous_box[2],
                    previous,
                )
            )
        if not previous_options:
            continue
        previous = min(previous_options, key=lambda item: (item[0], item[1]))[2]
        previous_box = as_box(previous.get("bbox"))
        if not previous_box:
            continue
        candidates.append(
            {
                "value": value,
                "bbox": marker_box,
                "source": "pymupdf",
                "line_text": line.get("text", ""),
                "line_bbox": line_box,
                "line_start": True,
                "inline_after_word": True,
                "attached": True,
                "sentence_terminal_before": sentence_terminal_context(str(previous.get("text", ""))),
                "superscript": elevated,
                "citation_like": False,
                "font_size": size,
                "body_font_size": body_size,
                "size_ratio": round(size_ratio, 4) if size_ratio is not None else None,
                "baseline": median([char.get("origin", [0, 0])[1] for char in run], 0.0),
                "flags": sorted({int(char.get("flags", 0)) for char in run}),
                "marker_at_line_end": not any(
                    str(char.get("text", "")).isalnum() for char in chars[cursor:]
                ),
                "line_start_visual_continuation": True,
                "visual_previous_text": str(previous.get("text", "")),
                "visual_previous_bbox": previous_box,
                "visual_horizontal_gap": round(line_box[0] - previous_box[2], 4),
            }
        )
    return candidates


def add_layout_suffix_candidates(
    candidates: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    suffixes: list[dict[str, Any]],
    explicit_note_values: set[str],
) -> None:
    """Rejoin OCR-only numeric lines using a same-block text suffix witness."""
    for suffix in suffixes:
        value = str(suffix.get("value"))
        if value not in explicit_note_values:
            continue
        for line in lines:
            text = str(line.get("text", "")).strip()
            box = line.get("box")
            if not re.fullmatch(rf"{re.escape(value)}[.)]?", text) or not inside(
                box, suffix.get("bbox"), tolerance=5.0
            ):
                continue
            if any(
                str(candidate.get("value")) == value
                and candidate.get("line_index") == line.get("index")
                for candidate in candidates
            ):
                continue
            candidate = make_ocr_candidate(
                line,
                value,
                0,
                len(text),
                False,
                citation_like=False,
            )
            candidate["layout_trailing_suffix"] = True
            candidate["layout_suffix_block_index"] = suffix.get("block_index")
            candidate["layout_suffix_content"] = suffix.get("content")
            candidate["inline_after_word"] = True
            candidate["attached"] = True
            candidate["sentence_terminal_before"] = True
            candidates.append(candidate)
            break


def heuristic_note_blocks(
    lines: list[dict[str, Any]],
    excluded_boxes: list[list[float]] | None = None,
    allow_bottom_run: bool = True,
) -> list[dict[str, Any]]:
    """Find explicit footnote headings and dense bottom note runs.

    A title such as ``Footnotes, Glossaries, and Other Paratextual Solutions``
    is not itself a note block.  Treat only exact headings (or ``Footnote 1``)
    as explicit section markers, then use a conservative bottom-run fallback
    for pages whose notes have no heading.
    """
    blocks = []
    excluded_boxes = excluded_boxes or []

    def excluded(line: dict[str, Any]) -> bool:
        return any(inside(line.get("box"), box, tolerance=3.0) for box in excluded_boxes)

    index = 0
    while index < len(lines):
        if excluded(lines[index]):
            index += 1
            continue
        if not (EXPLICIT_NOTE_HEADING.match(lines[index]["text"]) or SINGULAR_NOTE_HEADING.match(lines[index]["text"])):
            index += 1
            continue
        collected = [lines[index]]
        note_lines = []
        if numeric_note_label(lines[index]["text"]):
            note_lines.append(lines[index])
        cursor = index + 1
        while cursor < len(lines):
            if excluded(lines[cursor]):
                cursor += 1
                continue
            text = clean_text(lines[cursor]["text"])
            if not text:
                cursor += 1
                continue
            if likely_page_number(lines, cursor) or (text.isupper() and len(text) >= 8):
                break
            if (EXPLICIT_NOTE_HEADING.match(text) or SINGULAR_NOTE_HEADING.match(text)) and cursor != index:
                break
            collected.append(lines[cursor])
            if numeric_note_label(text) or LETTER_NOTE_LABEL.match(text):
                note_lines.append(lines[cursor])
            cursor += 1
        if note_lines:
            blocks.append(
                {
                    "source": "ocr_heading",
                    "label": "footnote",
                    "order": None,
                    "bbox": union_box([line.get("box") for line in collected]),
                    "content": " ".join(line["text"] for line in collected),
                    "line_indices": [line["index"] for line in collected],
                }
            )
        index = max(cursor, index + 1)

    if not allow_bottom_run:
        return blocks

    # If no explicit heading exists, find a dense run of numbered definitions
    # in the lower part of the page.  Requiring three labels avoids mistaking
    # ordinary numbered paragraphs (for example items 4 and 5 in an appendix)
    # for a note block.
    if lines:
        page_bottom = max((line.get("box") or [0, 0, 0, 0])[3] for line in lines)
        lower_limit = page_bottom * 0.68
        label_indices = [
            pos
            for pos, line in enumerate(lines)
            if line.get("box")
            and line["box"][1] >= lower_limit
            and not excluded(line)
            and not likely_page_number(lines, pos)
            and numeric_note_label(line["text"])
        ]
        # A normal numbered list often has a label on one line and its prose
        # on the following indented line (for example ``1.`` / ``Sabbath
        # observance``).  Footnote OCR generally keeps at least some of the
        # label and prose together.  Require two such inline definitions so a
        # lower-page list cannot manufacture a note block.
        inline_definition_count = 0
        for pos in label_indices:
            text = clean_text(lines[pos]["text"])
            match = numeric_note_label(text)
            remainder = text[match.end() :].strip() if match else ""
            if remainder.strip(" .:)-"):
                inline_definition_count += 1
        if len(label_indices) >= 3 and inline_definition_count >= 2:
            start = min(label_indices)
            end = max(label_indices)
            while end + 1 < len(lines) and not likely_page_number(lines, end + 1):
                end += 1
            collected = lines[start : end + 1]
            blocks.append(
                {
                    "source": "ocr_bottom_run",
                    "label": "footnote",
                    "order": None,
                    "bbox": union_box([line.get("box") for line in collected]),
                    "content": " ".join(line["text"] for line in collected),
                    "line_indices": [line["index"] for line in collected],
                }
            )
    return blocks


def note_entries_near(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return whether two label observations occupy the same physical line."""
    if left.get("block_index") != right.get("block_index"):
        return False
    left_box = as_box(left.get("bbox"))
    right_box = as_box(right.get("bbox"))
    if not left_box or not right_box:
        return True
    vertical = min(left_box[3], right_box[3]) - max(left_box[1], right_box[1])
    height = max(box_height(left_box), box_height(right_box), 1.0)
    return vertical >= -1.0 and abs(box_center_y(left_box) - box_center_y(right_box)) <= height * 0.75


def dedupe_note_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate OCR/PDF labels and prefer a longer native label.

    OCR often reads the beginning of a multi-digit label (``43`` as ``4``),
    while the PDF text layer retains the complete value.  This correction is
    allowed only on the same recognized note block and physical line; it does
    not synthesize a label from a nearby number.
    """
    result: list[dict[str, Any]] = []

    def native(entry: dict[str, Any]) -> bool:
        return str(entry.get("source", "")).lower() == "pymupdf_note_text"

    for entry in entries:
        value = str(entry.get("value", ""))
        replacement_index = None
        skip = False
        for index, existing in enumerate(result):
            existing_value = str(existing.get("value", ""))
            if not note_entries_near(entry, existing):
                continue
            exact = value == existing_value
            longer_current = len(value) > len(existing_value) and value.startswith(existing_value)
            longer_existing = len(existing_value) > len(value) and existing_value.startswith(value)
            correction = native(entry) and not native(existing) and longer_current
            reverse_correction = native(existing) and not native(entry) and longer_existing
            prefix_correction = longer_current or longer_existing
            content_correction = (
                bool(entry.get("content_recovered")) != bool(existing.get("content_recovered"))
                and (exact or (
                    len(value) > len(existing_value) and value.startswith(existing_value)
                ) or (
                    len(existing_value) > len(value) and existing_value.startswith(value)
                ))
            )
            if not (exact or correction or reverse_correction or prefix_correction or content_correction):
                continue
            if (
                (prefix_correction and longer_current)
                or correction
                or (content_correction and not entry.get("content_recovered"))
                or (exact and native(entry) and not native(existing))
            ):
                replacement_index = index
            else:
                skip = True
            break
        if replacement_index is not None:
            result[replacement_index] = entry
        elif not skip:
            result.append(entry)
    return result


def note_entries(
    blocks: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    native_lines: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entries = []
    for block_index, block in enumerate(blocks):
        block_entry_start = len(entries)
        recovered_entries = []
        indices = set(block.get("line_indices", []))
        ocr_scoped_lines = [line for line in lines if line.get("index") in indices] if indices else []
        if not ocr_scoped_lines:
            ocr_scoped_lines = [
                line
                for line in lines
                if line.get("box") and inside(line["box"], block.get("bbox"), tolerance=3.0)
            ]
        scoped_lines = list(ocr_scoped_lines)
        native_scoped = []
        if native_lines:
            native_scoped = [
                line
                for line in native_lines
                if line.get("box") and inside(line["box"], block.get("bbox"), tolerance=3.0)
            ]
            # A PDF text layer can restore a label omitted or truncated by
            # OCR.  Geometry order keeps the sequence physical; assembled
            # block text is not reliable in multi-column pages.
            scoped_lines = sorted(
                [*scoped_lines, *native_scoped],
                key=lambda line: (
                    float((line.get("box") or [0, 0, 0, 0])[1]),
                    float((line.get("box") or [0, 0, 0, 0])[0]),
                    0 if line.get("note_source") else 1,
                ),
            )
        for line_index, line in enumerate(scoped_lines):
            text = clean_text(line.get("text", ""))
            match = note_label_match(text)
            if not match or numeric_only_parenthesized_reference(text):
                continue
            previous_text = (
                clean_text(scoped_lines[line_index - 1].get("text", ""))
                if line_index
                else ""
            )
            # A wrapped page-range tail can begin a line with a number that
            # looks exactly like a note label (for example ``l. 4-`` followed
            # by ``18. Though ...``).  Keep it as page text, not a new note.
            if re.search(
                r"\b(?:p|pp|l|ll|page|pages)\.?\s*\d+\s*[-–—]\s*$",
                previous_text,
                re.IGNORECASE,
            ):
                continue
            remainder = text[match.end() :].strip()
            # PP-Structure may label symbol footnotes as a footnote block but
            # OCR their explanatory prose as ``1 graduate...`` or ``4
            # graduates...``.  In a PP-Structure block, reject an unpunctuated
            # lowercase continuation; true numbered notes normally begin with
            # a capitalized name/sentence or a quoted citation.
            if block.get("source") in {"ppstructure", "ocr_heading"} and remainder and remainder[0].islower():
                continue
            value = match.group(1)
            entry = {
                "value": value,
                "block_index": block_index,
                "source": line.get("note_source") or block.get("source"),
                "block_source": block.get("source"),
                "bbox": line.get("box") or block.get("bbox"),
                "line_index": line.get("index"),
                "text": text,
            }
            first_word = re.match(r"[A-Za-z]+", remainder)
            if first_word and re.search(
                rf"\b\d+\s*[,.-]+\s*{re.escape(value)}\.\s+{re.escape(first_word.group(0))}\b",
                clean_text(block.get("content", "")),
                re.IGNORECASE,
            ):
                entry["sequence_anomaly"] = True
                entry["anomaly_reason"] = "wrapped_citation_range_tail"
            entries.append(entry)
        if not scoped_lines and block.get("content"):
            # Layout-only pages may not retain the OCR line array.  Parse only
            # number-like labels followed by note prose; this fallback is
            # intentionally narrower than general digit extraction.
            for match in re.finditer(r"(?<![A-Za-z0-9])([0-9]{1,3})(?=\s*[A-Z\"'])", block["content"]):
                recovered_entries.append(
                    {
                        "value": match.group(1),
                        "block_index": block_index,
                        "source": block.get("source"),
                        "block_source": block.get("source"),
                        "content_recovered": True,
                        "bbox": block.get("bbox"),
                        "line_index": None,
                        "text": block.get("content", ""),
                    }
                )
        if block.get("content"):
            # A line-level OCR record may retain later labels while collapsing
            # the first label into its prose.  Recover only missing labels at
            # content line starts; the ordinary line parser remains the source
            # of precise geometry whenever it recognized the label.
            existing_values = {
                str(entry["value"])
                for entry in entries
                if entry.get("block_index") == block_index
            }
            content_order = {}
            content_lines = str(block["content"]).splitlines()
            for content_index, raw_line in enumerate(content_lines):
                content_match = note_label_match(clean_text(raw_line))
                if content_match:
                    content_order.setdefault(content_match.group(1), content_index)
            first_existing_order = min(
                (
                    content_order.get(value, 10**6)
                    for value in existing_values
                ),
                default=10**6,
            )
            for content_index, raw_line in enumerate(content_lines):
                text = clean_text(raw_line)
                match = note_label_match(text)
                if not match or numeric_only_parenthesized_reference(text):
                    continue
                value = match.group(1)
                if value in existing_values:
                    continue
                # If OCR already supplied a later line label, only recover a
                # content label that is visibly before it.  This prevents an
                # enumerated list inside a note from being mistaken for a new
                # footnote label.
                if (
                    ocr_scoped_lines
                    and content_index >= first_existing_order
                ):
                    continue
                if native_scoped:
                    native_values = []
                    for entry in entries:
                        if entry.get("block_index") != block_index:
                            continue
                        if entry.get("source") != "pymupdf_note_text":
                            continue
                        try:
                            native_values.append(int(entry["value"]))
                        except (TypeError, ValueError):
                            continue
                    # Content assembled by PP-Structure can contain an
                    # indented numbered list inside an otherwise valid note.
                    # With a native label present, only a missing leading
                    # label is eligible for recovery; later values are kept
                    # out of the note-label stream.
                    if native_values:
                        try:
                            if int(value) >= min(native_values):
                                continue
                        except ValueError:
                            continue
                recovered_entries.append(
                    {
                        "value": value,
                        "block_index": block_index,
                        "source": block.get("source"),
                        "block_source": block.get("source"),
                        "content_recovered": True,
                        "bbox": block.get("bbox"),
                        "line_index": None,
                        "text": text,
                    }
                )
                existing_values.add(value)
        # Preserve the original line-level order.  Content assembled by a
        # layout/OCR adapter is not guaranteed to retain physical order (some
        # blocks interleave lines), so sorting every entry by block content can
        # regress otherwise valid sequences.  Only insert a recovered label
        # before the existing entries when it is visibly a leading label; a
        # recovered label in the middle remains conservative and is checked as
        # an anomaly below.
        block_entries = entries[block_entry_start:]
        content_order: dict[str, int] = {}
        for content_index, raw_line in enumerate(str(block.get("content") or "").splitlines()):
            text = clean_text(raw_line)
            match = note_label_match(text)
            if match:
                content_order.setdefault(match.group(1), content_index)
        if recovered_entries:
            first_existing_order = min(
                (
                    content_order.get(str(entry.get("value")), 10**6)
                    for entry in block_entries
                ),
                default=10**6,
            )
            leading = [
                entry
                for entry in recovered_entries
                if content_order.get(str(entry.get("value")), 10**6) < first_existing_order
            ]
            trailing = [entry for entry in recovered_entries if entry not in leading]
            entries[block_entry_start:] = leading + block_entries + trailing
    # A continuation page can begin a recognized footnote block with lettered
    # subpoints (``a.``, ``b.``, ...), while the next block visibly starts at
    # numeric label 2.  In that narrow, structurally explicit case the first
    # block is the preceding numeric note; retain the inference as auditable
    # evidence instead of silently losing the note block.
    inferred_entries = []
    for block_index, block in enumerate(blocks):
        if str(block.get("label", "")).lower() not in FOOTNOTE_LABELS:
            continue
        block_entries = [entry for entry in entries if entry.get("block_index") == block_index]
        if block_entries or not LETTER_NOTE_LABEL.match(clean_text(block.get("content", ""))):
            continue
        later_values = []
        for entry in entries:
            if entry.get("block_index", -1) <= block_index:
                continue
            try:
                later_values.append(int(entry["value"]))
            except (TypeError, ValueError):
                continue
        if not later_values or min(later_values) <= 1:
            continue
        inferred_entries.append(
            {
                "value": str(min(later_values) - 1),
                "block_index": block_index,
                "source": block.get("source"),
                "block_source": block.get("source"),
                "content_recovered": True,
                "inference_reason": "lettered_subnotes_following_numeric_block",
                "bbox": block.get("bbox"),
                "line_index": None,
                "text": block.get("content", ""),
            }
        )
    if inferred_entries:
        entries = inferred_entries + entries
    entries = dedupe_note_entries(entries)
    # A PP-Structure label can be a stray glyph inside a more reliable native
    # label line (for example OCR reads the native ``5`` line as an isolated
    # ``7``).  Keep that disagreement visible, but prevent the contained
    # non-native fragment from entering the usable note-label sequence.
    for entry in entries:
        if entry.get("source") == "pymupdf_note_text":
            continue
        entry_box = as_box(entry.get("bbox"))
        if not entry_box:
            continue
        for native_entry in entries:
            if native_entry.get("source") != "pymupdf_note_text":
                continue
            if native_entry.get("block_index") != entry.get("block_index"):
                continue
            if str(native_entry.get("value")) == str(entry.get("value")):
                continue
            if inside(entry_box, as_box(native_entry.get("bbox")), tolerance=0.75):
                entry["sequence_anomaly"] = True
                entry["anomaly_reason"] = "contained_non_native_label_conflicts_with_native"
                break
    # OCR can split a multi-digit note label (for example ``124`` followed by
    # a line beginning ``4 Ibid.``).  Preserve the observation, but mark values
    # outside the longest non-decreasing run as anomalous so they cannot create
    # a false link.
    for block_index in {entry["block_index"] for entry in entries}:
        scoped = [entry for entry in entries if entry["block_index"] == block_index]
        label_lefts = [
            float(as_box(entry.get("bbox"))[0])
            for entry in scoped
            if as_box(entry.get("bbox"))
        ]
        if label_lefts:
            base_left = min(label_lefts)
            # Wrapped note prose can begin with a number (``100 TEs`` or a
            # citation page) after the actual label column.  A multi-digit
            # number shifted materially to the right is retained as evidence
            # but marked anomalous; genuine labels stay aligned with the note
            # column.  This is deliberately an anomaly, not a deletion.
            for entry in scoped:
                box = as_box(entry.get("bbox"))
                if (
                    box
                    and len(str(entry.get("value", ""))) >= 2
                    and box[0] > base_left + 8.0
                ):
                    entry["sequence_anomaly"] = True
        numeric = []
        for entry in scoped:
            if entry.get("sequence_anomaly"):
                continue
            try:
                numeric.append((entry, int(entry["value"])))
            except (TypeError, ValueError):
                continue
        if len(numeric) >= 3:
            # A citation in the middle of a note can look like a label when
            # OCR starts the line with its page number: ``52 ... 368 N.W.2d``
            # followed by the real ``53 ...`` label.  Interior spikes are
            # stronger evidence of this error than a global longest-run test.
            local_anomalies = {
                index
                for index in range(1, len(numeric) - 1)
                if numeric[index - 1][1] <= numeric[index + 1][1]
                and not numeric[index - 1][1] <= numeric[index][1] <= numeric[index + 1][1]
            }
            best: list[list[int]] = [[] for _ in numeric]
            for index, (_, value) in enumerate(numeric):
                if index in local_anomalies:
                    continue
                best[index] = [index]
                for previous in range(index):
                    if previous in local_anomalies or not best[previous]:
                        continue
                    if numeric[previous][1] <= value and len(best[previous]) + 1 > len(best[index]):
                        best[index] = best[previous] + [index]
            non_empty = [run for run in best if run]
            keep = set(max(non_empty, key=lambda run: (len(run), -run[0], -run[-1]))) if non_empty else set()
            for index, (entry, _) in enumerate(numeric):
                if index in local_anomalies or index not in keep:
                    entry["sequence_anomaly"] = True
    for entry in entries:
        entry.setdefault("sequence_anomaly", False)
    # PP-Structure may split one physical note across blocks.  Mark an
    # interior numeric spike across those block boundaries as a continuation
    # line too (for example 6, 7, ``42. If ...``, 8), without changing the
    # original entry order.  This complements the per-block sequence check
    # above and prevents a wrapped citation from becoming a new note target.
    numeric = []
    for index, entry in enumerate(entries):
        if entry.get("sequence_anomaly"):
            continue
        try:
            numeric.append((index, int(entry["value"])))
        except (TypeError, ValueError):
            continue
    for position in range(1, len(numeric) - 1):
        previous_index, previous_value = numeric[position - 1]
        current_index, current_value = numeric[position]
        next_index, next_value = numeric[position + 1]
        if (
            previous_value <= next_value
            and not previous_value <= current_value <= next_value
        ):
            entries[current_index]["sequence_anomaly"] = True
    return entries


def augment_note_entries_from_marker_sequences(
    entries: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recover omitted note labels from a corroborated consecutive marker run.

    This is intentionally narrower than general sequence completion.  It
    requires a recognized semantic note block, at least three consecutive
    inline marker values, and at least one value already present in that
    block.  Missing values are retained as sequence-recovered evidence, while
    conflicting non-native labels are retained as anomalies for audit.
    """
    sequence_candidates = [
        candidate
        for candidate in candidates
        if not candidate.get("line_start")
        and (candidate.get("superscript") or candidate.get("inline_after_word"))
        and str(candidate.get("value", "")).isdigit()
    ]
    marker_numbers = sorted({int(candidate["value"]) for candidate in sequence_candidates})
    positions: dict[str, list[tuple[float, float]]] = {}
    for candidate in sequence_candidates:
        bbox = candidate.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        positions.setdefault(str(candidate["value"]), []).append(
            ((float(bbox[1]) + float(bbox[3])) / 2.0, (float(bbox[0]) + float(bbox[2])) / 2.0)
        )
    runs: list[list[int]] = []
    for number in marker_numbers:
        if not runs or number != runs[-1][-1] + 1:
            runs.append([number])
        else:
            runs[-1].append(number)
    runs = [run for run in runs if len(run) >= 3]
    if not runs:
        return entries

    # A numeric run is stronger when the witnesses also occur in reading
    # order.  This rejects a stray body citation such as 3 appearing after
    # genuine 4 and 5 markers, while retaining the 64, 65, 66 progression.
    ordered_runs = []
    for run in runs:
        previous: tuple[float, float] | None = None
        ordered = True
        for value in run:
            options = sorted(positions.get(str(value), []))
            if previous is not None:
                options = [option for option in options if option >= previous]
            if not options:
                ordered = False
                break
            previous = options[0]
        if ordered:
            ordered_runs.append(run)
    runs = ordered_runs
    if not runs:
        return entries

    page_existing_values = {str(entry.get("value")) for entry in entries}

    for block_index, block in enumerate(blocks):
        block_label = str(block.get("label", "")).lower()
        block_source = str(block.get("source", "")).lower()
        if block_label not in FOOTNOTE_LABELS and block_source not in {
            "ppstructure",
            "ppstructure_heading",
            "ocr_heading",
        }:
            continue
        block_entries = [entry for entry in entries if entry.get("block_index") == block_index]
        existing_values = {str(entry.get("value")) for entry in block_entries}
        for run in runs:
            run_values = {str(value) for value in run}
            if not existing_values & run_values:
                continue
            # If every value in the corroborated run is already represented
            # somewhere on the page, there is nothing to recover.  In
            # particular, do not duplicate labels across several note blocks
            # that share the same marker sequence.
            missing_values = [value for value in run if str(value) not in page_existing_values]
            if not missing_values:
                continue
            for entry in block_entries:
                value = str(entry.get("value"))
                if value in run_values or entry.get("source") == "pymupdf_note_text":
                    continue
                entry["sequence_anomaly"] = True
                entry["anomaly_reason"] = "outside_corroborated_marker_sequence"
            for value in missing_values:
                value_text = str(value)
                entries.append(
                    {
                        "value": value_text,
                        "block_index": block_index,
                        "source": "sequence_recovered",
                        "block_source": block.get("source"),
                        "content_recovered": False,
                        "sequence_recovered": True,
                        "bbox": block.get("bbox"),
                        "line_index": None,
                        "text": block.get("content", ""),
                        "sequence_anomaly": False,
                    }
                )
                page_existing_values.add(value_text)
            break
    return entries


def sequence_support(value: str, marker_values: set[str], note_values: set[str]) -> bool:
    try:
        number = int(value)
    except ValueError:
        return False
    neighbors = {str(number - 1), str(number + 1)}
    return bool(neighbors & marker_values and neighbors & note_values)


def score_marker(candidate: dict[str, Any], paired: bool, near_note: bool, sequence: bool) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    if candidate.get("superscript"):
        score += 4
        reasons.append("superscript_or_unicode")
    if candidate.get("size_ratio") is not None and candidate["size_ratio"] <= 0.88:
        score += 2
        reasons.append("reduced_font_size")
    if candidate.get("inline_after_word"):
        score += 2
        reasons.append("inline_after_word")
    if candidate.get("attached"):
        score += 1
        reasons.append("attached_to_text")
    if candidate.get("word_suffix"):
        score += 2
        reasons.append("numeric_word_suffix")
    if candidate.get("parenthesized_token"):
        score += 5
        reasons.append("parenthesized_table_token")
    if candidate.get("split_line_continuation"):
        score += 2
        reasons.append("split_line_continuation")
    if candidate.get("layout_trailing_suffix"):
        score += 2
        reasons.append("layout_trailing_suffix")
    if candidate.get("line_start_layout_suffix"):
        score += 2
        reasons.append("line_start_layout_suffix")
    if candidate.get("line_start_visual_continuation"):
        score += 2
        reasons.append("line_start_visual_continuation")
    if candidate.get("structural_layout_exception"):
        reasons.append("structural_native_superscript_exception")
    if paired:
        score += 4
        reasons.append("matching_note_number")
    if near_note:
        score += 2
        reasons.append("near_footnote_block")
    if sequence:
        score += 2
        reasons.append("sequence_support")
    if candidate.get("citation_like"):
        score -= 2
        reasons.append("citation_like_context")
    if terminal_explicit_ocr_marker(candidate, paired):
        reasons.append("terminal_marker_with_explicit_note")
    if candidate.get("line_start"):
        score -= 5
        reasons.append("line_start")
    if len(str(candidate.get("value", ""))) >= 4:
        score -= 5
        reasons.append("long_numeric_run")
    return score, reasons


def classify(score: int, candidate: dict[str, Any], paired: bool) -> str:
    # A matching number in a footnote block is not enough by itself: it would
    # incorrectly promote vote totals and ordinary numbers near the footer.
    has_marker_shape = bool(
        candidate.get("superscript")
        or candidate.get("inline_after_word")
        or (candidate.get("size_ratio") is not None and candidate["size_ratio"] <= 0.88)
    )
    if candidate.get("citation_like") and not candidate.get("superscript") and not candidate.get("legacy_support"):
        return "ambiguous"
    if terminal_explicit_ocr_marker(candidate, paired):
        return "confirmed"
    if (
        paired
        and candidate.get("line_start_layout_suffix")
        and candidate.get("sequence_support")
        and explicit_note_pair(candidate, paired)
        and not candidate.get("citation_like")
    ):
        return "confirmed"
    if (
        paired
        and candidate.get("line_start_visual_continuation")
        and candidate.get("sequence_support")
        and explicit_note_pair(candidate, paired)
        and not candidate.get("citation_like")
    ):
        return "confirmed"
    geometry_ocr = {"paddle_ocr", "tesseract_hocr"}
    # An unlabeled bottom run is useful discovery evidence, but it is also the
    # exact shape produced by tables and numbered lists when layout detection
    # is absent.  Do not let that heuristic alone promote a scan witness to a
    # confirmed footnote.  Explicit PP-Structure or OCR-heading blocks remain
    # eligible, and native/legacy evidence can still corroborate the result.
    paired_note_entries = candidate.get("paired_note_entries", []) or []
    heuristic_only_pair = (
        paired
        and candidate.get("source") in geometry_ocr
        and paired_note_entries
        and not candidate.get("legacy_support")
        and not explicit_note_pair(candidate, paired)
    )
    if heuristic_only_pair:
        return "candidate" if score >= 4 and has_marker_shape else "ambiguous"
    if candidate.get("source") in geometry_ocr and not paired and not candidate.get("superscript") and not candidate.get("legacy_support"):
        # Current Paddle artifacts are line/word geometry.  Without a paired
        # note or an explicit superscript glyph, an inline digit near a footer
        # is too easily a citation or vote total to promote automatically.
        return "ambiguous"
    if (
        paired
        and candidate.get("source") == "pymupdf"
        and not candidate.get("line_start_visual_continuation")
        and (candidate.get("superscript") or (candidate.get("size_ratio") or 1) <= 0.88)
    ):
        return "confirmed"
    if paired and score >= 9:
        return "confirmed"
    if score >= 4 and has_marker_shape:
        return "candidate"
    return "ambiguous"


def strong_native_structural_marker(
    candidate: dict[str, Any], explicit_note_values: set[str]
) -> bool:
    """Allow only strong native glyphs through a non-table layout exclusion."""
    if candidate.get("source") != "pymupdf":
        return False
    if str(candidate.get("value")) not in explicit_note_values:
        return False
    if candidate.get("citation_like"):
        return False
    if not (
        candidate.get("superscript")
        or (candidate.get("size_ratio") is not None and candidate["size_ratio"] <= 0.88)
    ):
        return False
    return bool(candidate.get("inline_after_word") and candidate.get("marker_at_line_end"))


def analyze_page(
    pdf_page: pymupdf.Page,
    page_json: dict[str, Any] | None,
    layout_json: dict[str, Any] | None,
    hocr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    native = native_page_evidence(pdf_page)
    ocr_lines, ocr_candidates = ocr_marker_candidates(page_json or {}) if page_json else ([], [])
    hocr_lines, hocr_candidates = hocr_marker_candidates(hocr or {}) if hocr else ([], [])
    block_lines = ocr_lines or hocr_lines
    structural_boxes = []
    table_boxes = []
    if layout_json:
        for block in layout_json.get("blocks", []):
            label = str(block.get("label", "")).lower()
            if label not in NON_TEXT_LAYOUT_LABELS:
                continue
            box = to_pdf_box(block.get("bbox"), layout_json)
            if not box:
                continue
            structural_boxes.append(box)
            if label == "table":
                table_boxes.append(box)
    layout_blocks = layout_note_blocks(layout_json)
    # PP-Structure layout is useful negative evidence too.  On a page it has
    # segmented, but not footnote-labeled, body content, an unlabeled bottom
    # numeric run is more likely to be a numbered list/table than a note block.
    # Keep explicit OCR headings available, while reserving the bottom-run
    # fallback for pages without layout evidence.
    blocks = layout_blocks + heuristic_note_blocks(
        block_lines,
        structural_boxes,
        allow_bottom_run=not bool(layout_json),
    )
    # Avoid duplicate block evidence when PP-Structure and an explicit OCR
    # heading describe the same region.
    deduped_blocks: list[dict[str, Any]] = []
    for block in blocks:
        if any(block.get("bbox") and existing.get("bbox") and inside(block["bbox"], existing["bbox"], tolerance=8.0) for existing in deduped_blocks):
            continue
        deduped_blocks.append(block)
    deduped_blocks.sort(
        key=lambda block: (
            float((block.get("bbox") or [0, 0, 0, 0])[1]),
            float((block.get("bbox") or [0, 0, 0, 0])[0]),
            float(block.get("order", 0) or 0),
        )
    )
    note_boxes = [block.get("bbox") for block in deduped_blocks if block.get("bbox")]
    non_table_structural_boxes = [
        box for box in structural_boxes if box not in table_boxes
    ]
    native_note_lines = [
        {**line, "box": line.get("bbox"), "note_source": "pymupdf_note_text"}
        for line in native.get("lines", [])
    ]
    entries = note_entries(deduped_blocks, block_lines, native_lines=native_note_lines)
    explicit_note_values = {
        str(entry["value"])
        for entry in entries
        if str(entry.get("block_source", entry.get("source", ""))).lower()
        in {"ppstructure", "ppstructure_heading", "ocr_heading"}
    }
    add_layout_suffix_candidates(
        ocr_candidates,
        ocr_lines,
        layout_trailing_suffixes(layout_json),
        explicit_note_values,
    )
    native_candidates = native_marker_candidates(
        native,
        note_boxes,
        word_suffix_values=explicit_note_values,
    )
    native_candidates.extend(
        native_line_start_layout_candidates(
            native,
            layout_json,
            note_boxes,
            explicit_note_values,
        )
    )
    native_candidates.extend(
        native_visual_continuation_candidates(
            native,
            note_boxes,
            explicit_note_values,
        )
    )
    # OCR sees note labels and note prose too.  Those digits are definitions,
    # not inline markers; remove them before scoring.
    ocr_candidates = [
        candidate
        for candidate in ocr_candidates
        if not any(
            candidate.get("bbox") and inside(candidate["bbox"], blocked_box, tolerance=3.0)
            for blocked_box in note_boxes + non_table_structural_boxes
        )
    ]
    # Apply structural exclusions to every witness.  In particular, hOCR box
    # output supplies ordinary character boxes inside tables; those boxes must
    # not bypass the same table/header/footer exclusions applied to native and
    # Paddle observations.  A reduced/elevated table glyph is the exception:
    # it is retained only when its value also occurs in an explicit note block.
    def candidate_allowed(candidate: dict[str, Any]) -> bool:
        if any(
            candidate.get("bbox") and inside(candidate["bbox"], blocked_box, tolerance=3.0)
            for blocked_box in note_boxes
        ):
            return False
        if any(
            candidate.get("bbox") and inside(candidate["bbox"], blocked_box, tolerance=3.0)
            for blocked_box in non_table_structural_boxes
        ):
            if not strong_native_structural_marker(candidate, explicit_note_values):
                return False
            candidate["structural_layout_exception"] = True
        if not any(
            candidate.get("bbox") and inside(candidate["bbox"], table_box, tolerance=3.0)
            for table_box in table_boxes
        ):
            if candidate.get("parenthesized_token"):
                return False
            return True
        return bool(
            candidate.get("superscript")
            and str(candidate.get("value")) in explicit_note_values
        ) or bool(
            candidate.get("word_suffix")
            and str(candidate.get("value")) in explicit_note_values
            and not candidate.get("citation_like")
        ) or bool(
            candidate.get("parenthesized_token")
            and str(candidate.get("value")) in explicit_note_values
            and not candidate.get("citation_like")
        )

    base_candidates = [
        candidate
        for candidate in native_candidates + ocr_candidates + hocr_candidates
        if not candidate.get("native_word_suffix") and candidate_allowed(candidate)
    ]
    base_sequence_marker_values = {
        str(candidate["value"])
        for candidate in base_candidates
        if (not candidate.get("line_start") or candidate.get("line_start_visual_continuation"))
        and (candidate.get("superscript") or candidate.get("inline_after_word"))
    }
    native_suffix_candidates = [
        candidate
        for candidate in native_candidates
        if candidate.get("native_word_suffix") and candidate_allowed(candidate)
    ]
    # Admit exact native suffixes one step at a time.  This lets a visible
    # run such as 5, 6, 7 be recovered when OCR supplies 4 and 8 but omits
    # all three native glyphs; each admitted value must still be adjacent to
    # an already observed marker and an explicit note value.
    admitted_suffixes = []
    known_sequence_values = set(base_sequence_marker_values)
    remaining_suffixes = list(native_suffix_candidates)
    while remaining_suffixes:
        next_suffixes = [
            candidate
            for candidate in remaining_suffixes
            if sequence_support(
                str(candidate.get("value")),
                known_sequence_values,
                explicit_note_values,
            )
        ]
        if not next_suffixes:
            break
        admitted_suffixes.extend(next_suffixes)
        known_sequence_values.update(str(candidate.get("value")) for candidate in next_suffixes)
        remaining_suffixes = [
            candidate for candidate in remaining_suffixes if candidate not in next_suffixes
        ]
    native_suffix_candidates = admitted_suffixes
    all_candidates = base_candidates + native_suffix_candidates
    entries = augment_note_entries_from_marker_sequences(entries, deduped_blocks, all_candidates)
    note_values = {
        str(entry["value"])
        for entry in entries
        if not entry.get("sequence_anomaly")
    }
    marker_values = {
        str(candidate["value"])
        for candidate in all_candidates
        if (not candidate.get("line_start") or candidate.get("line_start_visual_continuation"))
        and (candidate.get("superscript") or candidate.get("inline_after_word"))
        and not candidate.get("citation_like")
    }
    sequence_marker_values = {
        str(candidate["value"])
        for candidate in all_candidates
        if (not candidate.get("line_start") or candidate.get("line_start_visual_continuation"))
        and (candidate.get("superscript") or candidate.get("inline_after_word"))
    }
    for candidate in all_candidates:
        candidate["inside_table"] = any(
            candidate.get("bbox") and inside(candidate["bbox"], table_box, tolerance=3.0)
            for table_box in table_boxes
        )
        candidate_box = candidate.get("bbox")
        paired_entries = [entry for entry in entries if entry["value"] == str(candidate["value"])]
        near_note = any(
            candidate_box and block.get("bbox") and abs(box_center_y(candidate_box) - box_center_y(block["bbox"])) <= 200
            for block in deduped_blocks
        )
        paired = bool(paired_entries)
        sequence = paired and sequence_support(
            str(candidate["value"]), sequence_marker_values, note_values
        )
        score, reasons = score_marker(candidate, paired, near_note, sequence)
        candidate["paired_note_entries"] = paired_entries
        candidate["near_note_block"] = near_note
        candidate["sequence_support"] = sequence
        candidate["score"] = score
        candidate["reasons"] = reasons
        candidate["classification"] = classify(score, candidate, paired)
    links = []
    review_links = []
    for candidate in all_candidates:
        for entry in candidate.get("paired_note_entries", []):
            link = {
                "marker_value": candidate["value"],
                "marker_source": candidate["source"],
                "marker_bbox": candidate.get("bbox"),
                "note_bbox": entry.get("bbox"),
                "classification": candidate["classification"],
                "score": candidate["score"],
            }
            (links if candidate["classification"] == "confirmed" else review_links).append(link)
    return {
        "native": {key: value for key, value in native.items() if key != "lines"},
        "hocr": {
            "character_box_count": hocr.get("character_box_count", 0),
            "box_character_count": hocr.get("box_character_count", 0),
            "dpi": hocr.get("dpi"),
        } if hocr else None,
        "blocks": deduped_blocks,
        "note_entries": entries,
        "markers": all_candidates,
        "marker_clusters": [],
        "links": links,
        "review_links": review_links,
    }


def load_scope_records(value: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    """Normalize non-overlapping document/case scopes for page-bounded linking.

    Scope is intentionally supplied separately from the detector because the
    repository's case index can contain overlapping companion-case ranges.
    A page that belongs to more than one supplied scope remains unresolved and
    cannot create a cross-scope link.
    """
    raw_scopes = value.get("scopes", []) if isinstance(value, dict) else value
    if not isinstance(raw_scopes, list):
        raise ValueError("scope JSON must contain a list named 'scopes'")
    scopes = []
    for index, raw in enumerate(raw_scopes):
        if not isinstance(raw, dict):
            raise ValueError(f"scope {index} is not an object")
        scope_id = str(raw.get("id") or raw.get("scope_id") or "").strip()
        start = raw.get("start_page", raw.get("pdf_page_start"))
        end = raw.get("end_page", raw.get("pdf_page_end", start))
        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError):
            raise ValueError(f"scope {index} needs integer start_page/end_page")
        if not scope_id or start < 1 or end < start:
            raise ValueError(f"scope {index} has invalid id or page range")
        scopes.append({"id": scope_id, "start_page": start, "end_page": end})
    return scopes


def apply_scopes(pages: list[dict[str, Any]], scopes: list[dict[str, Any]]) -> None:
    """Attach deterministic scope matches to each selected page."""
    for page in pages:
        number = int(page["page"])
        matches = [
            scope["id"]
            for scope in scopes
            if int(scope["start_page"]) <= number <= int(scope["end_page"])
        ]
        page["scope_ids"] = matches
        page["scope_id"] = matches[0] if len(matches) == 1 else None
        page["scope_resolved"] = len(matches) == 1


def scope_allows(marker_page: dict[str, Any], note_page: dict[str, Any], scoped: bool) -> bool:
    """Allow same-page links by default and cross-page links only within scope."""
    if int(marker_page["page"]) == int(note_page["page"]):
        return True
    if not scoped:
        return False
    return bool(
        marker_page.get("scope_resolved")
        and note_page.get("scope_resolved")
        and marker_page.get("scope_id") == note_page.get("scope_id")
    )


def _marker_sort_key(marker: dict[str, Any], index: int) -> tuple[float, float, int]:
    box = marker.get("bbox") or [float("inf"), float("inf"), 0, 0]
    return (float(box[1]), float(box[0]), index)


def marker_witnesses_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Conservatively recognize two observations of one physical marker."""
    if str(left.get("value")) != str(right.get("value")):
        return False
    a, b = left.get("bbox"), right.get("bbox")
    if not a or not b:
        return False
    vertical = min(a[3], b[3]) - max(a[1], b[1])
    horizontal_gap = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    center_gap = abs(box_center_y(a) - box_center_y(b))
    height = max(box_height(a), box_height(b), 1.0)
    return (vertical > -2.0 and horizontal_gap <= 8.0) or (center_gap <= height and horizontal_gap <= 18.0)


def rebuild_marker_clusters(pages: list[dict[str, Any]]) -> None:
    """Group native/OCR observations without discarding any witness."""
    rank = {"ambiguous": 0, "candidate": 1, "confirmed": 2}
    for page in pages:
        markers = page.get("markers", [])
        groups: list[list[tuple[int, dict[str, Any]]]] = []
        for marker_index, marker in sorted(
            enumerate(markers), key=lambda item: _marker_sort_key(item[1], item[0])
        ):
            for group in groups:
                if any(marker_witnesses_overlap(marker, existing) for _, existing in group):
                    group.append((marker_index, marker))
                    break
            else:
                groups.append([(marker_index, marker)])
        clusters = []
        for index, group in enumerate(groups, start=1):
            cluster_id = f"p{page['page']}-m{index:03d}"
            group_markers = [marker for _, marker in group]
            for marker in group_markers:
                marker["cluster_id"] = cluster_id
            classifications = [marker.get("classification", "ambiguous") for marker in group_markers]
            classification = max(classifications, key=lambda value: rank.get(value, 0))
            reasons = []
            for marker in group_markers:
                for reason in marker.get("reasons", []):
                    if reason not in reasons:
                        reasons.append(reason)
            entries = []
            for marker in group_markers:
                for entry in marker.get("paired_note_entries", []):
                    key = (entry.get("page"), entry.get("value"), tuple(entry.get("bbox") or []))
                    if not any((old.get("page"), old.get("value"), tuple(old.get("bbox") or [])) == key for old in entries):
                        entries.append(entry)
            # The published Markdown is generated from the Paddle line text.
            # Preserve one representative line/context witness in the compact
            # link so the application pass can locate the marker after OCR and
            # layout processing, without trying to recover a character offset
            # from PDF geometry alone.
            representative = next(
                (
                    marker
                    for marker in group_markers
                    if marker.get("source") == "paddle_ocr"
                ),
                group_markers[0],
            )
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "value": str(group_markers[0].get("value")),
                    "bbox": union_box([marker.get("bbox") for marker in group_markers]),
                    "classification": classification,
                    "score": max(int(marker.get("score", 0)) for marker in group_markers),
                    "reasons": reasons,
                    "sources": sorted({str(marker.get("source")) for marker in group_markers}),
                    "witness_count": len(group_markers),
                    "witness_indices": [marker_index for marker_index, _ in group],
                    "marker_source": representative.get("source"),
                    "marker_line_index": representative.get("line_index"),
                    "marker_line_text": representative.get("line_text", ""),
                    "marker_before_text": representative.get("before_text", ""),
                    "marker_after_text": representative.get("after_text", ""),
                    "paired_note_entries": entries,
                }
            )
        page["marker_clusters"] = clusters


def resolve_document(
    pages: list[dict[str, Any]],
    note_page_window: int = 2,
    scopes: list[dict[str, Any]] | None = None,
) -> None:
    """Resolve marker/note links across adjacent pages in a fixed window.

    A footnote definition commonly starts on the next page when the marker is
    near the bottom of a page.  Pairing is exact on the normalized number and
    bounded by ``note_page_window``; cross-page pairing additionally requires
    an explicit uniquely resolved scope so an unrelated later note cannot
    silently satisfy a marker.
    """
    scoped = scopes is not None
    if scoped:
        apply_scopes(pages, scopes or [])
    page_by_number = {int(page["page"]): page for page in pages}
    note_records = [
        {"page": page["page"], **entry}
        for page in pages
        for entry in page.get("note_entries", [])
    ]
    marker_values = {
        str(marker.get("value"))
        for page in pages
        for marker in page.get("markers", [])
        if (not marker.get("line_start") or marker.get("line_start_visual_continuation"))
        and (marker.get("superscript") or marker.get("inline_after_word"))
        and not marker.get("citation_like")
    }
    sequence_marker_values = {
        str(marker.get("value"))
        for page in pages
        for marker in page.get("markers", [])
        if (not marker.get("line_start") or marker.get("line_start_visual_continuation"))
        and (marker.get("superscript") or marker.get("inline_after_word"))
    }
    note_values = {str(entry["value"]) for entry in note_records if not entry.get("sequence_anomaly")}
    for page in pages:
        page_blocks = [block for block in page.get("blocks", []) if block.get("bbox")]
        for marker in page.get("markers", []):
            value = str(marker.get("value"))
            potential = [
                entry
                for entry in note_records
                if str(entry.get("value")) == value
                and not entry.get("sequence_anomaly")
                and abs(int(entry["page"]) - int(page["page"])) <= note_page_window
            ]
            matching = [
                entry
                for entry in potential
                if scope_allows(page, page_by_number[int(entry["page"])], scoped)
            ]
            matching.sort(key=lambda entry: (abs(int(entry["page"]) - int(page["page"])), int(entry["page"])))
            paired = bool(matching)
            marker_box = marker.get("bbox")
            near_note = any(
                marker_box
                and block.get("bbox")
                and abs(box_center_y(marker_box) - box_center_y(block["bbox"])) <= 200
                for block in page_blocks
            )
            sequence = paired and sequence_support(value, sequence_marker_values, note_values)
            score, reasons = score_marker(marker, paired, near_note, sequence)
            marker["paired_note_entries"] = matching
            marker["near_note_block"] = near_note
            marker["sequence_support"] = sequence
            marker["score"] = score
            marker["reasons"] = reasons
            marker["classification"] = classify(score, marker, paired)
            if potential and not matching:
                if not scoped and any(int(entry["page"]) != int(page["page"]) for entry in potential):
                    marker["reasons"].append("scope_required_for_cross_page")
                elif scoped and "scope_boundary_blocked" not in marker["reasons"]:
                    marker["reasons"].append("scope_boundary_blocked")
            if scoped and not page.get("scope_resolved"):
                if "scope_unresolved" not in marker["reasons"]:
                    marker["reasons"].append("scope_unresolved")
        page["links"] = []
    # Candidates must be resolved before witnesses can be clustered: a native
    # and OCR observation of one marker should yield one logical link.
    rebuild_marker_clusters(pages)
    rebuild_links(pages)


def legacy_markers_by_page(markdown: str) -> dict[int, set[str]]:
    """Extract only explicit marker syntax from a legacy page-bounded Markdown file."""
    markers: dict[int, set[str]] = {}
    current_page: int | None = None
    for line in markdown.splitlines():
        page_match = PAGE_MARKER.match(line)
        if page_match:
            current_page = int(page_match.group(1))
            markers.setdefault(current_page, set())
            continue
        if current_page is None:
            continue
        values = set(re.findall(r"\[\^([0-9]{1,3})\]", line))
        for run in SUPERSCRIPT_RUN.findall(line):
            values.add(run.translate(SUPERSCRIPT_TRANSLATION))
        markers[current_page].update(values)
    return markers


def apply_legacy_witness(pages: list[dict[str, Any]], legacy: dict[int, set[str]]) -> None:
    """Attach checkpoint evidence without allowing it to replace source geometry."""
    for page in pages:
        values = legacy.get(int(page["page"]), set())
        page["legacy_marker_values"] = sorted(values, key=lambda value: (len(value), value))
        observed = set()
        for marker in page.get("markers", []):
            support = str(marker.get("value")) in values
            marker["legacy_support"] = support
            if support:
                marker["score"] += 2
                if "legacy_checkpoint_marker" not in marker["reasons"]:
                    marker["reasons"].append("legacy_checkpoint_marker")
                marker["classification"] = classify(marker["score"], marker, bool(marker.get("paired_note_entries")))
                observed.add(str(marker.get("value")))
        page["legacy_only_marker_values"] = sorted(values - observed, key=lambda value: (len(value), value))
    rebuild_marker_clusters(pages)


def rebuild_links(pages: list[dict[str, Any]]) -> None:
    """Rebuild accepted and review-only links per logical marker/note pair."""
    for page in pages:
        links = []
        review_links = []
        for cluster in page.get("marker_clusters", []):
            if cluster.get("classification") == "ambiguous":
                continue
            for entry in cluster.get("paired_note_entries", []):
                link = {
                    "marker_page": page["page"],
                    "note_page": entry.get("page", page["page"]),
                    "marker_value": cluster.get("value"),
                    "marker_source": "marker_cluster",
                    "marker_sources": cluster.get("sources", []),
                    "marker_cluster_id": cluster.get("cluster_id"),
                    "marker_bbox": cluster.get("bbox"),
                    "marker_line_index": cluster.get("marker_line_index"),
                    "marker_line_text": cluster.get("marker_line_text", ""),
                    "marker_before_text": cluster.get("marker_before_text", ""),
                    "marker_after_text": cluster.get("marker_after_text", ""),
                    "note_bbox": entry.get("bbox"),
                    "note_line_index": entry.get("line_index"),
                    "note_text": entry.get("text", ""),
                    "classification": cluster.get("classification"),
                    "score": cluster.get("score"),
                    "scope_id": page.get("scope_id"),
                }
                (links if cluster.get("classification") == "confirmed" else review_links).append(link)
        page["links"] = links
        page["review_links"] = review_links


def page_numbers(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    numbers: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            numbers.update(range(int(left), int(right) + 1))
        else:
            numbers.add(int(part))
    return sorted(number for number in numbers if 1 <= number <= total)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect deterministic footnote marker/note evidence.")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--ocr-dir", type=Path, required=True)
    parser.add_argument("--layout-dir", type=Path)
    parser.add_argument("--legacy-markdown", type=Path, help="Optional page-bounded Markdown witness from an earlier extraction")
    parser.add_argument("--legacy-git-ref", help="Read the legacy Markdown witness from a local Git ref")
    parser.add_argument(
        "--legacy-git-path",
        help="Path to the page-bounded Markdown witness inside the legacy Git ref (required with --legacy-git-ref)",
    )
    parser.add_argument(
        "--scope-json",
        type=Path,
        help="Optional JSON document/case page scopes; links require one unique equal scope on both pages",
    )
    parser.add_argument(
        "--hocr-dir",
        type=Path,
        help="Optional Tesseract hOCR sidecars named page_NNNN.hocr",
    )
    parser.add_argument(
        "--box-dir",
        type=Path,
        help="Optional Tesseract box sidecars named page_NNNN.box for character geometry",
    )
    parser.add_argument("--hocr-dpi", type=float, default=300.0)
    parser.add_argument("--pages", help="1-based page numbers/ranges, e.g. 361-362,538")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.legacy_git_ref and not args.legacy_git_path:
        raise SystemExit("--legacy-git-path is required when --legacy-git-ref is supplied")
    document = pymupdf.open(args.pdf)
    selected = page_numbers(args.pages, len(document))
    pages = []
    for number in selected:
        ocr_path = args.ocr_dir / f"page_{number:04d}.json"
        layout_path = args.layout_dir / f"page_{number:04d}.json" if args.layout_dir else None
        hocr_path = args.hocr_dir / f"page_{number:04d}.hocr" if args.hocr_dir else None
        if hocr_path and not hocr_path.exists():
            html_path = args.hocr_dir / f"page_{number:04d}.html"
            hocr_path = html_path if html_path.exists() else hocr_path
        box_path = args.box_dir / f"page_{number:04d}.box" if args.box_dir else None
        page_json = load_json(ocr_path)
        layout_json = load_json(layout_path) if layout_path else None
        hocr = (
            hocr_page_evidence(hocr_path, args.hocr_dpi, box_path=box_path)
            if hocr_path and hocr_path.exists()
            else None
        )
        evidence = analyze_page(document[number - 1], page_json, layout_json, hocr=hocr)
        pages.append(
            {
                "page": number,
                "ocr_artifact": str(ocr_path),
                "layout_artifact": str(layout_path) if layout_path else None,
                "hocr_artifact": str(hocr_path) if hocr_path and hocr_path.exists() else None,
                "box_artifact": str(box_path) if box_path and box_path.exists() else None,
                "has_ocr": bool(page_json),
                "has_layout": bool(layout_json),
                "has_hocr": bool(hocr),
                **evidence,
            }
        )
    scopes = None
    scope_source = None
    if args.scope_json:
        scope_value = json.loads(args.scope_json.read_text(encoding="utf-8"))
        scopes = load_scope_records(scope_value)
        scope_source = str(args.scope_json)
    resolve_document(pages, scopes=scopes)
    legacy = {}
    if args.legacy_git_ref:
        legacy_text = subprocess.run(
            ["git", "show", f"{args.legacy_git_ref}:{args.legacy_git_path}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        legacy_source = f"git:{args.legacy_git_ref}:{args.legacy_git_path}"
    elif args.legacy_markdown:
        legacy_text = sys.stdin.read() if str(args.legacy_markdown) == "-" else args.legacy_markdown.read_text(encoding="utf-8")
        legacy_source = str(args.legacy_markdown)
    else:
        legacy_text = ""
        legacy_source = None
    if legacy_text:
        legacy = legacy_markers_by_page(legacy_text)
        apply_legacy_witness(pages, legacy)
        rebuild_links(pages)
    output = {
        "schema": SCHEMA,
        "pdf": str(args.pdf),
        "pages_requested": selected,
        "settings": {
            "native_source": "pymupdf.rawdict",
            "ocr_source": "paddle_ocr_json",
            "layout_source": "ppstructure_layout_json",
            "coordinate_system": "PDF points for all boxes",
            "classification": "fixed evidence score with abstention",
            "legacy_witness": legacy_source,
            "scope_source": scope_source,
            "scope_policy": "unique_equal_scope_required" if scopes is not None else "same_page_only",
            "hocr_source": str(args.hocr_dir) if args.hocr_dir else None,
            "box_source": str(args.box_dir) if args.box_dir else None,
            "hocr_dpi": args.hocr_dpi if args.hocr_dir else None,
        },
        "pages": pages,
        "summary": {
            "pages": len(pages),
            "markers": sum(len(page.get("marker_clusters", [])) for page in pages),
            "marker_clusters": sum(len(page.get("marker_clusters", [])) for page in pages),
            "marker_witnesses": sum(len(page["markers"]) for page in pages),
            "confirmed": sum(sum(cluster["classification"] == "confirmed" for cluster in page.get("marker_clusters", [])) for page in pages),
            "candidates": sum(sum(cluster["classification"] == "candidate" for cluster in page.get("marker_clusters", [])) for page in pages),
            "ambiguous": sum(sum(cluster["classification"] == "ambiguous" for cluster in page.get("marker_clusters", [])) for page in pages),
            "confirmed_witnesses": sum(sum(marker["classification"] == "confirmed" for marker in page["markers"]) for page in pages),
            "links": sum(len(page["links"]) for page in pages),
            "review_links": sum(len(page.get("review_links", [])) for page in pages),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
