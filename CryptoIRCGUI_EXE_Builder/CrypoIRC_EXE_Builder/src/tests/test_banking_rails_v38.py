"""Phase 11 test-only gateway and desktop integration acceptance tests."""
from __future__ import annotations
import hashlib,hmac,json,tempfile,time,unittest,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from banking_rails import RailRequests, RailError, SandboxRailsClient, minor_units,printable_amount
from financial_backend.rails_gateway import SandboxRailLedger,GatewayError,make_handler

TOKEN='client-sandbox-token-'+('c'*40)
SECRET='test-event-signing-secret-'+('s'*45)

class TestBankingRails(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local=RailRequests(Path(self.tmp.name)/'local.sqlite3')
        self.server=SandboxRailLedger(Path(self.tmp.name)/'server.sqlite3')
    def _local(self,flow='DEPOSIT',amount='50.25',currency='USD',key='pay-test-aaaaaaaa'):
        return self.local.create(flow=flow,currency=currency,amount=amount,label='Personal account',key=key)
    def _register(self,rec):
        return self.server.create({k:rec[k] for k in ('id','flow','currency','minor','label')})
    def _event(self,rec,event_type='test.deposit.settled',event_id='event_00001',amount=None,provider_ref='provider_123456',stamp=None):
        body={'event_id':event_id,'intent_id':rec['id'],'type':event_type,'currency':rec['currency'],
              'minor':rec['minor'] if amount is None else amount,'provider_ref':provider_ref,'environment':'sandbox'}
        raw=json.dumps(body,separators=(',',':')).encode()
        stamp=int(time.time()) if stamp is None else stamp
        sig=hmac.new(SECRET.encode(),str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return raw,f't={stamp},v1={sig}'
    def test_money_minor_precision(self):
        self.assertEqual(minor_units('0.01','USD'),1)
        self.assertEqual(minor_units('500','JPY'),500)
        self.assertEqual(printable_amount(1025,'USD'),'10.25')
        for amount in ('1.001','-5','NaN','Infinity','0','1e99','0.000000001'):
            with self.subTest(amount=amount),self.assertRaises(RailError):minor_units(amount,'USD')
        with self.assertRaises(RailError):minor_units('1.5','JPY')
    def test_no_bank_numbers_or_card_fields(self):
        with self.assertRaises(RailError):self.local.create(flow='DEPOSIT',currency='USD',amount='2',label='123456789')
        self.assertNotIn('routing',str(self._local()).lower())
        self.assertNotIn('account_number',str(self._local()).lower())
    def test_idempotency_across_restart(self):
        a=self._local();b=self._local()
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(RailRequests(Path(self.tmp.name)/'local.sqlite3').get(a['id'])['minor'],5025)
        with self.assertRaises(RailError):self._local(amount='3')
    def test_desktop_cannot_verify_settlement(self):
        a=self._local()
        for status in ('SETTLED','PAID','TEST_SETTLED','COMPLETED','CONFIRMED'):
            with self.subTest(status=status),self.assertRaises(RailError):self.local.state(a['id'],status)
        self.assertEqual(self.local.get(a['id'])['status'],'DRAFT')
    def test_gateway_immutable_intent(self):
        rec=self._local();a=self._register(rec);b=self._register(rec)
        self.assertEqual(a,b)
        with self.assertRaises(GatewayError):self.server.create({**{k:rec[k] for k in ('id','flow','currency','minor','label')},'minor':100})
    def test_signed_event_replay(self):
        rec=self._local();self._register(rec)
        raw,header=self._event(rec)
        first=self.server.accept_event(raw,header,SECRET)
        second=self.server.accept_event(raw,header,SECRET)
        self.assertEqual(first,second);self.assertEqual(first['state'],'TEST_SETTLED')
        self.assertIs(first['real_funds_transferred'],False)
        self.assertEqual(self.local.get(rec['id'])['status'],'DRAFT')
        restarted=SandboxRailLedger(Path(self.tmp.name)/'server.sqlite3')
        self.assertEqual(restarted.get(rec['id'])['state'],'TEST_SETTLED')
        with self.assertRaises(GatewayError):self.server.accept_event(*self._event(rec,event_type='test.payment.failed'),SECRET)
    def test_malformed_tampered_and_stale_signatures(self):
        rec=self._local();self._register(rec)
        raw,header=self._event(rec)
        with self.assertRaises(GatewayError):self.server.accept_event(raw.replace(b'5025',b'9025'),header,SECRET)
        with self.assertRaises(GatewayError):self.server.accept_event(raw,header,'wrong-secret-'+('q'*40))
        raw,header=self._event(rec,stamp=int(time.time())-800)
        with self.assertRaises(GatewayError):self.server.accept_event(raw,header,SECRET)
    def test_wrong_amount_rejected(self):
        rec=self._local();self._register(rec)
        raw,header=self._event(rec,amount=5024)
        with self.assertRaises(GatewayError):self.server.accept_event(raw,header,SECRET)
        self.assertEqual(self.server.get(rec['id'])['state'],'TEST_PENDING')
    def test_payout_event_requires_withdrawal(self):
        rec=self._local();self._register(rec)
        raw,header=self._event(rec,event_type='test.withdrawal.paid')
        with self.assertRaises(GatewayError):self.server.accept_event(raw,header,SECRET)
        withdrawal=self._local(flow='WITHDRAWAL',key='pay-test-bbbbbbbb')
        self._register(withdrawal)
        raw,header=self._event(withdrawal,'test.withdrawal.paid','event_00002')
        self.assertEqual(self.server.accept_event(raw,header,SECRET)['state'],'TEST_PAID')
    def test_returns_and_terminal_rejection(self):
        rec=self._local();self._register(rec)
        raw,header=self._event(rec)
        self.server.accept_event(raw,header,SECRET)
        raw,header=self._event(rec,'test.payment.returned','event_00002')
        self.assertEqual(self.server.accept_event(raw,header,SECRET)['state'],'TEST_RETURNED')
        raw,header=self._event(rec,'test.payment.processing','event_00003')
        with self.assertRaises(GatewayError):self.server.accept_event(raw,header,SECRET)
    def test_unauthorized_remote_gateway_prohibited(self):
        with self.assertRaises(RailError):SandboxRailsClient('http://evil.example:1234',TOKEN)
        with self.assertRaises(RailError):SandboxRailsClient('https://example.com',TOKEN)
        with self.assertRaises(RailError):SandboxRailsClient('http://127.0.0.1:18450','short')
    def test_actual_loopback_http_contract(self):
        svc=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.server,TOKEN,SECRET))
        t=threading.Thread(target=svc.serve_forever,kwargs={'poll_interval':.05},daemon=True);t.start()
        self.addCleanup(svc.server_close);self.addCleanup(svc.shutdown)
        client=SandboxRailsClient(f'http://127.0.0.1:{svc.server_address[1]}',TOKEN)
        rec=self._local()
        result=client.create(rec)
        self.assertEqual(result['state'],'TEST_PENDING')
        self.assertEqual(client.status(rec['id'])['id'],rec['id'])
        with self.assertRaises(RailError):SandboxRailsClient(f'http://127.0.0.1:{svc.server_address[1]}','bad'*15).status(rec['id'])

if __name__=='__main__':unittest.main()

class TestStripeVerifiedRails(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger=SandboxRailLedger(Path(self.tmp.name)/'backend.sqlite3')
        self.request={'id':'test_request_00000001','flow':'DEPOSIT','currency':'USD',
                      'minor':1000,'label':'My bank'}
        self.ledger.create(self.request)
        self.whsec='whsec_'+'k'*45
    def event(self,*,kind='payment_intent.succeeded',amount_received=1000,livemode=False):
        statuses={'payment_intent.succeeded':'succeeded',
            'payment_intent.processing':'processing',
            'payment_intent.payment_failed':'requires_payment_method'}
        evt={'id':'evt_test_0000000001','livemode':livemode,'type':kind,
            'data':{'object':{'id':'pi_test_000000001','object':'payment_intent',
                'livemode':livemode,'currency':'usd','amount':1000,
                'amount_received':amount_received,'status':statuses[kind],
                'metadata':{'nocturne_rail_intent_id':self.request['id']}}}}
        raw=json.dumps(evt).encode()
        stamp=int(time.time())
        mac=hmac.new(self.whsec.encode(),str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return raw,f't={stamp},v1={mac}'
    def test_verified_stripe_sandbox_event(self):
        self.assertEqual(self.ledger.accept_stripe_test_event(*self.event(),self.whsec,SECRET)['state'],'TEST_SETTLED')
    def test_stripe_invalid_sig_and_live_mode(self):
        raw,sig=self.event()
        with self.assertRaises(GatewayError):self.ledger.accept_stripe_test_event(raw,sig,'whsec_'+'z'*45,SECRET)
        raw,sig=self.event(livemode=True)
        with self.assertRaises(GatewayError):self.ledger.accept_stripe_test_event(raw,sig,self.whsec,SECRET)
    def test_stripe_partial_payment_not_settled(self):
        with self.assertRaises(GatewayError):self.ledger.accept_stripe_test_event(*self.event(amount_received=500),self.whsec,SECRET)
        self.assertEqual(self.ledger.get(self.request['id'])['state'],'TEST_PENDING')
