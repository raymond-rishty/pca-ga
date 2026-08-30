#!/usr/bin/env python3
"""
48_case_citation_inventory.py — exploratory judicial-case identity registry and
case-to-case reference inventory.

This is deliberately a READ-ONLY enrichment pass over the verbatim case pages.
It does not rewrite case markdown and it does not promote guessed aliases to
canonical identity.

Inputs:
  index/CASES.md
  cases/*.md

Outputs:
  index/case_identity_registry.json
  index/case_reference_candidates.json
  index/case_reference_unresolved.json
  index/CASE-REFERENCE-REPORT.md

The goal of this first pass is empirical:
  * learn how cases are actually named in the index and in printed decision text;
  * use known docket numbers as the strongest resolution signal;
  * retain exact source-text evidence for every candidate;
  * expose ambiguity rather than guessing;
  * establish stable decision entities for later inline links / cites / cited-by.

No third-party case database is used as an authority here.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

ROOT = Path(os.environ.get("PCA_GA_ROOT", os.getcwd()))
CASES_INDEX = ROOT / "index" / "CASES.md"
CASES_DIR = ROOT / "cases"
OUT_REGISTRY = ROOT / "index" / "case_identity_registry.json"
OUT_CANDIDATES = ROOT / "index" / "case_reference_candidates.json"
OUT_UNRESOLVED = ROOT / "index" / "case_reference_unresolved.json"
OUT_REPORT = ROOT / "index" / "CASE-REFERENCE-REPORT.md"

# Modern docket numbers plus older CJB/GA-era forms such as 3-12, 12-83, 92-9b.
DOCKET_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z-])(\d{1,4}-\d{1,3}[A-Za-z]?)(?![0-9A-Za-z-])")

# Deliberately broad: this is for an unresolved-candidate report, never direct
# resolution. It is constrained to ecclesiastical-looking right-hand parties so
# ordinary civil-case citations are less likely to flood the report.
CAPTION_CANDIDATE_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9 .,'’&()\-]{1,90}?\s+(?:v\.?|vs\.?|versus)\s+"
    r"[A-Z][A-Za-z0-9 .,'’&()\-]{1,100}?(?:Presbytery|Session|Church|PCA))\b",
    re.I,
)

PROCEEDING_PREFIX_RE = re.compile(
    r"^(?:complaints?\s+of|complaint\s+of|appeal\s+of|appeal|complaint|"
    r"reference|petition|memorial)\s+",
    re.I,
)

TRAILING_DECISION_RE = re.compile(
    r"\s+(?:decision|ruling|judgment)\s+on\s+(?:appeal|complaint|reference|petition).*$",
    re.I,
)

CASE_LEAD_RE = re.compile(
    r"^(?:case|cases|sjc\s+case|sjc\s+cases|judicial\s+case)\s+"
    r"(?:no\.?\s*)?(?:\d{1,4}-\d{1,3}[A-Za-z]?"
    r"(?:\s*(?:,|/|&|and)\s*(?:case\s*)?\d{1,4}-\d{1,3}[A-Za-z]?)*\s*)",
    re.I,
)

ROLE_PREFIX_RE = re.compile(
    r"\b(?:TE|RE|REV\.?|MR\.?|MRS\.?|MS\.?|DEACON|ELDER|RULING\s+ELDER|"
    r"TEACHING\s+ELDER)\s+",
    re.I,
)

DISSENT_DECOR_RE = re.compile(r"\s*·\s*\*(?:dissent|concurrence)\*\s*", re.I)


@dataclass(frozen=True)
class IndexRow:
    decision_id: str
    case_cell: str
    title_cell: str
    disposition: str
    summary: str
    page_cell: str
    ga_heading: str


@dataclass
class Occurrence:
    source_decision: str
    source_file: str
    source_dockets: list[str]
    target_decision: str | None
    target_dockets: list[str]
    surface_text: str
    match_type: str
    confidence: float
    line: int
    context: str
    self_reference: bool
    evidence_key: str


def clean_md(text: str) -> str:
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def norm_compare(text: str) -> str:
    """Conservative comparison normalization; not a canonical display form."""
    text = text.casefold()
    text = text.replace("’", "'")
    text = re.sub(r"\bversus\b|\bvs\.?\b|\bv\.\b", " v ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_space(text)


def clean_index_title(text: str) -> str:
    text = DISSENT_DECOR_RE.sub(" ", text)
    text = clean_md(text)
    # Strip obvious page-note pollution but preserve proceeding labels for raw data.
    text = re.sub(r"\s+p\.\s*\d+\s*$", "", text, flags=re.I)
    return normalize_space(text)


def provisional_caption(text: str) -> str:
    """Produce a display candidate without treating it as authoritative."""
    text = clean_index_title(text)
    text = re.sub(r"^BCO\s+\d+(?:-\d+)?\s+", "", text, flags=re.I)
    text = PROCEEDING_PREFIX_RE.sub("", text)
    text = CASE_LEAD_RE.sub("", text)
    text = TRAILING_DECISION_RE.sub("", text)
    text = re.sub(r"\s+\(\s*(?:appeal|complaint|reference|petition)\s*\)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+#{2,}.*$", "", text)
    return normalize_space(text.strip(" -—:;."))


def parse_index(path: Path) -> list[IndexRow]:
    rows: list[IndexRow] = []
    ga_heading = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("## "):
            ga_heading = raw[3:].strip()
            continue
        if not raw.startswith("|") or "../cases/" not in raw:
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        m = re.search(r"\.\./cases/([^/)]+)\.md", cells[0])
        if not m:
            # stubs and some pages may link in the Page column rather than case cell.
            m = re.search(r"\.\./cases/([^/)]+)\.md", raw)
        if not m:
            continue
        rows.append(IndexRow(
            decision_id=m.group(1),
            case_cell=cells[0],
            title_cell=cells[1],
            disposition=cells[2],
            summary=cells[3],
            page_cell=cells[4],
            ga_heading=ga_heading,
        ))
    return rows


def docket_tokens(text: str) -> list[str]:
    found = []
    seen = set()
    for m in DOCKET_TOKEN_RE.finditer(clean_md(text)):
        d = m.group(1)
        if d not in seen:
            seen.add(d)
            found.append(d)
    return found


def page_h1_and_headers(path: Path) -> tuple[str, list[str]]:
    h1 = ""
    headers: list[str] = []
    if not path.exists():
        return h1, headers
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("# ") and not h1:
            h1 = clean_md(raw[2:])
        if raw.startswith("##"):
            text = clean_md(re.sub(r"^#+\s*", "", raw))
            if re.search(r"\b(?:case|complaint|appeal|v\.?|vs\.?|versus)\b", text, re.I):
                headers.append(text)
        if len(headers) >= 8:
            break
    return h1, headers


def caption_from_h1(h1: str) -> str:
    if " — " in h1:
        return provisional_caption(h1.split(" — ", 1)[1])
    if " - " in h1:
        left, right = h1.split(" - ", 1)
        if DOCKET_TOKEN_RE.search(left):
            return provisional_caption(right)
    return provisional_caption(h1)


def caption_from_printed_header(header: str) -> str:
    text = CASE_LEAD_RE.sub("", header)
    text = TRAILING_DECISION_RE.sub("", text)
    # Printed headers often begin with proceeding form before the parties.
    text = PROCEEDING_PREFIX_RE.sub("", text)
    return provisional_caption(text)


def safe_caption_alias(text: str) -> bool:
    if not text or len(text) < 8 or len(text) > 220:
        return False
    if re.search(r"#{2,}|statement of the facts|summary of the", text, re.I):
        return False
    return bool(re.search(r"\b(?:v\.?|vs\.?|versus)\b", text, re.I))


def build_registry(rows: list[IndexRow]) -> list[dict]:
    grouped: dict[str, list[IndexRow]] = collections.defaultdict(list)
    for row in rows:
        grouped[row.decision_id].append(row)

    registry = []
    for decision_id, rs in sorted(grouped.items()):
        page = CASES_DIR / f"{decision_id}.md"
        h1, headers = page_h1_and_headers(page)

        dockets = []
        for r in rs:
            dockets.extend(docket_tokens(r.case_cell))
        dockets.extend(docket_tokens(h1))
        # Filename is often the cleanest source for consolidated docket aliases.
        dockets.extend(docket_tokens(decision_id.replace("_", "/")))
        dockets = list(dict.fromkeys(dockets))

        raw_titles = list(dict.fromkeys(clean_index_title(r.title_cell) for r in rs if r.title_cell.strip()))
        h1_caption = caption_from_h1(h1) if h1 else ""
        index_caption = next((provisional_caption(t) for t in raw_titles if provisional_caption(t)), "")
        printed_captions = []
        for header in headers:
            cap = caption_from_printed_header(header)
            if safe_caption_alias(cap):
                printed_captions.append(cap)
        printed_captions = list(dict.fromkeys(printed_captions))

        canonical_caption = h1_caption or index_caption or (printed_captions[0] if printed_captions else "")

        # Only exact/near-exact observed caption strings become aliases in this
        # exploratory registry. Surname-only aliases are intentionally NOT guessed.
        aliases = []
        for value in [canonical_caption, *raw_titles, *printed_captions]:
            value = provisional_caption(value)
            if safe_caption_alias(value) and value not in aliases:
                aliases.append(value)

        # A normalized v/vs/versus form is useful for matching while retaining the
        # exact observed strings above as evidence.
        alias_keys = sorted({norm_compare(a) for a in aliases if a})

        registry.append({
            "decision_id": decision_id,
            "case_file": f"cases/{decision_id}.md",
            "docket_numbers": dockets,
            "canonical_caption_provisional": canonical_caption,
            "aliases_observed": aliases,
            "alias_keys": alias_keys,
            "index_titles_raw": raw_titles,
            "page_h1": h1,
            "printed_headers_sample": headers,
            "dispositions_observed": list(dict.fromkeys(clean_md(r.disposition) for r in rs if r.disposition.strip())),
            "assembly_headings": list(dict.fromkeys(r.ga_heading for r in rs if r.ga_heading)),
            "identity_status": "provisional",
            "authority_note": (
                "Identity assembled from this corpus's index/page headings for exploration; "
                "canonical identity should ultimately be reconciled to the authoritative roster/minutes."
            ),
        })
    return registry


def context_window(line: str, start: int, end: int, width: int = 150) -> str:
    a = max(0, start - width)
    b = min(len(line), end + width)
    return normalize_space(line[a:b])


def make_maps(registry: list[dict]):
    docket_to_decisions: dict[str, set[str]] = collections.defaultdict(set)
    alias_key_to_decisions: dict[str, set[str]] = collections.defaultdict(set)
    by_id = {}
    for entry in registry:
        by_id[entry["decision_id"]] = entry
        for d in entry["docket_numbers"]:
            docket_to_decisions[d].add(entry["decision_id"])
        for k in entry["alias_keys"]:
            alias_key_to_decisions[k].add(entry["decision_id"])
    return docket_to_decisions, alias_key_to_decisions, by_id


def source_dockets(decision_id: str, by_id: dict[str, dict]) -> list[str]:
    return by_id.get(decision_id, {}).get("docket_numbers", [])


def add_occurrence(
    out: list[Occurrence],
    seen: set[tuple],
    *,
    source_decision: str,
    source_file: str,
    source_dockets_: list[str],
    target_decision: str | None,
    target_dockets: list[str],
    surface_text: str,
    match_type: str,
    confidence: float,
    line_no: int,
    context: str,
    self_reference: bool,
):
    key = (source_decision, target_decision, line_no, surface_text, match_type)
    if key in seen:
        return
    seen.add(key)
    out.append(Occurrence(
        source_decision=source_decision,
        source_file=source_file,
        source_dockets=source_dockets_,
        target_decision=target_decision,
        target_dockets=target_dockets,
        surface_text=surface_text,
        match_type=match_type,
        confidence=confidence,
        line=line_no,
        context=context,
        self_reference=self_reference,
        evidence_key=f"{source_file}:L{line_no}",
    ))


def scan_references(registry: list[dict]) -> tuple[list[dict], list[dict]]:
    docket_map, alias_map, by_id = make_maps(registry)
    known_dockets = set(docket_map)

    # Exact observed aliases only. Longer strings first prevents a short caption
    # from masking a more informative full caption on the same line.
    alias_patterns: list[tuple[str, str, re.Pattern]] = []
    for entry in registry:
        for alias in entry["aliases_observed"]:
            if len(alias) < 10:
                continue
            # Flexible only for v/vs/versus and whitespace; names otherwise remain exact.
            parts = re.split(r"\s+(?:v\.?|vs\.?|versus)\s+", alias, maxsplit=1, flags=re.I)
            if len(parts) == 2:
                pat = re.compile(
                    re.escape(parts[0]).replace(r"\ ", r"\s+")
                    + r"\s+(?:v\.?|vs\.?|versus)\s+"
                    + re.escape(parts[1]).replace(r"\ ", r"\s+"),
                    re.I,
                )
            else:
                pat = re.compile(re.escape(alias).replace(r"\ ", r"\s+"), re.I)
            alias_patterns.append((entry["decision_id"], alias, pat))
    alias_patterns.sort(key=lambda x: len(x[1]), reverse=True)

    resolved: list[Occurrence] = []
    unresolved: list[Occurrence] = []
    seen_resolved: set[tuple] = set()
    seen_unresolved: set[tuple] = set()

    for page in sorted(CASES_DIR.glob("*.md")):
        source = page.stem
        if source not in by_id:
            # Orphan pages are still useful evidence, but the graph cannot safely
            # identify their source node until registry reconciliation catches up.
            source_ds = docket_tokens(source.replace("_", "/"))
        else:
            source_ds = source_dockets(source, by_id)

        lines = page.read_text(encoding="utf-8").splitlines()
        # Skip generated page metadata above the horizontal rule; the decision text
        # itself begins after it. If there is no rule, scan the whole page.
        start_ix = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                start_ix = i + 1
                break

        for i in range(start_ix, len(lines)):
            line = lines[i]
            if not line.strip() or line.lstrip().startswith("<!--"):
                continue
            line_no = i + 1

            # 1. Registry-known docket tokens: strongest first-pass signal.
            for m in DOCKET_TOKEN_RE.finditer(line):
                docket = m.group(1)
                if docket not in known_dockets:
                    continue
                targets = sorted(docket_map[docket])
                explicit_case_word = bool(re.search(
                    r"(?:case|cases|sjc|judicial|decision|ruling)\s*(?:no\.?\s*)?$",
                    line[max(0, m.start() - 30):m.start()], re.I,
                ))
                confidence = 1.0 if len(targets) == 1 and explicit_case_word else (0.98 if len(targets) == 1 else 0.55)
                for target in targets:
                    add_occurrence(
                        resolved if len(targets) == 1 else unresolved,
                        seen_resolved if len(targets) == 1 else seen_unresolved,
                        source_decision=source,
                        source_file=str(page.relative_to(ROOT)),
                        source_dockets_=source_ds,
                        target_decision=target if len(targets) == 1 else None,
                        target_dockets=[docket],
                        surface_text=m.group(0),
                        match_type="docket_explicit" if explicit_case_word else "docket_known",
                        confidence=confidence,
                        line_no=line_no,
                        context=context_window(line, m.start(), m.end()),
                        self_reference=(target == source),
                    )

            # 2. Exact observed captions / conservative v-vs normalization.
            occupied = []
            for target, alias, pat in alias_patterns:
                for m in pat.finditer(line):
                    # Avoid duplicate nested caption matches on the same span.
                    span = (m.start(), m.end())
                    if any(a <= span[0] and span[1] <= b for a, b in occupied):
                        continue
                    occupied.append(span)
                    key = norm_compare(alias)
                    targets = sorted(alias_map.get(key, {target}))
                    unique = len(targets) == 1
                    add_occurrence(
                        resolved if unique else unresolved,
                        seen_resolved if unique else seen_unresolved,
                        source_decision=source,
                        source_file=str(page.relative_to(ROOT)),
                        source_dockets_=source_ds,
                        target_decision=targets[0] if unique else None,
                        target_dockets=(by_id[targets[0]]["docket_numbers"] if unique else []),
                        surface_text=m.group(0),
                        match_type="caption_observed",
                        confidence=0.97 if unique else 0.5,
                        line_no=line_no,
                        context=context_window(line, m.start(), m.end()),
                        self_reference=(unique and targets[0] == source),
                    )

            # 3. Caption-shaped strings that did not resolve. These are discovery
            # material for extending the alias registry, not guessed graph edges.
            for m in CAPTION_CANDIDATE_RE.finditer(line):
                surface = normalize_space(m.group(1))
                key = norm_compare(surface)
                targets = sorted(alias_map.get(key, set()))
                if len(targets) == 1:
                    # Already captured by observed-caption matching in most cases.
                    continue
                add_occurrence(
                    unresolved,
                    seen_unresolved,
                    source_decision=source,
                    source_file=str(page.relative_to(ROOT)),
                    source_dockets_=source_ds,
                    target_decision=None,
                    target_dockets=[],
                    surface_text=surface,
                    match_type="caption_unresolved",
                    confidence=0.25,
                    line_no=line_no,
                    context=context_window(line, m.start(), m.end()),
                    self_reference=False,
                )

    resolved_dicts = [asdict(o) for o in resolved]
    unresolved_dicts = [asdict(o) for o in unresolved]
    return resolved_dicts, unresolved_dicts


def graph_edges(candidates: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for c in candidates:
        if not c["target_decision"] or c["self_reference"]:
            continue
        buckets[(c["source_decision"], c["target_decision"])].append(c)
    edges = []
    for (source, target), occs in sorted(buckets.items()):
        edges.append({
            "source": source,
            "target": target,
            "occurrences": len(occs),
            "evidence": [
                {
                    "surface_text": o["surface_text"],
                    "match_type": o["match_type"],
                    "confidence": o["confidence"],
                    "source_file": o["source_file"],
                    "line": o["line"],
                    "context": o["context"],
                }
                for o in occs
            ],
        })
    return edges


def write_report(registry: list[dict], candidates: list[dict], unresolved: list[dict]) -> None:
    edges = graph_edges(candidates)
    docket_hits = [c for c in candidates if c["match_type"].startswith("docket")]
    caption_hits = [c for c in candidates if c["match_type"] == "caption_observed"]
    self_hits = [c for c in candidates if c["self_reference"]]
    inbound = collections.Counter(e["target"] for e in edges)
    outbound = collections.Counter(e["source"] for e in edges)
    alias_counts = collections.Counter(len(e["aliases_observed"]) for e in registry)
    no_caption = [e for e in registry if not e["canonical_caption_provisional"]]
    no_docket = [e for e in registry if not e["docket_numbers"]]

    lines = [
        "# Case-reference exploratory report",
        "",
        "Generated by `scripts/48_case_citation_inventory.py`. This report is an audit aid, not authority.",
        "",
        "## Identity registry",
        "",
        f"- Decision/page entities: **{len(registry)}**",
        f"- Entities with no parsed docket number: **{len(no_docket)}**",
        f"- Entities with no provisional caption: **{len(no_caption)}**",
        f"- Entities with at least one observed caption alias: **{sum(1 for e in registry if e['aliases_observed'])}**",
        f"- Entities with multiple observed caption aliases: **{sum(1 for e in registry if len(e['aliases_observed']) > 1)}**",
        "",
        "The registry intentionally does not invent surname-only aliases. Its aliases are strings actually observed in the corpus's index/page headings.",
        "",
        "## Reference candidates",
        "",
        f"- Resolved occurrences: **{len(candidates)}**",
        f"- Registry-known docket occurrences: **{len(docket_hits)}**",
        f"- Observed-caption occurrences: **{len(caption_hits)}**",
        f"- Self-reference occurrences retained for audit: **{len(self_hits)}**",
        f"- Unresolved/ambiguous candidates: **{len(unresolved)}**",
        f"- Distinct non-self decision-to-decision edges: **{len(edges)}**",
        "",
        "## Most referenced targets in this exploratory graph",
        "",
        "| Decision | Distinct citing decisions |",
        "|---|---:|",
    ]
    for decision, count in inbound.most_common(25):
        entry = next((e for e in registry if e["decision_id"] == decision), None)
        label = entry["canonical_caption_provisional"] if entry else decision
        lines.append(f"| `{decision}` — {label} | {count} |")

    lines += [
        "",
        "## Decisions with the most outgoing reference edges",
        "",
        "| Decision | Distinct referenced decisions |",
        "|---|---:|",
    ]
    for decision, count in outbound.most_common(25):
        entry = next((e for e in registry if e["decision_id"] == decision), None)
        label = entry["canonical_caption_provisional"] if entry else decision
        lines.append(f"| `{decision}` — {label} | {count} |")

    lines += [
        "",
        "## What to review next",
        "",
        "1. Review `case_reference_unresolved.json` for recurring caption forms that should become *observed* aliases.",
        "2. Inspect docket matches without an explicit `Case`/`SJC`/`Decision` cue; some may be dates or unrelated numbers that happen to equal a docket.",
        "3. Reconcile provisional captions/identity against the Digest roster before calling them canonical.",
        "4. Only after that, add inline rendering and generated `cites` / `cited by` views.",
        "5. Later distinguish SJC reliance from citations occurring only inside party briefs, quoted material, procedural history, concurrences, or dissents.",
        "",
    ]
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", help="Repository root (defaults to PCA_GA_ROOT/cwd)")
    args = ap.parse_args()
    global ROOT, CASES_INDEX, CASES_DIR, OUT_REGISTRY, OUT_CANDIDATES, OUT_UNRESOLVED, OUT_REPORT
    if args.root:
        ROOT = Path(args.root).resolve()
        CASES_INDEX = ROOT / "index" / "CASES.md"
        CASES_DIR = ROOT / "cases"
        OUT_REGISTRY = ROOT / "index" / "case_identity_registry.json"
        OUT_CANDIDATES = ROOT / "index" / "case_reference_candidates.json"
        OUT_UNRESOLVED = ROOT / "index" / "case_reference_unresolved.json"
        OUT_REPORT = ROOT / "index" / "CASE-REFERENCE-REPORT.md"

    if not CASES_INDEX.exists():
        raise SystemExit(f"missing {CASES_INDEX}")
    if not CASES_DIR.is_dir():
        raise SystemExit(f"missing {CASES_DIR}")

    rows = parse_index(CASES_INDEX)
    registry = build_registry(rows)
    candidates, unresolved = scan_references(registry)

    OUT_REGISTRY.write_text(json.dumps({
        "version": 1,
        "status": "exploratory",
        "identity_unit": "one adjudicated decision/page; may carry multiple docket numbers",
        "entries": registry,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    OUT_CANDIDATES.write_text(json.dumps({
        "version": 1,
        "status": "exploratory",
        "occurrences": candidates,
        "edges": graph_edges(candidates),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    OUT_UNRESOLVED.write_text(json.dumps({
        "version": 1,
        "status": "exploratory",
        "occurrences": unresolved,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    write_report(registry, candidates, unresolved)

    print(f"identity entities: {len(registry)}")
    print(f"resolved reference occurrences: {len(candidates)}")
    print(f"unresolved/ambiguous occurrences: {len(unresolved)}")
    print(f"graph edges: {len(graph_edges(candidates))}")
    print(f"wrote {OUT_REGISTRY.relative_to(ROOT)}")
    print(f"wrote {OUT_CANDIDATES.relative_to(ROOT)}")
    print(f"wrote {OUT_UNRESOLVED.relative_to(ROOT)}")
    print(f"wrote {OUT_REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
