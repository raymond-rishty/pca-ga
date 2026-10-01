#!/usr/bin/env python3
"""Generate printed-page markers and page wrappers in rendered Minutes HTML."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re

from minutes_page_locators import count_printed_pages, page_identifiers


PAGE_COMMENT_RE = re.compile(
    r"<!--\s*PAGE\s+ga=(?P<ga>\d+)\s+pdf_page=(?P<pdf_page>\d+)\s+"
    r"printed_page=(?P<printed_page>[^\s>]+)"
    r"(?:\s+printed_page_source=(?P<printed_source>[^\s>]+))?\s*-->",
    re.IGNORECASE,
)
READING_COLUMN_RE = re.compile(
    r"<article\b(?=[^>]*\bclass\s*=\s*([\"'])[^\"']*\breading-col\b[^\"']*\1)[^>]*>",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"^</?([a-zA-Z][\w:-]*)\b")
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
PAGE_ANCHOR_RE = re.compile(r"^<a\b(?=[^>]*\bid=[\"'][^\"']+[\"'])[^>]*>\s*</a>$", re.I | re.S)
LEGACY_PAGE_ANCHOR_RE = re.compile(
    r'<a\b(?=[^>]*\bid=["\']ga\d+-p[A-Za-z0-9.-]+["\'])[^>]*>\s*</a>', re.I)
MARKER_RE = re.compile(r"<div\b(?=[^>]*\bclass=[\"'][^\"']*\bpage-marker\b)", re.I)


@dataclass(frozen=True)
class Node:
    start: int
    end: int
    kind: str
    text: str


def _tag_end(source: str, start: int) -> int:
    quote: str | None = None
    index = start + 1
    while index < len(source):
        character = source[index]
        if quote:
            if character == quote:
                quote = None
        elif character in "\"'":
            quote = character
        elif character == ">":
            return index + 1
        index += 1
    return len(source)


def top_level_nodes(fragment: str) -> list[Node]:
    """Return direct element and comment nodes with their original byte spans."""
    nodes: list[Node] = []
    depth = 0
    element_start: int | None = None
    index = 0
    while index < len(fragment):
        if fragment.startswith("<!--", index):
            end = fragment.find("-->", index + 4)
            end = len(fragment) if end < 0 else end + 3
            if depth == 0:
                nodes.append(Node(index, end, "comment", fragment[index:end]))
            index = end
            continue
        if fragment[index] != "<":
            next_tag = fragment.find("<", index + 1)
            index = len(fragment) if next_tag < 0 else next_tag
            continue
        end = _tag_end(fragment, index)
        token = fragment[index:end]
        match = TAG_RE.match(token)
        if not match:
            index = end
            continue
        name = match.group(1).lower()
        closing = token.startswith("</")
        self_closing = token.rstrip().endswith("/>") or name in VOID_TAGS
        if closing:
            if depth > 0:
                depth -= 1
                if depth == 0 and element_start is not None:
                    nodes.append(Node(element_start, end, "element", fragment[element_start:end]))
                    element_start = None
        elif depth == 0:
            if self_closing:
                nodes.append(Node(index, end, "element", token))
            else:
                element_start = index
                depth = 1
        elif not self_closing:
            depth += 1
        index = end
    if element_start is not None:
        nodes.append(Node(element_start, len(fragment), "element", fragment[element_start:]))
    # Nodes are discovered in source order, so sorting here only adds work on
    # volumes with tens of thousands of page boundaries.
    return nodes


def _remove_page_break_paragraphs(fragment: str) -> str:
    """Promote CommonMark's paragraph around a standalone marker and empty anchor."""
    paragraph_re = re.compile(r"<p>(?P<body>.*?)</p>", re.IGNORECASE | re.DOTALL)

    # Keep the page-break paragraph if it has any content beyond its empty anchor,
    # marker comment, or whitespace. For break-only paragraphs, remove the tags.
    def remove_if_break_only(match: re.Match[str]) -> str:
        body = match.group("body")
        residue = PAGE_COMMENT_RE.sub("", body)
        residue = re.sub(r"<a\b(?=[^>]*\bid=[\"'][^\"']+[\"'])[^>]*>\s*</a>", "", residue, flags=re.I)
        if residue.strip() or not PAGE_COMMENT_RE.search(body):
            return match.group(0)
        return body

    return paragraph_re.sub(remove_if_break_only, fragment)


def _flatten_generated_pages(fragment: str) -> str:
    """Remove prior generated wrappers/markers so incremental builds can migrate."""
    wrappers = [node for node in top_level_nodes(fragment)
                if re.match(r'<div\b(?=[^>]*\bclass=["\'][^"\']*\bminutes-page\b)',
                            node.text, re.I)]
    generated_marker = re.compile(
        r'(?:<span\b(?=[^>]*\bclass=["\'][^"\']*\bminutes-page__anchor\b)'
        r'[^>]*>\s*</span>)*'
        r'<div\b(?=[^>]*\bclass=["\'][^"\']*\bpage-marker\b)[^>]*>.*?</div>',
        re.I | re.S,
    )
    if wrappers:
        parts: list[str] = []
        cursor = 0
        for wrapper in wrappers:
            opening_end = _tag_end(wrapper.text, 0)
            inner = wrapper.text[opening_end:]
            close_start = inner.rfind("</div>")
            if close_start >= 0:
                inner = inner[:close_start]
            # The generated page action markup has a stable shape. Remove it
            # with one local regex pass instead of parsing every page again.
            inner = generated_marker.sub("", inner)
            if wrapper.start < cursor:
                raise ValueError("overlapping generated Minutes page wrappers")
            parts.extend((fragment[cursor:wrapper.start], inner))
            cursor = wrapper.end
        parts.append(fragment[cursor:])
        fragment = ''.join(parts)
    # Some PAGE comments are inside lists or other nested blocks where a page
    # wrapper cannot be inserted. Their marker and stationary IDs still need
    # to be cleared before a warm render regenerates them.
    fragment = generated_marker.sub("", fragment)
    return fragment


def marker_markup(match: re.Match[str], printed_counts: Counter[str],
                  first_printed_pdf: dict[str, int]) -> str:
    ga = match.group("ga")
    pdf_page = match.group("pdf_page")
    printed_page = match.group("printed_page")
    printed = printed_page.lower() != "null"
    page = printed_page if printed else pdf_page
    identifiers = page_identifiers(ga, int(pdf_page), printed_page if printed else None,
                                   printed_counts)
    target = identifiers["qualified"] or identifiers["printed"] or identifiers["pdf"]
    short = f"M{ga}GA {'p.' if printed else 'PDF p.'}{page}"
    printed_source = match.group("printed_source") or ""
    page_anchors = [f'<span id="{identifiers["pdf"]}" class="minutes-page__anchor"></span>']
    if (identifiers["printed"] and
            (printed_counts[printed_page] == 1
             or first_printed_pdf.get(printed_page) == int(pdf_page))):
        page_anchors.append(
            f'<span id="{identifiers["printed"]}" class="minutes-page__anchor"></span>')
    if identifiers["qualified"]:
        page_anchors.append(
            f'<span id="{identifiers["qualified"]}" class="minutes-page__anchor"></span>')
    return (
        ''.join(page_anchors) +
        f'<div class="page-marker" data-ga="{ga}" '
        f'data-pdf-page="{pdf_page}" data-printed-page="{printed_page}" '
        f'data-pdf-anchor="{identifiers["pdf"]}" '
        f'data-printed-anchor="{identifiers["printed"] or ""}" '
        f'data-printed-source="{printed_source}">'
        f'<a href="#{target}">{short}</a>'
        f'<button type="button" class="page-marker__actions" aria-label="Actions for {short}">'
        '<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
        '<path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8M8 16h5" '
        'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M3 2h5v5l-2.5-1.8L3 7z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>'
        '</svg><span>Page actions</span></button></div>'
    )


def transform_volume(source: str, path: Path) -> tuple[str, int, int]:
    match = READING_COLUMN_RE.search(source)
    if not match:
        raise ValueError(f"{path}: no .reading-col article found")
    start = match.end()
    end = source.rfind("</article>")
    if end < start:
        raise ValueError(f"{path}: .reading-col article has no closing tag")
    fragment = _remove_page_break_paragraphs(source[start:end])
    # The old -pN anchors had both PDF-page and printed-folio meanings. Remove
    # only empty anchors immediately adjacent to PAGE boundaries; their targets
    # are rebuilt from unambiguous page metadata below.
    fragment = LEGACY_PAGE_ANCHOR_RE.sub("", fragment)
    fragment = re.sub(r"<p>\s*</p>", "", fragment, flags=re.I)
    fragment = _flatten_generated_pages(fragment)
    comments = list(PAGE_COMMENT_RE.finditer(fragment))
    if not comments:
        raise ValueError(f"{path}: no rendered PAGE comments found")

    existing_markers = len(MARKER_RE.findall(fragment))
    wrappers = len(re.findall(r"<div\b(?=[^>]*\bclass=[\"'][^\"']*\bminutes-page\b)", fragment, re.I))
    if existing_markers == len(comments):
        return source, len(comments), wrappers
    if existing_markers:
        raise ValueError(f"{path}: found partially generated page markers; expected a clean volume")

    # Leave the source comments for the citation linker, which reads them when
    # refreshing minutes-pages.json during later incremental builds.
    printed_counts = count_printed_pages(
        (item.group("printed_page"), item.group("pdf_page")) for item in comments)
    first_printed_pdf: dict[str, int] = {}
    for item in comments:
        folio = item.group("printed_page")
        if folio.lower() != "null":
            first_printed_pdf.setdefault(folio, int(item.group("pdf_page")))
    fragment = PAGE_COMMENT_RE.sub(
        lambda item: item.group(0) + marker_markup(item, printed_counts, first_printed_pdf), fragment)
    nodes = top_level_nodes(fragment)
    comment_nodes = [node for node in nodes if node.kind == "comment" and PAGE_COMMENT_RE.fullmatch(node.text)]

    wraps: list[tuple[int, int, int]] = []
    node_indexes = {node.start: index for index, node in enumerate(nodes)}
    for index, comment in enumerate(comment_nodes):
        comment_index = node_indexes[comment.start]
        marker_index = comment_index + 1
        while (marker_index < len(nodes)
               and re.match(r'<span\b(?=[^>]*\bclass=["\'][^"\']*\bminutes-page__anchor\b)',
                            nodes[marker_index].text, re.I)):
            marker_index += 1
        if marker_index >= len(nodes) or not MARKER_RE.match(nodes[marker_index].text):
            raise ValueError(f"{path}: generated marker did not follow its PAGE comment")
        page_start = comment.start
        content_start = page_start

        page_end = len(fragment)
        if index + 1 < len(comment_nodes):
            following_comment = comment_nodes[index + 1]
            following_index = node_indexes[following_comment.start]
            preceding = nodes[following_index - 1] if following_index else None
            if preceding and PAGE_ANCHOR_RE.fullmatch(preceding.text.strip()):
                page_end = preceding.start
            else:
                page_end = following_comment.start
        info = PAGE_COMMENT_RE.fullmatch(comment.text)
        assert info is not None
        printed = info.group("printed_page")
        ids = page_identifiers(info.group("ga"), int(info.group("pdf_page")),
                               printed if printed.lower() != "null" else None,
                               printed_counts)
        wraps.append((page_start, page_end, content_start))

    # Build the wrapped fragment in one pass. Repeated string splices copy the
    # whole (multi-megabyte) volume once per printed page, which is quadratic in
    # the number of pages. Appending untouched spans and wrappers keeps this
    # linear in the rendered HTML size.
    parts: list[str] = []
    cursor = 0
    for page_start, page_end, content_start in wraps:
        if page_start < cursor or page_end < page_start:
            raise ValueError(f"{path}: overlapping page wrapper spans")
        parts.extend((
            fragment[cursor:page_start],
            '<div class="minutes-page">',
            fragment[content_start:page_end],
            '</div>',
        ))
        cursor = page_end
    parts.append(fragment[cursor:])
    fragment = ''.join(parts)
    return source[:start] + fragment + source[end:], len(comments), len(wraps)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, help="Rendered site directory")
    parser.add_argument("--changed-files-output", type=Path,
                        help="Write the relative paths of files changed by this pass")
    parser.add_argument("--files-manifest", type=Path,
                        help="Restrict processing to a JSON list of changed site-relative paths")
    args = parser.parse_args()
    site = args.site.resolve()
    all_volumes = sorted(path for path in (site / "markdown").glob("ga*_*.html")
                         if re.fullmatch(r"ga\d+_\d{4}\.html", path.name))
    if len(all_volumes) != 52:
        raise SystemExit(f"Expected 52 rendered Minutes volumes, found {len(all_volumes)}")
    volumes = all_volumes
    if args.files_manifest:
        try:
            selected = json.loads(args.files_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            parser.error(f"Cannot read changed-file manifest: {error}")
        if not isinstance(selected, list):
            parser.error("Changed-file manifest must be a JSON list")
        by_relative = {path.relative_to(site).as_posix(): path for path in all_volumes}
        unknown = sorted(set(map(str, selected)) - by_relative.keys())
        if unknown:
            parser.error(f"Manifest contains non-Minutes or missing volume paths: {unknown[:10]}")
        volumes = [by_relative[name] for name in sorted(set(map(str, selected)))]
    marker_count = 0
    wrapper_count = 0
    changed_files: list[str] = []
    for path in volumes:
        source = path.read_text(encoding="utf-8")
        rendered, count, wrappers = transform_volume(source, path)
        if rendered != source:
            path.write_text(rendered, encoding="utf-8", newline="")
            changed_files.append(path.relative_to(site).as_posix())
        marker_count += count
        wrapper_count += wrappers
    print(f"Generated {marker_count} printed-page markers and {wrapper_count} .minutes-page wrappers across {len(volumes)} Minutes volumes.")
    if args.changed_files_output:
        args.changed_files_output.parent.mkdir(parents=True, exist_ok=True)
        args.changed_files_output.write_text(
            json.dumps(changed_files, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
