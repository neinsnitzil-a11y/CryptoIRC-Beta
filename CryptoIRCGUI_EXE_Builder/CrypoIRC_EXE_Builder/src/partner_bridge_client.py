"""Strictly sandbox checkout requests over HTTPS or loopback HTTP only.

No checkout keys are kept in the distributed desktop EXE. The token passed
here is an ephemeral session token for the partner bridge, NOT a provider key.
"""
from __future__ import annotations
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

class BridgeError(ValueError):pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise BridgeError('Redirects from partner checkout service are prohibited')

def _safe_api(url:str):
    parsed=urlsplit(url.strip())
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise BridgeError('Invalid bridge URL')
    if (parsed.scheme=='https' and parsed.hostname and parsed.port is None and
            parsed.hostname==os.environ.get('NOCTURNE_APPROVED_PARTNER_HOST','').lower() and
            parsed.hostname not in ('','localhost')):
        return url.rstrip('/')
    if parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port:
        return url.rstrip('/')
    raise BridgeError('Partner service must use approved HTTPS hostname or local 127.0.0.1 HTTP')

def fetch_sandbox_checkout(api_url:str,session_token:str,asset:str,address:str,fiat:str,amount:str):
    if not isinstance(session_token,str) or len(session_token)<32:
        raise BridgeError('A configured partner-service session token is required')
    url=_safe_api(api_url)+'/v1/sandbox/moonpay/buy'
    data=json.dumps({'asset':asset,'address':address,'fiat':fiat,'amount':str(amount)},
                    separators=(',',':')).encode()
    req=Request(url,method='POST',data=data,headers={
        'Authorization':'Bearer '+session_token,'Content-Type':'application/json',
        'Accept':'application/json'})
    try:
        with build_opener(NoRedirect()).open(req,timeout=15) as resp:
            if resp.status!=200:raise BridgeError('Partner service did not accept request')
            raw=resp.read(8193)
            if len(raw)>8192:raise BridgeError('Partner response too large')
            result=json.loads(raw)
    except (OSError,ValueError,TypeError) as exc:
        raise BridgeError('Partner checkout unavailable or rejected') from None
    if not isinstance(result,dict) or result.get('mode')!='sandbox' or result.get('payment_status')!='NOT_STARTED':
        raise BridgeError('Unexpected partner response; no checkout opened')
    checkout=result.get('checkout_url')
    u=urlsplit(checkout) if isinstance(checkout,str) else None
    if not u or u.scheme!='https' or u.hostname!='buy-sandbox.moonpay.com' or u.username or u.password or u.fragment or u.port:
        raise BridgeError('Untrusted checkout destination')
    if len(checkout)>3000:raise BridgeError('Invalid checkout URL length')
    return checkout
