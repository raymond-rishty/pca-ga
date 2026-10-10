#!/usr/bin/env python3
"""
21_overture_titles.py — give each overture a short subject title (e.g. "Establish a theological
library at Ridge Haven"), so the catalogue answers "has the PCA considered X before?" by subject,
not just by number/presbytery.

  extract : pull each overture's body text from the rendered markdown (header -> next heading),
            keyed by (vol, number, pdf_page) to join the structure index / DB overtures.
            -> index/overture_bodies.jsonl   {vol, ga_ordinal, number, pdf_page, source, body}
               (with source Markdown paragraph and list structure retained in body)

Titles themselves are generated (by an LLM, from the body) into index/overture_titles.jsonl
  {vol, number, pdf_page, title}
which 19_export folds into the DB `overtures.title` column and 20_markdown_index renders as a
"Subject" column. Generation is decoupled from extraction so it can be batched/re-run cheaply.

CLI:  21_overture_titles.py extract [ROOT]   (ROOT defaults to /workspace)
"""
from __future__ import annotations
import glob, json, os, re, sys
from html import unescape

ROOT = sys.argv[2] if len(sys.argv) > 2 else "/workspace"
MD = os.path.join(ROOT, "markdown")
OUT = os.path.join(ROOT, "index", "overture_bodies.jsonl")

_HEAD = re.compile(r"^#{1,6}\s")
_OV = re.compile(r"^#{1,6}\s*Overture\s+(\d+)\b", re.I)
_PLAIN_REVISED_OVERTURE = re.compile(
    r"^Overture\s+(\d+)\s+\(Revised\)\s+from\s+.+$", re.I
)
_PLAIN_OVERTURE_BOUNDARY = re.compile(r"^OVERTURE\s+(\d+)\s*,?\s+from\s+(.+)$", re.I)
_BRACKETED_OVERTURE = re.compile(
    r"^\[OVERTURE\s+(\d+)\s*,?\s+from\s+(.+[“\"].+)$", re.I
)
_APPENDIX_SOURCE = re.compile(r"^#{1,6}\s*APPENDIX\s+([A-Z0-9]+)\b", re.I)
_PAGE = re.compile(r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\w+)")
_NOISE = re.compile(r"^\s*(<a id=|<!--\s*PAGE|#*\s*\d*\s*MINUTES OF THE GENERAL ASSE|JOURNAL OF THE)")
# Committee-report numbered disposal: "4. That Overture 4 ... be answered in..." or
# "4. That the MNA Committee recommend ... Overture 4 ... be answered in...". This fires only
# when the mentioned overture number differs from the one being collected, because such lines
# belong to the NEXT item's committee recommendation, not this overture.
_CMTE_DISP = re.compile(
    r"(?:^|\s)(\d+)\.\s+That\b.*?\b[Oo]verture\s+(\d+)\b"
    r"(?=.*?\bbe\s+answered\s+(?:in\s+the\s+)?(?:affirmative|negative))",
    re.I,
)


def preserve_markdown(lines: list[str]) -> str:
    """Retain the source minutes' structural Markdown in an extracted body.

    Single newlines are ordinary source wrapping, which Markdown renders as
    spaces. Blank lines carry paragraph and list boundaries, so flattening all
    whitespace destroys meaningful formatting in the standalone overture page.
    """
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract():
    # agent-located true end lines for the over-long bodies (see overture-end-finder workflow):
    # {"<vol>__o<number>@<start_line>": <1-based end line>} — keyed by the occurrence's start line
    # because an overture number can recur in a volume (as filed + in a committee report).
    ends_path = os.path.join(ROOT, "index", "overture_body_ends.json")
    ENDS = json.load(open(ends_path)) if os.path.exists(ends_path) else {}
    recs = []
    for p in sorted(glob.glob(os.path.join(MD, "ga*_*.md"))):
        vol = os.path.basename(p).split(".")[0]
        ordn = int(re.match(r"ga(\d+)", vol).group(1))
        lines = open(p, encoding="utf-8").read().split("\n")
        cur_page = None
        source_appendix = None
        cur = None            # active overture being accumulated
        for i, ln in enumerate(lines, 1):
            appendix_match = _APPENDIX_SOURCE.match(ln)
            if appendix_match:
                appendix = appendix_match.group(1).upper()
                source_appendix = appendix if appendix in {"U", "V", "W"} else None
            elif re.match(r"^#{1,6}\s*INDEX\b", ln, re.I):
                source_appendix = None
            mp = _PAGE.search(ln)
            if mp:
                cur_page = None if mp.group(1) in ("null", "None") else int(mp.group(1))
            # Some recent minutes put overture headings in a single HTML table
            # row instead of a Markdown heading. Normalize that source header so
            # it starts and ends a body just like the ordinary heading form.
            table_header = None
            if "<table" in ln.lower() and "overture" in ln.lower():
                cells = re.findall(r"<td[^>]*>(.*?)</td>", ln, flags=re.I)
                if cells:
                    first_cell = unescape(re.sub(r"<[^>]+>", " ", cells[0])).strip()
                    header_match = re.match(r"(?i)^overture\s+(\d+)\s+from\s+(.+?)\s*$", first_cell)
                    if header_match:
                        number = int(header_match.group(1))
                        source = re.sub(r"\s+", " ", header_match.group(2)).strip()
                        committee = ""
                        if len(cells) > 1:
                            committee = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", cells[1]))).strip()
                        table_header = (number, f"{source} {committee}".strip())
                        ln = f"## Overture {number} from {source} {committee}".strip()
            plain_revised = _PLAIN_REVISED_OVERTURE.match(ln)
            bracketed_overture = _BRACKETED_OVERTURE.match(ln)
            plain_source = (_PLAIN_OVERTURE_BOUNDARY.match(ln)
                            if source_appendix in {"U", "V", "W"} else None)
            plain_boundary = _PLAIN_OVERTURE_BOUNDARY.match(ln)
            mo = _OV.match(ln) or plain_revised or plain_source or bracketed_overture
            if cur is not None and not mo and plain_boundary:
                recs.append(cur)
                cur = None
                continue
            if mo:                                   # start a new overture body
                if cur:
                    recs.append(cur)
                if table_header:
                    num, src = table_header
                elif plain_revised:
                    num = int(mo.group(1))
                    src = re.sub(
                        r"(?i)^Overture\s+\d+\s+\(Revised\)\s+from\s+", "", ln
                    ).strip(" *_#")
                elif plain_source:
                    num = int(plain_source.group(1))
                    source_text = re.sub(r"\s+", " ", plain_source.group(2)).strip()
                    # Some Appendix V/W source headings run directly into the
                    # first Whereas/Therefore clause on the same Markdown line.
                    # Keep only the source/title as metadata and retain that
                    # clause as submitted text instead of dropping it with the header.
                    inline = re.match(
                        r"(?is)^(.*[\"”])\s+((?:Whereas|Therefore|Be it resolved)\b.*)$",
                        source_text,
                    )
                    if inline:
                        src = inline.group(1).strip()
                        inline_body = inline.group(2).strip()
                    else:
                        src = source_text
                        inline_body = ""
                elif bracketed_overture:
                    num = int(bracketed_overture.group(1))
                    src = re.sub(r"\s+", " ", bracketed_overture.group(2)).strip().rstrip("\"]")
                    inline_body = ""
                else:
                    src = re.sub(r"^#{1,6}\s*Overture\s+\d+\b[.:,\s]*", "", ln).strip(" *_#")
                    src = re.sub(r"(?i)^from\s+", "", src)
                    num = int(mo.group(1))
                cur = {"vol": vol, "ga_ordinal": ordn, "number": num,
                       "pdf_page": cur_page, "source": src, "_lines": [],
                       "_end": ENDS.get(f"{vol}__o{num}@{i}"),
                       "_table_header": bool(table_header or plain_revised),
                       "_bracketed_source": bool(bracketed_overture)}
                if plain_source and inline_body:
                    cur["_lines"].append(inline_body)
                continue
            if cur is not None:
                if _HEAD.match(ln) and re.match(r"(?i)^#{1,6}\s*APPENDIX\s+[A-Z0-9]+\b", ln):
                    # Appendix headings repeat at printed-page breaks inside a long submission.
                    continue
                if _HEAD.match(ln):                  # next heading ends the body
                    recs.append(cur); cur = None
                elif not _NOISE.match(ln):
                    if cur["_end"] and i > cur["_end"]:   # past the agent-located true end
                        continue
                    # Hard-stop: numbered committee-report disposal of a DIFFERENT overture.
                    # "4. That Overture 4, from Westminster Presbytery be answered in the negative."
                    # belongs to the next item; we never want it in the current overture's body.
                    # Disposals may follow the proposal text on the same source line.
                    # If the numbered recommendation is for another overture, retain
                    # only this line's prefix as part of the current body's text.
                    # Disposals that mention THIS overture (minority reports etc.) stay.
                    m_disp = next(
                        (match for match in _CMTE_DISP.finditer(ln)
                         if int(match.group(2)) != cur["number"]),
                        None,
                    )
                    if m_disp:
                        prefix = ln[:m_disp.start()].rstrip()
                        if prefix:
                            cur["_lines"].append(prefix)
                        recs.append(cur); cur = None
                        continue
                    cur["_lines"].append(ln)
                    if cur.get("_bracketed_source") and ln.rstrip().endswith("]"):
                        recs.append(cur)
                        cur = None
        if cur:
            recs.append(cur)
    table_keys = {
        (r.get("vol"), int(r.get("number") or 0), r.get("pdf_page"))
        for r in recs if r.get("_table_header")
    }
    generated = []
    for r in recs:
        had_end = r.pop("_end", None)
        r.pop("_table_header", None)
        r.pop("_bracketed_source", None)
        body = preserve_markdown(r.pop("_lines"))
        # A located true end is trusted (just a generous safety ceiling); otherwise bound runaway
        # over-extraction at 6000. Either way cut on a word boundary with an ellipsis, never
        # mid-word — and the full text is always one click away at the page's deep-link.
        cap = 12000 if had_end else 6000
        if len(body) > cap:
            body = body[:cap].rsplit(" ", 1)[0].rstrip(" ,;") + " …"
        r["body"] = body
        generated.append(r)

    # The body file contains curated material that may not be reconstructible from
    # current Markdown headings. Preserve it; refresh only matching table-wrapped
    # source entries and append genuinely missing extracted records.
    existing = []
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            existing = [json.loads(line) for line in f if line.strip()]
    positions = {
        (r.get("vol"), int(r.get("number") or 0), r.get("pdf_page")): i
        for i, r in enumerate(existing)
    }
    added = 0
    refreshed = 0
    for r in generated:
        key = (r.get("vol"), int(r.get("number") or 0), r.get("pdf_page"))
        if key in positions:
            old = existing[positions[key]]
            old_source = str(old.get("source") or "").strip()
            source_contains_body = (
                bool(re.match(r"(?i)^OVERTURE\s+\d+\s+from\s+", old_source))
                or len(old_source) > 180
            )
            if key in table_keys or source_contains_body:
                existing[positions[key]] = r
                refreshed += 1
        else:
            positions[key] = len(existing)
            existing.append(r)
            added += 1
    with open(OUT, "w", encoding="utf-8") as f:
        for r in existing:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"merged {added} new and refreshed {refreshed} table-wrapped overture bodies ({len(existing)} total) -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        extract()
    else:
        print(__doc__)
