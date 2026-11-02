"""Durable SANDBOX operations: transactional outbox and controlled reconciliation.

No real funds, no merchant API credentials, no identity provider, no ACH/card
transfers. A real deployment must replace SQLite and these reference roles
with vetted multi-tenant infrastructure and verified external settlement.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from typing import Mapping

from .ledger import SandboxLedger, FinanceError, canonical

ACTOR_RE = re.compile(r"[A-Za-z0-9_-]{3,64}\Z")
WORKER_RE = re.compile(r"[A-Za-z0-9_-]{3,64}\Z")
PROVIDERS = frozenset(('sandbox-stripe', 'sandbox-paypal', 'sandbox-bank'))
STATES = frozenset(('pending', 'settled', 'failed', 'reversed'))
MAX_ATTEMPTS = 5


class SandboxOperations:
    """A trusted server-side reference wrapper around one SandboxLedger.

    `staff_roles` is supplied by a **test harness**. It is NOT authentication;
    caller identity must come from a production identity provider in real use.
    """

    def __init__(self, ledger: SandboxLedger, staff_roles: Mapping[str, str] | None = None):
        self.ledger = ledger
        self.staff_roles = dict(staff_roles or {})

    def _role(self, actor: str, permitted: tuple[str, ...]):
        if not isinstance(actor, str) or not ACTOR_RE.fullmatch(actor):
            raise FinanceError('Invalid operator identity')
        if self.staff_roles.get(actor) not in permitted:
            raise FinanceError('Permission denied for sandbox financial operation')

    def claim_outbox(self, worker: str, *, now: int | None = None, lease_seconds: int = 60):
        """Lease one queued notification atomically. No financial side effects."""
        if not isinstance(worker, str) or not WORKER_RE.fullmatch(worker):
            raise FinanceError('Invalid worker identifier')
        if not isinstance(lease_seconds, int) or not 5 <= lease_seconds <= 300:
            raise FinanceError('Lease interval must be between 5 and 300 seconds')
        now = int(time.time()) if now is None else int(now)
        store = self.ledger
        with store.lock:
            store._begin()
            try:
                # Unacknowledged leases eventually dead-letter instead of looping forever.
                store.db.execute('''UPDATE outbox SET status='dead',lease_token=NULL,
                    lease_until=NULL WHERE status='leased' AND lease_until<=?
                    AND attempts>=?''', (now, MAX_ATTEMPTS))
                item = store.db.execute('''
                    SELECT * FROM outbox
                    WHERE (status='pending' AND next_attempt <= ?)
                       OR (status='leased' AND lease_until <= ?)
                    ORDER BY id LIMIT 1''', (now, now)).fetchone()
                if item is None:
                    store.db.commit()
                    return None
                token = secrets.token_hex(20)
                store.db.execute('''UPDATE outbox SET status='leased', lease_token=?,
                     lease_until=?, attempts=attempts+1 WHERE id=?''',
                     (token, now + lease_seconds, item['id']))
                leased = dict(store.db.execute('SELECT * FROM outbox WHERE id=?',
                    (item['id'],)).fetchone())
                store.db.commit()
                return {'id': leased['id'], 'event_type': leased['event_type'],
                        'payload': json.loads(leased['public_payload']),
                        'lease_token': token, 'attempts': leased['attempts']}
            except BaseException:
                store.db.rollback()
                raise

    def _complete(self, item_id: int, lease_token: str, delivered: bool, *, now: int | None = None):
        if type(item_id) is not int or item_id <= 0 or not isinstance(lease_token, str):
            raise FinanceError('Invalid queue acknowledgment')
        now = int(time.time()) if now is None else int(now)
        store = self.ledger
        with store.lock:
            store._begin()
            try:
                row = store.db.execute('SELECT * FROM outbox WHERE id=?', (item_id,)).fetchone()
                if not row or row['status'] != 'leased' or not secrets.compare_digest(
                        row['lease_token'] or '', lease_token) or row['lease_until'] <= now:
                    raise FinanceError('Queue acknowledgment denied: lease missing or expired')
                if delivered:
                    store.db.execute('''UPDATE outbox SET status='delivered', delivered_at=?,
                        lease_token=NULL,lease_until=NULL WHERE id=?''', (now, item_id))
                    status = 'delivered'
                else:
                    attempts = row['attempts']
                    status = 'dead' if attempts >= MAX_ATTEMPTS else 'pending'
                    delay = min(3600, 2 ** attempts)
                    store.db.execute('''UPDATE outbox SET status=?,next_attempt=?,
                        lease_token=NULL,lease_until=NULL WHERE id=?''',
                        (status, now + delay, item_id))
                store.db.commit()
                return status
            except BaseException:
                store.db.rollback()
                raise

    def acknowledge_delivery(self, item_id: int, lease_token: str, *, now: int | None = None):
        """Only after the downstream consumer confirms an idempotent receipt."""
        return self._complete(item_id, lease_token, True, now=now)

    def record_delivery_failure(self, item_id: int, lease_token: str, *, now: int | None = None):
        """Back off then dead-letter; failures do NOT alter transaction balances."""
        return self._complete(item_id, lease_token, False, now=now)

    def queue_summary(self, *, now: int | None = None):
        now = int(time.time()) if now is None else int(now)
        db = self.ledger.db
        result = {r['status']: r['n'] for r in db.execute(
            'SELECT status,COUNT(*) AS n FROM outbox GROUP BY status')}
        return {**{name: result.get(name, 0) for name in ('pending', 'leased', 'delivered', 'dead')},
                'expired_leases': db.execute("SELECT COUNT(*) FROM outbox WHERE status='leased' AND lease_until<=?", (now,)).fetchone()[0]}

    def record_reconciliation(self, *, actor: str, provider: str, statement_id: str,
                              provider_records: list[dict]):
        """Write a repeatable exception report; never silently adjust the journal.

        The source statement must be authenticated before it reaches this API.
        This module does not authenticate external statements itself.
        Only provided records are examined; missing provider-side transactions
        are NOT inferred because statements can be partial.
        """
        self._role(actor, ('reconciler',))
        if provider not in PROVIDERS:
            raise FinanceError('Only sandbox payment providers are supported')
        if not isinstance(statement_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{6,120}', statement_id):
            raise FinanceError('Invalid statement identifier')
        if not isinstance(provider_records, list) or len(provider_records) > 10000:
            raise FinanceError('Invalid reconciliation statement')
        seen = set()
        validated = []
        expected_fields = {'provider_ref', 'provider', 'currency', 'minor', 'status'}
        for rec in provider_records:
            if not isinstance(rec, dict) or set(rec) != expected_fields:
                raise FinanceError('Invalid statement record schema')
            ref = rec['provider_ref']
            if (not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,120}', ref)
                    or ref in seen or rec['provider'] != provider or rec['status'] not in STATES
                    or not isinstance(rec['currency'], str) or not re.fullmatch(r'[A-Z]{3}', rec['currency'])
                    or type(rec['minor']) is not int or rec['minor'] <= 0):
                raise FinanceError('Malformed or repeated provider record')
            seen.add(ref)
            validated.append(rec)
        # Sorting makes signed statement content independent of row ordering.
        validated.sort(key=lambda r: r['provider_ref'])
        digest = hashlib.sha256(canonical(validated).encode()).hexdigest()
        store = self.ledger
        with store.lock:
            store._begin()
            try:
                existing = store.db.execute('SELECT * FROM reconciliation_runs WHERE provider=? AND statement_id=?',
                    (provider, statement_id)).fetchone()
                if existing:
                    if existing['content_sha256'] != digest:
                        raise FinanceError('Reconciliation statement ID conflict')
                    result = dict(existing)
                    store.db.commit()
                    return result
                issues = store.reconcile(validated)
                run_id = str(uuid.uuid4())
                now = int(time.time())
                store.db.execute('''INSERT INTO reconciliation_runs VALUES(?,?,?,?,?,?,?)''',
                    (run_id, provider, statement_id, digest, actor, now, len(issues)))
                for item in issues:
                    ref_hash = hashlib.sha256(item['provider_ref'].encode()).hexdigest()
                    store.db.execute('''INSERT INTO reconciliation_exceptions
                      (id,run_id,ref_sha256,reason,modified) VALUES(?,?,?,?,?)''',
                        (str(uuid.uuid4()), run_id, ref_hash, item['error'], now))
                store._append_audit('reconciliation.recorded', {'run_id': run_id,
                    'statement_digest': digest, 'exception_count': len(issues)})
                store.db.commit()
                return dict(store.db.execute('SELECT * FROM reconciliation_runs WHERE id=?',
                    (run_id,)).fetchone())
            except BaseException:
                store.db.rollback()
                raise

    def list_exceptions(self, *, actor: str, state: str = 'open'):
        self._role(actor, ('reconciler', 'reviewer', 'auditor'))
        if state not in ('open', 'acknowledged', 'resolved', 'all'):
            raise FinanceError('Invalid exception state filter')
        query = 'SELECT * FROM reconciliation_exceptions'
        params = ()
        if state != 'all':
            query += ' WHERE state=?'
            params = (state,)
        return [dict(r) for r in self.ledger.db.execute(query + ' ORDER BY modified, id', params)]

    def acknowledge_exception(self, *, actor: str, exception_id: str, note: str):
        self._role(actor, ('reconciler',))
        return self._review(actor, exception_id, note, 'open', 'acknowledged')

    def resolve_exception(self, *, actor: str, exception_id: str, note: str):
        self._role(actor, ('reviewer',))
        return self._review(actor, exception_id, note, 'acknowledged', 'resolved')

    def _review(self, actor, exception_id, note, before, after):
        if not isinstance(exception_id, str) or len(exception_id) > 80:
            raise FinanceError('Invalid exception identifier')
        if not isinstance(note, str) or not 12 <= len(note.strip()) <= 500:
            raise FinanceError('Written evidence required (12–500 characters)')
        store = self.ledger
        with store.lock:
            store._begin()
            try:
                row = store.db.execute('SELECT * FROM reconciliation_exceptions WHERE id=?',
                    (exception_id,)).fetchone()
                if not row or row['state'] != before:
                    raise FinanceError('Exception state transition denied')
                if after == 'resolved' and row['maker'] == actor:
                    raise FinanceError('Independent checker must differ from the maker')
                column = 'maker' if before == 'open' else 'checker'
                store.db.execute(f'''UPDATE reconciliation_exceptions SET state=?, {column}=?,
                     note=?, modified=? WHERE id=?''', (after, actor, note.strip(), int(time.time()), exception_id))
                store._append_audit('reconciliation.' + after,
                    {'exception_id': exception_id, 'actor': actor, 'transition': after})
                store.db.commit()
                return after
            except BaseException:
                store.db.rollback()
                raise

    def health(self):
        """Read-only operational snapshot, no balances, identities or secret material."""
        db = self.ledger.db
        integrity = self.ledger.verify_integrity()
        integrity_row = db.execute('PRAGMA quick_check').fetchone()[0]
        exceptions = {r['state']: r['n'] for r in db.execute(
            'SELECT state,COUNT(*) AS n FROM reconciliation_exceptions GROUP BY state')}
        return {'service': 'NOCTURNE SANDBOX (no live money)',
                'sqlite_quick_check': integrity_row,
                'journal_integrity_ok': not integrity,
                'journal_problem_count': len(integrity),
                'outbox': self.queue_summary(),
                'reconciliation_exceptions': {s: exceptions.get(s, 0) for s in ('open', 'acknowledged', 'resolved')},
                'live_payments_enabled': False,
                'production_ready': False}
