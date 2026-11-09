import json

import httpx
import pytest

from traceguard_core.dataset import build_dataset, load_dataset, read_jsonl
from traceguard_core.evaluation import HTTPJudge, JudgeConfig
from traceguard_core.experiment import SplitRegistry, run_batch


def test_registry_blocks_equivalent_test_groups_across_profiles(tmp_path):
    registry = SplitRegistry(tmp_path / 'registry.json')
    registry.reserve_test_groups(['fault-dns'], 'gsn-v1')
    registry.assert_pilot_allowed(['fault-listen_port'])
    with pytest.raises(ValueError, match='frozen'):
        registry.assert_pilot_allowed(['fault-dns'])
    registry.reserve_test_groups(['fault-dns'], 'pp-v1')
    with pytest.raises(ValueError):
        registry.assert_pilot_allowed(['fault-dns'])


def test_repeats_bypass_cache_resume_deduplicates_and_partial_tail_recovers(tmp_path):
    ds = tmp_path / 'ds'
    build_dataset(ds)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content':
            '{"verdict":"PASS","reason":"fixture","evidence":["e1"]}'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})
    config = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='mock', repeats=3)
    results = tmp_path / 'results.jsonl'
    registry = SplitRegistry(tmp_path / 'registry.json')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        judge = HTTPJudge(client)
        run_batch(ds, results, config, judge, registry, split='pilot')
        assert len(calls) == 300
        assert len(read_jsonl(results)) == 300
        run_batch(ds, results, config, judge, registry, split='pilot')
        assert len(calls) == 300
        with results.open('ab') as f:
            f.write(b'{"partial":')
        run_batch(ds, results, config, judge, registry, split='pilot')
        assert len(read_jsonl(results)) == 300 and len(calls) == 300
        with pytest.raises(ValueError, match='frozen'):
            run_batch(ds, results, config, judge, registry, split='test')


def test_resume_rejects_changed_config(tmp_path):
    ds = tmp_path / 'ds'
    build_dataset(ds)
    c = JudgeConfig(model='mock', endpoint='https://judge.test/chat', provider_id='mock')
    results = tmp_path / 'results.jsonl'
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        judge = HTTPJudge(client, sleep=lambda _: None)
        run_batch(ds, results, c, judge, SplitRegistry(tmp_path / 'registry.json'))
        with pytest.raises(ValueError, match='configuration'):
            run_batch(ds, results, c.model_copy(update={'model': 'other'}), judge, SplitRegistry(tmp_path / 'registry.json'))
