#!/usr/bin/env python3
"""Extract page-anchored, searchable candidate action passages from GA minutes.

This is a finding aid for action-trail research, not an authority or an auto-linker.
Every row preserves the Markdown passage and points to its minute page; researchers
must confirm relevance and transcribe adopted events into overture_events.jsonl.
"""
from __future__ import annotations

import json
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
MARKDOWN = ROOT / "markdown"
OUTPUT = ROOT / "index" / "overture_action_candidates.jsonl"
REVIEW_FILE = ROOT / "index" / "overture_action_candidate_reviews.jsonl"

# Keep manual review decisions when the searchable finding aid is regenerated.
REVIEWED_IDS: set[str] = set()
if OUTPUT.exists():
    for line in OUTPUT.read_text(encoding="utf-8").splitlines():
        try:
            previous = json.loads(line)
        except json.JSONDecodeError:
            continue
        if previous.get("reviewed"):
            REVIEWED_IDS.add(previous.get("candidate_id", ""))

# Research disposition is curated separately from the generated finding aid so
# a full candidate re-extraction cannot erase a researcher's reviewed links.
REVIEW_METADATA: dict[str, dict] = {}
if REVIEW_FILE.exists():
    for line in REVIEW_FILE.read_text(encoding="utf-8").splitlines():
        try:
            review = json.loads(line)
        except json.JSONDecodeError:
            continue
        candidate_id = review.get("candidate_id")
        if candidate_id:
            REVIEW_METADATA[candidate_id] = {
                key: review[key]
                for key in ("reviewed", "review_disposition", "review_note", "linked_record_ids")
                if key in review
            }

PAGE = re.compile(
    r'<a id="(?P<anchor>ga(?P<ga>\d+)-p(?P<pdf>\d+))"></a>\s*'
    r'<!-- PAGE ga=\d+ pdf_page=(?P<pdf_comment>\d+) printed_page=(?P<printed>null|\d+) -->'
)
OVERTURE_MENTION = re.compile(r"(?i)\bovertures?\s+(\d+)\b")
PATTERNS: dict[str, re.Pattern[str]] = {
    "advice": re.compile(
        r"(?i)(committee on constitutional business.{0,160}(advice|conflict)|"
        r"advice on overtures|in the opinion of the CCB|CCB.{0,100}"
        r"(advis|found|concluded|determined)|not in conflict with|"
        r"in conflict with|advice and consent|constitutional advice|"
        r"constitutional review)"
    ),
    "overture_or_amendment_action": re.compile(
        r"(?i)(\bovertures?\s+\d+\b.{0,300}\b(?:answer(?:s|ed)?|adopted|approved|"
        r"rejected|defeated|refer(?:s|red|ring)?|defer(?:s|red|ring)?|"
        r"amend(?:ed|ment)?|substitut(?:e|ed|ion)|"
        r"recommitted|withdrawn|postponed|carried over|ratified|affirmative|negative|"
        r"ruled out of order)\b)|"
        r"(\b(?:committee|assembly|motion|recommendation)\b.{0,200}\bovertures?\s+\d+"
        r"\b.{0,250}\b(?:adopted|approved|rejected|defeated|refer(?:s|red|ring)?|"
        r"defer(?:s|red|ring)?|recommitted|withdrawn|postponed|carried over|"
        r"answered|ratified|affirmative|negative)\b)|"
        r"(\b(?:committee|assembly|motion|recommendation)\b.{0,200}\b"
        r"(?:answer(?:s|ed)?|refer(?:s|red|ring)?|defer(?:s|red|ring)?|"
        r"adopted|approved|rejected|defeated|withdrawn|postponed|ratified)\b"
        r".{0,160}\bovertures?\s+\d+\b)|"
        r"(\b(?:amendment|substitute)\b.{0,250}\b(?:adopted|approved|rejected|"
        r"defeated|carried|substituted)\b)|"
        r"(amended to read|amendment was (?:adopted|approved|defeated|rejected)|"
        r"overtures?\s+\d+\s+(?:was|were)\s+amended|"
        r"motion to amend|moved to amend)"
    ),
    "presbytery_vote": re.compile(
        r"(?i)(presbyter(?:y|ies)).{0,110}(voted|vote of|votes were|by a vote|"
        r"unanimously)|"
        r"(presbyter(?:y|ies)).{0,100}(approved|adopted|ratified|concurred)"
        r".{0,70}(\d+\s*[-–]\s*\d+|by (?:a |an )?(?:majority|unanimous|two.thirds)"
        r"|at (?:its|their) (?:stated )?meeting)|"
        r"(approved|adopted|ratified|concurred|voted) by (?:the )?(?:"
        r"[\w .,'’-]{1,80}\s+presbyter(?:y|ies)|"
        r"presbyter(?:y|ies)\s+of\s+[\w .,'’-]{1,80})|"
        r"votes? (?:in|of) (?:the )?[\w .,'’-]{1,80}presbyter(?:y|ies)"
    ),
    "later_approval_or_ratification": re.compile(
        r"(?i)(declared adopted|declared ratified|now in effect|"
        r"two.thirds of the presbyteries|presbyteries (?:have |had )?(?:approved|"
        r"adopted|ratified|voted)|(?:ratified|ratification).{0,180}(?:assembly|presby|"
        r"overture|amendment))"
    ),
}


def candidates(path: Path):
    text = path.read_text(encoding="utf-8")
    markers = list(PAGE.finditer(text))
    volume = path.stem
    # Some committee recommendations introduce a multi-page list of overtures
    # answered by reference. The action is stated on the first page, while later
    # pages contain only the continued list and may end with “Adopted.” Carry
    # that context across page markers so those continuation passages remain
    # searchable and reviewable instead of disappearing from the packet.
    reference_list_active = False
    in_overtures_report = False
    overtures_heading_pending = False
    in_overtures_summary = False
    for index, marker in enumerate(markers):
        page_text = text[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(text)]
        occurrences: Counter[str] = Counter()
        # A blank-line split retains source paragraph boundaries; preserve the actual
        # Markdown wording and line structure in the candidate field. Overture report
        # locators are occasionally split into their own Markdown block (for example,
        # `...,` followed by `- **p.** 1041) be referred ...`), so index that joined
        # continuation as well as each standalone paragraph.
        blocks = [block.strip() for block in re.split(r"\n\s*\n", page_text) if block.strip()]
        passages = list(blocks)
        for previous, following in zip(blocks, blocks[1:]):
            if (previous and following
                    and re.search(r"[,(“\"]\s*$", previous)
                    and re.match(r"-\s+\*\*p\.\*\*\s+\d+", following)):
                passages.append(previous + "\n\n" + following)
        for passage in passages:
            if len(passage) < 20:
                if re.search(r"(?i)\breport of the\s*$", passage):
                    overtures_heading_pending = True
                elif (overtures_heading_pending
                        and re.search(r"(?i)\bovertures committee\b", passage)):
                    in_overtures_report = True
                    overtures_heading_pending = False
                continue
            if len(passage) < 20 or passage.startswith(("<!--", "<a id=")):
                continue
            searchable = re.sub(r"\s+", " ", passage)
            if re.search(r"(?i)\breport of the overtures committee\b", searchable):
                in_overtures_report = True
            elif re.search(r"(?i)\breport of the\s*$", searchable):
                overtures_heading_pending = True
            elif (overtures_heading_pending
                    and re.search(r"(?i)\bovertures committee\b", searchable)):
                in_overtures_report = True
                overtures_heading_pending = False
            if in_overtures_report and re.search(
                r"(?i)\bIII\.\s+Summary of Recommendations\b", searchable
            ):
                in_overtures_summary = True
            kinds = [kind for kind, pattern in PATTERNS.items() if pattern.search(searchable)]
            starts_reference_list = bool(re.search(
                r"(?i)following overtures be answered by reference to this action", searchable
            ))
            if (reference_list_active
                    and re.search(r"(?i)\bovertures?\s+\d+\s+from\b", searchable)
                    and "overture_or_amendment_action" not in kinds):
                kinds.append("overture_or_amendment_action")
            if (in_overtures_summary
                    and re.search(r"(?m)^\s*\d+\.\s+.+", passage)
                    and re.search(r"\b\d+\s*[-–]\s*\d+\s*[-–]\s*\d+\b", searchable)
                    and "overture_or_amendment_action" not in kinds):
                kinds.append("overture_or_amendment_action")
            if not kinds:
                if re.match(r"(?i)^\d+\.\s+that overture\s+\d+\s+from\b", searchable):
                    reference_list_active = False
                continue
            digest = hashlib.sha1(passage.encode("utf-8")).hexdigest()[:12]
            occurrences[digest] += 1
            printed = marker.group("printed")
            candidate_id = f"{volume}:{marker.group('anchor')}:{digest}:{occurrences[digest]}"
            row = {
                "candidate_id": candidate_id,
                "source_volume": volume,
                "ga_ordinal": int(marker.group("ga")),
                "source_printed_page": int(printed) if printed != "null" else None,
                "source_pdf_page": int(marker.group("pdf")),
                "source_anchor": f"#{marker.group('anchor')}",
                "source_link": f"../markdown/{volume}.md#{marker.group('anchor')}",
                "candidate_types": kinds,
                # References are literal search hints, not confirmed joins to catalogue rows.
                "overture_number_mentions": sorted({int(n) for n in OVERTURE_MENTION.findall(passage)}),
                "text": passage,
                "reviewed": candidate_id in REVIEWED_IDS,
            }
            row.update(REVIEW_METADATA.get(candidate_id, {}))
            yield row
            if starts_reference_list:
                reference_list_active = True
            elif reference_list_active and re.search(r"(?i)\badopted\b", searchable):
                reference_list_active = False
            if in_overtures_summary and re.search(
                r"(?i)\bIV\.\s+Recommendations\b", searchable
            ):
                in_overtures_summary = False
                in_overtures_report = False


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    # Let Windows choose its native newline translation; Gradle normalizes line
    # endings when tracking this generated JSONL as an input.
    with OUTPUT.open("w", encoding="utf-8") as out:
        for path in sorted(MARKDOWN.glob("ga*_*.md")):
            for row in candidates(path):
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
    print(f"wrote {count} page-anchored candidate passages -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
