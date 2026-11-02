"""Universal transaction *monitoring* and transfer-policy foundation, NOCTURNE v3.4.

The existing BitcoinJournal and ChainJournal remain authoritative for signing,
nonce/UTXO reservations and broadcasts. This module ONLY reads their public
transaction metadata and builds an append-only, hash-chained local projection.
It has no broadcast, sign, unlock, RPC, or fund-movement API.

Never store PSBTs, raw transactions, Monero relay metadata, wallet paths,
passwords, key material or arbitrary backend payloads here.
"""
from __future__ import annotations
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import time

class ProjectionError(ValueError):
    pass

UNITS = {'BTC': 8, 'XMR': 12}
SUPPORTED = {'BTC', 'EVM', 'XMR'}
# Never promote a backend "unknown" into confirmed without a backend-reported
# receipt/confirmation. Already-confirmed transactions can lose confirmation.
STATES = frozenset({'PREPARING','PREPARED','SIGNED','BROADCASTING','UNKNOWN',
    'PENDING','CONFIRMED','REORG_REVIEW','REQUIRES_REVIEW','CONFLICTED',
    'REPLACED','REVERTED','FAILED','CANCELLED','REJECTED','UNSPENDABLE'})
STOPPED = frozenset({'REVERTED','FAILED','CANCELLED','REJECTED','UNSPENDABLE'})
NEEDS_REVIEW = frozenset({'BROADCASTING','UNKNOWN','REORG_REVIEW','REQUIRES_REVIEW','CONFLICTED','REPLACED','UNSPENDABLE'})
MAX_FIELD = 512


def data_dir() -> Path:
    if os.name == 'nt':
        base=Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'AppData'/'Local'))
    else:
        base=Path(os.environ.get('XDG_DATA_HOME') or (Path.home()/'.local'/'share'))
    return base/'CRYPTO_NOCTURNE'


def _text(value, name, *, empty=False, length=MAX_FIELD):
    if not isinstance(value,str) or len(value) > length or (not empty and not value.strip()):
        raise ProjectionError('Invalid '+name)
    if any(ord(ch)<32 for ch in value):
        raise ProjectionError('Invalid '+name)
    return value.strip()


def _positive_int_string(value, name, *, allow_zero=False):
    if isinstance(value,bool): raise ProjectionError('Invalid '+name)
    raw=str(value)
    if not re.fullmatch(r'(?:0|[1-9][0-9]{0,90})',raw):
        raise ProjectionError('Invalid '+name)
    if not allow_zero and int(raw)==0: raise ProjectionError('Invalid '+name)
    return raw


def exact_units(amount, decimals: int) -> str:
    """Exact decimal conversion: floats rejected; no rounding money."""
    if not isinstance(decimals,int) or isinstance(decimals,bool) or not 0<=decimals<=36:
        raise ProjectionError('Invalid asset decimal precision')
    if isinstance(amount,float) or isinstance(amount,bool):
        raise ProjectionError('Financial amounts must be text or Decimal, not floats')
    if not isinstance(amount,(str,Decimal,int)):
        raise ProjectionError('Invalid amount type')
    try:
        val=Decimal(str(amount))
        if not val.is_finite() or val<=0:raise ProjectionError('Amount must be positive and finite')
        result=val*Decimal(10)**decimals
        if result!=result.to_integral_value():
            raise ProjectionError('Amount has more decimal places than the network supports')
        return _positive_int_string(str(int(result)),'amount')
    except (InvalidOperation,OverflowError,ValueError) as exc:
        if isinstance(exc,ProjectionError):raise
        raise ProjectionError('Invalid precise amount') from None


def display_units(amount_units, decimals:int) -> str:
    v=_positive_int_string(amount_units,'amount units',allow_zero=True)
    if not 0<=decimals<=36:raise ProjectionError('Invalid precision')
    return format(Decimal(v)/(Decimal(10)**decimals),'f')

@dataclass(frozen=True)
class TxSnapshot:
    chain: str
    network: str
    backend_id: str
    source: str
    destination: str
    asset: str
    amount_units: str
    decimals: int
    max_fee_units: str
    status: str
    tx_hash: str = ''
    confirmations: int = 0

    def validate(self):
        if self.chain not in SUPPORTED:raise ProjectionError('Unsupported signer chain')
        for field in ('network','backend_id','source','destination','asset'):
            _text(getattr(self,field),field)
        if self.status not in STATES:raise ProjectionError('Unknown backend transaction status')
        _positive_int_string(self.amount_units,'amount units')
        _positive_int_string(self.max_fee_units,'max fee',allow_zero=True)
        if not isinstance(self.decimals,int) or isinstance(self.decimals,bool) or not 0<=self.decimals<=36:
            raise ProjectionError('Invalid decimals')
        if not isinstance(self.confirmations,int) or isinstance(self.confirmations,bool) or not 0<=self.confirmations<=10_000_000:
            raise ProjectionError('Invalid confirmations')
        if self.tx_hash:_text(self.tx_hash,'transaction hash',length=128)
        if self.status=='CONFIRMED' and (not self.tx_hash or self.confirmations<1):
            raise ProjectionError('Cannot display a transaction confirmed without a hash and confirmations')
        if self.chain=='BTC' and self.decimals!=8:raise ProjectionError('BTC must use satoshis')
        if self.chain=='XMR' and self.decimals!=12:raise ProjectionError('Monero must use atomic units')
        return self

    def as_public(self):
        self.validate()
        return {k:getattr(self,k) for k in self.__dataclass_fields__}


def snapshot_btc(row):
    """Adapt BitcoinJournal.list(); never import stored PSBTs/signed raw bytes."""
    return TxSnapshot(chain='BTC',network=_text(row['network'],'network'),
        backend_id=_text(row['id'],'backend ID'),source=_text(row['wallet'],'Core wallet'),
        destination=_text(row['recipient'],'recipient'),asset='BTC',
        amount_units=_positive_int_string(row['amount_sats'],'sats'),decimals=8,
        max_fee_units=_positive_int_string(row['fee_sats'],'fee sats',allow_zero=True),
        status=str(row['status']),tx_hash=str(row.get('txid') or ''),
        confirmations=int(row.get('confirmations') or 0)).validate()


def snapshot_chain(row):
    chain=row['chain']
    if chain not in ('EVM','XMR'):raise ProjectionError('Only existing EVM/XMR signer journals accepted')
    # Token decimals are captured in the trusted legacy journal payload.
    # Never include the payload (may include other transaction metadata).
    decimals=12 if chain=='XMR' else int(row.get('payload',{}).get('decimals',18))
    return TxSnapshot(chain=chain,network=str(row['network']),
        backend_id=_text(row['id'],'backend ID'),source=_text(row['source'],'source'),
        destination=_text(row['destination'],'destination'),asset=_text(row['asset'],'asset'),
        amount_units=_positive_int_string(row['amount_units'],'amount units'),decimals=decimals,
        max_fee_units=_positive_int_string(row['max_fee_units'],'max fee',allow_zero=True),
        status=str(row['status']),tx_hash=str(row.get('tx_hash') or ''),
        confirmations=int(row.get('confirmations') or 0)).validate()


class UniversalTxJournal:
    """Sanitized durable read-only dashboard projection with a tamper-evident local event chain.

    Hash chaining detects accidental/offline modifications when checked against a
    trusted external head, but is not a digital signature or an immutable audit.
    """
    def __init__(self,path:Path|str|None=None):
        self.path=Path(path) if path is not None else data_dir()/'universal_transactions.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ProjectionError('Transaction projection must be a regular file')
        with closing(self._db()) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
              CREATE TABLE IF NOT EXISTS snapshots (
                chain TEXT NOT NULL, network TEXT NOT NULL, backend_id TEXT NOT NULL,
                data TEXT NOT NULL, updated INTEGER NOT NULL,
                PRIMARY KEY(chain,network,backend_id)
              );
              CREATE TABLE IF NOT EXISTS events (
                serial INTEGER PRIMARY KEY AUTOINCREMENT, chain TEXT NOT NULL,
                network TEXT NOT NULL, backend_id TEXT NOT NULL,
                payload TEXT NOT NULL, recorded INTEGER NOT NULL,
                previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL
              );
              CREATE INDEX IF NOT EXISTS event_source ON events(chain,network,backend_id,serial);
            ''')
            db.commit()
        if os.name!='nt':os.chmod(self.path,0o600)

    def _db(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        return db

    @staticmethod
    def _serialize(snapshot):
        return json.dumps(snapshot.as_public(),sort_keys=True,separators=(',',':'))

    def ingest(self,snapshot:TxSnapshot):
        """Idempotently mirror a verified *backend-reported* status, not an app guess."""
        payload=self._serialize(snapshot)
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            key=(snapshot.chain,snapshot.network,snapshot.backend_id)
            old=db.execute('SELECT data FROM snapshots WHERE chain=? AND network=? AND backend_id=?',key).fetchone()
            if old:
                prior=json.loads(old['data'])
                immutable=('chain','network','backend_id','source','destination','asset','amount_units','decimals','max_fee_units')
                if any(prior[field]!=getattr(snapshot,field) for field in immutable):
                    db.rollback();raise ProjectionError('Backend identity or approved payment details changed; manual investigation required')
                if prior['tx_hash'] and snapshot.tx_hash and prior['tx_hash'].lower()!=snapshot.tx_hash.lower():
                    db.rollback();raise ProjectionError('Changed transaction hash requires explicit replacement review')
                if old['data']==payload:
                    db.commit();return False
                if prior['status'] in STOPPED and snapshot.status not in (prior['status'],'REQUIRES_REVIEW'):
                    db.rollback();raise ProjectionError('Terminal transaction state changed; manual reconciliation required')
            stamp=int(time.time())
            prev=db.execute('SELECT event_hash FROM events ORDER BY serial DESC LIMIT 1').fetchone()
            prevhash=prev['event_hash'] if prev else '0'*64
            body={'chain':snapshot.chain,'network':snapshot.network,'backend_id':snapshot.backend_id,
                  'payload':payload,'recorded':stamp,'previous_hash':prevhash}
            digest=sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
            db.execute('INSERT INTO events(chain,network,backend_id,payload,recorded,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?)',
                       (*key,payload,stamp,prevhash,digest))
            db.execute('INSERT INTO snapshots(chain,network,backend_id,data,updated) VALUES(?,?,?,?,?) '
                       'ON CONFLICT(chain,network,backend_id) DO UPDATE SET data=excluded.data, updated=excluded.updated',
                       (*key,payload,stamp))
            db.commit()
        return True

    def list(self,chain=None,limit=150):
        if chain is not None and chain not in SUPPORTED:raise ProjectionError('Unsupported transaction filter')
        with closing(self._db()) as db:
            rows=db.execute('SELECT data,updated FROM snapshots WHERE (? IS NULL OR chain=?) ORDER BY updated DESC,chain,backend_id LIMIT ?',
                            (chain,chain,min(max(int(limit),1),1000))).fetchall()
        return [{**json.loads(x['data']),'updated':x['updated']} for x in rows]

    def summary(self):
        rows=self.list(limit=1000)
        return {'total':len(rows),'pending':sum(r['status']=='PENDING' for r in rows),
                'confirmed':sum(r['status']=='CONFIRMED' for r in rows),
                'review':sum(r['status'] in NEEDS_REVIEW for r in rows),
                'other':sum(r['status'] not in NEEDS_REVIEW|{'PENDING','CONFIRMED'} for r in rows)}

    def verify_events(self):
        with closing(self._db()) as db:
            rows=db.execute('SELECT * FROM events ORDER BY serial').fetchall()
            snapshots=db.execute('SELECT chain,network,backend_id,data FROM snapshots').fetchall()
        prev='0'*64;last={}
        for row in rows:
            body={key:row[key] for key in ('chain','network','backend_id','payload','recorded','previous_hash')}
            hash_value=sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if body['previous_hash']!=prev or hash_value!=row['event_hash']:
                raise ProjectionError('Local transaction history checksum mismatch; inspect database and backups')
            prev=hash_value
            last[(row['chain'],row['network'],row['backend_id'])]=row['payload']
        for row in snapshots:
            key=(row['chain'],row['network'],row['backend_id'])
            if last.get(key)!=row['data']:
                raise ProjectionError('Transaction projection differs from its recorded history')
        if len(snapshots)!=len(last):
            raise ProjectionError('Missing transaction projection rows')
        return {'events':len(rows),'records':len(last),'head':prev,
                'warning':'Local hashes are not independent proof: a local attacker can rewrite the full chain.'}


def sync_existing(*,projection=None,btc=None,chains=None,limit=150):
    """Read only existing BTC and EVM/XMR journals. No RPC or signing."""
    if projection is None: projection=UniversalTxJournal()
    if btc is None:
        from btc_phase1 import BitcoinJournal
        btc=BitcoinJournal()
    if chains is None:
        from chain_journal import ChainJournal
        chains=ChainJournal()
    projection.verify_events()
    imported=0;errors=[]
    for kind,journal,converter in (('BTC',btc,snapshot_btc),('EVM/XMR',chains,snapshot_chain)):
        try:
            for r in journal.list(limit=limit):
                try:
                    if projection.ingest(converter(r)):imported+=1
                except (ProjectionError,ValueError,KeyError,TypeError) as exc:
                    errors.append(f'{kind}: invalid or changed transaction record; review required ({type(exc).__name__})')
        except (OSError,sqlite3.Error,ValueError) as exc:
            errors.append(f'{kind}: transaction journal unavailable ({type(exc).__name__})')
    return {'imported':imported,'rows':projection.list(),'summary':projection.summary(),
            'integrity':projection.verify_events(),'errors':errors}
