"""v3.3 read-only per-chain balance adapters (no signer, no transactions).

These adapters intentionally DO NOT claim that public balance proves private-key
ownership, recovery, node honesty or readiness for fiat funding. Never send
wallet passwords, private keys or mnemonic seeds to remote node endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

from core.transfer import BitcoinRPC, TransferError

COINS = ('LTC', 'DOGE', 'BCH', 'SOL', 'TRX', 'XRP')
UTXO = ('LTC', 'DOGE', 'BCH')
PRECISION = {'LTC':8, 'DOGE':8, 'BCH':8, 'SOL':9, 'TRX':6, 'XRP':6}
BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
RIPPLE58 = 'rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz'
NETWORKS = {
    'LTC':('test','main'), 'DOGE':('test','main'), 'BCH':('test','main'),
    'SOL':('devnet','mainnet'), 'TRX':('shasta','mainnet'), 'XRP':('testnet','mainnet'),
}

@dataclass(frozen=True)
class Balance:
    asset: str
    network: str
    address: str
    confirmed: str
    unit: str
    height: int | None
    state: str
    note: str
    spendable: bool = False
    signer_verified: bool = False
    recovery_verified: bool = False


def b58decode(s: str, alphabet: str = BASE58) -> bytes:
    if not isinstance(s,str) or not s or len(s)>128 or len(set(alphabet))!=58:
        raise TransferError('Invalid public address encoding')
    v=0
    for c in s:
        i=alphabet.find(c)
        if i<0:raise TransferError('Invalid public address alphabet')
        v=v*58+i
    return b'\0'*(len(s)-len(s.lstrip(alphabet[0]))) + (v.to_bytes((v.bit_length()+7)//8,'big') if v else b'')


def b58check(s: str, alphabet: str = BASE58) -> bytes:
    raw=b58decode(s,alphabet)
    if len(raw)<5 or hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4]!=raw[-4:]:
        raise TransferError('Invalid public address checksum')
    return raw[:-4]


def validate_address(asset: str, address: str) -> str:
    if asset not in COINS or not isinstance(address,str) or address!=address.strip() or not address:
        raise TransferError('Unsupported asset or invalid public address')
    if any(ord(ch)<33 or ord(ch)>126 for ch in address) or len(address)>110:
        raise TransferError('Invalid public address')
    if asset=='SOL':
        if len(b58decode(address))!=32:
            raise TransferError('Solana public address must decode to 32 bytes')
    elif asset=='TRX':
        if b58check(address)[:1]!=b'\x41' or len(b58check(address))!=21:
            raise TransferError('Invalid TRON address version')
    elif asset=='XRP':
        payload=b58check(address,RIPPLE58)
        if len(payload)!=21 or payload[:1]!=b'\x00' or not address.startswith('r'):
            raise TransferError('Expected XRP Ledger classic account address (not X-address)')
    elif asset in UTXO:
        # CashAddr / bech32 / legacy vary by chain and network: ONLY the
        # corresponding local coin daemon is authoritative for these formats.
        if not re.fullmatch(r'[A-Za-z0-9:]{18,110}',address):
            raise TransferError('Invalid UTXO public address syntax')
    return address


def amount_from_units(value, places: int) -> str:
    if isinstance(value,bool) or not isinstance(value,int) or value<0 or value>10**26:
        raise TransferError('Node returned invalid base-unit balance')
    return format(Decimal(value)/(Decimal(10)**places),'f')


def safe_rpc_endpoint(url: str, *, allow_path: bool=False) -> str:
    try:u=urlsplit(url.strip())
    except (ValueError,AttributeError):raise TransferError('Invalid node endpoint')
    try: port=u.port
    except ValueError:raise TransferError('Invalid node endpoint port')
    if u.username or u.password or u.fragment or u.query or not u.hostname or (not port and u.scheme=='http'):
        raise TransferError('Invalid node endpoint or embedded credentials')
    if u.scheme=='http':
        try:addr=ipaddress.ip_address(u.hostname)
        except ValueError:raise TransferError('HTTP requires numeric loopback RPC')
        if not addr.is_loopback:raise TransferError('HTTP requires loopback RPC')
    elif u.scheme!='https':raise TransferError('RPC requires HTTPS or local loopback HTTP')
    if not allow_path and u.path not in ('','/'):
        raise TransferError('RPC endpoint must not contain a path')
    if u.path and ('..' in u.path or '//' in u.path or '%' in u.path):
        raise TransferError('Invalid RPC URL path')
    return url.strip().rstrip('/')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise TransferError('Node redirect refused')


def post_json(url: str, body: dict) -> dict:
    """Bounded synchronous request; call from background worker only."""
    safe_rpc_endpoint(url,allow_path=True)
    payload=json.dumps(body,separators=(',',':')).encode()
    if len(payload)>8_000:raise TransferError('Node request too large')
    req=Request(url,data=payload,method='POST',headers={'Content-Type':'application/json','Accept':'application/json'})
    try:
        with build_opener(_NoRedirect()).open(req,timeout=12) as response:
            if int(response.headers.get('Content-Length') or 0)>1_000_000:
                raise TransferError('Node response too large')
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise TransferError('Node response too large')
        result=json.loads(raw)
        if not isinstance(result,dict):raise TransferError('Unexpected node response')
        return result
    except (HTTPError,URLError,TimeoutError,OSError,UnicodeError,ValueError) as exc:
        raise TransferError('Could not obtain a valid response from selected node') from exc


def rpc_json(url:str, method:str, params:list, *, transport=post_json) -> dict:
    obj=transport(url,{'jsonrpc':'2.0','id':1,'method':method,'params':params})
    if obj.get('error') is not None:
        raise TransferError('Blockchain RPC rejected '+method)
    return obj


def read_utxo_balance(asset: str, network: str, address: str, url: str, cookie_path: str,
                      wallet: str, *, rpc_factory=BitcoinRPC) -> Balance:
    """Owned-address UTXO sum, not a full wallet total. No signing whatsoever."""
    if asset not in UTXO or network not in NETWORKS[asset]:raise TransferError('Unsupported UTXO network')
    validate_address(asset,address)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', wallet):
        raise TransferError('Select a loaded local wallet name')
    if not cookie_path:raise TransferError('Select local node cookie credentials')
    # BitcoinRPC enforces numeric loopback HTTP and reads the cookie locally.
    root=rpc_factory(url,Path(cookie_path))
    chain=root.call('getblockchaininfo')
    if not isinstance(chain,dict) or chain.get('chain') != network or chain.get('initialblockdownload'):
        raise TransferError('UTXO node network mismatch or node not synchronized')
    wallets=root.call('listwallets')
    if not isinstance(wallets,list) or wallet not in wallets:
        raise TransferError('Selected coin wallet is not loaded')
    client=rpc_factory(url,Path(cookie_path),wallet)
    ownership=client.call('validateaddress',address)
    if not isinstance(ownership,dict) or not ownership.get('isvalid') or ownership.get('ismine') is not True or ownership.get('iswatchonly') is True:
        raise TransferError('Address is not owned by selected coin wallet')
    coins=client.call('listunspent',1,9999999,[address])
    if not isinstance(coins,list) or len(coins)>100000:
        raise TransferError('Cannot validate UTXO response')
    total=Decimal('0')
    for coin in coins:
        if not isinstance(coin,dict) or coin.get('address') != address:
            raise TransferError('Unexpected UTXO address')
        try:amt=Decimal(str(coin['amount']))
        except (KeyError,ValueError,InvalidOperation,TypeError):raise TransferError('Invalid UTXO amount')
        if not amt.is_finite() or amt<0 or amt.as_tuple().exponent < -8:
            raise TransferError('Invalid UTXO precision')
        total+=amt
    height=chain.get('blocks')
    if isinstance(height,bool) or not isinstance(height,int) or height<0:raise TransferError('Invalid node block height')
    return Balance(asset,network,address,format(total,'f'),asset,height,'OWNED ADDRESS / CONFIRMED UTXOs',
        'Read-only local daemon query. Confirmed unspent outputs for this address only; does not prove independent backup or recovery. No sending adapter.')


def read_solana(network: str, address: str, endpoint: str, *, expected_genesis: str='', transport=post_json) -> Balance:
    if network not in NETWORKS['SOL']:raise TransferError('Invalid Solana cluster')
    validate_address('SOL',address)
    url=safe_rpc_endpoint(endpoint)
    genesis=rpc_json(url,'getGenesisHash',[],transport=transport).get('result')
    if not isinstance(genesis,str) or len(b58decode(genesis))!=32:
        raise TransferError('Solana RPC did not return a valid genesis hash')
    if not expected_genesis or expected_genesis!=genesis:
        raise TransferError('Solana genesis hash must match an independently verified cluster genesis hash')
    result=rpc_json(url,'getBalance',[address,{'commitment':'finalized'}],transport=transport).get('result')
    if not isinstance(result,dict) or not isinstance(result.get('context'),dict) or not isinstance(result.get('value'),int):
        raise TransferError('Malformed Solana balance response')
    slot=result['context'].get('slot')
    if isinstance(slot,bool) or not isinstance(slot,int) or slot<0:raise TransferError('Invalid Solana slot')
    return Balance('SOL',network,address,amount_from_units(result['value'],9),'SOL',slot,
        'FINALIZED RPC / GENESIS MATCH', 'Read-only finalized SOL balance; SPL token accounts and signing not included. RPC honesty and private-key ownership not proven.')


def read_tron(network: str, address: str, endpoint: str, *, transport=post_json) -> Balance:
    if network not in NETWORKS['TRX']:raise TransferError('Invalid TRON network')
    validate_address('TRX',address)
    base=safe_rpc_endpoint(endpoint)
    obj=transport(base+'/walletsolidity/getaccount',{'address':address,'visible':True})
    if obj.get('Error') or obj.get('error'):raise TransferError('TRON node rejected account request')
    # Empty object means not activated. Do not advertise it as a verified account.
    if not obj or 'address' not in obj or obj['address'] != address:
        raise TransferError('TRON account absent or address mismatched')
    val=obj.get('balance',0)
    return Balance('TRX',network,address,amount_from_units(val,6),'TRX',None,'SOLIDITY NODE / NETWORK UNVERIFIED',
        'Read-only solidified state. Node does not prove mainnet versus Shasta; verify endpoint independently. No signer or TRC-20 transfers.')


def read_xrp(network: str, address: str, endpoint: str, *, transport=post_json) -> Balance:
    if network not in NETWORKS['XRP']:raise TransferError('Invalid XRP network')
    validate_address('XRP',address)
    url=safe_rpc_endpoint(endpoint)
    obj=rpc_json(url,'account_info',[{'account':address,'ledger_index':'validated','strict':True}],transport=transport)
    result=obj.get('result')
    if not isinstance(result,dict) or result.get('validated') is not True:
        raise TransferError('XRP response not from a validated ledger')
    data=result.get('account_data')
    if not isinstance(data,dict) or data.get('Account')!=address:
        raise TransferError('XRP account missing or mismatched; may not be activated')
    drops=data.get('Balance')
    if not isinstance(drops,str) or not re.fullmatch(r'\d{1,24}',drops):
        raise TransferError('Invalid XRP drops amount')
    ledger=result.get('ledger_index')
    if isinstance(ledger,bool) or not isinstance(ledger,int) or ledger<0:
        raise TransferError('Invalid validated XRP ledger number')
    return Balance('XRP',network,address,amount_from_units(int(drops),6),'XRP',ledger,'VALIDATED LEDGER / NETWORK UNVERIFIED',
        'Read-only validated account balance includes required XRP reserve; not fully spendable. Verify node network, destination tags and signer separately.')


def read_balance(asset: str, network: str, address: str, endpoint: str, *, cookie_path='',wallet='',expected_genesis='') -> Balance:
    if asset in UTXO:
        return read_utxo_balance(asset,network,address,endpoint,cookie_path,wallet)
    if asset=='SOL':return read_solana(network,address,endpoint,expected_genesis=expected_genesis)
    if asset=='TRX':return read_tron(network,address,endpoint)
    if asset=='XRP':return read_xrp(network,address,endpoint)
    raise TransferError('No chain read adapter')
