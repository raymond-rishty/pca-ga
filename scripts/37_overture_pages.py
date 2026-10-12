#!/usr/bin/env python3
"""37_overture_pages.py — render an individual page per overture, like cases/ + inquiries/.

Reads (from <ROOT>/index/):
  - overture_bodies.jsonl        : {vol, ga_ordinal, number, pdf_page, source, body}
  - overture_titles.jsonl        : {vol, number, pdf_page, title}
  - overture_dispositions.jsonl  : {vol, number, ..., disposition, final_disposition, ratified, bco, ratification_note}
  - overture_events.jsonl        : optional curated action histories keyed by stable record_id

Writes, mirroring cases/* and inquiries/*:
  - <ROOT>/overtures/<vol>__o<number>[__p<source-page>].md
  - <ROOT>/index/overture_pages_map.json   : record_id -> page, plus unambiguous GA/number aliases

An overture can be extracted at several pages (as filed + as reported). The reconciled catalogue
provides the record identity and originating page, so repeated numbers in one volume remain distinct.

Usage:  37_overture_pages.py [ROOT]      (ROOT defaults to /workspace)
"""
from __future__ import annotations
import json, os, re, sys, glob
from collections import Counter, defaultdict
from html import escape
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_links import source_entries_for_record, source_front_matter
from overture_identity import load_reconciled_overture_records

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
OUT = os.path.join(ROOT, "overtures")
MIN_BODY = 40   # shorter extractions are shown as unavailable and retain the minutes link


_OPENER = (r"\*{0,2}(?:Whereas|"
           r"(?:Now,?\s+therefore,?\s+)?(?:Therefore,?\s+)?[Bb]e\s+it\s+(?:further\s+)?resolved|"
           r"Now,?\s+therefore|Resolved,|RESOLVED)\b")


def para_clauses(text: str) -> str:
    """Put each Whereas / resolution clause of an overture on its own paragraph (the bodies arrive as
    one run-on block). Breaks before each clause opener; clause connectors ("; and") stay at the end
    of the preceding clause, the way recital/resolution text reads."""
    text = re.sub(r"\s+(" + _OPENER + ")", r"\n\n\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def escape_minutes_quote(text: str) -> str:
    """Escape quoted source text while rendering recognized redline deletions."""
    return escape(text).replace("&lt;del&gt;", "<del>").replace("&lt;/del&gt;", "</del>")


class _MinutesTableRenderer(HTMLParser):
    """Render a curated minutes table as table markup, allowing only table structure."""
    ALLOWED = {"table", "thead", "tbody", "tfoot", "tr", "th", "td"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.valid = True
        self.table_count = 0

    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED or attrs:
            self.valid = False
            return
        if tag == "table":
            self.table_count += 1
            self.parts.append('<table class="overture-action-table">')
        else:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag not in self.ALLOWED:
            self.valid = False
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(escape(data))

    def handle_entityref(self, name):
        self.parts.append(f"&amp;{escape(name)};")


def render_minutes_table(text: str) -> str | None:
    """Safely preserve source table structure without emitting arbitrary HTML."""
    parser = _MinutesTableRenderer()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return None
    if not parser.valid or parser.table_count != 1:
        return None
    return "".join(parser.parts)


def ordinal(n: int) -> str:
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def load_jsonl(name):
    p = os.path.join(IDX, name)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def catalogue_records():
    """Read the reconciled catalogue; its originating page distinguishes reused numbers."""
    return load_reconciled_overture_records(Path(IDX))


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "*.md")):
        os.remove(f)

    records = catalogue_records()
    record_ids = [record["record_id"] for record in records]
    if len(record_ids) != len(set(record_ids)):
        duplicates = sorted(rid for rid in set(record_ids) if record_ids.count(rid) > 1)
        raise ValueError(f"duplicate overture record IDs in catalogue: {duplicates[:12]}")
    pair_counts = Counter((r["vol"], str(r["number"])) for r in records)
    events = {}
    event_bundles = {}
    related_records = {}
    catalogue_ids = set(record_ids)
    for row in load_jsonl("overture_events.jsonl"):
        # Migrate the unique-key prototype in memory. Ambiguous legacy rows are an error.
        rid = row.get("record_id")
        if not rid:
            matches = [r for r in records if r["vol"] == row.get("vol") and
                       str(r["number"]) == str(row.get("number"))]
            if len(matches) != 1:
                raise ValueError(f"legacy event identity {(row.get('vol'), row.get('number'))} "
                                 f"maps to {len(matches)} catalogue records")
            rid = matches[0]["record_id"]
        if rid not in catalogue_ids:
            raise ValueError(f"overture events refer to unknown catalogue record: {rid}")
        if rid in events:
            raise ValueError(f"duplicate overture event record: {rid}")
        for event in row.get("events", []):
            event_record_id = event.get("record_id")
            if event_record_id and event_record_id != rid:
                raise ValueError(f"event {event.get('event_id')} belongs to {event_record_id}, "
                                 f"not parent record {rid}")
        events[rid] = row.get("events", [])
        event_bundles[rid] = row
        related_records[rid] = row.get("related_records", [])

    def page_path(record):
        slug = f"{record['vol']}__o{record['number']}"
        if pair_counts[(record["vol"], str(record["number"]))] > 1:
            slug += f"__p{record['source_page']}"
        return f"overtures/{slug}.md"

    planned_pages = {record["record_id"]: page_path(record) for record in records}
    page_paths = list(planned_pages.values())
    if len(page_paths) != len(set(page_paths)):
        duplicates = sorted(path for path in set(page_paths) if page_paths.count(path) > 1)
        raise ValueError(f"multiple overture records resolve to the same page: {duplicates[:12]}")

    # If multiple extractions start on a record's source page, prefer overture language over an
    # index/contents occurrence. Exact-page matching keeps reused numbers attached to the right text.
    _OVERTUREY = re.compile(r"\b(whereas|be it (further )?resolved|therefore|resolved,?\s+that|now,?\s+therefore)\b", re.I)
    def _score(r):
        b = r.get("body") or ""
        return (1 if _OVERTUREY.search(b) else 0, len(b))
    candidates: dict[tuple, list[dict]] = defaultdict(list)
    for r in load_jsonl("overture_bodies.jsonl"):
        key = (r["vol"], str(r["number"]), int(r.get("pdf_page") or -1))
        candidates[key].append(r)

    pages_map = {}
    n = 0
    for record in records:
        vol, number = record["vol"], str(record["number"])
        source_page = record["source_page"]
        source_volume = record.get("source_page_vol") or vol
        exact = candidates.get((source_volume, number, source_page), [])
        if exact:
            r = max(exact, key=_score)
        else:
            # A reused number must never borrow another record's body. For unique
            # numbers, a secondary extracted occurrence may still hold the full text.
            if pair_counts[(vol, number)] > 1:
                body = ""
                r = {"body": body, "ga_ordinal": record["ga_ordinal"], "pdf_page": source_page}
            else:
                options = [candidate for (v, num, _), rows in candidates.items()
                           if v == source_volume and num == number for candidate in rows]
                r = max(options, key=_score) if options else {
                    "body": "", "ga_ordinal": record["ga_ordinal"], "pdf_page": source_page
                }
        body = (r.get("body") or "").strip()
        body_available = len(body) >= MIN_BODY
        ga, year = record["ga_ordinal"], str(record["year"])
        prefix = source_volume.split("_")[0]             # source minutes volume prefix
        page = source_page
        title = (record.get("title") or "").strip() or "(untitled overture)"
        source = (record.get("source") or "").strip()
        record_events = events.get(record["record_id"], [])

        hdr = [f"**Assembly:** {ordinal(ga)} ({year})" if year else f"**Assembly:** {ordinal(ga)}"]
        if source:
            hdr.append(f"**Source:** {source}")
        disp = (record.get("disposition") or "").strip()
        # Action-trail pages show the sourced decisions below; don't repeat a catalogue
        # summary in the page header as if it were part of the minutes.
        if disp and not record_events:
            hdr.append(f"**Disposition:** {disp}")

        anchor = f"#{prefix}-p{page}" if page else ""
        src = (f"*Source: [{source_volume} p. {page}](../markdown/{source_volume}.md{anchor})*" if page
               else f"*Source: [{source_volume}](../markdown/{source_volume}.md)*")
        rn = ""
        ratnote = [f"> *{rn.strip()}*", ""] if (rn or "").strip() else []

        source_meta = source_front_matter(source_entries_for_record(
            Path(ROOT), "overture", f"{source_volume}:{number}:{source_page}", source_volume,
            int(page) if page else None
        ))
        # The helper's trailing blank line is useful at other insertion points, but
        # overture pages already add a blank after the heading metadata below.
        if source_meta and source_meta[-1] == "":
            source_meta = source_meta[:-1]
        page_md = source_meta + [f"# GA{ga} O{number} — {title}", "", "  ·  ".join(hdr), "", src, "", "---", ""]
        if record_events:
            page_md += ratnote
            event_bundle = event_bundles.get(record["record_id"], {})
            proposal_body_available = body_available and not event_bundle.get("proposal_text_unavailable")
            proposal_text_heading = (event_bundle.get("proposal_text_heading") or
                                     "Submitted overture").strip()
            proposal_text_note = (event_bundle.get("proposal_text_note") or "").strip()
            page_md += [f"## {proposal_text_heading}", ""]
            if proposal_text_note:
                page_md += [f"*{proposal_text_note}*", ""]
            if proposal_body_available:
                page_md += [para_clauses(body)]
            elif not proposal_text_note:
                page_md += ["*The submitted text is not available in the extracted catalogue; "
                            "consult the cited minutes.*"]
            page_md += ["", "## Action history", ""]
            for event in record_events:
                heading = (event.get("heading") or "Overture action").strip()
                action_text = (event.get("action_text") or "").strip()
                source_volume = (event.get("source_volume") or vol).strip()
                source_page = event.get("source_pdf_page")
                source_label = event.get("source_label") or (
                    f"{source_volume} PDF p. {source_page}" if source_page else source_volume
                )
                source_url = (event.get("source_url") or "").strip()
                source_match = re.search(r"ga(\d+)", source_volume)
                source_anchor = (f"#ga{int(source_match.group(1))}-p{source_page}"
                                 if source_page and source_match else "")
                page_md += [f'<h3 class="overture-action-heading">{escape(heading)}</h3>', ""]
                if action_text:
                    quoted = "<br>\n".join(escape_minutes_quote(line) for line in action_text.splitlines())
                    text_kind = event.get("text_kind")
                    if text_kind is None:
                        # Compatibility for older rows: is_excerpt used to double
                        # as a quote/note switch. New rows should set text_kind.
                        text_kind = "minutes_quote" if event.get("is_excerpt", True) else "editorial_note"
                    if text_kind == "minutes_quote":
                        # Keep transcribed minutes text visibly distinct from research notes.
                        page_md += ['<blockquote class="overture-action-text">', quoted,
                                    "</blockquote>", ""]
                    elif text_kind == "minutes_table":
                        # Preserve the source table's rows and columns when the research record
                        # supplies structured cells; retain a quoted fallback for older rows.
                        table = event.get("table") or {}
                        headers = table.get("headers", [])
                        rows = table.get("rows", [])
                        if headers and rows:
                            page_md += ['<table class="overture-action-table">', "<thead>", "<tr>"]
                            page_md.extend(f"<th>{escape(str(cell))}</th>" for cell in headers)
                            page_md += ["</tr>", "</thead>", "<tbody>"]
                            for row in rows:
                                page_md.append("<tr>")
                                page_md.extend(f"<td>{escape(str(cell))}</td>" for cell in row)
                                page_md.append("</tr>")
                            page_md += ["</tbody>", "</table>", ""]
                        else:
                            page_md += ['<blockquote class="overture-action-text">', quoted,
                                        "</blockquote>", ""]
                    elif text_kind == "editorial_note":
                        page_md += ["*Source note; not a minutes quotation.*", "",
                                    f'<p class="overture-action-note">{quoted}</p>', ""]
                    elif text_kind == "minutes_paraphrase":
                        page_md += ["*Paraphrase of the minutes; not a quotation.*", "",
                                    f'<p class="overture-action-note">{quoted}</p>', ""]
                    elif text_kind == "minutes_note":
                        page_md += ["*Minutes status note; not a separate Assembly action.*", "",
                                    f'<p class="overture-action-note">{quoted}</p>', ""]
                    else:
                        raise ValueError(f"unsupported overture event text_kind: {text_kind!r}")
                source_href = source_url or f"../markdown/{source_volume}.md{source_anchor}"
                page_md += [f"*Source: [{escape(source_label)}]({source_href})*", ""]
                for support in event.get("supporting_excerpts", []):
                    support_text = (support.get("action_text") or "").strip()
                    support_volume = (support.get("source_volume") or vol).strip()
                    support_page = support.get("source_pdf_page")
                    support_label = (support.get("source_label") or
                                     f"{support_volume} PDF p. {support_page}").strip()
                    support_match = re.search(r"ga(\d+)", support_volume)
                    support_anchor = (f"#ga{int(support_match.group(1))}-p{support_page}"
                                      if support_page and support_match else "")
                    if support_text:
                        table_html = (render_minutes_table(support_text)
                                      if support.get("text_kind") == "minutes_table" else None)
                        page_md += [f"*{escape(support.get('label') or 'Supporting excerpt')}:*", ""]
                        if table_html:
                            page_md += ['<div class="overture-action-table-wrap">', table_html,
                                        "</div>", ""]
                        else:
                            quoted_support = "<br>\n".join(escape_minutes_quote(line) for line in support_text.splitlines())
                            page_md += ['<blockquote class="overture-action-text">', quoted_support,
                                        "</blockquote>", ""]
                    page_md += [f"*Source: [{escape(support_label)}]"
                                f"(../markdown/{support_volume}.md{support_anchor})*", ""]
                related_page = (event.get("related_page") or "").strip()
                if related_page:
                    related_label = (event.get("related_label") or "Related overture").strip()
                    page_md += [f"*Related record: [{related_label}]({related_page})*", ""]
        else:
            page_md += ratnote
            page_md += ([para_clauses(body)] if body_available else
                        ["*The submitted text is not available in the extracted catalogue; "
                         "consult the cited minutes.*"])
        related = related_records.get(record["record_id"], [])
        if related:
            page_md += ["", "## Related records", ""]
            for relation in related:
                if isinstance(relation, str):
                    related_id = relation
                    label = relation
                    description = ""
                else:
                    related_id = relation.get("related_record_id")
                    label = (relation.get("label") or related_id or "Related overture").strip()
                    description = (relation.get("relationship") or "").strip()
                related_path = planned_pages.get(related_id)
                if not related_path:
                    continue
                suffix = f" — {escape(description)}" if description else ""
                page_md += [f"- [{escape(label)}](../{related_path}){suffix}"]
            page_md.append("")
        page_md += ["---", "", "[← Overture catalogue](../index/OVERTURES.md)"]
        slug = Path(page_path(record)).stem
        open(os.path.join(OUT, f"{slug}.md"), "w", encoding="utf-8").write("\n".join(page_md) + "\n")
        pages_map[record["record_id"]] = f"overtures/{slug}.md"
        if pair_counts[(vol, number)] == 1:
            pages_map[f"GA{ga} O{number}"] = f"overtures/{slug}.md"
        n += 1

    json.dump(pages_map, open(os.path.join(IDX, "overture_pages_map.json"), "w"), indent=1)
    print(f"[{ROOT}] wrote {n} overture pages "
          f"-> overtures/ + index/overture_pages_map.json")


if __name__ == "__main__":
    main()
