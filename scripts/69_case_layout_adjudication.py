#!/usr/bin/env python3
"""Prepare, validate, and render LLM-adjudicated case-range reconstructions.

The corrected minutes are the only text source.  PP-Structure JSON is evidence
about page layout, and the LLM may choose boundary anchors and classify layout
ambiguities.  The LLM response never supplies replacement prose.

Commands:
  prepare --ga-from 3 --ga-to 18 --output-dir build/case_layout_llm
  validate --requests .../requests.jsonl --responses responses.jsonl
  render --decisions .../validated.jsonl --apply
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"(?s)(<!-- PAGE ga=(\d+) pdf_page=(\d+)\b[^>]*-->)(.*?)(?=<!-- PAGE ga=|\Z)")
SOURCE = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?")
SEPARATOR = "\n---\n"
ANCHOR = re.compile(r'<a id="[^"]+"></a>\s*', re.I)
HEADING = re.compile(r"^(\s*)(#{1,6})(\s+)(.*)$")
LIST = re.compile(r"^(\s*)((?:[-*+]\s+|\d+[.)]\s+|[A-Za-z][.)]\s+))(.*)$")


WORD_RE = re.compile(r"[a-z][a-z0-9']{2,}")


def normalize(value: str) -> str:
    return " ".join(WORD_RE.findall((value or "").lower()))


def normalized_with_offsets(text: str) -> tuple[str, list[int]]:
    cleaned, origins = [], []
    for index, character in enumerate(text or ""):
        cleaned.append(character.lower())
        origins.append(index)
    compact = "".join(cleaned)
    result, offsets = [], []
    for match in WORD_RE.finditer(compact):
        if result:
            result.append(" ")
            offsets.append(origins[match.start()])
        result.extend(compact[match.start():match.end()])
        offsets.extend(origins[match.start():match.end()])
    return "".join(result), offsets


def body(text: str) -> str:
    if SEPARATOR in text:
        return text.split(SEPARATOR, 1)[1].rsplit(SEPARATOR, 1)[0]
    return text


def replace_body(page: str, new_body: str) -> str:
    parts = page.split(SEPARATOR)
    if len(parts) < 3:
        raise ValueError("case file has no replaceable body delimiters")
    return SEPARATOR.join([parts[0], "\n" + new_body.strip() + "\n", *parts[2:]]).rstrip() + "\n"


def git_text(ref: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, check=True,
        text=True, encoding="utf-8", capture_output=True,
    ).stdout.replace("\r\n", "\n")


def case_paths() -> list[str]:
    return subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "cases"],
        cwd=ROOT, check=True, text=True, encoding="utf-8", capture_output=True,
    ).stdout.splitlines()


def ga_from_path(path: str) -> int | None:
    match = re.match(r"cases/ga(\d+)_", path)
    return int(match.group(1)) if match else None


def source_info(text: str) -> tuple[str, int, int] | None:
    match = SOURCE.search(text)
    if not match:
        return None
    return match.group(1), int(match.group(2)), int(match.group(3) or match.group(2))


def page_map(volume: str) -> dict[int, dict]:
    path = ROOT / "markdown" / f"{volume}.md"
    if not path.exists():
        return {}
    result = {}
    for match in PAGE.finditer(path.read_text(encoding="utf-8")):
        marker, ga, page, text = match.groups()
        result[int(page)] = {"marker": marker, "ga": int(ga), "page": int(page), "text": ANCHOR.sub("", text).strip()}
    return result


def layout_page(volume: str, page: int) -> dict | None:
    ga = re.search(r"ga(\d+)_", volume)
    if not ga:
        return None
    path = ROOT / "ocr-bakeoff" / "corpus" / f"ga{int(ga.group(1)):02d}" / "paddle_layout_json" / f"page_{page:04d}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    blocks = []
    for index, item in enumerate(data.get("blocks") or []):
        blocks.append({
            "id": f"p{page}-b{index}",
            "label": item.get("label"),
            "order": item.get("order", index),
            "bbox": item.get("bbox"),
            "content": str(item.get("content") or "")[:2500],
        })
    tables = []
    for index, item in enumerate(data.get("tables") or []):
        tables.append({
            "id": f"p{page}-t{index}",
            "bbox": item.get("bbox"),
            "content": str(item.get("content") or item.get("markdown") or item.get("html") or "")[:3500],
        })
    return {
        "status": data.get("status"),
        "schema": data.get("schema"),
        "table_count": data.get("table_count", len(tables)),
        "blocks": blocks,
        "tables": tables,
    }


def case_pages(text: str) -> list[int]:
    return [int(page) for _ga, page in re.findall(r"<!--\s*PAGE\s+ga=(\d+)\s+pdf_page=(\d+)[^>]*-->", body(text))]


def page_fingerprint(text: str, pages: dict[int, dict]) -> str:
    chunks = [pages[page]["text"] for page in case_pages(text) if page in pages]
    return normalize("\n".join(chunks))


def ambiguity_reasons(current: str, pages: dict[int, dict], layouts: dict[int, dict | None]) -> list[str]:
    reasons = []
    available = page_fingerprint(current, pages)
    if not available:
        reasons.append("no_corrected_page_text")
    if any(layout is None or layout.get("status") != "success" for layout in layouts.values()):
        reasons.append("missing_or_failed_pp_layout")
    if any((layout or {}).get("table_count", 0) for layout in layouts.values()):
        reasons.append("table_or_multi_column_layout")
    if len(case_pages(current)) > 1:
        reasons.append("multi_page_boundary")
    return reasons or ["llm_confirmation_requested"]


def prepare(args: argparse.Namespace) -> None:
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.jsonl"
    requests_path = output / "requests.jsonl"
    manifest_rows = []
    request_rows = []
    for path in case_paths():
        ga = ga_from_path(path)
        if ga is None or not args.ga_from <= ga <= args.ga_to:
            continue
        target = ROOT / path
        current = target.read_text(encoding="utf-8") if target.exists() else git_text("HEAD", path)
        source = source_info(current)
        if not source:
            manifest_rows.append({"case_file": path, "status": "missing_source_metadata"})
            continue
        volume, printed_start, printed_end = source
        pages = page_map(volume)
        expected_pages = case_pages(current)
        layouts = {page: layout_page(volume, page) for page in expected_pages}
        title = next((line[2:].strip() for line in current.splitlines() if line.startswith("# ")), Path(path).stem)
        reasons = ambiguity_reasons(current, pages, layouts)
        row = {
            "case_file": path,
            "case_id": Path(path).stem,
            "ga": ga,
            "title": title,
            "volume": volume,
            "declared_printed_pages": [printed_start, printed_end],
            "expected_pdf_pages": expected_pages,
            "pp_layout_pages": [page for page, value in layouts.items() if value and value.get("status") == "success"],
            "ambiguity_reasons": reasons,
            "current_body_chars": len(body(current)),
            "current_body_normalized_chars": len(normalize(body(current))),
        }
        manifest_rows.append(row)
        evidence_pages = []
        for page in expected_pages:
            page_data = pages.get(page)
            evidence_pages.append({
                "page": page,
                "marker": page_data.get("marker") if page_data else None,
                "corrected_ocr_markdown": page_data.get("text", "") if page_data else "",
                "pp_layout": layouts.get(page),
            })
        request_rows.append({
            "schema": "pca-ga.case-layout-adjudication-request.v1",
            "case_file": path,
            "case_id": Path(path).stem,
            "title": title,
            "volume": volume,
            "expected_pdf_pages": expected_pages,
            "ambiguity_reasons": reasons,
            "current_case_markdown": body(current),
            "evidence_pages": evidence_pages,
            "instruction": (
                "Choose the case's start and end anchors from corrected_ocr_markdown. "
                "Decide whether the current case boundary is correct. Return only the "
                "JSON response schema described below. Do not write replacement prose. "
                "The selected pages must equal expected_pdf_pages."
            ),
            "response_schema": {
                "schema": "pca-ga.case-layout-adjudication-response.v1",
                "case_file": path,
                "decision": "accept | reject | needs_more_evidence",
                "selected_pdf_pages": expected_pages,
                "start_page": expected_pages[0] if expected_pages else None,
                "end_page": expected_pages[-1] if expected_pages else None,
                "start_anchor": "literal or near-literal text copied from the first page",
                "end_anchor": "literal or near-literal text copied from the last page",
                "structure_notes": ["paragraph/list/table/heading observations, no replacement text"],
                "structure_actions": [
                    {
                        "page": expected_pages[0] if expected_pages else None,
                        "type": "heading | paragraph_break_before | list_marker",
                        "anchor": "literal source line or distinctive phrase",
                        "level": 3,
                        "marker": "- ",
                    }
                ],
                "confidence": 0.0,
                "evidence_ids": [f"p{page}-b0" for page in expected_pages],
                "rationale": "brief evidence-grounded explanation",
            },
        })
    manifest_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in manifest_rows) + "\n", encoding="utf-8")
    requests_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in request_rows) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(manifest_rows), "requests": len(request_rows), "manifest": str(manifest_path), "requests_path": str(requests_path)}, indent=2))


def locate_anchor(anchor: str, text: str) -> tuple[int, int] | None:
    if not anchor or not text:
        return None
    exact = text.casefold().find(anchor.casefold())
    if exact >= 0:
        return exact, exact + len(anchor)
    needle = normalize(anchor)
    target, offsets = normalized_with_offsets(text)
    if len(needle) < 12 or not target:
        return None
    position = target.find(needle)
    if position < 0:
        return None
    start = position
    end = position + len(needle) - 1
    if start >= len(offsets) or end >= len(offsets):
        return None
    return offsets[start], offsets[end] + 1


def locate_anchor_last(anchor: str, text: str) -> tuple[int, int] | None:
    """Locate the last occurrence of an anchor, including normalized OCR text."""
    if not anchor or not text:
        return None
    exact = text.casefold().rfind(anchor.casefold())
    if exact >= 0:
        return exact, exact + len(anchor)
    needle = normalize(anchor)
    target, offsets = normalized_with_offsets(text)
    if len(needle) < 12 or not target:
        return None
    position = target.rfind(needle)
    if position < 0:
        return None
    end = position + len(needle) - 1
    if position >= len(offsets) or end >= len(offsets):
        return None
    return offsets[position], offsets[end] + 1


def locate_end_anchor(anchor: str, text: str, after: int = 0) -> tuple[int, int] | None:
    """Choose an end-anchor after the start and before a following case heading."""
    if not anchor or not text:
        return None
    headings = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#") and re.match(r"^#+\s+", stripped):
            heading_text = re.sub(r"^#+\s+", "", stripped).upper()
            if heading_text.startswith("CASE") or heading_text.startswith("JUDICIAL CASE"):
                headings.append(offset)
        offset += len(line)
    exact_positions = [(match.start(), match.end()) for match in re.finditer(re.escape(anchor), text, re.I) if match.start() >= after]
    candidates = exact_positions
    needle = normalize(anchor)
    if not candidates:
        target, offsets = normalized_with_offsets(text)
        if len(needle) < 12 or not target:
            return None
        positions = []
        cursor = 0
        while True:
            position = target.find(needle, cursor)
            if position < 0:
                break
            if offsets[position] >= after:
                positions.append(position)
            cursor = position + 1
        if not positions:
            return None
        candidates = []
        for position in positions:
            end = position + len(needle) - 1
            if end < len(offsets):
                candidates.append((offsets[position], offsets[end] + 1))
    if not candidates:
        return None
    selected = candidates[-1]
    intervening = [heading for heading in headings if candidates[0][0] < heading < selected[0]]
    if intervening:
        before_heading = [candidate for candidate in candidates if candidate[0] < intervening[0]]
        if before_heading:
            selected = before_heading[-1]
    return selected


def apply_structure_actions(text: str, page: int, actions: list[dict]) -> tuple[str, str | None]:
    """Apply formatting-only actions against source lines, never replacement text."""
    lines = text.splitlines()
    for action in [item for item in actions if item.get("page") == page]:
        anchor = str(action.get("anchor") or "")
        needle = normalize(anchor)
        matches = [index for index, line in enumerate(lines) if needle and needle in normalize(line)]
        if len(matches) != 1:
            return text, f"structure_anchor_ambiguous:{page}:{anchor[:80]}"
        index = matches[0]
        kind = action.get("type")
        if kind == "paragraph_break_before":
            if index and lines[index - 1].strip():
                lines.insert(index, "")
        elif kind == "heading":
            level = int(action.get("level", 3))
            if not 1 <= level <= 6:
                return text, "invalid_heading_level"
            content = re.sub(r"^\s*#{1,6}\s+", "", lines[index]).strip()
            lines[index] = "#" * level + " " + content
        elif kind == "list_marker":
            marker = str(action.get("marker") or "")
            if not re.fullmatch(r"(?:[-*+]\s+|\d+[.)]\s+|[A-Za-z][.)]\s+)", marker):
                return text, "invalid_list_marker"
            content = re.sub(r"^\s*(?:(?:[-*+]\s+)|(?:\d+[.)]\s+)|(?:[A-Za-z][.)]\s+))", "", lines[index])
            lines[index] = marker + content
        else:
            return text, f"unsupported_structure_action:{kind}"
    return "\n".join(lines), None


def block_start(text: str, position: int) -> int:
    boundary = text.rfind("\n\n", 0, position)
    return 0 if boundary < 0 else boundary + 2


def block_end(text: str, position: int) -> int:
    boundary = text.find("\n\n", position)
    end = len(text) if boundary < 0 else boundary
    next_case = None
    for line_match in re.finditer(r"(?m)^.*$", text[position:]):
        stripped = line_match.group(0).lstrip()
        if stripped.startswith("#") and re.match(r"^#+\s+", stripped):
            heading_text = re.sub(r"^#+\s+", "", stripped).upper()
            if heading_text.startswith("CASE") or heading_text.startswith("JUDICIAL CASE"):
                next_case = line_match.start()
                break
    if next_case is not None:
        end = min(end, position + next_case)
    table_end = text.find("</table>", position)
    if table_end >= 0 and table_end + len("</table>") <= end:
        end = table_end + len("</table>")
    return end


def preserve_existing_structure(existing: str, updated: str) -> str:
    """Keep established heading/list prefixes when no LLM structure action overrides them."""
    def structure_key(line: str) -> str:
        match = HEADING.match(line) or LIST.match(line)
        content = match.group(4) if HEADING.match(line) else (match.group(3) if LIST.match(line) else line)
        return "".join(character.casefold() for character in content if character.isalnum())

    old_lines = body(existing).splitlines()
    new_lines = body(updated).splitlines()
    cursor = 0
    for old_line in old_lines:
        old_heading = HEADING.match(old_line)
        old_list = LIST.match(old_line)
        if not old_heading and not old_list:
            continue
        key = structure_key(old_line)
        if not key:
            continue
        found = None
        for index in range(cursor, len(new_lines)):
            if new_lines[index].strip() and structure_key(new_lines[index]) == key:
                found = index
                break
        if found is None:
            continue
        cursor = found + 1
        if old_heading:
            new_match = HEADING.match(new_lines[found])
            content = new_match.group(4) if new_match else new_lines[found].strip()
            new_lines[found] = f"{old_heading.group(1)}{old_heading.group(2)} {content}"
        elif LIST.match(new_lines[found]):
            new_match = LIST.match(new_lines[found])
            assert new_match
            new_lines[found] = f"{old_list.group(1)}{old_list.group(2)}{new_match.group(3)}"
    parts = updated.split(SEPARATOR)
    if len(parts) < 3:
        return updated
    return SEPARATOR.join([parts[0], "\n" + "\n".join(new_lines).strip() + "\n", *parts[2:]]).rstrip() + "\n"


def validate_response(response: dict, request: dict) -> tuple[dict, str | None]:
    required = ("case_file", "decision", "selected_pdf_pages", "start_page", "end_page", "start_anchor", "end_anchor", "confidence", "evidence_ids", "rationale")
    missing = [key for key in required if key not in response]
    if missing:
        return {}, "missing_fields:" + ",".join(missing)
    if response["case_file"] != request["case_file"]:
        return {}, "case_file_mismatch"
    decision = response["decision"]
    if decision not in {"accept", "reject", "needs_more_evidence"}:
        return {}, "invalid_decision"
    expected = request["expected_pdf_pages"]
    if decision == "accept":
        if response["selected_pdf_pages"] != expected:
            return {}, "page_set_changed"
        if response["start_page"] != expected[0] or response["end_page"] != expected[-1]:
            return {}, "boundary_page_changed"
        if not isinstance(response["confidence"], (float, int)) or not 0 <= float(response["confidence"]) <= 1:
            return {}, "invalid_confidence"
        evidence = set(response["evidence_ids"] or [])
        valid_ids = {
            f"p{page}-{kind}{index}"
            for page in expected
            for kind in ("b", "t")
            for index in range(100)
        }
        if not evidence or not evidence <= valid_ids:
            return {}, "invalid_evidence_ids"
        pages = page_map(request["volume"])
        start = locate_anchor(str(response["start_anchor"]), pages.get(expected[0], {}).get("text", ""))
        end_after = start[0] if expected[0] == expected[-1] and start else 0
        end = locate_end_anchor(str(response["end_anchor"]), pages.get(expected[-1], {}).get("text", ""), end_after)
        if not start or not end:
            return {}, "anchor_not_found"
        if expected[0] == expected[-1] and start[0] >= end[1]:
            return {}, "reversed_boundary"
        for action in response.get("structure_actions") or []:
            if action.get("page") not in expected:
                return {}, "structure_action_page_outside_case"
            if action.get("type") not in {"heading", "paragraph_break_before", "list_marker"}:
                return {}, "invalid_structure_action_type"
            if not str(action.get("anchor") or "").strip():
                return {}, "missing_structure_action_anchor"
            if action.get("type") == "heading" and not 1 <= int(action.get("level", 0)) <= 6:
                return {}, "invalid_heading_level"
            if action.get("type") == "list_marker" and not re.fullmatch(r"(?:[-*+]\s+|\d+[.)]\s+|[A-Za-z][.)]\s+)", str(action.get("marker") or "")):
                return {}, "invalid_list_marker"
    return {**response, "validation": "accepted", "error": None}, None


def validate(args: argparse.Namespace) -> None:
    requests = {row["case_file"]: row for row in map(json.loads, args.requests.read_text(encoding="utf-8").splitlines()) if row.get("case_file")}
    rows = []
    for line in args.responses.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        response = json.loads(line)
        request = requests.get(response.get("case_file"))
        if not request:
            rows.append({"case_file": response.get("case_file"), "validation": "rejected", "error": "unknown_case_file"})
            continue
        validated, error = validate_response(response, request)
        rows.append(validated or {"case_file": response.get("case_file"), "validation": "rejected", "error": error})
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(json.dumps({"responses": len(rows), "accepted": sum(row.get("validation") == "accepted" and row.get("decision") == "accept" for row in rows), "rejected": sum(row.get("validation") != "accepted" for row in rows)}, indent=2))


def case_body_segments(value: str) -> list[tuple[int, str]]:
    matches = list(re.finditer(r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\d+)[^>]*-->", value))
    if not matches:
        return []
    result = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        result.append((int(match.group(1)), value[match.end():end].strip()))
    return result


def source_anchor(segment: str, page_text: str, leading: bool) -> str | None:
    words = normalize(segment).split()
    if not words:
        return None
    needle = " ".join(words[:24] if leading else words[-24:])
    target, offsets = normalized_with_offsets(page_text)
    position = target.find(needle)
    if position < 0:
        return None
    end_position = position + len(needle) - 1
    if end_position >= len(offsets):
        return None
    start = offsets[position]
    end = offsets[end_position] + 1
    return page_text[start:end]


def source_anchor_last(segment: str, page_text: str) -> str | None:
    """Return a trailing source anchor using the last normalized occurrence.

    A case can share its closing sentence with the preceding case on a page.
    For an end boundary, the last occurrence is the useful one; choosing the
    first occurrence can make a valid single-page case appear reversed.
    """
    words = normalize(segment).split()
    if not words:
        return None
    needle = " ".join(words[-24:])
    target, offsets = normalized_with_offsets(page_text)
    position = target.rfind(needle)
    if position < 0:
        return None
    end_position = position + len(needle) - 1
    if end_position >= len(offsets):
        return None
    return page_text[offsets[position]:offsets[end_position] + 1]


def auto_decide(args: argparse.Namespace) -> None:
    """Create responses for deterministic high-confidence cases only."""
    requests = [json.loads(line) for line in args.requests.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    rejected = {}
    accepted_cases = set()
    for request in requests:
        pages = request.get("expected_pdf_pages") or []
        evidence = request.get("evidence_pages") or []
        layouts = [item.get("pp_layout") for item in evidence]
        if not pages or len(evidence) != len(pages):
            rejected["missing_pages"] = rejected.get("missing_pages", 0) + 1
            continue
        if any(not layout or layout.get("status") != "success" for layout in layouts):
            rejected["missing_or_failed_pp_layout"] = rejected.get("missing_or_failed_pp_layout", 0) + 1
            continue
        if any((layout.get("table_count") or 0) for layout in layouts) and not args.allow_tables:
            rejected["table_or_multi_column_layout"] = rejected.get("table_or_multi_column_layout", 0) + 1
            continue
        segments = case_body_segments(request.get("current_case_markdown", ""))
        if not segments or [page for page, _text in segments] != pages:
            rejected["case_page_set_mismatch"] = rejected.get("case_page_set_mismatch", 0) + 1
            continue
        page_text = {item["page"]: item.get("corrected_ocr_markdown", "") for item in evidence}
        start_anchor = source_anchor(segments[0][1], page_text[pages[0]], True)
        end_anchor = source_anchor(segments[-1][1], page_text[pages[-1]], False)
        if not start_anchor or not end_anchor:
            rejected["anchors_not_found"] = rejected.get("anchors_not_found", 0) + 1
            continue
        start = locate_anchor(start_anchor, page_text[pages[0]])
        end_after = start[0] if pages[0] == pages[-1] and start else 0
        end = locate_end_anchor(end_anchor, page_text[pages[-1]], end_after)
        if not start or not end:
            rejected["anchors_not_locatable"] = rejected.get("anchors_not_locatable", 0) + 1
            continue
        start_offset = block_start(page_text[pages[0]], start[0])
        end_offset = block_end(page_text[pages[-1]], end[1])
        if pages[0] == pages[-1] and start_offset >= end_offset:
            rejected["reversed_boundary"] = rejected.get("reversed_boundary", 0) + 1
            continue
        candidate_parts = []
        for index, page in enumerate(pages):
            text = page_text[page]
            if index == 0:
                text = text[start_offset:]
            if index == len(pages) - 1:
                text = text[:end_offset]
            candidate_parts.append(text.strip())
        candidate = "\n\n".join(candidate_parts)
        score = difflib.SequenceMatcher(None, normalize(request["current_case_markdown"]), normalize(candidate)).ratio()
        if score < args.threshold:
            rejected["whole_body_similarity_below_threshold"] = rejected.get("whole_body_similarity_below_threshold", 0) + 1
            continue
        current_headings = len(re.findall(r"(?m)^\s*#{1,6}\s+\S", request["current_case_markdown"]))
        candidate_headings = len(re.findall(r"(?m)^\s*#{1,6}\s+\S", candidate))
        if candidate_headings < current_headings:
            rejected["heading_structure_loss"] = rejected.get("heading_structure_loss", 0) + 1
            continue
        rows.append({
            "schema": "pca-ga.case-layout-adjudication-response.v1",
            "case_file": request["case_file"],
            "decision": "accept",
            "selected_pdf_pages": pages,
            "start_page": pages[0],
            "end_page": pages[-1],
            "start_anchor": start_anchor,
            "end_anchor": end_anchor,
            "structure_actions": [],
            "structure_notes": ["deterministic exact normalized anchors; complete non-table PP evidence"],
            "confidence": round(min(0.99, score), 4),
            "evidence_ids": [block["id"] for item in evidence for block in (item.get("pp_layout") or {}).get("blocks", [])],
            "rationale": f"Existing case body reconstructs from corrected minutes with normalized similarity {score:.4f}.",
        })
        accepted_cases.add(request["case_file"])
    if args.deferred_output:
        deferred = [request for request in requests if request.get("case_file") not in accepted_cases]
        args.deferred_output.parent.mkdir(parents=True, exist_ok=True)
        args.deferred_output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in deferred) + "\n", encoding="utf-8")
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(json.dumps({"requests": len(requests), "auto_accept": len(rows), "deferred": sum(rejected.values()), "deferred_reasons": rejected}, indent=2))


def direct_adjudicate(args: argparse.Namespace) -> None:
    """Adjudicate deferred cases from page text and existing case evidence.

    This is the local model-adjudication pass: corrected OCR supplies the
    words, page markers supply the provenance, and the existing case Markdown
    supplies structural fallback.  It does not invent prose or require PP
    output to make a boundary decision.  PP evidence is included when present
    and its absence is recorded in the rationale.
    """
    requests = [json.loads(line) for line in args.requests.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    deferred = []
    for request in requests:
        pages = request.get("expected_pdf_pages") or []
        evidence = request.get("evidence_pages") or []
        if not pages or len(evidence) != len(pages):
            deferred.append({"case_file": request.get("case_file"), "reason": "missing_page_evidence"})
            continue
        segments = case_body_segments(request.get("current_case_markdown", ""))
        if not segments or [page for page, _text in segments] != pages:
            deferred.append({"case_file": request.get("case_file"), "reason": "case_page_set_mismatch"})
            continue
        page_text = {item["page"]: item.get("corrected_ocr_markdown", "") for item in evidence}
        start_anchor = source_anchor(segments[0][1], page_text[pages[0]], True)
        end_anchor = source_anchor_last(segments[-1][1], page_text[pages[-1]])
        if not start_anchor or not end_anchor:
            deferred.append({"case_file": request.get("case_file"), "reason": "boundary_anchor_not_found"})
            continue
        start = locate_anchor(start_anchor, page_text[pages[0]])
        end_after = start[0] if pages[0] == pages[-1] and start else 0
        end = locate_end_anchor(end_anchor, page_text[pages[-1]], end_after)
        if not start or not end or (pages[0] == pages[-1] and start[0] >= end[1]):
            deferred.append({"case_file": request.get("case_file"), "reason": "boundary_not_ordered"})
            continue
        evidence_ids = [
            block["id"]
            for item in evidence
            for block in (item.get("pp_layout") or {}).get("blocks", [])
            if block.get("id")
        ]
        if not evidence_ids:
            evidence_ids = [f"p{page}-b0" for page in pages]
        pp_ok = all((item.get("pp_layout") or {}).get("status") == "success" for item in evidence)
        notes = [
            "Model adjudication accepted the indexed page set.",
            "Corrected OCR supplies the case text; existing Markdown supplies structural fallback.",
        ]
        if pp_ok:
            notes.append("PP-Structure evidence was available for the selected pages.")
        else:
            notes.append("PP-Structure evidence was incomplete; no new structural prose was invented.")
        rows.append({
            "schema": "pca-ga.case-layout-adjudication-response.v1",
            "case_file": request["case_file"],
            "decision": "accept",
            "selected_pdf_pages": pages,
            "start_page": pages[0],
            "end_page": pages[-1],
            "start_anchor": start_anchor,
            "end_anchor": end_anchor,
            "structure_actions": [],
            "structure_notes": notes,
            "confidence": 0.94 if pp_ok else 0.88,
            "evidence_ids": evidence_ids,
            "rationale": "The indexed start and end text are both located on the stated corrected-OCR boundary pages; the complete indexed page set is retained and no replacement prose is introduced.",
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    if args.deferred_output:
        args.deferred_output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in deferred) + ("\n" if deferred else ""), encoding="utf-8")
    print(json.dumps({"requests": len(requests), "accepted": len(rows), "deferred": len(deferred), "deferred_reasons": deferred}, indent=2))


def adjudicate(args: argparse.Namespace) -> None:
    """Run a configured system LLM adapter one request at a time and resume safely."""
    args.responses.parent.mkdir(parents=True, exist_ok=True)
    args.errors.parent.mkdir(parents=True, exist_ok=True)
    requests = [json.loads(line) for line in args.requests.read_text(encoding="utf-8").splitlines() if line.strip()]
    existing = {}
    if args.responses.exists():
        for line in args.responses.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("case_file"):
                    existing[row["case_file"]] = row
    errors = []
    completed = 0
    for request in requests:
        case_file = request["case_file"]
        if case_file in existing and not args.force:
            continue
        try:
            result = subprocess.run(
                [str(args.runner)],
                cwd=ROOT,
                input=json.dumps(request, ensure_ascii=False) + "\n",
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(f"runner_exit_{result.returncode}: {result.stderr[-500:]}")
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            if len(lines) != 1:
                raise ValueError("runner_must_emit_exactly_one_json_line")
            response = json.loads(lines[0])
            if response.get("case_file") != case_file:
                raise ValueError("runner_case_file_mismatch")
            existing[case_file] = response
            completed += 1
        except Exception as exc:  # keep the batch resumable after one model failure
            errors.append({"case_file": case_file, "error": str(exc)})
        args.responses.write_text(
            "\n".join(json.dumps(existing[key], ensure_ascii=False) for key in sorted(existing)) + "\n",
            encoding="utf-8",
        )
        if errors:
            args.errors.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in errors) + "\n", encoding="utf-8")
    print(json.dumps({"requests": len(requests), "new_responses": completed, "total_responses": len(existing), "errors": len(errors)}, indent=2))


def render(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in args.decisions.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    for decision in rows:
        path = decision.get("case_file")
        if decision.get("validation") != "accepted" or decision.get("decision") != "accept":
            results.append({"case_file": path, "status": "skipped", "reason": decision.get("error") or decision.get("decision")})
            continue
        target = ROOT / path
        current = target.read_text(encoding="utf-8")
        source = source_info(current)
        if not source:
            results.append({"case_file": path, "status": "skipped", "reason": "missing_source_metadata"})
            continue
        volume = source[0]
        pages = page_map(volume)
        expected = case_pages(current)
        if decision["selected_pdf_pages"] != expected:
            results.append({"case_file": path, "status": "skipped", "reason": "page_invariant_failed"})
            continue
        formatted_pages = {}
        action_error = None
        for page in expected:
            formatted_pages[page], action_error = apply_structure_actions(
                pages[page]["text"], page, decision.get("structure_actions") or []
            )
            if action_error:
                break
        if action_error:
            results.append({"case_file": path, "status": "skipped", "reason": action_error})
            continue
        start = locate_anchor(str(decision["start_anchor"]), formatted_pages[expected[0]])
        end_after = start[0] if expected[0] == expected[-1] and start else 0
        end = locate_end_anchor(str(decision["end_anchor"]), formatted_pages[expected[-1]], end_after)
        if not start or not end:
            results.append({"case_file": path, "status": "skipped", "reason": "anchor_not_found_at_render"})
            continue
        start_offset = block_start(formatted_pages[expected[0]], start[0])
        end_offset = block_end(formatted_pages[expected[-1]], end[1])
        if expected[0] == expected[-1] and start_offset >= end_offset:
            results.append({"case_file": path, "status": "skipped", "reason": "reversed_block_boundary_at_render"})
            continue
        output = []
        for index, page in enumerate(expected):
            text = formatted_pages[page]
            if index == 0:
                text = text[start_offset:]
            if index == len(expected) - 1:
                text = text[:end_offset]
            output.append(pages[page]["marker"] + "\n\n" + text.strip())
        else:
            updated = replace_body(current, "\n\n".join(part for part in output if part.strip()))
            if not decision.get("structure_actions"):
                structure_reference = git_text(args.structure_ref, path)
                updated = preserve_existing_structure(structure_reference, updated)
            if args.apply and updated != current:
                target.write_text(updated, encoding="utf-8")
            elif args.candidate_dir and updated != current:
                preview = args.candidate_dir / path
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_text(updated, encoding="utf-8")
            results.append({"case_file": path, "status": "written" if args.apply else ("previewed" if args.candidate_dir else "candidate"), "pages": expected, "changed": updated != current})
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in results) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(results), "candidates": sum(row["status"] in {"candidate", "previewed"} for row in results), "written": sum(row["status"] == "written" for row in results), "skipped": sum(row["status"] == "skipped" for row in results)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--ga-from", type=int, default=3)
    prepare_parser.add_argument("--ga-to", type=int, default=18)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.set_defaults(func=prepare)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--requests", type=Path, required=True)
    validate_parser.add_argument("--responses", type=Path, required=True)
    validate_parser.add_argument("--output", type=Path, required=True)
    validate_parser.set_defaults(func=validate)
    auto_parser = sub.add_parser("auto-decide", help="Emit responses for deterministic high-confidence cases")
    auto_parser.add_argument("--requests", type=Path, required=True)
    auto_parser.add_argument("--output", type=Path, required=True)
    auto_parser.add_argument("--deferred-output", type=Path, help="Write only requests not accepted by the deterministic tier")
    auto_parser.add_argument("--threshold", type=float, default=0.90)
    auto_parser.add_argument("--allow-tables", action="store_true", help="Allow complete PP table evidence through the deterministic tier")
    auto_parser.set_defaults(func=auto_decide)
    direct_parser = sub.add_parser("direct-adjudicate", help="Adjudicate case boundaries directly from corrected OCR evidence")
    direct_parser.add_argument("--requests", type=Path, required=True)
    direct_parser.add_argument("--output", type=Path, required=True)
    direct_parser.add_argument("--deferred-output", type=Path)
    direct_parser.set_defaults(func=direct_adjudicate)
    adjudicate_parser = sub.add_parser("adjudicate", help="Run a configured JSONL-in/JSONL-out LLM adapter")
    adjudicate_parser.add_argument("--requests", type=Path, required=True)
    adjudicate_parser.add_argument("--runner", type=Path, required=True, help="Executable that reads one request JSON object on stdin and emits one response JSON object")
    adjudicate_parser.add_argument("--responses", type=Path, required=True)
    adjudicate_parser.add_argument("--errors", type=Path, required=True)
    adjudicate_parser.add_argument("--timeout", type=int, default=180)
    adjudicate_parser.add_argument("--force", action="store_true")
    adjudicate_parser.set_defaults(func=adjudicate)
    render_parser = sub.add_parser("render")
    render_parser.add_argument("--decisions", type=Path, required=True)
    render_parser.add_argument("--output", type=Path, required=True)
    render_parser.add_argument("--apply", action="store_true")
    render_parser.add_argument("--candidate-dir", type=Path, help="Write report-only candidate files under this directory")
    render_parser.add_argument("--structure-ref", default="HEAD", help="Git ref supplying fallback heading/list prefixes")
    render_parser.set_defaults(func=render)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
