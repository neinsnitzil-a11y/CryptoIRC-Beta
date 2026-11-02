"""Security invariants and simulated provider replies; NO REAL MONEY sent."""
import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from financial_backend import provider_reference as p

class FiatPaymentTests(unittest.TestCase):
    def setUp(self):
        self.mock_only_environment=patch.dict(os.environ,{'CRYPTO_TEST_LEGACY_PROVIDER_API':'1'})
        self.mock_only_environment.start()
    def tearDown(self):
        self.mock_only_environment.stop()
    def test_real_desktop_provider_api_disabled_by_default(self):
        with patch.dict(os.environ,{'CRYPTO_TEST_LEGACY_PROVIDER_API':''}):
            with self.assertRaises(p.PaymentError):
                p.create_request('Stripe Checkout','10.00','USD','example')

    def test_ten_methods(self):
        self.assertEqual(len(p.METHODS),11)
    def test_external_reference_never_paid(self):
        ext=p.make_external_request('Cash App Personal (external)','8.00','USD','from a friend','https://cash.app/')
        self.assertEqual(ext['state'],'external-unverified')
        with self.assertRaises(p.PaymentError):p.payment_state(ext)
        with self.assertRaises(p.PaymentError):p.make_external_request('Cash App Personal (external)','8.00','USD','test','https://cash.app.evil.org/pay')
    def test_amount_precision(self):
        self.assertEqual(p.amount_minor('12.34','USD'),1234)
        self.assertEqual(p.amount_minor('99','JPY'),99)
        for a,c in [('1.001','USD'),('0','USD'),('-5','EUR'),('NaN','USD'),('Infinity','USD'),('5.20','JPY')]:
            with self.subTest(amount=a,currency=c),self.assertRaises(p.PaymentError):p.amount_minor(a,c)
    def test_safe_checkout_hosts(self):
        self.assertEqual(p.https_url('https://checkout.stripe.com/c/pay/test',{'checkout.stripe.com'}),'https://checkout.stripe.com/c/pay/test')
        for v in ['http://checkout.stripe.com/x','https://checkout.stripe.com.evil.example/x',
                  'https://attacker@checkout.stripe.com/x','https://evil.example/x']:
            with self.subTest(url=v),self.assertRaises(p.PaymentError):p.https_url(v,{'checkout.stripe.com'})
    def test_handoff_cannot_claim_receive(self):
        with self.assertRaises(p.PaymentError):p.create_request('Wise','15','USD','test')
        with self.assertRaises(p.PaymentError):p.create_request('Venmo (PayPal)','15','USD','test')
    def test_stripe_create_and_confirm(self):
        with patch.dict(os.environ,{'STRIPE_SECRET_KEY':'sk_test_TEST'},clear=False),patch.object(p,'request_json') as api:
            api.return_value={'id':'cs_test_123','url':'https://checkout.stripe.com/x'}
            r=p.create_request('Stripe Checkout','10.50','USD','Example','sandbox')
            self.assertEqual(r['state'],'pending')
            self.assertEqual(r['minor'],1050)
            api.assert_called_once()
            api.return_value={'id':'cs_test_123','currency':'usd','amount_total':1050,
                              'client_reference_id':r['id'],'metadata':{'crypto_suite_request_id':r['id']},'payment_status':'paid'}
            self.assertEqual(p.payment_state(r),'paid')
            api.return_value['amount_total']=1051
            with self.assertRaises(p.PaymentError):p.payment_state(r)
    def test_no_live_with_sandbox_key(self):
        with patch.dict(os.environ,{'STRIPE_SECRET_KEY':'sk_test_ABC'},clear=False):
            with self.assertRaises(p.PaymentError):p.create_request('Stripe Checkout','5','USD','x','live')
    def test_paypal_requires_capture(self):
        record={'method':'PayPal Checkout','provider':'PayPal','environment':'sandbox','provider_id':'PAYID',
                'minor':1234,'currency':'USD','id':'request-1'}
        o={'id':'PAYID','status':'APPROVED','purchase_units':[{'custom_id':'request-1','amount':{'currency_code':'USD','value':'12.34'}}]}
        with patch.object(p,'paypal_token',return_value=('https://api-m.sandbox.paypal.com',{})),patch.object(p,'request_json',return_value=o):
            self.assertEqual(p.payment_state(record),'approved')
            o['status']='COMPLETED';o['purchase_units'][0]['payments']={'captures':[{'status':'COMPLETED','amount':{'currency_code':'USD','value':'12.34'}}]}
            self.assertEqual(p.payment_state(record),'paid')
            o['purchase_units'][0]['payments']['captures'][0]['status']='PENDING'
            self.assertEqual(p.payment_state(record),'pending')
    def test_square_order_match(self):
        r={'method':'Square Checkout','provider':'Square','environment':'sandbox','provider_id':'link','provider_order_id':'order-1','minor':600,'currency':'USD','id':'r1'}
        with patch.dict(os.environ,{'SQUARE_ACCESS_TOKEN':'fake'},clear=False),patch.object(p,'request_json',return_value={
            'payments':[{'order_id':'other','status':'COMPLETED','amount_money':{'currency':'USD','amount':600}},
                        {'order_id':'order-1','status':'PENDING','amount_money':{'currency':'USD','amount':600}}]}):
            self.assertEqual(p.payment_state(r),'pending')
        with patch.dict(os.environ,{'SQUARE_ACCESS_TOKEN':'fake'},clear=False),patch.object(p,'request_json',return_value={
            'payments':[{'order_id':'order-1','status':'COMPLETED','amount_money':{'currency':'USD','amount':600}}]}):
            self.assertEqual(p.payment_state(r),'paid')
    def test_record_encryption(self):
        with tempfile.TemporaryDirectory() as td:
            rec={'schema':1,'id':'example','method':'Stripe Checkout','provider':'Stripe','environment':'sandbox',
                'currency':'USD','minor':100,'memo':'Hi','state':'pending','provider_id':'cs_test_1',
                'provider_order_id':'','checkout_url':'https://checkout.stripe.com/x','verified_utc':None}
            path=p.new_payment_file(td,'very-strong-password',rec)
            self.assertNotIn(b'checkout.stripe.com',Path(path).read_bytes())
            self.assertEqual(p.read_payment_file(path,'very-strong-password')['minor'],100)
            with self.assertRaises(Exception):p.read_payment_file(path,'wrong-pass')
            rec['state']='paid';p.update_payment_file(path,'very-strong-password',rec)
            self.assertEqual(p.read_payment_file(path,'very-strong-password')['state'],'paid')
            rec['minor']=200
            with self.assertRaises(p.PaymentError):p.update_payment_file(path,'very-strong-password',rec)
    def test_provider_failure_no_sensitive_response(self):
        class R:
            status_code=401
            text='sk_test_FAKE_PRIVATE_KEY'
        with patch.object(p.requests,'request',return_value=R()):
            with self.assertRaises(p.PaymentError) as ex:p.request_json('GET','https://api.stripe.com','/x')
            self.assertNotIn('PRIVATE_KEY',str(ex.exception))

if __name__=='__main__':unittest.main()
