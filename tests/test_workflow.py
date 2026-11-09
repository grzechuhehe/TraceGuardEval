import json
import subprocess
import sys

import httpx
import pytest

from traceguard_core.analysis import calibrate_threshold, report
from traceguard_core.annotations import freeze_references
from traceguard_core.dataset import build_dataset, load_dataset, read_jsonl, write_jsonl
from traceguard_core.evaluation import HTTPJudge, JudgeConfig
from traceguard_core.experiment import SplitRegistry, freeze_experiment, make_pairs, run_batch
from test_annotations import completed_forms


@pytest.fixture
def workspace(tmp_path):
    ds = tmp_path / 'ds'
    build_dataset(ds)
    write_jsonl(tmp_path / 'human.jsonl', completed_forms(ds))
    refs = tmp_path / 'refs.json'
    freeze_references(ds, tmp_path / 'human.jsonl', refs)
    return tmp_path, ds, refs, SplitRegistry(tmp_path / 'registry.json')


def test_score_calibration_freeze_test_and_offline_report(workspace):
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test', method='score')
    def response(request):
        return httpx.Response(200, json={'choices': [{'message': {'content':
            '{"score":7,"reason":"fixture","evidence":["e1"]}'}}]})
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        judge = HTTPJudge(client)
        run_batch(ds, root / 'pilot.jsonl', c, judge, registry)
        calibration = calibrate_threshold(ds, refs, root / 'pilot.jsonl', registry)
        frozen_config = JudgeConfig.model_validate(calibration['configuration'])
        assert frozen_config.threshold == 8.0
        freeze_experiment(ds, refs, frozen_config, root / 'frozen.json', registry, calibration)
        run_batch(ds, root / 'test.jsonl', frozen_config, judge, registry, 'test', root / 'frozen.json')
    summary = report(ds, refs, root / 'test.jsonl', root / 'frozen.json')
    assert summary['metrics']['expected'] == summary['metrics']['recorded'] == 150
    assert summary['cost']['api_calls'] == summary['cost']['input_tokens_unknown_attempts'] == 150
    assert summary['annotator_agreement'] is None
    with pytest.raises(ValueError, match='pilot'):
        calibrate_threshold(ds, refs, root / 'test.jsonl', registry)


def test_twenty_pairs_include_ties_and_both_orders_in_three_repeats(workspace):
    root, ds, refs, registry = workspace
    pairs = make_pairs(ds, refs)
    assert len(pairs) == 20 and {p['reference'] for p in pairs} == {'A', 'TIE'}
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test', method='pairwise')
    freeze_experiment(ds, refs, c, root / 'pair-freeze.json', registry)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        'choices': [{'message': {'content': '{"preference":"TIE","reason":"fixture","evidence":["A:e1","B:answer"]}'}}]}))) as client:
        stats = run_batch(ds, root / 'pairs.jsonl', c, HTTPJudge(client), registry, 'test', root / 'pair-freeze.json')
    assert stats['executed'] == 120
    summary = report(ds, refs, root / 'pairs.jsonl', root / 'pair-freeze.json')
    assert summary['metrics']['agreement'] == 0.5
    assert summary['metrics']['complete_swaps'] == 60


def test_cli_build_validate_and_export_blind_annotations(tmp_path):
    def cli(*args):
        return subprocess.run([sys.executable, '-m', 'traceguard_core', *map(str, args)], capture_output=True, text=True)
    ds = tmp_path / 'cli-dataset'
    result = cli('build', '--output', ds)
    assert result.returncode == 0, result.stderr
    result = cli('validate', '--dataset', ds)
    assert result.returncode == 0 and json.loads(result.stdout)['trajectories'] == 150
    out = tmp_path / 'annotations.jsonl'
    result = cli('annotations', '--dataset', ds, '--annotator', 'reviewer', '--split', 'test', '--output', out)
    assert result.returncode == 0, result.stderr
    assert len(read_jsonl(out)) == 50
    assert cli('build', '--output', ds).returncode != 0
    legacy = tmp_path / 'legacy-dataset'
    result = cli('build', '--output', legacy, '--configs', 'configs')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['trajectories'] == 60
    assert load_dataset(legacy).profile.profile_id == 'gsn-v1'
