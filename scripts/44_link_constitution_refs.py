#!/usr/bin/env python3
"""Link constitutional references in rendered PCA-GA HTML and emit preview data.

The PCA Constitution Reader remains the source of truth. This script reads its
content files during the Pages build, emits a small section index plus one JSON
payload per numbered BCO chapter and compact Westminster Standards payloads,
then converts explicit citation clusters in the rendered site into links with
in-page text previews.

Examples:
  BCO 25-5
  B.C.O. 31–2 and 31-5
  See also BCO 5-9.c, 8-4, 13-2, 13-10
  WCF 28-4; WLC 166B; WSC 95B; RAO 16-3.e.5

Lettered subparagraphs retain their visible label but resolve to their enclosing
chapter-and-section record (5-9.c -> 5-9).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import sys
import tempfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

READER_BASE = "https://raymond-rishty.github.io/pca-constitution-reader/"
DASH = r"[-\u2010\u2011\u2012\u2013\u2014\u2212]"
BCO_PREFIX = r"(?:B\.?\s*C\.?\s*O\.?|Book\s+of\s+Church\s+Order)"
WCF_PREFIX = r"W\.?\s*C\.?\s*F\.?"
WLC_PREFIX = r"W\.?\s*L\.?\s*C\.?"
WSC_PREFIX = r"W\.?\s*S\.?\s*C\.?"
RAO_PREFIX = r"(?:[\"“]\s*)?(?:R\.?\s*A\.?\s*O\.?|Rules?\s+of\s+Assembly\s+Operations?)(?:\s*[\"”])?"
PREFIX = rf"(?:{BCO_PREFIX}|{WCF_PREFIX}|{WLC_PREFIX}|{WSC_PREFIX}|{RAO_PREFIX})"
BCO_REF = rf"\d{{1,2}}\s*{DASH}\s*\d{{1,2}}(?:\s*(?:\.\s*[A-Za-z]|\(\s*[A-Za-z]\s*\)))?"
WCF_REF = rf"\d{{1,2}}\s*(?:\.|{DASH})\s*\d{{1,2}}(?:\s*(?:\.\s*[A-Za-z]|\(\s*[A-Za-z]\s*\)))?"
CATECHISM_REF = r"(?:Q\.?\s*)?\d{1,3}(?:\s*(?:[A-Za-z]|\(\s*[A-Za-z]\s*\)))?"
RAO_SECTION_SEP = rf"(?:{DASH}|[.:])"
RAO_NUMERIC_REF = rf"\d{{1,2}}(?:\s*{RAO_SECTION_SEP}\s*\d{{1,2}})?"
RAO_ROMAN_REF = r"[IVXLCDM]{1,7}"
# Historical minutes vary between hyphens, dots, and colons; some also omit
# punctuation before a lettered subparagraph (for example ``14-3c.8``).
RAO_REF = rf"(?:{RAO_NUMERIC_REF}|(?:(?:Article|Section)\s+)?{RAO_ROMAN_REF})(?:\s*(?:[.\-]\s*|(?<=[0-9])(?=[A-Za-z]))[A-Za-z0-9]+|\s*\(\s*[A-Za-z0-9]+\s*\))*(?!\d)"
OTHER_PREFIX = rf"(?:{BCO_PREFIX}|{WCF_PREFIX}|{WLC_PREFIX}|{WSC_PREFIX})"
OTHER_REF = rf"(?:{BCO_REF}|{WCF_REF}|{CATECHISM_REF})"
REF = rf"(?:{RAO_REF}|{OTHER_REF})"
SEP = r"(?:\s*,\s*|\s*;\s*|\s+(?:and|or)\s+)"
CLUSTER_RE = re.compile(
    rf"\b(?:(?P<rao_prefix>{RAO_PREFIX})\s+(?:§\s*)?{RAO_REF}(?:{SEP}(?:§\s*)?{RAO_REF})*|"
    rf"(?P<other_prefix>{OTHER_PREFIX})\s+{OTHER_REF}(?:{SEP}{OTHER_REF})*)",
    re.IGNORECASE,
)
PREFIX_RE = re.compile(rf"\b{PREFIX}\b", re.IGNORECASE)
REF_RE_BY_BOOK = {
    "bco": re.compile(BCO_REF, re.IGNORECASE),
    "wcf": re.compile(WCF_REF, re.IGNORECASE),
    "wlc": re.compile(CATECHISM_REF, re.IGNORECASE),
    "wsc": re.compile(CATECHISM_REF, re.IGNORECASE),
    "rao": re.compile(RAO_REF, re.IGNORECASE),
}
BCO_CANON_RE = re.compile(rf"(\d{{1,2}})\s*{DASH}\s*(\d{{1,2}})", re.IGNORECASE)
WCF_CANON_RE = re.compile(rf"(\d{{1,2}})\s*(?:\.|{DASH})\s*(\d{{1,2}})", re.IGNORECASE)
CATECHISM_CANON_RE = re.compile(r"(?:Q\.?\s*)?(\d{1,3})", re.IGNORECASE)
RAO_CANON_RE = re.compile(rf"(\d{{1,2}})(?:\s*{RAO_SECTION_SEP}\s*(\d{{1,2}}))?", re.IGNORECASE)

# Minutes citations are deliberately narrower than the loose formats accepted by
# the research indexes.  A link should only be made when it names both a volume
# and a single printed page; ranges and bare volume references remain plain text.
MINUTES_CITATION_RE = re.compile(
    r"\bM\s*(?P<ga>\d{1,2})\s*GA\s*,?\s*"
    r"(?:p(?:age)?\.?\s*)(?P<page>\d{1,4})\b",
    re.IGNORECASE,
)
MINUTES_PAGE_RE = re.compile(
    r'<a\s+id=["\'](?P<anchor>ga(?P<anchor_ga>\d+)-p[^"\']+)["\']></a>\s*'
    r'<!--\s*PAGE\s+ga=(?P<ga>\d+)\s+pdf_page=(?P<pdf_page>\d+)\s+'
    r'printed_page=(?P<printed_page>\d+)\s*-->',
    re.IGNORECASE,
)

EXCLUDED_TAGS = {"a", "code", "pre", "script", "style", "textarea", "noscript"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
INLINE_CITATION_PREFIX_RE = re.compile(
    rf"<(?P<tag>em|i|strong|b)\b[^>]*>\s*(?P<prefix>{PREFIX})\s*</(?P=tag)>"
    rf"(?=(?:\s|&nbsp;)*(?:§|&sect;)?(?:\s|&nbsp;)*(?:\d|(?:Article|Section)\s+{RAO_ROMAN_REF}\b))",
    re.IGNORECASE,
)


def normalize_inline_citation_prefixes(rendered_html: str) -> str:
    """Make an emphasized citation abbreviation available to the text linker.

    Markdown commonly renders ``_RAO_ 16-3`` as two separate HTML text nodes.
    The linker works inside text nodes so it cannot otherwise see the prefix and
    number as one citation. Citation abbreviations are normalized to plain text;
    the generated citation link still preserves the visible wording.
    """
    rendered_html = INLINE_CITATION_PREFIX_RE.sub(
        lambda match: match.group("prefix"), rendered_html
    )
    return re.sub(
        rf"(?P<prefix>{RAO_PREFIX})(?:\s|&nbsp;)+(?:§|&sect;)(?:\s|&nbsp;)*",
        lambda match: f"{match.group('prefix')} § ",
        rendered_html,
        flags=re.IGNORECASE,
    )


def load_bco(path: Path) -> tuple[dict[str, Any], str]:
    source = path.read_text(encoding="utf-8")
    marker = "window.BCO ="
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"{path} does not define {marker!r}")
    start += len(marker)
    end = source.find(";\nwindow.BCO_ORDER", start)
    if end < 0:
        end = source.rfind("};")
        if end < 0:
            raise ValueError(f"Could not find the end of window.BCO in {path}")
        end += 1
    data = json.loads(source[start:end].strip())
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return data, digest


def load_window_json(path: Path, variable: str) -> Any:
    """Read a JSON-valued ``window.VARIABLE = …`` assignment from the reader."""
    source = path.read_text(encoding="utf-8")
    marker = f"window.{variable} ="
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"{path} does not define {marker!r}")
    value = source[start + len(marker):].lstrip()
    return json.JSONDecoder().raw_decode(value)[0]


def load_bundled_book_pack(path: Path, key: str) -> dict[str, Any]:
    """Load one JSON pack passed to ``window.BUNDLED_PACKS.push(…)``."""
    source = path.read_text(encoding="utf-8")
    marker = "window.BUNDLED_PACKS.push("
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"{path} does not define a bundled book pack")
    value = source[start + len(marker):].lstrip()
    pack = json.JSONDecoder().raw_decode(value)[0]
    if pack.get("component", {}).get("key") != key:
        raise ValueError(f"{path} does not contain the {key!r} book pack")
    return pack


def canonical_ref(book: str, token: str) -> str | None:
    if book == "bco":
        match = BCO_CANON_RE.search(token)
        return f"{int(match.group(1))}-{int(match.group(2))}" if match else None
    if book == "wcf":
        match = WCF_CANON_RE.search(token)
        return f"{int(match.group(1))}.{int(match.group(2))}" if match else None
    if book in {"wlc", "wsc"}:
        match = CATECHISM_CANON_RE.search(token)
        return f"Q.{int(match.group(1))}" if match else None
    if book == "rao":
        match = RAO_CANON_RE.search(token)
        if match:
            return f"{int(match.group(1))}-{int(match.group(2))}" if match.group(2) else str(int(match.group(1)))
        roman = re.search(RAO_ROMAN_REF, token, re.IGNORECASE)
        if roman:
            value = roman_to_int(roman.group(0))
            return str(value) if value else None
        return None
    return None


def roman_to_int(value: str) -> int | None:
    """Convert the small Roman-numeral RAO article references found in minutes."""
    numerals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for character in reversed(value.upper()):
        current = numerals.get(character)
        if current is None:
            return None
        total += -current if current < previous else current
        previous = max(previous, current)
    return total if 1 <= total <= 20 else None


def citation_book(prefix: str) -> str:
    compact = re.sub(r"[^a-z]", "", prefix.lower())
    if compact in {"bco", "bookofchurchorder"}:
        return "bco"
    if compact in {"rao", "rulesofassemblyoperation", "rulesofassemblyoperations"}:
        return "rao"
    return compact


def build_minutes_page_index(
    site_dir: Path,
) -> tuple[dict[str, dict[str, dict[str, str]]], dict[str, Any]]:
    """Index printed-page anchors in rendered minute volumes.

    The minutes themselves remain the source of truth.  This compact build
    artifact records only reliable, detected printed folios and the rendered
    anchor that represents each one.  It is used for citations now and gives a
    future in-page reader a stable page locator without guessing PDF offsets.
    """
    refs: dict[str, dict[str, dict[str, str]]] = {}
    volumes: dict[str, dict[str, Any]] = {}

    for path in sorted((site_dir / "markdown").glob("ga*_*.html")):
        rel_path = path.relative_to(site_dir).as_posix()
        for match in MINUTES_PAGE_RE.finditer(path.read_text(encoding="utf-8")):
            ga = str(int(match.group("ga")))
            printed_page = str(int(match.group("printed_page")))
            if ga != str(int(match.group("anchor_ga"))):
                continue

            entry = {
                "path": rel_path,
                "anchor": match.group("anchor"),
                "pdf_page": match.group("pdf_page"),
            }
            # A volume's printed folio is expected to be unique.  Keep the
            # first occurrence if a malformed source duplicates it.
            refs.setdefault(ga, {}).setdefault(printed_page, entry)
            volume = volumes.setdefault(ga, {"source": rel_path, "pages": {}})
            volume["pages"].setdefault(printed_page, {
                "anchor": entry["anchor"],
                "pdf_page": int(entry["pdf_page"]),
            })

    payload = {
        "version": 1,
        "source": "rendered markdown minute volumes",
        "volumes": volumes,
    }
    return refs, payload


def minutes_href(file_name: str, target: dict[str, str]) -> str:
    """Return a site-relative deep link from one rendered page to a minute page."""
    source_dir = posixpath.dirname(file_name) or "."
    target_path = posixpath.relpath(target["path"], start=source_dir)
    return f"{target_path}#{target['anchor']}"


def linkify_minutes_text(
    text: str,
    minutes_refs: dict[str, dict[str, dict[str, str]]],
    file_name: str,
) -> tuple[str, int]:
    if not MINUTES_CITATION_RE.search(text):
        return text, 0

    pieces: list[str] = []
    cursor = 0
    linked = 0
    for match in MINUTES_CITATION_RE.finditer(text):
        pieces.append(text[cursor:match.start()])
        ga = str(int(match.group("ga")))
        page = str(int(match.group("page")))
        target = minutes_refs.get(ga, {}).get(page)
        label = match.group(0)
        if target:
            href = minutes_href(file_name, target)
            pieces.append(
                f'<a class="minutes-ref" href="{html.escape(href, quote=True)}" '
                f'data-minutes-ga="{ga}" data-minutes-page="{page}" '
                f'title="Open M{ga}GA printed page {page} in the minutes">{label}</a>'
            )
            linked += 1
        else:
            pieces.append(label)
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces), linked


def build_standard_refs(
    wcf: dict[str, Any],
    wlc: list[dict[str, Any]],
    wsc: list[dict[str, Any]],
) -> dict[str, set[str]]:
    return {
        "wcf": {
            str(section.get("ref"))
            for chapter in wcf.values()
            for section in chapter.get("sections") or []
            if re.fullmatch(r"\d{1,2}\.\d{1,2}", str(section.get("ref") or ""))
        },
        "wlc": {f"Q.{int(item['n'])}" for item in wlc if str(item.get("n", "")).isdigit()},
        "wsc": {f"Q.{int(item['n'])}" for item in wsc if str(item.get("n", "")).isdigit()},
    }


def build_standard_preview_data(
    wcf: dict[str, Any],
    wlc: list[dict[str, Any]],
    wsc: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    """Emit one lazy preview payload for each Westminster standard."""
    standard_dir = output_dir / "standards"
    standard_dir.mkdir(parents=True, exist_ok=True)

    wcf_sections: dict[str, dict[str, str]] = {}
    for chapter, record in wcf.items():
        for section in record.get("sections") or []:
            ref = str(section.get("ref") or "")
            if re.fullmatch(r"\d{1,2}\.\d{1,2}", ref):
                wcf_sections[ref] = {
                    "chapter": str(chapter),
                    "chapterTitle": str(record.get("title") or ""),
                    "body": str(section.get("body") or ""),
                }

    def catechism_sections(items: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
        return {
            f"Q.{int(item['n'])}": {
                "question": str(item.get("q") or ""),
                "answer": str(item.get("a") or ""),
            }
            for item in items
            if str(item.get("n", "")).isdigit()
        }

    payloads = {
        "wcf": {"version": 1, "book": "wcf", "sections": wcf_sections},
        "wlc": {"version": 1, "book": "wlc", "sections": catechism_sections(wlc)},
        "wsc": {"version": 1, "book": "wsc", "sections": catechism_sections(wsc)},
    }
    for book, payload in payloads.items():
        (standard_dir / f"{book}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )


def build_rao_preview_data(rao: dict[str, Any], output_dir: Path) -> dict[str, dict[str, str]]:
    """Emit the current RAO as a supplementary (not constitutional) preview pack."""
    sections: dict[str, dict[str, str]] = {}
    for article in rao.get("order") or []:
        chapter = (rao.get("chapters") or {}).get(str(article), {})
        for section in chapter.get("sections") or []:
            ref = str(section.get("ref") or "")
            if not ref:
                continue
            sections[ref] = {
                "article": str(article),
                "articleTitle": str(chapter.get("title") or ""),
                "body": render_section_body(section),
            }
    pack_dir = output_dir / "packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "book": "rao",
        "name": "Rules of Assembly Operations",
        "edition": "Revisions adopted through the 52nd General Assembly (2025)",
        "nonConstitutional": True,
        "sections": sections,
    }
    (pack_dir / "rao.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return sections


def render_section_body(section: dict[str, Any]) -> str:
    """Render the Constitution Reader's structured blocks without flattening them."""
    blocks = section.get("blocks") or []
    if not blocks:
        return str(section.get("body") or "")

    rendered: list[str] = []
    start = 0
    first = blocks[0] if blocks else None
    if first and len(first) >= 3 and first[0] == "p" and int(first[1]) == 0:
        rendered.append(f'<p class="lead">{first[2]}</p>')
        start = 1

    for block in blocks[start:]:
        if not block or len(block) < 3:
            continue
        kind = str(block[0])
        try:
            depth = max(0, min(int(block[1]), 4))
        except (TypeError, ValueError):
            depth = 0
        if kind == "p":
            rendered.append(f'<p class="bpara d{depth}">{block[2]}</p>')
        elif len(block) >= 4:
            marker_text = html.escape(str(block[2]))
            rendered.append(
                f'<div class="li d{depth}"><span class="mk">{marker_text}</span> {block[3]}</div>'
            )

    return "".join(rendered)


def build_reference_data(
    bco: dict[str, Any],
    output_dir: Path,
    source_digest: str,
) -> dict[str, dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chapter_dir = output_dir / "chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    refs: dict[str, dict[str, str]] = {}
    chapters: dict[str, dict[str, Any]] = {}

    for chapter, record in bco.items():
        if not str(chapter).isdigit():
            continue
        section_payload: dict[str, dict[str, str]] = {}
        for section in record.get("sections") or []:
            ref = str(section.get("ref") or "")
            if not re.fullmatch(r"\d{1,2}-\d{1,2}", ref):
                continue
            body = render_section_body(section)
            section_payload[ref] = {"body": body}
            refs[ref] = {
                "chapter": str(chapter),
                "chapterTitle": str(record.get("title") or ""),
            }

        if not section_payload:
            continue

        chapter_payload = {
            "version": 2,
            "chapter": str(chapter),
            "title": str(record.get("title") or ""),
            "sections": section_payload,
        }
        chapters[str(chapter)] = {
            "title": chapter_payload["title"],
            "sections": list(section_payload),
        }
        (chapter_dir / f"{chapter}.json").write_text(
            json.dumps(chapter_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    index_payload = {
        "version": 1,
        "source": "pca-constitution-reader/content/bco.js",
        "sourceSha256": source_digest,
        "chapters": chapters,
        "sections": refs,
    }
    (output_dir / "bco-index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return refs


def linkify_text(
    text: str,
    bco_refs: dict[str, dict[str, str]],
    standard_refs: dict[str, set[str]],
    rao_refs: dict[str, dict[str, str]],
    unresolved: list[dict[str, str]],
    file_name: str,
) -> tuple[str, int]:
    if not PREFIX_RE.search(text):
        return text, 0

    pieces: list[str] = []
    cursor = 0
    linked = 0

    for cluster_match in CLUSTER_RE.finditer(text):
        pieces.append(text[cursor:cluster_match.start()])
        cluster = cluster_match.group(0)
        prefix = cluster_match.group("rao_prefix") or cluster_match.group("other_prefix")
        book = citation_book(prefix)
        valid_refs: Any = bco_refs if book == "bco" else (rao_refs if book == "rao" else standard_refs.get(book, set()))
        local_cursor = 0

        for index, ref_match in enumerate(REF_RE_BY_BOOK.get(book, re.compile(REF)).finditer(cluster)):
            token = ref_match.group(0)
            canonical = canonical_ref(book, token)

            if index == 0:
                before = ""
                label = cluster[:ref_match.start()] + token
            else:
                before = cluster[local_cursor:ref_match.start()]
                label = token

            pieces.append(before)

            if canonical and canonical in valid_refs:
                href = f"{READER_BASE}#{book}/{canonical}"
                if book == "bco":
                    chapter = valid_refs[canonical]["chapter"]
                    pieces.append(
                        f'<a class="bco-ref" href="{href}" '
                        f'data-bco-ref="{html.escape(canonical, quote=True)}" '
                        f'data-bco-chapter="{html.escape(chapter, quote=True)}" '
                        'aria-haspopup="dialog" '
                        f'title="Read current BCO {html.escape(canonical, quote=True)} text">'
                        f"{label}</a>"
                    )
                else:
                    display_book = book.upper()
                    source_note = " (not part of the PCA Constitution)" if book == "rao" else ""
                    pieces.append(
                        f'<a class="constitution-ref" href="{href}" '
                        f'data-constitution-book="{book}" '
                        f'data-constitution-ref="{html.escape(canonical, quote=True)}" '
                        'aria-haspopup="dialog" '
                        f'title="Read current {display_book} {html.escape(canonical, quote=True)}{source_note} in the Constitution Reader">'
                        f"{label}</a>"
                    )
                linked += 1
            else:
                pieces.append(label)
                unresolved.append(
                    {
                        "file": file_name,
                        "reference": canonical or token.strip(),
                        "context": cluster,
                    }
                )

            local_cursor = ref_match.end()

        pieces.append(cluster[local_cursor:])
        cursor = cluster_match.end()

    pieces.append(text[cursor:])
    return "".join(pieces), linked


class ConstitutionLinker(HTMLParser):
    def __init__(
        self,
        bco_refs: dict[str, dict[str, str]],
        standard_refs: dict[str, set[str]],
        rao_refs: dict[str, dict[str, str]],
        minutes_refs: dict[str, dict[str, dict[str, str]]],
        file_name: str,
    ) -> None:
        super().__init__(convert_charrefs=False)
        self.bco_refs = bco_refs
        self.standard_refs = standard_refs
        self.rao_refs = rao_refs
        self.minutes_refs = minutes_refs
        self.file_name = file_name
        self.output: list[str] = []
        self.stack: list[dict[str, Any]] = []
        self.link_count = 0
        self.unresolved: list[dict[str, str]] = []

    def state(self) -> dict[str, Any]:
        if self.stack:
            return self.stack[-1]
        return {"reading": False, "skip": False, "tag": None}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        parent = self.state()
        classes: set[str] = set()
        for key, value in attrs:
            if key == "class" and value:
                classes.update(value.split())

        reading = parent["reading"] or (
            tag == "article" and "reading-col" in classes
        )
        skip = parent["skip"] or tag in EXCLUDED_TAGS
        if tag not in VOID_TAGS:
            self.stack.append({"tag": tag, "reading": reading, "skip": skip})
        self.output.append(self.get_starttag_text())

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.output.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        self.output.append(f"</{tag}>")
        lowered = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == lowered:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        state = self.state()
        if state["reading"] and not state["skip"]:
            linked_minutes, minutes_count = linkify_minutes_text(
                data,
                self.minutes_refs,
                self.file_name,
            )
            linked, count = linkify_text(
                linked_minutes,
                self.bco_refs,
                self.standard_refs,
                self.rao_refs,
                self.unresolved,
                self.file_name,
            )
            self.output.append(linked)
            self.link_count += count + minutes_count
        else:
            self.output.append(data)

    def handle_entityref(self, name: str) -> None:
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.output.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.output.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.output.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self.output.append(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self.output.append(f"<![{data}]>")


def asset_prefix(rendered_html: str) -> str:
    match = re.search(
        r"(?:href|src)=[\"']([^\"']*/assets/)(?:pca-style\.css|pca-nav\.js)[\"']",
        rendered_html,
        re.IGNORECASE,
    )
    return match.group(1) if match else "/pca-ga/assets/"


def inject_assets(rendered_html: str) -> str:
    if "constitution-links.css" in rendered_html:
        return rendered_html

    prefix = asset_prefix(rendered_html)
    stylesheet = (
        f'  <link rel="stylesheet" href="{prefix}constitution-links.css">\n'
    )
    script = (
        f'  <script src="{prefix}constitution-links.js" defer></script>\n'
    )

    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace(
            "</head>", stylesheet + "</head>", 1
        )
    if "</body>" in rendered_html:
        rendered_html = rendered_html.replace(
            "</body>", script + "</body>", 1
        )
    return rendered_html


def process_html(
    path: Path,
    site_dir: Path,
    bco_refs: dict[str, dict[str, str]],
    standard_refs: dict[str, set[str]],
    rao_refs: dict[str, dict[str, str]],
    minutes_refs: dict[str, dict[str, dict[str, str]]],
) -> tuple[int, list[dict[str, str]]]:
    source = normalize_inline_citation_prefixes(path.read_text(encoding="utf-8"))
    if not PREFIX_RE.search(source) and not MINUTES_CITATION_RE.search(source):
        return 0, []

    linker = ConstitutionLinker(
        bco_refs,
        standard_refs,
        rao_refs,
        minutes_refs,
        path.relative_to(site_dir).as_posix(),
    )
    linker.feed(source)
    linker.close()

    if not linker.link_count:
        return 0, linker.unresolved

    rendered = inject_assets("".join(linker.output))
    path.write_text(rendered, encoding="utf-8")
    return linker.link_count, linker.unresolved


def self_test() -> None:
    structured = render_section_body({
        "blocks": [
            ["p", 0, "The court shall have power:"],
            ["i", 1, "a.", "First paragraph."],
            ["p", 1, "Editor's note."],
            ["i", 2, "(1)", "Nested paragraph."],
        ]
    })
    assert '<p class="lead">The court shall have power:</p>' in structured
    assert '<div class="li d1"><span class="mk">a.</span> First paragraph.</div>' in structured
    assert '<p class="bpara d1">Editor\'s note.</p>' in structured
    assert '<div class="li d2"><span class="mk">(1)</span> Nested paragraph.</div>' in structured

    bco_refs = {
        "5-9": {"chapter": "5", "chapterTitle": "Organization"},
        "8-4": {"chapter": "8", "chapterTitle": "The Elder"},
        "13-2": {"chapter": "13", "chapterTitle": "The Presbytery"},
        "25-5": {"chapter": "25", "chapterTitle": "Congregational Meetings"},
    }
    standard_refs = {
        "wcf": {"3.3", "8.5", "11.4", "28.4"},
        "wlc": {"Q.166"},
        "wsc": {"Q.95"},
    }
    rao_refs = {
        "16-3": {"article": "16", "articleTitle": "Review of Presbytery Records"},
        "14-10": {"article": "14", "articleTitle": "Review of Records"},
        "14-4": {"article": "14", "articleTitle": "Review of Records"},
        "18": {"article": "18", "articleTitle": "Motions"},
        "20": {"article": "20", "articleTitle": "Amendment or Suspension of Rules"},
    }
    sample = (
        '<!DOCTYPE html><html><head></head><body>'
        '<article class="reading-col">'
        '<p>See also BCO 5-9.c, 8-4, 13-2.</p>'
        '<p>WCF 3-3, 8-5 and 11-4; WLC 166B; WSC 95B; WCF 28.4; RAO 16-3.e.5 and RAO 20.</p>'
        '<p>“RAO” 16:3; RAO § 14-10-D-2; RAO 14.4.C.2; RAO XVIII.</p>'
        '<p><em>RAO</em> 16-3.e.5</p>'
        '<p>See M14GA p. 330 for the original action.</p>'
        '<p>M14GA p. 331 remains plain text when no printed folio is available.</p>'
        '<a href="#">BCO 25-5</a><code>BCO 25-5</code>'
        '</article></body></html>'
    )
    minutes_refs = {
        "14": {"330": {"path": "markdown/ga14_1986.html", "anchor": "ga14-p330", "pdf_page": "332"}}
    }
    linker = ConstitutionLinker(bco_refs, standard_refs, rao_refs, minutes_refs, "test.html")
    linker.feed(normalize_inline_citation_prefixes(sample))
    rendered = "".join(linker.output)
    assert linker.link_count == 17
    assert 'data-bco-ref="5-9"' in rendered
    assert 'data-bco-ref="8-4"' in rendered
    assert f'{READER_BASE}#bco/5-9' in rendered
    assert f'{READER_BASE}#wcf/3.3' in rendered
    assert f'{READER_BASE}#wcf/8.5' in rendered
    assert f'{READER_BASE}#wlc/Q.166' in rendered
    assert f'{READER_BASE}#wsc/Q.95' in rendered
    assert 'data-constitution-book="wlc"' in rendered
    assert 'data-constitution-ref="Q.166"' in rendered
    assert f'{READER_BASE}#rao/16-3' in rendered
    assert f'{READER_BASE}#rao/14-10' in rendered
    assert f'{READER_BASE}#rao/14-4' in rendered
    assert f'{READER_BASE}#rao/18' in rendered
    assert 'data-constitution-book="rao"' in rendered
    assert '>WLC 166B</a>' in rendered
    assert '<a href="#">BCO 25-5</a>' in rendered
    assert '<code>BCO 25-5</code>' in rendered
    assert 'class="minutes-ref" href="markdown/ga14_1986.html#ga14-p330"' in rendered
    assert 'data-minutes-ga="14" data-minutes-page="330"' in rendered
    assert 'M14GA p. 331 remains plain text' in rendered
    assert 'data-minutes-page="331"' not in rendered
    assert minutes_href(
        "cases/example.html", minutes_refs["14"]["330"]
    ) == "../markdown/ga14_1986.html#ga14-p330"

    with tempfile.TemporaryDirectory() as temp:
        site_dir = Path(temp)
        minute_dir = site_dir / "markdown"
        minute_dir.mkdir()
        (minute_dir / "ga14_1986.html").write_text(
            '<a id="ga14-p330"></a><!-- PAGE ga=14 pdf_page=332 printed_page=330 -->',
            encoding="utf-8",
        )
        indexed_refs, payload = build_minutes_page_index(site_dir)
        assert indexed_refs["14"]["330"]["anchor"] == "ga14-p330"
        assert payload["volumes"]["14"]["pages"]["330"]["pdf_page"] == 332


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("bco_js", type=Path)
    parser.add_argument("wcf_js", type=Path)
    parser.add_argument("wlc_js", type=Path)
    parser.add_argument("wsc_js", type=Path)
    parser.add_argument("rao_js", type=Path)
    args = parser.parse_args()

    self_test()

    if not args.site_dir.is_dir():
        parser.error(f"Site directory does not exist: {args.site_dir}")
    for label, path in (("BCO", args.bco_js), ("WCF", args.wcf_js), ("WLC", args.wlc_js), ("WSC", args.wsc_js), ("RAO", args.rao_js)):
        if not path.is_file():
            parser.error(f"{label} source does not exist: {path}")

    bco, digest = load_bco(args.bco_js)
    wcf = load_window_json(args.wcf_js, "WCF")
    wlc = load_window_json(args.wlc_js, "WLC")
    wsc = load_window_json(args.wsc_js, "WSC")
    rao = load_bundled_book_pack(args.rao_js, "rao")
    standard_refs = build_standard_refs(
        wcf,
        wlc,
        wsc,
    )
    data_dir = args.site_dir / "assets" / "constitution"
    bco_refs = build_reference_data(bco, data_dir, digest)
    build_standard_preview_data(wcf, wlc, wsc, data_dir)
    rao_refs = build_rao_preview_data(rao, data_dir)
    minutes_refs, minutes_payload = build_minutes_page_index(args.site_dir)
    (args.site_dir / "assets" / "minutes-pages.json").write_text(
        json.dumps(minutes_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    total_links = 0
    changed_files = 0
    unresolved: list[dict[str, str]] = []

    for path in sorted(args.site_dir.rglob("*.html")):
        linked, missing = process_html(
            path, args.site_dir, bco_refs, standard_refs, rao_refs, minutes_refs
        )
        total_links += linked
        unresolved.extend(missing)
        if linked:
            changed_files += 1

    counts = Counter(item["reference"] for item in unresolved)
    unresolved_payload = {
        "version": 1,
        "total": sum(counts.values()),
        "references": [
            {"reference": ref, "count": count}
            for ref, count in sorted(counts.items())
        ],
        "examples": unresolved[:250],
    }
    (data_dir / "unresolved.json").write_text(
        json.dumps(
            unresolved_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    print(
        f"References: linked {total_links} citations "
        f"across {changed_files} HTML files; "
        f"{len(bco_refs)} current BCO sections and "
        f"{sum(len(refs) for refs in standard_refs.values())} Westminster provisions available; "
        f"{len(rao_refs)} current RAO provisions available; "
        f"{sum(len(pages) for pages in minutes_refs.values())} printed minute pages available; "
        f"{len(unresolved)} unresolved candidates."
    )
    if total_links == 0:
        print(
            "warning: no constitutional references were linked; check the rendered markup",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
