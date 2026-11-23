"""Durable API reservations shared by generation, judging and retries."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field

from traceguard_core.models import Model, canonical, digest


class BudgetExceeded(ValueError):
    pass


class Price(Model):
    input_micro_usd_per_million: int = Field(gt=0)
    output_micro_usd_per_million: int = Field(gt=0)
    source: str = Field(min_length=1)
    checked_on: str = Field(min_length=1)

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        if type(input_tokens) is not int or type(output_tokens) is not int or min(input_tokens, output_tokens) < 0:
            raise ValueError('Invalid token counts')
        total = input_tokens * self.input_micro_usd_per_million + output_tokens * self.output_micro_usd_per_million
        return (total + 999999) // 1000000


class Account(Model):
    provider: Literal['openai', 'anthropic', 'openrouter', 'mock']
    model: str = Field(min_length=1)
    monthly_model_micro_usd: int = Field(default=10000000, gt=0, le=10000000)
    monthly_provider_micro_usd: int | None = Field(default=None, gt=0)

    def provider_limit(self) -> int | None:
        if self.provider == 'anthropic':
            return min(self.monthly_provider_micro_usd or 20000000, 20000000)
        return self.monthly_provider_micro_usd


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, binding TEXT NOT NULL, month TEXT NOT NULL,
                provider TEXT NOT NULL, model TEXT NOT NULL, role TEXT NOT NULL,
                reserved INTEGER NOT NULL, charged INTEGER NOT NULL,
                input_cap INTEGER NOT NULL, output_cap INTEGER NOT NULL,
                status TEXT NOT NULL, result TEXT, usage_known INTEGER NOT NULL, price TEXT NOT NULL)''')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(attempts)')}
            for name in ('input_tokens', 'output_tokens'):
                if name not in columns:
                    db.execute(f'ALTER TABLE attempts ADD COLUMN {name} INTEGER')
            db.execute('CREATE TABLE IF NOT EXISTS policy (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, attempt_id: str, account: Account, role: Literal['agent', 'judge'],
                request: dict, input_cap: int, output_cap: int, price: Price | None) -> dict:
        if price is None:
            raise ValueError('Unknown API price; request blocked')
        if not attempt_id or role not in {'agent', 'judge'} or min(input_cap, output_cap) <= 0:
            raise ValueError('Invalid reservation')
        reserved = price.cost(input_cap, output_cap)
        binding = digest({'account': account.model_dump(), 'role': role, 'request': request,
                          'input_cap': input_cap, 'output_cap': output_cap, 'price': price.model_dump()})
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for key, value in [(f'model:{account.provider}:{account.model}', account.monthly_model_micro_usd),
                               (f'provider:{account.provider}', account.provider_limit())]:
                stored = db.execute('SELECT value FROM policy WHERE key=?', (key,)).fetchone()
                encoded = canonical(value)
                if stored is not None and stored['value'] != encoded:
                    raise ValueError('Budget policy changed; do not replace shared ledger')
                db.execute('INSERT OR IGNORE INTO policy VALUES (?,?)', (key, encoded))
            old = db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone()
            if old is not None:
                if old['binding'] != binding:
                    raise ValueError('Attempt identity changed')
                return dict(old)
            model_spent = db.execute('SELECT COALESCE(SUM(charged),0) FROM attempts WHERE month=? AND provider=? AND model=?',
                                     (month, account.provider, account.model)).fetchone()[0]
            provider_spent = db.execute('SELECT COALESCE(SUM(charged),0) FROM attempts WHERE month=? AND provider=?',
                                        (month, account.provider)).fetchone()[0]
            if model_spent + reserved > account.monthly_model_micro_usd:
                raise BudgetExceeded('Monthly model budget exhausted before API call')
            if account.provider_limit() is not None and provider_spent + reserved > account.provider_limit():
                raise BudgetExceeded('Monthly provider budget exhausted before API call')
            db.execute('INSERT INTO attempts (id,binding,month,provider,model,role,reserved,charged,input_cap,output_cap,status,result,usage_known,price) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (attempt_id, binding, month, account.provider, account.model, role, reserved, reserved,
                        input_cap, output_cap, 'reserved', None, 0, canonical(price.model_dump())))
            return dict(db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone())

    def complete(self, attempt_id: str, result: dict, usage: tuple[int, int] | None, price: Price) -> None:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone()
            if row is None:
                raise ValueError('Attempt was not reserved')
            if row['price'] != canonical(price.model_dump()):
                raise ValueError('Settlement price differs from reservation')
            if usage is not None:
                cost = price.cost(*usage)
                if usage[0] > row['input_cap'] or usage[1] > row['output_cap']:
                    cost = max(cost, row['reserved'])
            else:
                cost = row['reserved']
            payload = canonical(result)
            if row['status'] == 'complete':
                if row['result'] != payload or row['charged'] != cost or row['usage_known'] != int(usage is not None) or (
                    usage is not None and (row['input_tokens'], row['output_tokens']) != usage
                ):
                    raise ValueError('Settlement changed')
                return
            db.execute('UPDATE attempts SET status=?, result=?, charged=?, usage_known=?, input_tokens=?, output_tokens=? WHERE id=?',
                       ('complete', payload, cost, int(usage is not None),
                        usage[0] if usage else None, usage[1] if usage else None, attempt_id))

    def summary(self) -> dict:
        with self.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM attempts ORDER BY id')]
        groups = {}
        for row in rows:
            key = (row['month'], row['provider'], row['model'], row['role'])
            group = groups.setdefault(key, {'month': key[0], 'provider': key[1], 'model': key[2], 'role': key[3],
                                             'attempts': 0, 'charged_micro_usd': 0, 'unknown_usage': 0, 'interrupted': 0,
                                             'known_input_tokens': 0, 'known_output_tokens': 0, 'unknown_token_records': 0})
            group['attempts'] += 1
            group['unknown_token_records'] += row['input_tokens'] is None or row['output_tokens'] is None
            group['known_input_tokens'] += row['input_tokens'] or 0
            group['known_output_tokens'] += row['output_tokens'] or 0
            group['charged_micro_usd'] += row['charged']
            group['unknown_usage'] += not row['usage_known']
            group['interrupted'] += row['status'] == 'reserved'
        return {'currency': 'USD', 'api': list(groups.values()), 'subscription_usage': 'NOT_MEASURED_SEPARATELY',
                'accounting': 'known_cost_plus_unresolved_reservations',
                'known_cost_micro_usd': sum(r['charged'] for r in rows if r['usage_known']),
                'unresolved_reserved_micro_usd': sum(r['charged'] for r in rows if not r['usage_known']),
                'charged_micro_usd': sum(r['charged'] for r in rows)}
