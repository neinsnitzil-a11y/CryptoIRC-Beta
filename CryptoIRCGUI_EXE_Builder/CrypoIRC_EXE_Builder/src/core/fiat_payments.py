"""Client-only payment reference record helpers and external handoff.

NO merchant secrets, processing, provider API calls, settlement or capture.
Real payment operations belong to a separately deployed approved backend.
"""
from __future__ import annotations
import json, secrets, re, os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse
from . import vaultforge as vf
from .assets import FIAT

class PaymentError(ValueError): pass

METHODS = {
 'Stripe Checkout': ('Stripe', 'Server-side provider integration required'),
 'PayPal Checkout': ('PayPal', 'Server-side provider integration required'),
 'Square Checkout': ('Square', 'Server-side provider integration required'),
 'Cash App Pay (Square)': ('Square', 'Square hosted checkout; seller/buyer eligibility'),
 'Cash App Personal (external)': ('Cash App', 'Personal $Cashtag payment link / external provider; not API-verifiable'),
 'Venmo (PayPal)': ('PayPal', 'Eligible US/USD mobile PayPal checkout; not guaranteed'),
 'Wise': ('Wise', 'External provider handoff; no unapproved API transfers'),
 'Revolut Merchant': ('Revolut', 'Server-side provider integration required'),
 'Zelle (your bank)': ('Zelle', 'External bank handoff; no third-party API'),
 'ACH bank transfer': ('ACH', 'External bank handoff; no bank account provisioning'),
 'Bank wire / SWIFT': ('Wire', 'External bank handoff; no bank account provisioning'),
}
HANDOFF_URLS={
 'Wise':'https://wise.com/',
 'Zelle (your bank)':'https://www.zellepay.com/',
 'ACH bank transfer':'https://www.consumerfinance.gov/consumer-tools/bank-accounts/',
 'Bank wire / SWIFT':'https://www.consumerfinance.gov/consumer-tools/bank-accounts/',
}
HINTS={
 'Stripe Checkout':'Connect approved Stripe service through a separate server. No desktop API keys.',
 'PayPal Checkout':'Connect approved PayPal service through a separate server. No desktop API keys.',
 'Square Checkout':'Connect Square through a separately secured payment service.',
 'Cash App Pay (Square)':'Set Square credentials; Cash App option depends on seller dashboard, buyer and region.',
 'Cash App Personal (external)':'Use an existing Cash App $Cashtag link created by Cash App. No API verification or payout control.',
 'Venmo (PayPal)':'PayPal order only; Venmo display requires eligible US/USD checkout (not guaranteed by this desktop application).',
 'Revolut Merchant':'Connect Revolut through a separately secured payment service.',
 'Wise':'Complete the transfer/FX inside your own authenticated Wise account.',
 'Zelle (your bank)':'Complete directly in an enrolled participating bank application.',
 'ACH bank transfer':'Complete ACH using your bank; independently verify beneficiary details.',
 'Bank wire / SWIFT':'Complete in your bank portal; independently verify recipient and fees.',
}
# Provider request coverage is deliberately narrower than the 164-currency reference/ledger catalog.
CURRENCIES={'USD','EUR','GBP','CAD','AUD','JPY','CHF','NZD','SGD','HKD','INR','MXN','BRL','ZAR','AED','KRW'}
ZERO_DECIMAL={'JPY','KRW'}


def amount_minor(amount: str, currency: str) -> int:
    if currency not in CURRENCIES:raise PaymentError('Unsupported currency')
    try:d=Decimal(amount)
    except (InvalidOperation,ValueError,TypeError):raise PaymentError('Invalid decimal amount') from None
    precision=0 if currency in ZERO_DECIMAL else 2
    if not d.is_finite() or not Decimal('0')<d<=Decimal('100000000'):
        raise PaymentError('Amount must be positive and finite')
    scale=Decimal(10)**precision
    if d*scale != (d*scale).to_integral_value():raise PaymentError('Too many decimals')
    return int(d*scale)

def https_url(url: str, hosts:set[str])->str:
    if not isinstance(url,str):raise PaymentError('Invalid checkout URL')
    try:q=urlparse(url)
    except ValueError:raise PaymentError('Invalid checkout URL') from None
    if q.scheme!='https' or q.hostname not in hosts or q.username or q.password or not q.netloc:
        raise PaymentError('Untrusted checkout host')
    return url

def config_status(method:str):
    if method not in METHODS:raise PaymentError('Unknown payment method')
    return 'API not available in desktop; provider-backed service required'

def create_request(*args,**kwargs):
    raise PaymentError('Merchant API creation is server-only. No desktop API key is accepted.')

def payment_state(*args,**kwargs):
    raise PaymentError('Only a separately deployed provider service may verify settlement.')

def capture_paypal(*args,**kwargs):
    raise PaymentError('Provider capture is disabled in the desktop application.')

EXTERNAL_LINK_HOSTS={
 'Wise':{'wise.com','www.wise.com'},
 'Cash App Personal (external)':{'cash.app'},
 'Venmo (PayPal)':{'venmo.com','www.venmo.com','account.venmo.com'},
 'Zelle (your bank)':set(),
 'ACH bank transfer':set(),
 'Bank wire / SWIFT':set(),
}

def make_external_request(method:str,amount:str,currency:str,memo:str,public_link:str='') -> dict:
    """Reference ONLY. NEVER paid/verified; no card or bank credential collection."""
    if method not in EXTERNAL_LINK_HOSTS:
        raise PaymentError('This method uses the official merchant API. Use Generate instead')
    cents=amount_minor(amount,currency)
    if len(memo)>100:raise PaymentError('Memo must be under 100 characters')
    url=''
    if public_link.strip():
        hosts=EXTERNAL_LINK_HOSTS[method]
        if not hosts:raise PaymentError('Do not enter bank or Zelle links here; use the official bank app')
        url=https_url(public_link.strip(),hosts)
    identifier=secrets.token_hex(16)
    return {'schema':1,'id':identifier,'method':method,'provider':METHODS[method][0],
            'environment':'external','currency':currency,'minor':cents,'memo':memo.strip(),
            'created_utc':datetime.now(timezone.utc).isoformat(),'state':'external-unverified',
            'verified_utc':None,'provider_id':'external-'+identifier,
            'checkout_url':url,'provider_order_id':''}

def new_payment_file(folder:str,password:str,rec:dict) -> str:
    if len(password)<14:raise PaymentError('Encrypting password must be 14+ chars')
    location=vf.secure_dir(Path(folder).expanduser().resolve())
    p=location/('payment_'+secrets.token_hex(14)+'.fiatpay')
    blob=vf.encrypt_payload({'format':'CRYPTO-FIAT-PAYMENT-v1','record':rec},password)
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,'wb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    except BaseException:
        p.unlink(missing_ok=True);raise
    return str(p)


def read_payment_file(path:str,password:str) -> dict:
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.suffix!='.fiatpay':raise PaymentError('Select a regular .fiatpay file')
    d=vf.decrypt_payload(p.read_bytes(),password)
    if d.get('format')!='CRYPTO-FIAT-PAYMENT-v1':raise PaymentError('Incorrect payment file type')
    rec=d['record']
    if rec.get('method') not in METHODS or rec.get('provider')!=METHODS[rec['method']][0]:raise PaymentError('Unknown provider')
    amount_minor(str(Decimal(rec['minor'])/(1 if rec['currency'] in ZERO_DECIMAL else 100)),rec['currency'])
    return rec


def update_payment_file(path,password,rec):
    orig=read_payment_file(path,password)
    for k in ('id','method','provider','environment','currency','minor','provider_id','provider_order_id'):
        if orig[k]!=rec[k]:raise PaymentError('Immutable payment request changed')
    vf.update_password(Path(path),{'format':'CRYPTO-FIAT-PAYMENT-v1','record':rec},password)


def verify_and_save(*args,**kwargs):
    raise PaymentError('Desktop cannot verify financial settlement. Use provider-backed service.')
