"""Funding controls: no false settlement or unapproved onramp injection."""
import unittest
from unittest.mock import patch
from wallet_funding import FundingTarget, validate_payment, target_from_row, provider_homepage

class WalletFundingV25Tests(unittest.TestCase):
    def test_amount_and_fiat_precision(self):
        self.assertEqual(str(validate_payment('45.50','USD')),'45.50')
        self.assertEqual(str(validate_payment('500','JPY')),'500')
        for amount,ccy in [('0','USD'),('-1','USD'),('nan','USD'),('Infinity','USD'),('45.235','USD'),('23.5','JPY'),('1','ZZZ')]:
            with self.subTest(amount=amount,ccy=ccy), self.assertRaises(ValueError):
                validate_payment(amount,ccy)

    def test_token_network_preserved(self):
        row={'coin':'USDT-ETH','address':'0x'+'a'*40,'network':'Ethereum (ERC-20)', 'kind':'Vault public','label':'Vault'}
        target=target_from_row(row)
        self.assertEqual((target.asset,target.network),('USDT-ETH','Ethereum (ERC-20)'))
        self.assertFalse(target.ownership_verified)

    def test_bad_address_rejected(self):
        with self.assertRaises(ValueError):
            target_from_row({'coin':'BTC','address':'seed private key', 'kind':'Vault public'})

    def test_core_verified_flag_not_for_regular_vault(self):
        row={'coin':'BTC','address':'bc1q'+'a'*38,'kind':'Vault public','label':'Vault'}
        self.assertFalse(target_from_row(row).ownership_verified)
        row['kind']='Bitcoin Core verified'
        self.assertTrue(target_from_row(row).ownership_verified)

    def test_external_official_provider_only(self):
        self.assertEqual(provider_homepage('MoonPay — official website'),'https://www.moonpay.com/buy')
        with self.assertRaises(KeyError):provider_homepage('https://bad.example')

    def test_no_private_key_or_money_movement_in_helper(self):
        import inspect, wallet_funding, wallet_funding_ui
        source=inspect.getsource(wallet_funding)+inspect.getsource(wallet_funding_ui)
        self.assertNotIn('sendrawtransaction',source)
        self.assertNotIn('stripe_secret_key',source)
        self.assertIn('NO PAYMENT CONFIRMED',source)
