#!/usr/bin/env python3
"""Generate printed-page markers and page wrappers in rendered Minutes HTML."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


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
    return sorted(nodes, key=lambda node: node.start)


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


def marker_markup(match: re.Match[str]) -> str:
    ga = match.group("ga")
    pdf_page = match.group("pdf_page")
    printed_page = match.group("printed_page")
    printed = printed_page.lower() != "null"
    page = printed_page if printed else pdf_page
    anchor = f"ga{ga}-p{page}" if printed else f"ga{ga}-pdf-p{page}"
    short = f"M{ga}GA {'p.' if printed else 'PDF p.'}{page}"
    printed_source = match.group("printed_source") or ""
    return (
        f'<div class="page-marker" id="{anchor}" data-ga="{ga}" '
        f'data-pdf-page="{pdf_page}" data-printed-page="{printed_page}" '
        f'data-printed-source="{printed_source}">'
        f'<a href="#{anchor}">{short}</a>'
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
    fragment = PAGE_COMMENT_RE.sub(lambda item: item.group(0) + marker_markup(item), fragment)
    nodes = top_level_nodes(fragment)
    comment_nodes = [node for node in nodes if node.kind == "comment" and PAGE_COMMENT_RE.fullmatch(node.text)]

    wraps: list[tuple[int, int]] = []
    node_indexes = {node.start: index for index, node in enumerate(nodes)}
    for index, comment in enumerate(comment_nodes):
        comment_index = node_indexes[comment.start]
        if comment_index + 1 >= len(nodes) or not MARKER_RE.match(nodes[comment_index + 1].text):
            raise ValueError(f"{path}: generated marker did not follow its PAGE comment")
        previous = nodes[comment_index - 1] if comment_index else None
        page_start = previous.start if previous and PAGE_ANCHOR_RE.fullmatch(previous.text.strip()) else comment.start

        page_end = len(fragment)
        if index + 1 < len(comment_nodes):
            following_comment = comment_nodes[index + 1]
            following_index = node_indexes[following_comment.start]
            preceding = nodes[following_index - 1] if following_index else None
            if preceding and PAGE_ANCHOR_RE.fullmatch(preceding.text.strip()):
                page_end = preceding.start
            else:
                page_end = following_comment.start
        wraps.append((page_start, page_end))

    for page_start, page_end in reversed(wraps):
        fragment = (fragment[:page_start] + '<div class="minutes-page">'
                    + fragment[page_start:page_end] + '</div>' + fragment[page_end:])
    return source[:start] + fragment + source[end:], len(comments), len(wraps)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, help="Rendered site directory")
    args = parser.parse_args()
    site = args.site.resolve()
    volumes = sorted(path for path in (site / "markdown").glob("ga*_*.html")
                     if re.fullmatch(r"ga\d+_\d{4}\.html", path.name))
    if len(volumes) != 52:
        raise SystemExit(f"Expected 52 rendered Minutes volumes, found {len(volumes)}")
    marker_count = 0
    wrapper_count = 0
    for path in volumes:
        source = path.read_text(encoding="utf-8")
        rendered, count, wrappers = transform_volume(source, path)
        if rendered != source:
            path.write_text(rendered, encoding="utf-8", newline="")
        marker_count += count
        wrapper_count += wrappers
    print(f"Generated {marker_count} printed-page markers and {wrapper_count} .minutes-page wrappers across {len(volumes)} Minutes volumes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
