"""Serve the local, keyboard-driven judicial synopsis review queue.

Decisions are written to the candidate-intake workspace. This tool never edits
canonical editorial overrides, generated indexes, case sources, or git state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import sys
import urllib.parse
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / 'index/synopsis_workflow/candidate-intake-1/registry.json'
DEFAULT_DECISIONS = ROOT / 'index/synopsis_workflow/candidate-intake-1/audit-decisions.json'
DEFAULT_PRIORITIES = ROOT / 'index/synopsis_workflow/candidate-intake-1/review-priorities.json'
APP = ROOT / 'index/synopsis_workflow/candidate-review/index.html'
MATTER_TYPES = {
    'complaint', 'appeal', 'judicial_reference', 'original_jurisdiction_request',
    'bco_40_5_matter', 'review_and_control', 'other'}
DISPOSITIONS = {
    'sustained', 'partially_sustained', 'not_sustained', 'denied', 'granted',
    'guilty', 'not_guilty', 'administratively_out_of_order',
    'judicially_out_of_order', 'out_of_order', 'dismissed', 'withdrawn',
    'abandoned', 'moot', 'affirmed', 'reversed', 'vacated', 'annulled',
    'remanded', 'referred', 'in_order', 'no_final_disposition', 'other'}
DECISIONS = {'approved', 'rejected', 'corrected', 'source_repair', 'unreviewed'}


def acceptability_pass(record):
    """Return the statistical synopsis result independently of edit status."""
    if 'acceptability_pass' in record:
        return record['acceptability_pass'] is True
    return record.get('decision') == 'approved'


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def inside(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path outside repository: ' + str(value))
    return path


def file_hash(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson_interval(failures, total, z=1.96):
    if not total:
        return None
    proportion = failures / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        (proportion * (1 - proportion) + z * z / (4 * total)) / total
    ) / denominator
    return [round(max(0, center - margin), 4), round(min(1, center + margin), 4)]


class ReviewStore:
    def __init__(self, root, registry_path, decisions_path, priorities_path=DEFAULT_PRIORITIES):
        self.root = root.resolve()
        self.registry_path = registry_path.resolve()
        self.decisions_path = decisions_path.resolve()
        self.catalog = {}
        for line in (root / 'index/judicial_cases.jsonl').read_text(
                encoding='utf-8').splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get('case_id') or 'roster:' + str(row.get('roster_id'))
            self.catalog[key] = row
        registry = read_json(self.registry_path)
        if registry.get('publication_authorized') is not False:
            raise ValueError('Review registry must not authorize publication')
        self.entries = {item['case_id']: item for item in registry['candidates']}
        if len(self.entries) != len(registry['candidates']):
            raise ValueError('Duplicate case IDs in candidate registry')
        unknown = set(self.entries) - set(self.catalog)
        if unknown:
            raise ValueError('Candidates absent from catalog: ' + ', '.join(sorted(unknown)))
        self.priority_report = read_json(priorities_path) if priorities_path.is_file() else {
            'counts': {}, 'statistical_audit': {}, 'cases': {}}
        self.priorities = self.priority_report.get('cases') or {}

    def decisions(self):
        if not self.decisions_path.exists():
            return {
                'schema_version': 1,
                'publication_authorized': False,
                'updated_at': None,
                'cases': {},
            }
        value = read_json(self.decisions_path)
        if value.get('publication_authorized') is not False:
            raise ValueError('Audit decisions must not authorize publication')
        return value

    def index(self):
        decisions = self.decisions().get('cases') or {}
        items = []
        for case_id, entry in self.entries.items():
            row = self.catalog[case_id]
            selected = entry['selected']
            decision = decisions.get(case_id, {})
            items.append({
                'case_id': case_id,
                'title': row.get('title') or '',
                'year': row.get('decision_year'),
                'provider': selected.get('provider'),
                'model': selected.get('model'),
                'identity_remapped_from': selected.get('identity_remapped_from'),
                'risk_score': self.priorities.get(case_id, {}).get('risk_score', 0),
                'impact_score': self.priorities.get(case_id, {}).get('impact_score', 0),
                'audit_group': self.priorities.get(case_id, {}).get('audit_group', 'remaining'),
                'selected_for_audit': self.priorities.get(case_id, {}).get('selected_for_audit', False),
                'decision': decision.get('decision', 'unreviewed'),
                'reviewer': decision.get('reviewer'),
                'updated_at': decision.get('updated_at'),
            })
        return {
            'items': items,
            'counts': self.counts(decisions),
            'priority_counts': self.priority_report.get('counts') or {},
            'statistical_audit': self.statistical_audit(decisions),
        }

    def statistical_audit(self, decisions):
        sample_ids = [
            case_id for case_id, priority in self.priorities.items()
            if priority.get('selection_basis') == 'statistical_sample']
        reviewed = [
            case_id for case_id in sample_ids
            if decisions.get(case_id, {}).get('decision') in
            {'approved', 'corrected', 'rejected', 'source_repair'}]
        failures = [
            case_id for case_id in reviewed
            if not acceptability_pass(decisions[case_id])]
        return {
            'planned_sample': len(sample_ids),
            'reviewed_sample': len(reviewed),
            'observed_failures': len(failures),
            'observed_failure_rate': round(len(failures) / len(reviewed), 4) if reviewed else None,
            'wilson_95_percent_interval': wilson_interval(len(failures), len(reviewed)),
        }

    def counts(self, decisions=None):
        decisions = decisions if decisions is not None else self.decisions().get('cases', {})
        counts = {key: 0 for key in DECISIONS}
        for case_id in self.entries:
            key = decisions.get(case_id, {}).get('decision', 'unreviewed')
            counts[key if key in counts else 'unreviewed'] += 1
        counts['total'] = len(self.entries)
        return counts

    def case(self, case_id):
        if case_id not in self.entries:
            raise KeyError(case_id)
        entry = self.entries[case_id]
        selected = entry['selected']
        candidate_path = inside(self.root, selected['path'])
        if file_hash(candidate_path) != selected['sha256']:
            raise ValueError('Candidate changed since registry build: ' + case_id)
        candidate = read_json(candidate_path)
        row = self.catalog[case_id]
        if selected.get('identity_remapped_from'):
            # Present the verified canonical identity while retaining the
            # original model artifact and its immutable hash as provenance.
            candidate = {
                **candidate,
                'case_id': case_id,
                'title': row.get('title') or candidate.get('title'),
                'identity_remapped_from': selected['identity_remapped_from'],
            }
        sources = candidate.get('sources') or []
        source_path = None
        for source in sources:
            possible = inside(self.root, source.get('path', ''))
            if possible.is_file():
                source_path = possible
                break
        if source_path is None and row.get('case_page'):
            possible = self.root / 'cases' / (row['case_page'] + '.md')
            if possible.is_file():
                source_path = possible
        source_text = source_path.read_text(encoding='utf-8') if source_path else ''
        source_name = source_path.relative_to(self.root).as_posix() if source_path else None
        return {
            'case_id': case_id,
            'catalog': row,
            'candidate': candidate,
            'selection': selected,
            'priority': self.priorities.get(case_id),
            'source': {'path': source_name, 'text': source_text},
            'decision': (self.decisions().get('cases') or {}).get(case_id),
        }

    def save_decision(self, case_id, payload):
        if case_id not in self.entries:
            raise ValueError('Unknown candidate: ' + case_id)
        decision = payload.get('decision')
        if decision not in DECISIONS:
            raise ValueError('Unknown decision')
        reviewer = str(payload.get('reviewer') or '').strip()
        if decision != 'unreviewed' and not reviewer:
            raise ValueError('Reviewer is required')
        statistical_pass = payload.get('acceptability_pass')
        if statistical_pass is not None and not isinstance(statistical_pass, bool):
            raise ValueError('acceptability_pass must be a boolean')

        data = self.decisions()
        cases = data.setdefault('cases', {})
        if decision == 'unreviewed':
            cases.pop(case_id, None)
        else:
            candidate = self.case(case_id)['candidate']
            record = {
                'case_id': case_id,
                'decision': decision,
                'reviewer': reviewer,
                'notes': str(payload.get('notes') or '').strip(),
                'updated_at': now(),
                'candidate_path': self.entries[case_id]['selected']['path'],
                'candidate_sha256': self.entries[case_id]['selected']['sha256'],
                'publication_authorized': False,
                'acceptability_pass': (
                    decision == 'approved' if statistical_pass is None
                    else statistical_pass),
            }
            if decision == 'corrected':
                summary = str(payload.get('summary') or '').strip()
                matter_type = payload.get('matter_type')
                dispositions = payload.get('final_dispositions')
                if not summary:
                    raise ValueError('Corrected synopsis is required')
                if matter_type not in MATTER_TYPES:
                    raise ValueError('Invalid corrected matter type')
                if (not isinstance(dispositions, list) or not dispositions
                        or len(dispositions) != len(set(dispositions))
                        or set(dispositions) - DISPOSITIONS):
                    raise ValueError('Invalid corrected dispositions')
                record['corrected'] = {
                    'summary': summary,
                    'matter_type': matter_type,
                    'final_dispositions': dispositions,
                }
                record['original'] = {
                    'summary': candidate.get('summary'),
                    'matter_type': candidate.get('matter_type'),
                    'final_dispositions': candidate.get('final_dispositions'),
                }
            cases[case_id] = record
        data['updated_at'] = now()
        data['counts'] = self.counts(cases)
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.decisions_path.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temporary.replace(self.decisions_path)
        return {'decision': cases.get(case_id), 'counts': data['counts']}


class Handler(BaseHTTPRequestHandler):
    store = None

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == '/api/index':
                self.send_json(self.store.index())
            elif parsed.path == '/api/case':
                case_id = urllib.parse.parse_qs(parsed.query).get('id', [''])[0]
                self.send_json(self.store.case(case_id))
            elif parsed.path == '/api/decisions':
                self.send_json(self.store.decisions())
            elif parsed.path in {'/', '/index.html'}:
                self.send_file(APP)
            else:
                self.send_error(404)
        except KeyError:
            self.send_json({'error': 'Case not found'}, 404)
        except (OSError, TypeError, ValueError) as exc:
            self.send_json({'error': str(exc)}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/api/decision':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 100_000:
                raise ValueError('Decision payload is too large')
            payload = json.loads(self.rfile.read(length))
            case_id = urllib.parse.parse_qs(parsed.query).get('id', [''])[0]
            self.send_json(self.store.save_decision(case_id, payload))
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            self.send_json({'error': str(exc)}, 400)

    def log_message(self, format, *args):
        sys.stdout.write('[review] ' + format % args + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument('--decisions', type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument('--priorities', type=Path, default=DEFAULT_PRIORITIES)
    parser.add_argument('--open', action='store_true', dest='open_browser')
    args = parser.parse_args(argv)
    if not APP.is_file():
        raise ValueError('Review app is missing: ' + str(APP))
    Handler.store = ReviewStore(ROOT, args.registry, args.decisions, args.priorities)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f'http://{args.host}:{args.port}/'
    print(f'Review {len(Handler.store.entries)} candidates at {url}')
    print('Decisions: ' + str(args.decisions))
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, TypeError, ValueError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
