"""SERVER-SIDE ONLY REFERENCE for sandbox merchant-provider requests.

NO PRODUCTION AUTHORIZATION. Intended for separately deployed, audited backend.

Fiat payment requests via real provider endpoints, with strict status matching.

No bank-account creation, peer-to-peer auto-send, stored API secrets or assumed settlement.
A hosted checkout request is not proof of payment. Start sandbox-only for new accounts.
"""
from __future__ import annotations
import os, json, secrets, re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse
import requests
from core import vaultforge as vf
from core.assets import FIAT

class PaymentError(ValueError): pass

def _require_isolated_provider_service():
    """Stop direct merchant-secret operations in distributed desktop clients.

    The optional test override is ignored in frozen executables, and should be
    used ONLY in offline tests that mock provider requests. In production, deploy
    a separately authenticated payment service using provider-native webhooks.
    """
    import sys
    if getattr(sys,'frozen',False) or os.environ.get('CRYPTO_TEST_LEGACY_PROVIDER_API')!='1':
        raise PaymentError('Direct merchant API operations disabled in desktop. Use an approved secure provider backend.')


METHODS = {
 'Stripe Checkout': ('Stripe', 'API receive / provider verification'),
 'PayPal Checkout': ('PayPal', 'API receive / capture / verify'),
 'Square Checkout': ('Square', 'API receive / provider verification'),
 'Cash App Pay (Square)': ('Square', 'Square hosted checkout; seller/buyer eligibility'),
 'Cash App Personal (external)': ('Cash App', 'Personal $Cashtag payment link / external provider; not API-verifiable'),
 'Venmo (PayPal)': ('PayPal', 'Eligible US/USD mobile PayPal checkout; not guaranteed'),
 'Wise': ('Wise', 'External provider handoff; no unapproved API transfers'),
 'Revolut Merchant': ('Revolut', 'API receive / provider verification'),
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
 'Stripe Checkout':'Set STRIPE_SECRET_KEY (sk_test_ for sandbox) in process environment.',
 'PayPal Checkout':'Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (matching mode).',
 'Square Checkout':'Set SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID.',
 'Cash App Pay (Square)':'Set Square credentials; Cash App option depends on seller dashboard, buyer and region.',
 'Cash App Personal (external)':'Use an existing Cash App $Cashtag link created by Cash App. No API verification or payout control.',
 'Venmo (PayPal)':'PayPal order only; Venmo display requires eligible US/USD checkout (not guaranteed by this desktop application).',
 'Revolut Merchant':'Set REVOLUT_MERCHANT_SECRET (approved merchant account).',
 'Wise':'Complete the transfer/FX inside your own authenticated Wise account.',
 'Zelle (your bank)':'Complete directly in an enrolled participating bank application.',
 'ACH bank transfer':'Complete ACH using your bank; independently verify beneficiary details.',
 'Bank wire / SWIFT':'Complete in your bank portal; independently verify recipient and fees.',
}
# Provider request coverage is deliberately narrower than the 164-currency reference/ledger catalog.
CURRENCIES={'USD','EUR','GBP','CAD','AUD','JPY','CHF','NZD','SGD','HKD','INR','MXN','BRL','ZAR','AED','KRW'}
ZERO_DECIMAL={'JPY','KRW'}
ENV_KEYS={'Stripe':'STRIPE_SECRET_KEY','PayPal':'PAYPAL_CLIENT_ID', 'Square':'SQUARE_ACCESS_TOKEN','Revolut':'REVOLUT_MERCHANT_SECRET'}


def amount_minor(amount: str, currency: str) -> int:
    if currency not in CURRENCIES: raise PaymentError('Unsupported currency')
    try: d=Decimal(amount)
    except (InvalidOperation, ValueError, TypeError): raise PaymentError('Invalid decimal amount')
    precision=0 if currency in ZERO_DECIMAL else 2
    if not d.is_finite() or not Decimal('0')<d<=Decimal('100000000'):
        raise PaymentError('Amount must be positive and finite (limit 100 million)')
    scale=Decimal(10)**precision
    if d*scale != (d*scale).to_integral_value():raise PaymentError('Too many decimals for selected currency')
    return int(d*scale)


def https_url(url:str, hosts:set[str]) -> str:
    if not isinstance(url,str): raise PaymentError('Provider returned an invalid checkout URL')
    try:p=urlparse(url)
    except ValueError:raise PaymentError('Invalid URL')
    if p.scheme!='https' or p.hostname not in hosts or p.username or p.password or not p.netloc:
        raise PaymentError('Untrusted checkout host. Do not open this link.')
    return url


def request_json(method, base, endpoint, headers=None, data=None, auth=None, form=False, params=None):
    # Caller always supplies constant provider hosts and constant endpoint prefixes.
    try:
        r=requests.request(method,base+endpoint,headers=headers,auth=auth,
                   data=data if form else None,json=None if form else data,
                   params=params,timeout=(7,25),allow_redirects=False)
    except requests.RequestException:raise PaymentError('Provider connection failed. Check network and credentials.') from None
    if r.status_code>=400:raise PaymentError(f'Provider rejected request (HTTP {r.status_code}). Check account eligibility, API keys and currency.')
    if r.status_code<200 or r.status_code>=300:raise PaymentError(f'Unexpected provider response HTTP {r.status_code}')
    try:out=r.json()
    except ValueError:raise PaymentError('Provider returned invalid JSON') from None
    if not isinstance(out,dict):raise PaymentError('Unexpected provider payload')
    return out


def config_status(method:str):
    if os.environ.get('CRYPTO_TEST_LEGACY_PROVIDER_API')!='1':
        return 'Desktop API disabled — use approved server-side provider connection'
    provider=METHODS[method][0]
    key=ENV_KEYS.get(provider)
    if not key:return 'External provider — no API credential needed'
    ok=bool(os.environ.get(key,''))
    if provider=='PayPal':ok =ok and bool(os.environ.get('PAYPAL_CLIENT_SECRET'))
    if provider=='Square':ok=ok and bool(os.environ.get('SQUARE_LOCATION_ID'))
    return 'Configured via environment (not connection-tested)' if ok else 'Not configured — use provider API keys'


def paypal_token(mode):
    client=os.environ.get('PAYPAL_CLIENT_ID','')
    secret=os.environ.get('PAYPAL_CLIENT_SECRET','')
    if not client or not secret:raise PaymentError('Missing PayPal client ID/secret')
    base='https://api-m.sandbox.paypal.com' if mode=='sandbox' else 'https://api-m.paypal.com'
    out=request_json('POST',base,'/v1/oauth2/token',auth=(client,secret),
                     headers={'Accept':'application/json'},data={'grant_type':'client_credentials'},form=True)
    token=out.get('access_token')
    if not token:raise PaymentError('PayPal did not grant an access token')
    return base,{'Authorization':'Bearer '+token, 'Content-Type':'application/json'}


def create_request(method:str,amount:str,currency:str,memo:str,mode:str='sandbox') -> dict:
    _require_isolated_provider_service()
    if method not in METHODS:raise PaymentError('Unknown payment method')
    if mode not in ('sandbox','live'):raise PaymentError('Unsupported mode')
    cents=amount_minor(amount,currency)
    if len(memo)>100:raise PaymentError('Memo must be at most 100 characters')
    if method.startswith('Venmo') and currency!='USD':raise PaymentError('Venmo merchant checkout requires USD')
    if method in HANDOFF_URLS or method.startswith('Venmo'):
        raise PaymentError('This method is an external account/checkout workflow. Use Open Provider; no fake payment link will be created.')
    ident=secrets.token_hex(16)
    provider=METHODS[method][0]
    rec={'schema':1,'id':ident,'method':method,'provider':provider,'environment':mode,
         'currency':currency,'minor':cents,'memo':memo.strip(),
         'created_utc':datetime.now(timezone.utc).isoformat(),
         'state':'pending','verified_utc':None,'provider_id':'','checkout_url':'', 'provider_order_id':''}
    if provider=='Stripe':
        key=os.environ.get('STRIPE_SECRET_KEY','')
        if not key or (mode=='sandbox' and not key.startswith('sk_test_')) or (mode=='live' and not key.startswith('sk_live_')):
            raise PaymentError('Stripe secret missing or not appropriate for the chosen environment')
        body={'mode':'payment','success_url':'https://stripe.com/','cancel_url':'https://stripe.com/',
              'line_items[0][price_data][currency]':currency.lower(),
              'line_items[0][price_data][unit_amount]':str(cents),
              'line_items[0][price_data][product_data][name]':memo.strip() or 'Payment request',
              'line_items[0][quantity]':'1','metadata[crypto_suite_request_id]':ident,
              'client_reference_id':ident}
        result=request_json('POST','https://api.stripe.com','/v1/checkout/sessions',
                       {'Authorization':'Bearer '+key,'Idempotency-Key':ident},body,form=True)
        rec['provider_id']=result.get('id','')
        rec['checkout_url']=https_url(result.get('url',''),{'checkout.stripe.com'})
    elif provider=='PayPal':
        base,headers=paypal_token(mode)
        headers['PayPal-Request-Id']=ident
        result=request_json('POST',base,'/v2/checkout/orders',headers,{
            'intent':'CAPTURE','purchase_units':[{'custom_id':ident,'amount':{'currency_code':currency,'value':str(Decimal(cents)/(1 if currency in ZERO_DECIMAL else 100))}}],
            'payment_source':{'paypal':{'experience_context':{'return_url':'https://www.paypal.com/','cancel_url':'https://www.paypal.com/'}}}})
        rec['provider_id']=result.get('id','')
        links=result.get('links',[])
        approve=next((a.get('href') for a in links if a.get('rel') in ('payer-action','approve')),None)
        rec['checkout_url']=https_url(approve,{'www.paypal.com','www.sandbox.paypal.com','sandbox.paypal.com'})
    elif provider=='Square':
        token=os.environ.get('SQUARE_ACCESS_TOKEN','');location=os.environ.get('SQUARE_LOCATION_ID','')
        if not token or not location:raise PaymentError('Missing Square token or location ID')
        base='https://connect.squareupsandbox.com' if mode=='sandbox' else 'https://connect.squareup.com'
        result=request_json('POST',base,'/v2/online-checkout/payment-links',{
            'Square-Version':'2026-09-16','Authorization':'Bearer '+token,'Content-Type':'application/json'},
            {'idempotency_key':ident,'description':memo[:80],
             'quick_pay':{'name':memo.strip() or 'Payment request','price_money':{'amount':cents,'currency':currency},'location_id':location}})
        link=result.get('payment_link',{})
        rec['provider_id']=link.get('id','')
        rec['provider_order_id']=link.get('order_id','')
        rec['checkout_url']=https_url(link.get('url',''),{'square.link','checkout.square.site'})
    elif provider=='Revolut':
        key=os.environ.get('REVOLUT_MERCHANT_SECRET','')
        if not key:raise PaymentError('Missing Revolut Merchant API secret')
        base='https://sandbox-merchant.revolut.com' if mode=='sandbox' else 'https://merchant.revolut.com'
        result=request_json('POST',base,'/api/orders',{
            'Authorization':'Bearer '+key,'Revolut-Api-Version':'2026-08-17','Content-Type':'application/json'},
            {'amount':cents,'currency':currency,'description':memo.strip() or 'Payment request'})
        rec['provider_id']=result.get('id','')
        # Domain list is deliberately strict; review Revolut changes before widening.
        rec['checkout_url']=https_url(result.get('checkout_url',''),{
            'checkout.revolut.com','pay.revolut.com','merchant.revolut.com','sandbox-merchant.revolut.com'})
    if not rec['provider_id'] or not re.fullmatch(r'[A-Za-z0-9_-]{3,160}',rec['provider_id']):
        raise PaymentError('Provider returned an invalid order identifier')
    if provider=='Square' and not re.fullmatch(r'[A-Za-z0-9_-]{3,160}',rec.get('provider_order_id','')):
        raise PaymentError('Square did not return a valid order identifier')
    return rec


def payment_state(rec:dict) -> str:
    _require_isolated_provider_service()
    """Returns paid / pending / approved; never guesses based on a submitted URL or user reference."""
    if rec.get('environment')=='external':
        raise PaymentError('External transfers cannot be verified through this app. Check the official provider or bank statement.')
    method=rec['method']; provider=rec['provider'];mode=rec['environment']; pid=rec['provider_id']
    expected=rec['minor']; currency=rec['currency']
    if not isinstance(pid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,160}',pid):
        raise PaymentError('Untrusted provider order ID')
    if provider=='Square' and not re.fullmatch(r'[A-Za-z0-9_-]{3,160}',rec.get('provider_order_id','')):
        raise PaymentError('Invalid Square order ID')
    if provider=='Stripe':
        key=os.environ.get('STRIPE_SECRET_KEY','')
        if not key:raise PaymentError('Missing Stripe key')
        o=request_json('GET','https://api.stripe.com','/v1/checkout/sessions/'+pid,{'Authorization':'Bearer '+key})
        if o.get('id')!=pid or o.get('client_reference_id')!=rec['id'] or o.get('metadata',{}).get('crypto_suite_request_id')!=rec['id']:
            raise PaymentError('Provider response does not match payment request')
        if o.get('amount_total')!=expected or str(o.get('currency','')).upper()!=currency:
            raise PaymentError('Provider amount or currency mismatch')
        return 'paid' if o.get('payment_status')=='paid' else 'pending'
    if provider=='PayPal':
        base,h=paypal_token(mode)
        o=request_json('GET',base,'/v2/checkout/orders/'+pid,h)
        if o.get('id')!=pid:raise PaymentError('PayPal order ID mismatch')
        units=o.get('purchase_units',[])
        if len(units)!=1 or units[0].get('custom_id')!=rec['id']:
            raise PaymentError('PayPal custom reference mismatch')
        am=units[0].get('amount',{})
        if am.get('currency_code')!=currency or amount_minor(am.get('value',''),currency)!=expected:
            raise PaymentError('PayPal amount mismatch')
        if o.get('status')=='COMPLETED':
            captures=units[0].get('payments',{}).get('captures',[])
            return 'paid' if any(c.get('status')=='COMPLETED' and c.get('amount',{}).get('currency_code')==currency and amount_minor(c['amount'].get('value',''),currency)==expected for c in captures) else 'pending'
        return 'approved' if o.get('status')=='APPROVED' else 'pending'
    if provider=='Square':
        token=os.environ.get('SQUARE_ACCESS_TOKEN','')
        if not token:raise PaymentError('Missing Square token')
        base='https://connect.squareupsandbox.com' if mode=='sandbox' else 'https://connect.squareup.com'
        headers={'Square-Version':'2026-09-16','Authorization':'Bearer '+token}
        orderid=rec.get('provider_order_id','')
        if not orderid:raise PaymentError('Missing Square order identifier')
        # Square payment listing is eventually consistent. Never assume an order means paid.
        params={'limit':100};matching=0
        for _ in range(5):
            o=request_json('GET',base,'/v2/payments',headers,params=params)
            for p in o.get('payments',[]):
                amt=p.get('amount_money',{})
                if p.get('order_id')==orderid and p.get('status')=='COMPLETED' and amt.get('currency')==currency:
                    matching+=int(amt.get('amount',0))
            cursor=o.get('cursor')
            if not cursor:break
            params={'limit':100,'cursor':cursor}
        return 'paid' if matching==expected else 'pending'
    if provider=='Revolut':
        key=os.environ.get('REVOLUT_MERCHANT_SECRET','')
        if not key:raise PaymentError('Missing Revolut secret')
        base='https://sandbox-merchant.revolut.com' if mode=='sandbox' else 'https://merchant.revolut.com'
        o=request_json('GET',base,'/api/orders/'+pid,{'Authorization':'Bearer '+key,'Revolut-Api-Version':'2026-08-17'})
        if o.get('id')!=pid or o.get('amount')!=expected or o.get('currency')!=currency:raise PaymentError('Revolut order mismatch')
        return 'paid' if str(o.get('state','')).lower()=='completed' else 'pending'
    raise PaymentError('Cannot verify this external handoff automatically')


def capture_paypal(rec:dict):
    _require_isolated_provider_service()
    """Merchant explicitly captures an APPROVED order; caller must obtain confirmation."""
    if rec.get('provider')!='PayPal':raise PaymentError('Not a PayPal order')
    if payment_state(rec)!='approved':raise PaymentError('Order must be approved before capture')
    base,headers=paypal_token(rec['environment'])
    headers['PayPal-Request-Id']=rec['id']+'-capture'
    request_json('POST',base,'/v2/checkout/orders/'+rec['provider_id']+'/capture',headers,{})
    return payment_state(rec)



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


def verify_and_save(path,password):
    rec=read_payment_file(path,password)
    state=payment_state(rec)
    rec['state']=state
    if state=='paid' and not rec['verified_utc']:
        rec['verified_utc']=datetime.now(timezone.utc).isoformat()
    update_payment_file(path,password,rec)
    return rec
