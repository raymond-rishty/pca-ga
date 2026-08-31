from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ensure_minutes_source_pdf_metadata.py"
spec = importlib.util.spec_from_file_location("ensure_minutes_source_pdf_metadata", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_adds_missing_source_pdf_before_extraction() -> None:
    source = """---
doc_type: ga_minutes
ga_ordinal: 48
year: 2021
page_count: 1154
extraction:
  method: paddle_ocr_v6_routed_semantic
schema_version: 2
---

Minutes body
"""
    normalized, changed = module.normalize_text(source, "ga48_2021.md")

    assert changed is True
    assert 'source_pdf:\n  file: "48th_pcaga_2021.pdf"\nextraction:' in normalized
    assert normalized.endswith("\nMinutes body\n")


def test_preserves_existing_source_pdf_fields() -> None:
    source = """---
doc_type: ga_minutes
ga_ordinal: 1
year: 1973
page_count: 252
source_pdf:
  file: 1st_pcaga_1973.pdf
  sha256: abc123
extraction:
  method: pdftotext_layout
schema_version: 1
---
Body
"""
    normalized, changed = module.normalize_text(source, "ga01_1973.md")

    assert changed is False
    assert normalized == source
    assert "sha256: abc123" in normalized


def test_adds_file_to_existing_source_pdf_block() -> None:
    source = """---
doc_type: ga_minutes
ga_ordinal: 21
year: 1993
source_pdf:
  sha256: abc123
schema_version: 2
---
Body
"""
    normalized, changed = module.normalize_text(source, "ga21_1993.md")

    assert changed is True
    assert 'source_pdf:\n  file: "21st_pcaga_1993.pdf"\n  sha256: abc123' in normalized


def test_refuses_conflicting_source_pdf_filename() -> None:
    source = """---
doc_type: ga_minutes
ga_ordinal: 22
year: 1994
source_pdf:
  file: wrong.pdf
schema_version: 2
---
Body
"""
    try:
        module.normalize_text(source, "ga22_1994.md")
    except ValueError as exc:
        assert "expected '22nd_pcaga_1994.pdf'" in str(exc)
    else:
        raise AssertionError("expected conflicting source_pdf.file to be rejected")


def test_ordinal_suffixes() -> None:
    assert module.ordinal_suffix(1) == "st"
    assert module.ordinal_suffix(2) == "nd"
    assert module.ordinal_suffix(3) == "rd"
    assert module.ordinal_suffix(11) == "th"
    assert module.ordinal_suffix(12) == "th"
    assert module.ordinal_suffix(13) == "th"
    assert module.ordinal_suffix(21) == "st"
    assert module.ordinal_suffix(52) == "nd"
