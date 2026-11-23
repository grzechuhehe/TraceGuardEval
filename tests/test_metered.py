import json

import httpx
import pytest

from traceguard_core.budget import Account, BudgetExceeded, Ledger, Price
from traceguard_core.metered import Limits, MeteredChat

PRICE = Price(input_micro_usd_per_million=1000000, output_micro_usd_per_million=1000000,
              source='mock', checked_on='2026-11-23')


def client(tmp_path, handler, **limits):
    return MeteredChat(Ledger(tmp_path / 'ledger.sqlite'), Account(provider='mock', model='test'), PRICE,
                       Limits(input_cap=200, output_cap=100, **limits), httpx.MockTransport(handler))


def ok(_):
    return httpx.Response(200, json={'choices': [{'message': {'content': '{"tool":"inspect"}'}}],
                                    'usage': {'prompt_tokens': 10, 'completion_tokens': 10}})


def test_resume_uses_durable_result_without_new_request(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return ok(request)
    chat = client(tmp_path, handler)
    first = chat.call('run/agent/0', [], 'agent')
    chat.close()
    chat = client(tmp_path, handler)
    assert chat.call('run/agent/0', [], 'agent') == first
    assert len(calls) == 1
    assert chat.ledger.summary()['charged_micro_usd'] == 20
    chat.close()


def test_retry_is_reserved_and_call_limit_checked_before_request(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429)
    chat = client(tmp_path, handler, max_calls=1)
    with pytest.raises(BudgetExceeded):
        chat.call('run/agent/0', [], 'agent')
    assert len(calls) == 1
    assert chat.ledger.summary()['charged_micro_usd'] == 300
    chat.close()


def test_interrupt_retains_reservation_and_resume_uses_a_new_attempt(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise KeyboardInterrupt
        return ok(request)
    chat = client(tmp_path, handler)
    with pytest.raises(KeyboardInterrupt):
        chat.call('run/agent/0', [], 'agent')
    assert chat.call('run/agent/0', [], 'agent')['error'] is None
    assert len(calls) == 2
    assert chat.ledger.summary()['charged_micro_usd'] == 320
    chat.close()


def test_session_time_limit_survives_new_transport_instance(tmp_path):
    now = [100.0]
    ledger = Ledger(tmp_path / 'ledger.sqlite')
    chat = MeteredChat(ledger, Account(provider='mock', model='test'), PRICE, Limits(),
                       httpx.MockTransport(ok), clock=lambda: now[0])
    chat.call('timed/agent/0', [], 'agent')
    chat.close()
    now[0] = 200.0
    resumed = MeteredChat(ledger, Account(provider='mock', model='test'), PRICE, Limits(),
                          httpx.MockTransport(lambda _: pytest.fail('Expired session must not call')),
                          clock=lambda: now[0])
    with pytest.raises(BudgetExceeded, match='time'):
        resumed.call('timed/agent/1', [], 'agent')
    resumed.close()


def test_unknown_price_and_unconfirmed_live_access_block(tmp_path):
    with pytest.raises(ValueError, match='confirmed'):
        MeteredChat(Ledger(tmp_path / 'ledger.sqlite'), Account(provider='mock', model='test'), PRICE, Limits())
    chat = client(tmp_path, ok)
    chat.price = None
    with pytest.raises(ValueError, match='Unknown'):
        chat.call('run/agent/0', [], 'agent')
    chat.close()


def test_prompt_token_and_time_limits_stop_before_call(tmp_path):
    chat = client(tmp_path, lambda _: pytest.fail('Must stop before network'), max_tokens=299)
    with pytest.raises(BudgetExceeded):
        chat.call('run/agent/0', [], 'agent')
    with pytest.raises(BudgetExceeded, match='Input'):
        chat.call('run/agent/0', [{'role': 'user', 'content': 'x' * 300}], 'agent')
    chat.clock = lambda: chat.started + 100
    with pytest.raises(BudgetExceeded):
        chat.call('run/agent/0', [], 'agent')
    chat.close()
