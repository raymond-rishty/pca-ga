"""Tool-free, one-response-per-case Sol synopsis runner.

The script supplies all evidence in the prompt, captures strict JSON, writes the
first/final artifacts mechanically, validates, and checks usage between cases.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import synopsis_queue as q
import run_synopses as base


RUNTIME_CONTRACT = (
    '.agents/skills/pca-ga-case-synopses/references/compact-runtime-contract.md')

TYPE_EXAMPLES = {
    'complaint': ['C01', 'C20'], 'appeal': ['A01', 'A19'],
    'judicial_reference': ['J01', 'J02'],
    'original_jurisdiction_request': ['O04', 'O05'],
    'bco_40_5_matter': ['B03', 'B08'], 'review_and_control': ['R01', 'R04']}
MIXED = {'partially_sustained', 'remanded', 'vacated', 'annulled', 'moot'}
NONMERITS = {'dismissed', 'withdrawn', 'abandoned', 'administratively_out_of_order',
             'judicially_out_of_order', 'out_of_order', 'no_final_disposition'}


def benchmark_entry(text, identifier):
    marker = '### ' + identifier + '.'
    begin = text.index(marker)
    match = text.find('\n### ', begin + len(marker))
    if match < 0:
        match = text.find('\n## ', begin + len(marker))
    return text[begin:] if match < 0 else text[begin:match]


def examples(row):
    result = list(TYPE_EXAMPLES.get(row.get('matter_type'), ['C01', 'A01']))
    dispositions = set(row.get('final_dispositions') or [])
    if dispositions & MIXED:
        result[1] = 'C02' if row.get('matter_type') == 'complaint' else 'A03'
    elif dispositions & NONMERITS:
        result[1] = 'C20' if row.get('matter_type') == 'complaint' else 'A20'
    return list(dict.fromkeys(result))


def schema():
    text = {'type': 'string', 'minLength': 1}
    scores = {'type': 'object', 'additionalProperties': False,
              'required': list(q.ledger.DIMENSIONS),
              'properties': {key: {'type': 'integer', 'minimum': 0, 'maximum': 2}
                             for key in q.ledger.DIMENSIONS}}
    reasons = {'type': 'object', 'additionalProperties': False,
               'required': list(q.ledger.DIMENSIONS),
               'properties': {key: text for key in q.ledger.DIMENSIONS}}
    evidence_keys = ['identity_and_adoption', 'dispute', 'outcomes_and_reasons',
                     'qualifications', 'incorporated_decisions']
    properties = {
        'case_id': text, 'title': text, 'matter_type': text,
        'final_dispositions': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': text},
        'disposition_detail': text, 'first_summary': text, 'summary': text,
        'sources': {'type': 'array', 'minItems': 1, 'items': {'type': 'object',
            'additionalProperties': False, 'required': ['path', 'sha256', 'locator', 'supports'],
            'properties': {'path': text, 'sha256': text, 'locator': text, 'supports': text}}},
        'evidence_notes': {'type': 'object', 'additionalProperties': False,
            'required': evidence_keys, 'properties': {key: text for key in evidence_keys}},
        'source_limits': text,
        'benchmark_examples': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': text},
        'scores': scores, 'score_reasons': reasons, 'verification_notes': text,
        'repair_needed': {'type': 'boolean'}, 'repair_notes': {'type': 'string'}}
    return {'type': 'object', 'additionalProperties': False,
            'required': list(properties), 'properties': properties}


def build_developer_prompt(root):
    contract = (root / RUNTIME_CONTRACT).read_text(encoding='utf-8')
    return f'''Write one PCA judicial-case synopsis and return only the required JSON object.

COMPACT RUNTIME CONTRACT:
{contract}
'''


def build_case_prompt(root, key):
    rows = q.ledger.catalog(root)
    row = rows[key]
    source_name = 'cases/' + row['case_page'] + '.md'
    source_path = q.ledger.source_path(root, source_name)
    source_hash = q.ledger.file_hash(source_path)
    benchmark = (root / 'docs/JUDICIAL-SYNOPSIS-BENCHMARKS.md').read_text(encoding='utf-8')
    selected = examples(row)
    excerpts = '\n\n'.join(benchmark_entry(benchmark, item) for item in selected)
    numbered = '\n'.join(f'{n}: {line}' for n, line in enumerate(
        source_path.read_text(encoding='utf-8').splitlines(), 1))
    return f'''APPLICABLE EDITORIAL EXAMPLES (comparison only, never evidence):
{excerpts}

CASE ASSIGNMENT:
The case_id must be {key}. The required source object path/sha256 are
{source_name} / {source_hash}. Use precise line or printed-page locators.

AUTHORITATIVE CASE SOURCE:
## SOURCE {source_name} SHA256 {source_hash}
{numbered}
'''


def build_prompt(root, key):
    return build_developer_prompt(root) + '\n' + build_case_prompt(root, key)


def command(codex, root, claim, schema_path, output_path):
    return [codex, 'exec', '--ephemeral', '--ignore-user-config', '--ignore-rules',
            '--json', '--color', 'never', '--sandbox', 'read-only', '-C', str(root),
            '--disable', 'shell_tool', '--disable', 'apps', '--disable', 'plugins',
            '--disable', 'remote_plugin', '-c', 'web_search="disabled"',
            '-m', claim['model'], '-c', 'model_reasoning_effort=' + json.dumps(claim['reasoning_effort']),
            '--output-schema', str(schema_path), '--output-last-message', str(output_path), '-']


def run_case(codex, root, folder, claim, attempt, timeout):
    key = claim['case_ids'][0]
    schema_path, output_path = attempt / 'schema.json', attempt / 'candidate.json'
    q.ledger.save(schema_path, schema())
    prompt = build_prompt(root, key)
    (attempt / 'prompt.txt').write_text(prompt, encoding='utf-8')
    args = command(codex, root, claim, schema_path, output_path)
    with (attempt / 'events.jsonl').open('x', encoding='utf-8') as out, \
            (attempt / 'stderr.txt').open('x', encoding='utf-8') as err:
        proc = subprocess.run(args, input=prompt, stdout=out, stderr=err, text=True,
                              encoding='utf-8', timeout=timeout, creationflags=base.FLAGS)
    metrics = base.event_metrics(attempt / 'events.jsonl')
    receipt = {'started_at': q.now(), 'ended_at': q.now(), 'command': args,
               'case_ids': [key], 'worker_exit_code': proc.returncode, **metrics}
    if proc.returncode == 0 and metrics['turn_completed'] and output_path.exists():
        body = q.ledger.read(output_path)
        target = folder / f"batch-{claim['batch']:02d}"
        first = dict(body)
        first['summary'] = body['first_summary']
        (target / 'first-drafts').mkdir(exist_ok=True)
        (target / 'final').mkdir(exist_ok=True)
        q.ledger.save(target / 'first-drafts' / (key + '.json'), first)
        q.ledger.save(target / 'final' / (key + '.json'), body)
    q.ledger.save(attempt / 'worker.json', receipt)
    return receipt


def run(root, folder, codex, max_cases=1, timeout=900):
    with base.runner_lock(folder):
        counts = None
        for _ in range(max_cases):
            before = base.read_usage(codex)
            claim = q.claim(root, folder, before, max_cases=1)
            if claim['status'] != 'claimed':
                return {'status': claim['status'], 'report': base.report(root, folder)['counts']}
            data = q.ledger.read(folder / 'queue.json')
            attempt = folder / 'compact-attempts' / f"run-{len(data['runs']):03d}"
            attempt.mkdir(parents=True, exist_ok=False)
            q.ledger.save(attempt / 'before.json', before)
            q.ledger.save(attempt / 'claim.json', claim)
            receipt = run_case(codex, root, folder, claim, attempt, timeout)
            after = base.read_usage(codex)
            q.ledger.save(attempt / 'after.json', after)
            q.finish(root, folder, after)
            counts = base.report(root, folder)['counts']
            state = next(e['state'] for e in q.ledger.read(folder / 'queue.json')['cases']
                         if e['case_id'] == claim['case_ids'][0])
            if receipt['worker_exit_code'] or not receipt['turn_completed'] or state != 'awaiting_audit':
                return {'status': 'paused: compact worker/output needs attention', 'report': counts}
        return {'status': 'case limit reached', 'report': counts}


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'payload'])
    parser.add_argument('--campaign', default='index/synopsis_workflow/sol-calibration-1')
    parser.add_argument('--case')
    parser.add_argument('--max-cases', type=int, default=1)
    parser.add_argument('--timeout-seconds', type=int, default=900)
    parser.add_argument('--codex', default=base.shutil.which('codex'))
    args = parser.parse_args()
    folder = q.inside(q.ROOT, args.campaign)
    if args.action == 'payload':
        if not args.case:
            parser.error('--case required')
        print(build_prompt(q.ROOT, args.case))
    else:
        if not args.codex or not 1 <= args.max_cases <= 100:
            parser.error('Codex and 1..100 cases required')
        print(json.dumps(run(q.ROOT, folder, args.codex, args.max_cases, args.timeout_seconds), indent=2))
