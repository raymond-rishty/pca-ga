#!/usr/bin/env python3
"""Link the OVERTURES.md catalogue's Overture-number cell to each overture's
individual page (overtures/<vol>__o<num>.md), where one exists — mirroring how
CASES.md links to case pages. The Pages column keeps its minutes deep-link.

Post-process (run AFTER 20_markdown_index.py, both trees) rather than baked into
the DB generator, so a re-render can't revert it and corpus text edits in the
catalogue aren't regenerated away. Idempotent.

Usage:  42_link_overture_catalogue.py [ROOT]
"""
import json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
CAT = os.path.join(ROOT, "index", "OVERTURES.md")
MAP = os.path.join(ROOT, "index", "overture_pages_map.json")
EVENTS = os.path.join(ROOT, "index", "overture_events.jsonl")

SEC = re.compile(r"`(ga\d+_\d+)`")
MAX_OUTCOME_WORDS = 12


def concise_outcome(bundle, current=""):
    """Project a short catalogue disposition; the full explanation stays in the trail."""
    current = (current or "").strip()
    if current and len(current.split()) <= MAX_OUTCOME_WORDS:
        return current

    def compact(text):
        text = (text or "").strip()
        if not text:
            return ""
        # Keep an overture reference only when the action itself names one.
        if re.search(r"\bby reference\b", text, re.I):
            match = re.search(r"\bby reference\s+to\s+(?:GA\s*\d+\s+)?Overture\s+(\d+)\b", text, re.I)
            return f"Answered by reference to Overture {match.group(1)}" if match else "Answered by reference"
        if re.search(r"\banswer\w*\b.{0,100}\bnegative\b", text, re.I):
            return "Answered in the negative"
        if re.search(r"\banswer\w*\b.{0,100}\baffirmative\b", text, re.I):
            return "Answered in the affirmative"
        if re.search(r"\bwithdrawn\b", text, re.I):
            return "Withdrawn"
        if re.search(r"\b(defeated|failed to pass|not adopted)\b", text, re.I):
            return "Defeated"
        if re.search(r"\bapproved\b.{0,40}\bratified\b|\bratified\b", text, re.I):
            return "Approved and ratified"
        if re.search(r"\badopted as amended\b", text, re.I):
            return "Adopted as amended"
        if re.search(r"\badopted\b", text, re.I):
            return "Adopted"
        if re.search(r"\breferred\b", text, re.I):
            return "Referred"
        if re.search(r"\bcarried over\b|\bcontinued to GA\d+\b", text, re.I):
            return "Carried over"
        return ""

    summary = (bundle.get("disposition") or "").strip()
    label = compact(summary)
    if label:
        return label

    # Prefer the latest substantive Assembly action. Referrals, committee
    # recommendations/advice, and procedural notes are supporting trail detail.
    events = [event for event in bundle.get("events", [])
              if "assembly" in (event.get("phase") or "").lower()
              and not re.search(r"referral|committee recommendation|committee advice|constitutional advice|dissent|procedural",
                               event.get("phase") or "", re.I)]
    for event in reversed(events):
        label = compact(" ".join((event.get("outcome") or "", event.get("action_text") or "")))
        if label:
            return label

    # Some trails document advice or prior handling without a final Assembly vote.
    context = " ".join((summary, current))
    if re.search(r"\breconsider\w*\b", context, re.I) and re.search(r"\b(final|exact) disposition\b", context, re.I):
        return "Reconsidered; final disposition unclear"
    if re.search(r"\b(CCB|Committee on Constitutional Business)\b", context, re.I):
        if re.search(r"\bunconstitutional\b", context, re.I):
            return "CCB found overture unconstitutional"
        return "CCB advice; no Assembly action located"
    if re.search(r"\b(minority negative-answer recommendation|recommendation .* not before the Assembly for action)\b", context, re.I):
        return "No final Assembly action located"
    # If the trail records only a referral, it is still a concise and useful
    # outcome; do not turn it into a lengthy narrative about later reports.
    for event in reversed(bundle.get("events", [])):
        if "assembly" in (event.get("phase") or "").lower():
            label = compact(" ".join((event.get("outcome") or "", event.get("action_text") or "")))
            if label:
                return label
    label = compact(current)
    if label:
        return label
    if re.search(r"\b(previous|prior) Assembly action|already (?:been )?dealt with\b", context, re.I):
        return "Previously addressed; exact action unclear"
    if re.search(r"\b(no|not located|no later)\b.{0,60}\b(action|disposition|answer)\b", context, re.I):
        return "No final action located"
    return ""


def action_dispositions():
    """Read curated action bundles by stable record ID."""
    if not os.path.exists(EVENTS):
        return {}
    dispositions = {}
    with open(EVENTS, encoding="utf-8") as stream:
        for raw in stream:
            if not raw.strip():
                continue
            bundle = json.loads(raw)
            record_id = bundle.get("record_id")
            if not record_id:
                continue
            dispositions[record_id] = bundle
    return dispositions


def main():
    if not (os.path.exists(CAT) and os.path.exists(MAP)):
        print(f"[{ROOT}] OVERTURES.md or map missing — skip"); return
    pmap = json.load(open(MAP))
    action_summary_by_id = action_dispositions()
    vol = None; linked = 0; filled = 0; compacted = 0
    out = []
    for line in open(CAT).read().split("\n"):
        s = SEC.search(line)
        if line.startswith("## ") and s:
            vol = s.group(1)
        m = re.match(r"^\|\s*(?:\[(\d+)\]\([^)]+\)|(\d+))\s*\|", line)
        if m and vol:
            num = m.group(1) or m.group(2)
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            page_refs = re.findall(r"\[p\.(\d+)\]\([^)]*#ga\d+-p(\d+)\)", cells[4]) if len(cells) == 5 else []
            source_page = int(page_refs[0][1]) if page_refs else None
            record_id = f"overture:{vol}:{num}:p{source_page}" if source_page else None
            page = pmap.get(record_id) if record_id else None
            if record_id and len(cells) == 5:
                bundle = action_summary_by_id.get(record_id)
                if bundle:
                    was_blank = not cells[2].strip()
                    outcome = concise_outcome(bundle, cells[2])
                    if outcome and outcome != cells[2]:
                        cells[2] = outcome.replace("|", "\\|").replace("\n", " ").strip()
                        compacted += 1
                    line = "| " + " | ".join(cells) + " |"
                    if was_blank and cells[2].strip():
                        filled += 1
            if page:
                replacement = f"[{num}](../{page})"
                first_cell = m.group(0)
                line = line.replace(first_cell, f"| {replacement} |", 1)
                linked += 1
        out.append(line)
    open(CAT, "w").write("\n".join(out))
    print(f"[{ROOT}] linked {linked} overture-catalogue rows; filled {filled} blanks and shortened {compacted - filled} long outcomes from action trails")

if __name__ == "__main__":
    main()
