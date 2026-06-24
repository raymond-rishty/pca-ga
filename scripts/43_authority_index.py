#!/usr/bin/env python3
"""43_authority_index.py — build per-provision authority index.

Generates:
  index/authority_index.json      flat list: one row per (provision, authority)
  index/AUTHORITY-BY-PROVISION.md cross-reference: each provision -> all authorities
  authorities/<slug>.md           per-provision detail pages

Authority weights:
  high              SJC/CJB judicial cases
  medium            constitutional inquiries; adopted overtures
  low-but-important RPR exceptions; non-adopted overtures

Usage: 43_authority_index.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import collections, json, os, re, sys

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
    return s

def extract_provisions(text: str) -> list[str]:
    return sorted({norm_prov(m.group(0)) for m in _PROV_RE.finditer(text)})

def norm_case_num(n: str) -> str:
    """'1990-08' -> '1990-8' to match cases.jsonl format."""
    m = re.match(r'^(\d{4})-(\d+)([a-z]?)$', str(n))
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}" if m else str(n)


# ── provision sort key ────────────────────────────────────────────────────────

_STD_RANK = {'BCO': 0, 'WCF': 1, 'WLC': 2, 'WSC': 3, 'RAO': 4}
_WEIGHT_RANK = {'high': 0, 'medium': 1, 'low-but-important': 2}

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

def snippet_for(text: str, prov: str, ctx: int = 220) -> str:
    m = re.search(re.escape(prov), text, re.I)
    if not m:
        nums = re.search(r'[\d][\d\-\.]+', prov)
        if nums:
            m = re.search(r'\b' + re.escape(nums.group(0)) + r'\b', text)
    if not m:
        return plain(text[:ctx])
    start = max(0, m.start() - 80)
    end = min(len(text), m.end() + 140)
    chunk = text[start:end].strip()
    lead = '…' if start > 0 else ''
    tail = '…' if end < len(text) else ''
    return lead + plain(chunk) + tail


# ── loaders ───────────────────────────────────────────────────────────────────

def load_json(path):
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# ── case rows ─────────────────────────────────────────────────────────────────

def build_case_rows() -> list[dict]:
    cases_by_num: dict[str, dict] = {}
    for c in load_jsonl(os.path.join(IDX, 'cases.jsonl')):
        num = c.get('case_number')
        if num:
            cases_by_num[norm_case_num(num)] = c

    cmap: dict = {}
    p = os.path.join(IDX, 'case_pages_map.json')
    if os.path.exists(p):
        cmap = json.load(open(p, encoding='utf-8'))

    rows = []
    seen_files: set[str] = set()

    for num, entry in cmap.items():
        fname = entry['file']
        if fname in seen_files:
            continue
        seen_files.add(fname)

        # Collect BCO provisions and metadata from all cases.jsonl entries for this file
        provs: set[str] = set()
        disposition = ''
        year: int | None = None
        topics: list[str] = []

        for n in entry.get('numbers', [num]):
            c = cases_by_num.get(norm_case_num(n))
            if not c:
                continue
            for b in (c.get('bco_cited_as') or []):
                if re.match(r'^[\d]', b):           # skip "Preface II-(7)" etc.
                    provs.add(f'BCO {b}')
            if not disposition and c.get('disposition'):
                disposition = c['disposition']
            if not year and c.get('year'):
                year = c['year']
            if not topics and c.get('topics'):
                topics = c['topics']

        # Fallback year from case number or vol
        if not year:
            m = re.match(r'(\d{4})', num or '')
            year = int(m.group(1)) if m else None
        if not year:
            m = re.match(r'ga\d+_(\d{4})', fname)
            year = int(m.group(1)) if m else None

        # Parse markdown for WCF/WLC/WSC/RAO and additional BCO refs not in cases.jsonl
        raw_text = ''
        md_path = os.path.join(CASES_DIR, fname + '.md')
        if os.path.exists(md_path):
            raw_text = open(md_path, encoding='utf-8').read()
            for prov in extract_provisions(raw_text):
                provs.add(prov)
            if not disposition:
                dm = re.search(r'\*\*Disposition:\*\*\s*([^\s·\n]+)', raw_text)
                if dm:
                    disposition = dm.group(1)

        if not provs:
            continue

        title = entry.get('title') or num
        url = f'cases/{fname}.md'

        for prov in sorted(provs, key=prov_sort_key):
            rows.append({
                'provision': prov,
                'type': 'Judicial case',
                'authority_weight': 'high',
                'title': title,
                'year': year,
                'disposition': disposition or '',
                'url': url,
                'snippet': snippet_for(raw_text, prov) if raw_text else '',
                'topics': topics,
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
                'snippet': r.get('sub', ''),
                'topics': [],
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
                'snippet': r['title'],
                'topics': [],
            })
    return rows


# ── overture rows ─────────────────────────────────────────────────────────────

_OVR_HEAD = re.compile(r'^##\s+.*General Assembly\s*\((\d{4})\)')
_OVR_LINK = re.compile(r'\]\(\.\./([^)#]+(?:#[^)]+)?)\)')
_OVR_PROV = re.compile(r'BCO\s+\d+-\d+(?:\.[0-9a-z]+)*', re.I)
_ADOPTED_WORDS = {'adopted', 'approved', 'ratified', 'passed', 'sustained'}

def build_overture_rows() -> list[dict]:
    p = os.path.join(IDX, 'OVERTURES.md')
    if not os.path.exists(p):
        return []
    rows: list[dict] = []
    year: int | None = None
    for line in open(p, encoding='utf-8'):
        h = _OVR_HEAD.match(line)
        if h:
            year = int(h.group(1))
            continue
        if not line.startswith('| '):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        num, subject, outcome, source, pages = cells[0], cells[1], cells[2], cells[3], cells[4]
        if not subject:
            continue
        matched = _OVR_PROV.findall(subject)
        if not matched:
            continue
        lm = _OVR_LINK.search(pages)
        url = lm.group(1) if lm else 'index/OVERTURES.md'
        weight = ('medium'
                  if any(w in (outcome or '').lower() for w in _ADOPTED_WORDS)
                  else 'low-but-important')
        provs = sorted({norm_prov(m) for m in matched})
        for prov in provs:
            rows.append({
                'provision': prov,
                'type': 'Overture',
                'authority_weight': weight,
                'title': subject,
                'year': year,
                'disposition': outcome,
                'url': url,
                'snippet': subject,
                'topics': [],
            })
    return rows


# ── markdown rendering ────────────────────────────────────────────────────────

_TYPE_ORDER = ['Judicial case', 'Constitutional inquiry', 'Overture', 'RPR exception']
_WEIGHT_LABEL = {
    'high': 'High authority',
    'medium': 'Medium authority',
    'low-but-important': 'Low-but-important',
}

def render_provision_page(prov: str, rows: list[dict]) -> str:
    lines = [f'# {prov}', '']
    lines.append(f'*All PCA authorities bearing on **{prov}**.*')
    lines.append('')

    by_weight: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: (
            _WEIGHT_RANK.get(r['authority_weight'], 9),
            _TYPE_ORDER.index(r['type']) if r['type'] in _TYPE_ORDER else 9,
            r.get('year') or 0)):
        by_weight.setdefault(r['authority_weight'], []).append(r)

    for weight in ['high', 'medium', 'low-but-important']:
        weight_rows = by_weight.get(weight)
        if not weight_rows:
            continue
        lines.append(f'## {_WEIGHT_LABEL[weight]}')
        lines.append('')
        lines.append('| Year | Type | Title | Disposition |')
        lines.append('|------|------|-------|-------------|')
        for r in weight_rows:
            year = str(r['year']) if r['year'] else '—'
            title = md_escape(r['title'])
            url_rel = f'../{r["url"]}'
            disp = md_escape(r.get('disposition') or '')
            rtype = r['type']
            lines.append(f'| {year} | {rtype} | [{title}]({url_rel}) | {disp} |')
        lines.append('')

    lines.append('---')
    lines.append(f'*[← Authority Index](../index/AUTHORITY-BY-PROVISION.md)*')
    return '\n'.join(lines) + '\n'


def render_main_index(rows_by_prov: dict[str, list[dict]]) -> str:
    sorted_provs = sorted(rows_by_prov.keys(), key=prov_sort_key)
    lines = [
        '# Authority Index by Constitutional Provision',
        '',
        'Every PCA authority (judicial cases, constitutional inquiries, RPR exceptions, overtures)'
        ' bearing on each BCO / Westminster Standards / RAO provision.',
        '',
        '| Provision | Cases | Inquiries | Overtures | RPR exceptions | Total |',
        '|-----------|------:|----------:|----------:|---------------:|------:|',
    ]
    for prov in sorted_provs:
        rows = rows_by_prov[prov]
        n_cases = sum(1 for r in rows if r['type'] == 'Judicial case')
        n_inq   = sum(1 for r in rows if r['type'] == 'Constitutional inquiry')
        n_ovr   = sum(1 for r in rows if r['type'] == 'Overture')
        n_rpr   = sum(1 for r in rows if r['type'] == 'RPR exception')
        total   = len(rows)
        slug    = prov_slug(prov)
        lines.append(
            f'| [{prov}](../authorities/{slug}.md) '
            f'| {n_cases} | {n_inq} | {n_ovr} | {n_rpr} | {total} |'
        )

    lines.append('')
    lines.append(f'*{len(sorted_provs)} provisions indexed.*')
    return '\n'.join(lines) + '\n'


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f'[{ROOT}] Building authority index…')

    all_rows: list[dict] = []
    print('  cases…', end=' ', flush=True)
    case_rows = build_case_rows()
    print(len(case_rows))
    all_rows.extend(case_rows)

    print('  inquiries…', end=' ', flush=True)
    inq_rows = build_inquiry_rows()
    print(len(inq_rows))
    all_rows.extend(inq_rows)

    print('  RPR exceptions…', end=' ', flush=True)
    rpr_rows = build_rpr_rows()
    print(len(rpr_rows))
    all_rows.extend(rpr_rows)

    print('  overtures…', end=' ', flush=True)
    ovr_rows = build_overture_rows()
    print(len(ovr_rows))
    all_rows.extend(ovr_rows)

    # Sort: provision -> weight -> type -> year
    all_rows.sort(key=lambda r: (
        prov_sort_key(r['provision']),
        _WEIGHT_RANK.get(r['authority_weight'], 9),
        _TYPE_ORDER.index(r['type']) if r['type'] in _TYPE_ORDER else 9,
        r.get('year') or 0,
    ))

    # Write flat index
    out_json = os.path.join(IDX, 'authority_index.json')
    json.dump(all_rows, open(out_json, 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print(f'  → index/authority_index.json: {len(all_rows)} rows')

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
    n_pages = 0
    for prov, prows in rows_by_prov.items():
        slug = prov_slug(prov)
        path = os.path.join(AUTH_DIR, slug + '.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(render_provision_page(prov, prows))
        n_pages += 1
    print(f'  → authorities/: {n_pages} provision pages')

    by_type = collections.Counter(r['type'] for r in all_rows)
    by_weight = collections.Counter(r['authority_weight'] for r in all_rows)
    print(f'  types:   {dict(by_type)}')
    print(f'  weights: {dict(by_weight)}')


if __name__ == '__main__':
    main()
