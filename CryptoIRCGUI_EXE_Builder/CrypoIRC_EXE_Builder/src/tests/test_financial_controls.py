"""Security, accounting and event-path regression tests, never real money."""
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from financial_backend.ledger import SandboxLedger,FinanceError,minor_units
from financial_backend.events import sign_test_event,handle_test_event
from financial_backend.auth import enroll_totp,totp_code,SessionAuth,LoginDenied
from security_gates import release_status

class FinancialCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=SandboxLedger(Path(self.temp.name)/'sandbox.sqlite3')
        self.key=b'sandbox-only-testing-key-material-32-bytes-xxxxxxxxxxx'
        self.a=self.store.create_intent(customer_id='customer_a',provider='sandbox-stripe',
                    provider_ref='provider_reference_a',currency='USD',amount='100.25',
                    idempotency_key='idempotency_key_aaa')
        self.serial=0
    def tearDown(self):self.store.close();self.temp.cleanup()
    def event(self, status='settled', **overrides):
        self.serial+=1
        e={'provider':self.a['provider'],'event_id':f'event_identity_{self.serial}',
           'intent_id':self.a['id'],'provider_ref':self.a['provider_ref'],
           'currency':self.a['currency'],'minor':self.a['amount_minor'],'status':status}
        e.update(overrides)
        return e
    def authenticated(self,e,key=None,when=None):
        when=int(time.time()) if when is None else when
        k=self.key if key is None else key
        return handle_test_event(self.store,e,sign_test_event(k,e,when),self.key,when)
    def test_precision_by_currency(self):
        self.assertEqual(minor_units('1.234','KWD'),1234)
        self.assertEqual(minor_units('100','JPY'),100)
        for amount,code in [('0','USD'),('-3','EUR'),('nan','USD'),('1.234','GBP'),('1.1','JPY'),('1','NOPE')]:
            with self.subTest(amount=amount,code=code),self.assertRaises(FinanceError):minor_units(amount,code)
    def test_idempotency_same_request_one_intent(self):
        copy=self.store.create_intent(customer_id='customer_a',provider='sandbox-stripe',
                    provider_ref='provider_reference_a',currency='USD',amount='100.25',
                    idempotency_key='idempotency_key_aaa')
        self.assertEqual(self.a['id'],copy['id'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0],1)
    def test_idempotency_reused_for_other_amount_rejected(self):
        with self.assertRaises(FinanceError):
            self.store.create_intent(customer_id='customer_a',provider='sandbox-stripe',
                    provider_ref='provider_reference_a',currency='USD',amount='900.25',
                    idempotency_key='idempotency_key_aaa')
    def test_no_provider_ref_reuse(self):
        with self.assertRaises(FinanceError):
            self.store.create_intent(customer_id='customer_b',provider='sandbox-stripe',
                    provider_ref='provider_reference_a',currency='USD',amount='10.25',
                    idempotency_key='idempotency_key_bbb')
    def test_reject_production_providers(self):
        with self.assertRaises(FinanceError):
            self.store.create_intent(customer_id='customer_a',provider='stripe',
                    provider_ref='provider_reference_b',currency='USD',amount='3',
                    idempotency_key='idempotency_key_ccc')
    def test_paid_intent_posts_two_balancing_entries(self):
        self.authenticated(self.event())
        self.assertEqual(self.store.customer_balance('customer_a','USD'),10025)
        self.assertFalse(self.store.verify_integrity())
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM postings').fetchone()[0],2)
    def test_pending_does_not_credit(self):
        self.assertEqual(self.store.customer_balance('customer_a','USD'),0)
        self.assertEqual(self.a['status'],'pending')
    def test_replay_event_no_extra_credit(self):
        e=self.event();self.authenticated(e);self.authenticated(e)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM journals').fetchone()[0],1)
        self.assertEqual(self.store.customer_balance('customer_a','USD'),10025)
    def test_duplicate_id_modified_payload_rejected(self):
        e=self.event();self.authenticated(e)
        wrong={**e,'status':'reversed'}
        with self.assertRaises(FinanceError):self.authenticated(wrong)
    def test_amount_mismatch_no_credit(self):
        with self.assertRaises(FinanceError):self.authenticated(self.event(minor=10026))
        self.assertEqual(self.store.customer_balance('customer_a','USD'),0)
    def test_provider_mismatch_no_credit(self):
        with self.assertRaises(FinanceError):self.authenticated(self.event(provider='sandbox-paypal'))
        self.assertEqual(self.store.customer_balance('customer_a','USD'),0)
    def test_currency_mismatch_no_credit(self):
        with self.assertRaises(FinanceError):self.authenticated(self.event(currency='EUR'))
    def test_signature_or_clock_wrong_rejected(self):
        e=self.event()
        with self.assertRaises(FinanceError):self.authenticated(e,key=b'other-invalid-hmac-key-material-very-long')
        t=int(time.time())-601
        with self.assertRaises(FinanceError):self.authenticated(e,when=t)
    def test_reversal_neutralizes_balance(self):
        self.authenticated(self.event())
        self.authenticated(self.event('reversed'))
        self.assertEqual(self.store.customer_balance('customer_a','USD'),0)
        self.assertFalse(self.store.verify_integrity())
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM journals').fetchone()[0],2)
    def test_failing_intent_not_creditable_later(self):
        self.authenticated(self.event('failed'))
        with self.assertRaises(FinanceError):self.authenticated(self.event('settled'))
        self.assertFalse(self.store.verify_integrity())
    def test_double_reversal_is_idempotent_no_extra_debit(self):
        self.authenticated(self.event())
        self.authenticated(self.event('reversed'))
        self.authenticated(self.event('reversed'))
        self.assertEqual(self.store.customer_balance('customer_a','USD'),0)
        self.assertFalse(self.store.verify_integrity())
    def test_reconciler_identifies_mismatch(self):
        good={'provider_ref':self.a['provider_ref'],'provider':'sandbox-stripe','currency':'USD','minor':10025,'status':'settled'}
        self.assertEqual(self.store.reconcile([good])[0]['error'],'status_mismatch')
        self.authenticated(self.event())
        self.assertEqual(self.store.reconcile([good]),[])
        self.assertEqual(self.store.reconcile([{**good,'minor':10026}])[0]['error'],'amount_currency_or_provider_mismatch')
    def test_audit_tamper_detected(self):
        self.authenticated(self.event())
        self.store.db.execute("UPDATE audit SET detail='{}' WHERE seq=1")
        self.assertTrue(self.store.verify_integrity())
    def test_posting_tamper_detected(self):
        self.authenticated(self.event())
        self.store.db.execute('UPDATE postings SET delta=delta+1 WHERE delta>0')
        self.assertTrue(any('Unbalanced journal' in x for x in self.store.verify_integrity()))
    def test_reopen_database(self):
        self.authenticated(self.event())
        name=self.store.path
        self.store.close();self.store=SandboxLedger(name)
        self.assertEqual(self.store.customer_balance('customer_a','USD'),10025)
        self.assertFalse(self.store.verify_integrity())

class AuthenticationTests(unittest.TestCase):
    def test_mfa_and_session_expiration(self):
        secret=enroll_totp()
        auth=SessionAuth('very-long-strong-password-123',secret)
        epoch=60_000
        token=auth.login('very-long-strong-password-123',totp_code(secret,epoch//30),now=epoch)
        self.assertTrue(auth.check(token,now=epoch+100))
        with self.assertRaises(LoginDenied):auth.check(token,now=epoch+950)
    def test_code_reuse_rejected(self):
        secret=enroll_totp();auth=SessionAuth('very-long-strong-password-123',secret)
        epoch=60_000;code=totp_code(secret,epoch//30)
        auth.login('very-long-strong-password-123',code,now=epoch)
        with self.assertRaises(LoginDenied):auth.login('very-long-strong-password-123',code,now=epoch)
    def test_bruteforce_lockout_and_no_short_password(self):
        with self.assertRaises(ValueError):SessionAuth('weak',enroll_totp())
        auth=SessionAuth('very-long-strong-password-123',enroll_totp())
        for i in range(5):
            with self.assertRaises(LoginDenied):auth.login('wrong','000000',now=60_000)
        with self.assertRaises(LoginDenied):auth.login('very-long-strong-password-123','000000',now=60_000)
    def test_user_logoff_revokes_session(self):
        secret=enroll_totp();auth=SessionAuth('very-long-strong-password-123',secret)
        epoch=60_000
        token=auth.login('very-long-strong-password-123',totp_code(secret,epoch//30),now=epoch)
        auth.logout(token)
        with self.assertRaises(LoginDenied):auth.check(token,now=epoch+1)

class GateTests(unittest.TestCase):
    def test_no_fraudulent_launch_approval(self):
        r=release_status();self.assertFalse(r['production_payments_enabled'])
        self.assertEqual(r['release'],'BLOCKED')
        self.assertFalse(r['financial_balances_authoritative'])

if __name__=='__main__':unittest.main()
