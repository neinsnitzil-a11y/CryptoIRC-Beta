"""Phase 16: privacy-minimized local consent/audit records and server-side eligibility primitives.

NO KYC, AML screening, sanctions checking, fiat transfer, compliance approval, or
provider integration occurs in this module. A local desktop entry NEVER authorizes
money movement. Store no names, addresses, wallet seeds, bank details or IDs.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

class ComplianceError(ValueError):
    pass

SCOPES = frozenset({'PRIVACY_NOTICE', 'TERMS_NOTICE', 'RISK_DISCLOSURE'})
PRIVACY_REQUESTS = frozenset({'ACCESS', 'CORRECTION', 'DELETION', 'RETENTION_REVIEW'})
OPERATIONS = frozenset({'BUY', 'SELL', 'DEPOSIT', 'WITHDRAWAL'})
COUNTRY = re.compile(r'[A-Z]{2}\Z')
PROVIDER = re.compile(r'[A-Za-z][A-Za-z0-9_-]{2,63}\Z')
CURRENCY = re.compile(r'[A-Z0-9]{2,12}\Z')
ZERO = '0' * 64
MAX_EVENTS = 50000

def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def local_journal_path():
    # Outside install/build tree so user data is not packaged by PyInstaller.
    root = (Path(os.environ.get('APPDATA', '')) / 'CRYPTO_NOCTURNE' if
            os.name == 'nt' and os.environ.get('APPDATA') else
            Path.home() / '.local' / 'share' / 'crypto_nocturne')
    return root / 'compliance_local.sqlite3'


class LocalComplianceJournal:
    """Append-only local evidence. Hash chain DETECTS casual edits, not privileged rewrites.

    Never treat consent recorded here as legal identity verification or eligibility.
    """
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else local_journal_path()
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.path.is_symlink():
            raise ComplianceError('Refusing symbolic-link compliance journal')
        with closing(self._db()) as con:
            with con:
                con.execute('''CREATE TABLE IF NOT EXISTS local_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    created INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    version TEXT NOT NULL,
                    prev_digest TEXT NOT NULL,
                    digest TEXT NOT NULL)''')
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

    def _db(self):
        con = sqlite3.connect(self.path, timeout=8)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _digest(seq, created, action, scope, version, previous):
        payload = [seq, created, action, scope, version, previous]
        return hashlib.sha256(_canonical(payload).encode('ascii')).hexdigest()

    def verify(self):
        previous = ZERO
        count = 0
        with closing(self._db()) as con:
            for row in con.execute('SELECT * FROM local_events ORDER BY seq'):
                count += 1
                if count > MAX_EVENTS or row['seq'] != count or row['prev_digest'] != previous:
                    raise ComplianceError('Local audit sequence is inconsistent')
                expected = self._digest(row['seq'], row['created'], row['action'], row['scope'], row['version'], previous)
                if not hmac.compare_digest(expected, row['digest']):
                    raise ComplianceError('Local audit digest mismatch')
                previous = row['digest']
        return count

    def append(self, action, scope, version, *, now=None):
        if action not in ('ACCEPT', 'REVOKE', 'PRIVACY_REQUEST'):
            raise ComplianceError('Unsupported audit event')
        # Draft terms cannot be recorded as accepted, even through direct API use.
        if action == 'ACCEPT' and scope == 'TERMS_NOTICE' and version.startswith('terms-draft'):
            raise ComplianceError('Draft terms are not eligible for acceptance')
        if action == 'PRIVACY_REQUEST':
            if scope not in PRIVACY_REQUESTS or version != '1':
                raise ComplianceError('Invalid privacy request')
        elif scope not in SCOPES or not re.fullmatch(r'[A-Za-z0-9._-]{1,40}', version or ''):
            raise ComplianceError('Invalid consent notice identifier')
        created = int(time.time()) if now is None else int(now)
        with closing(self._db()) as con:
            with con:
                con.execute('BEGIN IMMEDIATE')
                previous = ZERO
                count = 0
                for row in con.execute('SELECT * FROM local_events ORDER BY seq'):
                    count += 1
                    if count > MAX_EVENTS or row['seq'] != count or row['prev_digest'] != previous:
                        raise ComplianceError('Local audit sequence invalid; new records blocked')
                    expected = self._digest(row['seq'], row['created'], row['action'], row['scope'], row['version'], previous)
                    if not hmac.compare_digest(expected, row['digest']):
                        raise ComplianceError('Local audit corruption; new records blocked')
                    previous = row['digest']
                if count >= MAX_EVENTS:
                    raise ComplianceError('Local journal limit reached; archive with review')
                digest = self._digest(count + 1, created, action, scope, version, previous)
                con.execute('INSERT INTO local_events(created,action,scope,version,prev_digest,digest) VALUES(?,?,?,?,?,?)',
                            (created, action, scope, version, previous, digest))
                return count + 1

    def records(self, limit=100):
        self.verify()
        with closing(self._db()) as con:
            rows = con.execute('SELECT seq,created,action,scope,version,digest FROM local_events ORDER BY seq DESC LIMIT ?',
                               (max(1,min(int(limit),500)),)).fetchall()
            return [dict(row) for row in rows]

    def consent_state(self, scope, version):
        if scope not in SCOPES:
            raise ComplianceError('Unknown notice')
        self.verify()
        with closing(self._db()) as con:
            row = con.execute('SELECT action FROM local_events WHERE scope=? AND version=? AND action IN (\'ACCEPT\',\'REVOKE\') ORDER BY seq DESC LIMIT 1',
                              (scope, version)).fetchone()
            return bool(row and row['action'] == 'ACCEPT')

    def export_redacted(self):
        # Metadata only; not a proof of identity or authorization; no PII fields.
        return _canonical({'format':'NOCTURNE_LOCAL_COMPLIANCE_V1', 'verified_local_chain':True, 'export_scope':'MOST_RECENT_500_ONLY', 'events':self.records(500)})


@dataclass(frozen=True)
class EligibilityResult:
    allowed: bool
    code: str
    note: str


def sign_policy_for_server(policy: dict, signing_key: bytes) -> dict:
    """Server/test utility; NEVER call with a key stored in the desktop app."""
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ComplianceError('Server signing key must be protected and at least 32 bytes')
    raw = _canonical(policy).encode('ascii')
    return {'policy':policy, 'signature':hmac.new(signing_key, raw, hashlib.sha256).hexdigest()}


def assess_provider_eligibility(envelope, *, signing_key=None, provider='', country='', operation='', currency='',
                                amount_minor=0, environment='sandbox', server_context=False, now=None):
    """Conservative signed-policy preflight; NOT KYC, sanctions or licensing certification.

    Only a separately configured backend may assess 'live' requests, and this
    function alone NEVER initiates money movement or guarantees provider acceptance.
    """
    deny = lambda code, message: EligibilityResult(False, code, message)
    if not server_context:
        return deny('DESKTOP_NOT_AUTHORITY', 'Only a separately secured provider backend can authorize eligibility.')
    if not signing_key or not isinstance(signing_key, bytes) or len(signing_key) < 32:
        return deny('NO_TRUST_KEY', 'No verified backend signing key available.')
    if not isinstance(envelope, dict) or set(envelope) != {'policy', 'signature'}:
        return deny('UNVERIFIED_POLICY', 'Signed policy was not provided.')
    policy, sig = envelope['policy'], envelope['signature']
    if not isinstance(policy, dict) or not isinstance(sig, str) or not re.fullmatch('[a-f0-9]{64}', sig):
        return deny('BAD_POLICY', 'Invalid policy encoding.')
    try: expected = hmac.new(signing_key, _canonical(policy).encode('ascii'), hashlib.sha256).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return deny('BAD_SCHEMA', 'Invalid eligibility policy values.')
    if not hmac.compare_digest(expected, sig):
        return deny('BAD_SIGNATURE', 'Policy signature verification failed.')
    required = {'version','environment','provider','countries','operations','currencies','issued_at','expires_at','max_minor'}
    if set(policy) != required or policy['version'] != 1:
        return deny('BAD_SCHEMA', 'Unrecognized policy version or fields.')
    current = int(time.time()) if now is None else int(now)
    try:
        if (type(policy['issued_at']) is not int or type(policy['expires_at']) is not int
            or not policy['issued_at'] <= current < policy['expires_at']
            or policy['expires_at'] - policy['issued_at'] > 86400):
            return deny('EXPIRED', 'Policy expired or valid for too long.')
        if not isinstance(policy['countries'], list) or not isinstance(policy['operations'], list) or not isinstance(policy['currencies'], list):
            return deny('BAD_SCHEMA', 'Policy lists invalid.')
        if (len(policy['countries']) > 250 or len(policy['operations']) > 10 or len(policy['currencies']) > 250
            or not all(isinstance(c,str) and COUNTRY.fullmatch(c) for c in policy['countries'])
            or not all(o in OPERATIONS for o in policy['operations'])
            or not all(isinstance(c,str) and CURRENCY.fullmatch(c) for c in policy['currencies'])
            or not isinstance(policy['provider'], str) or not PROVIDER.fullmatch(policy['provider'])
            or type(policy['max_minor']) is not int or policy['max_minor'] < 1):
            return deny('BAD_SCHEMA', 'Policy scope invalid.')
        if environment not in ('sandbox','live') or policy['environment'] != environment:
            return deny('ENVIRONMENT', 'Sandbox/live environment mismatch.')
        if (provider != policy['provider'] or country not in policy['countries']
            or operation not in policy['operations'] or currency not in policy['currencies']):
            return deny('OUTSIDE_SCOPE', 'Provider, jurisdiction, transaction type or currency not approved in policy.')
        if type(amount_minor) is not int or not 1 <= amount_minor <= policy['max_minor']:
            return deny('LIMIT', 'Amount exceeds the scoped policy limit.')
    except (TypeError, ValueError, KeyError):
        return deny('BAD_SCHEMA', 'Invalid eligibility policy values.')
    return EligibilityResult(True, 'POLICY_SCOPE_MATCH',
        'Signed scope matched; actual provider, sanctions, KYC and legal approvals must still be verified separately.')
