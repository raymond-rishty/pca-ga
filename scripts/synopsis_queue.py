"""Budget-gated preparation/checkpoint queue; no model calls or production writes.

An orchestrator supplies fresh account snapshots and dispatches one Sol worker.
Queue state is intentionally separate from editorial approval in the existing ledger.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'synopsis_ledger', ROOT / '.agents/skills/pca-ga-case-synopses/scripts/batch_synopses.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)
REFERENCES = [
    '.agents/skills/pca-ga-case-synopses/SKILL.md',
    '.agents/skills/pca-ga-case-synopses/references/batch-workflow.md',
    '.agents/skills/pca-ga-case-synopses/references/requirements-and-trial.md',
    'docs/JUDICIAL-SYNOPSIS-BENCHMARKS.md', 'docs/JUDICIAL-CASE-TAXONOMY.md',
    '.agents/skills/pca-ga-case-synopses/references/compact-runtime-contract.md']


def now():
    return datetime.now(timezone.utc).isoformat()


def inside(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path outside workspace: ' + str(name))
    return path


@contextmanager
def locked(folder):
    lock = folder / '.queue.lock'
    stream = lock.open('x')
    try:
        yield
    finally:
        stream.close()
        lock.unlink()


def exclusions(root):
    files = [root / REFERENCES[3]]
    files += [p for p in (root / 'index/synopsis_workflow').rglob('*.md')
              if p.name in ('assignment.md', 'audit.md', 'review.md')]
    ids = set()
    for path in files:
        ids.update(re.findall(r'\b\d{4}-\d{2}[a-z]?\b', path.read_text(encoding='utf-8')))
    return ids


def existing_sol(root):
    """Discover drafts from recorded Sol runs, not model guesses or filenames alone.

Older trial schemas remain usable drafts. Stale evidence means review, never an
automatic redraft. Multiple candidates are retained without selecting a winner.
"""
    workflow = root / 'index/synopsis_workflow'
    directories = {}
    for manifest in workflow.rglob('runs.json'):
        for arm in ledger.read(manifest).get('arms', []):
            if arm.get('model') == 'gpt-5.6-sol' and arm.get('output_directory'):
                directories[inside(root, arm['output_directory'])] = manifest
    for manifest in workflow.rglob('queue.json'):
        campaign = ledger.read(manifest)
        if campaign.get('model') == 'gpt-5.6-sol':
            for directory in manifest.parent.glob('batch-*/final'):
                directories[directory] = manifest
    found = {}
    for directory, manifest in directories.items():
        for path in sorted(directory.glob('*.json')):
            if not re.fullmatch(r'\d{4}-\d{2}[a-z]?', path.stem):
                continue
            try:
                body = ledger.read(path)
                if body.get('case_id') != path.stem or not isinstance(body.get('summary'), str) or not body['summary'].strip():
                    continue
            except (ValueError, OSError, AttributeError):
                continue
            evidence = body.get('sources') or []
            fresh = bool(evidence)
            for source in evidence:
                try:
                    fresh = fresh and ledger.file_hash(ledger.source_path(root, source['path'])) == source['sha256']
                except (ValueError, KeyError, OSError, TypeError):
                    fresh = False
            found.setdefault(path.stem, []).append({
                'path': path.relative_to(root).as_posix(), 'sha256': ledger.file_hash(path),
                'provenance': manifest.relative_to(root).as_posix(),
                'source_hashes_match': fresh,
                'status': 'existing_draft_requires_review', 'publication_approved': False})
    return found


def inventory_sol(root):
    found = existing_sol(root)
    result = {'unique_cases': len(found), 'candidate_count': sum(map(len, found.values())),
              'policy': 'Reuse existing Sol drafts; audit/repair separately. No automatic approval or redrafting.',
              'cases': found}
    ledger.save(root / 'index/synopsis_workflow/existing-sol.json', result)
    return result


def light_screen(root):
    """Candidate discovery only; catalog labels and size never authorize routing."""
    rows = ledger.catalog(root)
    result = []
    for key, row in rows.items():
        if row.get('final_dispositions') not in (['withdrawn'], ['abandoned']) or not row.get('case_page'):
            continue
        path = root / ('cases/' + row['case_page'] + '.md')
        if not path.is_file() or path.stat().st_size >= 1600:
            continue
        result.append({'case_id': key, 'path': path.relative_to(root).as_posix(),
                       'sha256': ledger.file_hash(path), 'bytes': path.stat().st_size,
                       'provisional_catalog_dispositions': row['final_dispositions'],
                       'eligibility': 'unreviewed', 'model_route': None})
    return {'description': 'Upper-bound discovery pool, not eligible/approved routing. '
            'Verify source identity, vehicle, finality, per-docket mapping and qualifications.',
            'count': len(result), 'candidates': result}


def prepare(root, folder, selection):
    if folder.exists():
        raise ValueError('Refusing to overwrite campaign')
    rows = ledger.catalog(root)
    ids = selection['case_ids']
    if len(ids) != 15 or len(set(ids)) != 15:
        raise ValueError('Calibration requires 15 distinct canonical dockets')
    excluded = exclusions(root) | set(existing_sol(root))
    prior_pages = {row.get('case_page') for key, row in rows.items() if key in excluded}
    base = ledger.read(root / 'index/synopsis_workflow/ledger.json')
    entries = []
    for key in ids:
        row = rows[key]
        if key in excluded or row.get('case_page') in prior_pages:
            raise ValueError('Previously reviewed docket or shared source: ' + key)
        if base['cases'].get(key, {}).get('stage', 'queued') != 'queued':
            raise ValueError('Existing editorial work: ' + key)
        path = ledger.source_path(root, 'cases/' + row['case_page'] + '.md')
        entries.append({'case_id': key, 'path': path.relative_to(root).as_posix(),
                        'sha256': ledger.file_hash(path), 'bytes': path.stat().st_size,
                        'catalog_hash': ledger.digest(row), 'state': 'queued'})
    refs = {p: ledger.file_hash(root / p) for p in REFERENCES}
    folder.mkdir(parents=True)
    batches, current, size = [], [], 0
    for entry in entries:
        if current and (len(current) == 5 or size + entry['bytes'] > 120000):
            batches.append(current)
            current, size = [], 0
        current.append(entry['case_id'])
        size += entry['bytes']
    if current:
        batches.append(current)
    packet_hashes = {}
    for number, keys in enumerate(batches, 1):
        target = folder / f'batch-{number:02d}'
        target.mkdir()
        packet = []
        seen = set()
        for entry in entries:
            if entry['case_id'] in keys and entry['path'] not in seen:
                seen.add(entry['path'])
                source = root / entry['path']
                packet.append(f"\n## SOURCE {entry['path']} SHA256 {entry['sha256']}\n")
                packet.extend(f'{i}: {line}' for i, line in enumerate(
                    source.read_text(encoding='utf-8').splitlines(), 1))
        (target / 'sources.txt').write_text('\n'.join(packet) + '\n', encoding='utf-8')
        prompt = (
            'Use pca-ga-case-synopses, including batch workflow and trial contract. '
            'Read its required references and only applicable benchmark examples.\n'
            f'Assigned canonical IDs: {", ".join(keys)}. Read sources.txt in this folder; '
            'it preserves full case pages with original line numbers. Generated headers '
            'and catalog metadata are not authority. Source-check identities and boundaries. '
            'Follow incorporated decisions in the repository; if unavailable, report a blocker.\n'
            'Do not read prior model outputs or audit answers. Draft from the sources. '
            'Save first-drafts/ID.json BEFORE reopening the operative judgment/reasoning '
            'for a separate same-reviewer check. Save final/ID.json after that check. '
            'Use the full structured trial contract, plus first_summary in the final record. '
            'Keep evidence and score reasons concise but case-specific. Preserve all material '
            'outcomes and qualifications; short notices should remain short. '
            'Record actual corrections, not generic verification assertions.\n'
            'Checkpoint each docket. Write only inside this batch folder; do not change '
            'production metadata, the editorial ledger, skill files, or case text. '
            'No publication, commits, additional agents, or repeated polishing cycles. '
            'If a source/catalog defect blocks completion, save blocked/ID.json with '
            'case_id, source location, and explanation. Record start/end times and any '
            'actual usage in run-notes.md; unavailable usage must remain unknown.\n')
        (target / 'prompt.txt').write_text(prompt, encoding='utf-8')
        for name in ('sources.txt', 'prompt.txt'):
            packet_hashes[(target / name).relative_to(folder).as_posix()] = ledger.file_hash(target / name)
    data = {'schema_version': 1, 'created_at': now(), 'model': 'gpt-5.6-sol',
            'reasoning_effort': 'medium', 'publication_authorized': False,
            'reserve_percent': 20, 'max_snapshot_age_seconds': 300,
            'max_account_percentage_points': 10,
            'selection_notes': selection['notes'], 'reference_hashes': refs,
            'packet_hashes': packet_hashes,
            'cases': entries, 'batches': batches, 'runs': []}
    ledger.save(folder / 'queue.json', data)
    return data


def gate(data, snapshot, current_time=None):
    current_time = current_time or datetime.now(timezone.utc)
    try:
        captured = datetime.fromisoformat(snapshot['captured_at'])
        age = (current_time - captured).total_seconds()
        if age < 0 or age > data['max_snapshot_age_seconds']:
            return 'paused: stale usage snapshot'
        limits = snapshot['rateLimitsByLimitId']['codex']
        if limits.get('spendControlReached') or limits.get('rateLimitReachedType'):
            return 'paused: account limit reached'
        for key in ('primary', 'secondary'):
            window = limits[key]
            used = window['usedPercent']
            if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used) or not 0 <= used <= 100:
                return 'paused: invalid usage'
            if window['resetsAt'] <= current_time.timestamp():
                return 'paused: snapshot requires refresh after reset'
            if 100 - used <= data['reserve_percent']:
                return f'paused: {key} reserve'
        consumed = 0
        for run in data['runs']:
            if 'after' not in run:
                return 'paused: unfinished run'
            before = run['before']['rateLimitsByLimitId']['codex']['primary']
            after = run['after']['rateLimitsByLimitId']['codex']['primary']
            if before['resetsAt'] != after['resetsAt'] or after['usedPercent'] < before['usedPercent']:
                return 'paused: usage crossed reset; manual budget review required'
            consumed += after['usedPercent'] - before['usedPercent']
        if consumed >= data['max_account_percentage_points']:
            return 'paused: calibration allowance budget reached'
    except (KeyError, TypeError, ValueError):
        return 'paused: missing or invalid usage snapshot'
    return 'ready'


def freshness(root, folder, data):
    rows = ledger.catalog(root)
    for name, digest in data['packet_hashes'].items():
        if ledger.file_hash(ledger.source_path(folder, name)) != digest:
            raise ValueError('Stale packet: ' + name)
    for path, digest in data['reference_hashes'].items():
        if ledger.file_hash(ledger.source_path(root, path)) != digest:
            raise ValueError('Stale reference: ' + path)
    for entry in data['cases']:
        if ledger.file_hash(ledger.source_path(root, entry['path'])) != entry['sha256']:
            raise ValueError('Stale source: ' + entry['case_id'])
        if ledger.digest(rows.get(entry['case_id'])) != entry['catalog_hash']:
            raise ValueError('Stale catalog: ' + entry['case_id'])


def validate_candidate(root, key, body, first):
    """Structural checks only; never certify semantic correctness."""
    for field in ('title', 'disposition_detail', 'summary', 'source_limits'):
        ledger.require_text(body, field)
    if body.get('case_id') != key or first.get('case_id') != key:
        raise ValueError('Candidate/first-draft identity mismatch: ' + key)
    ledger.require_text(first, 'summary')
    if body.get('first_summary') != first['summary']:
        raise ValueError('First draft not preserved: ' + key)
    taxonomy = (root / REFERENCES[4]).read_text(encoding='utf-8')
    matter_section = taxonomy.split('## Matter types')[1].split('## Final dispositions')[0]
    disposition_section = taxonomy.split('## Final dispositions')[1].split('## Metadata facets')[0]
    codes = lambda section: set(re.findall(r'^\| `([^`]+)` \|', section, re.M))
    if body.get('matter_type') not in codes(matter_section):
        raise ValueError('Invalid matter type: ' + key)
    dispositions = body.get('final_dispositions')
    if not isinstance(dispositions, list) or not dispositions or any(
            not isinstance(d, str) or d not in codes(disposition_section) for d in dispositions
    ) or len(dispositions) != len(set(dispositions)):
        raise ValueError('Invalid dispositions: ' + key)
    for field in ('scores', 'score_reasons', 'evidence_notes'):
        if not isinstance(body.get(field), dict) or not body[field]:
            raise ValueError('Missing structured field: ' + field)
    for dimension in ledger.DIMENSIONS:
        score = body['scores'].get(dimension)
        if type(score) is not int or score not in (0, 1, 2):
            raise ValueError('Invalid rubric score: ' + dimension)
        ledger.require_text(body['score_reasons'], dimension)
    if not isinstance(body.get('benchmark_examples'), list) or not body['benchmark_examples']:
        raise ValueError('Missing benchmark examples')
    if not body.get('verification_notes') or type(body.get('repair_needed')) is not bool:
        raise ValueError('Missing verification/repair status')
    if not isinstance(body.get('repair_notes'), str):
        raise ValueError('Missing repair notes')
    if not isinstance(body.get('sources'), list) or not body['sources']:
        raise ValueError('Missing sources')
    for source in body['sources']:
        ledger.require_text(source, 'path', 'sha256', 'locator', 'supports')
        if ledger.file_hash(ledger.source_path(root, source['path'])) != source['sha256']:
            raise ValueError('Stale candidate evidence: ' + source['path'])


def claim(root, folder, snapshot, max_cases=None):
    with locked(folder):
        data = ledger.read(folder / 'queue.json')
        prior = existing_sol(root)
        for entry in data['cases']:
            if entry['state'] == 'queued' and entry['case_id'] in prior:
                entry['state'] = 'existing_draft_requires_review'
                entry['existing_candidates'] = prior[entry['case_id']]
        ledger.save(folder / 'queue.json', data)
        freshness(root, folder, data)
        status = gate(data, snapshot)
        if status != 'ready':
            return {'status': status}
        queued = {e['case_id'] for e in data['cases'] if e['state'] == 'queued'}
        for number, keys in enumerate(data['batches'], 1):
            pending = [key for key in keys if key in queued]
            if max_cases is not None:
                pending = pending[:max_cases]
            if pending:
                run = {'batch': number, 'case_ids': pending, 'before': snapshot,
                       'started_at': now(), 'status': 'claimed'}
                data['runs'].append(run)
                for entry in data['cases']:
                    if entry['case_id'] in pending:
                        entry['state'] = 'running'
                ledger.save(folder / 'queue.json', data)
                return {'status': 'claimed', 'model': data['model'],
                        'reasoning_effort': data['reasoning_effort'], **run,
                        'dispatch_instruction': 'Process ONLY case_ids in this claim; ignore other IDs in the batch prompt on retries.',
                        'prompt': str(folder / f'batch-{number:02d}/prompt.txt')}
        return {'status': 'awaiting audit; no queued cases'}


def finish(root, folder, snapshot):
    with locked(folder):
        data = ledger.read(folder / 'queue.json')
        if not data['runs'] or 'after' in data['runs'][-1]:
            raise ValueError('No active claim')
        run = data['runs'][-1]
        target = folder / f"batch-{run['batch']:02d}"
        for entry in data['cases']:
            key = entry['case_id']
            if key not in run['case_ids']:
                continue
            candidate = target / 'final' / (key + '.json')
            first = target / 'first-drafts' / (key + '.json')
            blocker = target / 'blocked' / (key + '.json')
            if candidate.exists() and first.exists():
                try:
                    body = ledger.read(candidate)
                    validate_candidate(root, key, body, ledger.read(first))
                    entry['state'] = 'awaiting_audit'
                except (ValueError, KeyError, TypeError, OSError) as error:
                    entry['state'] = 'validation_failed'
                    entry['validation_error'] = str(error)
                entry['candidate_sha256'] = ledger.file_hash(candidate)
            elif candidate.exists():
                entry['state'] = 'validation_failed'
                entry['validation_error'] = 'Final candidate has no preserved first draft'
            elif blocker.exists():
                try:
                    body = ledger.read(blocker)
                    if body.get('case_id') != key or not body.get('explanation'):
                        raise ValueError('Invalid blocker: ' + key)
                    entry['state'] = 'blocked'
                except (ValueError, KeyError, TypeError, OSError) as error:
                    entry['state'] = 'validation_failed'
                    entry['validation_error'] = str(error)
            else:
                entry['state'] = 'queued'
        run.update(after=snapshot, ended_at=now(), status='checkpointed')
        ledger.save(folder / 'queue.json', data)
        return {'status': 'checkpointed; not editorially verified',
                'cases': {e['case_id']: e['state'] for e in data['cases']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare').add_argument('--selection', required=True)
    for action in ('gate', 'claim', 'finish'):
        sub.add_parser(action).add_argument('--snapshot', required=True)
    sub.add_parser('status')
    sub.add_parser('inventory-sol')
    sub.add_parser('light-screen').add_argument('--out', required=True)
    args = parser.parse_args()
    folder = inside(ROOT, args.campaign)
    if args.command == 'inventory-sol':
        result = inventory_sol(ROOT)
    elif args.command == 'light-screen':
        output = inside(ROOT, args.out)
        if output.exists():
            raise ValueError('Refusing to overwrite screening artifact')
        result = light_screen(ROOT)
        ledger.save(output, result)
        result = {'count': result['count'], 'path': str(output), 'routing_approved': False}
    elif args.command == 'prepare':
        result = prepare(ROOT, folder, ledger.read(inside(ROOT, args.selection)))
    elif args.command == 'status':
        result = ledger.read(folder / 'queue.json')
    else:
        snapshot = ledger.read(inside(ROOT, args.snapshot))
        if args.command == 'gate':
            result = {'status': gate(ledger.read(folder / 'queue.json'), snapshot)}
        else:
            result = globals()[args.command](ROOT, folder, snapshot)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
