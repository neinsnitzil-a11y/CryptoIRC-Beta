"""Explicit asset and account taxonomy. Token contracts must be externally verified.

Each stablecoin selection produces an underlying chain address, not a new key
algorithm invented for tokens. Fiat entries are encrypted bookkeeping only.
"""
from dataclasses import dataclass
from .vaultforge import COINS

@dataclass(frozen=True)
class Asset:
    code: str
    label: str
    category: str
    network: str
    method: str
    base_coin: str = ''
    note: str = ''

BASE = {row[0]: Asset(row[0], row[1], 'Cryptocurrency', row[0],
                       'Monero 25-word legacy seed' if row[0]=='XMR' else ('BIP39 / BIP84' if row[2]=='bip84' else 'BIP39 / BIP44'),
                       row[0]) for row in COINS}
TOKENS = [
  Asset('USDT-ETH','Tether USD₮','Stablecoin','Ethereum (ERC-20)','Ethereum BIP44 address','ETH','Gas: ETH'),
  Asset('USDT-TRX','Tether USD₮','Stablecoin','Tron (TRC-20)','TRON BIP44 address','TRX','Gas: TRX / energy'),
  Asset('USDT-SOL','Tether USD₮','Stablecoin','Solana (SPL)','Solana BIP44 address','SOL','Receiving SPL tokens requires associated token account; verify in a trusted Solana wallet'),
  Asset('USDT-BSC','Tether USD₮','Stablecoin','BNB Smart Chain (BEP-20)','Ethereum BIP44-compatible EVM address','ETH','Gas: BNB; verify token contract on BSC'),
  Asset('USDT-POL','Tether USD₮','Stablecoin','Polygon PoS','Ethereum BIP44-compatible EVM address','ETH','Gas: POL; verify token contract'),
  Asset('USDT-ARB','Tether USD₮','Stablecoin','Arbitrum One','Ethereum BIP44-compatible EVM address','ETH','Gas: ETH; verify token contract'),
  Asset('USDT-OP','Tether USD₮','Stablecoin','Optimism','Ethereum BIP44-compatible EVM address','ETH','Gas: ETH; verify token contract'),
  Asset('USDT-AVAX','Tether USD₮','Stablecoin','Avalanche C-Chain','Ethereum BIP44-compatible EVM address','ETH','Gas: AVAX; verify token contract'),
  Asset('USDC-ETH','USD Coin','Stablecoin','Ethereum (ERC-20)','Ethereum BIP44 address','ETH','Gas: ETH; verify official contract'),
  Asset('USDC-SOL','USD Coin','Stablecoin','Solana (SPL)','Solana BIP44 address','SOL','Verify token account and token mint in independent wallet'),
  Asset('USDC-BASE','USD Coin','Stablecoin','Base','Ethereum BIP44-compatible EVM address','ETH','Gas: ETH; verify official Base contract'),
  Asset('DAI-ETH','DAI','Stablecoin','Ethereum (ERC-20)','Ethereum BIP44 address','ETH','Gas: ETH; verify official contract'),
]
# Broad ISO-4217 catalog for OFFLINE bookkeeping only. It does not provide payment rails.
from .exchange_engine import CURRENCY_CATALOG
FIAT = [(code, CURRENCY_CATALOG[code]['name']) for code in sorted(CURRENCY_CATALOG)]

ASSETS = {**BASE, **{x.code:x for x in TOKENS}}
CATEGORIES = ('Cryptocurrency','Stablecoin','Fiat ledger')

def assets_for(category: str):
    if category == 'Cryptocurrency':
        return [x for x in BASE.values()]
    if category == 'Stablecoin':
        return TOKENS[:]
    return []

def coin_for_asset(code: str):
    return ASSETS[code].base_coin

def validate_asset_code(code: str):
    if code not in ASSETS: raise ValueError('Unsupported crypto asset identifier')
    return ASSETS[code]
