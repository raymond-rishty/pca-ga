"""Build and run resumable DeepSeek V4.1 Flash synopsis campaigns.

DeepSeek has no documented Batch API. This runner sends ordinary stateless
Responses API calls with bounded concurrency and per-case checkpoints. It never
publishes candidates.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import random
import sys
import time
import urllib.error
import urllib.request

import run_synopses_compact as compact
import synopsis_batch_api as common
import synopsis_queue as queue


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN = 'index/synopsis_workflow/deepseek-v4.1-flash-1'
DEFAULT_BASE_URL = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-flash'
DEFAULT_CONCURRENCY = 8
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def request_record(root, case_id, model, reasoning_effort, max_output_tokens):
    return {
        'custom_id': 'pca-synopsis-' + case_id,
        'method': 'POST',
        'url': '/responses',
        'body': {
            'model': model,
            'instructions': compact.build_developer_prompt(root),
            'input': compact.build_case_prompt(root, case_id),
            'reasoning': {'effort': reasoning_effort},
            'max_output_tokens': max_output_tokens,
            'text': {'format': {
                'type': 'json_schema',
                'name': 'pca_judicial_case_synopsis',
                'schema': common.api_schema(),
            }},
            'user': 'pca_ga_synopsis_campaign',
        },
    }


def build(folder, model=DEFAULT_MODEL, reasoning_effort='max',
          max_output_tokens=12000, requested=None, limit=None,
          shard_requests=common.DEFAULT_SHARD_REQUESTS,
          shard_estimated_tokens=common.DEFAULT_SHARD_ESTIMATED_TOKENS):
    if folder.exists():
        raise ValueError('Refusing to overwrite campaign: ' + str(folder))
    selected, processed, unpromptable = common.select_cases(ROOT, requested, limit)
    if not selected:
        raise ValueError('No unprocessed, promptable cases selected')
    if shard_requests < 1 or shard_estimated_tokens < 1:
        raise ValueError('Shard limits must be positive')

    folder.mkdir(parents=True)
    for name in ('raw', 'errors', 'first-drafts', 'final'):
        (folder / name).mkdir()
    rows = queue.ledger.catalog(ROOT)
    entries, encoded = [], []
    developer_chars = len(compact.build_developer_prompt(ROOT))
    for case_id in selected:
        record = request_record(ROOT, case_id, model, reasoning_effort,
                                max_output_tokens)
        line = json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n'
        row = rows[case_id]
        source = ROOT / 'cases' / (row['case_page'] + '.md')
        entry = {
            'case_id': case_id,
            'custom_id': record['custom_id'],
            'source': source.relative_to(ROOT).as_posix(),
            'source_sha256': queue.ledger.file_hash(source),
            'benchmark_examples': compact.examples(row),
            'developer_chars': developer_chars,
            'case_prompt_chars': len(compact.build_case_prompt(ROOT, case_id)),
            'estimated_input_tokens': (len(line) + 2) // 3,
        }
        entries.append(entry)
        encoded.append((entry, line))

    groups, current, current_tokens = [], [], 0
    for entry, line in encoded:
        estimate = entry['estimated_input_tokens']
        if current and (len(current) >= shard_requests or
                        current_tokens + estimate > shard_estimated_tokens):
            groups.append(current)
            current, current_tokens = [], 0
        current.append((entry, line))
        current_tokens += estimate
    if current:
        groups.append(current)

    request_files = []
    for number, group in enumerate(groups, 1):
        path = folder / f'requests-{number:03d}.jsonl'
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            for _, line in group:
                stream.write(line)
        ids = [entry['case_id'] for entry, _ in group]
        validation = common.validate_request_file(path, ids, 'deepseek')
        request_files.append({
            'shard': number,
            'path': path.relative_to(ROOT).as_posix(),
            'sha256': queue.ledger.file_hash(path),
            'request_count': validation['requests'],
            'request_bytes': validation['bytes'],
            'estimated_input_tokens': sum(
                entry['estimated_input_tokens'] for entry, _ in group),
            'case_ids': ids,
        })

    references = {path: queue.ledger.file_hash(ROOT / path) for path in queue.REFERENCES}
    manifest = {
        'schema_version': 1,
        'created_at': common.now(),
        'provider': 'deepseek',
        'transport': 'concurrent_responses_api',
        'batch_api_available': False,
        'endpoint': '/responses',
        'base_url': DEFAULT_BASE_URL,
        'model': model,
        'model_version_label': 'DeepSeek-V4.1-Flash',
        'reasoning_effort': reasoning_effort,
        'max_output_tokens': max_output_tokens,
        'cache': {'mode': 'automatic_identical_prefix',
                  'stable_prefix': 'instructions / compact developer contract'},
        'publication_authorized': False,
        'request_count': len(selected),
        'request_bytes': sum(item['request_bytes'] for item in request_files),
        'estimated_input_tokens': sum(
            item['estimated_input_tokens'] for item in request_files),
        'shard_limits': {'requests': shard_requests,
                         'estimated_input_tokens': shard_estimated_tokens},
        'request_files': request_files,
        'selected': entries,
        'processed_exclusions': processed,
        'unpromptable': unpromptable,
        'reference_hashes': references,
        'policy': ('Existing Sol candidates are omitted regardless of audit state. '
                   'DeepSeek candidates require source audit and are not published.'),
    }
    queue.ledger.save(folder / 'manifest.json', manifest)
    queue.ledger.save(folder / 'schema.json', common.api_schema())
    queue.ledger.save(folder / 'validation-schema.json', compact.schema())
    queue.ledger.save(folder / 'runs.json', {'schema_version': 1, 'arms': [{
        'model': model,
        'reasoning_effort': reasoning_effort,
        'output_directory': (folder / 'final').relative_to(ROOT).as_posix(),
    }]})
    return {
        'campaign': folder.relative_to(ROOT).as_posix(),
        'selected': len(selected),
        'excluded_processed': len(processed),
        'unpromptable': len(unpromptable),
        'shards': len(request_files),
        'estimated_input_tokens': manifest['estimated_input_tokens'],
    }


def require_key():
    value = os.environ.get('DEEPSEEK_API_KEY')
    if not value:
        raise ValueError('DEEPSEEK_API_KEY is not set')
    return value


def load_shard(folder, shard):
    manifest, _ = common.verify_campaign(folder)
    item = common.shard_record(manifest, shard)
    path = queue.inside(ROOT, item['path'])
    records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    return manifest, item, records


def call_response(api_key, base_url, record, attempts):
    case_id = record['custom_id'].removeprefix('pca-synopsis-')
    payload = json.dumps(record['body']).encode('utf-8')
    request = urllib.request.Request(
        base_url.rstrip('/') + record['url'], data=payload, method='POST',
        headers={'Authorization': 'Bearer ' + api_key,
                 'Content-Type': 'application/json'})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=720) as response:
                body = json.loads(response.read())
                return case_id, {'custom_id': record['custom_id'], 'response': {
                    'status_code': response.status,
                    'request_id': response.headers.get('x-request-id'),
                    'body': body}, 'error': None}, None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            error = {'case_id': case_id, 'attempt': attempt, 'http_status': exc.code,
                     'error': detail, 'at': common.now()}
            if exc.code not in RETRYABLE_HTTP or attempt == attempts:
                return case_id, None, error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = {'case_id': case_id, 'attempt': attempt,
                     'error': str(exc), 'at': common.now()}
            if attempt == attempts:
                return case_id, None, error
        time.sleep(min(30, 2 ** (attempt - 1)) + random.random())
    raise AssertionError('unreachable')


def compile_output(folder, shard, case_ids):
    lines = []
    for case_id in case_ids:
        path = folder / 'raw' / common.case_filename(case_id)
        if path.is_file():
            lines.append(json.dumps(queue.ledger.read(path), ensure_ascii=False,
                                    separators=(',', ':')))
    target = folder / f'output-{shard:03d}.jsonl'
    value = ('\n'.join(lines) + '\n') if lines else ''
    target.write_text(value, encoding='utf-8', newline='\n')
    return target


def run(folder, shard, base_url, concurrency=DEFAULT_CONCURRENCY, attempts=4):
    if concurrency < 1 or attempts < 1:
        raise ValueError('Concurrency and attempts must be positive')
    _, item, records = load_shard(folder, shard)
    api_key = require_key()
    pending, skipped = [], []
    for record in records:
        case_id = record['custom_id'].removeprefix('pca-synopsis-')
        if (folder / 'raw' / common.case_filename(case_id)).is_file():
            skipped.append(case_id)
        else:
            pending.append(record)

    completed, failures = [], []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(call_response, api_key, base_url, record, attempts)
                   for record in pending]
        for future in as_completed(futures):
            case_id, response, error = future.result()
            if response is not None:
                common.save_candidate(folder / 'raw' / common.case_filename(case_id), response)
                completed.append(case_id)
                error_path = folder / 'errors' / common.case_filename(case_id)
                if error_path.exists():
                    error_path.unlink()
            else:
                queue.ledger.save(folder / 'errors' / common.case_filename(case_id), error)
                failures.append(error)

    output = compile_output(folder, shard, item['case_ids'])
    report = {
        'finished_at': common.now(),
        'shard': shard,
        'concurrency': concurrency,
        'attempts': attempts,
        'completed_this_run': sorted(completed),
        'already_completed': skipped,
        'failures': failures,
        'output': output.relative_to(ROOT).as_posix(),
        'remaining': item['request_count'] - len(completed) - len(skipped),
    }
    queue.ledger.save(folder / f'run-{shard:03d}.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', default=DEFAULT_CAMPAIGN)
    parser.add_argument('--base-url', default=os.environ.get(
        'DEEPSEEK_BASE_URL', DEFAULT_BASE_URL))
    sub = parser.add_subparsers(dest='action', required=True)
    build_parser = sub.add_parser('build')
    build_parser.add_argument('--model', default=DEFAULT_MODEL)
    build_parser.add_argument('--reasoning-effort', default='max',
                              choices=['none', 'low', 'high', 'max'])
    build_parser.add_argument('--max-output-tokens', type=int, default=12000)
    build_parser.add_argument('--case', action='append', dest='cases')
    build_parser.add_argument('--limit', type=int)
    build_parser.add_argument('--shard-requests', type=int,
                              default=common.DEFAULT_SHARD_REQUESTS)
    build_parser.add_argument('--shard-estimated-tokens', type=int,
                              default=common.DEFAULT_SHARD_ESTIMATED_TOKENS)
    sub.add_parser('validate')
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--shard', type=int, required=True)
    run_parser.add_argument('--concurrency', type=int, default=DEFAULT_CONCURRENCY)
    run_parser.add_argument('--attempts', type=int, default=4)
    ingest_parser = sub.add_parser('ingest')
    ingest_parser.add_argument('--results', type=Path, action='append')
    args = parser.parse_args(argv)
    folder = common.campaign_path(args.campaign)

    if args.action == 'build':
        result = build(folder, args.model, args.reasoning_effort,
                       args.max_output_tokens, args.cases, args.limit,
                       args.shard_requests, args.shard_estimated_tokens)
    elif args.action == 'validate':
        manifest, validations = common.verify_campaign(folder)
        result = {'request_count': manifest['request_count'],
                  'shards': len(validations), 'validations': validations}
    elif args.action == 'run':
        result = run(folder, args.shard, args.base_url,
                     args.concurrency, args.attempts)
    else:
        result = common.ingest(folder, args.results)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
