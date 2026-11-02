"""Server-side Stripe TEST MODE webhook verifier (raw bytes, signature v1).

Financial reference integration, not a public HTTP endpoint and never live.
Use Stripe's official SDK in a deployed service after a security review.
It accepts only test-mode payment_intent.succeeded/payment_failed events
and matches an already-existing SANDBOX intent before journal posting.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import time
from .ledger import SandboxLedger, FinanceError


def verify_stripe_signature(raw_body: bytes, header: str, endpoint_secret: str, *, now: int | None = None):
    if not isinstance(raw_body, bytes) or len(raw_body) > 256 * 1024:
        raise FinanceError('Invalid Stripe webhook body')
    if not isinstance(header, str) or len(header) > 2048:
        raise FinanceError('Missing or invalid Stripe signature header')
    if not isinstance(endpoint_secret, str) or not endpoint_secret.startswith('whsec_') or len(endpoint_secret) < 24:
        raise FinanceError('Invalid endpoint signing secret')
    segments = [piece.strip().split('=', 1) for piece in header.split(',')]
    timestamps = [x[1] for x in segments if len(x) == 2 and x[0] == 't']
    signatures = [x[1] for x in segments if len(x) == 2 and x[0] == 'v1']
    if len(timestamps) != 1 or not timestamps[0].isdigit() or not signatures:
        raise FinanceError('Malformed Stripe-Signature header')
    stamped = int(timestamps[0])
    current = int(time.time()) if now is None else int(now)
    if abs(current - stamped) > 300:
        raise FinanceError('Stripe webhook timestamp outside tolerance')
    signed = str(stamped).encode('ascii') + b'.' + raw_body
    expected = hmac.new(endpoint_secret.encode('utf-8'), signed, hashlib.sha256).hexdigest()
    if not any(re.fullmatch('[0-9a-f]{64}', s) and hmac.compare_digest(expected, s) for s in signatures):
        raise FinanceError('Stripe webhook signature verification failed')
    try:
        event = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FinanceError('Invalid signed webhook JSON') from exc
    if not isinstance(event, dict):
        raise FinanceError('Unexpected signed event')
    return event


def handle_stripe_test_webhook(store: SandboxLedger, raw_body: bytes, signature: str,
                               endpoint_secret: str, *, now: int | None = None):
    event = verify_stripe_signature(raw_body, signature, endpoint_secret, now=now)
    if event.get('livemode') is not False:
        raise FinanceError('Live Stripe events are disabled')
    event_type = event.get('type')
    if event_type not in ('payment_intent.succeeded','payment_intent.payment_failed'):
        raise FinanceError('Unsupported Stripe sandbox event type')
    obj = (event.get('data') or {}).get('object')
    if not isinstance(obj, dict) or obj.get('object') != 'payment_intent' or obj.get('livemode') is not False:
        raise FinanceError('Unexpected signed payment object')
    event_id = event.get('id')
    pi_id = obj.get('id')
    intent_id = (obj.get('metadata') or {}).get('sandbox_intent_id')
    if not isinstance(event_id,str) or not re.fullmatch('[a-zA-Z0-9_]{6,128}',event_id):
        raise FinanceError('Invalid event reference')
    if not isinstance(pi_id,str) or not re.fullmatch('[a-zA-Z0-9_]{5,120}',pi_id):
        raise FinanceError('Invalid payment reference')
    if not isinstance(intent_id,str) or not re.fullmatch('[0-9a-f-]{36}',intent_id):
        raise FinanceError('Sandbox payment must explicitly bind to existing intent')
    currency = obj.get('currency')
    if not isinstance(currency,str) or not re.fullmatch('[a-z]{3}',currency):
        raise FinanceError('Invalid event currency')
    status = 'settled' if event_type == 'payment_intent.succeeded' else 'failed'
    if obj.get('status') != ('succeeded' if status == 'settled' else 'requires_payment_method'):
        raise FinanceError('Payment status does not match event type')
    # Amount received may be smaller than requested; never credit the requested
    # amount if a different amount was actually received.
    amount = obj.get('amount_received') if status == 'settled' else obj.get('amount')
    if type(amount) is not int or amount <= 0:
        raise FinanceError('Invalid actual amount received')
    return store.record_authenticated_event(provider='sandbox-stripe', event_id=event_id,
        intent_id=intent_id, provider_ref=pi_id, currency=currency.upper(),
        minor=amount, status=status, payload_sha256=hashlib.sha256(raw_body).hexdigest())
