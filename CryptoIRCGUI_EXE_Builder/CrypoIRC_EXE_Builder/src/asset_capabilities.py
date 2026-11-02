"""Truthful per-asset capability registry. Coverage != live-money certification.

Registry is generated from the canonical 30 cryptocurrency and 12 stablecoin
choices. In particular, never invent a signing mechanism for a listed coin.
"""
from __future__ import annotations
from dataclasses import dataclass
from core.assets import BASE, TOKENS
from core.transfer import COIN_NETWORKS

# Existing EVM adapter codes; these use an independently configured Ethereum
# V3 keystore and a chain-matching authenticated RPC. Not spendable via .vault.
EVM_ALIASES = {
    'ETH':'ETH', 'ETC':'ETC', 'BSC':'BNB', 'POLYGON':'POL',
    'AVAXC':'AVAX', 'ARB':'ARB', 'OP':'OP',
}
TOKEN_EVM = {
    'USDT-ETH':'ETH', 'USDT-BSC':'BNB', 'USDT-POL':'POL',
    'USDT-ARB':'ARB','USDT-OP':'OP', 'USDT-AVAX':'AVAX',
    'USDC-ETH':'ETH','USDC-BASE':'BASE','DAI-ETH':'ETH',
}

@dataclass(frozen=True)
class Capability:
    code: str
    name: str
    category: str
    network: str
    address_generation: bool
    sign_method: str
    can_spend_if_connected: bool
    chain_key: str
    note: str
    recovery_verified: bool = False
    mainnet_tested: bool = False


def _capability(a) -> Capability:
    code=a.code
    if code=='BTC':
        method='Bitcoin Core descriptor wallet + PSBT (separate from .vault)';chain='BTC';spend=True
        note='Bitcoin Core wallet needed. Generated BIP39 .vault address is NOT automatically imported or spendable.'
    elif code=='XMR':
        method='Local Monero wallet RPC';chain='XMR';spend=True
        note='Requires synchronized, backed-up wallet RPC. Native 25-word legacy recovery needs independent restore.'
    elif code in EVM_ALIASES and EVM_ALIASES[code] in COIN_NETWORKS:
        chain=EVM_ALIASES[code];spend=True
        method='EVM Phase 2 / encrypted V3 keystore'
        note='A separate V3 keystore and matching chain-ID RPC required; the .vault is not connected automatically.'
    elif code in TOKEN_EVM and TOKEN_EVM[code] in COIN_NETWORKS:
        chain=TOKEN_EVM[code];spend=True
        method='EVM Phase 2 / ERC-20 contract transfer'
        note='Requires V3 keystore, native gas coin, and independently verified token contract; chain-matched RPC required.'
    elif code in ('LTC','DOGE','BCH','SOL','TRX','XRP'):
        method='Address/key generation + Phase 6 read-only chain RPC (NO signing)';chain=code;spend=False
        note='Network-specific balance lookup available in Chain Expansion. NO signing or independent recovery. Do NOT fund a generated address without independent recovery and spending proof.'
    else:
        method='Address/key generation only';chain='';spend=False
        note='No verified in-app signing, chain synchronization, or full recovery flow. Do NOT fund without external verification.'
    return Capability(code,a.label,a.category,a.network,True,method,spend,chain,note)

CAPABILITIES = {a.code:_capability(a) for a in [*BASE.values(),*TOKENS]}


def get_capability(code: str) -> Capability:
    return CAPABILITIES[code]


def catalog_stats() -> dict:
    values=list(CAPABILITIES.values())
    return {
        'base_coins':sum(c.category=='Cryptocurrency' for c in values),
        'token_networks':sum(c.category=='Stablecoin' for c in values),
        'connected_signer_routes':sum(c.can_spend_if_connected for c in values),
        'address_only':sum(not c.can_spend_if_connected for c in values),
        'mainnet_certified':sum(c.mainnet_tested for c in values),
        'read_only_chain_adapters':sum(c.code in ('LTC','DOGE','BCH','SOL','TRX','XRP') for c in values),
        'generator_only':sum(not c.can_spend_if_connected and c.code not in ('LTC','DOGE','BCH','SOL','TRX','XRP') for c in values),
    }
