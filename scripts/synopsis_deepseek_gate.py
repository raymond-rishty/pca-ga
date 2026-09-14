"""Partition DeepSeek synopsis candidates with the conservative acceptance gate.

The gate never deletes provider responses from ``raw/``.  By default it is a
read-only report.  ``--apply`` writes only passing candidate JSON objects to
``gate/accepted/`` and records every rejection reason in ``gate/report.json``.
Passing this gate means "eligible for the sampled DeepSeek lane," not that a
case has received an independent source audit or publication approval.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys

import synopsis_batch_api as common
import synopsis_queue as queue


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN = 'index/synopsis_workflow/deepseek-v4.1-flash-1'
SHARED_CASE_SOURCE_RE = re.compile(r'\d{4}-\d+[a-z]?_\d{4}-\d+[a-z]?', re.I)
BENCHMARK_ID_RE = re.compile(r'^([A-Z]\d+)\b')


def now():
    return datetime.now(timezone.utc).isoformat()


def candidate_reasons(candidate, entry):
    """Return deterministic reasons that keep a candidate out of the safe lane."""
    reasons = []
    scores = candidate['scores']
    total = sum(scores.values())
    dispositions = candidate['final_dispositions']

    if candidate['repair_needed']:
        reasons.append('repair_needed')
    if scores['fidelity'] < 2:
        reasons.append('fidelity_below_2')
    if total < 10:
        reasons.append('score_below_10')
    if candidate['matter_type'] == 'other' or 'other' in dispositions:
        reasons.append('other_taxonomy')
    if len(dispositions) > 2:
        reasons.append('more_than_two_dispositions')
    if 'partially_sustained' in dispositions:
        reasons.append('partially_sustained')
    if SHARED_CASE_SOURCE_RE.search(entry['source']):
        reasons.append('shared_case_source')
    return reasons


def validate_candidate(candidate, entry):
    """Validate a DeepSeek candidate without requiring bare benchmark IDs.

    The compact prompt supplied benchmark IDs, but DeepSeek commonly returned
    annotations such as ``C01 (Allin ...): ...``.  Those are valid citations so
    long as their leading ID was actually supplied for this case.
    """
    common.validate_value(candidate, common.compact.schema())
    if candidate['case_id'] != entry['case_id']:
        raise ValueError('Candidate case_id does not match custom_id')
    if candidate['matter_type'] not in common.MATTER_TYPES:
        raise ValueError('Unknown matter_type: ' + candidate['matter_type'])
    unknown = set(candidate['final_dispositions']) - common.DISPOSITIONS
    if unknown:
        raise ValueError('Unknown final dispositions: ' + ', '.join(sorted(unknown)))
    expected_source = (entry['source'], entry['source_sha256'])
    supplied = {(item['path'], item['sha256']) for item in candidate['sources']}
    if expected_source not in supplied:
        raise ValueError('Required case source path/hash is missing')

    expected_examples = set(entry['benchmark_examples'])
    matched_example = False
    for example in candidate['benchmark_examples']:
        match = BENCHMARK_ID_RE.match(example.strip())
        if not match:
            continue
        if match.group(1) not in expected_examples:
            raise ValueError('Candidate claims unprovided benchmark examples')
        matched_example = True
    if expected_examples and not matched_example:
        raise ValueError('Candidate cites no supplied benchmark example')


def load_candidate(path, entry):
    record = queue.ledger.read(path)
    response = record.get('response') or {}
    if response.get('status_code') != 200:
        raise ValueError('HTTP status ' + str(response.get('status_code')))
    body = response.get('body') or {}
    if body.get('status') != 'completed':
        raise ValueError('Response status ' + str(body.get('status')))
    candidate = json.loads(common.output_text(body))
    validate_candidate(candidate, entry)
    return candidate


def evaluate(folder):
    manifest, _ = common.verify_campaign(folder)
    entries = {item['case_id']: item for item in manifest['selected']}
    accepted, rejected = [], []

    for case_id, entry in sorted(entries.items()):
        path = folder / 'raw' / common.case_filename(case_id)
        if not path.is_file():
            rejected.append({'case_id': case_id, 'reasons': ['missing_raw_response']})
            continue
        try:
            candidate = load_candidate(path, entry)
            reasons = candidate_reasons(candidate, entry)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            rejected.append({
                'case_id': case_id,
                'reasons': ['invalid_candidate'],
                'detail': str(exc),
            })
            continue
        item = {
            'case_id': case_id,
            'matter_type': candidate['matter_type'],
            'final_dispositions': candidate['final_dispositions'],
            'score_total': sum(candidate['scores'].values()),
            'fidelity': candidate['scores']['fidelity'],
        }
        if reasons:
            item['reasons'] = reasons
            rejected.append(item)
        else:
            item['candidate'] = candidate
            accepted.append(item)

    reason_counts = {}
    for item in rejected:
        for reason in item['reasons']:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        'generated_at': now(),
        'campaign': folder.relative_to(ROOT).as_posix(),
        'policy': 'deepseek-conservative-gate-v1',
        'publication_authorized': False,
        'raw_responses_preserved': True,
        'total': len(entries),
        'accepted_count': len(accepted),
        'rejected_count': len(rejected),
        'reason_counts': dict(sorted(reason_counts.items())),
        'accepted': accepted,
        'rejected': rejected,
    }


def apply_report(folder, report, replace=False):
    target = folder / 'gate'
    if target.exists():
        if not replace:
            raise ValueError('Gate output exists; pass --replace to rebuild it: ' + str(target))
        shutil.rmtree(target)
    accepted_dir = target / 'accepted'
    accepted_dir.mkdir(parents=True)
    for item in report['accepted']:
        queue.ledger.save(
            accepted_dir / common.case_filename(item['case_id']), item['candidate'])

    persisted = dict(report)
    persisted['accepted'] = [
        {key: value for key, value in item.items() if key != 'candidate'}
        for item in report['accepted']
    ]
    queue.ledger.save(target / 'report.json', persisted)
    return target


def display_report(report):
    return {
        key: report[key] for key in (
            'campaign', 'policy', 'total', 'accepted_count', 'rejected_count',
            'reason_counts', 'raw_responses_preserved')
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', default=DEFAULT_CAMPAIGN)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args(argv)
    if args.replace and not args.apply:
        raise ValueError('--replace requires --apply')
    folder = common.campaign_path(args.campaign)
    report = evaluate(folder)
    result = display_report(report)
    if args.apply:
        target = apply_report(folder, report, args.replace)
        result['written_to'] = target.relative_to(ROOT).as_posix()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
