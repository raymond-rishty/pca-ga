from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "footnote_evidence.py"
SPEC = importlib.util.spec_from_file_location("footnote_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
footnote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(footnote)

EVAL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_footnote_evidence.py"
EVAL_SPEC = importlib.util.spec_from_file_location("evaluate_footnote_evidence", EVAL_PATH)
assert EVAL_SPEC and EVAL_SPEC.loader
evaluator = importlib.util.module_from_spec(EVAL_SPEC)
EVAL_SPEC.loader.exec_module(evaluator)

SCOPE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "derive_footnote_scopes.py"
SCOPE_SPEC = importlib.util.spec_from_file_location("derive_footnote_scopes", SCOPE_PATH)
assert SCOPE_SPEC and SCOPE_SPEC.loader
scope_deriver = importlib.util.module_from_spec(SCOPE_SPEC)
SCOPE_SPEC.loader.exec_module(scope_deriver)

SCAN_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scan_footnote_corpus.py"
SCAN_SPEC = importlib.util.spec_from_file_location("scan_footnote_corpus", SCAN_PATH)
assert SCAN_SPEC and SCAN_SPEC.loader
corpus_scanner = importlib.util.module_from_spec(SCAN_SPEC)
SCAN_SPEC.loader.exec_module(corpus_scanner)


def native_char(text: str, x: float, size: float, flags: int = 4, superscript: bool = False) -> dict:
    return {
        "text": text,
        "bbox": [x, 0, x + max(1.0, size / 2), size],
        "origin": [x, size],
        "size": size,
        "flags": flags,
        "font": "Test",
        "superscript": superscript,
    }


class FootnoteEvidenceTests(unittest.TestCase):
    def test_native_reduced_superscript_is_marker(self) -> None:
        line = {
            "text": "context.1",
            "bbox": [0, 0, 55, 12],
            "chars": [
                native_char("c", 0, 10),
                native_char("o", 5, 10),
                native_char("n", 10, 10),
                native_char("t", 15, 10),
                native_char("e", 20, 10),
                native_char("x", 25, 10),
                native_char("t", 30, 10),
                native_char(".", 35, 10),
                native_char("1", 42, 7, flags=5, superscript=True),
            ],
        }
        candidates = footnote.native_marker_candidates(
            {"lines": [line], "body_font_size": 10}, []
        )
        self.assertEqual([candidate["value"] for candidate in candidates], ["1"])
        self.assertTrue(candidates[0]["superscript"])
        self.assertTrue(candidates[0]["inline_after_word"])

    def test_native_superscript_survives_mislabeled_figure_title(self) -> None:
        text = "Sentence.156"
        native = {
            "lines": [
                {
                    "text": text,
                    "bbox": [0, 0, 100, 12],
                    "chars": [
                        native_char(
                            char,
                            index * 5,
                            6 if index >= len(text) - 3 else 9,
                            flags=5 if index >= len(text) - 3 else 4,
                            superscript=index >= len(text) - 3,
                        )
                        for index, char in enumerate(text)
                    ],
                }
            ],
            "body_font_size": 9,
        }
        layout = {
            "render": {"dpi": 72, "padding_pixels": 0},
            "blocks": [
                {
                    "label": "figure_title",
                    "bbox": [0, 0, 100, 12],
                    "content": text,
                },
                {
                    "label": "footnote",
                    "bbox": [0, 20, 100, 40],
                    "content": "156 Note text",
                },
            ],
        }
        document = footnote.pymupdf.open()
        page = document.new_page(width=100, height=100)
        with mock.patch.object(footnote, "native_page_evidence", return_value=native):
            result = footnote.analyze_page(page, None, layout)
        markers = [marker for marker in result["markers"] if marker["value"] == "156"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["classification"], "confirmed")
        self.assertIn("structural_native_superscript_exception", markers[0]["reasons"])

    def test_wrapped_native_marker_uses_layout_and_sequence_evidence(self) -> None:
        def make_line(text: str, y: float, raised: set[str] = set()) -> dict:
            chars = []
            raised_positions = set()
            for value in raised:
                start = text.find(value)
                if start >= 0:
                    raised_positions.update(range(start, start + len(value)))
            for index, char in enumerate(text):
                is_raised = index in raised_positions
                chars.append(
                    native_char(
                        char,
                        index * 5,
                        6 if is_raised else 10,
                        flags=5 if is_raised else 4,
                        superscript=is_raised,
                    )
                )
            return {"text": text, "bbox": [0, y, 100, y + 10], "chars": chars}

        native = {
            "lines": [
                make_line("A sentence.39", 0, {"39"}),
                make_line("40 The next", 11),
                make_line("Another word.41", 22, {"41"}),
            ],
            "body_font_size": 10,
        }
        layout = {
            "render": {"dpi": 72, "padding_pixels": 0},
            "blocks": [
                {
                    "label": "text",
                    "bbox": [0, 0, 100, 32],
                    "content": "A sentence.39A sentence.40The next Another word.41",
                },
                {
                    "label": "footnote",
                    "bbox": [0, 50, 100, 70],
                    "content": "39 First note\n40 Second note\n41 Third note",
                },
            ],
        }
        document = footnote.pymupdf.open()
        page = document.new_page(width=100, height=100)
        with mock.patch.object(footnote, "native_page_evidence", return_value=native):
            result = footnote.analyze_page(page, None, layout)
        markers = [marker for marker in result["markers"] if marker["value"] == "40"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["classification"], "confirmed")
        self.assertTrue(markers[0]["line_start"])
        self.assertTrue(markers[0]["line_start_layout_suffix"])
        self.assertTrue(markers[0]["sequence_support"])

    def test_wrapped_native_marker_rejects_hyphenated_code_context(self) -> None:
        native = {
            "lines": [
                {
                    "text": "The reference continues",
                    "bbox": [0, 0, 100, 10],
                    "chars": [native_char(char, index * 5, 10) for index, char in enumerate("The reference continues")],
                },
                {
                    "text": "40 The next line",
                    "bbox": [0, 11, 100, 21],
                    "chars": [native_char(char, index * 5, 10) for index, char in enumerate("40 The next line")],
                },
            ],
            "body_font_size": 10,
        }
        layout = {
            "render": {"dpi": 72, "padding_pixels": 0},
            "blocks": [
                {
                    "label": "text",
                    "bbox": [0, 0, 100, 21],
                    "content": "The reference cites BCO 40-5 and continues",
                }
            ],
        }
        self.assertEqual(
            footnote.native_line_start_layout_candidates(
                native,
                layout,
                [],
                {"40"},
            ),
            [],
        )

    def test_native_visual_continuation_recovers_split_block_sequence(self) -> None:
        def make_line(
            text: str,
            block_index: int,
            line_index: int,
            box: list[float],
            marker: str | None = None,
            x_offset: float = 0.0,
        ) -> dict:
            chars = []
            marker_positions = set()
            if marker:
                start = text.find(marker)
                marker_positions.update(range(start, start + len(marker)))
            for index, char in enumerate(text):
                raised = index in marker_positions
                chars.append(
                    native_char(
                        char,
                        x_offset + index * 4,
                        6 if raised else 10,
                        flags=5 if raised else 4,
                        superscript=raised,
                    )
                )
            return {
                "text": text,
                "bbox": box,
                "chars": chars,
                "block_index": block_index,
                "line_index": line_index,
            }

        native = {
            "lines": [
                make_line("Sentence.4", 0, 0, [0, 0, 80, 10], "4"),
                make_line("circumstance?", 1, 0, [0, 20, 50, 30]),
                make_line("5 The censure", 2, 0, [50, 20, 100, 30], "5", 50),
                make_line("Scripture,", 3, 0, [0, 40, 35, 50]),
                make_line("6 not granted", 4, 0, [35, 40, 100, 50], "6", 35),
            ],
            "body_font_size": 10,
        }
        layout = {
            "render": {"dpi": 72, "padding_pixels": 0},
            "blocks": [
                {
                    "label": "footnote",
                    "bbox": [0, 70, 100, 100],
                    "content": "4 First note\n5 Second note\n6 Third note",
                }
            ],
        }
        document = footnote.pymupdf.open()
        page = document.new_page(width=100, height=120)
        with mock.patch.object(footnote, "native_page_evidence", return_value=native):
            result = footnote.analyze_page(page, None, layout)
        markers = {
            marker["value"]: marker
            for marker in result["markers"]
            if marker["value"] in {"5", "6"}
        }
        self.assertEqual(set(markers), {"5", "6"})
        self.assertTrue(all(marker["line_start_visual_continuation"] for marker in markers.values()))
        self.assertTrue(all(marker["sequence_support"] for marker in markers.values()))
        self.assertTrue(all(marker["classification"] == "confirmed" for marker in markers.values()))

    def test_native_visual_continuation_rejects_hyphenated_code_context(self) -> None:
        previous = "BCO 40-"
        marker = "5 The next"
        native = {
            "lines": [
                {
                    "text": previous,
                    "bbox": [0, 0, 50, 10],
                    "chars": [native_char(char, index * 4, 10) for index, char in enumerate(previous)],
                    "block_index": 0,
                    "line_index": 0,
                },
                {
                    "text": marker,
                    "bbox": [50, 0, 100, 10],
                    "chars": [
                        native_char(char, 50 + index * 4, 6 if index == 0 else 10, flags=5 if index == 0 else 4, superscript=index == 0)
                        for index, char in enumerate(marker)
                    ],
                    "block_index": 1,
                    "line_index": 0,
                },
            ],
            "body_font_size": 10,
        }
        self.assertEqual(
            footnote.native_visual_continuation_candidates(native, [], {"5"}),
            [],
        )

    def test_native_superscript_digit_splits_from_base_digit(self) -> None:
        line = {
            "text": "$9²",
            "bbox": [0, 0, 30, 12],
            "chars": [
                native_char("$", 0, 10),
                native_char("9", 5, 10),
                native_char("²", 10, 6, flags=5, superscript=True),
            ],
        }
        candidates = footnote.native_marker_candidates(
            {"lines": [line], "body_font_size": 10}, []
        )
        values = [candidate["value"] for candidate in candidates]
        self.assertIn("2", values)
        self.assertNotIn("92", values)

    def test_native_attached_suffix_requires_explicit_note_value(self) -> None:
        text = "Athanasius,6"
        chars = [native_char(char, index * 5, 10) for index, char in enumerate(text)]
        candidates = footnote.native_marker_candidates(
            {"lines": [{"text": text, "bbox": [0, 0, 80, 12], "chars": chars}], "body_font_size": 10},
            [],
            word_suffix_values={"6"},
        )
        self.assertEqual([candidate["value"] for candidate in candidates], ["6"])
        self.assertTrue(candidates[0]["word_suffix"])
        self.assertTrue(candidates[0]["native_word_suffix"])
        self.assertEqual(
            footnote.native_marker_candidates(
                {"lines": [{"text": text, "bbox": [0, 0, 80, 12], "chars": chars}], "body_font_size": 10},
                [],
                set(),
            ),
            [],
        )

    def test_full_scripture_book_chapter_is_citation_context(self) -> None:
        self.assertTrue(footnote.citation_like_context("quoted in Genesis ", ";"))
        self.assertFalse(footnote.citation_like_context("quoted by Warfield ", ";"))

    def test_sentence_terminal_number_after_legal_keyword_is_not_hidden(self) -> None:
        self.assertFalse(
            footnote.citation_like_context("Westminster Presbytery.", " While")
        )
        self.assertTrue(
            footnote.citation_like_context(
                "Westminster Confession of Faith, Chapter ", ", and"
            )
        )

    def test_legal_word_before_quoted_sentence_does_not_hide_marker(self) -> None:
        self.assertFalse(
            footnote.citation_like_context(
                'to the judgment of a commission . .. ."', " Now it is no"
            )
        )

    def test_ocr_trailing_word_digit_is_retained_as_lexical_witness(self) -> None:
        lines, candidates = footnote.ocr_marker_candidates(
            {
                "render": {"dpi": 220, "padding_pixels": 0},
                "structured_lines": [
                    {"index": 0, "text": "Warfield2 and Machen3 and MSP5", "box": [0, 0, 200, 12], "score": 0.99}
                ],
            }
        )
        self.assertEqual([candidate["value"] for candidate in candidates], ["2", "3", "5"])
        self.assertTrue(all(candidate["word_suffix"] for candidate in candidates))
        self.assertTrue(all(candidate["inline_after_word"] for candidate in candidates))
        self.assertEqual(len(lines), 1)

    def test_split_line_continuation_is_retained_as_marker_witness(self) -> None:
        lines, candidates = footnote.ocr_marker_candidates(
            {
                "render": {"dpi": 220, "padding_pixels": 0},
                "structured_lines": [
                    {"index": 0, "text": "A sentence ends here.", "box": [0, 0, 100, 12], "score": 0.99},
                    {"index": 1, "text": "15", "box": [96, 1, 110, 9], "score": 0.99},
                ],
            }
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual([candidate["value"] for candidate in candidates], ["15"])
        self.assertTrue(candidates[0]["split_line_continuation"])
        self.assertTrue(candidates[0]["sentence_terminal_before"])

    def test_distant_numeric_line_is_not_split_marker(self) -> None:
        _, candidates = footnote.ocr_marker_candidates(
            {
                "render": {"dpi": 220, "padding_pixels": 0},
                "structured_lines": [
                    {"index": 0, "text": "A sentence ends here.", "box": [0, 0, 100, 12], "score": 0.99},
                    {"index": 1, "text": "15", "box": [220, 30, 234, 38], "score": 0.99},
                ],
            }
        )
        self.assertEqual(candidates, [])

    def test_layout_trailing_suffix_rejoins_numeric_ocr_line(self) -> None:
        layout = {
            "render": {"dpi": 220, "padding_pixels": 0},
            "blocks": [
                {
                    "label": "text",
                    "bbox": [0, 0, 200, 100],
                    "content": "The sentence ends here.9",
                }
            ],
        }
        raw_lines = [
            {"index": 0, "text": "The sentence ends here.", "box": [0, 0, 180, 12]},
            {"index": 1, "text": "9", "box": [0, 12, 16, 22]},
        ]
        _, candidates = footnote.ocr_marker_candidates(
            {"render": {"dpi": 220, "padding_pixels": 0}, "structured_lines": raw_lines}
        )
        footnote.add_layout_suffix_candidates(
            candidates,
            raw_lines,
            footnote.layout_trailing_suffixes(layout),
            {"9"},
        )
        self.assertEqual([candidate["value"] for candidate in candidates], ["9"])
        self.assertTrue(candidates[0]["layout_trailing_suffix"])

    def test_layout_trailing_suffix_does_not_rejoin_numeric_code(self) -> None:
        layout = {
            "render": {"dpi": 220, "padding_pixels": 0},
            "blocks": [
                {
                    "label": "text",
                    "bbox": [0, 0, 200, 100],
                    "content": "See BCO 40-5.2",
                }
            ],
        }
        suffixes = footnote.layout_trailing_suffixes(layout)
        self.assertEqual(suffixes, [])

    def test_single_letter_code_is_not_a_trailing_word_digit_witness(self) -> None:
        _, candidates = footnote.ocr_marker_candidates(
            {
                "render": {"dpi": 220, "padding_pixels": 0},
                "structured_lines": [
                    {"index": 0, "text": "C1 through C6", "box": [0, 0, 100, 12], "score": 0.99}
                ],
            }
        )
        self.assertEqual(candidates, [])

    def test_parenthesized_token_is_marked_for_table_context(self) -> None:
        _, candidates = footnote.ocr_marker_candidates(
            {
                "render": {"dpi": 220, "padding_pixels": 0},
                "structured_lines": [
                    {"index": 0, "text": "(1)", "box": [0, 0, 100, 12], "score": 0.99}
                ],
            }
        )
        self.assertEqual([candidate["value"] for candidate in candidates], ["1"])
        self.assertTrue(candidates[0]["parenthesized_token"])

    def test_note_label_does_not_truncate_year(self) -> None:
        self.assertEqual(footnote.NOTE_LABEL.match("Footnote 1.").group(1), "1")
        self.assertIsNone(footnote.NOTE_LABEL.match("1982)."))

    def test_note_sequence_marks_anomalous_ocr_label(self) -> None:
        values = ("123", "124", "4", "125")
        lines = [
            {"index": index, "text": f"{value} Ibid.", "box": [0, index * 10, 100, index * 10 + 8]}
            for index, value in enumerate(values)
        ]
        result = footnote.note_entries(
            [{"source": "test", "bbox": [0, 0, 100, 100], "content": "", "line_indices": [0, 1, 2, 3]}],
            lines,
        )
        numeric = [int(entry["value"]) for entry in result]
        self.assertEqual(numeric, [123, 124, 4, 125])
        self.assertTrue(result[2]["sequence_anomaly"])
        self.assertFalse(result[1]["sequence_anomaly"])

    def test_note_sequence_marks_cross_block_continuation(self) -> None:
        lines = [
            {"index": 1, "text": "6 Note text", "box": [10, 700, 120, 712]},
            {"index": 2, "text": "7 Longer note text", "box": [10, 714, 140, 726]},
            {"index": 3, "text": "42. If this is continued prose", "box": [10, 728, 180, 740]},
            {"index": 4, "text": "8 Citation text", "box": [10, 742, 140, 754]},
        ]
        blocks = [
            {"source": "ppstructure", "bbox": [0, 690, 200, 716], "line_indices": [1]},
            {"source": "ppstructure", "bbox": [0, 710, 200, 742], "line_indices": [2, 3]},
            {"source": "ppstructure", "bbox": [0, 738, 200, 760], "line_indices": [4]},
        ]
        result = footnote.note_entries(blocks, lines)
        by_value = {entry["value"]: entry for entry in result}
        self.assertTrue(by_value["42"]["sequence_anomaly"])
        self.assertFalse(by_value["7"]["sequence_anomaly"])

    def test_numeric_only_parenthesized_reference_is_not_note_label(self) -> None:
        lines = [
            {"index": 1, "text": "582).", "box": [10, 700, 60, 712]},
            {"index": 2, "text": "18 Here are two examples.", "box": [10, 714, 180, 726]},
        ]
        block = {
            "source": "ppstructure",
            "bbox": [0, 690, 200, 740],
            "line_indices": [1, 2],
        }
        result = footnote.note_entries([block], lines)
        self.assertEqual([entry["value"] for entry in result], ["18"])

    def test_wrapped_parenthesized_reference_with_prose_is_not_note_label(self) -> None:
        lines = [
            {"index": 1, "text": "7 Note text", "box": [10, 700, 100, 712]},
            {"index": 2, "text": "190)and yet can also say", "box": [10, 714, 200, 726]},
            {"index": 3, "text": "8 Final note", "box": [10, 728, 120, 740]},
        ]
        block = {
            "source": "ppstructure",
            "bbox": [0, 690, 220, 750],
            "line_indices": [1, 2, 3],
        }
        result = footnote.note_entries([block], lines)
        self.assertEqual([entry["value"] for entry in result], ["7", "8"])

    def test_content_recovery_rejects_wrapped_parenthesized_reference(self) -> None:
        lines = [
            {"index": 1, "text": "7 Note text", "box": [10, 700, 100, 712]},
            {"index": 2, "text": "8 Final note", "box": [10, 728, 120, 740]},
        ]
        block = {
            "source": "ppstructure",
            "bbox": [0, 690, 220, 750],
            "line_indices": [1, 2],
            "content": "7 Note text\n190)and yet can also say\n8 Final note",
        }
        result = footnote.note_entries([block], lines)
        self.assertEqual([entry["value"] for entry in result], ["7", "8"])

    def test_indented_numeric_continuation_is_sequence_anomaly(self) -> None:
        lines = [
            {"index": 1, "text": "1. First note", "box": [10, 700, 120, 712]},
            {"index": 2, "text": "100 TEs in the continuation", "box": [28, 714, 180, 726]},
            {"index": 3, "text": "2. Second note", "box": [10, 728, 120, 740]},
        ]
        block = {
            "source": "ppstructure_heading",
            "bbox": [0, 690, 220, 750],
            "line_indices": [1, 2, 3],
        }
        result = footnote.note_entries([block], lines)
        by_value = {entry["value"]: entry for entry in result}
        self.assertTrue(by_value["100"]["sequence_anomaly"])
        self.assertFalse(by_value["1"]["sequence_anomaly"])
        self.assertFalse(by_value["2"]["sequence_anomaly"])

    def test_note_sequence_ignores_inline_citation_number(self) -> None:
        values = ("50", "51", "52", "368", "53")
        lines = [
            {"index": index, "text": f"{value} note text", "box": [0, index * 10, 100, index * 10 + 8]}
            for index, value in enumerate(values)
        ]
        result = footnote.note_entries(
            [{"source": "test", "bbox": [0, 0, 100, 100], "content": "", "line_indices": list(range(5))}],
            lines,
        )
        by_value = {entry["value"]: entry for entry in result}
        self.assertTrue(by_value["368"]["sequence_anomaly"])
        self.assertFalse(by_value["53"]["sequence_anomaly"])

    def test_note_entries_recovers_collapsed_ocr_label(self) -> None:
        lines = [
            {"index": 1, "text": "2 The expense of the committee.", "box": [10, 714, 200, 726]},
            {"index": 2, "text": "3 The committee filed its report.", "box": [10, 728, 220, 740]},
        ]
        blocks = [
            {
                "source": "ppstructure",
                "bbox": [0, 690, 300, 750],
                "line_indices": [1, 2],
                "content": "1Review of Presbytery Records is included in the total.\n"
                "2 The expense of the committee.\n"
                "3 The committee filed its report.",
            }
        ]
        entries = footnote.note_entries(blocks, lines)
        self.assertEqual([entry["value"] for entry in entries], ["1", "2", "3"])

    def test_note_entries_accepts_parenthesized_labels(self) -> None:
        lines = [
            {"index": 1, "text": "(1) 1423 Registered Commissioners in 1998", "box": [10, 714, 240, 726]},
            {"index": 2, "text": "(2) AC's 1/9 share of total", "box": [10, 728, 220, 740]},
        ]
        entries = footnote.note_entries(
            [{"source": "ppstructure_heading", "label": "footnote", "bbox": [0, 690, 300, 750], "line_indices": [1, 2]}],
            lines,
        )
        self.assertEqual([entry["value"] for entry in entries], ["1", "2"])

    def test_note_entries_marks_wrapped_citation_range_tail(self) -> None:
        lines = [
            {"index": 1, "text": "10 We note further that established custom, once discovered", "box": [10, 700, 280, 712]},
            {"index": 2, "text": "18. Though it may be customary in some presbyteries", "box": [10, 714, 280, 726]},
        ]
        entries = footnote.note_entries(
            [{
                "source": "ppstructure",
                "label": "footnote",
                "bbox": [0, 690, 300, 750],
                "line_indices": [1, 2],
                "content": "10 We note ... p. 17, l. 4-18. Though it may be customary ...",
            }],
            lines,
        )
        by_value = {entry["value"]: entry for entry in entries}
        self.assertFalse(by_value["10"]["sequence_anomaly"])
        self.assertTrue(by_value["18"]["sequence_anomaly"])

    def test_note_entries_does_not_recover_nested_numbered_list(self) -> None:
        lines = [
            {"index": 1, "text": "2 In U.S. law, an interlocutory appeal is ...", "box": [10, 700, 280, 712]},
        ]
        entries = footnote.note_entries(
            [{
                "source": "ppstructure",
                "label": "footnote",
                "bbox": [0, 690, 300, 750],
                "line_indices": [1],
                "content": "2 In U.S. law, an interlocutory appeal is ...\n1. the outcome of the case ...",
            }],
            lines,
        )
        self.assertEqual([entry["value"] for entry in entries], ["2"])

    def test_note_entries_marks_contained_native_label_conflict(self) -> None:
        lines = [
            {"index": 1, "text": "7", "box": [12, 700, 20, 708]},
        ]
        native_lines = [
            {"index": 2, "text": "5 SJC #2009-6, Bordwine, et al.", "box": [10, 699, 180, 711], "note_source": "pymupdf_note_text"},
        ]
        entries = footnote.note_entries(
            [{"source": "ppstructure", "label": "footnote", "bbox": [0, 690, 300, 750], "line_indices": [1]}],
            lines,
            native_lines=native_lines,
        )
        by_value = {entry["value"]: entry for entry in entries}
        self.assertFalse(by_value["5"]["sequence_anomaly"])
        self.assertTrue(by_value["7"]["sequence_anomaly"])

    def test_lettered_footnote_block_infers_preceding_numeric_label(self) -> None:
        blocks = [
            {"source": "ppstructure", "label": "footnote", "bbox": [0, 600, 300, 650], "line_indices": [], "content": "a. BCO 40-3 prohibits review."},
            {"source": "ppstructure", "label": "footnote", "bbox": [0, 655, 300, 680], "line_indices": [1], "content": "2 See grounds in endnote 1."},
        ]
        lines = [{"index": 1, "text": "2 See grounds in endnote 1.", "box": [10, 655, 180, 667]}]
        entries = footnote.note_entries(blocks, lines)
        self.assertEqual([entry["value"] for entry in entries], ["1", "2"])
        self.assertTrue(entries[0]["content_recovered"])

    def test_layout_rejoins_parenthesized_table_notes(self) -> None:
        layout = {
            "blocks": [
                {"label": "vision_footnote", "order": 4, "bbox": [100, 500, 300, 520], "content": "NOTES:"},
                {"label": "text", "order": 1, "bbox": [100, 525, 300, 545], "content": "(1) 1423 Registered Commissioners"},
                {"label": "text", "order": 2, "bbox": [100, 550, 300, 570], "content": "(2) AC's 1/9 share"},
            ]
        }
        blocks = footnote.layout_note_blocks(layout)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["source"], "ppstructure_heading")
        self.assertIn("(1)", blocks[0]["content"])

    def test_generic_note_heading_stops_before_action_list(self) -> None:
        layout = {
            "blocks": [
                {"label": "paragraph_title", "order": 1, "bbox": [100, 100, 300, 120], "content": "SPECIFIC COMMITTEE AND AGENCY NOTES"},
                {"label": "text", "order": 2, "bbox": [100, 125, 300, 145], "content": "1. First explanatory note."},
                {"label": "text", "order": 3, "bbox": [100, 150, 300, 170], "content": "2. Second explanatory note."},
                {"label": "text", "order": 4, "bbox": [100, 175, 300, 195], "content": "3. Third explanatory note."},
                {"label": "text", "order": 5, "bbox": [100, 200, 300, 220], "content": "26. That ordinary action follows."},
                {"label": "text", "order": 6, "bbox": [100, 225, 300, 245], "content": "adopted"},
            ]
        }
        blocks = footnote.layout_note_blocks(layout)
        self.assertEqual(len(blocks), 1)
        self.assertIn("3. Third explanatory note", blocks[0]["content"])
        self.assertNotIn("26. That ordinary action", blocks[0]["content"])

    def test_marker_sequence_recovers_missing_note_labels(self) -> None:
        entries = [
            {"value": "4", "block_index": 0, "source": "ppstructure", "bbox": [10, 700, 20, 710]},
            {"value": "65", "block_index": 0, "source": "pymupdf_note_text", "bbox": [10, 720, 100, 730]},
        ]
        blocks = [{"source": "ppstructure", "label": "footnote", "bbox": [0, 690, 300, 750], "content": "4 Ramsay ...\n65 Alexander ..."}]
        candidates = [
            {"value": "64", "inline_after_word": True, "superscript": False, "citation_like": False, "bbox": [10, 100, 20, 110]},
            # A local citation-like warning must not break an otherwise
            # corroborated consecutive marker sequence.
            {"value": "65", "inline_after_word": True, "superscript": False, "citation_like": True, "bbox": [10, 200, 20, 210]},
            {"value": "66", "inline_after_word": True, "superscript": False, "citation_like": False, "bbox": [10, 300, 20, 310]},
        ]
        result = footnote.augment_note_entries_from_marker_sequences(entries, blocks, candidates)
        usable = [entry["value"] for entry in result if not entry.get("sequence_anomaly")]
        self.assertEqual(set(usable), {"64", "65", "66"})
        self.assertTrue(next(entry for entry in result if entry["value"] == "4")["sequence_anomaly"])
        self.assertTrue(next(entry for entry in result if entry["value"] == "64")["sequence_recovered"])

    def test_citation_without_typography_stays_ambiguous(self) -> None:
        candidate = footnote.make_ocr_candidate(
            {"index": 1, "text": "I Cor. iii.2.", "box": [0, 0, 100, 10], "score": 0.99},
            "2",
            10,
            11,
            False,
            citation_like=True,
        )
        score, _ = footnote.score_marker(candidate, paired=True, near_note=False, sequence=True)
        self.assertEqual(footnote.classify(score, candidate, paired=True), "ambiguous")

    def test_written_date_day_is_not_a_marker(self) -> None:
        self.assertTrue(footnote.citation_like_context("On February ", ", 2002"))
        candidate = footnote.make_ocr_candidate(
            {"index": 1, "text": "On February 1, 2002 the Session met", "box": [0, 0, 100, 10], "score": 0.99},
            "1",
            13,
            14,
            False,
            citation_like=True,
        )
        score, _ = footnote.score_marker(candidate, paired=True, near_note=True, sequence=True)
        self.assertEqual(footnote.classify(score, candidate, paired=True), "ambiguous")

    def test_percentage_quantity_is_not_a_marker(self) -> None:
        self.assertTrue(footnote.citation_like_context("An overall 5", "% increase"))
        candidate = footnote.make_ocr_candidate(
            {"index": 1, "text": "An overall 5% increase", "box": [0, 0, 100, 10], "score": 0.99},
            "5",
            10,
            11,
            False,
            citation_like=True,
        )
        score, _ = footnote.score_marker(candidate, paired=True, near_note=True, sequence=False)
        self.assertEqual(footnote.classify(score, candidate, paired=True), "ambiguous")

    def test_terminal_ocr_marker_with_explicit_note_is_confirmed(self) -> None:
        candidate = footnote.make_ocr_candidate(
            {"index": 1, "text": "A sentence ends here.76", "box": [0, 0, 100, 10], "score": 0.99},
            "76",
            21,
            23,
            False,
            citation_like=False,
        )
        candidate["paired_note_entries"] = [{"source": "ppstructure"}]
        score, reasons = footnote.score_marker(candidate, paired=True, near_note=False, sequence=False)
        self.assertIn("terminal_marker_with_explicit_note", reasons)
        self.assertEqual(score, 7)
        self.assertEqual(footnote.classify(score, candidate, paired=True), "confirmed")

    def test_sentence_terminal_ocr_marker_with_explicit_note_is_confirmed(self) -> None:
        candidate = footnote.make_ocr_candidate(
            {"index": 1, "text": "Westminster Presbytery.6 While", "box": [0, 0, 100, 10], "score": 0.99},
            "6",
            23,
            24,
            False,
        )
        candidate["paired_note_entries"] = [{"source": "ppstructure"}]
        score, reasons = footnote.score_marker(candidate, paired=True, near_note=False, sequence=False)
        self.assertTrue(candidate["sentence_terminal_before"])
        self.assertIn("terminal_marker_with_explicit_note", reasons)
        self.assertEqual(score, 7)
        self.assertEqual(footnote.classify(score, candidate, paired=True), "confirmed")

    def test_quoted_marker_allows_space_after_closing_quote(self) -> None:
        self.assertTrue(footnote.inline_after_word_context('quoted text"'))

    def test_strong_context_does_not_override_citation_penalty(self) -> None:
        candidate = footnote.make_ocr_candidate(
            {"index": 1, "text": "Word3 (John 3:16)", "box": [0, 0, 100, 10], "score": 0.99},
            "3",
            4,
            5,
            False,
            citation_like=True,
        )
        score, _ = footnote.score_marker(candidate, paired=True, near_note=True, sequence=True)
        self.assertGreaterEqual(score, 9)
        self.assertEqual(footnote.classify(score, candidate, paired=True), "ambiguous")

    def test_cross_page_pairing_is_bounded_and_explainable(self) -> None:
        marker = {
            "value": "1",
            "source": "pymupdf",
            "bbox": [100, 100, 104, 108],
            "superscript": True,
            "size_ratio": 0.7,
            "inline_after_word": True,
            "attached": True,
            "line_start": False,
        }
        pages = [
            {"page": 1, "markers": [marker], "note_entries": [], "blocks": []},
            {
                "page": 2,
                "markers": [],
                "note_entries": [{"value": "1", "bbox": [10, 500, 100, 510]}],
                "blocks": [],
            },
            {
                "page": 5,
                "markers": [],
                "note_entries": [{"value": "1", "bbox": [10, 500, 100, 510]}],
                "blocks": [],
            },
        ]
        scopes = footnote.load_scope_records(
            {"scopes": [
                {"id": "case-a", "start_page": 1, "end_page": 2},
                {"id": "case-b", "start_page": 5, "end_page": 5},
            ]}
        )
        footnote.resolve_document(pages, note_page_window=2, scopes=scopes)
        self.assertEqual(pages[0]["markers"][0]["classification"], "confirmed")
        self.assertEqual(len(pages[0]["links"]), 1)
        self.assertEqual(pages[0]["links"][0]["note_page"], 2)

    def test_unscoped_cross_page_pairing_requires_scope(self) -> None:
        marker = {
            "value": "1",
            "source": "pymupdf",
            "bbox": [100, 100, 104, 108],
            "superscript": True,
            "size_ratio": 0.7,
            "inline_after_word": True,
            "attached": True,
            "line_start": False,
        }
        pages = [
            {"page": 1, "markers": [marker], "note_entries": [], "blocks": []},
            {
                "page": 2,
                "markers": [],
                "note_entries": [{"value": "1", "bbox": [10, 500, 100, 510]}],
                "blocks": [],
            },
        ]
        footnote.resolve_document(pages, note_page_window=2)
        self.assertEqual(pages[0]["markers"][0]["paired_note_entries"], [])
        self.assertEqual(pages[0]["links"], [])
        self.assertIn("scope_required_for_cross_page", pages[0]["markers"][0]["reasons"])

    def test_scope_boundary_blocks_neighboring_document(self) -> None:
        marker = {
            "value": "1",
            "source": "pymupdf",
            "bbox": [100, 100, 104, 108],
            "superscript": True,
            "size_ratio": 0.7,
            "inline_after_word": True,
            "attached": True,
            "line_start": False,
        }
        pages = [
            {"page": 1, "markers": [marker], "note_entries": [], "blocks": []},
            {
                "page": 2,
                "markers": [],
                "note_entries": [{"value": "1", "bbox": [10, 500, 100, 510]}],
                "blocks": [],
            },
        ]
        scopes = footnote.load_scope_records(
            {"scopes": [
                {"id": "case-a", "start_page": 1, "end_page": 1},
                {"id": "case-b", "start_page": 2, "end_page": 2},
            ]}
        )
        footnote.resolve_document(pages, note_page_window=2, scopes=scopes)
        self.assertEqual(pages[0]["scope_id"], "case-a")
        self.assertEqual(pages[0]["markers"][0]["paired_note_entries"], [])
        self.assertEqual(pages[0]["links"], [])
        self.assertIn("scope_boundary_blocked", pages[0]["markers"][0]["reasons"])

    def test_native_and_ocr_witnesses_form_one_logical_marker(self) -> None:
        witnesses = [
            {
                "value": "1", "source": "pymupdf", "bbox": [50, 100, 54, 108],
                "classification": "confirmed", "score": 11,
                "reasons": ["superscript_or_unicode"], "paired_note_entries": [],
            },
            {
                "value": "1", "source": "paddle_ocr", "bbox": [51, 99, 58, 110],
                "classification": "candidate", "score": 8,
                "reasons": ["inline_after_word"], "paired_note_entries": [],
            },
        ]
        pages = [{"page": 10, "markers": witnesses}]
        footnote.rebuild_marker_clusters(pages)
        self.assertEqual(len(pages[0]["marker_clusters"]), 1)
        cluster = pages[0]["marker_clusters"][0]
        self.assertEqual(cluster["witness_count"], 2)
        self.assertEqual(cluster["classification"], "confirmed")
        self.assertEqual(cluster["sources"], ["paddle_ocr", "pymupdf"])

    def test_hocr_character_boxes_supply_scan_geometry(self) -> None:
        self.assertTrue(footnote.inline_after_word_context('parent."'))
        parser = footnote.HocrParser()
        parser.feed(
            "<span class='ocr_line' title='bbox 0 0 100 30; baseline 0 20'>"
            "<span class='ocrx_word' title='bbox 0 0 60 25'>"
            "<span class='ocrx_cinfo' title='bbox 0 5 8 20'>w</span>"
            "<span class='ocrx_cinfo' title='bbox 9 4 15 18'>1</span>"
            "</span></span>"
        )
        self.assertEqual(parser.lines[0]["words"][0]["text"], "w1")
        lines = [{
            "text": "w1",
            "box": [0, 0, 100, 30],
            "words": [],
            "chars": [
                {"text": "w", "bbox": [0, 5, 8, 20]},
                {"text": "1", "bbox": [9, 4, 15, 18]},
            ],
        }]
        _, candidates = footnote.hocr_marker_candidates({"body_char_height": 15, "lines": lines})
        self.assertEqual([candidate["value"] for candidate in candidates], ["1"])
        self.assertTrue(candidates[0]["superscript"])
        self.assertFalse(candidates[0]["character_box_approximate"])

    def test_tesseract_box_sidecar_supplies_scan_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hocr_path = root / "page_0001.hocr"
            box_path = root / "page_0001.box"
            hocr_path.write_text(
                "<div class='ocr_page' title='bbox 0 0 100 100'>"
                "<span class='ocr_line' title='bbox 0 0 100 30; baseline 0 20'>"
                "<span class='ocrx_word' title='bbox 0 0 30 25'>w1</span>"
                "</span></div>",
                encoding="utf-8",
            )
            box_path.write_text("w 0 80 8 95 0\n1 9 84 15 96 0\n", encoding="utf-8")
            evidence = footnote.hocr_page_evidence(hocr_path, dpi=72, box_path=box_path)
        self.assertEqual(evidence["box_character_count"], 2)
        _, candidates = footnote.hocr_marker_candidates(evidence)
        self.assertEqual([candidate["value"] for candidate in candidates], ["1"])
        self.assertTrue(candidates[0]["superscript"])
        self.assertFalse(candidates[0]["character_box_approximate"])

    def test_layout_table_excludes_hocr_candidates(self) -> None:
        document = footnote.pymupdf.open()
        page = document.new_page(width=100, height=100)
        hocr = {
            "body_char_height": 10,
            "lines": [{
                "text": "word1",
                "box": [0, 0, 40, 12],
                "chars": [
                    {"text": "w", "bbox": [0, 0, 8, 10]},
                    {"text": "1", "bbox": [9, 0, 13, 5]},
                ],
                "words": [],
            }],
        }
        layout = {
            "render": {"dpi": 72, "padding_pixels": 0},
            "blocks": [{"label": "table", "bbox": [0, 0, 100, 100]}],
        }
        result = footnote.analyze_page(page, None, layout, hocr=hocr)
        self.assertEqual(result["markers"], [])

    def test_heuristic_bottom_run_pair_stays_reviewable_for_ocr(self) -> None:
        for source in ("paddle_ocr", "tesseract_hocr"):
            candidate = {
                "value": "1",
                "source": source,
                "superscript": True,
                "inline_after_word": True,
                "attached": True,
                "paired_note_entries": [{"source": "ocr_bottom_run"}],
            }
            self.assertEqual(footnote.classify(15, candidate, paired=True), "candidate")

    def test_candidate_pair_is_review_link_not_accepted_link(self) -> None:
        pages = [{
            "page": 1,
            "markers": [{
                "value": "1",
                "source": "tesseract_hocr",
                "bbox": [40, 40, 44, 45],
                "superscript": True,
                "inline_after_word": True,
                "attached": True,
                "line_start": False,
                "paired_note_entries": [{
                    "page": 1,
                    "value": "1",
                    "source": "ocr_bottom_run",
                    "bbox": [10, 80, 20, 90],
                }],
                "classification": "candidate",
                "score": 15,
                "reasons": [],
            }],
            "note_entries": [],
            "blocks": [],
        }]
        footnote.rebuild_marker_clusters(pages)
        footnote.rebuild_links(pages)
        self.assertEqual(pages[0]["links"], [])
        self.assertEqual(len(pages[0]["review_links"]), 1)
        self.assertEqual(pages[0]["review_links"][0]["classification"], "candidate")

    def test_explicit_note_block_can_confirm_hocr_geometry(self) -> None:
        candidate = {
            "value": "1",
            "source": "tesseract_hocr",
            "superscript": True,
            "inline_after_word": True,
            "attached": True,
            "paired_note_entries": [{"source": "pymupdf_note_text", "block_source": "ppstructure"}],
        }
        self.assertEqual(footnote.classify(15, candidate, paired=True), "confirmed")

    def test_legacy_witness_is_page_bounded(self) -> None:
        markdown = """<!-- PAGE ga=40 pdf_page=10 printed_page=8 -->
Text with a superscript¹ and [^2].
<!-- PAGE ga=40 pdf_page=11 printed_page=9 -->
Text with a superscript³.
"""
        self.assertEqual(footnote.legacy_markers_by_page(markdown), {10: {"1", "2"}, 11: {"3"}})

    def test_legacy_witness_promotes_matching_explicit_pair(self) -> None:
        marker = footnote.make_ocr_candidate(
            {"index": 1, "text": "Princeton Session 1)", "box": [0, 0, 100, 10], "score": 0.99},
            "1",
            17,
            18,
            False,
        )
        marker["paired_note_entries"] = [{"source": "pymupdf_note_text", "block_source": "ppstructure"}]
        marker["classification"] = "candidate"
        marker["score"] = 7
        marker["reasons"] = ["inline_after_word", "attached_to_text", "matching_note_number"]
        pages = [{"page": 104, "markers": [marker]}]
        footnote.apply_legacy_witness(pages, {104: {"1"}})
        self.assertTrue(marker["legacy_support"])
        self.assertIn("legacy_checkpoint_marker", marker["reasons"])
        self.assertEqual(marker["classification"], "confirmed")
        self.assertEqual(pages[0]["legacy_only_marker_values"], [])

    def test_legacy_path_uses_volume_and_pdf_year(self) -> None:
        self.assertEqual(
            corpus_scanner.legacy_path_for(
                "ga25", Path("25th_pcaga_1997.pdf"), "archive/{volume}_{year}.md"
            ),
            "archive/ga25_1997.md",
        )

    def test_compact_page_preserves_legacy_audit_fields(self) -> None:
        compact = corpus_scanner.compact_page(
            {
                "page": 130,
                "scope_ids": [],
                "scope_id": None,
                "scope_resolved": False,
                "blocks": [],
                "note_entries": [],
                "marker_clusters": [],
                "review_links": [],
                "legacy_marker_values": ["56", "57", "58", "59"],
                "legacy_only_marker_values": ["58"],
            }
        )
        self.assertEqual(compact["legacy_marker_values"], ["56", "57", "58", "59"])
        self.assertEqual(compact["legacy_only_marker_values"], ["58"])

    def test_gold_evaluator_reports_exact_set_metrics(self) -> None:
        report = {
            "pdf": "test.pdf",
            "pages": [{
                "page": 10,
                "marker_clusters": [{"value": "1", "classification": "confirmed"}],
                "links": [{"marker_value": "1"}],
            }],
        }
        gold = {"volume": "test", "pages": [{"page": 10, "expected_markers": ["1"], "expected_links": ["1"]}]}
        result = evaluator.evaluate(report, gold)
        self.assertEqual(result["marker_metrics"]["precision"], 1.0)
        self.assertEqual(result["link_metrics"]["recall"], 1.0)

    def test_gold_evaluator_preserves_duplicate_occurrences(self) -> None:
        report = {
            "pdf": "test.pdf",
            "pages": [{
                "page": 10,
                "marker_clusters": [
                    {"value": "2", "classification": "confirmed"},
                    {"value": "2", "classification": "confirmed"},
                ],
                "links": [{"marker_value": "2"}, {"marker_value": "2"}],
            }],
        }
        gold = {"volume": "test", "pages": [{"page": 10, "expected_markers": ["2", "2"], "expected_links": ["2", "2"]}]}
        result = evaluator.evaluate(report, gold)
        self.assertEqual(result["marker_occurrence_metrics"]["true_positive"], 2)
        self.assertEqual(result["link_occurrence_metrics"]["false_positive"], 0)

    def test_structural_table_cannot_be_note_block(self) -> None:
        lines = [
            {"text": "1 12 34", "bbox": [10, 700, 200, 712]},
            {"text": "2 56 78", "bbox": [10, 714, 200, 726]},
            {"text": "3 90 12", "bbox": [10, 728, 200, 740]},
        ]
        excluded = [[0, 680, 600, 780]]
        self.assertEqual(footnote.heuristic_note_blocks(lines, excluded), [])

    def test_numbered_list_with_split_labels_is_not_note_block(self) -> None:
        lines = [
            {"index": 1, "text": "1.", "box": [10, 700, 25, 712]},
            {"index": 2, "text": "First item", "box": [30, 700, 100, 712]},
            {"index": 3, "text": "2.", "box": [10, 714, 25, 726]},
            {"index": 4, "text": "Second item", "box": [30, 714, 110, 726]},
            {"index": 5, "text": "3.", "box": [10, 728, 25, 740]},
            {"index": 6, "text": "Third item", "box": [30, 728, 100, 740]},
        ]
        self.assertEqual(footnote.heuristic_note_blocks(lines), [])

    def test_layout_mode_disables_unlabeled_bottom_run_fallback(self) -> None:
        lines = [
            {"index": 1, "text": "1. First item", "box": [10, 700, 120, 712]},
            {"index": 2, "text": "2. Second item", "box": [10, 714, 120, 726]},
            {"index": 3, "text": "3. Third item", "box": [10, 728, 120, 740]},
        ]
        self.assertEqual(footnote.heuristic_note_blocks(lines, allow_bottom_run=False), [])

    def test_symbol_footnote_prose_is_not_numeric_note_label(self) -> None:
        lines = [
            {"index": 1, "text": "6 graduates have double majors", "box": [10, 700, 160, 712]},
            {"index": 2, "text": "1 graduate has a double major", "box": [10, 714, 160, 726]},
            {"index": 3, "text": "4 graduates have double majors", "box": [10, 728, 160, 740]},
        ]
        block = {
            "source": "ppstructure",
            "bbox": [0, 690, 200, 750],
            "line_indices": [1, 2, 3],
        }
        self.assertEqual(footnote.note_entries([block], lines), [])

    def test_vision_footnote_layout_mislabels_are_rejected(self) -> None:
        self.assertFalse(
            footnote.credible_vision_note_block(
                {"label": "vision_footnote", "content": "Number of Churches.10"}
            )
        )
        self.assertFalse(
            footnote.credible_vision_note_block(
                {"label": "vision_footnote", "content": "12. That the Trustees seek annual bids."}
            )
        )
        self.assertFalse(
            footnote.credible_vision_note_block(
                {"label": "vision_footnote", "content": "1.The proposed Budget be approved."}
            )
        )

    def test_vision_footnote_with_note_prose_is_retained(self) -> None:
        self.assertTrue(
            footnote.credible_vision_note_block(
                {"label": "vision_footnote", "content": "1Includes $58,626 budget for New Church Building Fund"}
            )
        )
        self.assertTrue(
            footnote.credible_vision_note_block(
                {"label": "footnote", "content": "may even be privately persuaded that he is guilty"}
            )
        )

    def test_scope_derivation_merges_only_overlapping_case_ranges(self) -> None:
        records = [
            {"ga_ordinal": 40, "case_id": "2010-26", "title": "A", "pdf_page_start": 532, "pdf_page_end": 540},
            {"ga_ordinal": 40, "case_id": "2009-16", "title": "B", "pdf_page_start": 533, "pdf_page_end": 543},
            {"ga_ordinal": 40, "case_id": "2010-27", "title": "C", "pdf_page_start": 544, "pdf_page_end": 551},
            {"ga_ordinal": 41, "case_id": "other", "title": "D", "pdf_page_start": 1, "pdf_page_end": 4},
        ]
        with tempfile.TemporaryDirectory() as directory:
            cases_path = Path(directory) / "cases.jsonl"
            cases_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            report = scope_deriver.derive("ga40_2012", cases_path)
            self.assertEqual([(scope["start_page"], scope["end_page"]) for scope in report["scopes"]], [(532, 543), (544, 551)])
            self.assertEqual(len(report["overlap_groups"]), 1)

    def test_scope_path_uses_volume_and_pdf_year(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scope_dir = Path(directory)
            expected = scope_dir / "footnote_scopes_ga23_1995_derived.json"
            expected.write_text("{}", encoding="utf-8")
            actual = corpus_scanner.scope_path_for(
                "ga23", Path("23rd_pcaga_1995.pdf"), scope_dir
            )
            self.assertEqual(actual, expected)

    def test_scope_path_rejects_missing_exact_volume_year(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                corpus_scanner.scope_path_for(
                    "ga23", Path("23rd_pcaga_1995.pdf"), Path(directory)
                )


if __name__ == "__main__":
    unittest.main()
