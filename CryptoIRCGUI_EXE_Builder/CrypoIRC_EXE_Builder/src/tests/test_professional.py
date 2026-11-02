"""Validate hard boundaries between cryptographic wallets and fiat bookkeeping."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from professional_ui import validate_storage_folder, validated_wallet_parameters, FIAT_PROVIDERS
from core import fiat_ledger
from core.assets import ASSETS


class AccountBoundaryTests(unittest.TestCase):
    def test_fiat_cannot_enter_seed_generation(self):
        with self.assertRaises(ValueError):
            validated_wallet_parameters('Fiat ledger','BTC','1','24','0',False)
    def test_assets_must_match_category(self):
        with self.assertRaises(ValueError):
            validated_wallet_parameters('Cryptocurrency','USDT-ETH','1','24','0',False)
        with self.assertRaises(ValueError):
            validated_wallet_parameters('Stablecoin','BTC','1','24','0',False)
    def test_native_crypto_selection(self):
        self.assertEqual(validated_wallet_parameters('Cryptocurrency','BTC','2','24','1',False),(2,24,1))
    def test_native_monero_no_generic_fiat(self):
        self.assertEqual(ASSETS['XMR'].base_coin,'XMR')
    def test_stablecoin_chain_mapping(self):
        self.assertEqual(ASSETS['USDT-ETH'].base_coin,'ETH')
        self.assertEqual(ASSETS['USDT-TRX'].base_coin,'TRX')
    def test_recovery_only_one_copy(self):
        with self.assertRaises(ValueError):
            validated_wallet_parameters('Cryptocurrency','BTC','2','24','0',True)
    def test_no_unsafe_wallet_counts_or_seed_size(self):
        for count,words in [('0','24'),('21','24'),('1','17')]:
            with self.assertRaises(ValueError):
                validated_wallet_parameters('Cryptocurrency','BTC',count,words,'0',False)
    def test_usb_storage_restricted_to_mount(self):
        with tempfile.TemporaryDirectory() as root:
            usb=Path(root)/'usb';usb.mkdir()
            destination=usb/'Wallets'
            self.assertEqual(validate_storage_folder('USB / external drive',str(destination),str(usb)),destination)
            with self.assertRaises(ValueError):
                validate_storage_folder('USB / external drive',str(Path(root)/'other'),str(usb))
            with self.assertRaises(ValueError):
                validate_storage_folder('USB / external drive',str(destination),'')
    def test_fiat_directory_stays_independent(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(validate_storage_folder('Custom directory',root),Path(root))
    def test_no_fake_provider_accounts(self):
        self.assertIsNone(FIAT_PROVIDERS['Offline encrypted ledger (manual records)'])
        self.assertTrue(FIAT_PROVIDERS['PayPal (existing PayPal account)'].startswith('https://'))
    def test_fiat_encrypted_ledger_not_seeded(self):
        with tempfile.TemporaryDirectory() as root:
            p=fiat_ledger.new(root,'USD','Test cash ledger','strong passphrase greater than 14')
            blob=Path(p).read_bytes()
            self.assertNotIn(b'Test cash ledger',blob)
            result=fiat_ledger.read(p,'strong passphrase greater than 14')
            self.assertEqual(result['currency'],'USD')
            self.assertNotIn('mnemonic',result)
            self.assertNotIn('private_key',result)
            self.assertIn('bookkeeping',result['notice'].lower())

if __name__=='__main__':unittest.main()
