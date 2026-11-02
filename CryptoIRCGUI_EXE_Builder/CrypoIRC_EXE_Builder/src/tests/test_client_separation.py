"""Desktop money-transport security boundary."""
import inspect
import unittest
from core import fiat_payments as client

class ClientMoneyBoundaryTests(unittest.TestCase):
    def test_no_provider_secrets_or_http_client_in_desktop(self):
        source=inspect.getsource(client)
        for term in ('STRIPE_SECRET_KEY','PAYPAL_CLIENT_SECRET','SQUARE_ACCESS_TOKEN',
                     'REVOLUT_MERCHANT_SECRET','requests.request','/v2/checkout/orders'):
            self.assertNotIn(term,source)
    def test_no_fake_payment_capture(self):
        for op in (client.create_request,client.payment_state,client.capture_paypal,client.verify_and_save):
            with self.assertRaises(client.PaymentError):op()
    def test_desktop_still_tracks_external_unverified_references(self):
        r=client.make_external_request('Cash App Personal (external)','5','USD','test','https://cash.app/')
        self.assertEqual(r['state'],'external-unverified')
    def test_desktop_merchant_configuration_never_claims_configured(self):
        self.assertIn('not available',client.config_status('Stripe Checkout'))
