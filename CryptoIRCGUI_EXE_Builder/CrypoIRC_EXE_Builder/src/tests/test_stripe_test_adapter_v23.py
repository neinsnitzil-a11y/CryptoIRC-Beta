import unittest
import tempfile
import json
import time
import hmac
import hashlib
from pathlib import Path
from financial_backend.ledger import SandboxLedger, FinanceError
from financial_backend.stripe_test_adapter import verify_stripe_signature,handle_stripe_test_webhook

class StripeSignatureUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=SandboxLedger(Path(self.tmp.name)/'sandbox.sqlite3')
        self.secret='whsec_'+('x'*35)
        self.intent=self.ledger.create_intent(customer_id='test_stripe',provider='sandbox-stripe',
            provider_ref='pi_sandbox_123456789',currency='USD',amount='8.40',
            idempotency_key='stripe_sandbox_key_12345')
        self.stamp=int(time.time())
    def tearDown(self):
        self.ledger.close();self.tmp.cleanup()
    def event(self,*,livemode=False,received=840,event_type='payment_intent.succeeded',status='succeeded'):
        return {'id':'evt_test_1234567','type':event_type,'livemode':livemode,
                'data':{'object':{'id':'pi_sandbox_123456789','object':'payment_intent','livemode':livemode,
                    'currency':'usd','amount_received':received,'amount':840,'status':status,
                    'metadata':{'sandbox_intent_id':self.intent['id']}}}}
    def signed(self,event=None):
        raw=json.dumps(event if event is not None else self.event(),separators=(',',':')).encode()
        signature=hmac.new(self.secret.encode(),str(self.stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return raw,f't={self.stamp},v1={signature}'
    def test_signed_test_mode_event_posts_once(self):
        raw,sig=self.signed()
        handle_stripe_test_webhook(self.ledger,raw,sig,self.secret)
        handle_stripe_test_webhook(self.ledger,raw,sig,self.secret)
        self.assertEqual(self.ledger.customer_balance('test_stripe','USD'),840)
        self.assertEqual(len(self.ledger.db.execute('SELECT * FROM journals').fetchall()),1)
        self.assertFalse(self.ledger.verify_integrity())
    def test_signature_rejects_change_and_wrong_secret(self):
        raw,sig=self.signed()
        with self.assertRaises(FinanceError):verify_stripe_signature(raw+b' ',sig,self.secret)
        with self.assertRaises(FinanceError):verify_stripe_signature(raw,sig,'whsec_'+('z'*35))
    def test_stale_timestamp(self):
        raw,sig=self.signed()
        with self.assertRaises(FinanceError):verify_stripe_signature(raw,sig,self.secret,now=self.stamp+301)
    def test_multiple_v1_allows_rotation(self):
        raw,sig=self.signed()
        result=verify_stripe_signature(raw,sig+',v1='+('0'*64),self.secret)
        self.assertEqual(result['id'],'evt_test_1234567')
    def test_livemode_must_not_credit(self):
        raw,sig=self.signed(self.event(livemode=True))
        with self.assertRaises(FinanceError):handle_stripe_test_webhook(self.ledger,raw,sig,self.secret)
        self.assertEqual(self.ledger.customer_balance('test_stripe','USD'),0)
    def test_amount_mismatch_must_not_credit(self):
        raw,sig=self.signed(self.event(received=839))
        with self.assertRaises(FinanceError):handle_stripe_test_webhook(self.ledger,raw,sig,self.secret)
        self.assertEqual(self.ledger.customer_balance('test_stripe','USD'),0)
    def test_mismatched_intent_rejected(self):
        body=self.event();body['data']['object']['metadata']['sandbox_intent_id']='00000000-0000-0000-0000-000000000000'
        raw,sig=self.signed(body)
        with self.assertRaises(FinanceError):handle_stripe_test_webhook(self.ledger,raw,sig,self.secret)
    def test_unexpected_event_rejected(self):
        raw,sig=self.signed(self.event(event_type='checkout.session.completed'))
        with self.assertRaises(FinanceError):handle_stripe_test_webhook(self.ledger,raw,sig,self.secret)

if __name__=='__main__':unittest.main()
