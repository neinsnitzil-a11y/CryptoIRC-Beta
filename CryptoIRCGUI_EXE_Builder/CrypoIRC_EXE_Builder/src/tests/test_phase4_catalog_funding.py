"""Phase 4 local request safety and 30-coin coverage. No real money used."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
import base64,hashlib,hmac
from asset_capabilities import CAPABILITIES,catalog_stats,EVM_ALIASES
from core.vaultforge import COINS
from core.assets import TOKENS
from wallet_funding import FundingTarget
from funding_orders import FundingOrders, OrderError
from financial_backend.moonpay_partner import signed_sandbox_buy_url, PartnerError

class Phase4CatalogTests(unittest.TestCase):
    def test_exact_thirty_base_plus_twelve_tokens(self):
        self.assertEqual(set(x[0] for x in COINS),{c.code for c in CAPABILITIES.values() if c.category=='Cryptocurrency'})
        self.assertEqual(set(x.code for x in TOKENS),{c.code for c in CAPABILITIES.values() if c.category=='Stablecoin'})
        self.assertEqual(catalog_stats()['base_coins'],30)
        self.assertEqual(catalog_stats()['token_networks'],12)
    def test_address_generation_not_misrepresented_as_signing(self):
        for coin in ('SOL','XRP','TRX','ZEC','DOGE','LTC','SUI','APT','XLM','NEAR'):
            self.assertFalse(CAPABILITIES[coin].can_spend_if_connected,coin)
        for coin in ('BTC','XMR','ETH','ETC','BSC','POLYGON','USDC-BASE'):
            self.assertTrue(CAPABILITIES[coin].can_spend_if_connected,coin)
        self.assertFalse(any(c.mainnet_tested for c in CAPABILITIES.values()))
    def test_only_real_wallet_paths(self):
        self.assertIn('Bitcoin Core',CAPABILITIES['BTC'].sign_method)
        self.assertIn('V3',CAPABILITIES['ETH'].sign_method)
        self.assertIn('RPC',CAPABILITIES['XMR'].sign_method)
        self.assertIn('Address',CAPABILITIES['SOL'].sign_method)

class FundingJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'funding.sqlite3';self.store=FundingOrders(self.db)
        self.target=FundingTarget('ETH','0x'+'a'*40,'ETH','Vault public','testing')
    def create(self,**kw):
        args=dict(flow='BUY',provider='MoonPay — official website',target=self.target,fiat='USD',amount='12.50',idempotency='this-is-idempotent-001')
        args.update(kw)
        return self.store.create(**args)
    def test_order_survives_restart_and_never_paid(self):
        row=self.create();self.assertEqual(row['status'],'REQUESTED')
        self.store.state(row['id'],'PROVIDER_OPENED')
        again=FundingOrders(self.db).list()[0]
        self.assertEqual(again['id'],row['id']);self.assertEqual(again['status'],'PROVIDER_OPENED')
        self.assertEqual(again['amount'],'12.50')
    def test_replay_same_idempotency_only_once(self):
        row=self.create();other=self.create();self.assertEqual(row['id'],other['id'])
        with self.assertRaises(OrderError):self.create(amount='13.50')
        self.assertEqual(len(self.store.list()),1)
    def test_no_payment_status_can_be_self_confirmed(self):
        row=self.create()
        for status in ('PAID','CONFIRMED','SETTLED','ONCHAIN_FINALIZED','DELIVERED'):
            with self.subTest(status=status),self.assertRaises(OrderError):
                self.store.state(row['id'],status)
        self.assertEqual(self.store.list()[0]['status'],'REQUESTED')
    def test_no_cashout_execution(self):
        with self.assertRaises(OrderError):self.create(flow='SELL')
    def test_network_and_precision_rejected(self):
        with self.assertRaises(OrderError):
            self.create(target=FundingTarget('USDT-ETH','0x'+'a'*40,'Tron (TRC-20)','Vault public','testing'))
        with self.assertRaises(ValueError):self.create(amount='8.123')

class PartnerSandboxTests(unittest.TestCase):
    def test_empty_approval_denies_all(self):
        with self.assertRaises(PartnerError):
            signed_sandbox_buy_url(asset='ETH',address='0x'+'a'*40,fiat='USD',amount='13.00',
                publishable_key='pk_test_example',secret_key='sk_test_secret_abc')
    def test_only_server_test_keys_and_explicit_route(self):
        args=dict(asset='ETH',address='0x'+'a'*40,fiat='USD',amount='13.00',
                  publishable_key='pk_test_example',secret_key='sk_test_secret_abc',approved_codes={'ETH':'eth'})
        url=signed_sandbox_buy_url(**args)
        u=urlsplit(url);self.assertEqual(u.hostname,'buy-sandbox.moonpay.com')
        self.assertIn('walletAddress',parse_qs(u.query))
        before='?'+u.query.split('&signature=')[0]
        actual=parse_qs(u.query)['signature'][0]
        expected=base64.b64encode(hmac.new(args['secret_key'].encode(),before.encode(),hashlib.sha256).digest()).decode()
        self.assertEqual(actual,expected)
        with self.assertRaises(PartnerError):signed_sandbox_buy_url(**(args|{'secret_key':'sk_live_secret'}))
        with self.assertRaises(PartnerError):signed_sandbox_buy_url(**(args|{'approved_codes':{'ETH':'btc'}}))
    def test_no_provider_secrets_in_client(self):
        root=Path(__file__).resolve().parents[1]
        text='\n'.join((root/p).read_text() for p in ('phase4_ui.py','funding_orders.py','asset_capabilities.py'))
        self.assertNotIn('secret_key',text)
        self.assertNotIn('whsec_',text)
        self.assertNotIn('sendrawtransaction',text)

if __name__=='__main__':unittest.main()

class PartnerBridgeHttpTests(unittest.TestCase):
    def test_real_local_http_request_returns_only_signed_sandbox_url(self):
        from financial_backend.partner_http import build_handler
        from partner_bridge_client import fetch_sandbox_checkout,BridgeError
        from http.server import ThreadingHTTPServer
        import threading
        tok='test_only_ephemeral_random_token_1234567890'
        cfg={'access_token':tok, 'publishable_key':'pk_test_example',
             'secret_key':'sk_test_secret_abc','approved_codes':{'ETH':'eth'}}
        srv=ThreadingHTTPServer(('127.0.0.1',0),build_handler(cfg))
        t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
        try:
            url=f'http://127.0.0.1:{srv.server_port}'
            out=fetch_sandbox_checkout(url,tok,'ETH','0x'+'b'*40,'USD','50.00')
            self.assertTrue(out.startswith('https://buy-sandbox.moonpay.com/'))
            with self.assertRaises(BridgeError):
                fetch_sandbox_checkout(url,'x'*40,'ETH','0x'+'b'*40,'USD','50.00')
            with self.assertRaises(BridgeError):
                fetch_sandbox_checkout('http://192.168.1.2:1234',tok,'ETH','0x'+'b'*40,'USD','50.00')
        finally:
            srv.shutdown();srv.server_close();t.join(timeout=2)
