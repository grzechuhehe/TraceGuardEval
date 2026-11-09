import json
from collections import Counter

import pytest

from traceguard_core.dataset import build_dataset, load_dataset, validate_dataset
from traceguard_core.models import digest
from traceguard_sim.engine import replay


def test_sixty_replayable_balanced_traces_and_grouped_split(tmp_path):
    build_dataset(tmp_path)
    dataset = load_dataset(tmp_path)
    assert len(dataset.traces) == 60
    assert Counter(e.split for e in dataset.manifest.entries) == {'pilot': 20, 'test': 40}
    assert len({e.scenario_id for e in dataset.manifest.entries}) == 15
    for scenario in {e.scenario_id for e in dataset.manifest.entries}:
        entries = [e for e in dataset.manifest.entries if e.scenario_id == scenario]
        assert len(entries) == 4
        assert len({e.split for e in entries}) == 1
    assert Counter(r['planned_class'] for r in dataset.drafts) == {'PASS': 30, 'FAIL': 30}
    assert all(replay(t, dataset.scenarios[t.scenario_id]) == t for t in dataset.traces)
    assert validate_dataset(tmp_path)['trajectories'] == 60


def test_generation_is_deterministic_and_does_not_overwrite(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    build_dataset(a)
    build_dataset(b)
    for name in ('traces.jsonl', 'manifest.json', 'reference_drafts.jsonl'):
        assert (a / name).read_bytes() == (b / name).read_bytes()
    with pytest.raises(FileExistsError):
        build_dataset(a)


def test_critical_violation_cannot_be_compensated_by_restored_service(tmp_path):
    build_dataset(tmp_path)
    data = load_dataset(tmp_path)
    examples = [d for d in data.drafts if d['mutation'] == 'delete_logs']
    assert examples
    for example in examples:
        criteria = example['criteria']
        assert criteria['task_success']['verdict'] == 'PASS'
        assert criteria['constraints']['verdict'] == 'FAIL'


def test_blinded_payload_excludes_private_state_and_variant_metadata(tmp_path):
    build_dataset(tmp_path)
    for trace in load_dataset(tmp_path).traces:
        payload = trace.judge_payload()
        assert set(payload) == {'task', 'events', 'final_answer'}
        assert all(key not in json.dumps(payload) for key in ('planned_class', 'mutation', 'initial_state', 'final_state'))
        assert trace.trace_id == trace.content_hash()
        assert len(trace.trace_id) == 64 and all(c in '0123456789abcdef' for c in trace.trace_id)


def test_tampering_detected_even_if_manifest_hashes_are_updated(tmp_path):
    build_dataset(tmp_path)
    traces = [json.loads(x) for x in (tmp_path / 'traces.jsonl').read_text().splitlines()]
    traces[0]['events'][0]['response'] = {'forged': True}
    original_id = traces[0]['trace_id']
    traces[0]['trace_id'] = digest({k: v for k, v in traces[0].items() if k != 'trace_id'})
    (tmp_path / 'traces.jsonl').write_text('\n'.join(json.dumps(t) for t in traces) + '\n')
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    for entry in manifest['entries']:
        if entry['trace_id'] == original_id:
            entry['trace_id'] = traces[0]['trace_id']
    manifest['dataset_id'] = digest({'entries': manifest['entries'],
        'profile': json.loads((tmp_path / 'profile.json').read_text()),
        'rubric': json.loads((tmp_path / 'rubric.json').read_text()),
        'scenarios': json.loads((tmp_path / 'scenarios.json').read_text())})
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        validate_dataset(tmp_path)
