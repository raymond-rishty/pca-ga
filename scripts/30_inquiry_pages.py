#!/usr/bin/env python3
"""Render inquiry records and their catalogue projections from inquiries.jsonl."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_links import line_to_pdf_page, pdf_page_for_anchor, source_entries_for_record, source_front_matter

ONLY_RELOCATED = "--only-relocated" in sys.argv[1:]
ROOT_ARG = next((arg for arg in sys.argv[1:] if not arg.startswith("--")), None)
ROOT = Path(ROOT_ARG or os.environ.get(
    "PCA_GA_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IDX = ROOT / "index"
OUT = ROOT / "inquiries"
_MD_CACHE: dict[str, list[str]] = {}
FOOTNOTE_REFERENCE = re.compile(r"\[\^(fn-[^\]]+)\](?!:)")
FOOTNOTE_DEFINITION = re.compile(r"^\[\^(fn-[^\]]+)\]:")


def ordinal(value: int) -> str:
    value = int(value)
    suffix = "th" if 10 <= value % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def md_escape(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def read_records() -> list[dict]:
    path = IDX / "inquiries.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [record.get("inquiry_id") for record in records]
    slugs = [record.get("page_slug") for record in records]
    if any(not value for value in ids + slugs):
        raise ValueError(f"{path} has a record without inquiry_id or page_slug")
    if len(ids) != len(set(ids)) or len(slugs) != len(set(slugs)):
        raise ValueError(f"{path} contains duplicate inquiry IDs or page slugs")
    for record in records:
        if record.get("schema_version") != 1:
            raise ValueError(f"{path}: {record.get('inquiry_id')} has an unsupported schema_version")
        locator = record.get("digest_section") or record.get("minute_para")
        if locator:
            locator = re.sub(r"^App\. O\s+", "App. O, ", str(locator))
        expected = (f"{record.get('year')}, p. {record.get('printed_page')}, {locator}."
                    if record.get("year") and record.get("printed_page") and locator else "")
        if record.get("digest_citation", "") != expected:
            raise ValueError(f"{path}: {record.get('inquiry_id')} has a noncanonical digest_citation")
    return records


def slice_md(stem: str, start: object, end: object) -> str:
    if not start or not end:
        return ""
    path = ROOT / "markdown" / f"{stem}.md"
    if not path.exists():
        return ""
    if stem not in _MD_CACHE:
        _MD_CACHE[stem] = path.read_text(encoding="utf-8").splitlines()
    lines = _MD_CACHE[stem]
    a, b = max(1, int(start)), min(len(lines), int(end))
    return "\n".join(lines[a - 1:b]).strip()


def marker_line(lines: list[str], marker: str, after: int = 0) -> int | None:
    """Find a durable text marker and return its zero-based line, ignoring punctuation."""
    wanted = re.findall(r"[a-z0-9]+", marker.casefold())
    if not wanted:
        return None
    tokens = [(match.group(0), index)
              for index, line in enumerate(lines)
              for match in re.finditer(r"[a-z0-9]+", line.casefold())]
    for offset in range(len(tokens) - len(wanted) + 1):
        window = tokens[offset:offset + len(wanted)]
        if window[0][1] >= after and [token for token, _ in window] == wanted:
            return window[0][1]
    return None


def resolve_text_locator(stem: str, locator: object) -> tuple[int, int] | None:
    if not isinstance(locator, dict):
        return None
    if stem not in _MD_CACHE:
        path = ROOT / "markdown" / f"{stem}.md"
        if not path.exists():
            return None
        _MD_CACHE[stem] = path.read_text(encoding="utf-8").splitlines()
    lines = _MD_CACHE[stem]
    start = marker_line(lines, str(locator.get("start_text") or ""))
    end_before = marker_line(lines, str(locator.get("end_before") or ""), (start + 1) if start is not None else 0)
    if start is None or end_before is None or end_before <= start:
        return None
    return start + 1, end_before


def complete_footnotes(page: list[str], stem: str) -> list[str]:
    """Keep extracted record footnotes complete when a source span cuts across notes."""
    source_path = ROOT / "markdown" / f"{stem}.md"
    if not source_path.exists():
        return page
    source_lines = _MD_CACHE.get(stem)
    if source_lines is None:
        source_lines = source_path.read_text(encoding="utf-8").splitlines()
        _MD_CACHE[stem] = source_lines
    page_lines = "\n".join(page).splitlines()
    refs = set(FOOTNOTE_REFERENCE.findall("\n".join(page_lines)))

    source_notes: dict[str, list[str]] = {}
    i = 0
    while i < len(source_lines):
        match = FOOTNOTE_DEFINITION.match(source_lines[i])
        if not match:
            i += 1
            continue
        note_id = match.group(1)
        note = [source_lines[i]]
        i += 1
        while i < len(source_lines) and source_lines[i].strip():
            if FOOTNOTE_DEFINITION.match(source_lines[i]):
                break
            note.append(source_lines[i])
            i += 1
        source_notes[note_id] = note

    # Rebuild the note block from the canonical minutes source. This both supplies
    # definitions cut off by a record boundary and removes notes copied from an
    # adjacent record or duplicated by overlapping question/answer ranges.
    cleaned: list[str] = []
    dropping_definition = False
    for line in page_lines:
        if FOOTNOTE_DEFINITION.match(line):
            dropping_definition = True
        elif not line.strip():
            dropping_definition = False
        if not dropping_definition:
            cleaned.append(line)
    page = cleaned
    for note_id in sorted(refs):
        note = source_notes.get(note_id)
        if note:
            page += ["", *note]
    return page


def deeplink(stem: str, anchor: str, printed: object) -> str:
    label = f"{stem} p.{printed}" if printed else stem
    return f"[{label}](../markdown/{stem}.md{'#' + anchor if anchor else ''})"


def canonical_anchor(value: object) -> str:
    anchor = str(value or "").strip()
    match = re.match(r"ga(\d+)-p(.+)$", anchor)
    return f"ga{int(match.group(1)):02d}-p{match.group(2)}" if match else anchor


def write_page(record: dict) -> None:
    stem = record["minutes_volume"]
    slug = record["page_slug"]
    title = record.get("digest_title") or "Constitutional inquiry"
    section = record.get("digest_section") or ""
    label = record.get("inquiry_number") or record.get("minute_para") or "Inquiry"
    if section:
        label = f"{label} {section}"
    source_range = record.get("source_range") or {}
    posed_range = record.get("posed_range") or {}
    substantive = record.get("substantive")
    action = record.get("assembly_action")
    anchor = canonical_anchor(record.get("page_anchor"))
    primary = substantive or {
        "start": source_range.get("start"), "end": source_range.get("end"),
        "page_anchor": anchor, "printed_page": record.get("printed_page"),
    }
    primary_anchor = canonical_anchor(primary.get("page_anchor"))
    stable_span = resolve_text_locator(stem, primary.get("text_locator"))
    if primary.get("text_locator") and stable_span is None:
        raise ValueError(f"{record['inquiry_id']}: substantive text_locator did not resolve")
    source_start, source_end = stable_span or (primary.get("start"), primary.get("end"))
    action_span = resolve_text_locator(stem, action.get("text_locator")) if action else None
    if action and action.get("text_locator") and action_span is None:
        raise ValueError(f"{record['inquiry_id']}: assembly_action text_locator did not resolve")
    if record.get("source_pdf_page") is not None:
        source_page = int(record["source_pdf_page"])
    else:
        source_page = pdf_page_for_anchor(ROOT, stem, primary_anchor) if primary_anchor else None
        if source_page is None and source_start:
            source_page = line_to_pdf_page(ROOT, stem, int(source_start))
    if source_page is None and source_range.get("start"):
        source_page = line_to_pdf_page(ROOT, stem, int(source_range["start"]))
    source_meta = source_front_matter(source_entries_for_record(
        ROOT, "inquiry", record["inquiry_id"], stem, source_page
    ))

    source_text = slice_md(stem, source_range.get("start"), source_range.get("end"))
    substantive_text = slice_md(stem, source_start, source_end) if substantive else ""
    posed_text = slice_md(stem, posed_range.get("start"), posed_range.get("end"))
    action_text = (slice_md(stem, *(action_span or (action.get("start"), action.get("end"))))
                   if action else "")
    if not source_text:
        source_text = "_(verbatim passage not located in this volume)_"

    kind = "Overture/amendment advice" if record.get("classification") == "ccb-advice" else "Constitutional inquiry"
    header = ["**Body:** Committee on Constitutional Business (CCB)", f"**Type:** {kind}",
              f"**Assembly:** {ordinal(record['ga_ordinal'])} ({record.get('year')})"]
    provisions = record.get("provisions") or []
    if provisions:
        header.append("**Provisions:** " + ", ".join(provisions))
    if record.get("disposition"):
        header.append("**Disposition:** " + md_escape(record["disposition"]))
    if primary.get("text_locator") and primary_anchor:
        page_label = primary.get("printed_page") or record.get("printed_page")
        source_line = (f"*Source: [{stem} p. {page_label}](../markdown/{stem}.md#{primary_anchor})*")
    elif source_start and source_end:
        source_line = (f"*Source: [{stem} lines {source_start}–{source_end}](../markdown/{stem}.md"
                       f"{'#' + primary_anchor if primary_anchor else ''})*")
    else:
        source_line = f"*Source: {stem}*"
    page = source_meta + [f"# {label} — {title}", ""]
    if record.get("synopsis"):
        page += [f"*{md_escape(record['synopsis'])}*", ""]
    page += ["  ·  ".join(header), "", source_line, "", "---", ""]
    if record.get("headnote"):
        page += ["## Digest headnote",
                 "*Editorial summary from the PCA Digest, Part II (Interpretations of the Constitution) — "
                 "this is the Digest's wording, not the verbatim minutes. The authoritative text is the "
                 "verbatim record below / linked above.*", "", record["headnote"], ""]
        if provisions:
            page += ["**Key words:** " + ", ".join(provisions), ""]
        if record.get("originating_body"):
            page += ["**Inquiry from:** " + md_escape(record["originating_body"]), ""]
        page += ["**In the minutes:** " + deeplink(stem, primary_anchor, primary.get("printed_page") or record.get("printed_page")),
                 "", "---", ""]
    page += ["## Verbatim record", ""]
    if record.get("answer_in_volume") is False:
        page += ["*The General Assembly ratified this advice by reference; the substantive answer "
                 "is not printed as a separate passage in this volume. The ratifying action is quoted below.*", ""]
    if substantive:
        page += ["### Question and answer", "", substantive_text, ""]
    elif posed_text:
        page += ["### As referred / posed", "", posed_text, "", "### CCB advice", "", source_text, ""]
    else:
        page += [source_text, ""]
    if action:
        action_anchor = canonical_anchor(action.get("page_anchor"))
        page += ["## Assembly action", "",
                 "The General Assembly's later action is preserved separately from the substantive Q&A: "
                 + deeplink(stem, action_anchor, action.get("printed_page")), "", action_text, ""]
    page = complete_footnotes(page, stem)
    back = ("[← Constitutional inquiry index](../index/INQUIRIES.md)"
            if record.get("classification") == "inquiry"
            else "[← Overture/amendment advice index](../index/CCB-OVERTURE-ADVICE.md)")
    page += ["---", "", back]
    (OUT / f"{slug}.md").write_text("\n".join(page) + "\n", encoding="utf-8")


def main() -> None:
    records = read_records()
    OUT.mkdir(parents=True, exist_ok=True)
    if not ONLY_RELOCATED:
        for path in OUT.glob("*.md"):
            path.unlink()

    inq_rows: dict[int, list[tuple[int, str, str]]] = {}
    adv_rows: dict[int, list[tuple[int, str, str]]] = {}
    search_rows = []
    generated = []
    for record in records:
        if ONLY_RELOCATED and not record.get("relocation"):
            continue
        write_page(record)
        generated.append(record)
        stem = record["minutes_volume"]
        anchor = canonical_anchor(record.get("page_anchor"))
        title = record.get("digest_title") or "Constitutional inquiry"
        label = record.get("inquiry_number") or record.get("minute_para") or "Inquiry"
        if record.get("digest_section"):
            label += " " + record["digest_section"]
        citation = record.get("digest_citation") or ""
        row = (f"| {md_escape(label)} | [{md_escape(title)}](../inquiries/{record['page_slug']}.md) | "
               f"{md_escape(record.get('synopsis'))} | {md_escape(', '.join(record.get('provisions') or []))} | "
               f"{md_escape(record.get('disposition'))} | {md_escape(citation)} | "
               f"{md_escape(record.get('originating_body'))} | "
               f"{deeplink(stem, anchor, record.get('printed_page'))} |")
        target = inq_rows if record.get("classification") == "inquiry" else adv_rows
        target.setdefault(int(record["ga_ordinal"]), []).append((int(record.get("year") or 0), stem, row))
        search_rows.append({
            "id": record["inquiry_id"], "type": record.get("classification"),
            "title": title, "citation": citation, "sub": record.get("synopsis") or "",
            "provisions": record.get("provisions") or [], "year": record.get("year"),
            "disposition": record.get("disposition") or "", "url": f"inquiries/{record['page_slug']}.md",
            "minutes_volume": stem, "printed_page": record.get("printed_page"),
            "page_anchor": anchor, "minute_para": record.get("minute_para"),
        })

    if ONLY_RELOCATED:
        print(f"[{ROOT}] refreshed {len(generated)} relocated inquiry pages; left catalogues and other pages untouched")
        return
    (IDX / "inquiries_search.json").write_text(json.dumps(search_rows, ensure_ascii=False) + "\n", encoding="utf-8")

    common = ("Each entry pairs a Digest headnote with the verbatim record in the minutes. The title and "
              "citation come from the canonical inquiry record in `inquiries.jsonl`.")

    def write_catalogue(path: str, title: str, blurb: str, rows_by_ord: dict[int, list[tuple[int, str, str]]], crosslink: str) -> int:
        lines = [f"# {title}", "", blurb, "", common, "", crosslink, ""]
        total = 0
        for ordn in sorted(rows_by_ord):
            rows = rows_by_ord[ordn]
            year, stem, _ = rows[0]
            lines += ["", f"## {ordinal(ordn)} General Assembly ({year})  ·  `{stem}`", "",
                      "| Inquiry | Subject | Synopsis | Provisions | Outcome | Digest citation | From | Minutes |",
                      "|---|---|---|---|---|---|---|---|"]
            lines.extend(row for _, _, row in rows)
            total += len(rows)
        (IDX / path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return total

    n_inq = write_catalogue(
        "INQUIRIES.md", "Constitutional Inquiry Catalogue",
        "Questions of constitutional interpretation referred to the CCB or its predecessor and answered with non-binding advice. Grouped by Assembly.",
        inq_rows, "*CCB constitutional review of proposed overtures/amendments is catalogued separately in **[Overture & amendment advice](CCB-OVERTURE-ADVICE.md)**.*")
    n_adv = write_catalogue(
        "CCB-OVERTURE-ADVICE.md", "CCB Advice on Overtures & Proposed Amendments",
        "The CCB's advice on whether a proposed overture or amendment conflicts with the Constitution. Grouped by Assembly.",
        adv_rows, "*Questions about constitutional meaning are catalogued separately in **[Constitutional inquiries](INQUIRIES.md)**.*")
    print(f"[{ROOT}] wrote {len(generated)} inquiry pages; INQUIRIES.md ({n_inq} inquiries), CCB-OVERTURE-ADVICE.md ({n_adv} advices)")


if __name__ == "__main__":
    main()
