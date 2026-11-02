"""Durable, non-custodial Phase-4 payment request journal.

Orders track REQUESTS and provider handoffs, not money or verified balances.
No status here is a substitute for provider-confirmed settlement plus an
independent blockchain transaction confirmation. No card details are retained.
"""
from __future__ import annotations
from decimal import Decimal
import sqlite3
import hashlib
from contextlib import contextmanager, closing
import time
import uuid
from pathlib import Path
from wallet_funding import validate_payment, FundingTarget
from asset_capabilities import get_capability, CAPABILITIES

class OrderError(ValueError): pass

STATES={'REQUESTED','PROVIDER_OPENED','AWAITING_PROVIDER','NEEDS_REVIEW','CANCELLED'}

class FundingOrders:
    def __init__(self, db: Path):
        self.db=Path(db)
        self.db.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with self._connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS funding_request (
                 id TEXT PRIMARY KEY, idempotency TEXT UNIQUE NOT NULL,
                 flow TEXT NOT NULL, provider TEXT NOT NULL, asset TEXT NOT NULL,
                 chain TEXT NOT NULL, address TEXT NOT NULL, fiat TEXT NOT NULL,
                 amount TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL,
                 last_update INTEGER NOT NULL)''')
            c.execute('''CREATE INDEX IF NOT EXISTS idx_funding_created ON funding_request(created_at DESC)''')
    @contextmanager
    def _connect(self):
        with closing(sqlite3.connect(self.db,timeout=15)) as c:
            c.row_factory=sqlite3.Row
            with c:
                yield c
    def create(self, *, flow:str,provider:str,target:FundingTarget,fiat:str,amount:str,idempotency:str):
        if flow not in ('BUY','SELL') or provider!='MoonPay — official website':
            raise OrderError('Only documented provider handoffs are supported')
        if flow=='SELL':
            raise OrderError('Cash-out requires an approved off-ramp integration and verified receiving fiat account; no sell order will be claimed')
        if not isinstance(idempotency,str) or not (8 <= len(idempotency) <= 128) or not idempotency.isascii():
            raise OrderError('Invalid request identity')
        amount=validate_payment(str(amount),fiat)
        if target.asset not in CAPABILITIES:
            raise OrderError('Unknown asset')
        cap=get_capability(target.asset)
        accepted_networks={cap.network}
        if target.asset=='BTC':accepted_networks.update(('Bitcoin mainnet','Bitcoin'))
        if target.asset=='XMR':accepted_networks.add('Monero mainnet')
        if target.asset=='ETH':accepted_networks.update(('Ethereum','Ethereum mainnet'))
        if target.network not in accepted_networks:
            # Legacy vault rows use alternative network labels; this is deliberately
            # strict to avoid quietly placing real purchases on a wrong chain.
            raise OrderError('Wallet network does not match asset catalog')
        if not target.address or not target.network:
            raise OrderError('Missing receiving address')
        # Validates selected address format, without falsely proving ownership.
        from backend import verify_public_address
        from core.assets import ASSETS
        underlying=ASSETS[target.asset].base_coin
        if not verify_public_address(underlying,target.address):
            raise OrderError('Invalid destination address format')
        now=int(time.time())
        # Data minimization: never persist full wallet address in funding journal.
        # Address ownership is NOT proven by a hash; actual payments are external.
        address_fingerprint='sha256:'+hashlib.sha256(target.address.encode('utf-8')).hexdigest()+':'+target.address[-8:]
        record=(str(uuid.uuid4()),idempotency,flow,provider,target.asset,target.network,
                address_fingerprint,fiat,str(amount),'REQUESTED',now,now)
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            found=c.execute('SELECT * FROM funding_request WHERE idempotency=?',(idempotency,)).fetchone()
            if found:
                vals=(flow,provider,target.asset,target.network,address_fingerprint,fiat,str(amount))
                if tuple(found[k] for k in ('flow','provider','asset','chain','address','fiat','amount')) != vals:
                    raise OrderError('Idempotency key reused with different payment details')
                return dict(found)
            c.execute('''INSERT INTO funding_request
                (id,idempotency,flow,provider,asset,chain,address,fiat,amount,status,created_at,last_update)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',record)
            return dict(c.execute('SELECT * FROM funding_request WHERE id=?',(record[0],)).fetchone())
    def list(self,limit=30):
        with self._connect() as c:
            return [dict(x) for x in c.execute('SELECT * FROM funding_request ORDER BY created_at DESC,id DESC LIMIT ?', (min(int(limit),100),)).fetchall()]
    def state(self,id:str,status:str):
        # Local desktop can record a user handoff or cancellation only.
        # It CANNOT record succeeded, paid, settled, finalized, or credited.
        if status not in ('PROVIDER_OPENED','AWAITING_PROVIDER','NEEDS_REVIEW','CANCELLED'):
            raise OrderError('Payment status can only be verified by the authorized provider and blockchain')
        with self._connect() as c:
            row=c.execute('SELECT * FROM funding_request WHERE id=?',(id,)).fetchone()
            if not row:raise OrderError('Unknown request')
            if row['status']=='CANCELLED' and status!='CANCELLED':
                raise OrderError('Cannot reopen cancelled request')
            if status=='PROVIDER_OPENED' and row['status'] not in ('REQUESTED','PROVIDER_OPENED'):
                raise OrderError('Unexpected state transition')
            c.execute('UPDATE funding_request SET status=?,last_update=? WHERE id=?', (status,int(time.time()),id))
            return dict(c.execute('SELECT * FROM funding_request WHERE id=?',(id,)).fetchone())
