"""Public-address funding routes. NO credit-card data or secrets.

Official checkout is opened separately; only an approved partner backend may
make signed, address-prefilled on-ramp sessions. This module never claims a
completed purchase or credits local balances.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

PROVIDER_URLS = {
    "MoonPay — official website": "https://www.moonpay.com/buy",
}
ALLOWED_FIAT = ("USD", "GBP", "EUR", "INR", "CAD", "AUD", "JPY", "BRL", "CHF", "NGN", "ZAR", "MXN", "AED")
# Explicit route labels: never silently convert a token to another chain.
NETWORKS = {
    "BTC": "Bitcoin mainnet", "ETH": "Ethereum mainnet", "LTC":"Litecoin mainnet",
    "XMR":"Monero mainnet", "SOL":"Solana mainnet",
    "USDT-ETH":"Ethereum (ERC-20)", "USDT-TRX":"Tron (TRC-20)",
    "USDT-SOL":"Solana (SPL)", "USDT-BSC":"BNB Smart Chain (BEP-20)",
    "USDT-POL":"Polygon PoS", "USDT-ARB":"Arbitrum One", "USDT-OP":"Optimism",
    "USDT-AVAX":"Avalanche C-Chain", "USDC-ETH":"Ethereum (ERC-20)",
    "USDC-SOL":"Solana (SPL)","USDC-BASE":"Base", "DAI-ETH":"Ethereum (ERC-20)",
}
@dataclass(frozen=True)
class FundingTarget:
    asset: str
    address: str
    network: str
    origin: str
    label: str
    ownership_verified: bool = False

    def __post_init__(self):
        if not self.asset or len(self.asset) > 35 or not re.fullmatch(r'[A-Z0-9-]+',self.asset):
            raise ValueError('Invalid asset')
        if not self.address or len(self.address)>160 or any(c.isspace() for c in self.address):
            raise ValueError('Invalid public address')
        if not self.network or len(self.network)>75:
            raise ValueError('Unknown network')

def validate_payment(amount: str, fiat: str) -> Decimal:
    if fiat not in ALLOWED_FIAT:
        raise ValueError('Select a supported fiat currency')
    try: value=Decimal(amount)
    except (InvalidOperation,ValueError,TypeError):raise ValueError('Enter a valid amount') from None
    if not value.is_finite() or value<=0 or value>Decimal('1000000'):
        raise ValueError('Amount must be greater than zero and at most 1,000,000')
    from core.exchange_engine import CURRENCY_CATALOG
    decimals = int(CURRENCY_CATALOG[fiat].get('precision',2))
    if value.as_tuple().exponent < -decimals:
        raise ValueError('Too many decimal places for '+fiat)
    return value

def target_from_row(row: dict) -> FundingTarget:
    coin=row['coin']
    network=row.get('network') or NETWORKS.get(coin) or coin
    # No inferred alternate networks for tokens. Missing network must fail closed.
    if '-' in coin and coin not in NETWORKS:
        raise ValueError('Unsupported token/network combination')
    address=row['address']
    from backend import verify_public_address
    from core.assets import ASSETS
    underlying= row.get('underlying_coin') or (ASSETS[coin].base_coin if coin in ASSETS else coin)
    if not verify_public_address(underlying,address):
        raise ValueError('Receiving address failed initial format check')
    return FundingTarget(asset=coin,address=address,network=network,
       origin=row.get('kind','Vault public'),label=row.get('label','Wallet'),
       ownership_verified=row.get('kind')=='Bitcoin Core verified')

def provider_homepage(provider: str) -> str:
    return PROVIDER_URLS[provider]
