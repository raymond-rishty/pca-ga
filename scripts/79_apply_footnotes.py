"""Apply confirmed footnote links to the published minutes Markdown.

The footnote detector works from PDF/OCR/layout evidence, while the files in
``markdown/`` are the published text.  This pass is the boundary between the
two: it consumes a scan report, locates each marker using the OCR line/context
witness retained in that report, and rewrites the matching note label as a
CommonMark footnote definition.

The default is a dry run.  Use ``--apply`` only after reviewing the generated
report::

    python scripts/79_apply_footnotes.py \
      --report ocr-bakeoff/reports/footnote_scan_all_52_scoped_review_v3.json \
      --gold ocr-bakeoff/benchmark/footnote_gold_marker_sample.json \
      --apply

Only ``confirmed`` links are eligible.  For production edits, pass one or
more explicitly adjudicated gold files with ``--gold``; a broad scan report
alone is intentionally not an authorization to edit the corpus.  A marker
with more than one equally plausible note target is left unchanged and
recorded for review; the pass never invents a note attachment merely because
the number matches.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"<!-- PAGE ga=(\d+) pdf_page=(\d+)\b[^>]*-->")
SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
TYPOGRAPHIC_TRANSLATION = str.maketrans({
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "–": "-",
    "—": "-",
    "−": "-",
})


@dataclass(frozen=True)
class PageChunk:
    page: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Change:
    start: int
    end: int
    replacement: str
    kind: str
    key: str


class CanonicalText:
    """A searchable text shadow with offsets back into the original string."""

    def __init__(self, text: str) -> None:
        chars: list[str] = []
        positions: list[int] = []
        in_tag = False
        pending_space = False
        pending_space_index = 0
        for index, raw in enumerate(text):
            if raw == "<" and not in_tag:
                in_tag = True
                continue
            if in_tag:
                if raw == ">":
                    in_tag = False
                continue
            if raw.isspace():
                pending_space = bool(chars)
                pending_space_index = index
                continue
            if pending_space and chars and chars[-1] != " ":
                chars.append(" ")
                positions.append(pending_space_index)
            pending_space = False
            if raw in "*_`":
                continue
            normalized = unicodedata.normalize("NFKC", raw).translate(SUPERSCRIPT_TRANSLATION)
            normalized = normalized.translate(TYPOGRAPHIC_TRANSLATION)
            normalized = html.unescape(normalized).casefold()
            if not normalized:
                continue
            for character in normalized:
                chars.append(character)
                positions.append(index)
        self.text = "".join(chars)
        self.positions = positions
        self.source = text

    def find(self, needle: str) -> Iterable[tuple[int, int]]:
        value = canonical(needle)
        if not value:
            return []
        result = []
        cursor = 0
        while True:
            found = self.text.find(value, cursor)
            if found < 0:
                break
            end = found + len(value)
            result.append((self.positions[found], self._end_offset(end)))
            cursor = max(end, found + 1)
        return result

    def _end_offset(self, canonical_end: int) -> int:
        if canonical_end <= 0:
            return 0
        if canonical_end >= len(self.positions):
            return len(self.source)
        return self.positions[canonical_end - 1] + 1


def canonical(text: str) -> str:
    shadow = CanonicalText(text)
    return shadow.text


def compact_shadow(shadow: CanonicalText) -> tuple[str, list[int]]:
    """Return an alphanumeric shadow for OCR that inserts spaces inside words."""
    chars = []
    positions = []
    for character, position in zip(shadow.text, shadow.positions):
        if character.isalnum():
            chars.append(character)
            positions.append(position)
    return "".join(chars), positions


def inside_html_table(text: str, offset: int) -> bool:
    """Whether an offset lies inside a raw HTML table block."""
    lower = text.casefold()
    return lower.rfind("<table", 0, offset + 1) > lower.rfind("</table>", 0, offset + 1)


def citation_like_at(text: str, start: int, end: int) -> bool:
    """Reject a final rewrite when the located number is part of a citation."""
    window = canonical(text[max(0, start - 8):end + 8])
    # This is deliberately narrower than the detector's citation model.  It is
    # a last-mile guard against turning forms such as ``Deuteronomy 6:6-9`` or
    # ``BCO 40-5.2`` into Markdown footnote references.
    return bool(re.search(r"(?:\d\s*[:/-]\s*[0-9lIi]|[0-9lIi]\s*[:/-]\s*\d)", window))


def page_chunks(text: str) -> dict[int, PageChunk]:
    markers = list(PAGE.finditer(text))
    if not markers:
        raise ValueError("Markdown has no PAGE markers")
    result: dict[int, PageChunk] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        page = int(marker.group(2))
        result[page] = PageChunk(page, marker.start(), end, text[marker.start():end])
    return result


def volume_from_report(report: dict[str, Any]) -> str:
    value = str(report.get("volume", "")).strip().lower()
    match = re.fullmatch(r"ga\d{2}", value)
    if not match:
        raise ValueError(f"unsupported report volume: {value!r}")
    return value


def markdown_path(volume: str) -> Path:
    matches = sorted((ROOT / "markdown").glob(f"{volume}_*.md"))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one Markdown file for {volume}, found {len(matches)}")
    return matches[0]


def confirmed_links(
    report: dict[str, Any],
    allowed_markers: dict[tuple[str, int], set[str]] | None = None,
) -> list[dict[str, Any]]:
    result = []
    volume = volume_from_report(report)
    for page in report.get("pages", []):
        page_number = int(page.get("page", -1))
        for link in page.get("links", []):
            if link.get("classification", "confirmed") != "confirmed":
                continue
            if allowed_markers is not None:
                values = allowed_markers.get((volume, page_number))
                if values is None or str(link.get("marker_value")) not in values:
                    continue
            result.append(dict(link))
    return result


def load_gold_markers(paths: Iterable[Path]) -> dict[tuple[str, int], set[str]]:
    """Load explicitly adjudicated marker occurrences from one or more gold files."""
    allowed: dict[tuple[str, int], set[str]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        default_volume = str(payload.get("volume", "")).strip().lower().split("_")[0]
        for page in payload.get("pages", []):
            volume = str(page.get("volume") or default_volume).strip().lower().split("_")[0]
            if not re.fullmatch(r"ga\d{2}", volume):
                continue
            values = {str(value) for value in page.get("expected_markers", [])}
            if values:
                allowed.setdefault((volume, int(page["page"])), set()).update(values)
    return allowed


def link_key(link: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(link.get("marker_cluster_id") or ""),
        int(link.get("marker_page", -1)),
        str(link.get("marker_value", "")),
    )


def choose_note_target(links: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    """Choose one target only when the report supplies a deterministic tie-break."""
    if not links:
        return None, "no link"
    marker_page = int(links[0].get("marker_page", -1))
    by_page: dict[int, list[dict[str, Any]]] = {}
    for link in links:
        by_page.setdefault(int(link.get("note_page", -1)), []).append(link)
    distances = {page: abs(page - marker_page) for page in by_page}
    nearest = min(distances.values())
    pages = [page for page, distance in distances.items() if distance == nearest]
    if len(pages) != 1:
        return None, f"equidistant note pages: {pages}"
    candidates = by_page[pages[0]]
    texts = {canonical(str(item.get("note_text", ""))) for item in candidates if item.get("note_text")}
    if len(texts) > 1:
        return None, "multiple note texts on the selected page"
    return candidates[0], None


def marker_change(
    page: PageChunk,
    link: dict[str, Any],
    footnote_id: str,
    allow_missing_marker: bool = False,
) -> Change | None:
    """Locate a marker from its retained OCR line/context witness."""
    line = str(link.get("marker_line_text") or "").strip()
    value = str(link.get("marker_value") or "")
    before = str(link.get("marker_before_text") or "")
    after = str(link.get("marker_after_text") or "")
    if not line or not value:
        return None

    source = CanonicalText(page.text)
    line_value = canonical(line)
    value_value = canonical(value)
    before_value = canonical(before)
    after_value = canonical(after)
    if not line_value or not value_value or not before_value:
        return None

    candidates: list[tuple[int, int, int]] = []
    cursor = 0
    while True:
        found = source.text.find(line_value, cursor)
        if found < 0:
            break
        marker_cursor = max(0, len(before_value) - 2)
        while True:
            marker_in_line = line_value.find(value_value, marker_cursor)
            if marker_in_line < 0:
                break
            marker_start = found + marker_in_line
            marker_end = marker_start + len(value_value)
            left = source.text[max(0, marker_start - len(before_value) - 8):marker_start]
            right = source.text[marker_end:marker_end + len(after_value) + 8]
            score = 0
            if left.endswith(before_value[-min(80, len(before_value)):]):
                score += 3
            # Some OCR witnesses include the marker itself at the end of the
            # retained ``after`` context (``)23`` for a citation followed by
            # a superscript 23).  In that form the preceding context is the
            # useful discriminator; do not reward an earlier citation merely
            # because its following text happens to equal the whole witness.
            if after_value.endswith(value_value) and len(after_value) > len(value_value):
                after_prefix = after_value[:-len(value_value)]
                if left.endswith(after_prefix):
                    score += 8
            elif not after_value or right.startswith(after_value[:80]):
                score += 2
            candidates.append((score, source.positions[marker_start], source._end_offset(marker_end)))
            marker_cursor = marker_in_line + max(1, len(value_value))
        cursor = max(found + 1, found + len(line_value))

    # A formatting renderer can split or wrap the OCR line while preserving its
    # text.  Fall back to the value plus both context sides in the page shadow.
    if not candidates:
        cursor = 0
        before_tail = before_value[-80:]
        after_head = after_value[:80]
        while True:
            found = source.text.find(value_value, cursor)
            if found < 0:
                break
            left = source.text[max(0, found - len(before_tail) - 8):found]
            right = source.text[found + len(value_value):found + len(value_value) + len(after_head) + 8]
            if not before_tail and not after_head:
                cursor = max(found + 1, found + len(value_value))
                continue
            if before_tail and not left.endswith(before_tail):
                cursor = max(found + 1, found + len(value_value))
                continue
            if after_head and not right.startswith(after_head):
                cursor = max(found + 1, found + len(value_value))
                continue
            score = int(bool(before_tail)) + int(bool(after_head))
            if score:
                candidates.append((score, source.positions[found], source._end_offset(found + len(value_value))))
            cursor = max(found + 1, found + len(value_value))

    # Native PDF text occasionally inserts spaces within a word while the
    # published Markdown has the word closed (``D irector``/``Director``).
    # Compare an alphanumeric shadow only after the punctuation-preserving
    # context search failed.
    if not candidates:
        compact_page, compact_positions = compact_shadow(source)
        compact_line = compact_shadow(CanonicalText(line))[0]
        compact_value = compact_shadow(CanonicalText(value))[0]
        compact_before = compact_shadow(CanonicalText(before))[0]
        compact_after = compact_shadow(CanonicalText(after))[0]
        cursor = 0
        while compact_line and compact_value:
            found = compact_page.find(compact_line, cursor)
            if found < 0:
                break
            marker_in_line = compact_line.find(compact_value, max(0, len(compact_before) - 2))
            if marker_in_line >= 0:
                marker_start = found + marker_in_line
                marker_end = marker_start + len(compact_value)
                left = compact_page[max(0, marker_start - len(compact_before) - 8):marker_start]
                right = compact_page[marker_end:marker_end + len(compact_after) + 8]
                if not compact_before and not compact_after:
                    cursor = max(found + 1, found + len(compact_line))
                    continue
                if compact_before and not left.endswith(compact_before[-80:]):
                    cursor = max(found + 1, found + len(compact_line))
                    continue
                if compact_after and not right.startswith(compact_after[:80]):
                    cursor = max(found + 1, found + len(compact_line))
                    continue
                score = int(bool(compact_before)) * 3
                score += int(bool(compact_after)) * 2
                candidates.append((score, compact_positions[marker_start], compact_positions[marker_end - 1] + 1))
            cursor = max(found + 1, found + len(compact_line))

    # A gold adjudication can confirm a visible marker that the published OCR
    # omitted.  Permit insertion only when the retained context identifies a
    # unique preceding phrase (and, when present, following phrase).  This is
    # deliberately disabled for broad scans; extracted-document propagation
    # enables it only after the same link has passed the gold/root gate.
    if not candidates and allow_missing_marker and before_value:
        for before_start, before_end in source.find(before):
            following = CanonicalText(page.text[before_end:])
            if after_value and not following.text.startswith(after_value):
                continue
            end = before_end
            artifact = f"{{{value}}}"
            if page.text[end:end + len(artifact)] == artifact:
                end += len(artifact)
            candidates.append((5, before_end, end))
        if not candidates:
            compact_page, compact_positions = compact_shadow(source)
            compact_before = compact_shadow(CanonicalText(before))[0]
            compact_after = compact_shadow(CanonicalText(after))[0]
            cursor = 0
            while compact_before:
                found = compact_page.find(compact_before, cursor)
                if found < 0:
                    break
                end_index = found + len(compact_before)
                right = compact_page[end_index:end_index + len(compact_after) + 8]
                if compact_after and not right.startswith(compact_after):
                    cursor = found + 1
                    continue
                end = compact_positions[end_index - 1] + 1
                candidates.append((5, end, end))
                cursor = end_index

    if not candidates:
        return None
    candidates.sort(reverse=True)
    best_score = candidates[0][0]
    best = [candidate for candidate in candidates if candidate[0] == best_score]
    if len(best) != 1:
        return None
    start, end = best[0][1:]
    if page.text[max(0, start - 2):start].endswith("[^") or page.text[end:end + 2] == "]":
        return None
    existing_window = page.text[max(0, start - 120):min(len(page.text), end + 120)]
    if (
        f'id="fnref-{footnote_id}"' in existing_window
        and f'href="#{footnote_id}"' in existing_window
    ):
        return None
    citation_boundary = page.text[max(0, start - 3):start].rstrip()
    if citation_like_at(page.text, start, end) and not (
        allow_missing_marker and citation_boundary.endswith((".", ")", ",", ";"))
    ):
        return None
    if inside_html_table(page.text, start):
        replacement = f'<sup id="fnref-{footnote_id}"><a href="#{footnote_id}">{value}</a></sup>'
        kind = "marker_html"
    else:
        replacement = f"[^{footnote_id}]"
        kind = "marker"
    return Change(start, end, replacement, kind, link_key(link)[0])


def note_change(
    page: PageChunk,
    link: dict[str, Any],
    footnote_id: str,
    html_style: bool = False,
    allow_missing_label: bool = False,
) -> Change | None:
    value = str(link.get("marker_value") or "")
    note_text = str(link.get("note_text") or "")
    if not value:
        return None
    if f'[^{footnote_id}]:' in page.text or f'<a id="{footnote_id}"></a>' in page.text:
        return None
    source = CanonicalText(page.text)
    # A report can contain only the native label (for example ``2``) or OCR
    # spacing that differs from the published text (``Herm an`` versus
    # ``Herman``).  Prefer an exact non-trivial text anchor; otherwise rank
    # label-shaped occurrences by similarity to the retained note prose.
    exact = list(source.find(note_text)) if len(canonical(note_text)) > len(canonical(value)) + 3 else []
    exact_labels = []
    for start, _ in exact:
        label = re.match(rf"{re.escape(value)}[.)]?", page.text[start:])
        if label:
            exact_labels.append((start, start + len(label.group(0))))
    target_tail = re.sub(rf"^\s*{re.escape(value)}[.)]?\s*", "", canonical(note_text))
    # A PDF/OCR note block can concatenate the next numbered note onto the
    # retained text.  Use only the first note body as the anchor; otherwise a
    # definition for 57 can accidentally absorb the visible label for 58.
    raw_target_tail = target_tail
    target_tail = re.split(r"\s+[1-9]\d{0,2}[,.)]?\s+(?=[A-Za-z\"'])", target_tail, maxsplit=1)[0]
    split_concatenated_note = target_tail != raw_target_tail
    labels: list[tuple[float, int, int]] = []
    # When the scan retains only a bare numeric note label (for example
    # ``23``), inline occurrences of that number are common elsewhere on the
    # page.  In gold-gated production application, prefer one unique label at
    # the start of a lower-page note line over those inline occurrences.
    if allow_missing_label and canonical(note_text) == canonical(value):
        raw_pattern = re.compile(rf"(?m)^[ \t]*{re.escape(value)}[.)]?(?=\s+[A-Za-z\"'])")
        raw_labels = [
            (2.0, match.start() + len(match.group(0)) - len(value), match.start() + len(match.group(0)))
            for match in raw_pattern.finditer(page.text)
            if match.start() >= len(page.text) * 0.60
        ]
        if len(raw_labels) == 1:
            labels.extend(raw_labels)
    # OCR frequently inserts or drops a space between the numeric label and a
    # quoted note body (``3 "Did`` versus ``3"Did``).  When the full note
    # string is not an exact match, anchor on the note body and require the
    # expected value immediately before it on the same source line.
    if len(target_tail) >= 8:
        tail = target_tail[:160]
        for body_start, _ in source.find(tail):
            line_start = page.text.rfind("\n", 0, body_start) + 1
            prefix = page.text[line_start:body_start]
            prefix_shadow = CanonicalText(prefix)
            label_match = re.search(rf"(?<!\w){re.escape(canonical(value))}[.)]?\s*$", prefix_shadow.text)
            if label_match:
                start = line_start + prefix_shadow.positions[label_match.start()]
                labels.append((2.0, start, body_start))
    pattern = re.compile(rf"(?<![\w]){re.escape(canonical(value))}[.)]?(?=\s+[A-Za-z\"'])")
    for match in pattern.finditer(source.text):
        context = source.text[match.end():match.end() + max(80, len(target_tail) + 20)]
        score = 1.0 if not target_tail else difflib.SequenceMatcher(None, target_tail[:120], context[:120]).ratio()
        labels.append((score, source.positions[match.start()], source._end_offset(match.end())))
    if exact_labels:
        labels.extend((1.0, start, end) for start, end in exact_labels)
    if not labels and allow_missing_label:
        # Some published pages retain only a bare label plus note prose
        # (``13 By this logic...``), while the scan's note witness likewise
        # contains only ``13``.  The canonical shadow collapses page line
        # boundaries, so the normal label search can confuse that definition
        # with a body reference.  A gold-gated fallback may use one unique
        # label-shaped line in the lower part of the page; requiring a raw
        # line start prevents ordinary inline references from qualifying.
        raw_pattern = re.compile(rf"(?m)^[ \t]*{re.escape(value)}[.)]?(?=\s+[A-Za-z\"'])")
        raw_labels = [
            (2.0, match.start() + len(match.group(0)) - len(value), match.start() + len(match.group(0)))
            for match in raw_pattern.finditer(page.text)
            if match.start() >= len(page.text) * 0.60
        ]
        if len(raw_labels) == 1:
            labels.extend(raw_labels)
    if not labels and allow_missing_label and html_style and len(target_tail) >= 8:
        for body_start, _ in source.find(target_tail[:160]):
            line_start = page.text.rfind("\n", 0, body_start) + 1
            if not canonical(page.text[line_start:body_start]).strip():
                labels.append((2.0, body_start, body_start))
    if not labels:
        return None
    unique_labels: dict[tuple[int, int], float] = {}
    for score, start, end in labels:
        unique_labels[(start, end)] = max(score, unique_labels.get((start, end), 0.0))
    labels = [(score, start, end) for (start, end), score in unique_labels.items()]
    labels.sort(reverse=True)
    best_score = labels[0][0]
    selected = [item for item in labels if item[0] >= best_score - 0.03]
    if len(selected) != 1:
        return None
    _, start, end = selected[0]
    replacement = (
        f'<a id="{footnote_id}"></a><sup>{value}</sup>'
        if html_style
        else f"[^{footnote_id}]:"
    )
    # The body-anchor path may consume the whitespace after the OCR label;
    # keep a separator so the definition remains readable and valid.
    if end > start and page.text[end - 1].isspace():
        replacement += " "
    elif start == end and allow_missing_label and html_style:
        replacement += " "
    change_end = end
    if split_concatenated_note:
        line_end = page.text.find("\n", end)
        if line_end < 0:
            line_end = len(page.text)
        remainder = page.text[end:line_end]
        remainder_shadow = CanonicalText(remainder)
        split_match = re.search(
            r"\s+[1-9]\d{0,2}[,.)]?\s+(?=[A-Za-z\"'])",
            remainder_shadow.text,
        )
        if split_match and split_match.start() >= max(0, len(target_tail) - 2):
            body_end = end + remainder_shadow.positions[split_match.start()]
            replacement += page.text[end:body_end].rstrip() + "\n\n"
            change_end = body_end
    if start and page.text[start - 1] not in "\r\n":
        replacement = "\n\n" + replacement
    return Change(start, change_end, replacement, "definition", f"{page.page}:{value}")


def apply_changes(text: str, changes: list[Change]) -> str:
    ordered = sorted(changes, key=lambda item: (item.start, item.end), reverse=True)
    previous_start = len(text) + 1
    for change in ordered:
        if change.end > previous_start:
            raise ValueError(f"overlapping footnote changes near offset {change.start}")
        text = text[:change.start] + change.replacement + text[change.end:]
        previous_start = change.start
    return text


def apply_volume_text(
    volume: str,
    text: str,
    links: list[dict[str, Any]],
    allow_gold_fallback: bool = False,
) -> tuple[str, dict[str, Any]]:
    pages = page_chunks(text)
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for link in links:
        grouped.setdefault(link_key(link), []).append(link)

    changes: dict[int, list[Change]] = {}
    marker_changes: dict[int, list[tuple[Change, tuple[int, str]]]] = {}
    failures: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    definitions: dict[tuple[int, str], str] = {}

    for key, marker_links in grouped.items():
        selected, reason = choose_note_target(marker_links)
        if reason or selected is None:
            skipped.append({"marker": key, "reason": reason})
            continue
        marker_page = int(selected["marker_page"])
        note_page = int(selected["note_page"])
        value = str(selected["marker_value"])
        footnote_id = f"fn-{volume}-p{note_page}-n{value}"
        marker = marker_change(
            pages[marker_page], selected, footnote_id,
            allow_missing_marker=allow_gold_fallback,
        )
        if marker is None:
            failures.append({"marker": key, "kind": "marker", "page": marker_page, "value": value})
            continue
        marker_changes.setdefault(marker_page, []).append((marker, (note_page, value)))
        definitions.setdefault((note_page, value), footnote_id)

    failed_definitions: set[tuple[int, str]] = set()
    html_definitions: set[tuple[int, str]] = {
        note_key
        for pending in marker_changes.values()
        for change, note_key in pending
        if change.kind == "marker_html"
    }
    for (note_page, value), footnote_id in definitions.items():
        # Pick the first link for this note target so its retained note text is
        # used as the textual anchor.  A different marker page can point to
        # the same definition without creating another definition.
        link = next(
            link
            for marker_links in grouped.values()
            for link in marker_links
            if int(link.get("note_page", -1)) == note_page and str(link.get("marker_value")) == value
        )
        definition = note_change(
            pages[note_page],
            link,
            footnote_id,
            html_style=(note_page, value) in html_definitions,
            allow_missing_label=allow_gold_fallback,
        )
        if definition is None:
            failed_definitions.add((note_page, value))
            failures.append({"note": f"{note_page}:{value}", "kind": "definition", "page": note_page, "value": value})
            continue
        changes.setdefault(note_page, []).append(definition)

    for page_number, pending in marker_changes.items():
        changes.setdefault(page_number, []).extend(
            change
            for change, note_key in pending
            if note_key not in failed_definitions
        )

    updated = text
    applied_pages = 0
    applied_markers = 0
    applied_definitions = 0
    for page_number, page_changes in sorted(changes.items(), reverse=True):
        page = pages[page_number]
        try:
            new_chunk = apply_changes(page.text, page_changes)
        except ValueError as exc:
            failures.append({
                "page": page_number,
                "kind": "overlapping_changes",
                "reason": str(exc),
            })
            continue
        if new_chunk != page.text:
            updated = updated[:page.start] + new_chunk + updated[page.end:]
            # Earlier absolute offsets are no longer valid after a page-size
            # change, so callers must apply pages from the end of the document.
            applied_pages += 1
            applied_markers += sum(change.kind.startswith("marker") for change in page_changes)
            applied_definitions += sum(change.kind == "definition" for change in page_changes)
            pages = page_chunks(updated)

    summary = {
        "volume": volume,
        "links": len(links),
        "unique_markers": len(grouped),
        "definitions": len(definitions),
        "changed_pages": applied_pages,
        "applied_markers": applied_markers,
        "applied_definitions": applied_definitions,
        "failures": failures,
        "skipped_ambiguous": skipped,
    }
    return updated, summary


def repair_concatenated_definitions(
    volume: str,
    text: str,
    expected_by_page: dict[int, set[str]],
    note_texts_by_page: dict[int, dict[str, str]] | None = None,
) -> tuple[str, int]:
    """Separate a following gold note label that OCR left on an applied line.

    Some source note blocks are emitted as one physical line (``4 ... 5 ...``).
    The first confirmed definition can therefore otherwise absorb the next
    visible label.  This repair only considers values on an adjudicated page
    and only inserts a separator; it does not create a new footnote link.
    """
    pages = page_chunks(text)
    changes: dict[int, list[Change]] = {}
    definition_pattern = re.compile(
        rf"^\[\^fn-{re.escape(volume)}-p(?P<page>\d+)-n(?P<value>[^]]+)\]:|"
        rf"^<a id=\"fn-{re.escape(volume)}-p(?P<html_page>\d+)-n(?P<html_value>[^\"]+)\"></a>"
    )
    repaired = 0
    for page_number, page in pages.items():
        expected = expected_by_page.get(page_number, set())
        if len(expected) < 2:
            continue
        for line_match in re.finditer(r"[^\r\n]*", page.text):
            line = line_match.group(0)
            definition = definition_pattern.match(line)
            if not definition:
                continue
            value = definition.group("value") or definition.group("html_value")
            later_values = sorted(
                (candidate for candidate in expected if candidate.isdigit() and int(candidate) > int(value)),
                key=int,
            )
            if not later_values:
                continue
            body_offset = line_match.start() + definition.end()
            body = line[definition.end():]
            shadow = CanonicalText(body)
            for later in later_values:
                note_text = (note_texts_by_page or {}).get(page_number, {}).get(later, "")
                note_body = re.sub(rf"^\s*{re.escape(later)}[.)]?\s*", "", note_text).strip()
                if note_body:
                    anchor = canonical(note_body[:160])
                    anchor_match = next(iter(shadow.find(anchor)), None) if anchor else None
                    if anchor_match is None:
                        continue
                    anchor_start = next(
                        index for index, position in enumerate(shadow.positions)
                        if position == anchor_match[0]
                    )
                    label_match = re.search(
                        rf"(?P<separator>\s+){re.escape(canonical(later))}[,.)]?\s*$",
                        shadow.text[:anchor_start],
                    )
                    if not label_match:
                        continue
                    label_start = label_match.start("separator")
                    source_start = body_offset + shadow.positions[label_start]
                    source_label = body_offset + shadow.positions[
                        label_start + len(label_match.group("separator"))
                    ]
                    changes.setdefault(page_number, []).append(
                        Change(
                            source_start,
                            source_label,
                            "\n\n",
                            "definition_repair",
                            f"{page_number}:{value}->{later}",
                        )
                    )
                    repaired += 1
                    break
                if note_texts_by_page is not None:
                    # A gold-covered later note without a retained body anchor is
                    # not enough evidence to split a citation containing the same
                    # number. Leave it for review.
                    continue
                separator = re.search(
                    rf"\s+{re.escape(canonical(later))}[,.)]?\s+(?=[A-Za-z\"'])",
                    shadow.text,
                )
                if not separator:
                    continue
                # Map the source range up to the label while preserving the
                # label itself (and its punctuation, if any).
                label_offset = separator.start() + separator.group(0).find(canonical(later))
                source_start = body_offset + shadow.positions[separator.start()]
                source_label = body_offset + shadow.positions[label_offset]
                changes.setdefault(page_number, []).append(
                    Change(source_start, source_label, "\n\n", "definition_repair", f"{page_number}:{value}->{later}")
                )
                repaired += 1
                break
    if not changes:
        return text, 0
    updated = text
    for page_number, page_changes in sorted(changes.items(), reverse=True):
        page = page_chunks(updated)[page_number]
        updated = updated[:page.start] + apply_changes(page.text, page_changes) + updated[page.end:]
    return updated, repaired


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="Footnote scan report with v3 link context.")
    parser.add_argument("--ga", help="Optional comma-separated assemblies, e.g. ga14,ga40.")
    parser.add_argument(
        "--gold",
        help="Optional comma-separated adjudicated gold JSON files; restrict application to their expected markers.",
    )
    parser.add_argument("--apply", action="store_true", help="Write updated markdown files; default is dry-run.")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "footnote_apply_report.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    if payload.get("schema") != "pca-ga.footnote-corpus-scan.v3":
        raise ValueError(
            "footnote application requires pca-ga.footnote-corpus-scan.v3; "
            "rerun scan_footnote_corpus.py so marker/note text witnesses are present"
        )
    requested = {item.strip().lower() for item in args.ga.split(",")} if args.ga else None
    gold_paths = [Path(item.strip()) for item in args.gold.split(",")] if args.gold else []
    if args.apply and not gold_paths:
        raise ValueError("--apply requires at least one adjudicated --gold file")
    allowed_markers = load_gold_markers(gold_paths) if gold_paths else None
    volume_results = []
    for raw_report in payload.get("reports", []):
        volume = volume_from_report(raw_report)
        if requested and volume not in requested:
            continue
        target = markdown_path(volume)
        original = target.read_text(encoding="utf-8")
        updated, summary = apply_volume_text(
            volume,
            original,
            confirmed_links(raw_report, allowed_markers),
            allow_gold_fallback=allowed_markers is not None,
        )
        repaired = 0
        if allowed_markers is not None:
            expected_by_page = {
                page: values
                for (allowed_volume, page), values in allowed_markers.items()
                if allowed_volume == volume
            }
            note_texts_by_page: dict[int, dict[str, str]] = {}
            for link in confirmed_links(raw_report, allowed_markers):
                note_page = int(link.get("note_page", -1))
                value = str(link.get("marker_value", ""))
                note_text = str(link.get("note_text", ""))
                if note_text and value:
                    note_texts_by_page.setdefault(note_page, {}).setdefault(value, note_text)
            updated, repaired = repair_concatenated_definitions(
                volume, updated, expected_by_page, note_texts_by_page
            )
        summary["repaired_definitions"] = repaired
        summary["markdown"] = str(target.relative_to(ROOT))
        summary["applied"] = bool(args.apply and updated != original)
        if args.apply and updated != original:
            target.write_text(updated, encoding="utf-8")
        volume_results.append(summary)
        print(json.dumps(summary, sort_keys=True))
    result = {
        "schema": "pca-ga.footnote-markdown-apply.v1",
        "source_report": str(args.report),
        "gold": [str(path) for path in gold_paths],
        "apply": bool(args.apply),
        "reports": volume_results,
        "links": sum(item["links"] for item in volume_results),
        "unique_markers": sum(item["unique_markers"] for item in volume_results),
        "definitions": sum(item["definitions"] for item in volume_results),
        "applied_markers": sum(item["applied_markers"] for item in volume_results),
        "applied_definitions": sum(item["applied_definitions"] for item in volume_results),
        "repaired_definitions": sum(item.get("repaired_definitions", 0) for item in volume_results),
        "failures": sum(len(item["failures"]) for item in volume_results),
        "skipped_ambiguous": sum(len(item["skipped_ambiguous"]) for item in volume_results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("reports", "links", "unique_markers", "definitions", "applied_markers", "applied_definitions", "repaired_definitions", "failures", "skipped_ambiguous")}, indent=2))


if __name__ == "__main__":
    main()
