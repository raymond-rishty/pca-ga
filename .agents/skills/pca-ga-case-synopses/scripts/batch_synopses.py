"""Resumable editorial checkpoints. Standard library only; no production writes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import tempfile

ROOT = Path(__file__).resolve().parents[4]
CATALOG = 'index/judicial_cases.jsonl'
BENCHMARK = 'docs/JUDICIAL-SYNOPSIS-BENCHMARKS.md'
DIMENSIONS = ('concrete_dispute', 'decision', 'decisive_reason',
              'distinctive_value', 'fidelity', 'economy')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def catalog(root):
    result = {}
    for line in (root / CATALOG).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = row.get('case_id') or 'roster:' + str(row['roster_id'])
        if key in result:
            raise ValueError('Duplicate docket: ' + key)
        result[key] = row
    return result


def source_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Source must be an existing repository file: ' + name)
    return path


def fresh(root, entry, rows):
    if entry['catalog_hash'] != digest(rows.get(entry['key'])):
        return False
    evidence = entry.get('evidence')
    if not evidence:
        return True
    if evidence['benchmark_hash'] != file_hash(root / BENCHMARK):
        return False
    try:
        return all(file_hash(source_path(root, s['path'])) == s['sha256']
                   for s in evidence['sources'])
    except (ValueError, OSError):
        return False


def state(root, entry, rows):
    return entry['stage'] if fresh(root, entry, rows) else 'stale'


def sync(ledger, rows):
    for key, row in rows.items():
        if key not in ledger['cases']:
            ledger['cases'][key] = {
                'key': key, 'case_id': row.get('case_id'),
                'roster_id': row.get('roster_id'), 'title': row.get('title'),
                'case_page': row.get('case_page'),
                'matter_type': row.get('matter_type'),
                'final_dispositions': row.get('final_dispositions'),
                'catalog_hash': digest(row), 'stage': 'queued', 'history': []}


def require_text(payload, *keys):
    for key in keys:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError('Nonempty text required: ' + key)


def record(root, ledger, rows, key, action, payload):
    entry = ledger['cases'][key]
    require_text(payload, 'reviewer', 'notes')
    current = state(root, entry, rows)
    if action not in ('triage', 'repair') and current == 'stale':
        raise ValueError('Inputs changed; repeat triage before continuing')
    if action == 'repair':
        entry['stage'] = 'repair_needed'
        entry['repair'] = payload
    elif action == 'triage':
        sources = payload.get('sources', [])
        if not sources or key not in rows:
            raise ValueError('Triage needs source evidence and an extant docket')
        checked = []
        for source in sources:
            require_text(source, 'path', 'locator', 'supports')
            checked.append(dict(source, sha256=file_hash(source_path(root, source['path']))))
        require_text(payload, 'identity', 'source_limits')
        entry['evidence'] = dict(payload, sources=checked,
                                 benchmark_hash=file_hash(root / BENCHMARK))
        entry['catalog_hash'] = digest(rows[key])
        for field in ('draft', 'verification', 'approval', 'repair'):
            entry.pop(field, None)
        entry['stage'] = 'ready'
    elif action == 'draft':
        if current not in ('ready', 'drafted', 'verified', 'approved'):
            raise ValueError('Draft requires completed triage and no repair blocker')
        require_text(payload, 'summary', 'benchmark_examples')
        entry['draft'] = payload
        entry.pop('verification', None)
        entry.pop('approval', None)
        entry['stage'] = 'drafted'
    elif action == 'verify':
        if current != 'drafted':
            raise ValueError('Verification requires a draft')
        require_text(payload, 'claim_checks', 'qualifications', 'pass_kind')
        if payload['pass_kind'] not in ('separate_pass_same_reviewer', 'independent_reviewer'):
            raise ValueError('Identify the actual verification pass')
        scores = payload.get('scores', {})
        if set(scores) != set(DIMENSIONS) or any(type(v) is not int or v not in (0, 1, 2) for v in scores.values()):
            raise ValueError('Supply all six rubric scores, each an integer 0–2')
        if payload.get('passed') is not True or scores['fidelity'] != 2:
            raise ValueError('Revise or queue repair: verification has not passed')
        if payload['pass_kind'] == 'independent_reviewer' and payload['reviewer'] == entry['draft']['reviewer']:
            raise ValueError('An independent reviewer must differ from the drafter')
        entry['verification'] = dict(payload, draft_hash=digest(entry['draft']))
        entry['stage'] = 'verified'
    elif action == 'approve':
        if current != 'verified':
            raise ValueError('Approval requires source verification')
        require_text(payload, 'authorization')
        entry['approval'] = payload
        entry['stage'] = 'approved'
    else:
        raise ValueError('Unknown action')
    entry['history'].append({'at': datetime.now(timezone.utc).isoformat(),
                             'action': action, 'payload': payload})


def packet(root, ledger, rows, keys):
    overrides = read(root / 'index/judicial_case_editorial_overrides.json')
    result = {}
    for key in keys:
        entry = ledger['cases'][key]
        if state(root, entry, rows) != 'approved' or not entry['case_id']:
            raise ValueError('Export requires a fresh, approved canonical docket: ' + key)
        if entry['verification']['draft_hash'] != digest(entry['draft']):
            raise ValueError('Draft changed after verification: ' + key)
        before = overrides.get(key)
        after = dict(before or {}, summary=entry['draft']['summary'],
                     summary_review_status='audited',
                     summary_audit_basis='source-checked-synopsis-workflow-v1')
        result[key] = {'before': before, 'after': after,
                       'evidence': entry['evidence'], 'approval': entry['approval']}
    return {'notice': 'Review packet only; not applied or published.',
            'catalog_before': rows, 'changes': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--ledger', type=Path, default=Path('index/synopsis_workflow/ledger.json'))
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'sync', 'status'):
        sub.add_parser(name)
    nxt = sub.add_parser('next')
    nxt.add_argument('--stage', default='queued')
    nxt.add_argument('--limit', type=int, default=15)
    rec = sub.add_parser('record')
    rec.add_argument('action', choices=('triage', 'draft', 'verify', 'approve', 'repair'))
    rec.add_argument('--case', required=True)
    rec.add_argument('--input', required=True, type=Path)
    exp = sub.add_parser('export')
    exp.add_argument('--cases', nargs='+', required=True)
    exp.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    path = root / args.ledger
    # Single-writer lock prevents accidental overlapping ledger mutations.
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix('.lock')
    try:
        with lock.open('x'):
            pass
    except FileExistsError:
        parser.error('Ledger is locked; check for another writer before removing ' + str(lock))
    try:
        rows = catalog(root)
        if args.command == 'init':
            if path.exists():
                raise ValueError('Ledger exists; use sync or resume')
            ledger = {'schema_version': 1, 'cases': {}}
            sync(ledger, rows)
            save(path, ledger)
        else:
            ledger = read(path)
            if ledger.get('schema_version') != 1:
                raise ValueError('Unsupported ledger schema')
            if args.command == 'sync':
                sync(ledger, rows)
                save(path, ledger)
            elif args.command == 'record':
                record(root, ledger, rows, args.case, args.action, read(args.input))
                save(path, ledger)
            elif args.command == 'next':
                if args.limit < 1:
                    raise ValueError('Limit must be positive')
                eligible = [e for e in ledger['cases'].values() if state(root, e, rows) == args.stage]
                eligible.sort(key=lambda e: (e.get('case_page') or e['key'], e['key']))
                print(json.dumps(eligible[:args.limit], ensure_ascii=False, indent=2))
            elif args.command == 'export':
                if args.out.exists():
                    raise ValueError('Output exists; choose a new packet name')
                save(args.out, packet(root, ledger, rows, args.cases))
        print(json.dumps(dict(Counter(state(root, e, rows) for e in ledger['cases'].values()))))
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
