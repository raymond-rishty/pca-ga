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
from overture_taxonomy import classify

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
CAT = os.path.join(ROOT, "index", "OVERTURES.md")
MAP = os.path.join(ROOT, "index", "overture_pages_map.json")
EVENTS = os.path.join(ROOT, "index", "overture_events.jsonl")

SEC = re.compile(r"`(ga\d+_\d+)`")
MAX_OUTCOME_WORDS = 12


def _needs_outcome_projection(current):
    """Whether the current label describes procedure rather than the overture's result."""
    value = re.sub(r"\s+", " ", (current or "").strip().lower()).rstrip(".")
    if value in {"adopted", "adopted (final)", "answered by reference", "referred"}:
        return True
    if value.startswith("committee report adopted as amended"):
        # The amendment to the report may have changed the answer itself.
        return False
    if re.search(r"\b(answered|negative|affirmative|by reference|referred|returned|withdrawn|approved|ratified|defeated|moot|out of order|unconstitutional)\b", value):
        if re.search(r"\bas recommended\b", value) and re.search(r"\badopted\b", value):
            return True
        return value.startswith(("answered by adopted recommendation", "recommended the recorded disposition"))
    return bool(re.search(
        r"(?:adopted in gross|adopted this recommendation|adopted the committee recommendation|"
        r"adopted the committee of commissioners.? recommendation|adopted overtures committee recommendations|"
        r"adopted the overtures committee report recommendation|adopted recommendation \d+\.?$|"
        r"recommendation \d+ was among recommendations .* adopted in gross|"
        r"answered by adopted recommendation|recommended the recorded disposition)",
        value,
    ))


def _recommendation_outcome(bundle):
    """Infer an overture-level result only from its adopted recommendation text."""
    events = bundle.get("events", [])

    def summarize(text):
        text = re.sub(r"\s+", " ", (text or "")).strip()
        if not text:
            return ""
        if re.search(r"\bnot ratified\b|\b(?:required|two-thirds) presbytery concurrence was not received\b", text, re.I):
            return "Not ratified"
        reference = re.search(
            r"by[- ]reference\s+to\s+(?:the\s+answer\s+to\s+)?(?:(Overture\s+\d{4}[-–]\d+)|(?:GA\s*\d+\s+)?Overture\s+(\d+)|Recommendation\s+(\d+))",
            text, re.I,
        )
        if reference:
            if reference.group(1):
                return f"Answered by reference to {reference.group(1)}"
            if reference.group(2):
                return f"Answered by reference to Overture {reference.group(2)}"
            return f"Answered by reference to Recommendation {reference.group(3)}"
        # A final decision may explain that it superseded an earlier answer.
        # Honor the decision stated first rather than classifying both votes.
        leading_answer = re.match(r"^answered\s+in\s+the\s+(negative|affirmative)\b", text, re.I)
        if leading_answer:
            if leading_answer.group(1).lower() == "negative":
                return "Answered in the negative"
            return "Answered in the affirmative as amended" if re.search(r"\bas amended\b", text, re.I) else "Answered in the affirmative"
        negative_answer = re.search(r"\banswer\w*\b.{0,500}\bnegative\b|\bnegative\b.{0,300}\banswer\w*\b", text, re.I)
        affirmative_answer = re.search(r"\banswer\w*\b.{0,500}\baffirmative\b|\baffirmative\b.{0,300}\banswer\w*\b", text, re.I)
        if negative_answer and affirmative_answer:
            if re.search(r"\b(?:paragraphs?\s*[12]|parts?\s+(?:one|two|1|2)|both parts|partly)\b", text, re.I):
                return "Answered in part in the negative and affirmative"
            return ""
        if negative_answer:
            return "Answered in the negative"
        if affirmative_answer:
            return "Answered in the affirmative as amended" if re.search(r"\bas amended\b", text, re.I) else "Answered in the affirmative"
        if re.search(r"\brespond\w*\s+to\s+overtures?\b", text, re.I):
            if re.search(r"joining.and.receiving", text, re.I):
                return "Answered by directing the OPC to the joining-and-receiving process"
            if re.search(r"continue to encourage church planting", text, re.I):
                return "Answered by encouraging western church planting"
            return "Answered with the adopted committee response"
        if re.search(r"\b(?:refer|referred|return|returned)\b.{0,160}\b(?:back to|to)\s+(?:the\s+)?(?:presbytery|author|overturing presbytery)\b", text, re.I):
            return "Referred back to Presbytery"
        if re.search(r"\b(?:refer|referred)\b.{0,160}\b(?:committee|study|consideration)\b", text, re.I):
            return "Referred for study"
        if re.search(r"\bapproved\b.{0,60}\bif the way\b", text, re.I):
            return "Approved if the way is clear"
        if re.search(r"\bapproved\b", text, re.I):
            return "Approved"
        if re.search(r"\badopted\b.{0,100}\b(?:division|boundary|transfer|merger)\s+(?:plan|proposal|change)?\b", text, re.I):
            return "Approved"
        return ""

    # Prefer a recorded Assembly answer when the action trail has one.
    assembly_events = [event for event in events
                       if "assembly" in (event.get("phase") or "").lower()
                       and not re.search(r"deferral|referral|implementation|procedural",
                                         event.get("phase") or "", re.I)]
    for event in reversed(assembly_events):
        # Action excerpts often contain unrelated motions or recommendation
        # lists. Use the curated event outcome here; recommendation text below
        # is linked to this overture and can supply the answer when needed.
        label = summarize(event.get("outcome", ""))
        if label and label not in {"Adopted", "Adopted as amended"}:
            return label

    # A generic Assembly adoption often points to the Committee of Commissioners'
    # report. Prefer that recommendation when both permanent and commissioner
    # recommendations appear in the same action trail.
    recommendations = [event for event in events if "recommendation" in (event.get("phase") or "").lower()]
    if any("minority" in (event.get("phase") or "").lower() for event in recommendations) and any(
        "minority" in (event.get("outcome", "") + " " + event.get("action_text", "")).lower()
        for event in assembly_events
    ):
        recommendations = [event for event in recommendations if "minority" in (event.get("phase") or "").lower()]
    else:
        recommendations = [event for event in recommendations if "minority" not in (event.get("phase") or "").lower()]
    commissioner_recommendations = [event for event in recommendations if "committee of commissioners" in (event.get("actor") or "").lower()]
    if commissioner_recommendations:
        recommendations = commissioner_recommendations
    inferred = []
    for event in reversed(recommendations):
        label = summarize(event.get("outcome", ""))
        if label in {"Adopted", "Adopted as amended"}:
            label = ""
        action_label = summarize(event.get("action_text", ""))
        # A curator may summarize a committee's routing step as a referral even
        # when its overture-specific recommendation text states an answer.
        if action_label.startswith("Answered in "):
            label = action_label
        else:
            label = label or action_label
        if label:
            inferred.append(label)
        elif len(recommendations) > 1:
            # A multi-part recommendation with an unclassified component may
            # have more than one kind of answer; keep the curated summary.
            return ""
    if inferred and len(set(inferred)) == 1:
        return inferred[0]
    return ""


def concise_outcome(bundle, current=""):
    """Project a short catalogue disposition; the full explanation stays in the trail."""
    current = (current or "").strip()
    project_recommendation = _needs_outcome_projection(current)
    if current and len(current.split()) <= MAX_OUTCOME_WORDS and not project_recommendation:
        if re.match(r"^(?:referred back|returned to)\s+(?:the\s+)?presbytery\b", current, re.I):
            return "Referred back to Presbytery"
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

    def compact_curated(text):
        """Shorten long curator summaries only when their lead clause is decisive."""
        text = re.sub(r"\s+", " ", (text or "")).strip()
        lower = text.lower()
        if re.search(r"(?:does not|do not|did not|cannot|could not) establish.{0,60}(?:final|exact)|(?:does not|do not) explicitly identify this as the answer|final (?:action|disposition) (?:is )?(?:unclear|unresolved)|exact (?:action|disposition) unclear", lower):
            return "Final disposition unclear"
        if re.search(r"no (?:printed )?assembly adoption marker|final ga\d+ action unresolved", lower):
            return "Final disposition unclear"
        if re.search(r"\bno (?:separate )?(?:assembly )?(?:answer|action|disposition) (?:was )?located\b", lower):
            return "No final action located"
        ref = re.search(r"answered by reference(?:\s+to\s+(?:(GA\s*\d+\s+)?Overture\s+(\d+)|(?:\w[\w -]*\s+)?Recommendation\s+(\d+)))?", text, re.I)
        if ref:
            if ref.group(2):
                ga = f"{ref.group(1).strip()} " if ref.group(1) else ""
                return f"Answered by reference to {ga}Overture {ref.group(2)}"
            if ref.group(3):
                return f"Answered by reference to Recommendation {ref.group(3)}"
            return "Answered by reference"
        if re.search(r"\b(two-thirds|required) presbytery approval\b", text, re.I) and re.search(r"\benacted\b", text, re.I):
            return "Approved and enacted"
        if re.search(r"\bsent (?:it )?for advice and consent\b", text, re.I) and re.search(r"\bpresbytery approval\b", text, re.I) and re.search(r"\b(?:adopted|enacted)\b", text, re.I):
            return "Approved and ratified"
        if re.match(r"^answered\s+(?:in\s+the\s+)?negative(?:ly)?\b", text, re.I) or re.search(r"\banswered\s+(?:in\s+the\s+)?negative\b", text, re.I):
            return "Answered in the negative"
        if re.match(r"^answered\s+(?:in\s+the\s+)?affirmative(?:ly)?\b", text, re.I):
            return "Answered in the affirmative as amended" if re.search(r"\b(?:as amended|with an amendment)\b", text[:160], re.I) else "Answered in the affirmative"
        if re.match(r"^approved\s+(?:but\s+not\s+ratified|and\s+ratified|&\s*ratified)\b", text, re.I):
            return "Approved but not ratified" if re.search(r"\bnot ratified\b", text[:100], re.I) else "Approved and ratified"
        if re.match(r"^(?:referred|returned)\s+back\s+to\s+(?:the\s+)?presbytery\b", text, re.I):
            return "Referred back to Presbytery"
        if re.match(r"^study referral\b", text, re.I):
            return "Referred for study"
        if re.match(r"^carried\b.{0,100}\bre-referred\b|^(?:study referral|referred\b.{0,100}\bstudy\b)", text, re.I):
            return "Referred for study"
        if re.match(r"^referred to the administrative committee\b", text, re.I):
            return "Referred to Administrative Committee"
        target = re.match(r"^referred\s+to\s+(?:the\s+)?([A-Za-z][A-Za-z -]{1,45}?)(?:\s+for\b|[;,\.])", text, re.I)
        if target:
            return f"Referred to {target.group(1).strip()}"
        if re.match(r"^answered by (?:the )?(?:ga\d+ )?substitute\b", text, re.I):
            return "Answered by substitute"
        if re.match(r"^answered by mna report\b", text, re.I):
            return "Answered by report"
        if re.match(r"^continued for (?:a )?five-year periods?\b", text, re.I):
            return "Continued for five-year periods"
        if re.match(r"^minutes corrected\b", text, re.I):
            return "No further action located"
        if re.match(r"^report recommendation not adopted\b", text, re.I) and re.search(r"answered negatively", text, re.I):
            return "Answered in the negative"
        if re.match(r"^the assembly adopted (?:the )?recommendation as amended\b", text, re.I):
            return "Adopted as amended"
        if re.match(r"^adopted (?:the )?(?:amended )?(?:recommendation|answer)\b", text, re.I):
            if re.search(r"\bby reference\b", text[:200], re.I):
                return compact(text)
            return "Adopted as amended" if re.search(r"\bas amended\b", text[:200], re.I) else "Adopted"
        return ""

    if project_recommendation:
        inferred = _recommendation_outcome(bundle)
        if current.lower().rstrip(".") == "answered by reference" and not inferred.startswith("Answered by reference to "):
            return current
        if current.lower().rstrip(".") == "referred" and not inferred.startswith("Referred"):
            return current
        if inferred:
            return inferred
        return current

    if current and len(current.split()) > MAX_OUTCOME_WORDS:
        shortened = compact_curated(current)
        return shortened or current

    # Long curator-written outcomes often preserve qualifications that a short
    # keyword compaction would erase. Reclassify only labels explicitly marked
    # as generic above; keep descriptive outcomes as written.
    if current:
        return current

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
    taxonomy_added = 0; taxonomy_updated = 0
    out = []
    for line in open(CAT).read().split("\n"):
        s = SEC.search(line)
        if line.startswith("## ") and s:
            vol = s.group(1)
        if line.startswith("| Overture | Subject | Outcome | Source | Pages |") and "| Type | Instrument | Topics | BCO amendment stage |" not in line:
            line = line[:-1] + "| Type | Instrument | Topics | BCO amendment stage |"
        elif line.startswith("|---:") and line.count("|") == 6:
            line = line[:-1] + "|---|---|---|---|"
        m = re.match(r"^\|\s*(?:\[(\d+)\]\([^)]+\)|(\d+))\s*\|", line)
        if m and vol:
            num = m.group(1) or m.group(2)
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            page_refs = re.findall(r"\[p\.(\d+)\]\([^)]*#ga\d+-p(\d+)\)", cells[4]) if len(cells) >= 5 else []
            source_page = int(page_refs[0][1]) if page_refs else None
            record_id = f"overture:{vol}:{num}:p{source_page}" if source_page else None
            page = pmap.get(record_id) if record_id else None
            if record_id and len(cells) >= 5:
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
                if len(cells) == 5:
                    facets = classify(cells[1], cells[2])
                    cells.extend([facets["type"], facets["instrument"], facets["topic"], facets["bco_stage"]])
                    line = "| " + " | ".join(cells) + " |"
                    taxonomy_added += 1
                elif len(cells) >= 9:
                    facets = classify(cells[1], cells[2])
                    cells[5:9] = [facets["type"], facets["instrument"], facets["topic"], facets["bco_stage"]]
                    line = "| " + " | ".join(cells) + " |"
                    taxonomy_updated += 1
            if page:
                replacement = f"[{num}](../{page})"
                first_cell = m.group(0)
                line = line.replace(first_cell, f"| {replacement} |", 1)
                linked += 1
        out.append(line)
    open(CAT, "w").write("\n".join(out))
    print(f"[{ROOT}] linked {linked} overture-catalogue rows; added taxonomy to {taxonomy_added}, refreshed {taxonomy_updated}; filled {filled} blanks and shortened {compacted - filled} long outcomes from action trails")

if __name__ == "__main__":
    main()
