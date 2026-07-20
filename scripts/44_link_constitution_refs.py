#!/usr/bin/env python3
"""Link constitutional references in rendered PCA-GA HTML and emit BCO preview data.

The PCA Constitution Reader remains the source of truth. This script reads its
content files during the Pages build, emits a small section index plus one JSON
payload per numbered BCO chapter, and converts explicit BCO and Westminster
Standards citation clusters in the rendered site into links. BCO links are
progressively enhanced with the in-page text preview; Westminster links open
their exact provision in the Constitution Reader.

Examples:
  BCO 25-5
  B.C.O. 31–2 and 31-5
  See also BCO 5-9.c, 8-4, 13-2, 13-10
  WCF 28-4; WLC 166B; WSC 95B

Lettered subparagraphs retain their visible label but resolve to their enclosing
chapter-and-section record (5-9.c -> 5-9).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
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
PREFIX = rf"(?:{BCO_PREFIX}|{WCF_PREFIX}|{WLC_PREFIX}|{WSC_PREFIX})"
BCO_REF = rf"\d{{1,2}}\s*{DASH}\s*\d{{1,2}}(?:\s*(?:\.\s*[A-Za-z]|\(\s*[A-Za-z]\s*\)))?"
WCF_REF = rf"\d{{1,2}}\s*(?:\.|{DASH})\s*\d{{1,2}}(?:\s*(?:\.\s*[A-Za-z]|\(\s*[A-Za-z]\s*\)))?"
CATECHISM_REF = r"(?:Q\.?\s*)?\d{1,3}(?:\s*(?:[A-Za-z]|\(\s*[A-Za-z]\s*\)))?"
REF = rf"(?:{BCO_REF}|{WCF_REF}|{CATECHISM_REF})"
SEP = r"(?:\s*,\s*|\s*;\s*|\s+(?:and|or)\s+)"
CLUSTER_RE = re.compile(
    rf"\b(?P<prefix>{PREFIX})\s+(?P<first>{REF})(?P<rest>(?:{SEP}{REF})*)",
    re.IGNORECASE,
)
PREFIX_RE = re.compile(rf"\b{PREFIX}\b", re.IGNORECASE)
REF_RE = re.compile(REF, re.IGNORECASE)
BCO_CANON_RE = re.compile(rf"(\d{{1,2}})\s*{DASH}\s*(\d{{1,2}})", re.IGNORECASE)
WCF_CANON_RE = re.compile(rf"(\d{{1,2}})\s*(?:\.|{DASH})\s*(\d{{1,2}})", re.IGNORECASE)
CATECHISM_CANON_RE = re.compile(r"(?:Q\.?\s*)?(\d{1,3})", re.IGNORECASE)

EXCLUDED_TAGS = {"a", "code", "pre", "script", "style", "textarea", "noscript"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


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
    return None


def citation_book(prefix: str) -> str:
    compact = re.sub(r"[^a-z]", "", prefix.lower())
    if compact in {"bco", "bookofchurchorder"}:
        return "bco"
    return compact


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
        book = citation_book(cluster_match.group("prefix"))
        valid_refs: Any = bco_refs if book == "bco" else standard_refs.get(book, set())
        local_cursor = 0

        for index, ref_match in enumerate(REF_RE.finditer(cluster)):
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
                    pieces.append(
                        f'<a class="constitution-ref" href="{href}" target="_blank" rel="noopener" '
                        f'title="Read {display_book} {html.escape(canonical, quote=True)} in the Constitution Reader">'
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
        file_name: str,
    ) -> None:
        super().__init__(convert_charrefs=False)
        self.bco_refs = bco_refs
        self.standard_refs = standard_refs
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
            linked, count = linkify_text(
                data,
                self.bco_refs,
                self.standard_refs,
                self.unresolved,
                self.file_name,
            )
            self.output.append(linked)
            self.link_count += count
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
) -> tuple[int, list[dict[str, str]]]:
    source = path.read_text(encoding="utf-8")
    if not PREFIX_RE.search(source):
        return 0, []

    linker = ConstitutionLinker(
        bco_refs,
        standard_refs,
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
    sample = (
        '<!DOCTYPE html><html><head></head><body>'
        '<article class="reading-col">'
        '<p>See also BCO 5-9.c, 8-4, 13-2.</p>'
        '<p>WCF 3-3, 8-5 and 11-4; WLC 166B; WSC 95B; WCF 28.4.</p>'
        '<a href="#">BCO 25-5</a><code>BCO 25-5</code>'
        '</article></body></html>'
    )
    linker = ConstitutionLinker(bco_refs, standard_refs, "test.html")
    linker.feed(sample)
    rendered = "".join(linker.output)
    assert linker.link_count == 9
    assert 'data-bco-ref="5-9"' in rendered
    assert 'data-bco-ref="8-4"' in rendered
    assert f'{READER_BASE}#bco/5-9' in rendered
    assert f'{READER_BASE}#wcf/3.3' in rendered
    assert f'{READER_BASE}#wcf/8.5' in rendered
    assert f'{READER_BASE}#wlc/Q.166' in rendered
    assert f'{READER_BASE}#wsc/Q.95' in rendered
    assert '>WLC 166B</a>' in rendered
    assert '<a href="#">BCO 25-5</a>' in rendered
    assert '<code>BCO 25-5</code>' in rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("bco_js", type=Path)
    parser.add_argument("wcf_js", type=Path)
    parser.add_argument("wlc_js", type=Path)
    parser.add_argument("wsc_js", type=Path)
    args = parser.parse_args()

    self_test()

    if not args.site_dir.is_dir():
        parser.error(f"Site directory does not exist: {args.site_dir}")
    for label, path in (("BCO", args.bco_js), ("WCF", args.wcf_js), ("WLC", args.wlc_js), ("WSC", args.wsc_js)):
        if not path.is_file():
            parser.error(f"{label} source does not exist: {path}")

    bco, digest = load_bco(args.bco_js)
    standard_refs = build_standard_refs(
        load_window_json(args.wcf_js, "WCF"),
        load_window_json(args.wlc_js, "WLC"),
        load_window_json(args.wsc_js, "WSC"),
    )
    data_dir = args.site_dir / "assets" / "constitution"
    bco_refs = build_reference_data(bco, data_dir, digest)

    total_links = 0
    changed_files = 0
    unresolved: list[dict[str, str]] = []

    for path in sorted(args.site_dir.rglob("*.html")):
        linked, missing = process_html(path, args.site_dir, bco_refs, standard_refs)
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
        f"Constitution references: linked {total_links} citations "
        f"across {changed_files} HTML files; "
        f"{len(bco_refs)} current BCO sections and "
        f"{sum(len(refs) for refs in standard_refs.values())} Westminster provisions available; "
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
