"""Public-only unified account registry, account verification and receiving controls.

Security boundaries:
- No mnemonic, private key, account password, RPC cookie or credential in registry.
- Storage of a public address does NOT demonstrate control, spendability, or recovery.
- Proof from a chain signer is session-bound and never persisted as 'verified'.
- Account identifiers are stable public-metadata hashes, not authorization tokens.
- No signing, fund movement, remote requests or implicit address creation in list().
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import secrets
from typing import Callable

from asset_capabilities import CAPABILITIES
from core.transfer import COIN_NETWORKS, TransferError, load_keystore_header

ACCOUNT_KINDS = ('vault', 'watch_only', 'btc_core', 'evm_keystore', 'xmr_rpc')
PERSIST_KINDS = ('watch_only', 'btc_core', 'evm_keystore', 'xmr_rpc')
BTC_NETWORKS = ('regtest', 'main')
XMR_NETWORKS = ('stagenet', 'mainnet')
EVM_NETWORKS = frozenset({*COIN_NETWORKS, 'SEPOLIA'})
ADDR_RE = re.compile(r'0x[0-9a-fA-F]{40}\Z')


def default_registry_path() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local'/'share')
    return base/'CRYPTO_NOCTURNE'/'unified_accounts.json'


def _id(kind: str, asset: str, network: str, source: str, address: str) -> str:
    return sha256(json.dumps([kind, asset, network, source, address],separators=(',',':')).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class Account:
    id: str
    kind: str
    asset: str
    network: str
    address: str
    source: str
    label: str
    status: str = 'UNVERIFIED'
    details: str = ''
    can_receive: bool = False
    can_spend: bool = False
    signer_proven: bool = False

    def public_record(self) -> dict:
        return {k:getattr(self,k) for k in ('kind','asset','network','address','source','label')}


def account_from_record(data: dict) -> Account:
    if not isinstance(data,dict): raise ValueError('Invalid account record')
    kind,asset,network,address,source,label=(data.get(k) for k in ('kind','asset','network','address','source','label'))
    if kind not in ACCOUNT_KINDS or asset not in CAPABILITIES:
        raise ValueError('Unsupported account or cryptocurrency')
    if not all(isinstance(x,str) and x and len(x)<=512 and not any(ord(c)<32 for c in x)
               for x in (network,address,source,label)):
        raise ValueError('Invalid public account metadata')
    if len(address)>160 or len(network)>75 or len(label)>100:
        raise ValueError('Account metadata is too long')
    if kind=='btc_core' and (asset!='BTC' or network not in BTC_NETWORKS):
        raise ValueError('Invalid Bitcoin Core network')
    if kind=='xmr_rpc' and (asset!='XMR' or network not in XMR_NETWORKS):
        raise ValueError('Invalid Monero RPC network')
    if kind=='evm_keystore' and (network not in EVM_NETWORKS or not ADDR_RE.fullmatch(address)
                                 or asset!=network and not (asset=='ETH' and network=='SEPOLIA')):
        raise ValueError('EVM account must match its explicit native asset/network')
    if kind=='vault' and not source.lower().endswith('.vault'):
        raise ValueError('Vault source must be a .vault')
    return Account(_id(kind,asset,network,source,address),kind,asset,network,address,source,label)


class UnifiedAccountRegistry:
    """Atomic public-only store; never serialize verification or spend flags."""
    def __init__(self,path: str | Path | None = None):
        self.path=Path(path) if path is not None else default_registry_path()

    def list(self) -> list[Account]:
        path=self.path
        if not path.exists():return []
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1_000_000:
            raise ValueError('Account registry is not a safe regular JSON file')
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema')!=1 or not isinstance(data.get('accounts'),list) or len(data['accounts'])>250:
            raise ValueError('Unknown or invalid account registry')
        items=[account_from_record(x) for x in data['accounts']]
        if any(x.kind not in PERSIST_KINDS for x in items):
            raise ValueError('Vault secret/session data may not be persisted')
        if len({x.id for x in items})!=len(items):raise ValueError('Duplicate account entries')
        return items

    def _write(self,items: list[Account]):
        if len(items)>250:raise ValueError('Account registry full')
        path=self.path
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('Refusing unsafe registry path')
        blob=json.dumps({'schema':1,'accounts':[a.public_record() for a in items]},
                        indent=2).encode('utf-8')
        temp=path.parent/('.accounts-'+secrets.token_hex(12))
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(blob);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path)
        finally:
            temp.unlink(missing_ok=True)
        if os.name!='nt':os.chmod(path,0o600)

    def add(self,account: Account):
        if account.kind not in PERSIST_KINDS:raise ValueError('Vaults are discovered when unlocked, not registered')
        # Re-validate before committing any externally supplied account object.
        acct=account_from_record(account.public_record())
        items=self.list()
        if acct.id not in {x.id for x in items}:
            self._write([*items,acct])
        return acct

    def remove(self,ident: str):
        items=self.list()
        if ident not in {x.id for x in items}:raise ValueError('Account not in registry')
        self._write([x for x in items if x.id!=ident])


def from_vault_rows(path: str, rows: list[dict]) -> list[Account]:
    """Only public entries supplied by the already-unlocked in-memory vault view."""
    result=[]
    for entry in rows:
        asset=entry.get('coin')
        if asset not in CAPABILITIES:continue
        try:
            account=account_from_record({'kind':'vault','asset':asset,'network':entry.get('network') or asset,
                   'address':entry['address'],'source':str(path),'label':Path(path).name})
        except (KeyError,ValueError):continue
        result.append(replace(account,status='ADDRESS ONLY / RECOVERY UNVERIFIED',
               details='Generated public address. Does not prove control of an external signer or independent recovery. '
                       'EVM vault signing is available only through the separate legacy send path, after password and source checks.'))
    return result


def from_watch_rows(rows: list[dict]) -> list[Account]:
    result=[]
    for entry in rows:
        if entry.get('coin') not in CAPABILITIES:continue
        try:
            acc=account_from_record({'kind':'watch_only','asset':entry['coin'],
                'network':entry.get('network') or entry['coin'], 'address':entry['address'],
                'source':'watch_only','label':entry.get('label') or 'Watch only'})
            result.append(replace(acc,status='WATCH ONLY / NO SIGNER',details='Cannot sign or spend.'))
        except (KeyError,ValueError):pass
    return result


def register_evm_keystore(path: str, network: str, *, label: str='EVM keystore') -> Account:
    """Read the public V3-keystore header only, never decrypt or import secrets."""
    if network not in EVM_NETWORKS:raise ValueError('Unsupported EVM chain')
    p=Path(path).expanduser()
    if p.is_symlink() or not p.is_file() or p.stat().st_size>1_000_000:
        raise ValueError('Select an existing regular encrypted keystore file under 1MB')
    _,addr=load_keystore_header(p)
    asset='ETH' if network=='SEPOLIA' else network
    return account_from_record({'kind':'evm_keystore','asset':asset,'network':network,
          'address':'0x'+str(addr).removeprefix('0x').lower(),
          'source':str(p.resolve()),'label':label})


def register_bitcoin_core(name: str,network: str,address: str, *, label='Bitcoin Core') -> Account:
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}',name):
        raise ValueError('Invalid Bitcoin Core wallet name')
    return account_from_record({'kind':'btc_core','asset':'BTC','network':network,
                  'address':address,'source':name,'label':label})


def register_monero_rpc(network: str,address: str, *, label='Monero wallet RPC') -> Account:
    return account_from_record({'kind':'xmr_rpc','asset':'XMR','network':network,
                  'address':address,'source':'local_wallet_rpc','label':label})


def inspect_evm_account(acc:Account, rpc_url:str, *, keystore_header: Callable=load_keystore_header,
                        service_factory=None) -> Account:
    """Check stable local signer identity and live chain ID; no password required."""
    if acc.kind!='evm_keystore':raise ValueError('Not an EVM keystore')
    path=Path(acc.source)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1_000_000:
        raise TransferError('Encrypted keystore missing or unsafe')
    _,current=keystore_header(path)
    if str(current).lower()!=acc.address.lower():
        raise TransferError('Keystore address changed! Refusing signer binding')
    if service_factory is None:
        from evm_phase2 import EVMPhaseTwo
        service_factory=EVMPhaseTwo
    service=service_factory(acc.network,rpc_url)
    health=service.health()
    balance=service.balance(acc.address)
    return replace(acc,status='EVM RPC + KEYSTORE PATH / PASSWORD NOT PROVEN',
                   can_receive=True,can_spend=False,signer_proven=False,
                   details=f"Chain ID {health['chain_id']} · Block {balance['block']} · "
                           f"Native {balance['native']} {balance['gas_asset']}. "
                           'Signing still requires password and transaction authorization; independently restore before funding.')


def inspect_btc_account(acc:Account, url:str, cookie:str, *, service_factory=None) -> Account:
    if acc.kind!='btc_core':raise ValueError('Not a Bitcoin Core account')
    if service_factory is None:
        from btc_phase1 import BitcoinPhaseOne,NodeConfig
        service_factory=lambda:BitcoinPhaseOne(NodeConfig(url,cookie,acc.network))
    svc=service_factory()
    rpc=svc.wallet_rpc(acc.source)
    ownership=rpc.call('getaddressinfo',acc.address)
    if not isinstance(ownership,dict) or not ownership.get('ismine') or ownership.get('iswatchonly'):
        raise TransferError('Selected Bitcoin address is not spendably owned by Core wallet')
    info=rpc.call('getwalletinfo')
    spend=bool(info.get('private_keys_enabled')) and not info.get('external_signer')
    bal=svc.balance(acc.source)
    return replace(acc,status='LIVE BITCOIN CORE / BACKUP NOT VERIFIED' if spend else 'WATCH ONLY BITCOIN CORE',
                   can_receive=True,can_spend=spend,signer_proven=spend,
                   details=f"{acc.network} · Trusted {bal['trusted']} BTC · Pending {bal['untrusted_pending']} BTC. "
                           'Wallet backup and independent restoration still required.')


def inspect_xmr_account(acc:Account,url:str,user:str,password:str,*,service_factory=None) -> Account:
    if acc.kind!='xmr_rpc':raise ValueError('Not a Monero wallet-RPC account')
    if service_factory is None:
        from xmr_phase3 import MoneroPhaseThree
        service_factory=lambda:MoneroPhaseThree(url,user,password,network=acc.network)
    svc=service_factory()
    health=svc.health()
    addr=health.get('address')
    if addr!=acc.address:
        raise TransferError('Monero wallet-RPC identity changed; refusing account binding')
    bal=svc.balance()
    return replace(acc,status='MONERO RPC LINKED / SPENDABILITY NOT PROVEN',
                   can_receive=True,can_spend=False,signer_proven=False,
                   details=f"{acc.network} · Unlocked {bal.get('unlocked','unavailable')} XMR. "
                           'Confirm wallet is spend-capable; independently test recovery before funding.')


def inspect_vault_evm_account(acc:Account, password:str, rpc_url:str, *,
                              signer_factory=None, balance_reader=None) -> Account:
    """Verify an EVM vault *derivation* against stored public address and chain RPC.

    This does NOT prove independent mnemonic recovery, real sending, or a token's
    balance/contract. Does not store the password/seed. Only accepts the exact
    vault entry and matching EVM network; never silently use another coin entry.
    """
    if acc.kind!='vault':raise ValueError('Not an unlocked VaultForge account')
    from asset_capabilities import EVM_ALIASES, TOKEN_EVM
    chain=EVM_ALIASES.get(acc.asset) or TOKEN_EVM.get(acc.asset)
    if not chain:raise TransferError('No verified EVM vault signing route for this asset')
    if not isinstance(password,str) or not password:
        raise TransferError('Vault password required to verify local key derivation')
    if signer_factory is None:
        from backend import evm_source
        signer_factory=lambda code,path,pw,asset:evm_source(code,path,'vault',pw,asset)
    actual=signer_factory(chain,acc.source,password,acc.asset)
    if str(actual).lower()!=acc.address.lower():
        raise TransferError('Decrypted vault source did not reproduce the selected public address')
    if balance_reader is None:
        from live_balances import snapshot_evm
        balance_reader=lambda c,url,address:snapshot_evm(c,url,address)
    snap=balance_reader(chain,rpc_url,acc.address)
    return replace(acc,status='VAULT EVM ADDRESS MATCHED / RECOVERY NOT VERIFIED',
                   can_receive=True,can_spend=False,signer_proven=False,
                   details=f'Local {acc.asset} derivation matches address; {chain} RPC checked. '
                           f'Native chain balance: {snap.available} {snap.currency} at height {snap.height}. '
                           'This is NOT token balance, independent seed recovery, or a Phase 2 keystore. '
                           'Legacy vault signing requires separate authorization.')
