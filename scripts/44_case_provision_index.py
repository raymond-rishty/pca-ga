#!/usr/bin/env python3
"""44_case_provision_index.py — auditable judicial-case provision index.

Builds a fresh constitutional-provision cross-reference for SJC/CJB case pages.
The index is intentionally audit-oriented: each (provision, case) row records
which source(s) produced the tag (structured case metadata and/or a direct
markdown text match) and, for text matches, the exact case-page line numbers
where the provision was seen.

This is a *reverse* index over existing case pages. It does not simply trust the
existing forward case -> provision facets: it keeps those structured tags, then
performs a fresh markdown pass for BCO numbered sections, BCO Preface /
Preliminary Principles, and Westminster Standards citations (WCF/WLC/WSC).

Outputs:
  index/case_provision_index.json   machine-readable audit rows
  index/CASES-BY-PROVISION.md       human-readable provision index

Usage: 44_case_provision_index.py [ROOT]   (default: current working directory)
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IDX = ROOT / "index"
CASES_DIR = ROOT / "cases"

SUMMARY_OVERRIDES = {
    "ga18_1990__case1": (
        "This case concerns North Texas Presbytery's discretion to receive Rev. C. Don "
        "Darling to labor within its bounds despite his exception on remarriage, and whether "
        "that exception struck at the vitals of religion strongly enough to overturn the presbytery's judgment."
    ),
    "ga18_1990__case2": (
        "This related Rowlett appeal concerns alleged procedural irregularities in North Texas "
        "Presbytery's handling of the Darling matter, including notice, participation, evidence, "
        "and alleged prejudice."
    ),
    "ga47_2019__2018-05": (
        "The SJC did not reach the merits of TE David McKay's complaint against Central Indiana Presbytery; "
        "it held only that his email to the clerk of the lower court was insufficient notice under BCO 43-3, "
        "so the complaint was administratively out of order."
    ),
}

ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
    "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13,
    "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18,
    "xix": 19, "xx": 20, "xxi": 21, "xxii": 22, "xxiii": 23,
    "xxiv": 24, "xxv": 25, "xxvi": 26, "xxvii": 27, "xxviii": 28,
    "xxix": 29, "xxx": 30, "xxxi": 31, "xxxii": 32, "xxxiii": 33,
}
WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
STD_RANK = {"BCO": 0, "WCF": 1, "WLC": 2, "WSC": 3}

# Explicit-prefix provisions: BCO numbered sections and Westminster Standards.
# Keep the grammar deliberately narrow. In case text, bare "LC"/"SC" often means
# lower court / session commission, so those abbreviations are normalized only from
# structured metadata, not direct markdown text.
_NUM = r"\d{1,3}(?:\s*[-–:.]\s*\d{1,3})?(?:\s*(?:[-–.]\s*)?(?:\([a-z]\)|[a-z]\b|\d+))*"
_ROM = r"[IVX]{1,8}(?:\s*[-–:.]\s*(?:[IVX]{1,8}|\d{1,3}))?"
EXPLICIT_RE = re.compile(
    rf"\b(?P<std>BCO|B\.C\.O\.|Book of Church Order)\s*(?:§)?\s*(?P<num>{_NUM})"
    rf"|\b(?P<std2>WCF|W\.C\.F\.)\s*(?P<num2>{_NUM}|{_ROM})"
    rf"|\b(?P<std3>Westminster Confession of Faith)\s+(?:Chapter|Ch\.|chap\.?|paragraph|par\.?)\s*(?P<num3>{_NUM}|{_ROM})"
    rf"|\b(?P<std4>WLC|W\.L\.C\.)\s*(?:Q(?:uestion)?\.?\s*)?(?P<num4>{_NUM})"
    rf"|\b(?P<std5>Westminster Larger Catechism|Larger Catechism)\s+(?:Q(?:uestion)?\.?\s*)?(?P<num5>{_NUM})"
    rf"|\b(?P<std6>WSC|W\.S\.C\.)\s*(?:Q(?:uestion)?\.?\s*)?(?P<num6>{_NUM})"
    rf"|\b(?P<std7>Westminster Shorter Catechism|Shorter Catechism)\s+(?:Q(?:uestion)?\.?\s*)?(?P<num7>{_NUM})",
    re.I,
)
PREFACE_RE = re.compile(
    r"\b(?:BCO\s+)?Preface\s+(?:(?:Section\s+)?(?P<section>[IVX]+|I{1,3})|(?P<section_num>\d+))"
    r"(?:\s*[-–]?\s*\(?(?P<para>\d+|[a-z])\)?)?",
    re.I,
)
PRELIM_RE = re.compile(
    r"\b(?:BCO\s+)?Preliminary Principles?\s+(?P<first>[A-Za-z]+|[IVX]+|\d+)"
    r"(?:\s+(?:and|&)\s+(?P<second>[A-Za-z]+|[IVX]+|\d+))?",
    re.I,
)


def md_escape(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).replace("|", "\\|").strip()


def md_summary(s: Any, limit: int = 320) -> str:
    text = md_escape(s)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:—- ")
    return cut + "…"




def case_content_summary(path: Path) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()

    def clean(line: str) -> str:
        line = re.sub(r"<!--.*?-->", "", line).strip()
        line = re.sub(r"^#+\s*", "", line)
        line = line.replace("*", "").replace("_", "")
        return md_escape(line)

    def collect(start: int) -> str:
        parts: list[str] = []
        for line in lines[start:]:
            text = clean(line)
            if not text:
                if parts:
                    break
                continue
            if text.startswith("Court:") or text.startswith("Source:") or set(text) <= {"-"}:
                continue
            # Skip standalone caption/section fragments; the next paragraph usually states the issue/result.
            if text.lower() in {"introduction", "summary of the facts", "statement of the issue", "judgment", "reasoning"}:
                continue
            if re.fullmatch(r"(?:STANDING JUDICIAL COMMISSION CASE|JUDICIAL CASE|APPEAL OF|COMPLAINT OF|VS\.|VERSUS|[IVX]+\.|[A-Z0-9 .:/&’'()-]{4,})", text):
                continue
            parts.append(text)
            if len(" ".join(parts)) >= 260:
                break
        summary = md_summary(" ".join(parts))
        return summary if meaningful_summary(summary) else ""

    # Prefer the first substantive case paragraph (often the judgment/result appears before
    # the detailed fact summary), then fall back to an explicit summary section.
    def section_summary(patterns, label=""):
        for i, line in enumerate(lines):
            heading = clean(line).lower()
            if not any(re.search(p, heading, re.I) for p in patterns):
                continue
            parts = []
            for raw in lines[i + 1:]:
                text = clean(raw)
                if not text:
                    if parts:
                        break
                    continue
                low = text.lower()
                if low in {"judgment", "reasoning", "reasoning and opinion", "statement of the issues", "statement of issues", "summary of the facts"}:
                    break
                if re.fullmatch(r"(?:[IVX]+\.|[A-Z][A-Z .:/&’'()-]{6,})", text):
                    break
                parts.append(text)
                if len(" ".join(parts)) >= 260:
                    break
            if parts:
                body = md_summary(" ".join(parts))
                summary = f"{label}: {body}" if label else body
                return summary if meaningful_summary(summary) else ""
        return ""

    opening = collect(1)
    if opening and re.search(r"\b(judicially out of order|moot|not sustained|sustained|denied|dismissed|granted|remanded|affirmed)\b", opening, re.I):
        return opening
    issues = section_summary([r"statement of (the )?issues?"], "Issues")
    if issues:
        return issues
    judgment = section_summary([r"^judg(e)?ment$"], "Judgment")
    if judgment:
        return judgment
    if opening:
        return opening
    for i, line in enumerate(lines):
        if re.search(r"\bSUMMARY\b", line, re.I):
            found = collect(i + 1)
            if found:
                return found
    return ""


def meaningful_summary(text):
    text = md_escape(text)
    if not text:
        return False
    if len(text) < 50 and not re.search(r"\b(issues?|judg(e)?ment|moot|sustained|denied|dismissed|remanded|affirmed|out of order)\b", text, re.I):
        return False
    if re.fullmatch(r"(?:PCA|vs\.?|exhibit ['\"]?[a-z0-9]['\"]?|adjudication of case #?\d+|case \d+(?:-\d+)?)", text, re.I):
        return False
    if re.match(r"^case \d+(?:-\d+)?(?:\s|:)", text, re.I) and not re.search(r"\b(ruled|found|sustained|denied|dismissed|moot|out of order|affirmed|remanded|granted|issues?)\b", text, re.I):
        return False
    if re.match(r"^(?:\d+-\d+\s+)?compla?i?nt\b", text, re.I) and not re.search(r"\b(ruled|found|sustained|denied|dismissed|moot|out of order|affirmed|remanded|granted|issues?|whether|because)\b", text, re.I):
        return False
    if re.search(r"\b(stated clerk|p\.?o\.? box|box \d+|late fil)", text, re.I):
        return False
    if re.search(r"\bsummary of (?:the )?facts\b", text, re.I):
        return False
    if re.match(r"^(?:[IVXL]+\.|L\s*A)?\s*summary\b", text, re.I):
        return False
    if re.match(r"^issues:\s*summary\b", text, re.I):
        return False
    if re.search(r"\b(this case|this controversy|this complaint) arose out of\b", text, re.I):
        return False
    if re.fullmatch(r"[A-Z0-9 ,.'’()-]+", text) and not re.search(r"\b(ISSUES?|JUDG|MOOT|SUSTAIN|DENIED|DISMISSED|REMANDED|AFFIRMED)\b", text):
        return False
    return True


def case_summary(title: Any, disposition: Any = "", synopsis: Any = "") -> str:
    return md_summary(synopsis) if synopsis and meaningful_summary(synopsis) else ""


def norm_case_num(n: Any) -> str:
    m = re.match(r"^(\d{4})-(\d+)([a-z]?)$", str(n or ""), re.I)
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3).lower()}" if m else str(n or "")


def canon_std(raw: str | None) -> str:
    s = re.sub(r"[^A-Za-z]", "", raw or "").lower()
    if s in {"bco", "bookofchurchorder"}:
        return "BCO"
    if s in {"wcf", "westminsterconfessionoffaith"}:
        return "WCF"
    if s in {"wlc", "lc", "largercatechism", "westminsterlargercatechism"}:
        return "WLC"
    if s in {"wsc", "sc", "shortercatechism", "westminstershortercatechism"}:
        return "WSC"
    return raw or "BCO"


def explicit_groups(m: re.Match[str]) -> tuple[str | None, str | None]:
    for suffix in ["", "2", "3", "4", "5", "6", "7"]:
        std = m.group(f"std{suffix}")
        num = m.group(f"num{suffix}")
        if std and num:
            return std, num
    return None, None

def number_value(token: str | None) -> int | None:
    if not token:
        return None
    t = token.strip().lower().strip(".,;:()[]")
    if t.isdigit():
        return int(t)
    return WORD_NUM.get(t) or ROMAN.get(t)


def norm_num(num: str) -> str:
    s = re.sub(r"\s+", "", str(num or ""))
    s = s.replace("–", "-").replace(":", ".")
    s = re.sub(r"\(([a-z])\)", r".\1", s, flags=re.I)
    parts = re.split(r"([-.])", s)
    out: list[str] = []
    for part in parts:
        if part in {"-", "."}:
            out.append(part)
            continue
        val = ROMAN.get(part.lower())
        out.append(str(val) if val is not None else part.lower())
    return "".join(out).strip(".;,):]")


def norm_explicit(std_raw: str | None, num_raw: str | None) -> str | None:
    std = canon_std(std_raw)
    n = norm_num(num_raw or "")
    if not n:
        return None
    if std == "BCO":
        # Keep BCO chapter-only refs (e.g. BCO 43) but reject obvious non-BCO numbers.
        chapter = re.match(r"^(\d{1,2})(?:\D|$)", n)
        if not chapter or int(chapter.group(1)) > 63:
            return None
        n = n.replace(".", "-", 1) if re.match(r"^\d+\.\d", n) else n
    return f"{std} {n}"


def norm_metadata(value: Any) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for m in PREFACE_RE.finditer(raw):
        p = norm_preface(m)
        if p:
            out.append(p)
    for m in PRELIM_RE.finditer(raw):
        out.extend(norm_prelim(m))
    for m in EXPLICIT_RE.finditer(raw):
        std, num = explicit_groups(m)
        p = norm_explicit(std, num)
        if p:
            out.append(p)
    if not out:
        legacy = re.match(r"^(LC|SC)\s+(.+)$", raw, re.I)
        if legacy:
            p = norm_explicit(legacy.group(1), legacy.group(2))
            if p:
                out.append(p)
    if not out:
        # Existing bco_cited_* metadata often stores bare BCO sections like "43-2".
        p = norm_explicit("BCO", raw)
        if p:
            out.append(p)
    return sorted(set(out), key=prov_sort_key)


def norm_preface(m: re.Match[str]) -> str | None:
    section = number_value(m.group("section") or m.group("section_num"))
    if not section:
        return None
    para = m.group("para")
    return f"BCO Preface {section}" + (f"-({para.lower()})" if para else "")


def norm_prelim(m: re.Match[str]) -> list[str]:
    vals = [number_value(m.group("first")), number_value(m.group("second"))]
    return [f"BCO Preliminary Principle {v}" for v in vals if v]


def prov_sort_key(p: str) -> tuple:
    std = p.split(" ", 1)[0]
    return (STD_RANK.get(std, 9), [int(n) for n in re.findall(r"\d+", p)], p)


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def text_hits(path: Path) -> dict[str, list[dict[str, Any]]]:
    hits: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    if not path.exists():
        return hits
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        snippet = re.sub(r"\s+", " ", line).strip()
        if not snippet:
            continue
        for m in PREFACE_RE.finditer(line):
            p = norm_preface(m)
            if p:
                hits[p].append({"line": lineno, "snippet": snippet[:260]})
        for m in PRELIM_RE.finditer(line):
            for p in norm_prelim(m):
                hits[p].append({"line": lineno, "snippet": snippet[:260]})
        for m in EXPLICIT_RE.finditer(line):
            std, num = explicit_groups(m)
            p = norm_explicit(std, num)
            if p:
                hits[p].append({"line": lineno, "snippet": snippet[:260]})
    return hits


def main() -> None:
    cases = {norm_case_num(c.get("case_number")): c for c in load_jsonl(IDX / "cases.jsonl") if c.get("case_number")}
    page_map = load_json(IDX / "case_pages_map.json", {})

    rows: list[dict[str, Any]] = []
    seen_files: set[str] = set()
    for map_num, entry in sorted(page_map.items(), key=lambda kv: (kv[1].get("file", ""), kv[0])):
        file_stem = entry.get("file")
        if not file_stem or file_stem in seen_files:
            continue
        seen_files.add(file_stem)
        case_path = CASES_DIR / f"{file_stem}.md"
        nums = [norm_case_num(n) for n in entry.get("numbers", [map_num])]
        case_records = [cases[n] for n in nums if n in cases]
        title = entry.get("title") or next((c.get("title") for c in case_records if c.get("title")), map_num)
        year = next((c.get("year") for c in case_records if c.get("year")), None)
        disposition = next((c.get("disposition") for c in case_records if c.get("disposition")), "")
        body = next((c.get("body") for c in case_records if c.get("body")), "SJC/CJB")
        synopsis = SUMMARY_OVERRIDES.get(file_stem) or case_summary(title, disposition, next((c.get("synopsis") for c in case_records if c.get("synopsis")), ""))

        by_prov: dict[str, dict[str, Any]] = collections.defaultdict(lambda: {"sources": set(), "evidence": []})
        for c in case_records:
            for raw in c.get("bco_cited_as") or []:
                for prov in norm_metadata(raw):
                    by_prov[prov]["sources"].add("cases.jsonl:bco_cited_as")
            for raw in c.get("bco_cited_current") or []:
                for prov in norm_metadata(raw):
                    by_prov[prov]["sources"].add("cases.jsonl:bco_cited_current")

        for prov, hits in text_hits(case_path).items():
            by_prov[prov]["sources"].add("case_markdown_text")
            by_prov[prov]["evidence"].extend(hits[:8])

        for prov, audit in sorted(by_prov.items(), key=lambda kv: prov_sort_key(kv[0])):
            rows.append({
                "provision": prov,
                "case_numbers": nums,
                "title": title,
                "body": body,
                "year": year,
                "disposition": disposition,
                "synopsis": synopsis,
                "url": f"cases/{file_stem}.md",
                "sources": sorted(audit["sources"]),
                "evidence": audit["evidence"],
            })

    rows.sort(key=lambda r: (prov_sort_key(r["provision"]), r.get("year") or 0, r["title"]))
    (IDX / "case_provision_index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        grouped[r["provision"]].append(r)

    lines = [
        "# Judicial Cases by Constitutional Provision",
        "",
        "Auditable cross-reference of SJC/CJB judicial case pages by constitutional provision, including BCO sections, BCO Preface / Preliminary Principles, and Westminster Standards citations (WCF/WLC/WSC).",
        "",
        "Each row lists its tag source: `case_markdown_text` means the provision was freshly found in the case page; `cases.jsonl:*` means it came from structured case metadata. The summary column gives a short case synopsis when one is available, so readers and RAG systems can triage which full-text cases to inspect. The JSON audit file preserves line-number evidence and snippets for text-derived tags.",
        "",
        f"*{len(rows)} case-provision tags across {len(grouped)} provisions.*",
        "",
    ]
    for prov in sorted(grouped, key=prov_sort_key):
        lines.extend([f"## {prov}", "", "| Year | Case | Disposition | Summary | Tag sources | Evidence lines |", "|---:|---|---|---|---|---|"])
        for r in grouped[prov]:
            nums = ", ".join(n for n in r["case_numbers"] if n) or "case"
            link = f"../{r['url']}"
            sources = ", ".join(f"`{s}`" for s in r["sources"])
            ev = ", ".join(str(e["line"]) for e in r["evidence"][:5]) or "—"
            lines.append(f"| {r.get('year') or '—'} | [{md_escape(nums)} — {md_escape(r['title'])}]({link}) | {md_escape(r.get('disposition'))} | {md_summary(r.get('synopsis'))} | {sources} | {ev} |")
        lines.append("")
    (IDX / "CASES-BY-PROVISION.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    by_std = collections.Counter(r["provision"].split(" ", 1)[0] for r in rows)
    print(f"case-provision rows: {len(rows)}")
    print(f"provisions: {len(grouped)}")
    print(f"standards: {dict(by_std)}")
    print("wrote index/case_provision_index.json")
    print("wrote index/CASES-BY-PROVISION.md")


if __name__ == "__main__":
    main()
