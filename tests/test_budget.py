import pytest

from traceguard_core.budget import Account, BudgetExceeded, Ledger, Price

PRICE = Price(input_micro_usd_per_million=1000000, output_micro_usd_per_million=2000000,
              source='mock-only', checked_on='2026-11-23')


def reserve(ledger, identity='a', account=None, role='agent', price=PRICE):
    return ledger.reserve(identity, account or Account(provider='mock', model='test', monthly_model_micro_usd=500),
                          role, {'messages': ['test']}, 100, 100, price)


def test_reservation_stops_before_shared_generation_and_judging_budget(tmp_path):
    ledger = Ledger(tmp_path / 'budget.sqlite')
    assert reserve(ledger)['charged'] == 300
    with pytest.raises(BudgetExceeded):
        reserve(ledger, 'judge-attempt', role='judge')
    assert ledger.summary()['charged_micro_usd'] == 300


def test_resume_never_double_charges_and_unknown_usage_is_not_zero(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = Ledger(path)
    reserve(ledger)
    assert reserve(Ledger(path))['status'] == 'reserved'
    assert ledger.summary()['charged_micro_usd'] == 300
    ledger.complete('a', {'error': 'interrupted or unknown usage'}, None, PRICE)
    assert reserve(Ledger(path))['status'] == 'complete'
    ledger.complete('a', {'error': 'interrupted or unknown usage'}, None, PRICE)
    assert ledger.summary()['charged_micro_usd'] == 300
    assert ledger.summary()['api'][0]['unknown_usage'] == 1


def test_known_usage_settles_once_and_response_is_durable(tmp_path):
    ledger = Ledger(tmp_path / 'budget.sqlite')
    reserve(ledger)
    ledger.complete('a', {'text': 'ok'}, (10, 20), PRICE)
    assert ledger.summary()['charged_micro_usd'] == 50
    assert ledger.summary()['api'][0]['known_input_tokens'] == 10
    assert ledger.summary()['api'][0]['known_output_tokens'] == 20
    assert 'ok' in reserve(ledger)['result']
    ledger.complete('a', {'text': 'ok'}, (10, 20), PRICE)
    with pytest.raises(ValueError):
        ledger.complete('a', {'text': 'different'}, (10, 20), PRICE)


def test_anthropic_provider_limit_is_additional_not_a_larger_model_budget(tmp_path):
    ledger = Ledger(tmp_path / 'budget.sqlite')
    a = Account(provider='anthropic', model='test-a', monthly_provider_micro_usd=500)
    b = Account(provider='anthropic', model='test-b', monthly_provider_micro_usd=500)
    reserve(ledger, account=a)
    with pytest.raises(BudgetExceeded, match='provider'):
        reserve(ledger, 'b', account=b)
    with pytest.raises(ValueError):
        Account(provider='anthropic', model='x', monthly_model_micro_usd=20000000)
    assert Account(provider='anthropic', model='x').provider_limit() == 20000000


def test_concurrent_reservations_cannot_overspend_shared_budget(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / 'budget.sqlite'
    Ledger(path)
    def attempt(identity):
        try:
            reserve(Ledger(path), identity)
            return 'reserved'
        except BudgetExceeded:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ['a', 'b'])) == ['blocked', 'reserved']
    assert Ledger(path).summary()['charged_micro_usd'] == 300


def test_unknown_price_or_changed_policy_never_issues_new_reservation(tmp_path):
    ledger = Ledger(tmp_path / 'budget.sqlite')
    with pytest.raises(ValueError, match='Unknown'):
        reserve(ledger, price=None)
    assert ledger.summary()['charged_micro_usd'] == 0
    reserve(ledger)
    with pytest.raises(ValueError, match='policy'):
        reserve(ledger, 'b', Account(provider='mock', model='test', monthly_model_micro_usd=1000))
    with pytest.raises(ValueError, match='price'):
        ledger.complete('a', {}, (1, 1), PRICE.model_copy(update={'input_micro_usd_per_million': 1}))


def test_pending_interrupted_attempt_retains_reservation_across_processes(tmp_path):
    path = tmp_path / 'budget.sqlite'
    reserve(Ledger(path))
    summary = Ledger(path).summary()
    assert summary['api'][0]['interrupted'] == 1
    assert summary['charged_micro_usd'] == 300
    with pytest.raises(BudgetExceeded):
        reserve(Ledger(path), 'retry')
