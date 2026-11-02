"""Durable, non-secret transaction intent storage for EVM / Monero.

Never stores mnemonic, private key, encrypted wallet passphrase, Monero relay
metadata or EVM signed raw transaction. Terminal records are retained for audit.
"""
from __future__ import annotations
from contextlib import closing
import json, os, re, secrets, sqlite3, time
from pathlib import Path
from core.transfer import TransferError

ACTIVE = ('PREPARING','PREPARED','BROADCASTING','UNKNOWN','PENDING','REORG_REVIEW','REQUIRES_REVIEW','UNSPENDABLE')
STATES = set(ACTIVE)|{'CONFIRMED','REVERTED','FAILED','CANCELLED','UNSPENDABLE'}
ALLOWED = {
 'PREPARING': {'PREPARED','UNKNOWN','CANCELLED','FAILED'},
 'PREPARED': {'BROADCASTING','CANCELLED','UNSPENDABLE'},
 'BROADCASTING': {'PENDING','UNKNOWN','CONFIRMED','REVERTED','REORG_REVIEW'},
 'UNKNOWN': {'UNKNOWN','PENDING','CONFIRMED','REVERTED','REORG_REVIEW','UNSPENDABLE','REQUIRES_REVIEW'},
 'PENDING': {'PENDING','CONFIRMED','REVERTED','UNKNOWN','REORG_REVIEW','REQUIRES_REVIEW'},
 'CONFIRMED': {'CONFIRMED','REORG_REVIEW'},
 'REORG_REVIEW': {'REORG_REVIEW','PENDING','CONFIRMED','REVERTED','UNKNOWN','REQUIRES_REVIEW'},
 'REQUIRES_REVIEW': {'REQUIRES_REVIEW'},
 'UNSPENDABLE': {'UNSPENDABLE','CANCELLED'},'REVERTED': {'REVERTED'},
 'FAILED': {'FAILED'},'CANCELLED': {'CANCELLED'}
}

def default_path():
    base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local') if os.name=='nt' else Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local'/'share')
    return base/'CRYPTO_NOCTURNE'/'chain_transactions.sqlite3'

class ChainJournal:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else default_path()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise TransferError('Transaction journal must be a regular non-symlink file.')
        with closing(self.connect()) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''CREATE TABLE IF NOT EXISTS intents(
              id TEXT PRIMARY KEY, chain TEXT NOT NULL, network TEXT NOT NULL,
              source TEXT NOT NULL, destination TEXT NOT NULL, asset TEXT NOT NULL,
              amount_units TEXT NOT NULL, nonce INTEGER, max_fee_units TEXT NOT NULL,
              tx_hash TEXT, block_hash TEXT, confirmations INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL, payload_json TEXT NOT NULL, updated INTEGER NOT NULL
              );
              CREATE INDEX IF NOT EXISTS idx_chain_source ON intents(chain,network,source,updated);''')
            c.commit()
        if os.name!='nt': os.chmod(self.path,0o600)

    def connect(self):
        c=sqlite3.connect(self.path,timeout=20)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA busy_timeout=20000')
        return c

    def new(self,*,chain,network,source,destination,asset,amount_units,max_fee_units,nonce=None,payload=None):
        if chain not in ('EVM','XMR') or not source or not destination:
            raise TransferError('Invalid chain or wallet source.')
        if not str(amount_units).isdigit() or int(amount_units)<=0:
            raise TransferError('Invalid transaction amount.')
        ident=secrets.token_hex(16)
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            q=','.join('?' for _ in ACTIVE)
            busy=c.execute(f'SELECT id FROM intents WHERE chain=? AND network=? AND source=? AND status IN ({q}) LIMIT 1',(chain,str(network),source,*ACTIVE)).fetchone()
            if busy:
                c.rollback();raise TransferError('Another unresolved send exists for this account. Reconcile or cancel safely first.')
            c.execute('''INSERT INTO intents(id,chain,network,source,destination,asset,amount_units,nonce,max_fee_units,status,payload_json,updated)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                     (ident,chain,str(network),source,destination,asset,str(amount_units),nonce,str(max_fee_units),'PREPARING',json.dumps(payload or {},sort_keys=True),int(time.time())))
            c.commit()
        return ident

    def get(self,ident):
        if not re.fullmatch(r'[0-9a-f]{32}',str(ident)):
            raise TransferError('Invalid transaction request ID.')
        with closing(self.connect()) as c:
            row=c.execute('SELECT * FROM intents WHERE id=?',(ident,)).fetchone()
        if row is None:raise TransferError('Transaction request not found.')
        d=dict(row);d['payload']=json.loads(d.pop('payload_json'));return d

    def transition(self,ident,from_states,to_state,**fields):
        if to_state not in STATES or any(k not in {'tx_hash','block_hash','confirmations','nonce','payload_json'} for k in fields):
            raise TransferError('Invalid journal transition.')
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT status FROM intents WHERE id=?',(ident,)).fetchone()
            if row is None or row['status'] not in from_states or to_state not in ALLOWED.get(row['status'],set()):
                c.rollback();raise TransferError('Transaction state changed; refresh before continuing.')
            fields={'status':to_state,'updated':int(time.time()),**fields}
            values=list(fields.values())+[ident]
            c.execute('UPDATE intents SET '+','.join(f'{k}=?' for k in fields)+' WHERE id=?',values)
            c.commit()
        return self.get(ident)

    def list(self,chain=None,limit=30):
        with closing(self.connect()) as c:
            rows=c.execute('SELECT id FROM intents WHERE (? IS NULL OR chain=?) ORDER BY updated DESC LIMIT ?',
                           (chain,chain,min(max(1,limit),100))).fetchall()
        return [self.get(r['id']) for r in rows]
