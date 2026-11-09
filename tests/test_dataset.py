import json
from collections import Counter
from pathlib import Path

import pytest

from traceguard_core.dataset import build_dataset, load_dataset, read_json, read_jsonl, validate_dataset, write_json, write_jsonl
from traceguard_core.models import Scenario, digest
from traceguard_sim.engine import replay, variants


@pytest.mark.parametrize(('configs', 'scenarios', 'pilot', 'test', 'per_scenario', 'classes'), [
    (Path('configs'), 15, 20, 40, 4, {'PASS': 30, 'FAIL': 30}),
    (Path('configs/gsn-v2'), 30, 100, 50, 5, {'PASS': 60, 'FAIL': 90}),
])
def test_replayable_balanced_traces_and_grouped_split(tmp_path, configs, scenarios, pilot, test, per_scenario, classes):
    build_dataset(tmp_path, configs)
    dataset = load_dataset(tmp_path)
    assert len(dataset.traces) == pilot + test
    assert Counter(e.split for e in dataset.manifest.entries) == {'pilot': pilot, 'test': test}
    assert len({e.scenario_id for e in dataset.manifest.entries}) == scenarios
    for scenario in {e.scenario_id for e in dataset.manifest.entries}:
        entries = [e for e in dataset.manifest.entries if e.scenario_id == scenario]
        assert len(entries) == per_scenario
        assert len({e.split for e in entries}) == 1
    assert Counter(r['planned_class'] for r in dataset.drafts) == classes
    assert all(replay(t, dataset.scenarios[t.scenario_id]) == t for t in dataset.traces)
    assert validate_dataset(tmp_path)['trajectories'] == pilot + test


def test_v2_has_two_correct_and_three_distinct_faults_per_scenario(tmp_path):
    build_dataset(tmp_path, Path('configs/gsn-v2'))
    dataset = load_dataset(tmp_path)
    assert validate_dataset(tmp_path)['trajectories'] == 150
    assert Counter(e.split for e in dataset.manifest.entries) == {'pilot': 100, 'test': 50}
    drafts = {d['trace_id']: d for d in dataset.drafts}
    for scenario in dataset.scenarios.values():
        traces = [t for t in dataset.traces if t.scenario_id == scenario.scenario_id]
        rows = [drafts[t.trace_id] for t in traces]
        assert len({t.trace_id for t in traces}) == 5
        assert Counter(r['planned_class'] for r in rows) == {'PASS': 2, 'FAIL': 3}
        assert len({r['mutation'] for r in rows if r['planned_class'] == 'FAIL'}) == 3
        for trace in traces:
            assert replay(trace, scenario) == trace
            row = drafts[trace.trace_id]
            verdicts = {v['verdict'] for v in row['criteria'].values()}
            if row['planned_class'] == 'PASS':
                assert verdicts == {'PASS', 'INDETERMINATE'}
            elif row['mutation'] == 'false_claim':
                assert 'Nie odczytano logów' in trace.final_answer
                assert any(e.tool == 'read_logs' for e in trace.events)
                assert any(e.tool == 'set_config' and e.error is None for e in trace.events)
            else:
                assert 'FAIL' in verdicts


def test_default_build_reproduces_committed_v2_dataset(tmp_path):
    build_dataset(tmp_path)
    assert load_dataset(tmp_path).profile.profile_id == 'gsn-v2'
    for expected in Path('data/gsn-v2').iterdir():
        assert (tmp_path / expected.name).read_bytes() == expected.read_bytes()


def test_legacy_dataset_is_byte_identical(tmp_path):
    build_dataset(tmp_path, Path('configs'))
    for expected in Path('data/gsn-v1').iterdir():
        assert (tmp_path / expected.name).read_bytes() == expected.read_bytes()


@pytest.mark.parametrize(('correct', 'incorrect'), [(0, 3), (3, 3), (2, 0), (2, 8)])
def test_generator_rejects_unsupported_variant_counts(correct, incorrect):
    scenario = Scenario.model_validate(read_json(Path('configs/scenarios.json'))[0])
    with pytest.raises(ValueError, match='variant counts'):
        variants(scenario, 0, correct_count=correct, incorrect_count=incorrect)


def test_build_rejects_unsupported_counts_without_writing_dataset(tmp_path):
    configs = tmp_path / 'configs'
    configs.mkdir()
    for name in ('gsn.json', 'scenarios.json', 'rubric.json'):
        write_json(configs / name, read_json(Path('configs') / name))
    profile = read_json(configs / 'gsn.json')
    profile.update(correct_per_scenario=3, incorrect_per_scenario=1)
    write_json(configs / 'gsn.json', profile)
    output = tmp_path / 'dataset'
    with pytest.raises(ValueError, match='variant counts'):
        build_dataset(output, configs)
    assert not output.exists()


def test_validator_rejects_tampered_class_counts(tmp_path):
    build_dataset(tmp_path)
    rows = read_jsonl(tmp_path / 'reference_drafts.jsonl')
    rows[0]['planned_class'] = 'FAIL'
    write_jsonl(tmp_path / 'reference_drafts.jsonl', rows)
    with pytest.raises(ValueError, match='class counts'):
        validate_dataset(tmp_path)


@pytest.mark.parametrize('case', ['duplicate_fault', 'mutated_correct'])
def test_validator_rejects_inconsistent_mutation_metadata(tmp_path, case):
    build_dataset(tmp_path)
    rows = read_jsonl(tmp_path / 'reference_drafts.jsonl')
    if case == 'duplicate_fault':
        rows[3]['mutation'] = rows[2]['mutation']
        message = 'duplicate fault'
    else:
        rows[0]['mutation'] = 'delete_logs'
        message = 'marked as mutated'
    write_jsonl(tmp_path / 'reference_drafts.jsonl', rows)
    with pytest.raises(ValueError, match=message):
        validate_dataset(tmp_path)


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
