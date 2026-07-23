"""Conservative, metadata-backed Scripture citation parsing for rendered prose."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

DASH = r"[-\u2010\u2011\u2012\u2013\u2014\u2212]"
NUMBER = re.compile(r"\d{1,3}")


def _alias_key(value: str) -> str:
    return re.sub(r"[.\s]", "", value).lower()


def load_metadata(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    books = payload.get("books") or []
    if len(books) != 66 or [book.get("order") for book in books] != list(range(1, 67)):
        raise ValueError("Scripture metadata must contain the ordered 66-book Protestant canon")
    by_id = {book["id"]: book for book in books}
    aliases: dict[str, str] = {}
    patterns: list[str] = []
    for book in books:
        counts = book.get("verseCounts") or []
        available = book.get("availableVerses") or []
        if not counts or len(counts) != len(available):
            raise ValueError(f"{book.get('name')} lacks chapter validation data")
        for alias in book.get("aliases") or []:
            key = _alias_key(alias)
            aliases[key] = book["id"]
            patterns.append(re.escape(alias).replace(r"\ ", r"\s+") + r"\.?")
    pattern = "|".join(sorted(set(patterns), key=len, reverse=True))
    return {
        "books": by_id,
        "aliases": aliases,
        "alias_re": re.compile(rf"(?<![A-Za-z0-9])(?P<alias>{pattern})(?![A-Za-z])", re.I),
    }


def _num(text: str, pos: int) -> tuple[int | None, int]:
    match = NUMBER.match(text, pos)
    return (int(match.group()), match.end()) if match else (None, pos)


def _space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace(): pos += 1
    return pos


def _dash(text: str, pos: int) -> tuple[bool, int]:
    pos = _space(text, pos)
    if pos < len(text) and re.match(DASH, text[pos]): return True, _space(text, pos + 1)
    return False, pos


def _verse_piece(text: str, pos: int, chapter: int, verse: int) -> tuple[int, int, int, bool]:
    """Return ending chapter/verse, cursor, and whether f./ff. was present."""
    pos = _space(text, pos)
    suffix = False
    suffix_match = re.match(r"ff?\.?(?![A-Za-z])", text[pos:], re.I)
    if suffix_match:
        return chapter, verse, pos + suffix_match.end(), True
    dashed, after_dash = _dash(text, pos)
    if not dashed: return chapter, verse, pos, suffix
    end_number, after_number = _num(text, after_dash)
    if end_number is None: return chapter, verse, pos, suffix
    after_number = _space(text, after_number)
    if after_number < len(text) and text[after_number] == ":":
        end_verse, end_pos = _num(text, _space(text, after_number + 1))
        if end_verse is None: return chapter, verse, pos, suffix
        return end_number, end_verse, end_pos, suffix
    return chapter, end_number, after_number, suffix


def parse_group(text: str, start: int, book: dict[str, Any]) -> dict[str, Any] | None:
    pos = _space(text, start)
    first, pos = _num(text, pos)
    if first is None: return None
    one_chapter = bool(book.get("oneChapter"))
    entries: list[dict[str, Any]] = []
    labels: list[str] = []
    if one_chapter:
        end_ch, end_verse, pos, suffix = _verse_piece(text, pos, 1, first)
        entries.append({"kind": "verse", "startChapter": 1, "startVerse": first, "endChapter": end_ch, "endVerse": end_verse, "suffix": suffix})
        labels.append(str(first) + (f"-{end_verse}" if end_verse != first else "") + ("ff." if suffix else ""))
        return {"end": pos, "entries": entries, "body": "".join(labels), "form": "single-chapter-book verse"}
    pos = _space(text, pos)
    if pos >= len(text) or text[pos] != ":":
        dashed, after_dash = _dash(text, pos)
        end_ch = first
        if dashed:
            candidate, candidate_pos = _num(text, after_dash)
            if candidate is not None: end_ch, pos = candidate, candidate_pos
        entries.append({"kind": "chapter", "startChapter": first, "endChapter": end_ch})
        return {"end": pos, "entries": entries, "body": str(first) + (f"-{end_ch}" if end_ch != first else ""), "form": "chapter range" if end_ch != first else "whole chapter"}
    verse, pos = _num(text, _space(text, pos + 1))
    if verse is None: return None
    end_ch, end_verse, pos, suffix = _verse_piece(text, pos, first, verse)
    entries.append({"kind": "verse", "startChapter": first, "startVerse": verse, "endChapter": end_ch, "endVerse": end_verse, "suffix": suffix})
    body = f"{first}.{verse}" + (f"-{end_ch}.{end_verse}" if end_ch != first else (f"-{end_verse}" if end_verse != verse else "")) + ("ff." if suffix else "")
    current_ch = end_ch
    # Continuations are deliberately narrow: comma = same chapter verse, and
    # semicolon requires an explicit chapter:verse expression.
    while True:
        separator_start = pos
        pos = _space(text, pos)
        if pos >= len(text) or text[pos] not in ",;": break
        separator = text[pos]
        next_number, after_number = _num(text, _space(text, pos + 1))
        if next_number is None: pos = separator_start; break
        after_number = _space(text, after_number)
        if after_number < len(text) and text[after_number] == ":":
            next_verse, next_pos = _num(text, _space(text, after_number + 1))
            if next_verse is None: pos = separator_start; break
            end_ch, end_verse, next_pos, suffix = _verse_piece(text, next_pos, next_number, next_verse)
            entries.append({"kind": "verse", "startChapter": next_number, "startVerse": next_verse, "endChapter": end_ch, "endVerse": end_verse, "suffix": suffix})
            body += f";{next_number}.{next_verse}" + (f"-{end_ch}.{end_verse}" if end_ch != next_number else (f"-{end_verse}" if end_verse != next_verse else ""))
            current_ch, pos = end_ch, next_pos
        elif separator == ",":
            end_ch, end_verse, next_pos, suffix = _verse_piece(text, after_number, current_ch, next_number)
            entries.append({"kind": "verse", "startChapter": current_ch, "startVerse": next_number, "endChapter": end_ch, "endVerse": end_verse, "suffix": suffix})
            body += f",{next_number}" + (f"-{end_verse}" if end_verse != next_number else "")
            current_ch, pos = end_ch, next_pos
        else:
            pos = separator_start; break
    return {"end": pos, "entries": entries, "body": body, "form": "citation group" if len(entries) > 1 else "chapter and verse"}


def resolve(book: dict[str, Any], parsed: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    counts, available = book["verseCounts"], book["availableVerses"]
    chapters: dict[int, dict[str, Any]] = {}
    for entry in parsed["entries"]:
        start_ch, end_ch = entry["startChapter"], entry["endChapter"]
        if not (1 <= start_ch <= len(counts) and 1 <= end_ch <= len(counts)) or end_ch < start_ch:
            return None, "invalid bounds"
        if entry["kind"] == "chapter":
            for chapter in range(start_ch, end_ch + 1): chapters[chapter] = {"all": True, "ranges": []}
            continue
        start_verse, end_verse = entry["startVerse"], entry["endVerse"]
        if (end_ch, end_verse) < (start_ch, start_verse): return None, "invalid bounds"
        if start_verse not in available[start_ch - 1] or end_verse not in available[end_ch - 1]: return None, "invalid bounds"
        for chapter in range(start_ch, end_ch + 1):
            bounds = (start_verse if chapter == start_ch else 1, end_verse if chapter == end_ch else counts[chapter - 1])
            item = chapters.setdefault(chapter, {"all": False, "ranges": []})
            item["ranges"].append(list(bounds))
    return [{"book": book["id"], "chapter": chapter, **value} for chapter, value in chapters.items()], None


def _audit(base: dict[str, Any], text: str, start: int, end: int, classification: str, suggestion: str | None = None) -> dict[str, Any]:
    context = text[max(0, start - 60):min(len(text), end + 80)]
    result = {**base, "originalText": text[start:end], "context": context, "classification": classification}
    if suggestion: result["suggestion"] = suggestion
    return result


def mask_and_link(text: str, metadata: dict[str, Any], base: dict[str, Any], sequence: int) -> tuple[str, dict[str, str], int, list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return plain-text placeholders plus links/audit records for one DOM node."""
    aliases, books = metadata["aliases"], metadata["books"]
    out, replacements, linked, review = [], {}, [], []
    cursor, serial = 0, sequence
    for match in metadata["alias_re"].finditer(text):
        if match.start() < cursor: continue
        # Spelled ordinals are intentionally not aliases: in this corpus
        # phrases such as "First John Franks" are personal/church names.
        if re.search(r"(?:First|Second|Third)\s+$", text[:match.start()], re.I):
            continue
        book = books[aliases[_alias_key(match.group("alias"))]]
        parsed = parse_group(text, match.end(), book)
        if not parsed:
            if re.match(r"\s*\d", text[match.end():]): review.append(_audit(base, text, match.start(), match.end(), "malformed separator"))
            continue
        end = parsed["end"]
        two_letter = len(re.sub(r"[^A-Za-z]", "", match.group("alias"))) <= 2
        if two_letter and parsed["entries"][0]["kind"] == "chapter":
            review.append(_audit(base, text, match.start(), end, "ambiguous alias")); continue
        resolved, error = resolve(book, parsed)
        if error:
            trailing = text[end:min(len(text), end + 32)]
            classification = "concatenated digits" if re.search(r":\d{3,}\b", text[match.start():end]) else error
            audit_end = end
            word = re.match(r"[A-Za-z]+", trailing)
            if parsed["entries"][0]["kind"] == "chapter" and word:
                classification = "probable non-Scripture text"; audit_end += word.end()
            review.append(_audit(base, text, match.start(), audit_end, classification)); continue
        label = text[match.start():end]
        canonical = f"{book['id']}.{parsed['body']}"
        reader_title = f"{book['name']} {parsed['body'].replace('.', ':', 1)}"
        payload = json.dumps(resolved, separators=(",", ":"))
        first_entry = parsed["entries"][0]
        if first_entry["kind"] == "chapter":
            aria_detail = f"chapter {first_entry['startChapter']}"
        else:
            aria_detail = f"chapter {first_entry['startChapter']}, verse {first_entry['startVerse']}"
        if len(parsed["entries"]) > 1:
            aria_detail += "; and related cited verses"
        aria = f"Open {book['name']} {aria_detail} in the Berean Standard Bible"
        control = (f'<button type="button" class="scripture-ref" data-scripture-ref="{html.escape(canonical, quote=True)}" data-scripture-title="{html.escape(reader_title, quote=True)}" '
                   f'data-scripture-refs="{html.escape(payload, quote=True)}" aria-haspopup="dialog" aria-label="{html.escape(aria, quote=True)}">{label}</button>')
        token = f"__SCRIPTURE_CITATION_{serial}__"; serial += 1
        out.append(text[cursor:match.start()]); out.append(token); replacements[token] = control
        linked.append({**base, "originalText": label, "reference": canonical, "parserForm": parsed["form"], "bsbChapters": [f"{item['book']}.{item['chapter']}" for item in resolved]})
        cursor = end
    out.append(text[cursor:])
    return "".join(out), replacements, len(linked), linked, review, serial


def self_test(metadata: dict[str, Any]) -> None:
    base = {"file": "fixture.html", "url": "fixture.html", "anchor": None, "printedFolio": None}
    text = "Romans 3:21–5:21; John 10:11, 16; Jude 7; 1 Cor. 5:1–5, 13; 14:33, 40; Matthew 18; Titus 1:69; Genesis 2:27; Revelation 5:610; Acts 29 network; First John 3:16; Mt. 5"
    masked, _replacements, count, linked, review, _next = mask_and_link(text, metadata, base, 0)
    assert count == 5
    assert any(item["reference"] == "Rom.3.21-5.21" for item in linked)
    assert any(item["originalText"] == "Jude 7" for item in linked)
    assert "First John 3:16" in masked and "Acts 29 network" in masked
    classifications = {item["classification"] for item in review}
    assert {"invalid bounds", "concatenated digits", "probable non-Scripture text", "ambiguous alias"} <= classifications
