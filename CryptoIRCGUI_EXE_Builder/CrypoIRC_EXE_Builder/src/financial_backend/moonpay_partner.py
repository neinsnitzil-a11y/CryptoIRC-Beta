"""SERVER-ONLY MoonPay *sandbox* URL signing utility for approved partners.

Never import this module in desktop/client code. This does not initiate
payments, verify receipts or guarantee the provider accepts a route. A
partner must obtain TEST credentials, approve supported currencies/network,
and deploy an authenticated backend before exposing a checkout endpoint.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import re
from urllib.parse import urlencode, quote
from asset_capabilities import CAPABILITIES

class PartnerError(ValueError): pass

# These mappings are candidates for an approved MoonPay partner configuration,
# NOT a declaration of current availability in every region. Further pairs
# are intentionally omitted pending live partner catalog verification.
CANDIDATE_MOONPAY_CODES = {
    'BTC':'btc', 'ETH':'eth','LTC':'ltc','SOL':'sol',
    'USDT-ETH':'usdt','USDC-ETH':'usdc','USDC-SOL':'usdc_sol',
}

def signed_sandbox_buy_url(*,asset:str,address:str,fiat:str,amount:str,
                            publishable_key:str,secret_key:str,approved_codes:dict[str,str]|None=None)->str:
    from wallet_funding import validate_payment
    if not (publishable_key.startswith('pk_test_') and secret_key.startswith('sk_test_')):
        raise PartnerError('Only sandbox API keys are accepted')
    if asset not in CAPABILITIES or asset not in CANDIDATE_MOONPAY_CODES:
        raise PartnerError('Not in the candidate sandbox on-ramp route set')
    # Partner approval must explicitly enable each asset. Empty by default.
    allowed=approved_codes or {}
    if asset not in allowed or allowed[asset] != CANDIDATE_MOONPAY_CODES[asset]:
        raise PartnerError('Route not approved in the partner sandbox configuration')
    if fiat not in ('USD','EUR','GBP','CAD','AUD'):
        raise PartnerError('Fiat currency not allowlisted in this sandbox example')
    from backend import verify_public_address
    from core.assets import ASSETS
    if not verify_public_address(ASSETS[asset].base_coin,address):
        raise PartnerError('Invalid public receiving address')
    if not re.fullmatch(r'[\x21-\x7e]{20,160}',address):
        raise PartnerError('Invalid address characters')
    value=validate_payment(amount,fiat)
    # Sign the exact '?query' including the question mark, as in MoonPay docs.
    params=[('apiKey',publishable_key),('currencyCode',allowed[asset]),
            ('walletAddress',address),('baseCurrencyCode',fiat.lower()),
            ('baseCurrencyAmount',str(value))]
    query='?'+urlencode(params,quote_via=quote,safe='')
    signature=base64.b64encode(hmac.new(secret_key.encode('utf-8'),query.encode('utf-8'),hashlib.sha256).digest()).decode('ascii')
    return 'https://buy-sandbox.moonpay.com/'+query+'&signature='+quote(signature,safe='')
