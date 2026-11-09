import json

import httpx
import pytest

from traceguard_core.dataset import build_dataset, load_dataset
from traceguard_core.evaluation import JudgeConfig, HTTPJudge, build_messages, parse_result


@pytest.fixture
def trace(tmp_path):
    build_dataset(tmp_path)
    return load_dataset(tmp_path).traces[0]


def config(**kwargs):
    return JudgeConfig(model='test-model', endpoint='https://judge.test/chat', provider_id='test', **kwargs)


def test_prompt_contains_only_public_evidence(trace):
    messages = build_messages(trace, config(), {'criteria': ['task_success']})
    assert json.loads(messages[1]['content']) == trace.judge_payload()
    assert trace.trace_id not in json.dumps(messages)
    assert 'final_state' not in json.dumps(messages)
    final = build_messages(trace, config(evidence_mode='final_only'), {})
    assert 'events' not in json.loads(final[1]['content'])


@pytest.mark.parametrize('raw', [
    '{"verdict":"PASS"}',
    '{"verdict":"PASS","reason":"yes","evidence":["e999"]}',
    '{"verdict":"PASS","reason":"yes","evidence":["e1"],"extra":true}',
    '{"verdict":"ERROR","reason":"yes","evidence":[]}',
    '```json\n{"verdict":"PASS"}\n```',
])
def test_parser_rejects_missing_evidence_unknown_ids_and_extra_fields(trace, raw):
    with pytest.raises(ValueError):
        parse_result(raw, config(), trace)


def test_score_range_and_frozen_threshold(trace):
    c = config(method='score', score_min=1, score_max=10, threshold=7.0)
    assert parse_result('{"score":6,"reason":"proof","evidence":["e1"]}', c, trace).verdict == 'FAIL'
    assert parse_result('{"score":7,"reason":"proof","evidence":["e1"]}', c, trace).verdict == 'PASS'
    for score in (0, 11, '7', True):
        with pytest.raises(ValueError):
            parse_result(json.dumps({'score': score, 'reason': 'x', 'evidence': ['e1']}), c, trace)


def test_retry_records_every_attempt_and_never_retries_bad_model_json(trace):
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={'choices': [{'message': {'content': 'not json'}}],
                                       'usage': {'prompt_tokens': 12, 'completion_tokens': 3}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result, attempts = HTTPJudge(client, sleep=lambda _: None).evaluate(trace, config(max_retries=2), {})
    assert result.status == 'ERROR'
    assert len(attempts) == len(calls) == 2
    assert attempts[0]['http_status'] == 429
    assert attempts[0]['input_tokens'] is None
    assert attempts[1]['input_tokens'] == 12
    assert attempts[1]['error_kind'] == 'FORMAT'


def test_auth_failure_is_not_retried_or_logged(trace):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text='sensitive response'))) as client:
        result, attempts = HTTPJudge(client, sleep=lambda _: None).evaluate(trace, config(), {})
    assert result.status == 'ERROR' and len(attempts) == 1
    assert 'sensitive response' not in json.dumps(attempts)
