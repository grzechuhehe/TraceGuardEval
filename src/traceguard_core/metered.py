"""Fail-closed transport for a bounded development slice, not subscription OAuth."""

import json
import re
import time
from collections.abc import Callable

import httpx
from pydantic import Field

from traceguard_core.budget import Account, BudgetExceeded, Ledger, Price
from traceguard_core.models import Model, canonical, digest
from traceguard_core.experiment import locked


class Limits(Model):
    max_calls: int = Field(default=10, gt=0)
    max_tokens: int = Field(default=20000, gt=0)
    max_seconds: float = Field(default=60.0, gt=0)
    input_cap: int = Field(default=2048, gt=0)
    output_cap: int = Field(default=512, gt=0)
    retries: int = Field(default=1, ge=0, le=5)


class MeteredChat:
    def __init__(self, ledger: Ledger, account: Account, price: Price | None, limits: Limits,
                 transport: httpx.MockTransport | None = None, *, access_confirmed: bool = False,
                 clock: Callable[[], float] = time.time):
        if transport is None and not access_confirmed:
            raise ValueError('Programmatic API access is not confirmed; use MockTransport')
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise ValueError('Offline transport must be MockTransport')
        if transport is None:
            raise ValueError('Live batches are not enabled in the development slice')
        self.ledger, self.account, self.price, self.limits = ledger, account, price, limits
        self.clock, self.started = clock, clock()
        self.client = httpx.Client(transport=transport, trust_env=False, follow_redirects=False)

    def close(self) -> None:
        self.client.close()

    def call(self, identity: str, messages: list[dict], role: str, parameters: dict | None = None) -> dict:
        if not re.fullmatch(r'[A-Za-z0-9_-]+/(agent|judge)/[0-9]+', identity) or identity.split('/')[1] != role:
            raise ValueError('Use run-id/role/step identities')
        with locked(self.ledger.path.with_suffix('.calls.lock')):
            if parameters is not None and not set(parameters) <= {'temperature', 'seed'}:
                raise ValueError('Unsupported request parameters')
            return self._call(identity, messages, role, parameters or {})

    def _call(self, identity: str, messages: list[dict], role: str, parameters: dict) -> dict:
        session = identity.rsplit('/', 1)[0]
        binding = digest({'account': self.account.model_dump(), 'limits': self.limits.model_dump(),
                          'price': self.price.model_dump() if self.price else None})
        with self.ledger.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, started REAL, binding TEXT)')
            db.execute('INSERT OR IGNORE INTO sessions VALUES (?,?,?)', (session, self.clock(), binding))
            saved = db.execute('SELECT * FROM sessions WHERE id=?', (session,)).fetchone()
            if saved['binding'] != binding:
                raise ValueError('Session configuration changed')
            self.started = saved['started']
        body = {'model': self.account.model, 'messages': messages, 'max_tokens': self.limits.output_cap, **parameters}
        # UTF-8 bytes plus a per-message framing allowance upper-bound the local prompt budget.
        # Live access stays disabled until provider-specific token accounting is validated.
        if len(canonical(messages).encode()) + 64 * len(messages) > self.limits.input_cap:
            raise BudgetExceeded('Input exceeds conservative local token bound')
        for attempt in range(self.limits.retries + 1):
            key = f'{identity}:{attempt}'
            with self.ledger.connect() as db:
                cached = db.execute('SELECT * FROM attempts WHERE id=?', (key,)).fetchone()
                prefix = session + '/'
                related = db.execute('SELECT * FROM attempts WHERE SUBSTR(id,1,?)=?', (len(prefix), prefix)).fetchall()
            calls = len(related)
            tokens = sum(r['input_cap'] + r['output_cap'] for r in related)
            if cached is None:
                if calls >= self.limits.max_calls or tokens + self.limits.input_cap + self.limits.output_cap > self.limits.max_tokens:
                    raise BudgetExceeded('Session call or token limit reached before call')
                if self.clock() - self.started >= self.limits.max_seconds:
                    raise BudgetExceeded('Session time limit reached before call')
            reserved = self.ledger.reserve(key, self.account, role, body, self.limits.input_cap,
                                           self.limits.output_cap, self.price)
            if reserved['status'] == 'complete':
                result = json.loads(reserved['result'])
            elif cached is not None:
                result = {'error': 'INTERRUPTED', 'retryable': True}
            else:
                started = self.clock()
                try:
                    response = self.client.post('https://mock.invalid/chat/completions', json=body,
                                                timeout=max(0.001, self.limits.max_seconds - (started - self.started)))
                    if response.is_success:
                        envelope = response.json()
                        content = envelope['choices'][0]['message']['content']
                        if not isinstance(content, str):
                            raise ValueError('Non-text content')
                        usage = envelope.get('usage', {})
                        counts = (usage.get('prompt_tokens'), usage.get('completion_tokens')) if isinstance(usage, dict) else (None, None)
                        known = counts if all(type(n) is int and n >= 0 for n in counts) else None
                        result = {'content': content, 'retryable': False, 'error': None}
                        if self.clock() - self.started > self.limits.max_seconds:
                            result = {'error': 'TIME_LIMIT', 'retryable': False}
                        self.ledger.complete(key, result, known, self.price)
                    else:
                        result = {'error': f'HTTP_{response.status_code}',
                                  'retryable': response.status_code == 429 or response.status_code >= 500}
                        self.ledger.complete(key, result, None, self.price)
                except httpx.RequestError:
                    result = {'error': 'TRANSPORT', 'retryable': True}
                    self.ledger.complete(key, result, None, self.price)
                except (ValueError, KeyError, TypeError, IndexError):
                    result = {'error': 'FORMAT', 'retryable': False}
                    self.ledger.complete(key, result, None, self.price)
            if not result['retryable'] or attempt == self.limits.retries:
                return result
        raise AssertionError('Unreachable')
