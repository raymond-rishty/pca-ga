#!/usr/bin/env python3
"""Project the per-provision authority index from the provision catalogue.

Projects:
  index/authority_index.json      flat list: one row per (provision, authority)
  index/AUTHORITY-BY-PROVISION.md cross-reference: each provision -> all authorities
  authorities/<slug>.md           per-provision detail pages

The provision catalogue is authoritative for text, records, relationships,
evidence, and coverage. This script only writes the legacy authority index and
its Markdown projections.

Usage: 43_authority_index.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import collections, json, os, re, sys
from pathlib import Path

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
CASES_DIR = os.path.join(ROOT, "cases")
AUTH_DIR = os.path.join(ROOT, "authorities")


# ── provision extraction ──────────────────────────────────────────────────────

_PROV_RE = re.compile(
    r'\b('
    r'BCO\s+\d+[-–]\d+(?:[.\-][0-9a-zA-Z]+)*'
    r'|WCF\s+\d+[-–]\d+'
    r'|WCF\s+\d+(?!\s*[-–]\s*\d)'
    r'|WLC\s+\d+'
    r'|WSC\s+\d+'
    r'|RAO\s+\d+[-–]\d+(?:[.\-][0-9a-zA-Z]+)*'
    r')',
    re.I
)

def norm_prov(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.replace('–', '-')
    # Strip section-sign variants: "BCO § 31:2" -> "BCO 31:2"
    s = re.sub(r'^(BCO|WCF|WLC|WSC|RAO)\s*§?\s*', lambda m: m.group(1).upper() + ' ', s, flags=re.I)
    # Fix OCR: lowercase 'l' (ell) mistaken for '1' inside provision numbers: "BCO 2l-4" -> "BCO 21-4"
    s = re.sub(r'^(BCO|WCF|WLC|WSC|RAO) (\d*l\d*)',
               lambda m: m.group(1) + ' ' + m.group(2).replace('l', '1'), s)
    # Normalize colon or dot as primary chapter-section separator: BCO 24:1 / BCO 24.1 -> BCO 24-1
    s = re.sub(r'^(BCO|WCF|WLC|WSC|RAO) (\d+)[.:](\d)',
               lambda m: f'{m.group(1)} {m.group(2)}-{m.group(3)}', s)
    # Normalize parenthetical sub-provisions: "BCO 21-4(e)" -> "BCO 21-4.e"
    s = re.sub(r'(-\d+)\(([a-z])\)', lambda m: f'{m.group(1)}.{m.group(2)}', s, flags=re.I)
    # Normalize bare-letter sub-provisions: "BCO 21-4e" (letter touching digit) -> "BCO 21-4.e"
    s = re.sub(r'(-\d+)([a-zA-Z])$', lambda m: f'{m.group(1)}.{m.group(2).lower()}', s)
    # Strip trailing punctuation and stray brackets: "BCO 21-7:" / "BCO 21-4)" -> clean
    s = s.rstrip(':;.,)')
    # Canonical provision numbers do not retain OCR/source padding: BCO 08-7 -> BCO 8-7.
    s = re.sub(
        r'^(BCO|WCF|WLC|WSC|RAO) (\d+)(.*)$',
        lambda m: f'{m.group(1)} {int(m.group(2))}{m.group(3)}',
        s,
    )
    return s

def extract_provisions(text: str) -> list[str]:
    return sorted({norm_prov(m.group(0)) for m in _PROV_RE.finditer(text)})

def norm_case_num(n: str) -> str:
    """'1990-08' -> '1990-8' to match cases.jsonl format."""
    m = re.match(r'^(\d{4})-(\d+)([a-z]?)$', str(n))
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}" if m else str(n)


# ── provision sort key ────────────────────────────────────────────────────────

_STD_RANK = {'BCO': 0, 'WCF': 1, 'WLC': 2, 'WSC': 3, 'RAO': 4}
def prov_sort_key(p: str) -> tuple:
    parts = p.split(' ', 1)
    std = parts[0].upper()
    nums = [int(x) for x in re.findall(r'\d+', parts[1] if len(parts) > 1 else '')]
    return (_STD_RANK.get(std, 9), nums)


# ── utilities ─────────────────────────────────────────────────────────────────

def prov_slug(p: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '-', p).strip('-')

def md_escape(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).replace('|', '\\|').strip()

_STRIP_MD = re.compile(r'<[^>]+>|<!--.*?-->|\*+|`+', re.S)
_STRIP_ANCHOR = re.compile(r'#+\s*')

def plain(s: str) -> str:
    s = _STRIP_MD.sub(' ', s)
    s = _STRIP_ANCHOR.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def without_front_matter(text: str) -> str:
    """Keep source metadata out of citations and excerpts drawn from Markdown."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == '---':
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() in {'---', '...'}:
                return ''.join(lines[index + 1:])
    return text

def snippet_for(text: str, prov: str, ctx: int = 220) -> str:
    m = re.search(re.escape(prov), text, re.I)
    if not m:
        nums = re.search(r'[\d][\d\-\.]+', prov)
        if nums:
            m = re.search(r'\b' + re.escape(nums.group(0)) + r'\b', text)
    if not m:
        return ''
    start = max(0, m.start() - 80)
    end = min(len(text), m.end() + 140)
    chunk = text[start:end].strip()
    lead = '…' if start > 0 else ''
    tail = '…' if end < len(text) else ''
    return lead + plain(chunk) + tail


# ── loaders ───────────────────────────────────────────────────────────────────

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as source:
        return json.load(source)

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding='utf-8') as source:
        for line in source:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ── case rows ─────────────────────────────────────────────────────────────────

def build_case_rows() -> list[dict]:
    """Project case relationships from the audited reverse index only."""
    taxonomy_by_num = {
        norm_case_num(c.get('case_id')): c
        for c in load_jsonl(os.path.join(IDX, 'judicial_cases.jsonl'))
        if c.get('case_id')
    }
    rows = []
    for item in load_json(os.path.join(IDX, 'case_provision_index.json')):
        provision = norm_prov(str(item.get('provision') or ''))
        url = str(item.get('url') or '')
        if not provision or not url.startswith('cases/'):
            continue
        case_numbers = [str(number) for number in (item.get('case_numbers') or []) if number]
        canonical_numbers = [norm_case_num(number) for number in case_numbers]
        canonical_cases = [taxonomy_by_num[number] for number in canonical_numbers if number in taxonomy_by_num]
        path_stem = os.path.splitext(os.path.basename(url.split('#', 1)[0]))[0]
        # Keep the relationship identity tied to the canonical case page. This
        # preserves existing editorial link assessments when the source index
        # changes its evidence without changing the case record itself.
        evidence = item.get('evidence') or []
        sources = item.get('sources') or []
        topics = next((case.get('topic_tags') for case in canonical_cases if case.get('topic_tags')), [])
        rows.append({
            'provision': provision,
            'type': 'Judicial case',
            'authority_weight': 'high',
            'title': item.get('title') or path_stem,
            'year': item.get('year'),
            'disposition': item.get('disposition') or '',
            'standard_of_review': item.get('standard_of_review'),
            'review_standards': item.get('review_standards') or [],
            'case_numbers': case_numbers,
            'record_id': f'case:cases/{path_stem}.md',
            'url': url,
            'snippet': evidence[0].get('snippet', '') if evidence else '',
            'topics': topics,
            'evidence': evidence,
            'evidence_sources': sources,
            'evidence_basis': 'direct_text' if evidence else 'structured_case_metadata',
            'relationship_kind': 'explicit_citation' if evidence else 'structured_case_reference',
            'match_method': 'case_provision_index:' + ','.join(sources),
            'match_confidence': 'high' if evidence else 'medium',
            'reader_scope': 'primary',
        })
    return rows


# ── inquiry rows ──────────────────────────────────────────────────────────────

def build_inquiry_rows() -> list[dict]:
    rows = []
    for r in load_json(os.path.join(IDX, 'inquiries_search.json')):
        if r.get('type') == 'ccb-advice':
            continue
        for prov in (r.get('provisions') or []):
            rows.append({
                'provision': prov,
                'type': 'Constitutional inquiry',
                'authority_weight': 'medium',
                'title': r['title'],
                'year': r.get('year'),
                'disposition': r.get('disposition', ''),
                'url': r['url'],
                'snippet': '',
                'summary': r.get('sub', ''),
                'topics': [],
                'evidence_basis': 'structured_provision_tag',
                'relationship_kind': 'structured_provision_tag',
                'match_method': 'index/inquiries_search.json:provisions',
                'match_confidence': 'medium',
                'reader_scope': 'primary',
            })
    return rows


# ── RPR rows ──────────────────────────────────────────────────────────────────

def build_rpr_rows() -> list[dict]:
    rows = []
    for r in load_json(os.path.join(IDX, 'rpr_search.json')):
        for prov in (r.get('provisions') or []):
            rows.append({
                'provision': norm_prov(prov),
                'type': 'RPR exception',
                'authority_weight': 'low-but-important',
                'title': f"{r['presbytery']}: {r['title']}",
                'year': r.get('year'),
                'disposition': r.get('disposition', ''),
                'url': r['url'],
                'snippet': '',
                'topics': [],
                'evidence_basis': 'structured_provision_tag',
                'relationship_kind': 'structured_exception_tag',
                'match_method': 'index/rpr_search.json:provisions',
                'match_confidence': 'medium',
                'reader_scope': 'contextual',
            })
    return rows


# ── overture rows ─────────────────────────────────────────────────────────────

def is_adopted_overture_action(outcome: str) -> bool:
    """Return true only for disposition text that records an affirmative action."""
    normalized = re.sub(r'\s+', ' ', (outcome or '').strip()).casefold()
    return bool(
        normalized in {
            'adopted', 'adopted (final)',
            'answered in the affirmative',
            'answered in the affirmative, as amended',
        }
        or re.fullmatch(r'approved\s*(?:&|and)\s*ratified(?:\s*\(\d{4}\))?', normalized)
    )

def build_overture_rows() -> list[dict]:
    """Project provision-bearing occurrences from the curated overture records."""
    from overture_catalogue import overture_records

    rows: list[dict] = []
    for record in overture_records(Path(IDX)):
        outcome = record.get('disposition') or ''
        adopted = is_adopted_overture_action(outcome)
        weight = 'medium' if adopted else 'low-but-important'
        for prov in (norm_prov(value) for value in record.get('provisions') or []):
            sources = (record.get('provision_sources') or {}).get(prov, [])
            target_sources = [source for source in sources
                              if source in {'disposition_bco', 'title_subject'}]
            direct_evidence = [item for item in record.get('provision_evidence') or []
                               if norm_prov(item.get('provision') or '') == prov and item.get('excerpt')]
            row = {
                'provision': prov,
                'type': 'Overture',
                'authority_weight': weight,
                'title': record['title'],
                'year': record.get('year'),
                'disposition': outcome,
                'url': record['url'],
                'record_id': record['record_id'],
                'snippet': '',
                'source': record.get('source', ''),
                'occurrence_number': record.get('number'),
                'occurrence_page': record.get('page'),
                'topics': [],
                'reader_scope': 'primary' if adopted else 'candidate',
            }
            if direct_evidence:
                for evidence in direct_evidence:
                    evidence_row = {
                        **row,
                        'url': evidence.get('url') or record['url'],
                        'occurrence_page': evidence.get('page') or record.get('page'),
                        'snippet': evidence['excerpt'],
                        'evidence_source': 'overture_body_text',
                        'evidence_basis': 'direct_text',
                        'relationship_kind': evidence.get('relationship_kind') or 'explicit_citation',
                        'match_method': evidence.get('match_method') or evidence.get('source') or 'overture_body_text',
                        'match_confidence': 'high',
                        'reader_scope': 'candidate',
                    }
                    rows.append(evidence_row)
            if target_sources or not direct_evidence:
                row.update({
                    'evidence_basis': 'overture_action_target' if 'disposition_bco' in target_sources else 'title_subject_reference',
                    'relationship_kind': 'proposal_target',
                    'match_method': ','.join(target_sources) if target_sources else 'index/OVERTURES.md:subject',
                    'match_confidence': 'high' if target_sources or record.get('title') else 'low',
                    'snippet': record.get('title', '') if 'title_subject' in target_sources or not target_sources else '',
                })
                rows.append(row)
    return rows


# ── markdown rendering ────────────────────────────────────────────────────────

_TYPE_ORDER = ['Judicial case', 'Constitutional inquiry', 'CCB advice', 'Overture', 'RPR exception']

def render_provision_page(prov: str, rows: list[dict]) -> str:
    lines = [f'# {prov}', '']
    lines.append(f'*Indexed PCA records associated with **{prov}**. Association type, evidence, and confidence are shown separately; this index does not assign legal force.*')
    lines.append('')
    lines.append('| Year | Record type | Relationship | Evidence | Confidence | Title | Disposition |')
    lines.append('|------|-------------|--------------|----------|------------|-------|-------------|')
    for r in sorted(rows, key=lambda r: (
            _TYPE_ORDER.index(r['type']) if r['type'] in _TYPE_ORDER else 9,
            -(r.get('year') or 0), r.get('title', '').casefold())):
        year = str(r['year']) if r['year'] else '—'
        title = md_escape(r['title'])
        url_rel = f'../{r["url"]}'
        disp = md_escape(r.get('disposition') or '')
        evidence = md_escape(r.get('evidence_basis') or '')
        kind = md_escape(r.get('relationship_kind') or '')
        confidence = md_escape(r.get('match_confidence') or '')
        lines.append(f'| {year} | {r["type"]} | {kind} | {evidence} | {confidence} | [{title}]({url_rel}) | {disp} |')
    lines.append('')

    lines.append('---')
    lines.append(f'*[← Authority Index](../index/AUTHORITY-BY-PROVISION.md)*')
    return '\n'.join(lines) + '\n'


def render_main_index(rows_by_prov: dict[str, list[dict]]) -> str:
    sorted_provs = sorted(rows_by_prov.keys(), key=prov_sort_key)
    lines = [
        '# Authority Index by Constitutional Provision',
        '',
        'Indexed PCA records associated with each provision. Relationship type, evidence, and confidence are separate fields; the legacy display rank does not establish legal force.',
        '',
        '| Provision | Cases | Inquiries | CCB advice | Overtures | RPR exceptions | Total |',
        '|-----------|------:|----------:|-----------:|----------:|---------------:|------:|',
    ]
    for prov in sorted_provs:
        rows = rows_by_prov[prov]
        n_cases = sum(1 for r in rows if r['type'] == 'Judicial case')
        n_inq   = sum(1 for r in rows if r['type'] == 'Constitutional inquiry')
        n_ccb   = sum(1 for r in rows if r['type'] == 'CCB advice')
        n_ovr   = sum(1 for r in rows if r['type'] == 'Overture')
        n_rpr   = sum(1 for r in rows if r['type'] == 'RPR exception')
        total   = len(rows)
        slug    = prov_slug(prov)
        lines.append(
            f'| [{prov}](../authorities/{slug}.md) '
            f'| {n_cases} | {n_inq} | {n_ccb} | {n_ovr} | {n_rpr} | {total} |'
        )

    lines.append('')
    lines.append(f'*{len(sorted_provs)} provisions indexed.*')
    return '\n'.join(lines) + '\n'


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    from provision_catalogue import authority_projection, load_catalogue

    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    catalogue_path = os.path.join(root, 'index', 'provision_catalogue.json')
    catalogue = load_catalogue(Path(catalogue_path))
    all_rows: list[dict] = authority_projection(catalogue)
    print(f'[{root}] Projecting {len(all_rows)} authority rows from the provision catalogue…')

    # Sort: provision -> weight -> type -> year
    all_rows.sort(key=lambda r: (
        prov_sort_key(r['provision']),
        _TYPE_ORDER.index(r['type']) if r['type'] in _TYPE_ORDER else 9,
        -(r.get('year') or 0),
    ))

    # Write flat index
    out_json = os.path.join(IDX, 'authority_index.json')
    json.dump(all_rows, open(out_json, 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print(f'  → index/authority_index.json: {len(all_rows)} catalogue projection rows')

    # Group by provision
    rows_by_prov: dict[str, list[dict]] = {}
    for r in all_rows:
        rows_by_prov.setdefault(r['provision'], []).append(r)

    # Write AUTHORITY-BY-PROVISION.md
    out_md = os.path.join(IDX, 'AUTHORITY-BY-PROVISION.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write(render_main_index(rows_by_prov))
    print(f'  → index/AUTHORITY-BY-PROVISION.md: {len(rows_by_prov)} provisions')

    # Write per-provision pages
    os.makedirs(AUTH_DIR, exist_ok=True)
    expected_pages = set()
    n_pages = 0
    for prov, prows in rows_by_prov.items():
        slug = prov_slug(prov)
        path = os.path.join(AUTH_DIR, slug + '.md')
        expected_pages.add(os.path.normcase(os.path.abspath(path)))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(render_provision_page(prov, prows))
        n_pages += 1
    for filename in os.listdir(AUTH_DIR):
        path = os.path.join(AUTH_DIR, filename)
        if (filename.lower().endswith('.md') and os.path.isfile(path)
                and os.path.normcase(os.path.abspath(path)) not in expected_pages):
            os.remove(path)
    print(f'  → authorities/: {n_pages} provision pages')

    by_type = collections.Counter(r['type'] for r in all_rows)
    by_weight = collections.Counter(r['authority_weight'] for r in all_rows)
    print(f'  types:   {dict(by_type)}')
    print(f'  weights: {dict(by_weight)}')


if __name__ == '__main__':
    main()
