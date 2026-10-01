#!/usr/bin/env python3
"""30_inquiry_pages.py — render the Constitutional Inquiry layer to markdown.

Reads canonical inquiry records from <ROOT>/index/inquiries.jsonl. Each JSONL
row combines the Digest/headnote metadata with a stable ID and its source locator.

Slices the verbatim record from <ROOT>/markdown/ and writes, mirroring CASES.md / cases/*:
  - <ROOT>/inquiries/<stem>__ci<NN>.md  : one page per inquiry (structured editorial header + minutes transcript)
  - <ROOT>/index/INQUIRIES.md           : the catalogue, grouped by Assembly

Usage:  30_inquiry_pages.py [ROOT]      (ROOT defaults to /workspace)

Per SPEC-INQUIRIES.md: the Digest headnote is editorial, attributed, and rendered in the record
header. The page body contains only source-located minutes text and source-derived section headings.
"""
from __future__ import annotations
import json, os, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_links import (pdf_page_for_anchor, printed_page_for_anchor,
                          normalize_text, source_entries_for_record, source_front_matter)
from minutes_page_locators import (canonical_page_anchor, count_printed_pages,
                                   page_records, resolve_legacy_page)
from inquiry_records import load_inquiry_records

ONLY_RELOCATED = "--only-relocated" in sys.argv[1:]
SEARCH_FROM_CATALOGUES = "--search-index-from-catalogues" in sys.argv[1:]
PAGES_ONLY = "--pages-only" in sys.argv[1:]
ROOT_ARG = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
ROOT = ROOT_ARG if ROOT_ARG else os.environ.get(
    "PCA_GA_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")
OUT = os.path.join(ROOT, "inquiries")

_LOCATOR = re.compile(r"^\s*\d{4},\s*p\.\s*\d+[a-zA-Z]?,\s*\d+-\d+,?\s*[\w.]*\.?\s*")
_md_text_cache: dict[str, str] = {}


def refresh_search_index_from_catalogues() -> None:
    """Rebuild search records without deriving page IDs from OCR/source order."""
    rows = []
    seen_urls = set()
    for filename, record_type in (("INQUIRIES.md", "inquiry"),
                                  ("CCB-OVERTURE-ADVICE.md", "ccb-advice")):
        year = None
        pending = None

        def consume(line: str) -> None:
            nonlocal year
            if not line:
                return
            heading = re.match(r"^## .*?\((\d{4})\)", line)
            if heading:
                year = int(heading.group(1))
                return
            if not line.startswith("|") or year is None:
                return
            cells, cell, escaped = [], [], False
            body = line.strip().strip("|")
            for char in body:
                if char == "|" and not escaped:
                    cells.append("".join(cell).strip())
                    cell = []
                else:
                    cell.append(char)
                if char == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
            cells.append("".join(cell).strip())
            if len(cells) != 7 or cells[0] in ("Inquiry", "---"):
                return
            subject = re.match(r"^\[(.*)\]\(\.\./inquiries/([^)]*)\)$", cells[1])
            if not subject:
                return
            title = subject.group(1).replace("\\|", "|")
            url = "inquiries/" + subject.group(2)
            if url in seen_urls:
                raise ValueError(f"Duplicate inquiry catalogue URL: {url}")
            if not (Path(ROOT) / url).is_file():
                raise ValueError(f"Inquiry catalogue points to missing page: {url}")
            seen_urls.add(url)
            rows.append({
                "type": record_type,
                "title": title,
                "sub": cells[2].replace("\\|", "|"),
                "provisions": [p.strip().replace("\\|", "|") for p in cells[3].split(",") if p.strip()],
                "year": year,
                "disposition": cells[4].replace("\\|", "|"),
                "url": url,
            })

        for raw in (Path(IDX) / filename).read_text(encoding="utf-8").splitlines():
            if raw.startswith("|"):
                if pending is not None:
                    consume(pending)
                pending = raw.strip()
            elif pending is not None and raw.strip() and not raw.lstrip().startswith("#"):
                pending += " " + raw.strip()
            else:
                if pending is not None:
                    consume(pending)
                    pending = None
                consume(raw.strip())
        if pending is not None:
            consume(pending)

    if not rows:
        raise ValueError("No inquiry catalogue records found")
    with open(os.path.join(IDX, "inquiries_search.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    print(f"[{ROOT}] refreshed inquiries_search.json ({len(rows)} catalogue records)")


def ordinal(n: int) -> str:
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def md_escape(s) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def yaml_scalar(value) -> str:
    """Encode a scalar using JSON's YAML-compatible quoted-string syntax."""
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def compact_disposition(value: str) -> str:
    """Keep a long outcome field from repeating the adjacent editorial summary."""
    text = (value or "").strip()
    if len(text) <= 110:
        return text
    tail = text.rsplit(";", 1)[-1].strip()
    if tail and len(tail) <= 48:
        return tail
    return text[:107].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def inquiry_front_matter(source_meta: list[str], context: dict) -> list[str]:
    """Write structured inquiry context for the server-rendered record header."""
    lines = source_meta[:-2] if source_meta else ["---"]
    lines += [
        "title: " + yaml_scalar(context["title"]),
        "description: " + yaml_scalar(context.get("synopsis") or context["title"]),
        "inquiry_record:",
    ]
    for key in ("title", "subject", "type", "assembly", "synopsis", "disposition",
                "disposition_display",
                "source", "minutes_label", "minutes_href", "source_status"):
        if context.get(key) is not None:
            lines.append(f"  {key}: {yaml_scalar(context[key])}")
    provisions = context.get("provisions", [])
    lines.append("  provisions:" if provisions else "  provisions: []")
    lines.extend("    - " + yaml_scalar(value) for value in provisions)
    summaries = context.get("digest_summaries", [])
    lines.append("  digest_summaries:" if summaries else "  digest_summaries: []")
    lines.extend("    - " + yaml_scalar(value) for value in summaries)
    lines += [
        "  digest_source: " + yaml_scalar("PCA Digest, Part II — Interpretations of the Constitution"),
        "---",
        "",
    ]
    return lines


def token_spans(text: str, marker: str) -> list[tuple[int, int]]:
    """Find a marker by its ordered words, independent of OCR line wrapping."""
    words = [m.group(0).casefold() for m in re.finditer(r"[\w]+", marker, re.UNICODE)]
    if not words:
        return []
    source = [(m.group(0).casefold(), m.start(), m.end())
              for m in re.finditer(r"[\w]+", text, re.UNICODE)]
    hits = []
    limit = len(source) - len(words) + 1
    for i in range(max(0, limit)):
        if [word for word, _, _ in source[i:i + len(words)]] == words:
            hits.append((source[i][1], source[i + len(words) - 1][2]))
    return hits


def md_text(stem: str) -> str:
    """Read a minutes volume without normalizing OCR whitespace or page markers."""
    if stem not in _md_text_cache:
        p = os.path.join(MD, stem + ".md")
        _md_text_cache[stem] = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    return _md_text_cache[stem]


def slice_text_locator(stem: str, locator: dict) -> str:
    """Resolve phrase-bounded source text, including spans crossing PDF pages.

    New locators put a physical-page anchor and unique phrase on each boundary.
    The older flat shape remains readable during migration. Matching uses word
    sequences, so OCR line wrapping and whitespace changes do not matter.
    """
    text = md_text(stem)
    page_anchors = list(re.finditer(r'<a\s+id="(ga\d+-p[^"]+)"\s*></a>', text))
    pages: dict[str, tuple[int, int]] = {}
    for index, anchor_match in enumerate(page_anchors):
        end = page_anchors[index + 1].start() if index + 1 < len(page_anchors) else len(text)
        key = anchor_match.group(1)
        if key in pages:
            pages[key] = (-1, -1)
        else:
            pages[key] = (anchor_match.end(), end)

    start_boundary = locator.get("start")
    end_boundary = locator.get("end")
    if not isinstance(start_boundary, dict) or not isinstance(end_boundary, dict):
        anchor = (locator.get("page_anchor") or "").strip()
        end_after, end_before = locator.get("end_after"), locator.get("end_before")
        if not anchor or bool(end_after) == bool(end_before):
            return ""
        start_boundary = {"page_anchor": anchor, "text": locator.get("start_text", "")}
        end_boundary = {"page_anchor": anchor,
                        "text": end_after or end_before,
                        "inclusive": bool(end_after)}

    start_anchor = (start_boundary.get("page_anchor") or "").strip()
    end_anchor = (end_boundary.get("page_anchor") or "").strip()
    if start_anchor not in pages or end_anchor not in pages:
        return ""
    start_page_start, start_page_end = pages[start_anchor]
    end_page_start, end_page_end = pages[end_anchor]
    if min(start_page_start, start_page_end, end_page_start, end_page_end) < 0:
        return ""
    start_page_text = text[start_page_start:start_page_end]
    end_page_text = text[end_page_start:end_page_end]
    starts = token_spans(start_page_text, start_boundary.get("text", ""))
    ends = token_spans(end_page_text, end_boundary.get("text", ""))
    if len(starts) != 1 or len(ends) != 1:
        return ""
    start = start_page_start + starts[0][0]
    end = end_page_start + ends[0][1]
    if start > end:
        return ""
    if not end_boundary.get("inclusive", True):
        end = end_page_start + ends[0][0]
    else:
        while end < end_page_end and text[end] in ".,;:!?\u2019\u201d'\")":
            end += 1
    if end <= start:
        return ""
    result = text[start:end]
    if not end_boundary.get("inclusive", True):
        # An exclusive boundary can point at the first words of the next
        # lettered report item. Avoid leaving its Markdown bullet prefix in
        # the preceding item's extracted text.
        result = re.sub(r"\s*-\s*\*\*[^*]*\*\*\s*$", "", result)
    return result.strip()


def clean_summary(s: str) -> str:
    return _LOCATOR.sub("", (s or "").strip()).strip()


def is_bare_provision(t: str) -> bool:
    return bool(re.fullmatch(r"(BCO|WCF|RAO)?\s*\d+[-.\d]*\s*", (t or "")))


def kind_of(e: dict) -> str:
    """Two buckets: the CCB's advice on a proposed overture/amendment, vs. a constitutional
    inquiry (a non-judicial reference asking what the Constitution means).

    The disposition is the primary signal: a CCB "in conflict / not in conflict" ruling is review
    of a PROPOSED change, never the answer to a question about meaning — so it overrides the
    source-based `kind` (a stated-clerk reference of a proposed amendment still gets a conflict
    ruling and belongs with overture advice)."""
    AMEND = "Overture/amendment advice"
    INQ = "Constitutional inquiry"
    disp = (e.get("disposition") or "").lower()
    if re.search(r"in conflict|conflict with the constitution|creates?\b[^.]*conflict", disp):
        return AMEND
    if e.get("kind") == "overture-advice":
        return AMEND
    if re.search(r"\boverture\s+\d", (e.get("source") or "").lower()):
        return AMEND
    if e.get("kind"):   # reference / communication / other, with no conflict ruling
        return INQ
    blob = f"{disp} {(e.get('summary','') or '')[:160]}".lower()
    if re.search(r"\bin conflict\b|\boverture\s+\d", blob):
        return AMEND
    return INQ


def deeplink(stem: str, anchor: str, printed=None) -> str:
    """Link to a minutes page using minutes folio/PDF coordinates, never Digest pagination."""
    root = Path(ROOT)
    pdf_page = pdf_page_for_anchor(root, stem, anchor) if anchor else None
    minutes_page = printed_page_for_anchor(root, stem, anchor) if anchor else None
    if minutes_page and pdf_page:
        label = f"{stem} minutes p.{minutes_page} / PDF p.{pdf_page}"
    elif minutes_page:
        label = f"{stem} minutes p.{minutes_page}"
    elif pdf_page:
        label = f"{stem} PDF p.{pdf_page}"
    else:
        label = stem
    frag = f"#{anchor}" if anchor else ""
    return f"[{label}](../markdown/{stem}.md{frag})"


def main():
    if SEARCH_FROM_CATALOGUES:
        refresh_search_index_from_catalogues()
        return

    records = load_inquiry_records(Path(ROOT))

    # Group canonical records into one page per distinct verbatim passage.
    groups: dict = {}
    for record_index, record in enumerate(records):
        r = {**record["locator"], "_record": record}
        # Group only records that share the same stable source locator. Legacy line
        # offsets can drift after re-OCR and must not determine record identity.
        stable_locator = (r.get("advice_locator")
                          or (r.get("substantive") or {}).get("locator")
                          or r.get("posed_locator"))
        if stable_locator:
            locator_key = json.dumps(stable_locator, ensure_ascii=False, sort_keys=True)
        else:
            locator_key = record["id"]
        key = (record["ga_ordinal"], locator_key)
        grp = groups.setdefault(key, {"ord": record["ga_ordinal"], "stem": record["stem"],
                                      "first_record_index": record_index, "results": []})
        grp["results"].append(r)

    os.makedirs(OUT, exist_ok=True)
    if not ONLY_RELOCATED:
        for f in os.listdir(OUT):
            if f.endswith(".md"):
                os.remove(os.path.join(OUT, f))

    per_vol = {}
    inq_rows, adv_rows = {}, {}   # ord -> list of (year, stem, row), split by Type
    search_rows = []              # compact export for the search app
    n_pages = 0

    for key, grp in sorted(groups.items(), key=lambda item: item[1]["first_record_index"]):
        ordn, stem, results = grp["ord"], grp["stem"], grp["results"]
        n = per_vol.get(stem, 0) + 1
        per_vol[stem] = n
        if ONLY_RELOCATED and not any(r.get("relocation") for r in results):
            continue
        rents = [(r, r["_record"]) for r in results]
        r0, e0 = rents[0]

        topics = [e.get("topic") for _, e in rents if e.get("topic")]
        provs = []
        for _, e in rents:
            for p in (e.get("provisions") or []):
                if p and p not in provs:
                    provs.append(p)
        summaries = []
        for _, e in rents:
            s = clean_summary(e.get("summary", ""))
            if s and s not in summaries:
                summaries.append(s)
        source = next((e.get("source") for _, e in rents if e.get("source")), "")
        disp = next((e.get("disposition") for _, e in rents if e.get("disposition")), "")
        gen_subject = next((e.get("gen_subject") for _, e in rents if e.get("gen_subject")), "")
        synopsis = next((e.get("synopsis") for _, e in rents if e.get("synopsis")), "")
        mtype = kind_of(next((e for _, e in rents if e), {}) or r0)
        ci = (r0.get("inquiry_number") or "").strip()
        year = e0.get("year")
        anchor = (r0.get("page_anchor") or "").strip()
        ma = re.match(r"ga(\d+)-p(.+)$", anchor)   # markdown anchors zero-pad the ordinal (ga04, not ga4)
        if ma:
            anchor = f"ga{int(ma.group(1)):02d}-p{ma.group(2)}"
        sect = e0.get("ccb_section", "")

        substantive = r0.get("substantive")
        action = r0.get("assembly_action")
        substantive_locator = (substantive or {}).get("locator")
        primary_locator = (substantive_locator or r0.get("advice_locator")
                           or r0.get("posed_locator"))
        primary_anchor = ((primary_locator or {}).get("start") or {}).get("page_anchor", "")
        primary_anchor = (primary_anchor or "").strip()
        primary_printed = ((substantive or {}).get("printed_page")
                           if substantive_locator else None)
        source_page = None
        if primary_anchor:
            legacy_source_page = resolve_legacy_page(
                Path(ROOT), stem, primary_anchor, primary_printed)
            if legacy_source_page:
                source_page = int(legacy_source_page["pdf_page"])
                counts = count_printed_pages(
                    (str(record["printed_page"] or "null"), str(record["pdf_page"]))
                    for record in page_records(Path(ROOT), stem))
                primary_anchor = canonical_page_anchor(legacy_source_page, counts)
        # display subject
        digest_topic = next((t for t in topics if not is_bare_provision(t)), "")
        digest_subject = digest_topic.split(", ", 1)[1].strip() if ", " in digest_topic else digest_topic
        subj = digest_subject or gen_subject
        if not subj:
            subj = (summaries[0][:80].rsplit(" ", 1)[0] + "…") if summaries else (topics[0] if topics else "Constitutional inquiry")
        label = (ci or (f"{e0.get('minute_para','')} {sect}".strip())
                 or (f"{r0.get('minute_para','')} {r0.get('topic','')}".strip()) or "Inquiry")

        slug = f"{stem}__ci{n:02d}"

        body = (slice_text_locator(stem, r0["advice_locator"])
                if r0.get("advice_locator") else "")
        substantive_body = (slice_text_locator(stem, substantive_locator)
                            if substantive and substantive_locator else "")
        action_body = (slice_text_locator(stem, action["locator"])
                       if action and action.get("locator") else "")
        posed = ""
        if r0.get("posed_locator"):
            posed = slice_text_locator(stem, r0["posed_locator"])
        ratified_only = (r0.get("answer_in_volume") is False)

        # ---- page ----
        hdr = ["**Body:** Committee on Constitutional Business (CCB)", f"**Type:** {mtype}",
               f"**Assembly:** {ordinal(ordn)} ({year})"]
        if provs:
            hdr.append("**Provisions:** " + ", ".join(provs))
        if disp:
            hdr.append("**Disposition:** " + md_escape(disp))
        srcline = (f"*Source: {deeplink(stem, primary_anchor)}*"
                   if primary_anchor else f"*Source volume: {stem} (passage not yet verified)*")
        verbatim_verified = bool(substantive_body or body or posed)

        if r0.get("source_pdf_page") is not None:
            source_page = int(r0["source_pdf_page"])
        elif source_page is None and primary_anchor:
            source_page = pdf_page_for_anchor(Path(ROOT), stem, primary_anchor)
        source_meta = source_front_matter(source_entries_for_record(
            Path(ROOT), "inquiry", e0["id"], stem, source_page
        ))
        is_inq = (mtype == "Constitutional inquiry")
        minutes_href = f"../markdown/{stem}.html" + (f"#{primary_anchor}" if primary_anchor else "")
        minutes_printed = (primary_printed or
                           (printed_page_for_anchor(Path(ROOT), stem, primary_anchor)
                            if primary_anchor else None))
        minutes_label = (f"{stem} minutes p.{minutes_printed}" if minutes_printed
                         else f"{stem} minutes — passage not yet verified")
        context = {
            "title": f"{label} — {subj}",
            "subject": subj,
            "type": mtype,
            "assembly": f"{ordinal(ordn)} ({year})",
            "synopsis": synopsis,
            "disposition": disp,
            "disposition_display": compact_disposition(disp),
            "source": source,
            "minutes_label": minutes_label,
            "minutes_href": minutes_href,
            "source_status": ("Verified phrase-located passage" if verbatim_verified
                              else "Minutes passage not yet verified"),
            "provisions": provs,
            "digest_summaries": summaries,
        }
        if is_inq:
            page = inquiry_front_matter(source_meta, context)
            page += ["## Minutes transcript", ""]
            if substantive or posed:
                page += ['<p class="record-transcript-note">Section headings below are added for navigation.</p>', ""]
        else:
            page = source_meta + [f"# {label} — {subj}", ""]
            if synopsis:
                page += [f"*{md_escape(synopsis)}*", ""]
            page += ["  ·  ".join(hdr), "", srcline, "", "---", ""]
            if summaries:
                page += ["## Digest headnote",
                         "*Editorial summary from the PCA Digest, Part II (Interpretations of the Constitution) — "
                         + ("this is the Digest's wording, not the verbatim minutes. The authoritative text is "
                            "the verbatim record below / linked above.*" if verbatim_verified else
                            "this is the Digest's wording, not the verbatim minutes. The primary source passage "
                            "still needs verification.*"), ""]
                if len(summaries) == 1:
                    page += [summaries[0], ""]
                else:
                    page += [f"- {s}" for s in summaries] + [""]
                if provs:
                    page += ["**Key words:** " + ", ".join(provs), ""]
                if source:
                    page += ["**Inquiry from:** " + md_escape(source), ""]
                page += ["**In the minutes:** " + (deeplink(stem, primary_anchor, primary_printed)
                                                    if primary_anchor else "_(source passage not yet verified)_"),
                         "", "---", ""]
            page += ["## Verbatim record", ""]
            if ratified_only:
                page += ["*The General Assembly ratified this advice by reference; the substantive answer "
                         "is not printed as a separate passage in this volume. The ratifying action is quoted "
                         "below.*", ""]
            if substantive or posed:
                page += ['<p class="record-transcript-note">Section headings below are added for navigation.</p>', ""]
        if substantive:
            heading = ('<h3 class="record-transcript-heading">Question and answer</h3>'
                       if is_inq else "### Question and answer")
            page += [heading, "", substantive_body, ""]
        elif posed:
            if is_inq:
                page += ['<h3 class="record-transcript-heading">Inquiry</h3>', "", posed, "",
                         '<h3 class="record-transcript-heading">Response</h3>', ""]
            else:
                page += ["### As referred / posed", "", posed, "", "### CCB advice", ""]
            page += [body or ("" if is_inq else "_(CCB advice has no verified phrase locator yet; legacy line offsets are retained for audit.)_"), ""]
        else:
            page += [body or ("" if is_inq else "_(Verbatim source passage has no verified phrase locator yet; legacy line offsets are retained for audit.)_"), ""]
        if action:
            action_anchor = (action.get("page_anchor") or "").strip()
            ma = re.match(r"ga(\d+)-p(.+)$", action_anchor)
            if ma:
                action_anchor = f"ga{int(ma.group(1)):02d}-p{ma.group(2)}"
            page += ["## Assembly action", ""]
            if not is_inq:
                page += ["The General Assembly's later action is preserved separately from the substantive Q&A: "
                         + (deeplink(stem, action_anchor, action.get("printed_page")) if action_anchor else stem), ""]
            page += [action_body or ("" if is_inq else "_(Assembly action has no verified phrase locator yet.)_"), ""]
        back = ("[← Constitutional inquiry index](../index/INQUIRIES.md)" if is_inq
                else "[← Overture/amendment advice index](../index/CCB-OVERTURE-ADVICE.md)")
        page += ["---", "", back]
        output_path = Path(OUT) / (slug + ".md")
        page_text, _ = normalize_text(Path(ROOT), "\n".join(page) + "\n", output_path)
        output_path.write_text(page_text, encoding="utf-8")
        n_pages += 1

        minutes_link = (deeplink(stem, primary_anchor, primary_printed)
                        if primary_anchor else "_(source passage not yet verified)_")
        row = (f"| {md_escape(label)} | [{md_escape(subj)}](../inquiries/{slug}.md) | "
               f"{md_escape(synopsis)} | {md_escape(', '.join(provs))} | {md_escape(disp)} | "
               f"{md_escape(source)} | {minutes_link} |")
        (inq_rows if is_inq else adv_rows).setdefault(ordn, []).append((year, stem, row))
        search_rows.append({"type": "inquiry" if is_inq else "ccb-advice",
                            "title": subj, "sub": synopsis or "", "provisions": provs,
                            "year": year, "disposition": disp, "url": f"inquiries/{slug}.md"})

    import json as _json
    if ONLY_RELOCATED:
        print(f"[{ROOT}] refreshed {n_pages} relocated inquiry pages; left catalogues and other pages untouched")
        return

    if not PAGES_ONLY:
        _json.dump(search_rows, open(os.path.join(IDX, "inquiries_search.json"), "w"), ensure_ascii=False)

    common = ("Each entry pairs a **Digest-level headnote** (the PCA Digest's editorial summary, Part II) "
              "with the **verbatim record** sliced from the minutes; the **Minutes** column deep-links to "
              "the source page. **Subject** and **Synopsis** are distilled from the Digest's own text. The "
              "roster is drawn from the PCA Digest, Part II (1973–2018); later Assemblies are extracted "
              "directly from each volume's CCB report.")

    def write_catalogue(path, title, blurb, rows_by_ord, crosslink):
        L = [f"# {title}", "", blurb, "", common, "", crosslink, ""]
        total = 0
        for ordn in sorted(rows_by_ord):
            rows = rows_by_ord[ordn]
            year, stem = rows[0][0], rows[0][1]
            L += ["", f"## {ordinal(ordn)} General Assembly ({year})  ·  `{stem}`", "",
                  "| Inquiry | Subject | Synopsis | Provisions | Outcome | From | Minutes |",
                  "|---|---|---|---|---|---|---|"]
            for _, _, row in rows:
                L.append(row)
                total += 1
        open(os.path.join(IDX, path), "w", encoding="utf-8").write("\n".join(L) + "\n")
        return total

    n_inq = write_catalogue(
        "INQUIRIES.md", "Constitutional Inquiry Catalogue",
        "Questions of *constitutional interpretation* (Westminster Standards, *Book of Church Order*, "
        "*Rules of Assembly Operations*) referred to the **Committee on Constitutional Business (CCB)** — "
        "and, before the 18th General Assembly, the Committee on Judicial Business — answered with "
        "**non-binding advice**. Grouped by Assembly.",
        inq_rows,
        "*The CCB's advice on whether proposed overtures/amendments conflict with the Constitution is "
        "catalogued separately in **[Overture & amendment advice](CCB-OVERTURE-ADVICE.md)**.*")

    n_adv = write_catalogue(
        "CCB-OVERTURE-ADVICE.md", "CCB Advice on Overtures & Proposed Amendments",
        "The **Committee on Constitutional Business (CCB)**'s advice on whether a proposed overture or "
        "amendment is *in conflict* with the Constitution (its constitutional review of proposed changes, "
        "distinct from answering questions about what the Constitution means). Grouped by Assembly.",
        adv_rows,
        "*Genuine constitutional inquiries / non-judicial references (questions about the Constitution's "
        "meaning) are catalogued separately in **[Constitutional inquiries](INQUIRIES.md)**.*")

    print(f"[{ROOT}] wrote {n_pages} pages; INQUIRIES.md ({n_inq} inquiries across {len(inq_rows)} GAs), "
          f"CCB-OVERTURE-ADVICE.md ({n_adv} advices across {len(adv_rows)} GAs)")


if __name__ == "__main__":
    main()
