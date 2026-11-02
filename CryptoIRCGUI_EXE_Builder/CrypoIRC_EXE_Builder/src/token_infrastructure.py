"""Phase 7: explicit, read-only EVM/SPL/TRC20 token balance infrastructure.

An operator-pinned token contract/mint is NOT an official-contract attestation.
No token module here signs or broadcasts. RPC/provider statements aren't proof of
ownership or independent recovery. Every network and token ID must be explicit.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import re
import sqlite3
from contextlib import closing

from core.assets import TOKENS
from core.transfer import COIN_NETWORKS, TransferError
from chain_expansion import b58decode, b58check, safe_rpc_endpoint, rpc_json, post_json, validate_address

# These codes come from the existing canonical asset catalog; no implicit
# transfers from a similarly named token on a different chain.
EVM_TOKEN_NETWORKS = {
    'USDT-ETH':'ETH', 'USDT-BSC':'BNB', 'USDT-POL':'POL',
    'USDT-ARB':'ARB', 'USDT-OP':'OP', 'USDT-AVAX':'AVAX',
    'USDC-ETH':'ETH', 'USDC-BASE':'BASE', 'DAI-ETH':'ETH',
}
SOL_TOKENS = frozenset(('USDT-SOL','USDC-SOL'))
TRON_TOKENS = frozenset(('USDT-TRX',))
TOKEN_CODES = tuple(x.code for x in TOKENS)
SOL_NETWORKS = ('devnet','mainnet')
TRON_NETWORKS = ('shasta','mainnet')
TOKEN_PROGRAMS = frozenset((
    'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
    'TokenzQdBNbLqP5VEhdkAS6EPF1GJBMURRmyWtxr5j',
))
HEX_64 = re.compile(r'[0-9a-fA-F]{64}\Z')
EVM_ADDRESS = re.compile(r'0x[a-fA-F0-9]{40}\Z')

@dataclass(frozen=True)
class TokenSpec:
    code: str
    protocol: str
    network: str
    chain_id: int | None
    gas_coin: str
    symbol: str
    token_id: str
    decimals: int
    genesis: str = ''
    attestation: str = 'USER_PINNED_NOT_AUDITED'

@dataclass(frozen=True)
class TokenBalance:
    code: str
    network: str
    address: str
    token_id: str
    symbol: str
    amount_units: int
    decimals: int
    amount: str
    block_or_slot: int | None
    gas_coin: str
    gas_units: int | None
    state: str
    note: str
    spendable: bool = False


def _units_to_decimal(n: int, decimals: int) -> str:
    if isinstance(n,bool) or not isinstance(n,int) or n<0 or n>=2**256:
        raise TransferError('Invalid token balance base units')
    return format(Decimal(n) / (Decimal(10)**decimals),'f')


def _positive_uint(value, limit=2**256):
    if isinstance(value,bool) or not isinstance(value,int) or value<0 or value>=limit:
        raise TransferError('Invalid integer response from token node')
    return value


def make_spec(code: str, network: str, token_id: str, decimals: int,
              *, genesis: str = '') -> TokenSpec:
    if code not in TOKEN_CODES:
        raise TransferError('Unknown stablecoin/network selection')
    if isinstance(decimals,bool) or not isinstance(decimals,int) or not 0<=decimals<=36:
        raise TransferError('Token decimals must be an integer from 0 to 36')
    symbol=code.split('-',1)[0]
    if code in EVM_TOKEN_NETWORKS:
        evm=EVM_TOKEN_NETWORKS[code]
        if network != evm or not EVM_ADDRESS.fullmatch(token_id):
            raise TransferError('Token contract and selected EVM chain must match the asset route')
        if genesis:raise TransferError('EVM route does not use Solana genesis')
        chain_id=COIN_NETWORKS[evm][1]
        return TokenSpec(code,'ERC20',network,chain_id,COIN_NETWORKS[evm][2],symbol,token_id.lower(),decimals)
    if code in SOL_TOKENS:
        if network not in SOL_NETWORKS:
            raise TransferError('Choose the Solana cluster explicitly')
        if len(b58decode(token_id))!=32:
            raise TransferError('Token mint must be a 32-byte Solana public key')
        if not genesis or len(b58decode(genesis))!=32:
            raise TransferError('Pin an independently verified Solana genesis hash')
        return TokenSpec(code,'SPL',network,None,'SOL',symbol,token_id,decimals,genesis)
    if code in TRON_TOKENS:
        if network not in TRON_NETWORKS:
            raise TransferError('Choose the TRON network explicitly')
        validate_address('TRX',token_id)
        if genesis:raise TransferError('TRON route does not use Solana genesis')
        return TokenSpec(code,'TRC20',network,None,'TRX',symbol,token_id,decimals)
    raise TransferError('No token adapter for asset')


class TokenRegistry:
    """Only public token metadata. Wallet keys/credentials are never stored."""
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else Path.home()/'.crypto_nocturne'/'token_registry.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=8)) as con:
            con.execute('''CREATE TABLE IF NOT EXISTS token_pins
                (code TEXT NOT NULL, network TEXT NOT NULL, protocol TEXT NOT NULL,
                 token_id TEXT NOT NULL, decimals INTEGER NOT NULL, genesis TEXT NOT NULL,
                 PRIMARY KEY(code,network))''')
            con.commit()
    def pin(self,spec: TokenSpec):
        # Force validation even for constructed dataclasses.
        spec=make_spec(spec.code,spec.network,spec.token_id,spec.decimals,genesis=spec.genesis)
        with closing(sqlite3.connect(self.path,timeout=8)) as con:
            con.execute('BEGIN IMMEDIATE')
            old=con.execute('SELECT token_id,decimals,genesis FROM token_pins WHERE code=? AND network=?',
                            (spec.code,spec.network)).fetchone()
            if old and old!=(spec.token_id,spec.decimals,spec.genesis):
                raise TransferError('Existing token pin differs. Remove it explicitly before replacing it.')
            con.execute('INSERT OR IGNORE INTO token_pins VALUES(?,?,?,?,?,?)',
                        (spec.code,spec.network,spec.protocol,spec.token_id,spec.decimals,spec.genesis))
            con.commit()
        return spec
    def get(self,code,network):
        with closing(sqlite3.connect(self.path,timeout=8)) as con:
            row=con.execute('SELECT token_id,decimals,genesis FROM token_pins WHERE code=? AND network=?',(code,network)).fetchone()
        return make_spec(code,network,row[0],row[1],genesis=row[2]) if row else None
    def unpin(self,code,network):
        with closing(sqlite3.connect(self.path,timeout=8)) as con:
            con.execute('DELETE FROM token_pins WHERE code=? AND network=?',(code,network));con.commit()


def read_evm_token(spec: TokenSpec, address: str, endpoint: str, *, w3=None) -> TokenBalance:
    if spec.protocol!='ERC20':raise TransferError('Not an ERC-20 family route')
    from evm_phase2 import EVMPhaseTwo
    svc=EVMPhaseTwo(spec.network,endpoint,w3=w3)
    check=svc.health()  # exact network/chain-ID is mandatory
    holder=svc._address(address)
    contract=svc._contract(spec.token_id)
    if int(contract.functions.decimals().call())!=spec.decimals:
        raise TransferError('On-chain decimals differ from user-pinned token; refusing balance')
    if str(contract.functions.symbol().call())!=spec.symbol:
        raise TransferError('On-chain symbol differs from selected token route; refusing balance')
    units=_positive_uint(int(contract.functions.balanceOf(holder).call()))
    gas=_positive_uint(int(svc.w3.eth.get_balance(holder)))
    return TokenBalance(spec.code,spec.network,holder,spec.token_id,spec.symbol,units,spec.decimals,
        _units_to_decimal(units,spec.decimals),check['block'],spec.gas_coin,gas,'CHAIN_ID_AND_METADATA_MATCH',
        'Read-only contract balance. User-pinned contract is NOT an independently authenticated issuer token; do not fund without verifying the official contract and signer.')


def read_spl_token(spec: TokenSpec, address: str, endpoint: str, *, transport=post_json) -> TokenBalance:
    if spec.protocol!='SPL':raise TransferError('Not a Solana SPL token route')
    validate_address('SOL',address)
    url=safe_rpc_endpoint(endpoint)
    observed=rpc_json(url,'getGenesisHash',[],transport=transport).get('result')
    if observed!=spec.genesis:
        raise TransferError('Solana genesis differs from independently pinned cluster')
    res=rpc_json(url,'getTokenAccountsByOwner',[address,{'mint':spec.token_id},
        {'encoding':'jsonParsed','commitment':'finalized'}],transport=transport).get('result')
    if not isinstance(res,dict) or not isinstance(res.get('context'),dict) or not isinstance(res.get('value'),list):
        raise TransferError('Malformed SPL token accounts response')
    slot=_positive_uint(res['context'].get('slot'),2**64)
    accounts=res['value']
    if len(accounts)>10000:raise TransferError('Excessive SPL token accounts response')
    total=0
    for acc in accounts:
        try:
            if acc['account']['owner'] not in TOKEN_PROGRAMS:raise ValueError()
            data=acc['account']['data']
            if data['program'] not in ('spl-token','spl-token-2022'):raise ValueError()
            info=data['parsed']['info']
            token=info['tokenAmount']
            if info['mint']!=spec.token_id or info['owner']!=address or info['state'] not in ('initialized','frozen'):
                raise ValueError()
            d=token['decimals'];s=token['amount']
            if isinstance(d,bool) or d!=spec.decimals or not isinstance(s,str) or not re.fullmatch(r'[0-9]{1,78}',s):
                raise ValueError()
            total+=_positive_uint(int(s),2**64)
            _positive_uint(total)
        except (KeyError,TypeError,ValueError,OverflowError) as e:
            raise TransferError('SPL token account does not match pinned mint, owner, state or decimals') from e
    return TokenBalance(spec.code,spec.network,address,spec.token_id,spec.symbol,total,spec.decimals,
        _units_to_decimal(total,spec.decimals),slot,'SOL',None,'FINALIZED_MINT_AND_GENESIS_MATCH',
        'Read-only sum of mint-matched SPL token accounts. Mint is user-pinned, not issuer-verified. No SPL signing, ATA creation, Token-2022 extension handling, or spendable gas calculation.')


def _tron_constant(url,contract,holder,selector,*,transport):
    req={'owner_address':holder,'contract_address':contract,'function_selector':selector,
         'parameter':b58check(holder)[1:].hex().rjust(64,'0') if selector=='balanceOf(address)' else '',
         'visible':True}
    result=transport(url+'/walletsolidity/triggerconstantcontract',req)
    if not isinstance(result,dict) or result.get('result',{}).get('result') is not True:
        raise TransferError('TRON solidified constant call failed')
    values=result.get('constant_result')
    if not isinstance(values,list) or len(values)!=1 or not isinstance(values[0],str) or not HEX_64.fullmatch(values[0]):
        raise TransferError('Malformed TRON constant call result')
    return int(values[0],16)


def read_trc20_token(spec: TokenSpec, address: str, endpoint: str, *, transport=post_json) -> TokenBalance:
    if spec.protocol!='TRC20':raise TransferError('Not a TRC-20 token route')
    validate_address('TRX',address)
    base=safe_rpc_endpoint(endpoint)
    decimals=_tron_constant(base,spec.token_id,address,'decimals()',transport=transport)
    if decimals!=spec.decimals:raise TransferError('TRON token decimals differ from pinned value')
    units=_positive_uint(_tron_constant(base,spec.token_id,address,'balanceOf(address)',transport=transport))
    return TokenBalance(spec.code,spec.network,address,spec.token_id,spec.symbol,units,spec.decimals,
        _units_to_decimal(units,spec.decimals),None,'TRX',None,'SOLIDIFIED_CONTRACT_READ_NETWORK_UNVERIFIED',
        'Read-only solidified TRC-20 balance; TRON endpoint network and token issuer are not independently authenticated. No signing, energy/bandwidth calculation or transaction delivery verification.')


def read_token_balance(spec: TokenSpec, address: str, endpoint: str, *, transport=post_json, w3=None) -> TokenBalance:
    # Guard against callers constructing inconsistent dataclasses directly.
    expected=make_spec(spec.code,spec.network,spec.token_id,spec.decimals,genesis=spec.genesis)
    if expected!=spec:raise TransferError('Token specification is inconsistent with canonical route')
    if spec.protocol=='ERC20':return read_evm_token(spec,address,endpoint,w3=w3)
    if spec.protocol=='SPL':return read_spl_token(spec,address,endpoint,transport=transport)
    if spec.protocol=='TRC20':return read_trc20_token(spec,address,endpoint,transport=transport)
    raise TransferError('No read adapter for requested token protocol')
