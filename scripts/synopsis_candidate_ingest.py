"""Build a provider-aware synopsis candidate registry for source audit.

This is an intake step, not editorial approval or publication. It combines
existing Sol drafts with only the DeepSeek candidates that passed the frozen
conservative gate, while retaining paths, hashes, and model provenance.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import synopsis_batch_api as common
import synopsis_deepseek_gate as deepseek_gate
import synopsis_queue as queue


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEEPSEEK_CAMPAIGN = 'index/synopsis_workflow/deepseek-v4.1-flash-1'
DEFAULT_OUTPUT = 'index/synopsis_workflow/candidate-intake-1/registry.json'


def canonical_id(value):
    import re
    match = re.fullmatch(r'\s*(\d{4})-(\d{1,3})([a-z]?)\s*', str(value or ''), re.I)
    if not match:
        return None
    return f'{match.group(1)}-{int(match.group(2)):02d}{match.group(3).lower()}'


def identity_rules(root):
    path = root / 'index/case_identity_overrides.json'
    if not path.exists():
        return []
    payload = queue.ledger.read(path)
    rules = payload.get('overrides', []) if isinstance(payload, dict) else payload
    return [rule for rule in rules if rule.get('status') == 'approved']


def resolved_identity(case_id, title, rules):
    source_id = canonical_id(case_id)
    caption = str(title or '').casefold()
    for rule in rules:
        if canonical_id(rule.get('roster_id')) != source_id:
            continue
        discriminator = str(rule.get('title_contains') or '').strip().casefold()
        if discriminator and discriminator not in caption:
            continue
        corrected = canonical_id(rule.get('canonical_id'))
        if corrected:
            return corrected
    return source_id


def remap_candidates(root, candidates, catalog, rules):
    """Attach legacy-ID candidates only when their evidence is the current page."""
    remapped = defaultdict(list)
    quarantined = []
    ids_by_page = defaultdict(list)
    for case_id, row in catalog.items():
        if row.get('case_page'):
            ids_by_page[f"cases/{row['case_page']}.md"].append(case_id)
    for source_id, records in candidates.items():
        for record in records:
            candidate = queue.ledger.read(queue.inside(root, record['path']))
            target_id = resolved_identity(source_id, candidate.get('title'), rules)
            source_paths = {
                str(item.get('path') or '') for item in candidate.get('sources') or []
            }
            # Some carried-case candidate captions omit the surname used by the
            # roster rule.  An exact, unique match to the current canonical page
            # is stronger evidence than fuzzy title matching.
            if not target_id or target_id not in catalog:
                page_targets = {
                    case_id for path in source_paths for case_id in ids_by_page.get(path, [])
                }
                if len(page_targets) == 1:
                    target_id = next(iter(page_targets))
            if not target_id or target_id not in catalog:
                quarantined.append({
                    'case_id': source_id,
                    'reason': 'candidate_identity_absent_from_current_catalog',
                    'path': record['path'],
                })
                continue
            if target_id != source_id:
                expected_page = catalog[target_id].get('case_page')
                expected_path = f'cases/{expected_page}.md' if expected_page else None
                if expected_path and expected_path not in source_paths:
                    quarantined.append({
                        'case_id': source_id,
                        'target_case_id': target_id,
                        'reason': 'remapped_candidate_does_not_cite_current_case_page',
                        'expected_source': expected_path,
                        'candidate_sources': sorted(source_paths),
                        'path': record['path'],
                    })
                    continue
                record = {
                    **record,
                    'identity_remapped_from': source_id,
                    'identity_rule': 'minutes_verified_case_identity_override',
                }
            remapped[target_id].append(record)
    return dict(remapped), quarantined


def now():
    return datetime.now(timezone.utc).isoformat()


def relative(root, path):
    return path.resolve().relative_to(root.resolve()).as_posix()


def verify_completed_campaign(root, folder):
    """Verify immutable requests and evidence; report later instruction edits.

    A changed instruction reference blocks a new API submission, but it does not
    retroactively corrupt a completed response. Preserve that fact for audit.
    """
    manifest = queue.ledger.read(folder / 'manifest.json')
    provider = manifest.get('provider', 'openai')
    all_ids = []
    for item in manifest['request_files']:
        request_path = queue.inside(root, item['path'])
        if queue.ledger.file_hash(request_path) != item['sha256']:
            raise ValueError('Request file hash changed: ' + item['path'])
        common.validate_request_file(request_path, item['case_ids'], provider)
        all_ids.extend(item['case_ids'])
    selected_ids = [entry['case_id'] for entry in manifest['selected']]
    if all_ids != selected_ids:
        raise ValueError('Shard case IDs do not match selected manifest order')
    changed_sources = []
    for entry in manifest['selected']:
        source = queue.inside(root, entry['source'])
        if (not source.is_file()
                or queue.ledger.file_hash(source) != entry['source_sha256']):
            changed_sources.append(entry['case_id'])
    changed_references = [
        path for path, digest in manifest['reference_hashes'].items()
        if queue.ledger.file_hash(root / path) != digest
    ]
    return manifest, changed_references, changed_sources


def load_deepseek(root, campaign_name):
    folder = queue.inside(root, campaign_name)
    manifest, changed_references, changed_sources = verify_completed_campaign(root, folder)
    report_path = folder / 'gate' / 'report.json'
    report = queue.ledger.read(report_path)
    if report.get('policy') != 'deepseek-conservative-gate-v1':
        raise ValueError('Unexpected DeepSeek gate policy')
    if report.get('publication_authorized') is not False:
        raise ValueError('DeepSeek gate must not authorize publication')

    entries = {item['case_id']: item for item in manifest['selected']}
    accepted_rows = report.get('accepted') or []
    accepted_ids = [item['case_id'] for item in accepted_rows]
    if len(accepted_ids) != len(set(accepted_ids)):
        raise ValueError('Duplicate case ID in DeepSeek gate report')
    if report.get('accepted_count') != len(accepted_ids):
        raise ValueError('DeepSeek accepted count does not match gate report')
    stale_accepted = sorted(set(accepted_ids) & set(changed_sources))

    accepted_dir = folder / 'gate' / 'accepted'
    actual_names = {path.name for path in accepted_dir.glob('*.json')}
    expected_names = {common.case_filename(case_id) for case_id in accepted_ids}
    if actual_names != expected_names:
        raise ValueError('DeepSeek accepted files do not match gate report')

    candidates = {}
    for case_id in sorted(accepted_ids):
        if case_id in stale_accepted:
            continue
        if case_id not in entries:
            raise ValueError('DeepSeek gate case missing from manifest: ' + case_id)
        path = accepted_dir / common.case_filename(case_id)
        candidate = queue.ledger.read(path)
        entry = entries[case_id]
        deepseek_gate.validate_candidate(candidate, entry)
        reasons = deepseek_gate.candidate_reasons(candidate, entry)
        if reasons:
            raise ValueError(
                'DeepSeek accepted candidate no longer passes gate: '
                + case_id + ' (' + ', '.join(reasons) + ')')
        candidates[case_id] = [{
            'provider': manifest.get('provider', 'deepseek'),
            'model': manifest.get('model_version_label', manifest.get('model')),
            'reasoning_effort': manifest.get('reasoning_effort'),
            'path': relative(root, path),
            'sha256': queue.ledger.file_hash(path),
            'provenance': relative(root, report_path),
            'route': 'deepseek_conservative_gate_pass',
            'gate_policy': report['policy'],
            'source_hashes_match': True,
            'status': 'awaiting_source_audit',
            'publication_approved': False,
        }]
    return candidates, changed_references, changed_sources, stale_accepted


def load_sol(root):
    candidates = queue.existing_sol(root)
    stale = []
    for case_id, records in candidates.items():
        kept = []
        for record in records:
            path = queue.inside(root, record['path'])
            if queue.ledger.file_hash(path) != record['sha256']:
                raise ValueError('Sol candidate hash changed: ' + case_id)
            if not record.get('source_hashes_match'):
                stale.append(case_id)
                continue
            record.update({
                'provider': 'openai',
                'model': 'gpt-5.6-sol',
                'route': 'existing_sol_draft',
                'status': 'awaiting_source_audit',
                'publication_approved': False,
            })
            kept.append(record)
        candidates[case_id] = kept
    return {key: value for key, value in candidates.items() if value}, sorted(set(stale))


def build_registry(root, deepseek_campaign=DEFAULT_DEEPSEEK_CAMPAIGN):
    deepseek, changed_references, changed_sources, stale_deepseek = load_deepseek(
        root, deepseek_campaign)
    sol, stale_sol = load_sol(root)
    catalog = queue.ledger.catalog(root)
    rules = identity_rules(root)
    sol, quarantined_sol = remap_candidates(root, sol, catalog, rules)
    deepseek, quarantined_deepseek = remap_candidates(root, deepseek, catalog, rules)
    all_ids = sorted(set(deepseek) | set(sol))
    candidates, conflicts = [], []

    for case_id in all_ids:
        sol_options = sol.get(case_id, [])
        deepseek_options = deepseek.get(case_id, [])
        options = sol_options + deepseek_options
        if len(sol_options) > 1:
            conflicts.append({
                'case_id': case_id,
                'reason': 'multiple_sol_candidates',
                'paths': [item['path'] for item in sol_options],
            })
            continue
        # Sol is the higher-reliability lane and takes precedence if both exist.
        selected = sol_options[0] if sol_options else deepseek_options[0]
        candidates.append({
            'case_id': case_id,
            'selected': selected,
            'alternatives': [item for item in options if item is not selected],
            'status': 'awaiting_source_audit',
            'publication_approved': False,
        })

    catalog_ids = set(catalog)
    selected_ids = {item['case_id'] for item in candidates}
    return {
        'schema_version': 1,
        'generated_at': now(),
        'policy': (
            'Select existing Sol drafts first; otherwise select only DeepSeek '
            'candidates passing deepseek-conservative-gate-v1. Every selection '
            'requires source audit before approval or publication.'),
        'publication_authorized': False,
        'input_integrity': {
            'request_files_match': True,
            'accepted_case_sources_match': True,
            'changed_rejected_or_unselected_case_sources': changed_sources,
            'stale_selected_candidates_omitted': {
                'sol': stale_sol,
                'deepseek': stale_deepseek,
            },
            'identity_candidates_quarantined': quarantined_sol + quarantined_deepseek,
            'instruction_references_match': not changed_references,
            'changed_instruction_references': changed_references,
            'note': (
                'Later instruction edits do not alter completed candidates; '
                'apply the current rubric during source audit.'),
        },
        'counts': {
            'catalog_cases': len(catalog_ids),
            'selected_cases': len(candidates),
            'sol_cases': len(sol),
            'deepseek_gate_cases': len(deepseek),
            'provider_overlaps': len(set(sol) & set(deepseek)),
            'conflicts': len(conflicts),
            'catalog_cases_without_candidate': len(catalog_ids - selected_ids),
        },
        'candidates': candidates,
        'conflicts': conflicts,
        'catalog_case_ids_without_candidate': sorted(catalog_ids - selected_ids),
        'candidate_ids_not_in_catalog': sorted(selected_ids - catalog_ids),
        'next_step': 'Audit each selected candidate against its cited case source.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deepseek-campaign', default=DEFAULT_DEEPSEEK_CAMPAIGN)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    output = queue.inside(ROOT, args.output)
    report = build_registry(ROOT, args.deepseek_campaign)
    queue.ledger.save(output, report)
    display = dict(report['counts'])
    display.update({
        'publication_authorized': report['publication_authorized'],
        'written_to': relative(ROOT, output),
        'next_step': report['next_step'],
    })
    print(json.dumps(display, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
