"""BTC Phase 1: explicit Bitcoin Core networks and crash-recoverable transaction journal.

Regtest is the default development network. Mainnet is never selected implicitly.
Signer: the local Core wallet. This code never uses a VaultForge mnemonic.
No unattended signing, rebroadcast, wallet unlock, or fund transfer.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Callable

from core.transfer import BitcoinRPC, TransferError, amount_decimal, float_exact, safe_loopback_url, verify_bitcoin_outputs, bitcoin_outputs

NETWORKS = {'regtest':18443, 'main':8332}
TXID_RE = re.compile(r'[a-fA-F0-9]{64}\Z')
WALLET_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,47}\Z')
SAT = Decimal('0.00000001')
ACTIVE = ('PREPARED', 'SIGNED', 'BROADCASTING', 'UNKNOWN')
STATUSES = ('PREPARED','SIGNED','BROADCASTING','UNKNOWN','PENDING','CONFIRMED','CONFLICTED','REPLACED','CANCELLED','REJECTED')


def state_path() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'AppData'/'Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or (Path.home()/'.local'/'share'))
    return base/'CRYPTO_NOCTURNE'/'btc_phase1.sqlite3'


def _sat(value) -> int:
    d = Decimal(str(value))
    n = d / SAT
    if not d.is_finite() or n != n.to_integral_value():
        raise TransferError('Bitcoin amount must be an exact multiple of one satoshi.')
    return int(n)


def _fee(value: str) -> Decimal:
    return amount_decimal(value, 8, 'maximum fee')


class BitcoinJournal:
    """Wallet transaction metadata and signed raw transaction only (no private keys).

    The database is stored outside application/installer source directories.
    All transactions use SQLite commits; connection handles close on Windows.
    """
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else state_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise TransferError('Refusing symlinked BTC transaction journal.')
        if self.path.exists() and not self.path.is_file():
            raise TransferError('BTC transaction journal must be a regular file.')
        self._init_db()
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

    def connect(self):
        c = sqlite3.connect(str(self.path), timeout=15)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA busy_timeout=15000')
        return c

    def _init_db(self):
        with closing(self.connect()) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=FULL')
            c.executescript('''
              CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY, network TEXT NOT NULL, wallet TEXT NOT NULL,
                recipient TEXT NOT NULL, amount_sats INTEGER NOT NULL,
                fee_sats INTEGER NOT NULL, psbt TEXT NOT NULL,
                approved_outputs TEXT NOT NULL, signed_raw TEXT,
                txid TEXT, status TEXT NOT NULL, confirmations INTEGER NOT NULL DEFAULT 0,
                created INTEGER NOT NULL, updated INTEGER NOT NULL,
                error_code TEXT NOT NULL DEFAULT ''
              );
              CREATE UNIQUE INDEX IF NOT EXISTS unique_txid ON intents(network,txid) WHERE txid IS NOT NULL;
              CREATE INDEX IF NOT EXISTS by_wallet ON intents(network,wallet,created);
            ''')
            c.commit()

    def insert(self, network, wallet, recipient, amount, fee, psbt, outputs) -> str:
        ident = secrets.token_hex(16)
        stamp = int(time.time())
        # No two in-flight prepared transactions in the same Core wallet: avoid input collision.
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            busy = c.execute('SELECT id FROM intents WHERE network=? AND wallet=? AND status IN (?,?,?,?) LIMIT 1',
                             (network,wallet,*ACTIVE)).fetchone()
            if busy:
                c.rollback()
                raise TransferError('Another send is awaiting completion/review for this wallet. Resolve it first.')
            c.execute('INSERT INTO intents(id,network,wallet,recipient,amount_sats,fee_sats,psbt,approved_outputs,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (ident,network,wallet,recipient,amount,fee,psbt,json.dumps(outputs), 'PREPARED',stamp,stamp))
            c.commit()
        return ident

    def get(self, ident: str) -> dict:
        with closing(self.connect()) as c:
            r=c.execute('SELECT * FROM intents WHERE id=?',(ident,)).fetchone()
        if r is None:
            raise TransferError('Unknown BTC transaction request.')
        result=dict(r)
        result['approved_outputs'] = json.loads(result['approved_outputs'])
        return result

    def update(self, ident: str, expected: tuple[str,...], status: str, **fields):
        if status not in STATUSES:
            raise TransferError('Invalid BTC transaction state.')
        allowed={'signed_raw','txid','confirmations','error_code'}
        if set(fields)-allowed:
            raise TransferError('Unknown journal field.')
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT status FROM intents WHERE id=?',(ident,)).fetchone()
            if not old or old['status'] not in expected:
                c.rollback()
                raise TransferError('BTC transaction state changed. Refresh transaction status before continuing.')
            changes={'status':status,'updated':int(time.time()),**fields}
            sets=','.join(f'{k}=?' for k in changes)
            c.execute(f'UPDATE intents SET {sets} WHERE id=?',(*changes.values(),ident))
            c.commit()

    def list(self, network=None, wallet=None, limit=25) -> list[dict]:
        sql='SELECT id,network,wallet,recipient,amount_sats,fee_sats,txid,status,confirmations,updated,error_code FROM intents WHERE 1=1'
        params=[]
        if network:
            sql+=' AND network=?';params.append(network)
        if wallet:
            sql+=' AND wallet=?';params.append(wallet)
        sql+=' ORDER BY updated DESC LIMIT ?';params.append(min(max(1,limit),100))
        with closing(self.connect()) as c:
            return [dict(r) for r in c.execute(sql,params).fetchall()]


def _output_pairs(tx: dict) -> list[list[str]]:
    return [[a,str(v)] for a,v in bitcoin_outputs(tx)]


def _reserved_inputs(tx: dict) -> list[dict]:
    return [{'txid':v['txid'],'vout':v['vout']} for v in tx.get('vin',[]) if isinstance(v,dict) and 'txid' in v and 'vout' in v]


@dataclass(frozen=True)
class NodeConfig:
    url: str
    cookie: str
    network: str = 'regtest'

    def validate(self):
        if self.network not in NETWORKS:
            raise TransferError('BTC network must be explicitly selected: regtest or mainnet.')
        clean=safe_loopback_url(self.url)
        # Default port is recommended, but custom local RPC ports are allowed.
        if not self.cookie.strip():
            raise TransferError('Bitcoin Core .cookie path required.')
        return clean


class BitcoinPhaseOne:
    def __init__(self, config: NodeConfig, journal: BitcoinJournal | None = None,
                 rpc_factory: Callable = BitcoinRPC):
        self.cfg=config
        self.url=config.validate()
        self.journal=journal if journal is not None else BitcoinJournal()
        self.rpc_factory=rpc_factory

    def rpc(self, wallet=None):
        return self.rpc_factory(self.url,Path(self.cfg.cookie),wallet)

    def health(self) -> dict:
        d=self.rpc().call('getblockchaininfo')
        if not isinstance(d,dict) or d.get('chain') != self.cfg.network:
            raise TransferError('Connected Bitcoin network does not match selected '+self.cfg.network+'.')
        if d.get('initialblockdownload'):
            raise TransferError('Bitcoin Core still syncing; no wallet transactions permitted.')
        blocks,headers=d.get('blocks'),d.get('headers')
        if not isinstance(blocks,int) or blocks < 0:
            raise TransferError('Node height is unavailable.')
        if isinstance(headers,int) and headers-blocks>1:
            raise TransferError('Node has not reached chain tip; no sends allowed.')
        return {'network':self.cfg.network,'blocks':blocks,'headers':headers,
                'verificationprogress':str(d.get('verificationprogress','unavailable'))}

    def wallet_rpc(self, wallet, *, spending=False):
        self.health()
        if not WALLET_RE.fullmatch(wallet or ''):
            raise TransferError('Choose a valid Bitcoin Core wallet name.')
        if wallet not in self.rpc().call('listwallets'):
            raise TransferError('Bitcoin Core wallet is not loaded.')
        rpc=self.rpc(wallet)
        info=rpc.call('getwalletinfo')
        if not isinstance(info,dict) or info.get('scanning'):
            raise TransferError('Bitcoin Core wallet is unavailable or rescanning.')
        if spending and (not info.get('private_keys_enabled') or info.get('external_signer')):
            raise TransferError('Use a compatible signer; this phase only handles Core software keys.')
        return rpc

    def create_encrypted_wallet(self, wallet: str, passphrase: str) -> dict:
        self.health()
        if not WALLET_RE.fullmatch(wallet or ''):
            raise TransferError('New Core wallet name must be 1–48 valid characters.')
        if not isinstance(passphrase,str) or not 14 <= len(passphrase) <= 512:
            raise TransferError('Core wallet passphrase must be 14–512 characters.')
        rpc=self.rpc()
        # Check both loaded wallets and Core's wallet directory to prevent colliding names.
        directories=rpc.call('listwalletdir').get('wallets',[])
        if wallet in rpc.call('listwallets') or wallet in [r.get('name') for r in directories]:
            raise TransferError('A Core wallet already uses this name.')
        created=rpc.call('createwallet',wallet,False,False,passphrase,False,True,False)
        if not isinstance(created,dict) or created.get('name')!=wallet:
            raise TransferError('Bitcoin Core did not confirm wallet creation.')
        info=self.rpc(wallet).call('getwalletinfo')
        if not info.get('private_keys_enabled') or not info.get('descriptors'):
            raise TransferError('Created wallet is not a spendable descriptor wallet. Do not fund it.')
        return {'wallet':wallet,'network':self.cfg.network,'backup_required':True,
                'message':'Back up and independently restore the Core wallet before depositing real BTC.'}

    def receiving_address(self, wallet: str) -> str:
        rpc=self.wallet_rpc(wallet)
        address=rpc.call('getnewaddress','NOCTURNE Receive','bech32')
        info=rpc.call('getaddressinfo',address)
        if not info.get('ismine') or info.get('iswatchonly',False):
            raise TransferError('Core did not verify ownership of new receiving address.')
        return address

    def balance(self, wallet) -> dict:
        rpc=self.wallet_rpc(wallet)
        b=rpc.call('getbalances').get('mine',{})
        return {k:str(b.get(k,'unavailable')) for k in ('trusted','untrusted_pending','immature')}

    def prepare(self, wallet: str, recipient: str, amount_btc: str, max_fee_btc: str) -> dict:
        rpc=self.wallet_rpc(wallet,spending=True)
        if not isinstance(recipient,str) or not rpc.call('validateaddress',recipient).get('isvalid'):
            raise TransferError('Invalid Bitcoin receiving address for the selected network.')
        amount=amount_decimal(amount_btc,8,'BTC amount')
        cap=_fee(max_fee_btc)
        trusted=Decimal(str(rpc.call('getbalances').get('mine',{}).get('trusted','0')))
        if trusted < amount+SAT:
            raise TransferError('Insufficient trusted wallet balance.')
        # Only one pending Core spend per wallet; SQLite records are the arbiter.
        if any(row['status'] in ACTIVE for row in self.journal.list(self.cfg.network,wallet,100)):
            raise TransferError('Resolve previous prepared/unknown transaction for this wallet first.')
        funded=rpc.call('walletcreatefundedpsbt',[],[{recipient:float_exact(amount)}],0,
                        {'replaceable':True,'lockUnspents':True,'estimate_mode':'conservative'})
        psbt=funded['psbt']
        decoded=rpc.call('decodepsbt',psbt)
        reserved=_reserved_inputs(decoded['tx'])
        try:
            fee=Decimal(str(funded['fee']))
            if fee<=0 or fee>cap or amount+fee>trusted:
                raise TransferError('Fee is invalid, over cap, or exceeds spendable funds.')
            verified=verify_bitcoin_outputs(rpc,decoded['tx'],recipient,amount)
            out=_output_pairs(decoded['tx'])
            ident=self.journal.insert(self.cfg.network,wallet,recipient,_sat(amount),_sat(fee),psbt,out)
            return {'id':ident,'wallet':wallet,'recipient':recipient,'amount':str(amount),
                    'fee':str(fee),'total_debit':str(amount+fee),'outputs':out,
                    'network':self.cfg.network}
        except Exception:
            # On failed preparation, release UTXOs locked by fundedpsbt.
            if reserved:
                try: rpc.call('lockunspent',True,reserved)
                except Exception: pass
            raise

    def cancel(self, ident: str):
        row=self.journal.get(ident)
        if row['network']!=self.cfg.network or row['status']!='PREPARED':
            raise TransferError('Only unapproved BTC transactions can be cancelled.')
        rpc=self.wallet_rpc(row['wallet'])
        psbt=rpc.call('decodepsbt',row['psbt'])
        reserved=_reserved_inputs(psbt['tx'])
        if reserved:
            rpc.call('lockunspent',True,reserved)
        self.journal.update(ident,('PREPARED',),'CANCELLED')

    def sign_and_broadcast(self, ident: str, challenge: str, wallet_passphrase: str = '') -> dict:
        row=self.journal.get(ident)
        if row['network'] != self.cfg.network or row['status']!='PREPARED':
            raise TransferError('Transaction is not pending authorization.')
        amount=Decimal(row['amount_sats'])*SAT
        expected=f'SEND {amount:.8f} BTC {row["recipient"][-8:]}'
        if challenge!=expected:
            raise TransferError('Authorization did not match complete payment details.')
        rpc=self.wallet_rpc(row['wallet'],spending=True)
        unlocked=False
        try:
            if wallet_passphrase:
                rpc.call('walletpassphrase',wallet_passphrase,30)
                unlocked=True
            signed=rpc.call('walletprocesspsbt',row['psbt'])
            final=rpc.call('finalizepsbt',signed['psbt'])
            if not final.get('complete') or not final.get('hex'):
                raise TransferError('Bitcoin Core did not completely sign the transaction.')
            raw=final['hex']
            decoded=rpc.call('decoderawtransaction',raw)
            if _output_pairs(decoded) != row['approved_outputs']:
                raise TransferError('Final signed outputs differ from approved preview.')
            verify_bitcoin_outputs(rpc,decoded,row['recipient'],amount)
            txid=decoded.get('txid')
            if not isinstance(txid,str) or not TXID_RE.fullmatch(txid):
                raise TransferError('Core did not return a valid signed transaction ID.')
            mempool=rpc.call('testmempoolaccept',[raw])
            if not isinstance(mempool,list) or not mempool or not mempool[0].get('allowed'):
                raise TransferError('Signed transaction not accepted by node mempool rules.')
            # Signed transaction is durable BEFORE network submit.
            self.journal.update(ident,('PREPARED',),'SIGNED',signed_raw=raw,txid=txid)
            self.journal.update(ident,('SIGNED',),'BROADCASTING')
            try:
                returned=rpc.call('sendrawtransaction',raw)
            except Exception:
                self.journal.update(ident,('BROADCASTING',),'UNKNOWN',error_code='RPC_BROADCAST_AMBIGUOUS')
                return {'id':ident,'txid':txid,'status':'UNKNOWN',
                        'message':'Broadcast result unknown. Reconcile before doing anything else. Do not send again.'}
            if returned != txid:
                self.journal.update(ident,('BROADCASTING',),'UNKNOWN',error_code='RPC_TXID_MISMATCH')
                raise TransferError('Node returned unexpected TXID; transaction requires manual review.')
            self.journal.update(ident,('BROADCASTING',),'PENDING')
            return {'id':ident,'txid':txid,'status':'PENDING'}
        finally:
            if unlocked:
                try: rpc.call('walletlock')
                except Exception: pass

    def reconcile(self, ident: str) -> dict:
        row=self.journal.get(ident)
        if row['network']!=self.cfg.network or not row.get('txid'):
            raise TransferError('No submitted BTC transaction is associated with this request.')
        rpc=self.wallet_rpc(row['wallet'])
        try:
            result=rpc.call('gettransaction',row['txid'])
        except Exception:
            # RPC may be down or Core may not recognize the tx. Never mark dropped/failed.
            if row['status'] in ('BROADCASTING','SIGNED'):
                self.journal.update(ident,(row['status'],),'UNKNOWN',error_code='TX_UNVERIFIED')
            return {'id':ident,'txid':row['txid'],'status':'UNKNOWN',
                    'message':'Transaction not verified. Check Core and mempool; never automatically retry.'}
        if result.get('replaced_by_txid'):
            status='REPLACED'
        elif result.get('walletconflicts') or int(result.get('confirmations',0))<0:
            status='CONFLICTED'
        elif int(result.get('confirmations',0))>=1:
            status='CONFIRMED'
        else:
            status='PENDING'
        current=row['status']
        if current not in ('PENDING','UNKNOWN','BROADCASTING','SIGNED','CONFIRMED','REPLACED','CONFLICTED'):
            raise TransferError('Cannot reconcile a transaction that was not submitted.')
        self.journal.update(ident,(current,),status,confirmations=int(result.get('confirmations',0)))
        return {'id':ident,'txid':row['txid'],'status':status,
                'confirmations':int(result.get('confirmations',0)),
                'replaced_by_txid':result.get('replaced_by_txid')}

    def restore_test(self, wallet: str, backup_file: str) -> dict:
        """Regtest only: restore into separate Core wallet and check a known address.

        A real mainnet restore must be independently tested on an offline/fresh environment.
        Does not delete or overwrite any Core wallet files.
        """
        if self.cfg.network!='regtest':
            raise TransferError('Automated restore test allowed only on regtest. Test mainnet backups independently.')
        source=self.wallet_rpc(wallet)
        addresses=source.call('listreceivedbyaddress',0,True)
        known=[row['address'] for row in addresses if isinstance(row,dict) and row.get('address')]
        if not known:
            raise TransferError('Generate a receiving address before creating/testing this backup.')
        name='nocturne_restore_'+secrets.token_hex(5)
        root=self.rpc()
        if name in root.call('listwallets'):
            raise TransferError('Restore-test wallet collision.')
        result=root.call('restorewallet',name,str(Path(backup_file).resolve()),False)
        if not isinstance(result,dict) or result.get('name')!=name:
            raise TransferError('Core did not confirm wallet restoration.')
        verified=False
        try:
            other=self.rpc(name)
            verified=all(bool(other.call('getaddressinfo',addr).get('ismine')) for addr in known)
        finally:
            root.call('unloadwallet',name,False)
        if not verified:
            raise TransferError('Restored wallet did not recognize the original receiving addresses.')
        return {'restored_wallet_name':name,'addresses_verified':len(known),
                'note':'Restored Core wallet remains in Core data directory (unloaded). No wallet files were deleted.'}
