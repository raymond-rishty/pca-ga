"""Build, submit, retrieve, and unpack OpenAI Batch API synopsis jobs.

Generation is local and does not call the API. Submission requires OPENAI_API_KEY.
Candidates are retained for audit; this script never publishes summaries.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

import run_synopses_compact as compact
import synopsis_queue as queue


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN = 'index/synopsis_workflow/openai-sol-deepseek-failures-1'
DEFAULT_BASE_URL = 'https://api.openai.com'
DEFAULT_SHARD_REQUESTS = 75
DEFAULT_SHARD_ESTIMATED_TOKENS = 750_000
MATTER_TYPES = {
    'complaint', 'appeal', 'judicial_reference', 'original_jurisdiction_request',
    'bco_40_5_matter', 'review_and_control', 'other'}
DISPOSITIONS = {
    'sustained', 'partially_sustained', 'not_sustained', 'denied', 'granted',
    'guilty', 'not_guilty', 'administratively_out_of_order',
    'judicially_out_of_order', 'out_of_order', 'dismissed', 'withdrawn',
    'abandoned', 'moot', 'affirmed', 'reversed', 'vacated', 'annulled',
    'remanded', 'referred', 'in_order', 'no_final_disposition', 'other'}


def now():
    return datetime.now(timezone.utc).isoformat()


def campaign_path(value):
    return queue.inside(ROOT, value)


def case_filename(case_id):
    return urllib.parse.quote(case_id, safe='-_.') + '.json'


BENCHMARK_ID = re.compile(r'(?<![A-Z0-9])([A-Z][0-9]{2})(?![A-Z0-9])')


def api_schema(benchmark_examples=None):
    """Return the strict-output schema without locally enforced-only keywords."""
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(child) for key, child in value.items()
                    if key != 'uniqueItems'}
        if isinstance(value, list):
            return [clean(child) for child in value]
        return value
    schema = clean(compact.schema())
    if benchmark_examples:
        schema['properties']['benchmark_examples']['items']['enum'] = list(
            benchmark_examples)
    return schema


def request_record(root, case_id, model, reasoning_effort, max_output_tokens,
                   benchmark_examples=None):
    developer = compact.build_developer_prompt(root)
    user = compact.build_case_prompt(root, case_id)
    if benchmark_examples is None:
        row = queue.ledger.catalog(root)[case_id]
        benchmark_examples = compact.examples(row)
    body = {
        'model': model,
        'reasoning': {'effort': reasoning_effort},
        'max_output_tokens': max_output_tokens,
        'store': False,
        'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
        'input': [
            {'role': 'developer', 'content': [{
                'type': 'input_text', 'text': developer,
                'prompt_cache_breakpoint': {'mode': 'explicit'}}]},
            {'role': 'user', 'content': [{'type': 'input_text', 'text': user}]},
        ],
        'text': {'verbosity': 'low', 'format': {
            'type': 'json_schema', 'name': 'pca_judicial_case_synopsis',
            'strict': True, 'schema': api_schema(benchmark_examples)}},
    }
    return {'custom_id': 'pca-synopsis-' + case_id, 'method': 'POST',
            'url': '/v1/responses', 'body': body}


def select_cases(root, requested=None, limit=None):
    rows = queue.ledger.catalog(root)
    processed = queue.existing_sol(root)
    selected, unpromptable = [], []
    requested = set(requested or [])
    unknown = requested - set(rows)
    if unknown:
        raise ValueError('Unknown case IDs: ' + ', '.join(sorted(unknown)))
    for case_id, row in sorted(rows.items()):
        if requested and case_id not in requested:
            continue
        page = row.get('case_page')
        path = root / 'cases' / ((page or '') + '.md')
        if not page or not path.is_file():
            unpromptable.append({'case_id': case_id, 'reason': 'no usable local case page'})
        elif case_id not in processed:
            selected.append(case_id)
    if limit is not None:
        selected = selected[:limit]
    return selected, processed, unpromptable


def validate_request_file(path, expected_ids=None, provider='openai'):
    seen = set()
    count = 0
    with path.open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f'Blank JSONL line {number}')
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Invalid JSONL line {number}: {exc}') from exc
            required = {'custom_id', 'method', 'url', 'body'}
            if set(record) != required:
                raise ValueError(f'Wrong envelope fields on line {number}')
            custom_id = record['custom_id']
            if custom_id in seen:
                raise ValueError('Duplicate custom_id: ' + custom_id)
            seen.add(custom_id)
            expected_endpoint = '/v1/responses' if provider == 'openai' else '/responses'
            if record['method'] != 'POST' or record['url'] != expected_endpoint:
                raise ValueError(f'Wrong method or endpoint on line {number}')
            body = record['body']
            if provider == 'openai':
                if body.get('prompt_cache_options') != {'mode': 'explicit', 'ttl': '30m'}:
                    raise ValueError(f'Cache settings missing on line {number}')
                content = body.get('input', [{}])[0].get('content', [{}])[0]
                if content.get('prompt_cache_breakpoint') != {'mode': 'explicit'}:
                    raise ValueError(f'Cache breakpoint missing on line {number}')
            elif provider == 'deepseek':
                if not isinstance(body.get('instructions'), str):
                    raise ValueError(f'Stable instructions missing on line {number}')
                unsupported = {'prompt_cache_options', 'prompt_cache_key',
                               'prompt_cache_retention', 'store', 'metadata'} & set(body)
                if unsupported:
                    raise ValueError(f'Unsupported DeepSeek fields on line {number}: '
                                     + ', '.join(sorted(unsupported)))
            else:
                raise ValueError('Unknown provider: ' + provider)
            fmt = body.get('text', {}).get('format', {})
            if fmt.get('type') != 'json_schema':
                raise ValueError(f'JSON schema missing on line {number}')
            if provider == 'openai' and not fmt.get('strict'):
                raise ValueError(f'Strict JSON schema missing on line {number}')
            count += 1
    if expected_ids is not None:
        expected = {'pca-synopsis-' + value for value in expected_ids}
        if seen != expected:
            raise ValueError('Request IDs do not match manifest')
    if path.stat().st_size > 200_000_000:
        raise ValueError('Batch input exceeds 200 MB')
    return {'requests': count, 'bytes': path.stat().st_size}


def build(folder, model='gpt-5.6-sol', reasoning_effort='medium',
          max_output_tokens=12000, requested=None, limit=None,
          shard_requests=DEFAULT_SHARD_REQUESTS,
          shard_estimated_tokens=DEFAULT_SHARD_ESTIMATED_TOKENS):
    if folder.exists():
        raise ValueError('Refusing to overwrite campaign: ' + str(folder))
    selected, processed, unpromptable = select_cases(ROOT, requested, limit)
    if not selected:
        raise ValueError('No unprocessed, promptable cases selected')
    folder.mkdir(parents=True)
    (folder / 'final').mkdir()
    (folder / 'first-drafts').mkdir()
    rows = queue.ledger.catalog(ROOT)
    if shard_requests < 1 or shard_estimated_tokens < 1:
        raise ValueError('Shard limits must be positive')
    entries, encoded = [], []
    developer_chars = len(compact.build_developer_prompt(ROOT))
    for case_id in selected:
        row = rows[case_id]
        benchmark_examples = compact.examples(row)
        record = request_record(ROOT, case_id, model, reasoning_effort,
                                max_output_tokens, benchmark_examples)
        line = json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n'
        source = ROOT / 'cases' / (row['case_page'] + '.md')
        entry = {
            'case_id': case_id,
            'custom_id': record['custom_id'],
            'source': source.relative_to(ROOT).as_posix(),
            'source_sha256': queue.ledger.file_hash(source),
            'benchmark_examples': benchmark_examples,
            'developer_chars': developer_chars,
            'case_prompt_chars': len(compact.build_case_prompt(ROOT, case_id)),
            # Deliberately conservative; JSON escaping and schema are included.
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
        request_path = folder / f'requests-{number:03d}.jsonl'
        with request_path.open('x', encoding='utf-8', newline='\n') as stream:
            for _, line in group:
                stream.write(line)
        ids = [entry['case_id'] for entry, _ in group]
        validation = validate_request_file(request_path, ids)
        request_files.append({
            'shard': number,
            'path': request_path.relative_to(ROOT).as_posix(),
            'sha256': queue.ledger.file_hash(request_path),
            'request_count': validation['requests'],
            'request_bytes': validation['bytes'],
            'estimated_input_tokens': sum(
                entry['estimated_input_tokens'] for entry, _ in group),
            'case_ids': ids,
        })
    references = {path: queue.ledger.file_hash(ROOT / path) for path in queue.REFERENCES}
    manifest = {
        'schema_version': 1, 'created_at': now(), 'provider': 'openai',
        'endpoint': '/v1/responses',
        'model': model, 'reasoning_effort': reasoning_effort,
        'max_output_tokens': max_output_tokens,
        'cache': {'mode': 'explicit', 'ttl': '30m',
                  'breakpoint': 'end of compact developer contract'},
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
                   'Generated candidates require source audit and are not published.'),
    }
    queue.ledger.save(folder / 'manifest.json', manifest)
    queue.ledger.save(folder / 'schema.json', api_schema())
    queue.ledger.save(folder / 'validation-schema.json', compact.schema())
    queue.ledger.save(folder / 'runs.json', {'schema_version': 1, 'arms': [{
        'model': model, 'reasoning_effort': reasoning_effort,
        'output_directory': (folder / 'final').relative_to(ROOT).as_posix()}]})
    return {'campaign': folder.relative_to(ROOT).as_posix(),
            'selected': len(selected), 'excluded_processed': len(processed),
            'unpromptable': len(unpromptable), 'shards': len(request_files),
            'request_bytes': manifest['request_bytes'],
            'estimated_input_tokens': manifest['estimated_input_tokens'],
            'request_files': request_files}


def verify_campaign(folder):
    manifest = queue.ledger.read(folder / 'manifest.json')
    provider = manifest.get('provider', 'openai')
    validations = []
    all_ids = []
    for item in manifest['request_files']:
        request_path = queue.inside(ROOT, item['path'])
        if queue.ledger.file_hash(request_path) != item['sha256']:
            raise ValueError('Request file hash changed: ' + item['path'])
        validations.append(validate_request_file(request_path, item['case_ids'], provider))
        all_ids.extend(item['case_ids'])
    for path, digest in manifest['reference_hashes'].items():
        if queue.ledger.file_hash(ROOT / path) != digest:
            raise ValueError('Reference changed after build: ' + path)
    ids = [entry['case_id'] for entry in manifest['selected']]
    if all_ids != ids:
        raise ValueError('Shard case IDs do not match selected manifest order')
    for entry in manifest['selected']:
        source = queue.inside(ROOT, entry['source'])
        if queue.ledger.file_hash(source) != entry['source_sha256']:
            raise ValueError('Case source changed after build: ' + entry['case_id'])
    return manifest, validations


def shard_record(manifest, shard):
    matches = [item for item in manifest['request_files'] if item['shard'] == shard]
    if not matches:
        raise ValueError(f'Unknown shard {shard}')
    return matches[0]


def preflight(folder):
    """Verify the frozen campaign and summarize local execution state."""
    manifest, validations = verify_campaign(folder)
    shards = []
    for item, validation in zip(manifest['request_files'], validations):
        shard = item['shard']
        receipt_path = folder / f'submission-{shard:03d}.json'
        receipt = queue.ledger.read(receipt_path) if receipt_path.exists() else None
        batch = (receipt or {}).get('batch') or {}
        shards.append({
            'shard': shard,
            'request_count': item['request_count'],
            'estimated_input_tokens': item['estimated_input_tokens'],
            'request_validation': validation,
            'submission_state': (
                'batch_created' if batch.get('id') else
                'upload_recorded_without_batch' if receipt else
                'not_submitted'),
            'batch_id': batch.get('id'),
            'output_downloaded': (folder / f'output-{shard:03d}.jsonl').exists(),
            'errors_downloaded': (folder / f'errors-{shard:03d}.jsonl').exists(),
        })
    return {
        'campaign': folder.relative_to(ROOT).as_posix(),
        'integrity': 'passed',
        'model': manifest['model'],
        'reasoning_effort': manifest['reasoning_effort'],
        'request_count': manifest['request_count'],
        'estimated_input_tokens': manifest['estimated_input_tokens'],
        'api_key_configured': bool(os.environ.get('OPENAI_API_KEY')),
        'publication_authorized': manifest.get('publication_authorized', False),
        'shards': shards,
    }


def api_headers(api_key, content_type=None):
    headers = {'Authorization': 'Bearer ' + api_key}
    if content_type:
        headers['Content-Type'] = content_type
    return headers


def api_call(api_key, base_url, method, path, body=None, content_type='application/json',
             parse_json=True):
    data = None
    if body is not None:
        data = (json.dumps(body).encode('utf-8') if content_type == 'application/json'
                else body)
    request = urllib.request.Request(base_url.rstrip('/') + path, data=data, method=method,
                                     headers=api_headers(api_key, content_type if data else None))
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'OpenAI API {exc.code}: {detail}') from exc
    return json.loads(payload) if parse_json else payload


def upload_file(api_key, base_url, path):
    boundary = '----pca-ga-' + uuid.uuid4().hex
    chunks = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nbatch\r\n'.encode(),
        (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
         f'filename="{path.name}"\r\nContent-Type: application/jsonl\r\n\r\n').encode(),
        path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
    return api_call(api_key, base_url, 'POST', '/v1/files', b''.join(chunks),
                    'multipart/form-data; boundary=' + boundary)


def require_key():
    value = os.environ.get('OPENAI_API_KEY')
    if not value:
        raise ValueError('OPENAI_API_KEY is not set')
    return value


def submit(folder, base_url, shard, allow_resubmit=False):
    manifest, validations = verify_campaign(folder)
    item = shard_record(manifest, shard)
    request_path = queue.inside(ROOT, item['path'])
    validation = validations[shard - 1]
    receipt_path = folder / f'submission-{shard:03d}.json'
    if receipt_path.exists() and not allow_resubmit:
        raise ValueError(
            f'{receipt_path.name} exists; refusing a duplicate paid submission')
    api_key = require_key()
    uploaded = upload_file(api_key, base_url, request_path)
    receipt = {'submitted_at': now(), 'request_validation': validation,
               'input_file': uploaded, 'batch': None}
    queue.ledger.save(receipt_path, receipt)
    batch = create_batch(api_key, base_url, manifest, folder, shard, item,
                         uploaded['id'])
    receipt['batch'] = batch
    queue.ledger.save(receipt_path, receipt)
    return batch


def create_batch(api_key, base_url, manifest, folder, shard, item, input_file_id):
    return api_call(api_key, base_url, 'POST', '/v1/batches', {
        'input_file_id': input_file_id, 'endpoint': manifest['endpoint'],
        'completion_window': '24h', 'metadata': {
            'purpose': 'pca-ga judicial synopses',
            'campaign': folder.name[:64], 'shard': str(shard),
            'request_sha256': item['sha256'][:64]}})


def retry_disposition(batch):
    """Classify whether retrying would duplicate successful Batch API work."""
    state = batch.get('status')
    counts = batch.get('request_counts') or {}
    completed = counts.get('completed') or 0
    if state in {'validating', 'in_progress', 'finalizing', 'cancelling'}:
        return 'still_running'
    if state == 'completed':
        return 'download'
    if state not in {'failed', 'expired', 'cancelled'}:
        return 'unknown_state'
    if completed or batch.get('output_file_id'):
        return 'partial_results'
    return 'retry_zero_success'


def retry(folder, base_url, shard):
    """Retry only a terminal batch that produced no successful requests."""
    manifest, _ = verify_campaign(folder)
    item = shard_record(manifest, shard)
    receipt_path = folder / f'submission-{shard:03d}.json'
    if not receipt_path.exists():
        raise ValueError(f'{receipt_path.name} does not exist; use Submit first')
    receipt = queue.ledger.read(receipt_path)
    current = receipt.get('batch') or {}
    current_id = current.get('id')
    if not current_id:
        raise ValueError('Submission receipt has no batch ID; inspect the partial receipt')

    api_key = require_key()
    current = api_call(api_key, base_url, 'GET', '/v1/batches/' + current_id)
    queue.ledger.save(folder / f'batch-status-{shard:03d}.json', current)
    disposition = retry_disposition(current)
    if disposition == 'still_running':
        return {'action': 'not_resubmitted', 'reason': 'batch is still running',
                'batch': current}
    if disposition == 'download':
        return {'action': 'not_resubmitted', 'reason': 'batch completed; download it',
                'batch': current}
    if disposition == 'partial_results':
        raise ValueError(
            'Recorded batch has successful or downloadable output; download it and '
            'build a remainder-only retry instead of resubmitting the whole shard')
    if disposition == 'unknown_state':
        raise ValueError('Recorded batch has unrecognized status: ' + str(current.get('status')))

    replacement = create_batch(
        api_key, base_url, manifest, folder, shard, item,
        receipt['input_file']['id'])
    history = list(receipt.get('previous_batches') or [])
    history.append(current)
    receipt['previous_batches'] = history
    receipt['retried_at'] = now()
    receipt['batch'] = replacement
    queue.ledger.save(receipt_path, receipt)
    return {'action': 'resubmitted_terminal_zero_success_batch',
            'previous_batch_id': current_id, 'batch': replacement}


def batch_id(folder, shard, explicit=None):
    if explicit:
        return explicit
    receipt = queue.ledger.read(folder / f'submission-{shard:03d}.json')
    return receipt['batch']['id']


def status(folder, base_url, shard, explicit=None):
    return api_call(require_key(), base_url, 'GET',
                    '/v1/batches/' + batch_id(folder, shard, explicit))


def download(folder, base_url, shard, explicit=None):
    api_key = require_key()
    batch = status(folder, base_url, shard, explicit)
    queue.ledger.save(folder / f'batch-status-{shard:03d}.json', batch)
    downloaded = {}
    for field, stem in (('output_file_id', 'output'), ('error_file_id', 'errors')):
        file_id = batch.get(field)
        if file_id:
            data = api_call(api_key, base_url, 'GET', '/v1/files/' + file_id + '/content',
                            parse_json=False)
            target = folder / f'{stem}-{shard:03d}.jsonl'
            if target.exists():
                raise ValueError('Refusing to overwrite downloaded file: ' + str(target))
            target.write_bytes(data)
            downloaded[field] = target.relative_to(ROOT).as_posix()
    if not downloaded:
        raise ValueError('Batch has no downloadable output or error file yet')
    return {'status': batch.get('status'), 'downloaded': downloaded}


def validate_value(value, spec, path='$'):
    kind = spec.get('type')
    good = ((kind == 'object' and isinstance(value, dict)) or
            (kind == 'array' and isinstance(value, list)) or
            (kind == 'string' and isinstance(value, str)) or
            (kind == 'integer' and isinstance(value, int) and not isinstance(value, bool)) or
            (kind == 'boolean' and isinstance(value, bool)))
    if not good:
        raise ValueError(f'{path}: expected {kind}')
    if kind == 'object':
        missing = set(spec.get('required', [])) - set(value)
        if missing:
            raise ValueError(f'{path}: missing {sorted(missing)}')
        if spec.get('additionalProperties') is False:
            extras = set(value) - set(spec.get('properties', {}))
            if extras:
                raise ValueError(f'{path}: extra fields {sorted(extras)}')
        for key, child in value.items():
            if key in spec.get('properties', {}):
                validate_value(child, spec['properties'][key], path + '.' + key)
    elif kind == 'array':
        if len(value) < spec.get('minItems', 0):
            raise ValueError(f'{path}: too few items')
        if spec.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            raise ValueError(f'{path}: duplicate items')
        for index, child in enumerate(value):
            validate_value(child, spec['items'], f'{path}[{index}]')
    elif kind == 'string' and len(value) < spec.get('minLength', 0):
        raise ValueError(f'{path}: string is empty')
    elif kind == 'integer':
        if value < spec.get('minimum', value) or value > spec.get('maximum', value):
            raise ValueError(f'{path}: integer outside range')


def output_text(body):
    texts = []
    for item in body.get('output', []):
        if item.get('type') != 'message':
            continue
        for content in item.get('content', []):
            if content.get('type') == 'output_text' and isinstance(content.get('text'), str):
                texts.append(content['text'])
            elif content.get('type') == 'refusal':
                raise ValueError('Model refusal: ' + str(content.get('refusal')))
    if not texts:
        raise ValueError('Response contains no output_text')
    return ''.join(texts)


def normalize_benchmark_examples(candidate, entry):
    """Repair annotated benchmark IDs without accepting unprovided examples.

    Early requests described this field as an array of IDs, but did not constrain
    each item to the supplied IDs. Sol therefore often returned strings such as
    ``C01 illustrates ...``. Keep only IDs supplied in the case packet. When a
    response contains only generic benchmark prose, use the complete supplied set
    and record that fallback in the ingestion report.
    """
    claimed = candidate.get('benchmark_examples')
    allowed = list(entry['benchmark_examples'])
    if not isinstance(claimed, list) or not all(isinstance(v, str) for v in claimed):
        return candidate, None
    if claimed and all(value in allowed for value in claimed):
        return candidate, None

    mentioned = []
    for value in claimed:
        for benchmark_id in BENCHMARK_ID.findall(value):
            if benchmark_id not in mentioned:
                mentioned.append(benchmark_id)
    if any(value not in allowed for value in mentioned):
        return candidate, None

    normalized = [value for value in mentioned if value in allowed]
    reason = 'extracted supplied benchmark IDs from annotated strings'
    if not normalized and claimed:
        normalized = allowed
        reason = 'generic benchmark prose normalized to the examples supplied in the request'
    if not normalized:
        return candidate, None

    repaired = dict(candidate)
    repaired['benchmark_examples'] = normalized
    return repaired, {
        'original': claimed,
        'normalized': normalized,
        'reason': reason,
    }


def validate_candidate(candidate, entry):
    validate_value(candidate, compact.schema())
    if candidate['case_id'] != entry['case_id']:
        raise ValueError('Candidate case_id does not match custom_id')
    if candidate['matter_type'] not in MATTER_TYPES:
        raise ValueError('Unknown matter_type: ' + candidate['matter_type'])
    unknown = set(candidate['final_dispositions']) - DISPOSITIONS
    if unknown:
        raise ValueError('Unknown final dispositions: ' + ', '.join(sorted(unknown)))
    expected_source = (entry['source'], entry['source_sha256'])
    supplied = {(item['path'], item['sha256']) for item in candidate['sources']}
    if expected_source not in supplied:
        raise ValueError('Required case source path/hash is missing')
    unknown_examples = set(candidate['benchmark_examples']) - set(entry['benchmark_examples'])
    if unknown_examples:
        raise ValueError('Candidate claims unprovided benchmark examples')


def save_candidate(path, value):
    if path.exists():
        if queue.ledger.read(path) != value:
            raise ValueError('Refusing to overwrite a different candidate: ' + str(path))
        return
    queue.ledger.save(path, value)


def ingest(folder, results_paths=None):
    manifest, _ = verify_campaign(folder)
    paths = list(results_paths or sorted(folder.glob('output-*.jsonl')))
    if not paths:
        raise ValueError('No result files supplied or downloaded')
    entries = {entry['custom_id']: entry for entry in manifest['selected']}
    seen, accepted, failures = set(), [], []
    usage = {'input_tokens': 0, 'cached_tokens': 0, 'cache_write_tokens': 0,
             'output_tokens': 0, 'reasoning_tokens': 0}
    for path in paths:
        with path.open(encoding='utf-8') as stream:
            for number, line in enumerate(stream, 1):
                try:
                    record = json.loads(line)
                    custom_id = record['custom_id']
                    if custom_id in seen:
                        raise ValueError('duplicate custom_id')
                    seen.add(custom_id)
                    if custom_id not in entries:
                        raise ValueError('custom_id not present in manifest')
                    response = record.get('response') or {}
                    if response.get('status_code') != 200:
                        raise ValueError('HTTP status ' + str(response.get('status_code')))
                    body = response.get('body') or {}
                    if body.get('status') != 'completed':
                        raise ValueError('Response status ' + str(body.get('status')))
                    candidate = json.loads(output_text(body))
                    entry = entries[custom_id]
                    candidate, benchmark_normalization = normalize_benchmark_examples(
                        candidate, entry)
                    validate_candidate(candidate, entry)
                    first = dict(candidate)
                    first['summary'] = candidate['first_summary']
                    filename = case_filename(entry['case_id'])
                    save_candidate(folder / 'first-drafts' / filename, first)
                    save_candidate(folder / 'final' / filename, candidate)
                    detail = body.get('usage') or {}
                    input_detail = detail.get('input_tokens_details') or {}
                    output_detail = detail.get('output_tokens_details') or {}
                    usage['input_tokens'] += detail.get('input_tokens') or 0
                    usage['cached_tokens'] += input_detail.get('cached_tokens') or 0
                    usage['cache_write_tokens'] += input_detail.get('cache_write_tokens') or 0
                    usage['output_tokens'] += detail.get('output_tokens') or 0
                    usage['reasoning_tokens'] += output_detail.get('reasoning_tokens') or 0
                    accepted_item = {'case_id': entry['case_id'],
                        'fidelity': candidate['scores']['fidelity'],
                        'repair_needed': candidate['repair_needed'],
                        'status': 'awaiting_source_audit'}
                    if benchmark_normalization:
                        accepted_item['benchmark_normalization'] = benchmark_normalization
                    accepted.append(accepted_item)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    failures.append({'file': str(path), 'line': number,
                                     'error': str(exc)})
    missing = sorted(set(entries) - seen)
    source_results = [path.resolve().relative_to(ROOT).as_posix()
                      if path.resolve().is_relative_to(ROOT) else str(path.resolve())
                      for path in paths]
    report = {'ingested_at': now(), 'source_results': source_results,
              'accepted_count': len(accepted), 'failure_count': len(failures),
              'missing_count': len(missing), 'accepted': accepted,
              'failures': failures, 'missing_custom_ids': missing, 'usage': usage,
              'publication_authorized': False,
              'next_step': 'Audit every candidate against its case source before publication.'}
    queue.ledger.save(folder / 'ingestion-report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', default=DEFAULT_CAMPAIGN)
    parser.add_argument('--base-url', default=os.environ.get('OPENAI_BASE_URL', DEFAULT_BASE_URL))
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('preflight', help='Verify the frozen campaign and show shard state')
    build_parser = sub.add_parser('build', help='Generate and validate sharded JSONL locally')
    build_parser.add_argument('--model', default='gpt-5.6-sol')
    build_parser.add_argument('--reasoning-effort', default='medium',
                              choices=['none', 'low', 'medium', 'high', 'xhigh', 'max'])
    build_parser.add_argument('--max-output-tokens', type=int, default=12000)
    build_parser.add_argument('--case', action='append', dest='cases')
    build_parser.add_argument('--limit', type=int)
    build_parser.add_argument('--shard-requests', type=int,
                              default=DEFAULT_SHARD_REQUESTS)
    build_parser.add_argument('--shard-estimated-tokens', type=int,
                              default=DEFAULT_SHARD_ESTIMATED_TOKENS)
    sub.add_parser('validate', help='Recheck hashes and JSONL without API access')
    submit_parser = sub.add_parser('submit', help='Upload the file and create a paid batch')
    submit_parser.add_argument('--shard', type=int, required=True)
    submit_parser.add_argument('--allow-resubmit', action='store_true')
    retry_parser = sub.add_parser(
        'retry', help='Safely replace a terminal zero-success batch')
    retry_parser.add_argument('--shard', type=int, required=True)
    status_parser = sub.add_parser('status', help='Fetch batch status')
    status_parser.add_argument('--shard', type=int, required=True)
    status_parser.add_argument('--batch-id')
    download_parser = sub.add_parser('download', help='Download available result/error files')
    download_parser.add_argument('--shard', type=int, required=True)
    download_parser.add_argument('--batch-id')
    ingest_parser = sub.add_parser('ingest', help='Validate results into audit candidates')
    ingest_parser.add_argument('--results', type=Path, action='append')
    args = parser.parse_args(argv)
    folder = campaign_path(args.campaign)
    if args.action == 'preflight':
        result = preflight(folder)
    elif args.action == 'build':
        result = build(folder, args.model, args.reasoning_effort,
                       args.max_output_tokens, args.cases, args.limit,
                       args.shard_requests, args.shard_estimated_tokens)
    elif args.action == 'validate':
        manifest, validations = verify_campaign(folder)
        result = {'request_count': manifest['request_count'],
                  'shards': len(validations), 'validations': validations}
    elif args.action == 'submit':
        result = submit(folder, args.base_url, args.shard, args.allow_resubmit)
    elif args.action == 'retry':
        result = retry(folder, args.base_url, args.shard)
    elif args.action == 'status':
        result = status(folder, args.base_url, args.shard, args.batch_id)
    elif args.action == 'download':
        result = download(folder, args.base_url, args.shard, args.batch_id)
    else:
        result = ingest(folder, args.results)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
