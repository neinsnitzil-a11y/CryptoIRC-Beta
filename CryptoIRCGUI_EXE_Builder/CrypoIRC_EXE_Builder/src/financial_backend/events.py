"""Illustrative sandbox event adapter, NOT Stripe/PayPal webhook verification.

Real provider webhooks have unique signature formats; this *cannot* verify them.
Do not call this adapter with production provider events. Server tests only.
"""
import hashlib,hmac,json,time
from .ledger import FinanceError, SandboxLedger, canonical

def sign_test_event(secret,body,timestamp):
    raw=canonical(body).encode()
    return hmac.new(secret,(str(timestamp)+'.').encode()+raw,hashlib.sha256).hexdigest()

def handle_test_event(store:SandboxLedger,body,signature,secret,timestamp,now=None):
    now=int(time.time() if now is None else now)
    if not isinstance(timestamp,int) or abs(timestamp-now)>300:
        raise FinanceError('Outside authenticated event time window')
    if len(secret)<32:raise FinanceError('Sandbox verification secret too short')
    expected=sign_test_event(secret,body,timestamp)
    if not hmac.compare_digest(expected,str(signature)):raise FinanceError('Invalid sandbox event signature')
    required={'provider','event_id','intent_id','provider_ref','currency','minor','status'}
    if set(body)!=required:raise FinanceError('Invalid sandbox event fields')
    if not body['provider'].startswith('sandbox-'):raise FinanceError('Only sandbox events supported')
    digest=hashlib.sha256(canonical(body).encode()).hexdigest()
    return store.record_authenticated_event(**body,payload_sha256=digest)
