"""Phase 14: durable, bounded, *read-only* operational maintenance.

Only allowlisted no-payload diagnostics are queued. This module never imports
wallet signers, never broadcasts, unlocks, or retries a financial transaction.
The operational DB lives in the user's data directory, never with packaged code.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import os
import secrets
import sys
import sqlite3
import time
import uuid

from universal_transactions import data_dir

KINDS = frozenset(('database_integrity', 'transaction_review'))
MAX_QUEUED = 128
MAX_ATTEMPTS = 3
LEASING_SECONDS = 30
ALLOWED_DB = ('universal_transactions.sqlite3', 'unified_wallets.sqlite3', 'token_registry.sqlite3')
REVIEW_STATES = frozenset(('UNKNOWN', 'BROADCASTING', 'REORG_REVIEW',
                           'REQUIRES_REVIEW', 'CONFLICTED', 'REPLACED'))

class ReliabilityError(ValueError):
    pass


def _db_connect(path: Path, *, readonly=False):
    if readonly:
        db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=5)
    else:
        db = sqlite3.connect(path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA busy_timeout=10000')
    db.row_factory=sqlite3.Row
    return db


class ReliabilityQueue:
    """SQL-backed lease queue. No user payloads, amounts, credentials or keys.

    A resumed lease is *only* an observation job; payment sends and reconciled
    settlement updates are intentionally unsupported. Claims are atomic across
    different queue instances/processes with BEGIN IMMEDIATE.
    """
    def __init__(self, path=None, *, observation_dir=None):
        self.path=Path(path) if path is not None else data_dir()/'operations_reliability.sqlite3'
        self.observation_dir=Path(observation_dir) if observation_dir is not None else data_dir()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ReliabilityError('Operational store must be a regular file')
        with closing(_db_connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','leased','done','dead')),
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at INTEGER NOT NULL,
                lease_until INTEGER,
                lease_token TEXT,
                queued_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                result TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(state,available_at);
            """)
            db.commit()
        if os.name!='nt': os.chmod(self.path,0o600)

    def enqueue(self, kind, *, now=None):
        if kind not in KINDS: raise ReliabilityError('Only allowlisted, read-only operations may be enqueued')
        now=int(time.time()) if now is None else int(now)
        with closing(_db_connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            # Coalesce exactly one outstanding job per category.
            old=db.execute('SELECT id FROM jobs WHERE kind=? AND state IN ("queued","leased") LIMIT 1',(kind,)).fetchone()
            if old:
                db.commit();return old['id'],False
            count=db.execute('SELECT COUNT(*) FROM jobs WHERE state IN ("queued","leased")').fetchone()[0]
            if count>=MAX_QUEUED:
                db.rollback();raise ReliabilityError('Read-only maintenance queue at capacity')
            uid=uuid.uuid4().hex
            db.execute("""INSERT INTO jobs (id,kind,state,available_at,queued_at,updated_at)
                VALUES (?,?,'queued',?,?,?)""",(uid,kind,now,now,now))
            db.commit()
        return uid,True

    def claim(self, *, now=None, lease_seconds=LEASING_SECONDS):
        if type(lease_seconds) is not int or not 5<=lease_seconds<=300:
            raise ReliabilityError('Invalid lease length')
        now=int(time.time()) if now is None else int(now)
        with closing(_db_connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("""UPDATE jobs SET state='dead',lease_token=NULL,lease_until=NULL,updated_at=?,
                  result='retry_exhausted' WHERE state='leased' AND lease_until<=? AND attempts>=?""",
                  (now,now,MAX_ATTEMPTS))
            row=db.execute("""SELECT id,kind,attempts FROM jobs
                  WHERE (state='queued' AND available_at<=?)
                    OR (state='leased' AND lease_until<=? AND attempts<?)
                  ORDER BY available_at,queued_at LIMIT 1""",(now,now,MAX_ATTEMPTS)).fetchone()
            if row is None:
                db.commit();return None
            token=secrets.token_hex(24)
            db.execute("""UPDATE jobs SET state='leased',lease_token=?,lease_until=?,
                attempts=attempts+1,updated_at=? WHERE id=?""",
                (token,now+lease_seconds,now,row['id']))
            db.commit()
            return {'id':row['id'],'kind':row['kind'],'lease_token':token,
                    'attempt':row['attempts']+1}

    def _finish(self, claim, *, success, result='', now=None):
        now=int(time.time()) if now is None else int(now)
        if not isinstance(claim,dict) or not isinstance(claim.get('id'),str):
            raise ReliabilityError('Invalid lease identity')
        with closing(_db_connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT attempts FROM jobs WHERE id=? AND state=? AND lease_token=?',
                           (claim['id'],'leased',claim.get('lease_token'))).fetchone()
            if row is None:
                db.rollback();raise ReliabilityError('Stale or invalid lease; completion rejected')
            if success:
                state='done'; available=now; marker=result
            else:
                state='dead' if row['attempts']>=MAX_ATTEMPTS else 'queued'
                available=now+min(300,2**row['attempts'])
                marker='diagnostic_failed' if state=='dead' else 'retry_scheduled'
            if not isinstance(marker,str) or len(marker)>200 or any(ord(c)<32 for c in marker):
                db.rollback();raise ReliabilityError('Invalid sanitized operation result')
            db.execute("""UPDATE jobs SET state=?,result=?,available_at=?,lease_token=NULL,
                lease_until=NULL,updated_at=? WHERE id=?""",
                (state,marker,available,now,claim['id']))
            db.commit()
        return state

    def complete(self, claim, result, *, now=None):
        # Only our own predetermined status strings; no user-visible exception text.
        if result not in ('ok','attention_required','no_transaction_data','integrity_failed'):
            raise ReliabilityError('Result is not a recognized operational status')
        return self._finish(claim,success=True,result=result,now=now)

    def fail(self, claim, *, now=None):
        return self._finish(claim,success=False,now=now)

    def stats(self):
        with closing(_db_connect(self.path,readonly=True)) as db:
            rows=db.execute('SELECT state,COUNT(*) AS count FROM jobs GROUP BY state').fetchall()
            recent=db.execute('SELECT kind,state,attempts,result,updated_at FROM jobs ORDER BY updated_at DESC LIMIT 12').fetchall()
            return {'counts':{state:next((row['count'] for row in rows if row['state']==state),0)
                    for state in ('queued','leased','done','dead')},
                    'recent':[dict(row) for row in recent]}

    def integrity_scan(self):
        # Only check internal operational DB + deliberately allowlisted public
        # projection DBs. Never scan a wallet, keystore or privileged payment DB.
        results={}
        for name,path in [('operations',self.path)]+[
             (n,(self.observation_dir/n)) for n in ALLOWED_DB]:
            if not path.exists():
                results[name]='not_configured';continue
            if path.is_symlink() or not path.is_file():
                results[name]='invalid_file';continue
            try:
                with closing(_db_connect(path,readonly=True)) as db:
                    rows=db.execute('PRAGMA quick_check').fetchall()
                    results[name]='ok' if len(rows)==1 and rows[0][0]=='ok' else 'integrity_failed'
            except sqlite3.Error:
                results[name]='unavailable'
        return results

    def transaction_review(self):
        path=self.observation_dir/'universal_transactions.sqlite3'
        if not path.exists(): return {'status':'no_transaction_data','attention_count':0}
        if path.is_symlink() or not path.is_file():
            raise ReliabilityError('Transaction record is not a regular file')
        with closing(_db_connect(path,readonly=True)) as db:
            rows=db.execute('SELECT data FROM snapshots LIMIT 200001').fetchall()
        if len(rows)>200000: raise ReliabilityError('Transaction review row limit exceeded')
        count=0
        for row in rows:
            try:
                doc=json.loads(row['data'])
                if isinstance(doc,dict) and doc.get('status') in REVIEW_STATES:count+=1
            except (ValueError,TypeError):
                count+=1 # malformed records require review
        return {'status':'attention_required' if count else 'ok', 'attention_count':count}

    def run_one(self, *, now=None):
        lease=self.claim(now=now)
        if lease is None:return {'executed':False,'status':'idle'}
        try:
            if lease['kind']=='database_integrity':
                detail=self.integrity_scan()
                result='integrity_failed' if any(v in ('unavailable','integrity_failed','invalid_file') for v in detail.values()) else 'ok'
            elif lease['kind']=='transaction_review':
                detail=self.transaction_review()
                result=detail['status']
            else: raise ReliabilityError('Operation category invalid')
            self.complete(lease,result,now=now)
            return {'executed':True,'kind':lease['kind'],'status':result,'details':detail}
        except Exception:
            # Deliberately do not store or display exception contents.
            self.fail(lease,now=now)
            return {'executed':True,'kind':lease['kind'],'status':'retry_scheduled_or_dead'}

    def backup(self,destination):
        """Exclusive SQLite online backup of operational metadata only.

        No wallet DB, no signing key, no financial ledger. Never overwrites files.
        This metadata backup is NOT encrypted and MUST be stored securely.
        """
        dest=Path(destination)
        if dest.suffix.lower() not in ('.sqlite3','.db'):
            raise ReliabilityError('Operational backup must use .sqlite3 or .db')
        if not dest.parent.is_dir() or dest.is_symlink() or dest.exists():
            raise ReliabilityError('Choose a new file in an existing backup directory')
        source_root=Path(__file__).resolve().parents[1]
        install_root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else source_root
        if (dest.resolve().is_relative_to(source_root) or
            dest.resolve().is_relative_to(install_root) or
            dest.resolve()==self.path.resolve()):
            raise ReliabilityError('Backup cannot be inside the application source or overwrite the operational DB')
        flags=os.O_CREAT|os.O_EXCL|os.O_RDWR
        if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
        fd=os.open(str(dest),flags,0o600)
        os.close(fd)
        try:
            with closing(_db_connect(self.path,readonly=True)) as src,closing(_db_connect(dest)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise ReliabilityError('Backup verification failed')
                src_counts=src.execute('SELECT state,COUNT(*) n FROM jobs GROUP BY state').fetchall()
                dst_counts=dst.execute('SELECT state,COUNT(*) n FROM jobs GROUP BY state').fetchall()
                if [(r['state'],r['n']) for r in src_counts]!=[(r['state'],r['n']) for r in dst_counts]:
                    raise ReliabilityError('Backup contents mismatch')
            with dest.open('rb') as f: digest=sha256(f.read()).hexdigest()
            return {'sha256':digest,'verified':True,'note':'Operational metadata only; not an encrypted wallet backup'}
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
