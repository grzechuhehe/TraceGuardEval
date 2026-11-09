"""Offline metrics with explicit missing/undefined denominators."""

from collections import Counter, defaultdict
from pathlib import Path

from traceguard_core.dataset import load_dataset, read_json, read_jsonl
from traceguard_core.evaluation import JudgeConfig, system_prompt
from traceguard_core.experiment import SplitRegistry, attempts_path, code_hash, load_references, verify_record
from traceguard_core.models import aggregate, digest


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def classification_metrics(rows: list[dict], references: dict, expected: int) -> dict:
    counts = Counter()
    for row in rows:
        reference = references[row['trace_id']]
        prediction = row['prediction']
        truth = reference['verdict']
        label = prediction['verdict']
        if truth not in {'PASS', 'FAIL'}:
            counts['unresolved_reference'] += 1
            continue
        if prediction['status'] == 'ERROR':
            counts['error'] += 1
        elif label in {'NA', 'INDETERMINATE'}:
            counts[label.lower()] += 1
        else:
            counts[{('FAIL', 'FAIL'): 'tp', ('PASS', 'FAIL'): 'fp',
                    ('FAIL', 'PASS'): 'fn', ('PASS', 'PASS'): 'tn'}[(truth, label)]] += 1
        if reference.get('critical_fail'):
            if prediction['status'] == 'OK' and label == 'PASS':
                counts['missed_critical'] += 1
            elif prediction['status'] == 'ERROR' or label not in {'PASS', 'FAIL'}:
                counts['unresolved_critical'] += 1
    tp, fp, fn, tn = [counts[k] for k in ('tp', 'fp', 'fn', 'tn')]
    resolved = tp + fp + fn + tn
    return {'expected': expected, 'recorded': len(rows), 'missing': expected - len(rows),
            'resolved': resolved, 'coverage': ratio(resolved, expected),
            'confusion_fail_positive': dict(tp=tp, fp=fp, fn=fn, tn=tn),
            'precision_fail': ratio(tp, tp + fp), 'recall_fail': ratio(tp, tp + fn),
            'f1_fail': ratio(2 * tp, 2 * tp + fp + fn), 'accuracy': ratio(tp + tn, resolved),
            **{k: counts[k] for k in ['error', 'na', 'indeterminate', 'unresolved_reference',
                                      'missed_critical', 'unresolved_critical']}}


def agreement(a: list[str], b: list[str]) -> dict:
    if len(a) != len(b):
        raise ValueError('Annotation sample sizes differ')
    n = len(a)
    observed = ratio(sum(x == y for x, y in zip(a, b, strict=True)), n)
    if not n:
        return {'n': 0, 'agreement': None, 'kappa': None}
    ca, cb = Counter(a), Counter(b)
    chance = sum(ca[k] * cb[k] for k in ca.keys() | cb.keys()) / (n * n)
    return {'n': n, 'agreement': observed, 'kappa': (observed - chance) / (1 - chance) if chance < 1 else None}


def stability(rows: list[dict], repeats: int, expected_units: set[tuple[str, str]] | None = None) -> dict:
    groups = defaultdict(list)
    for unit in expected_units or set():
        groups[unit] = []
    for row in rows:
        groups[row['unit_id'], row['orientation']].append(row)
    stable = complete = 0
    for group in groups.values():
        if len(group) != repeats or {r['repeat_id'] for r in group} != set(range(repeats)):
            continue
        labels = [r['prediction'].get('preference') or r['prediction']['verdict'] for r in group]
        if any(r['prediction']['status'] != 'OK' for r in group) or not set(labels) <= {'PASS', 'FAIL', 'A', 'B', 'TIE'}:
            continue
        complete += 1
        stable += len(set(labels)) == 1
    return {'groups': len(groups), 'complete_groups': complete, 'incomplete_groups': len(groups) - complete,
            'stable_groups': stable, 'stability': ratio(stable, complete)}


def pairwise_metrics(rows: list[dict], pairs: list[dict], repeats: int) -> dict:
    references = {p['pair_id']: p['reference'] for p in pairs}
    normalized, correct, errors = {}, 0, 0
    for row in rows:
        prediction = row['prediction']
        preference = prediction.get('preference')
        if prediction['status'] != 'OK' or preference not in {'A', 'B', 'TIE'}:
            errors += 1
            continue
        if row['orientation'] == 'BA':
            preference = {'A': 'B', 'B': 'A', 'TIE': 'TIE'}[preference]
        normalized[row['unit_id'], row['repeat_id'], row['orientation']] = preference
        correct += preference == references[row['unit_id']]
    flips = swaps = 0
    for pair_id in references:
        for repeat in range(repeats):
            ab, ba = normalized.get((pair_id, repeat, 'AB')), normalized.get((pair_id, repeat, 'BA'))
            if ab is not None and ba is not None:
                swaps += 1
                flips += ab != ba
    expected = len(pairs) * repeats * 2
    return {'expected': expected, 'recorded': len(rows), 'missing': expected - len(rows),
            'resolved': len(normalized), 'errors': errors, 'agreement': ratio(correct, len(normalized)),
            'coverage': ratio(len(normalized), expected), 'complete_swaps': swaps,
            'position_flips': flips, 'position_flip_rate': ratio(flips, swaps)}


def _validated_rows(directory: Path, results: Path) -> tuple:
    d = load_dataset(directory)
    rows = read_jsonl(results)
    if rows:
        metadata = rows[0]['metadata']
    else:
        journal = read_jsonl(attempts_path(results))
        if not journal:
            raise ValueError('No saved results or API attempts to analyze')
        verify_record(journal[0])
        metadata = journal[0]['metadata']
    config = JudgeConfig.model_validate(metadata['configuration'])
    if metadata['dataset_id'] != d.manifest.dataset_id:
        raise ValueError('Results belong to a different dataset')
    if metadata['split'] not in {'pilot', 'test'}:
        raise ValueError('Unknown result split')
    selected = {e.trace_id for e in d.manifest.entries if e.split == metadata['split']}
    seen = set()
    for row in rows:
        verify_record(row)
        key = (row['unit_id'], row['orientation'], row['repeat_id'])
        if (row['metadata'] != metadata or row['run_hash'] != digest(metadata) or key in seen or
                row['trace_id'] not in selected or type(row['repeat_id']) is not int or not 0 <= row['repeat_id'] < config.repeats):
            raise ValueError('Inconsistent or duplicated result ledger')
        if config.method != 'pairwise' and (row['orientation'] != 'single' or row['unit_id'] != row['trace_id']):
            raise ValueError('Invalid classification unit')
        seen.add(key)
    return d, rows, metadata, config


def calibrate_threshold(directory: Path, references_file: Path, results: Path, registry: SplitRegistry) -> dict:
    d, rows, metadata, config = _validated_rows(directory, results)
    if metadata['split'] != 'pilot' or config.method != 'score' or config.threshold is not None:
        raise ValueError('Calibration requires unthresholded pilot score predictions')
    if metadata['code_hash'] != code_hash() or metadata['prompt_hash'] != digest(system_prompt(config, d.rubric)):
        raise ValueError('Pilot results were produced by a different code or prompt version')
    registry.assert_pilot_allowed([e.template_group for e in d.manifest.entries if e.split == 'pilot'])
    snapshot = load_references(references_file, d.manifest.dataset_id)
    references = {r['trace_id']: r for r in snapshot['references']}
    selected = [r for r in rows if r['prediction']['status'] == 'OK' and r['prediction']['score'] is not None]
    expected = d.profile.pilot_size * config.repeats
    if len(rows) != expected or len(selected) != expected:
        raise ValueError('Resolve all pilot scores before selecting a threshold')
    if not {'PASS', 'FAIL'} <= {references[r['trace_id']]['verdict'] for r in selected}:
        raise ValueError('Calibration requires both reference classes')
    candidates = sorted({float(i) for i in range(config.score_min, config.score_max + 1)} |
                        {r['prediction']['score'] for r in selected})
    measurements = []
    for threshold in candidates:
        predictions = [{**r, 'prediction': {**r['prediction'],
                        'verdict': 'PASS' if r['prediction']['score'] >= threshold else 'FAIL'}} for r in selected]
        measurements.append((classification_metrics(predictions, references, expected)['f1_fail'], threshold))
    best_f1, threshold = max(measurements, key=lambda x: (x[0], -x[1]))
    return {'dataset_id': d.manifest.dataset_id, 'reference_hash': snapshot['reference_hash'],
            'source_run_hash': rows[0]['run_hash'], 'source_results_hash': digest(rows),
            'configuration': config.model_copy(update={'threshold': threshold}).model_dump(),
            'pilot_f1_fail': best_f1, 'rule': 'max F1(FAIL), lowest threshold on ties',
            'code_hash': metadata['code_hash'], 'prompt_hash': metadata['prompt_hash']}


def report(directory: Path, references_file: Path, results: Path, frozen_file: Path | None = None) -> dict:
    d, rows, metadata, config = _validated_rows(directory, results)
    snapshot = load_references(references_file, d.manifest.dataset_id)
    references = {r['trace_id']: r for r in snapshot['references']}
    split_size = d.profile.pilot_size if metadata['split'] == 'pilot' else d.profile.test_size
    if metadata['split'] == 'test':
        if frozen_file is None:
            raise ValueError('Test report requires its frozen reference identity')
        frozen = read_json(frozen_file)
        if frozen['reference_hash'] != snapshot['reference_hash'] or metadata['freeze_hash'] != frozen['freeze_hash']:
            raise ValueError('Report reference differs from the frozen experiment')
    if config.method == 'pairwise':
        metrics = pairwise_metrics(rows, metadata['pairs'], config.repeats)
    else:
        metrics = classification_metrics(rows, references, split_size * config.repeats)
    attempts_by_id = {attempt['request_id']: attempt for row in rows for attempt in row['attempts']}
    completed_ids = set(attempts_by_id)
    journal = attempts_path(results)
    if not journal.exists():
        raise ValueError('Missing API attempt journal; costs cannot be reproduced completely')
    for record in read_jsonl(journal):
        verify_record(record)
        if record['run_hash'] != digest(metadata) or record['metadata'] != metadata:
            raise ValueError('Attempt journal belongs to another run')
        attempt = record['attempt']
        request_id = attempt['request_id']
        if attempts_by_id.get(request_id, {}).get('phase') != 'completed' or attempt['phase'] == 'completed':
            attempts_by_id[request_id] = attempt
    attempts = list(attempts_by_id.values())
    costs = {'api_calls': len(attempts), 'elapsed_ms': sum(a['elapsed_ms'] for a in attempts),
             'time_scope': 'API attempt durations only; excludes backoff, downtime and unknown interrupted durations',
             'orphan_attempts': len(set(attempts_by_id) - completed_ids),
             'interrupted_attempts': sum(a['phase'] == 'started' for a in attempts),
             'format_errors': sum(a['error_kind'] == 'FORMAT' for a in attempts), 'monetary_cost': None}
    for kind in ['input_tokens', 'output_tokens']:
        costs[kind + '_known'] = sum(a[kind] for a in attempts if a[kind] is not None)
        costs[kind + '_unknown_attempts'] = sum(a[kind] is None for a in attempts)
    annotators = None
    if snapshot['secondary']:
        author = {a['trace_id']: a for a in snapshot['author']}
        annotators = agreement([aggregate([v['verdict'] for v in author[a['trace_id']]['criteria'].values()])
                                for a in snapshot['secondary']],
                               [aggregate([v['verdict'] for v in a['criteria'].values()]) for a in snapshot['secondary']])
    criteria = {}
    if config.method == 'criteria':
        for criterion in d.rubric['criteria']:
            key = criterion['criterion_id']
            criterion_refs = {tid: {'verdict': r['criteria'][key]['verdict']} for tid, r in references.items()}
            criterion_rows = [{**r, 'prediction': {'status': r['prediction']['status'],
                              'verdict': r['prediction']['criteria'].get(key, {}).get('verdict', 'INDETERMINATE')}} for r in rows]
            criteria[key] = classification_metrics(criterion_rows, criterion_refs, split_size * config.repeats)
    expected_units = ({(pair['pair_id'], orientation) for pair in metadata['pairs'] for orientation in ['AB', 'BA']}
                      if config.method == 'pairwise' else
                      {(e.trace_id, 'single') for e in d.manifest.entries if e.split == metadata['split']})
    return {'dataset_id': d.manifest.dataset_id, 'metadata': metadata, 'metrics': metrics, 'criteria': criteria,
            'stability': stability(rows, config.repeats, expected_units), 'cost': costs, 'annotator_agreement': annotators,
            'limitations': ['Synthetic controlled incidents; descriptive results on a small grouped sample.',
                            'Monetary cost is unknown without provider billing rates.',
                            'No inter-annotator agreement is claimed when secondary annotations are absent.']}
