"""Independent human review, disputes and immutable reference snapshots."""

from pathlib import Path

from traceguard_core.dataset import load_dataset, read_jsonl, validate_dataset
from traceguard_core.models import CRITERIA, CriterionResult, aggregate, canonical, digest
from traceguard_core.rules import reference_rules


def export_forms(directory: Path, annotator: str, split: str | None = None) -> list[dict]:
    validate_dataset(directory)
    if not annotator.strip():
        raise ValueError('Annotator identity is required')
    d = load_dataset(directory)
    entries = {e.trace_id: e for e in d.manifest.entries}
    return [{'trace_id': t.trace_id, 'split': entries[t.trace_id].split, 'annotator_id': annotator,
             'origin': 'human', 'reviewed': False, 'observation': t.judge_payload(),
             'criteria': {k: {'verdict': 'INDETERMINATE', 'evidence': [], 'reason': ''} for k in CRITERIA}}
            for t in d.traces if split is None or entries[t.trace_id].split == split]


def _checked(rows: list[dict], traces: dict, expected: set[str] | None = None) -> dict:
    result = {}
    for row in rows:
        trace_id = row['trace_id']
        if trace_id not in traces or trace_id in result:
            raise ValueError('Unknown or duplicate annotation')
        trace = traces[trace_id]
        if row.get('origin') != 'human' or row.get('reviewed') is not True or not row.get('annotator_id', '').strip():
            raise ValueError('Independent human review is required')
        if row.get('observation') != trace.judge_payload():
            raise ValueError('Annotation observation differs from original trace')
        if not isinstance(row['criteria'], dict) or set(row['criteria']) != set(CRITERIA):
            raise ValueError('All rubric criteria are required')
        evidence_ids = {e.event_id for e in trace.events} | {'answer'}
        for data in row['criteria'].values():
            criterion = CriterionResult.model_validate(data)
            if criterion.verdict not in {'PASS', 'FAIL'}:
                raise ValueError('Main dataset requires resolved applicable criteria')
            if not criterion.reason.strip() or not criterion.evidence or not set(criterion.evidence) <= evidence_ids:
                raise ValueError('Each annotation needs valid evidence and a reason')
        result[trace_id] = row
    if expected is not None and set(result) != expected:
        raise ValueError('Missing annotations')
    if len({r['annotator_id'] for r in rows}) != 1:
        raise ValueError('Each annotation file must belong to one annotator')
    return result


def freeze_references(directory: Path, author_file: Path, output: Path,
                      secondary_file: Path | None = None, adjudications_file: Path | None = None) -> dict:
    if output.exists():
        raise FileExistsError(output)
    validate_dataset(directory)
    d = load_dataset(directory)
    traces = {t.trace_id: t for t in d.traces}
    author = _checked(read_jsonl(author_file), traces, set(traces))
    author_id = next(iter(author.values()))['annotator_id']
    secondary, adjudications, disputes = {}, {}, []
    if secondary_file is not None:
        secondary = _checked(read_jsonl(secondary_file), traces)
        test_ids = {e.trace_id for e in d.manifest.entries if e.split == 'test'}
        if len(secondary) != 20 or not set(secondary) <= test_ids:
            raise ValueError('Secondary sample must contain 20 test trajectories')
        if any(r['annotator_id'] == author_id for r in secondary.values()):
            raise ValueError('Second annotator must be independent')
        disputes = [tid for tid, row in secondary.items() if any(
            row['criteria'][k]['verdict'] != author[tid]['criteria'][k]['verdict'] for k in CRITERIA)]
        if adjudications_file is not None:
            adjudications = _checked(read_jsonl(adjudications_file), traces, set(disputes))
        elif disputes:
            raise ValueError(f'Unresolved annotation disputes: {len(disputes)}')
    references = []
    for tid, trace in traces.items():
        row = adjudications.get(tid, author[tid])
        rules = reference_rules(trace, d.scenarios[trace.scenario_id])
        if any(row['criteria'][k]['verdict'] != rules.criteria[k].verdict for k in CRITERIA[:-1]):
            raise ValueError('Human/rule disagreement requires correcting the scenario or documented rules before freezing')
        references.append({'trace_id': tid, 'criteria': row['criteria'],
                           'verdict': aggregate([v['verdict'] for v in row['criteria'].values()]),
                           'critical_fail': row['criteria']['constraints']['verdict'] == 'FAIL'})
    snapshot = {'schema_version': '1.0', 'dataset_id': d.manifest.dataset_id,
                'rubric_hash': d.manifest.rubric_hash, 'references': references,
                'author': list(author.values()), 'secondary': list(secondary.values()),
                'adjudications': list(adjudications.values()), 'disputes': disputes,
                'secondary_annotation': 'AVAILABLE' if secondary else 'NOT_AVAILABLE'}
    snapshot['reference_hash'] = digest(snapshot)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as file:
        file.write(canonical(snapshot) + '\n')
    return snapshot
