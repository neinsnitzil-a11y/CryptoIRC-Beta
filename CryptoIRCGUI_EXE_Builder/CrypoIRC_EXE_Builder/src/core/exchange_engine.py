"""Read-only reference FX / market price quoting.

NEVER executes financial transactions, cards, purchases, payouts, or wallet credits.
All rates are indicative; actual money operations must occur at provider checkout.
Data calls use fixed HTTPS hosts and strict response validation. No keys or PII sent.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
import json, time, threading
import requests

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data' / 'iso4217_catalog.json'
CURRENCY_CATALOG = {x['code']:x for x in json.loads(CATALOG_PATH.read_text('utf-8'))}
FIAT_CODES=tuple(sorted(CURRENCY_CATALOG))

# Explicit CoinGecko IDs prevent ambiguous symbol matches and lookalike token names.
CRYPTO_IDS = {
 'BTC':'bitcoin', 'ETH':'ethereum', 'XMR':'monero', 'LTC':'litecoin',
 'SOL':'solana','DOGE':'dogecoin','XRP':'ripple','TRX':'tron','BNB':'binancecoin',
 'ADA':'cardano','DOT':'polkadot','AVAX':'avalanche-2','BCH':'bitcoin-cash',
 'LINK':'chainlink','XLM':'stellar','ETC':'ethereum-classic','ATOM':'cosmos',
 'XTZ':'tezos','ALGO':'algorand','HBAR':'hedera-hashgraph',
 'USDT':'tether', 'USDC':'usd-coin','DAI':'dai',
}
STABLECOIN_NETWORKS = {
 'USDT':('Ethereum (ERC-20)','Tron (TRC-20)','Solana (SPL)','BNB Smart Chain (BEP-20)','Polygon PoS','Arbitrum One','Optimism','Avalanche C-Chain'),
 'USDC':('Ethereum (ERC-20)','Solana (SPL)','Base'),
 'DAI':('Ethereum (ERC-20)',),
}
FIAT_PROVIDERS = {
 'Wise': 'https://wise.com/',
 'Revolut': 'https://www.revolut.com/',
 'Bank / official institution': 'https://www.consumerfinance.gov/consumer-tools/bank-accounts/',
 'PayPal': 'https://www.paypal.com/',
 'Cash App': 'https://cash.app/',
}
CRYPTO_ONRAMPS = {
 'Stripe Crypto Onramp': 'https://crypto.link.com/',
 'Ramp Network': 'https://ramp.network/',
}
class ExchangeError(ValueError):pass

@dataclass(frozen=True)
class Estimate:
    source: str
    destination: str
    source_amount: Decimal
    rate: Decimal
    estimated_amount: Decimal
    source_name: str
    updated_utc: str
    notice: str


def positive_amount(value: str, code: str | None = None) -> Decimal:
    try: amount=Decimal(str(value).strip())
    except (InvalidOperation, ValueError):raise ExchangeError('Enter a numeric amount') from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal('1000000000'):
        raise ExchangeError('Amount must be positive, finite, and at most 1 billion')
    if code and code in CURRENCY_CATALOG:
        precision=CURRENCY_CATALOG[code]['precision']
        if amount != amount.quantize(Decimal(1).scaleb(-precision)):
            raise ExchangeError(f'{code} requires no more than {precision} decimal places')
    return amount


def _https_json(url: str, timeout=(5,13)) -> dict:
    # URL is ALWAYS built inside this file from hardcoded HTTPS hosts and allowlisted codes.
    try:
        r=requests.get(url, timeout=timeout, allow_redirects=False, headers={'User-Agent':'CRYPTO-Wallet-Suite/1.3 (indicative rate viewer)'})
        r.raise_for_status()
    except requests.RequestException:
        raise ExchangeError('Rate provider unavailable. No quote was generated.') from None
    if not 200 <= r.status_code < 300 or len(r.content)>700000:
        raise ExchangeError('Unexpected rate-provider response')
    try: o=r.json()
    except ValueError:raise ExchangeError('Invalid rate response') from None
    if not isinstance(o,dict):raise ExchangeError('Invalid rate schema')
    return o

_fx_lock=threading.Lock()
_fx_cache:dict[str,tuple[float,dict]]={}
_crypto_cache:dict[str,tuple[float,dict]]={}


def fiat_rates(base: str) -> tuple[dict,str]:
    if base not in CURRENCY_CATALOG:raise ExchangeError('Unknown source currency')
    with _fx_lock:
        cached=_fx_cache.get(base)
        if cached and time.monotonic()-cached[0]<3600:return cached[1]['rates'],cached[1]['time_last_update_utc']
    data=_https_json('https://open.er-api.com/v6/latest/'+base)
    if data.get('result')!='success' or data.get('base_code')!=base or not isinstance(data.get('rates'),dict):
        raise ExchangeError('Rate provider returned inconsistent currency information')
    update=data.get('time_last_update_unix')
    if not isinstance(update,int) or update<=0 or abs(time.time()-update)>3*86400:
        raise ExchangeError('Reference FX rates are too old. No quote generated.')
    with _fx_lock:_fx_cache[base]=(time.monotonic(),data)
    return data['rates'],data.get('time_last_update_utc') or datetime.fromtimestamp(update,timezone.utc).isoformat()


def fiat_estimate(amount:str,from_code:str,to_code:str) -> Estimate:
    val=positive_amount(amount,from_code)
    if from_code not in CURRENCY_CATALOG or to_code not in CURRENCY_CATALOG:
        raise ExchangeError('Unsupported ISO currency code')
    if from_code==to_code:
        return Estimate(from_code,to_code,val,Decimal('1'),val,'Identity / no exchange',
                        datetime.now(timezone.utc).isoformat(), 'Same-currency calculation; no money transferred.')
    rates,updated=fiat_rates(from_code)
    raw=rates.get(to_code)
    try:rate=Decimal(str(raw))
    except (InvalidOperation,ValueError):raise ExchangeError(f'No reference rate for {from_code} → {to_code}') from None
    if not rate.is_finite() or rate<=0:raise ExchangeError('Rate provider returned a nonpositive rate')
    with localcontext() as ctx:
        ctx.prec=36
        est=val*rate
    return Estimate(from_code,to_code,val,rate,est,'ExchangeRate-API reference rates',updated,
        'Indicative daily mid-market reference. NOT an executable provider quote. Provider spreads, card fees and settlement may differ.')


def crypto_estimate(amount:str, from_fiat:str, coin:str) -> Estimate:
    val=positive_amount(amount,from_fiat)
    if from_fiat not in CURRENCY_CATALOG:raise ExchangeError('Unknown source fiat currency')
    if coin not in CRYPTO_IDS:raise ExchangeError(f'No verified market-pricing mapping for {coin}')
    coin_id=CRYPTO_IDS[coin]
    with _fx_lock:
        cache=_crypto_cache.get(coin_id)
        if cache and time.monotonic()-cache[0]<45:data=cache[1]
        else:data=None
    if data is None:
        from urllib.parse import urlencode
        url='https://api.coingecko.com/api/v3/simple/price?'+urlencode({'ids':coin_id,'vs_currencies':'usd','include_last_updated_at':'true'})
        data=_https_json(url)
        with _fx_lock:_crypto_cache[coin_id]=(time.monotonic(),data)
    obj=data.get(coin_id,{})
    if not isinstance(obj,dict):raise ExchangeError('No crypto price returned')
    try:usd_per_coin=Decimal(str(obj.get('usd')))
    except (InvalidOperation,ValueError):raise ExchangeError('Crypto market price unavailable') from None
    updated=obj.get('last_updated_at')
    if not isinstance(updated,int) or abs(time.time()-updated)>1800:raise ExchangeError('Crypto price too old to display')
    if usd_per_coin<=0 or not usd_per_coin.is_finite():raise ExchangeError('Invalid crypto market price')
    fx_usd_per_unit=Decimal('1') if from_fiat=='USD' else fiat_estimate('1',from_fiat,'USD').rate
    with localcontext() as ctx:
        ctx.prec=36
        rate=fx_usd_per_unit/usd_per_coin
        units=val*rate
    return Estimate(from_fiat,coin,val,rate,units,'CoinGecko market reference + ExchangeRate-API FX',
                    datetime.fromtimestamp(updated,timezone.utc).isoformat(),
                    'INDICATIVE MARKET ESTIMATE ONLY. This is NOT a card purchase or exchange order. On-ramp quote, slippage, provider fees, limits, and network support may differ.')


def quote_summary(q:Estimate) -> str:
    def fmt(n):return format(n,'.10g')
    return (f'YOU PAY:   {q.source_amount} {q.source}\n'
            f'ESTIMATE:  {fmt(q.estimated_amount)} {q.destination}\n'
            f'REFERENCE RATE:  1 {q.source} ≈ {fmt(q.rate)} {q.destination}\n'
            f'SOURCE: {q.source_name}\nUPDATED: {q.updated_utc}\n\n'
            f'{q.notice}\n\nStatus: ESTIMATE ONLY — no money moved, no balance credited.')
