import json

import httpx
import pytest

from traceguard_core.analysis import calibrate_threshold, report
from traceguard_core.annotations import freeze_references
from traceguard_core.dataset import build_dataset, read_jsonl, write_jsonl
from traceguard_core.evaluation import HTTPJudge, JudgeConfig
from traceguard_core.experiment import SplitRegistry, freeze_experiment, run_batch
from traceguard_core.models import CriterionResult, EvaluationResult
from traceguard_core.rules import quality_decision
from test_annotations import completed_forms


@pytest.fixture
def workspace(tmp_path):
    ds = tmp_path / 'ds'
    build_dataset(ds)
    refs = tmp_path / 'refs.json'
    write_jsonl(tmp_path / 'human.jsonl', completed_forms(ds))
    freeze_references(ds, tmp_path / 'human.jsonl', refs)
    return tmp_path, ds, refs, SplitRegistry(tmp_path / 'registry.json')


def test_partial_criteria_cannot_accept():
    result = EvaluationResult(criteria={'task_success': CriterionResult(verdict='PASS', evidence=['e1'], reason='proof')})
    assert quality_decision(result, critical={'constraints'}) == 'REVIEW'


def test_malformed_usage_becomes_format_error(workspace):
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
            'choices': [{'message': {'content': '{"verdict":"PASS","reason":"ok","evidence":["e1"]}'}}],
            'usage': 'invalid'}))) as client:
        run_batch(ds, root / 'bad-usage.jsonl', c, HTTPJudge(client), registry)
    rows = read_jsonl(root / 'bad-usage.jsonl')
    assert len(rows) == 300 and all(r['prediction']['status'] == 'ERROR' for r in rows)
    assert all(r['attempts'][0]['error_kind'] == 'FORMAT' for r in rows)


def test_report_counts_entirely_absent_repeat_groups(workspace):
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test')
    count = 0
    def respond(request):
        nonlocal count
        count += 1
        if count > 3:
            raise KeyboardInterrupt
        return httpx.Response(200, json={'choices': [{'message': {'content':
            '{"verdict":"PASS","reason":"ok","evidence":["e1"]}'}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(KeyboardInterrupt):
            run_batch(ds, root / 'partial.jsonl', c, HTTPJudge(client), registry)
    summary = report(ds, refs, root / 'partial.jsonl')
    assert summary['stability']['complete_groups'] == 1
    assert summary['stability']['incomplete_groups'] == 99
    assert summary['stability']['groups'] == 100


def test_interruption_during_backoff_preserves_orphan_api_attempt(workspace):
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test')
    calls = 0
    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={'choices': [{'message': {'content':
            '{"verdict":"PASS","reason":"ok","evidence":["e1"]}'}}]})
    def interrupt(_):
        raise KeyboardInterrupt
    results = root / 'results.jsonl'
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(KeyboardInterrupt):
            run_batch(ds, results, c, HTTPJudge(client, sleep=interrupt), registry)
        run_batch(ds, results, c, HTTPJudge(client), registry)
    summary = report(ds, refs, results)
    assert summary['cost']['api_calls'] == calls == 301
    assert summary['cost']['orphan_attempts'] == 1


def test_freeze_rejects_calibration_from_different_code(workspace):
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test', method='score')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
            'choices': [{'message': {'content': '{"score":7,"reason":"ok","evidence":["e1"]}'}}]}))) as client:
        run_batch(ds, root / 'scores.jsonl', c, HTTPJudge(client), registry)
    calibration = calibrate_threshold(ds, refs, root / 'scores.jsonl', registry)
    assert calibration['configuration']['threshold'] == 8.0
    assert calibration['pilot_f1_fail'] == pytest.approx(0.75)
    calibration['code_hash'] = 'old-code'
    with pytest.raises(ValueError, match='code'):
        freeze_experiment(ds, refs, JudgeConfig.model_validate(calibration['configuration']),
                          root / 'freeze.json', registry, calibration)


def test_calibration_checks_source_prompt_and_code(workspace, monkeypatch):
    import traceguard_core.analysis as analysis
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test', method='score')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
            'choices': [{'message': {'content': '{"score":7,"reason":"ok","evidence":["e1"]}'}}]}))) as client:
        run_batch(ds, root / 'scores.jsonl', c, HTTPJudge(client), registry)
    monkeypatch.setattr(analysis, 'system_prompt', lambda *_: 'changed-prompt')
    with pytest.raises(ValueError, match='prompt'):
        calibrate_threshold(ds, refs, root / 'scores.jsonl', registry)


def test_saved_prediction_is_bound_to_content_hash(workspace):
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
            'choices': [{'message': {'content': '{"verdict":"PASS","reason":"ok","evidence":["e1"]}'}}]}))) as client:
        run_batch(ds, root / 'results.jsonl', c, HTTPJudge(client), registry)
    rows = read_jsonl(root / 'results.jsonl')
    rows[0]['prediction']['verdict'] = 'FAIL'
    write_jsonl(root / 'results.jsonl', rows)
    with pytest.raises(ValueError, match='hash'):
        report(ds, refs, root / 'results.jsonl')


def test_report_preserves_costs_when_interrupted_before_any_result(workspace):
    root, ds, refs, registry = workspace
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='test')
    def interrupt(request):
        raise KeyboardInterrupt
    with httpx.Client(transport=httpx.MockTransport(interrupt)) as client:
        with pytest.raises(KeyboardInterrupt):
            run_batch(ds, root / 'empty.jsonl', c, HTTPJudge(client), registry)
    summary = report(ds, refs, root / 'empty.jsonl')
    assert summary['metrics']['recorded'] == 0
    assert summary['metrics']['missing'] == 300
    assert summary['stability']['incomplete_groups'] == 100
    assert summary['cost']['api_calls'] == summary['cost']['interrupted_attempts'] == 1
