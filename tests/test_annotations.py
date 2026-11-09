import json
from collections import Counter
from pathlib import Path

import pytest

from traceguard_core.annotations import export_forms, freeze_references
from traceguard_core.dataset import build_dataset, load_dataset, read_json, read_jsonl, write_jsonl


def completed_forms(dataset, annotator='author'):
    rows = export_forms(dataset, annotator)
    data = load_dataset(dataset)
    drafts = {d['trace_id']: d for d in data.drafts}
    for row in rows:
        draft = drafts[row['trace_id']]
        row['reviewed'] = True
        row['criteria'] = draft['criteria']
        row['criteria']['answer_faithfulness'] = {
            'verdict': 'FAIL' if draft['mutation'] in {'false_claim', 'no_verify', 'no_diagnosis', 'wrong_resource', 'wrong_value', 'bad_type'} else 'PASS',
            'evidence': ['answer', 'e1'], 'reason': 'Test fixture: independent human decision.'}
    return rows


def test_committed_v2_forms_and_secondary_sample_are_blind_and_reproducible():
    directory = Path('data/gsn-v2')
    tasks = Path('data/annotation_tasks/gsn-v2')
    dataset = load_dataset(directory)
    author = read_jsonl(tasks / 'author.jsonl')
    secondary = read_jsonl(tasks / 'secondary.jsonl')
    sample = read_json(tasks / 'secondary_sample.json')
    assert author == export_forms(directory, 'author')
    assert len(author) == 150
    expected_ids = [tid for sid in sorted(dataset.scenarios) for tid in sorted(
        e.trace_id for e in dataset.manifest.entries if e.scenario_id == sid and e.split == 'test')[:2]]
    assert sample['dataset_id'] == dataset.manifest.dataset_id
    assert sample['trace_ids'] == expected_ids
    assert sample['selection_rule'] == 'two lexicographically smallest trace IDs per test scenario, before annotation and model calls'
    forms = {r['trace_id']: r for r in export_forms(directory, 'secondary', 'test')}
    assert secondary == [forms[tid] for tid in expected_ids]
    by_id = {t.trace_id: t for t in dataset.traces}
    assert len(secondary) == 20
    assert Counter(by_id[r['trace_id']].scenario_id for r in secondary) == {
        s.scenario_id: 2 for s in dataset.scenarios.values() if s.split == 'test'}
    assert not any(r['reviewed'] for r in author + secondary)
    assert all(v['verdict'] == 'INDETERMINATE' and not v['evidence'] and not v['reason']
               for row in author + secondary for v in row['criteria'].values())
    assert all(key not in json.dumps(author + secondary) for key in (
        'mutation', 'planned_class', 'initial_state', 'final_state'))


def test_forms_are_blind_and_unreviewed_forms_cannot_freeze(tmp_path):
    ds = tmp_path / 'ds'
    build_dataset(ds)
    rows = export_forms(ds, 'author')
    assert len(rows) == 150 and not any(r['reviewed'] for r in rows)
    assert 'mutation' not in json.dumps(rows) and 'planned_class' not in json.dumps(rows)
    path = tmp_path / 'forms.jsonl'
    write_jsonl(path, rows)
    with pytest.raises(ValueError, match='review'):
        freeze_references(ds, path, tmp_path / 'gold.json')


def test_frozen_references_require_all_traces_and_evidence(tmp_path):
    ds = tmp_path / 'ds'
    build_dataset(ds)
    rows = completed_forms(ds)
    forms = tmp_path / 'forms.jsonl'
    out = tmp_path / 'gold.json'
    write_jsonl(forms, rows)
    frozen = freeze_references(ds, forms, out)
    assert len(frozen['references']) == 150
    assert frozen['secondary_annotation'] == 'NOT_AVAILABLE'
    assert sum(r['verdict'] == 'PASS' for r in frozen['references']) == 60
    with pytest.raises(FileExistsError):
        freeze_references(ds, forms, out)
    rows[0]['criteria']['answer_faithfulness']['evidence'] = ['e999']
    write_jsonl(forms, rows)
    with pytest.raises(ValueError, match='evidence'):
        freeze_references(ds, forms, tmp_path / 'invalid.json')


def test_second_annotator_cannot_be_same_person_or_see_pilot(tmp_path):
    ds = tmp_path / 'ds'
    build_dataset(ds)
    author = completed_forms(ds)
    other = [r for r in completed_forms(ds, 'author') if r['split'] == 'test'][:20]
    write_jsonl(tmp_path / 'author.jsonl', author)
    write_jsonl(tmp_path / 'other.jsonl', other)
    with pytest.raises(ValueError, match='independent'):
        freeze_references(ds, tmp_path / 'author.jsonl', tmp_path / 'gold.json', tmp_path / 'other.jsonl')
