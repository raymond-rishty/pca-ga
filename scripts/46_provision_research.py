#!/usr/bin/env python3
"""Generate canonical constitutional provision research pages.

The provision catalogue is authoritative for current text, relationships,
evidence, and coverage. This script renders one static page per supported
reference after Jekyll has built the site. Search records are projected from the
same catalogue during the pre-build step.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import re
import sys
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit


SITE_ORIGIN = "https://raymond-rishty.github.io"
DEFAULT_BASEURL = "/pca-ga"
READER_BASE = "https://raymond-rishty.github.io/pca-constitution-reader/"
BOOKS = {
    "bco": ("Book of Church Order", "BCO", "Constitutional text"),
    "wcf": ("Westminster Confession of Faith", "WCF", "Constitutional text"),
    "wlc": ("Westminster Larger Catechism", "WLC", "Constitutional text"),
    "wsc": ("Westminster Shorter Catechism", "WSC", "Constitutional text"),
    "rao": ("Rules of Assembly Operations", "RAO", "Supplementary material · not part of the PCA Constitution"),
}
GROUP_ORDER = (
    ("Judicial case", "Judicial cases"),
    ("Constitutional inquiry", "Constitutional inquiries"),
    ("CCB advice", "CCB advice on overtures"),
    ("Overture", "Overtures and amendments"),
    ("RPR exception", "RPR exceptions"),
    ("Study or recommendation", "Studies and recommendations"),
)

def load_linker_module():
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    path = scripts_dir / "44_link_constitution_refs.py"
    spec = importlib.util.spec_from_file_location("pca_constitution_linker", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINKER = load_linker_module()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def route_ref(book: str, ref: str) -> str:
    if book in {"wlc", "wsc"} and ref.startswith("Q."):
        return "q-" + ref[2:]
    return re.sub(r"[^a-z0-9.-]+", "-", ref.lower()).strip("-")


def provision_path(book: str, ref: str, baseurl: str = DEFAULT_BASEURL) -> str:
    return f"{baseurl.rstrip('/')}/provisions/{book}/{route_ref(book, ref)}/"


def _unit(book: str, ref: str, title: str, body: str, *, reader_ref: str | None = None,
          chapter: str = "", children: list[dict[str, Any]] | None = None,
          supplementary: bool = False) -> dict[str, Any]:
    name, abbr, label = BOOKS[book]
    return {
        "id": f"{book}:{ref}", "book": book, "book_name": name, "abbr": abbr,
        "book_label": label if supplementary or book != "rao" else "Supplementary material",
        "ref": ref, "route_ref": route_ref(book, ref), "reader_ref": reader_ref or ref,
        "title": title, "body": body, "chapter": chapter,
        "children": children or [], "supplementary": supplementary or book == "rao",
        "groups": {kind: [] for kind, _ in GROUP_ORDER}, "history": [],
    }


def load_units(reader_dir: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Load the supported current text units from the Constitution Reader."""
    bco, bco_digest = LINKER.load_bco(reader_dir / "bco.js")
    wcf = LINKER.load_window_json(reader_dir / "wcf.js", "WCF")
    wlc = LINKER.load_window_json(reader_dir / "wlc.js", "WLC")
    wsc = LINKER.load_window_json(reader_dir / "wsc.js", "WSC")
    rao = LINKER.load_bundled_book_pack(reader_dir / "rao.js", "rao")
    units: list[dict[str, Any]] = []

    for key, record in bco.items():
        if str(key).isdigit():
            chapter = str(int(key))
            child_units = []
            chapter_sections = []
            for section in record.get("sections") or []:
                ref = str(section.get("ref") or "")
                if not ref:
                    continue
                body = str(section.get("body") or "")
                child_units.append(_unit("bco", ref, f"Section {ref}", f"<p>{body}</p>", chapter=chapter))
                chapter_sections.append((ref, body))
            links = "".join(
                f'<section class="provision-chapter-section" id="bco-{html.escape(ref, quote=True)}">'
                f'<h3><a href="{provision_path("bco", ref)}">BCO {html.escape(ref)}</a></h3>'
                f'<div class="provision-text"><p>{body}</p></div></section>'
                for ref, body in chapter_sections
            )
            units.append(_unit("bco", chapter, f"Chapter {chapter} · {record.get('title', '')}", links,
                               reader_ref=chapter, chapter=chapter, children=child_units))
            units.extend(child_units)
            continue

        if key == "pref-1":
            body = "".join(f"<p>{paragraph}</p>" for paragraph in record.get("paras") or [])
            units.append(_unit("bco", "preface", "Preface", body, reader_ref="bco/pref-1"))
        elif key == "pref-2":
            for section in record.get("sections") or []:
                ref = str(section.get("ref") or "")
                if not re.fullmatch(r"PP-\d+", ref, re.I):
                    continue
                principle = ref.upper()
                body = f"<p>{section.get('body') or ''}</p>"
                units.append(_unit("bco", principle.lower(), f"Preliminary Principle {principle[3:]}", body,
                                   reader_ref=f"bco/pref-2/{principle}"))
        elif key == "pref-3":
            body = "".join(f"<p>{paragraph}</p>" for paragraph in record.get("paras") or [])
            units.append(_unit("bco", "constitution-defined", "The Constitution Defined", body,
                               reader_ref="bco/pref-3"))
        elif str(key).startswith("app"):
            appendix = str(key)[3:].lower()
            body = "".join(f"<p>{paragraph}</p>" for paragraph in record.get("paras") or [])
            units.append(_unit("bco", f"appendix-{appendix}", record.get("title") or f"Appendix {appendix.upper()}",
                               body, reader_ref=f"bco/{key}"))

    for chapter_key, chapter_data in wcf.items():
        chapter = str(int(chapter_key))
        child_units = []
        parts = []
        for section in chapter_data.get("sections") or []:
            ref = str(section.get("ref") or "")
            if not ref:
                continue
            body = str(section.get("body") or "")
            child_units.append(_unit("wcf", ref, f"Section {ref}", f"<p>{body}</p>", chapter=chapter))
            parts.append((ref, body))
        body = "".join(
            f'<section class="provision-chapter-section" id="wcf-{html.escape(ref, quote=True)}">'
            f'<h3><a href="{provision_path("wcf", ref)}">WCF {html.escape(ref)}</a></h3>'
            f'<div class="provision-text"><p>{text}</p></div></section>'
            for ref, text in parts
        )
        units.append(_unit("wcf", chapter, f"Chapter {chapter} · {chapter_data.get('title', '')}", body,
                           reader_ref=chapter, chapter=chapter, children=child_units))
        units.extend(child_units)

    for book, questions in (("wlc", wlc), ("wsc", wsc)):
        for item in questions:
            number = str(int(item["n"]))
            ref = f"Q.{number}"
            body = (f'<p class="provision-question"><strong>Q. {number}.</strong> {item.get("q", "")}</p>'
                    f'<p><strong>A.</strong> {item.get("a", "")}</p>')
            units.append(_unit(book, ref, f"Question {number}", body, reader_ref=ref))

    for article in rao.get("order") or []:
        chapter = (rao.get("chapters") or {}).get(str(article), {})
        child_units = []
        parts = []
        for section in chapter.get("sections") or []:
            ref = str(section.get("ref") or "")
            if not ref:
                continue
            body = LINKER.render_section_body(section)
            if ref == str(article):
                continue
            child_units.append(_unit("rao", ref, f"Section {ref} of Article {article}", body,
                                     chapter=str(article), supplementary=True))
            parts.append((ref, body))
        article_body = "".join(
            f'<section class="provision-chapter-section" id="rao-{html.escape(ref, quote=True)}">'
            f'<h3><a href="{provision_path("rao", ref)}">RAO {html.escape(ref)}</a></h3>'
            f'<div class="provision-text">{text}</div></section>' for ref, text in parts
        )
        units.append(_unit("rao", str(article), f"Article {article} · {chapter.get('title', '')}",
                           article_body, chapter=str(article), supplementary=True))
        units.extend(child_units)

    ids = [unit["id"] for unit in units]
    paths = [(unit["book"], unit["route_ref"]) for unit in units]
    if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
        raise ValueError("Reader inventory contains duplicate stable provision IDs or routes")
    meta = {
        "bco.js": bco_digest,
        **{filename: hashlib.sha256((reader_dir / filename).read_bytes()).hexdigest()
           for filename in ("wcf.js", "wlc.js", "wsc.js", "rao.js")},
    }
    return units, meta


def canonical_record_ref(value: str) -> tuple[str, str] | None:
    """Map a catalogue reference to a stable current-text book/reference pair."""
    text = re.sub(r"\s+", " ", str(value or "").strip()).replace("–", "-").replace("—", "-")
    upper = text.upper()
    preface_principle = re.search(r"\bPREFACE\s+(?:II|2)\s*[-.(]*\s*\(?(\d+)\b", upper)
    if preface_principle:
        return ("bco", f"pp-{int(preface_principle.group(1))}")
    if re.search(r"\b(?:PRELIMINARY PRINCIPLES?|PP)\s*(?:(?:II|2)\s*[-.(]*\s*)?(\d+)\b", upper):
        match = re.search(r"\b(?:PRELIMINARY PRINCIPLES?|PP)\s*(?:(?:II|2)\s*[-.(]*\s*)?(\d+)\b", upper)
        return ("bco", f"pp-{int(match.group(1))}")
    if re.search(r"\bPREFACE\b", upper):
        return ("bco", "preface")
    appendix = re.search(r"\bAPPENDIX\s+([A-J])\b", upper)
    if appendix:
        return ("bco", f"appendix-{appendix.group(1).lower()}")

    for book in ("bco", "wcf", "wlc", "wsc", "rao"):
        prefixes = {
            "bco": r"(?:B\.?\s*C\.?\s*O\.?|BOOK\s+OF\s+CHURCH\s+ORDER)\s*",
            "wcf": r"W\.?\s*C\.?\s*F\.?\s*",
            "wlc": r"(?:W\.?\s*L\.?\s*C\.?|LARGER\s+CATECHISM|LC)\s*",
            "wsc": r"W\.?\s*S\.?\s*C\.?\s*",
            "rao": r"(?:R\.?\s*A\.?\s*O\.?|RULES?\s+OF\s+ASSEMBLY\s+OPERATIONS?)\s*",
        }
        match = re.search(prefixes[book], text, re.I)
        if not match:
            continue
        token = text[match.end():].strip().lstrip("§").strip()
        ref = LINKER.canonical_ref(book, token)
        if ref:
            return book, ref
    return None


def canonical_id(value: str) -> str | None:
    pair = canonical_record_ref(value)
    if not pair:
        return None
    book, ref = pair
    return f"{book}:{ref}"


def build_search_records(root: Path) -> list[dict[str, Any]]:
    """Return the search projection of the generated provision read model."""
    from provision_catalogue import load_catalogue, provision_search_rows
    return provision_search_rows(load_catalogue(root / "index" / "provision_catalogue.json"))


def _external_or_local_url(root: Path, value: str, baseurl: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return value
    path = parts.path.lstrip("./")
    if path.endswith(".md"):
        path = path[:-3] + ".html"
    if path.endswith(".markdown"):
        path = path[:-9] + ".html"
    return f"{baseurl.rstrip('/')}/{path}{('?' + parts.query) if parts.query else ''}{('#' + parts.fragment) if parts.fragment else ''}"


def _history_for_units(root: Path, unit_by_id: dict[str, dict[str, Any]]) -> None:
    for row in read_jsonl(root / "index" / "bco_changes.jsonl"):
        for reference in row.get("bco_sections") or []:
            identifier = canonical_id(f"BCO {reference}")
            if identifier in unit_by_id:
                unit_by_id[identifier]["history"].append({
                    "kind": "change", "year": row.get("year"), "ga": row.get("ga"),
                    "note": f"The indexed BCO change record names {reference}.",
                    "url": f"markdown/ga{int(row['ga']):02d}_{int(row['year'])}.md" if row.get("ga") and row.get("year") else "",
                    "status": "section named in extracted change metadata",
                })
    for row in read_jsonl(root / "index" / "bco_renumberings.jsonl"):
        status = str(row.get("status") or "unverified")
        for mapping in row.get("mappings") or []:
            for side in ("from", "to"):
                reference = mapping.get(side)
                identifier = canonical_id(f"BCO {reference}") if reference else None
                if identifier in unit_by_id:
                    unit_by_id[identifier]["history"].append({
                        "kind": "renumbering", "year": row.get("adopted_year"), "ga": row.get("ga"),
                        "note": f"Indexed crosswalk: BCO {mapping.get('from')} → BCO {mapping.get('to')}.",
                        "url": f"markdown/ga{int(row['ga']):02d}_{int(row['adopted_year'])}.md" if row.get("ga") and row.get("adopted_year") else "",
                        "status": status,
                    })


def _ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _assembly_label(year: Any) -> str:
    try:
        year = int(year)
    except (TypeError, ValueError):
        return ""
    ga = year - 1972 if year < 2020 else (year - 1973 if year > 2020 else 0)
    return f"{_ordinal(ga)} GA · {year}" if ga > 0 else str(year)


def _record_html(row: dict[str, Any], root: Path, baseurl: str) -> str:
    title = html.escape(str(row.get("title") or row.get("url") or "Untitled record"))
    occurrences = row.get("occurrences") or []
    if not occurrences and (row.get("evidence_snippet") or row.get("evidence_line")):
        occurrences = [{
            "url": row.get("url", ""),
            "locator": {"line": row.get("evidence_line")},
            "excerpt": row.get("evidence_snippet") or "",
        }]
    record_path = row.get("record_url") or ((occurrences or [{}])[0].get("url", "")) or row.get("url", "")
    url = _external_or_local_url(root, record_path, baseurl)
    evidence = next((str(item.get("excerpt") or "").strip() for item in occurrences if item.get("excerpt")), "")
    direct_occurrence = next((item for item in occurrences
                              if (item.get("locator") or {}).get("line") and item.get("excerpt")), None)
    title_url = url
    title_label = "record page"
    if direct_occurrence and url:
        occurrence_url = _external_or_local_url(root, direct_occurrence.get("url") or record_path, baseurl)
        phrase = " ".join(str(direct_occurrence["excerpt"]).split()[:28]).strip()
        text_fragment = "text=" + quote(phrase, safe="'")
        title_url = f"{occurrence_url}{':~:' if urlsplit(occurrence_url).fragment else '#:~:'}{text_fragment}"
        title_label = "cited text"
    link = (f'<a href="{html.escape(title_url, quote=True)}" aria-label="Open {title} at {title_label}">{title}</a>'
            if url else f"<strong>{title}</strong>")
    facts = []
    if row.get("year"):
        facts.append(html.escape(_assembly_label(row["year"])))
    if row.get("disposition"):
        facts.append(f"Disposition: {html.escape(str(row['disposition']))}")
    facts_html = f'<p class="provision-record__facts">{" · ".join(facts)}</p>' if facts else ""
    excerpt = (f'<p class="provision-record__facts">Indexed excerpt</p><blockquote>{html.escape(evidence[:500])}</blockquote>'
               if evidence else "")
    source_links = []
    for occurrence in occurrences:
        occurrence_path = occurrence.get("url") or record_path
        occurrence_url = _external_or_local_url(root, occurrence_path, baseurl)
        locator = occurrence.get("locator") or {}
        label = "Source occurrence"
        if locator.get("page"):
            label = f"Minutes page {locator['page']}"
        elif locator.get("line"):
            line_kind = "Case text" if row.get("type") == "Judicial case" else "RPR exception text" if row.get("type") == "RPR exception" else "Record text"
            label = f"{line_kind} line {locator['line']}"
        elif locator.get("fragment"):
            label = "Exact source occurrence"
        if locator.get("line") and occurrence.get("excerpt") and row.get("type") == "Judicial case":
            phrase = " ".join(str(occurrence["excerpt"]).split()[:28]).strip()
            text_fragment = "text=" + quote(phrase, safe="'")
            occurrence_url = f"{occurrence_url}{':~:' if urlsplit(occurrence_url).fragment else '#:~:'}{text_fragment}"
        if occurrence_url:
            source_links.append(f'<a href="{html.escape(occurrence_url, quote=True)}">{html.escape(label)}</a>')
    if row.get("official_pdf_url"):
        source_links.append(f'<a href="{html.escape(str(row["official_pdf_url"]), quote=True)}">Official decision PDF</a>')
    sources_html = f'<p class="provision-record__source">{" · ".join(source_links)}</p>' if source_links else ""
    basis_label = {
        "direct_text": "Cited in source text",
        "structured_case_metadata": "Structured case metadata",
        "structured_provision_tag": "Structured provision tag",
        "title_subject_reference": "Reference in title or subject",
        "indexed_reference": "Indexed reference",
    }.get(str(row.get("evidence_basis") or ""), "Indexed reference")
    from provision_catalogue import PRESENTATION_GROUPS, reference_presentation
    presentation = reference_presentation(row)
    presentation_label = presentation.get("label")
    if presentation_label == PRESENTATION_GROUPS.get(str(presentation.get("group") or "")):
        presentation_label = None
    label = html.escape(str(presentation_label)) if presentation_label else ""
    relation_id = html.escape(str(row.get("id") or row.get("relationship_id") or ""), quote=True)
    record_id = html.escape(str(row.get("record_id") or ""), quote=True)
    relation_html = (f'<p class="provision-record__relation">{label}</p>' if label else "")
    evidence_html = f'<p class="provision-record__evidence">Reference source · {html.escape(basis_label)}</p>'
    return (f'<li class="provision-record" data-relationship-id="{relation_id}" data-record-id="{record_id}">'
            f'{relation_html}{evidence_html}'
            f'<h3>{link}</h3>{facts_html}{excerpt}{sources_html}</li>')


def _history_html(unit: dict[str, Any], root: Path, baseurl: str) -> str:
    if not unit["history"]:
        return '<p class="provision-empty">No section-specific change record is indexed here. This does not establish that the provision has never changed.</p>'
    items = []
    for entry in unit["history"]:
        note = html.escape(entry["note"])
        url = _external_or_local_url(root, entry.get("url", ""), baseurl)
        source = f' <a href="{html.escape(url, quote=True)}">View Assembly minutes</a>' if url else ""
        items.append(f'<li><p>{note}</p><p class="provision-record__facts">{html.escape(str(entry["status"]))} · {html.escape(_assembly_label(entry.get("year")))}</p>{source}</li>')
    return f'<ul class="provision-record-list">{"".join(items)}</ul><p class="provision-note">These extracted change and renumbering records are partial metadata; previous full text and complete historical crosswalks are not provided.</p>'


def _site_shell_open(baseurl: str, breadcrumb: str, page_title: str,
                     description: str, canonical: str = "") -> str:
    """Use the shared PCA-GA application chrome for generated provision pages."""
    canonical_link = f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">' if canonical else ""
    provision_css = Path(__file__).resolve().parent.parent / "assets" / "provision-research.css"
    provision_css_version = hashlib.sha256(provision_css.read_bytes()).hexdigest()[:12]
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#1B2640">
  <meta name="description" content="{html.escape(description, quote=True)}">
  {canonical_link}
  <link rel="manifest" href="{baseurl}/manifest.json">
  <link rel="icon" href="{baseurl}/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="{baseurl}/icon-192.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{baseurl}/assets/pca-style.css">
  <link rel="stylesheet" href="{baseurl}/assets/provision-research.css?v={provision_css_version}">
  <script>if ('serviceWorker' in navigator) navigator.serviceWorker.register('{baseurl}/sw.js');</script>
  <title>{page_title} · PCA General Assembly Minutes</title>
</head>
<body data-page-type="provision">
  <a class="skip-link" href="#content">Skip to main content</a>
  <div class="sidebar-overlay" id="sidebarOverlay"></div>
  <nav class="sidebar" id="sidebar" aria-label="Research menu" inert>
    <div class="sb-header">
      <a class="sb-title" href="{baseurl}/">Research Menu</a>
      <button class="sb-close" id="sidebarClose" aria-label="Close navigation">×</button>
    </div>
    <form class="sb-search" action="{baseurl}/" method="get" role="search">
      <label class="visually-hidden" for="menu-search-input">Search records</label>
      <input id="menu-search-input" name="q" type="search" autocomplete="off" placeholder="Search records…">
    </form>
    <div class="sb-section-label">Browse</div>
    <ul class="sb-list">
      <li><a href="{baseurl}/browse.html#provisions"><span class="sb-icon" aria-hidden="true">§</span>By constitutional provision</a></li>
      <li><a href="{baseurl}/index/JUDICIAL-CASES.html"><span class="sb-icon" aria-hidden="true">⚖</span>Judicial cases</a></li>
      <li><a href="{baseurl}/index/OVERTURES.html"><span class="sb-icon" aria-hidden="true">▤</span>Overtures &amp; amendments</a></li>
      <li><a href="{baseurl}/index/RPR.html"><span class="sb-icon" aria-hidden="true">✓</span>RPR exceptions</a></li>
      <li><a href="{baseurl}/index/INQUIRIES.html"><span class="sb-icon" aria-hidden="true">?</span>Constitutional inquiries</a></li>
      <li><a href="{baseurl}/index/STUDIES.html"><span class="sb-icon" aria-hidden="true">▭</span>Studies &amp; position papers</a></li>
      <li><a href="{baseurl}/index/INDEX.html"><span class="sb-icon" aria-hidden="true">▣</span>Assemblies &amp; minutes</a></li>
    </ul>
    <div class="sb-section-label sb-divider">Research tools</div>
    <ul class="sb-list"><li><a href="{baseurl}/research.html"><span class="sb-icon" aria-hidden="true">▱</span>My research</a></li></ul>
    <div class="sb-section-label sb-divider">About &amp; access</div>
    <ul class="sb-list"><li><a href="{baseurl}/about.html"><span class="sb-icon" aria-hidden="true">i</span>About this corpus</a></li></ul>
  </nav>
  <div class="layout">
    <header class="topbar">
      <button class="menu-btn" id="menuBtn" aria-label="Open navigation" aria-expanded="false" aria-controls="sidebar"><span></span><span></span><span></span></button>
      <a class="topbar-brand" href="{baseurl}/" aria-label="PCA General Assembly Minutes home">
        <svg class="brand-mark" width="28" height="28" viewBox="0 0 100 100" fill="none" aria-hidden="true"><circle cx="50" cy="50" r="41" stroke="#C8993A" stroke-width="4"/><path d="M50 21v58M21 50h58" stroke="#C8993A" stroke-width="7" stroke-linecap="round"/><circle cx="50" cy="50" r="11" fill="#C8993A"/></svg>
        <span class="brand-text"><span class="brand-title">PCA General Assembly</span><span class="brand-sub">Minutes 1973–2025</span></span>
      </a>
      <nav class="topbar-breadcrumb" aria-label="Breadcrumb">{breadcrumb}</nav>
      <button class="topbar-find" type="button" data-page-find-open aria-label="Find text in this page"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8"/><path d="m16 16 4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg><span>Find</span><kbd>⌘F</kbd></button>
    </header>
    <main class="page-main page-main--workspace" id="content">
      <article class="reading-col reading-col--workspace provision-page">'''


def _site_shell_close(baseurl: str) -> str:
    return f'''</article>
    </main>
  </div>
  <nav class="mobile-nav" aria-label="Primary navigation">
    <a href="{baseurl}/#home-search-input"><span aria-hidden="true">⌕</span><small>Search</small></a>
    <a href="{baseurl}/browse.html"><span aria-hidden="true">▤</span><small>Browse</small></a>
    <a href="{baseurl}/research.html"><span aria-hidden="true">▱</span><small>My research</small></a>
  </nav>
  <script src="{baseurl}/assets/research-store.js"></script>
  <script src="{baseurl}/assets/pca-nav.js"></script>
</body>
</html>'''


def _relevance_bucket(row: dict[str, Any]) -> str:
    from provision_catalogue import reference_presentation
    return str(reference_presentation(row)["group"])


def _record_list(records: list[dict[str, Any]], root: Path, baseurl: str) -> str:
    return f'<ul class="provision-record-list">{"".join(_record_html(row, root, baseurl) for row in records)}</ul>'


def _render_record_groups(records: list[dict[str, Any]], root: Path, baseurl: str) -> str:
    buckets = {name: [] for name in (
        "discusses", "cites", "other_case_discussion", "other_mentions", "review"
    )}
    for row in records:
        buckets[_relevance_bucket(row)].append(row)
    groups = []
    for name in ("discusses", "cites"):
        items = buckets[name]
        if items:
            heading = "Discusses this provision" if name == "discusses" else "Cites this provision"
            groups.append(f'<section class="provision-group"><h3>{heading} <span>({len(items)})</span></h3>{_record_list(items, root, baseurl)}</section>')
    nonmajority = buckets["other_case_discussion"]
    if nonmajority:
        groups.append(
            '<details class="provision-record-details"><summary>Other discussion in the case '
            f'({len(nonmajority)})</summary><p class="provision-note">This may reflect a separate opinion, '
            'party argument, or background discussion.</p>'
            f'{_record_list(nonmajority, root, baseurl)}</details>'
        )
    mentions = buckets["other_mentions"]
    if mentions:
        groups.append(
            '<details class="provision-record-details"><summary>Other mentions '
            f'({len(mentions)})</summary><p class="provision-note">These records include a brief reference. '
            'Open the linked passage to see its context.</p>'
            f'{_record_list(mentions, root, baseurl)}</details>'
        )
    review = buckets["review"]
    if review:
        groups.append(
            '<details class="provision-record-details"><summary>References to review '
            f'({len(review)})</summary><p class="provision-note">These references have limited or unclear '
            'support, or have not yet been reviewed. Check the linked passage.</p>'
            f'{_record_list(review, root, baseurl)}</details>'
        )
    return "".join(groups)


def _render_type_sections(records: list[dict[str, Any]], root: Path, baseurl: str) -> str:
    sections = []
    for kind, label in GROUP_ORDER:
        items = [row for row in records if row.get("type") == kind]
        if not items:
            continue
        sections.append(
            f'<section class="provision-type-section"><h2>{label} <span>({len(items)})</span></h2>'
            f'{_render_record_groups(items, root, baseurl)}</section>'
        )
    return "".join(sections) or '<p class="provision-empty">No indexed records are currently linked to this provision.</p>'


def render_unit(unit: dict[str, Any], root: Path, baseurl: str, source_revision: str) -> str:
    citation = f"{unit['abbr']} {unit['ref']}"
    title = f"{citation} · {unit['title']}"
    relations = unit.get("relationships") or []
    related_count = len(relations)
    discussion_count = sum(
        _relevance_bucket(row) in {"discusses", "cites", "other_case_discussion"}
        for row in relations
    )
    if unit["book"] == "bco":
        anchor = unit["reader_ref"] if unit["reader_ref"].startswith("bco/") else f"bco/{unit['reader_ref']}"
        reader_href = f"{READER_BASE}#{anchor}"
    else:
        reader_href = f"{READER_BASE}#{unit['book']}/{unit['reader_ref']}"
    child_links = ""
    if unit.get("_child_units"):
        child_links = '<nav class="provision-children" aria-label="Sections in this chapter"><h2>Sections in this chapter</h2><ul>' + "".join(
            f'<li><a href="{provision_path(child["book"], child["ref"], baseurl)}">{html.escape(child["abbr"])} {html.escape(child["ref"])}</a></li>'
            for child in unit["_child_units"]
        ) + "</ul></nav>"
    history = ""
    if unit["book"] == "bco" and re.fullmatch(r"\d+-\d+", unit["ref"]):
        history = _history_html(unit, root, baseurl)
    supplementary = (f'<p class="provision-status provision-status--supplementary">{html.escape(unit["book_label"])} · Current through the 52nd General Assembly (2025)</p>'
                     if unit["supplementary"] else f'<p class="provision-status">{html.escape(unit["book_label"])}</p>')
    context_line = (f"{related_count} linked record{'s' if related_count != 1 else ''} · "
                    f"{discussion_count} in discussion or citation groups.")
    coverage = "These links are based on references in the recorded sources. Some connections may be incomplete or incidental; check the linked passage."
    if unit["book"] == "rao":
        coverage += " RAO is supplementary PCA material and is not part of the PCA Constitution."
    coverage += " Recommendations and study papers do not yet have a complete provision-level index."
    page_title = html.escape(title)
    canonical = provision_path(unit["book"], unit["ref"], baseurl)
    source = "PCA Constitution Reader"
    if source_revision:
        source += f" · source revision {source_revision[:12]}"
    breadcrumb = (f'<a href="{baseurl}/">Home</a><span aria-hidden="true">/</span>'
                  f'<a href="{baseurl}/provisions/">Constitutional provisions</a>'
                  f'<span aria-hidden="true">/</span><span aria-current="page">{html.escape(citation)}</span>')
    return f'''{_site_shell_open(baseurl, breadcrumb, page_title,
                                 f'Current text and linked PCA General Assembly records for {citation}.',
                                 SITE_ORIGIN + canonical)}
    <nav class="provision-breadcrumb" aria-label="Breadcrumb"><a href="{baseurl}/">Home</a><span aria-hidden="true">/</span><a href="{baseurl}/provisions/">Constitutional provisions</a><span aria-hidden="true">/</span><span aria-current="page">{html.escape(citation)}</span></nav>
    <header class="provision-heading">{supplementary}<h1>{page_title}</h1><p>{html.escape(context_line)}</p><a class="provision-reader-link" href="{html.escape(reader_href, quote=True)}" target="_blank" rel="noopener">Open current text in Constitution Reader</a></header>
    <section class="provision-current"><h2>Current text</h2><div class="provision-text">{unit['body']}</div><p class="provision-source">Source: <a href="{html.escape(reader_href, quote=True)}">{html.escape(source)}</a></p></section>
    {child_links}
    <section class="provision-coverage" aria-label="Coverage note"><h2>How to read these links</h2><p>{html.escape(coverage)}</p><p>Each group is a guide to the linked source, not an editorial finding. References remain available here even when their context is uncertain. When available, a source link opens the catalogue record or its referenced Assembly page.</p></section>
    <section aria-labelledby="related-title" class="provision-related"><h2 id="related-title">Related records</h2>{_render_type_sections(relations, root, baseurl)}</section>
    {f'<section class="provision-history"><h2>Amendment and renumbering history</h2>{history}</section>' if history else ''}
  <footer class="provision-footer"><a href="{baseurl}/provisions/">Browse all supported provisions</a><a href="{baseurl}/api/provisions/{unit['book']}/{unit['route_ref']}.json">Machine-readable JSON</a><span>Generated from {html.escape(source)}</span></footer>
{_site_shell_close(baseurl)}'''

def render_index(units: list[dict[str, Any]], baseurl: str) -> str:
    book_links = []
    for book, (name, abbr, label) in BOOKS.items():
        entries = [u for u in units if u["book"] == book]
        links = "".join(
            f'<li><a href="{provision_path(book, unit["ref"], baseurl)}">{html.escape(abbr)} {html.escape(unit["ref"])} · {html.escape(unit["title"])}</a></li>'
            for unit in entries if not unit["children"]
        )
        chapter_entries = [u for u in entries if u["children"]]
        if chapter_entries:
            chapter_links = "".join(
                f'<li><a href="{provision_path(book, unit["ref"], baseurl)}">{html.escape(abbr)} {html.escape(unit["ref"])} · {html.escape(unit["title"])}</a></li>'
                for unit in chapter_entries
            )
            links += chapter_links
        book_links.append(
            f'<details class="provision-book"><summary>{html.escape(name)} <span>{len(entries)} text units</span></summary><ul>{links}</ul></details>'
        )
    breadcrumb = (f'<a href="{baseurl}/">Home</a><span aria-hidden="true">/</span>'
                  f'<span aria-current="page">Constitutional provisions</span>')
    return f'''{_site_shell_open(baseurl, breadcrumb, 'Constitutional provisions',
                                 'Browse current PCA constitutional provisions and linked General Assembly records.',
                                 SITE_ORIGIN + baseurl + '/provisions/')}
    <nav class="provision-breadcrumb" aria-label="Breadcrumb"><a href="{baseurl}/">Home</a><span aria-hidden="true">/</span><span aria-current="page">Constitutional provisions</span></nav>
    <header class="provision-heading"><p class="provision-status">Current PCA constitutional text and supplementary RAO</p><h1>Browse by provision</h1><p>Open a provision to read its current text alongside indexed cases, inquiries, CCB advice, overtures, RPR exceptions, and available amendment history.</p><p>Linked records show where the catalogue names a provision. They are not editorial judgments of relevance.</p></header>{''.join(book_links)}<p class="provision-coverage">Recommendations and study papers do not yet have a complete provision-level index. RAO articles are supplementary PCA material, not part of the PCA Constitution.</p>
{_site_shell_close(baseurl)}'''


def add_legacy_authority_links(root: Path, site_dir: Path,
                              unit_by_id: dict[str, dict[str, Any]]) -> int:
    """Add a route from generated authority pages to their canonical provision page."""
    linked = 0
    source_dir = root / "authorities"
    output_dir = site_dir / "authorities"
    if not source_dir.is_dir() or not output_dir.is_dir():
        return linked
    for source in sorted(source_dir.glob("*.md")):
        heading = re.search(r"(?m)^#\s+(.+?)\s*$", source.read_text(encoding="utf-8"))
        if not heading:
            continue
        unit = unit_by_id.get(canonical_id(heading.group(1)) or "")
        if not unit:
            continue
        rendered_path = output_dir / f"{source.stem}.html"
        if not rendered_path.exists():
            continue
        rendered = rendered_path.read_text(encoding="utf-8")
        if "provision-compatibility-link" in rendered:
            continue
        end = re.search(r"</h1\s*>", rendered, re.I)
        if not end:
            continue
        href = f"../provisions/{unit['book']}/{unit['route_ref']}/"
        label = f"Open the unified research view for {unit['abbr']} {unit['ref']}"
        link = (f'<p class="provision-compatibility-link"><a href="{html.escape(href, quote=True)}">'
                f'{html.escape(label)}</a></p>')
        rendered_path.write_text(rendered[:end.end()] + link + rendered[end.end():], encoding="utf-8")
        linked += 1
    return linked


def source_revision(reader_dir: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(reader_dir), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def build_site(root: Path, site_dir: Path, reader_dir: Path | None = None,
               baseurl: str = DEFAULT_BASEURL) -> int:
    from provision_catalogue import load_catalogue

    catalogue = load_catalogue(root / "index" / "provision_catalogue.json")
    units = catalogue["provisions"]
    unit_by_id = {unit["id"]: unit for unit in units}
    for unit in units:
        unit["_child_units"] = [unit_by_id[child_id] for child_id in unit.get("children", [])
                                if child_id in unit_by_id]
    output = site_dir / "provisions"
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(render_index(units, baseurl), encoding="utf-8")
    revision = catalogue.get("source", {}).get("revision", "")
    for unit in units:
        path = output / unit["book"] / unit["route_ref"] / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_unit(unit, root, baseurl, revision), encoding="utf-8")
    compatibility_links = add_legacy_authority_links(root, site_dir, unit_by_id)
    print(f"Generated {len(units)} canonical provision pages under {output}; linked {compatibility_links} legacy authority pages")
    return len(units)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    search = subparsers.add_parser("search", help="emit the catalogue search projection")
    search.add_argument("root", type=Path)
    search.add_argument("output", type=Path)
    site = subparsers.add_parser("site", help="generate canonical static pages")
    site.add_argument("root", type=Path)
    site.add_argument("site_dir", type=Path)
    site.add_argument("reader", nargs="?", type=Path,
                      help="deprecated; provision text is read from index/provision_catalogue.json")
    site.add_argument("--baseurl", default=DEFAULT_BASEURL)
    args = parser.parse_args()
    if args.command == "search":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        records = build_search_records(args.root)
        args.output.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"Wrote {len(records)} provision search records to {args.output}")
        return 0
    build_site(args.root, args.site_dir, args.reader, args.baseurl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
