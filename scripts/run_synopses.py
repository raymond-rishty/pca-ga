"""Mechanical Codex runner. No model calls except explicit `run` commands.

Uses the existing ChatGPT login, app-server usage reads, and ephemeral codex exec
workers. Never consumes reset credits or publishes editorial candidates.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue as messages
import shutil
import subprocess
import sys
import threading
import time

import synopsis_queue as q

FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def preflight(codex, root, folder):
    data = q.ledger.read(folder / 'queue.json')
    queued = {e['case_id'] for e in data['cases'] if e['state'] == 'queued'}
    selected = next((n for n, keys in enumerate(data['batches'], 1) if queued.intersection(keys)), None)
    if selected is None:
        return {'status': 'nothing queued'}
    target = folder / f'batch-{selected:02d}'
    args = [codex, 'sandbox', '-P', 'synopsis_preflight',
            '-c', 'permissions.synopsis_preflight.extends=":workspace"',
            '--include-managed-config', '-C', str(root), sys.executable,
            str(root / 'scripts/synopsis_preflight.py'), '--root', str(root), '--target', str(target)]
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                            timeout=45, creationflags=FLAGS)
    receipt = {'checked_at': q.now(), 'batch': selected, 'command': args,
               'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    q.ledger.save(folder / 'preflight.json', receipt)
    if result.returncode != 0:
        raise RuntimeError('Sandbox preflight failed; no model launched. See preflight.json')
    # Successful process exit alone is insufficient.
    body = json.loads(result.stdout)
    if body.get('status') != 'passed' or body.get('write_read_delete') is not True:
        raise RuntimeError('Sandbox preflight did not confirm file access')
    return body


def read_usage(codex, timeout=30):
    """Read-only JSON-RPC. No raw auth files, API keys, or model calls."""
    proc = subprocess.Popen([codex, 'app-server', '--stdio'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding='utf-8', creationflags=FLAGS)
    inbox = messages.Queue()

    def receive():
        try:
            for line in proc.stdout:
                try:
                    inbox.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        finally:
            inbox.put(None)

    reader = threading.Thread(target=receive, daemon=True)
    reader.start()

    def send(value):
        proc.stdin.write(json.dumps(value) + '\n')
        proc.stdin.flush()

    def response(identifier):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Codex usage read timed out; no worker launched')
            try:
                value = inbox.get(timeout=remaining)
            except messages.Empty as error:
                raise TimeoutError('Codex usage read timed out') from error
            if value is None:
                raise RuntimeError('Codex app-server exited; check codex login status in a normal terminal')
            if value.get('id') == identifier:
                if 'error' in value:
                    raise RuntimeError('Codex usage RPC failed: ' + str(value['error'].get('code')))
                return value['result']
            if 'id' in value and 'method' in value:
                # Fail closed for unexpected auth/approval/elicitation requests.
                raise RuntimeError('Usage client cannot answer server request: ' + value['method'])

    try:
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'pca_synopsis_runner', 'version': '1.0.0'}}})
        response(1)
        send({'method': 'initialized'})
        send({'id': 2, 'method': 'account/rateLimits/read'})
        result = response(2)
        buckets = result.get('rateLimitsByLimitId')
        if not buckets:
            legacy = result.get('rateLimits')
            buckets = {legacy.get('limitId') or 'codex': legacy} if legacy else {}
        return {'captured_at': q.now(), 'rateLimitsByLimitId': buckets}
    finally:
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        reader.join(timeout=2)
        proc.stdout.close()


@contextmanager
def runner_lock(folder):
    path = folder / '.runner.lock'
    stream = path.open('x')
    try:
        stream.write(str(os.getpid()))
        stream.flush()
        yield
    finally:
        stream.close()
        path.unlink()


def event_metrics(path):
    totals, thread_id, completed, errors = None, None, False, 0
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get('type') == 'thread.started':
                thread_id = event.get('thread_id')
            elif event.get('type') == 'turn.completed':
                totals = event.get('usage')
                completed = True
            elif event.get('type') in ('error', 'turn.failed'):
                errors += 1
    return {'thread_id': thread_id, 'tokens': totals, 'turn_completed': completed,
            'error_events': errors, 'cost': None}


def command(codex, folder, claim, root=None):
    root = root or q.ROOT
    return [codex, 'exec', '--ephemeral', '--json', '--color', 'never',
            '--sandbox', 'workspace-write', '-C', str(root),
            '--disable', 'apps', '--disable', 'plugins', '--disable', 'remote_plugin',
            '-c', 'web_search="disabled"', '-c', 'mcp_servers.node_repl.enabled=false',
            '-m', claim['model'], '-c', 'model_reasoning_effort=' + json.dumps(claim['reasoning_effort']),
            '-c', 'approval_policy="never"', '-']


def execute(codex, root, folder, claim, attempt, timeout):
    target = folder / f"batch-{claim['batch']:02d}"
    prompt = (f'Repository root: {root}. Your output directory is {target}. '
              'Read source files and skill references from the repository root. '
              'You may write ONLY the requested first-drafts, final, blocked and run-notes '
              'inside this batch directory. Do not rewrite completed outputs. If a first '
              'draft already exists for a claimed case, preserve it and perform only the '
              'remaining source-check/finalization; do not redraft or overwrite it.\n' +
              (target / 'prompt.txt').read_text(encoding='utf-8') +
              '\nIMPORTANT: Process ONLY these currently claimed IDs, overriding the '
              'original assignment if necessary: ' + ', '.join(claim['case_ids']) + '.\n'
              'If a tool reports sandbox initialization/setup refresh failure, stop immediately. '
              'Do not retry through another tool, browser, web search, or remote repository.\n')
    args = command(codex, folder, claim, root)
    receipt = {'started_at': q.now(), 'command': args, 'case_ids': claim['case_ids'],
               'status': 'starting', 'worker_exit_code': None}
    q.ledger.save(attempt / 'worker.json', receipt)
    with (attempt / 'events.jsonl').open('x', encoding='utf-8') as output, \
            (attempt / 'stderr.txt').open('x', encoding='utf-8') as error:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=output, stderr=error,
                                text=True, encoding='utf-8', creationflags=FLAGS)
        receipt.update(pid=proc.pid, status='running')
        q.ledger.save(attempt / 'worker.json', receipt)
        try:
            proc.communicate(prompt, timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            receipt.update(status='interrupted_requires_reconciliation', ended_at=q.now())
            q.ledger.save(attempt / 'worker.json', receipt)
            # Descendant tool processes may outlive the CLI: do not requeue blindly.
            raise RuntimeError('Worker interrupted. Confirm all worker processes stopped before collect.')
    receipt.update(status='exited', ended_at=q.now(), worker_exit_code=proc.returncode,
                   **event_metrics(attempt / 'events.jsonl'))
    q.ledger.save(attempt / 'worker.json', receipt)
    return receipt


def report(root, folder):
    data = q.ledger.read(folder / 'queue.json')
    entries = []
    for entry in data['cases']:
        item = {k: entry[k] for k in ('case_id', 'state')}
        if entry.get('validation_error'):
            item['validation_error'] = entry['validation_error']
        for number, keys in enumerate(data['batches'], 1):
            if entry['case_id'] in keys:
                path = folder / f'batch-{number:02d}/final/{entry["case_id"]}.json'
                if path.exists():
                    item['candidate'] = path.relative_to(root).as_posix()
                    item['sha256'] = q.ledger.file_hash(path)
        entries.append(item)
    result = {'generated_at': q.now(), 'counts': dict(Counter(e['state'] for e in entries)),
              'publication_authorized': False, 'cases': entries,
              'runs': len(data['runs']), 'semantic_review': 'not performed by scripts'}
    q.ledger.save(folder / 'report.json', result)
    return result


def run(root, folder, codex, max_batches=1, timeout=1200,
        usage_reader=read_usage, worker=execute):
    with runner_lock(folder):
        for _ in range(max_batches):
            preflight(codex, root, folder)
            before = usage_reader(codex)
            claim = q.claim(root, folder, before)
            if claim['status'] != 'claimed':
                return {'status': claim['status'], 'report': report(root, folder)['counts']}
            data = q.ledger.read(folder / 'queue.json')
            attempt = folder / 'attempts' / f"run-{len(data['runs']):03d}"
            attempt.mkdir(parents=True, exist_ok=False)
            q.ledger.save(attempt / 'before.json', before)
            q.ledger.save(attempt / 'claim.json', claim)
            receipt = worker(codex, root, folder, claim, attempt, timeout)
            after = usage_reader(codex)
            q.ledger.save(attempt / 'after.json', after)
            q.finish(root, folder, after)
            counts = report(root, folder)['counts']
            # Never loop over a failed/empty worker or spend tokens on schema repair.
            if receipt['worker_exit_code'] != 0 or not receipt['turn_completed'] or any(
                    e['state'] != 'awaiting_audit' for e in q.ledger.read(folder / 'queue.json')['cases']
                    if e['case_id'] in claim['case_ids']):
                return {'status': 'paused: worker/output needs attention', 'report': counts}
        return {'status': 'batch limit reached', 'report': counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'preflight', 'run', 'collect', 'status'])
    parser.add_argument('--campaign', default='index/synopsis_workflow/sol-calibration-1')
    parser.add_argument('--codex', default=shutil.which('codex'))
    parser.add_argument('--max-batches', type=int, default=1)
    parser.add_argument('--timeout-seconds', type=int, default=1200)
    parser.add_argument('--confirm-worker-stopped', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_batches <= 100 or args.timeout_seconds <= 0:
        parser.error('Require 1..100 batches and a positive timeout')
    root, folder = q.ROOT, q.inside(q.ROOT, args.campaign)
    if args.action != 'status' and not args.codex:
        parser.error('Codex CLI not found; supply --codex PATH')
    if args.action == 'status':
        result = report(root, folder)
    elif args.action == 'preflight':
        with runner_lock(folder):
            result = preflight(args.codex, root, folder)
    elif args.action == 'check':
        q.freshness(root, folder, q.ledger.read(folder / 'queue.json'))
        result = {'status': q.gate(q.ledger.read(folder / 'queue.json'), read_usage(args.codex))}
    elif args.action == 'collect':
        if not args.confirm_worker_stopped:
            parser.error('collect requires --confirm-worker-stopped; never collect an active worker')
        with runner_lock(folder):
            result = q.finish(root, folder, read_usage(args.codex))
            report(root, folder)
    else:
        result = run(root, folder, args.codex, args.max_batches, args.timeout_seconds)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
