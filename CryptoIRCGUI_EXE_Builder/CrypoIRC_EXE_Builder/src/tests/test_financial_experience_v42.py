"""Phase 15: never infer real funds, signing authority, or a provider settlement."""
import unittest
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from financial_experience import capabilities, observation_display, matching_history, selected_funding_target
from portfolio_engine import Observation, wallet_identity
from unified_wallet import account_from_record

class MoneyHubPolicyTests(unittest.TestCase):
    @staticmethod
    def account(kind,asset,network,address='1ExamplePublicAddress',source='wallet'):
        if kind=='evm_keystore':address='0x'+'2'*40
        if kind=='vault':source='test.vault'
        return account_from_record(dict(kind=kind,asset=asset,network=network,address=address,
                         source=source,label='Account'))
    def test_watch_only_never_eligible_to_send_or_fund(self):
        a=self.account('watch_only','BTC','main')
        p=capabilities(a,fresh=True,observed=True)
        self.assertTrue(p.receive)
        self.assertIsNone(p.send_page)
        self.assertFalse(p.buy_route)
    def test_bitcoin_test_network_never_cash_funded(self):
        a=self.account('btc_core','BTC','regtest')
        self.assertFalse(capabilities(a,fresh=True,observed=True).buy_route)
    def test_core_mainnet_requires_a_fresh_rpc_observation(self):
        a=self.account('btc_core','BTC','main')
        self.assertFalse(capabilities(a).buy_route)
        self.assertTrue(capabilities(a,fresh=True,observed=True).buy_route)
        self.assertEqual(capabilities(a).send_page,'BTC Phase 1')
    def test_encrypted_evm_keystore_requires_separate_recovery(self):
        a=self.account('evm_keystore','ETH','ETH')
        self.assertFalse(capabilities(a,fresh=True,observed=True).buy_route)
        self.assertEqual(capabilities(a).send_page,'EVM Phase 2')
    def test_vault_unverified_even_with_observation(self):
        a=self.account('vault','BTC','BTC')
        p=capabilities(a,fresh=True,observed=True)
        self.assertIsNone(p.send_page)
        self.assertFalse(p.buy_route)
    def test_invalid_reference_has_no_actions(self):
        p=capabilities(SimpleNamespace(asset='',network='',address='',kind='btc_core'))
        self.assertFalse(p.receive)
        self.assertIsNone(p.send_page)
    def test_observation_is_identity_bound(self):
        a=self.account('btc_core','BTC','main')
        b=self.account('btc_core','BTC','main',source='another-wallet')
        obs=Observation(wallet_identity(a),'BTC','main',Decimal('1.00000000'),Decimal('0.9'),100.,'500','Core','pending')
        self.assertEqual(observation_display(a,obs,now=101)['pending'],'0.10000000')
        with self.assertRaises(ValueError):observation_display(b,obs,now=101)
    def test_old_or_unknown_observations_never_become_zero(self):
        a=self.account('btc_core','BTC','main')
        self.assertEqual(observation_display(a,None)['total'],'—')
        obs=Observation(wallet_identity(a),'BTC','main',Decimal('10'),Decimal('9'),100.,'5','Core','pending')
        display=observation_display(a,obs,now=200)
        self.assertEqual(display['status'],'STALE')
        self.assertEqual(display['available'],'—')
    def test_no_cross_network_observation(self):
        a=self.account('btc_core','BTC','main')
        obs=Observation(wallet_identity(a),'BTC','regtest',Decimal('1'),Decimal('1'),100.,'5','Core','')
        with self.assertRaises(ValueError):observation_display(a,obs,now=101)
    def test_impossible_available_is_rejected(self):
        a=self.account('btc_core','BTC','main')
        obs=Observation(wallet_identity(a),'BTC','main',Decimal('1'),Decimal('2'),100.,'5','Core','')
        with self.assertRaises(ValueError):observation_display(a,obs,now=101)
    def test_local_history_is_read_only_filtered(self):
        a=self.account('btc_core','BTC','main')
        rows=[{'chain':'BTC','network':'regtest','source':'wallet'},
              {'chain':'BTC','network':'main','source':'another-wallet'},
              {'chain':'BTC','network':'main','source':'wallet','status':'UNKNOWN'}]
        self.assertEqual(matching_history(rows,a),[rows[2]])
    def test_funding_target_is_public_only(self):
        a=self.account('btc_core','BTC','main')
        t=selected_funding_target(a)
        self.assertEqual(t.address,a.address)
        self.assertTrue(t.ownership_verified)
        with self.assertRaises(ValueError):selected_funding_target(self.account('watch_only','BTC','main'))

if __name__=='__main__':unittest.main()
