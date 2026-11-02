import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
from core.assets import ASSETS, FIAT, TOKENS
from core import fiat_ledger, fiat_registry
from core.extended_wallets import create_vaults
from core import vaultforge as vf
from backend import read_vault,public_wallets, _evm_vault_entry

class TestExtended(unittest.TestCase):
    def test_assets_and_wordlist(self):
        self.assertGreaterEqual(len(ASSETS),40)
        self.assertEqual(len({a.code for a in TOKENS}),len(TOKENS))
        self.assertEqual(ASSETS['USDT-TRX'].base_coin,'TRX')
        self.assertEqual(ASSETS['USDT-ETH'].base_coin,'ETH')
        self.assertIn(('USD','US Dollar'),FIAT)
        p=Path(__file__).resolve().parent.parent/'data/2048_BIP_39_words.csv'
        with open(p,encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2048)
        self.assertEqual(len({x['Word'] for x in rows}),2048)
        self.assertEqual([int(x['Row']) for x in rows],list(range(1,2049)))
        self.assertEqual([rows[0]['Word'],rows[-1]['Word']],['abandon','zoo'])

    def test_fiat_encryption_and_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            pw='example strong ledger password'
            p=fiat_ledger.new(d,'USD','Cash',pw)
            self.assertTrue(Path(p).is_file())
            raw=Path(p).read_text()
            self.assertNotIn('Cash',raw)
            self.assertNotIn('Crypto-Fiat-Ledger-v1',raw)
            self.assertEqual(fiat_ledger.balance(fiat_ledger.read(p,pw)),Decimal('0'))
            fiat_ledger.append(p,pw,'Money in','300.50','test deposit')
            d2=fiat_ledger.append(p,pw,'Money out','35.20','test payment')
            self.assertEqual(fiat_ledger.balance(d2),Decimal('265.30'))
            self.assertNotIn('test deposit',Path(p).read_text())
            with self.assertRaises(Exception):fiat_ledger.read(p,'wrong password')
            for bad in ('NaN','Infinity','-2','0','1.234','2e99'):
                with self.assertRaises(ValueError):fiat_ledger.append(p,pw,'Money in',bad,'')
            with self.assertRaises(ValueError):fiat_ledger.new(d,'NOTREAL','x',pw)

    def test_fiat_registry(self):
        with tempfile.TemporaryDirectory() as d:
            import core.fiat_registry as fr
            with patch.object(fr,'HOME',Path(d)), patch.object(fr,'FILE',Path(d)/'fiat_paths.json'):
                fr.save(['/x.fiat','/y.fiat','/x.fiat'])
                self.assertEqual(fr.load(),['/x.fiat','/y.fiat'])

    def test_reject_invalid_requests(self):
        for args in [([],1,24,'secure long password'),(['BAD'],1,24,'secure long password'),(['BTC'],0,24,'secure long password'),(['BTC'],1,20,'secure long password')]:
            with self.assertRaises(ValueError):
                create_vaults('/tmp',*args)

    def test_token_signer_selection_fails_closed(self):
        vault={'wallets':[{'coin':'ETH','address':'0x'+'0'*40}, {'coin':'USDT-ETH','address':'0x'+'1'*40}]}
        with self.assertRaises(Exception):_evm_vault_entry(vault,'ETH','Auto')
        self.assertEqual(_evm_vault_entry(vault,'ETH','USDT-ETH')['coin'],'USDT-ETH')
        with self.assertRaises(Exception):_evm_vault_entry(vault,'BNB','USDT-ETH')
        with self.assertRaises(Exception):_evm_vault_entry(vault,'ETH','USDT-TRX')

    def test_create_compatible_encrypted_vault_with_stub_crypto(self):
        from itertools import count
        n=count()
        with tempfile.TemporaryDirectory() as d:
            def mk(words):return 'test-phrase-'+str(next(n))
            def deriv(code,mnemonic,passphrase,account=0):
                return {'coin':code,'address':f'mock-{code}-{mnemonic}-{account}', 'derivation':'mock-test-only'}
            with patch.object(vf,'load_crypto'),patch.object(vf,'generate_bip39',side_effect=mk),patch.object(vf,'generate_monero',side_effect=lambda:'xmr-test-seed'),patch.object(vf,'derive_coin',side_effect=deriv):
                files=create_vaults(d,['BTC','ETH','USDT-ETH','XMR'],1,24,'sufficiently strong passphrase')
                d1=read_vault(files[0],'sufficiently strong passphrase')
                self.assertEqual(len(d1['groups']),4)
                self.assertEqual(len({g['mnemonic'] for g in d1['groups']}),4)
                self.assertEqual(d1['wallets'][2]['underlying_coin'],'ETH')
                self.assertEqual(d1['wallets'][3]['coin'],'XMR')
                self.assertEqual(len(public_wallets(files[0],'sufficiently strong passphrase')),4)
                old=create_vaults(d,['ETH','USDT-ETH'],1,24,'sufficiently strong passphrase',strategy='Shared BIP39 seed (advanced)')
                self.assertEqual(len(read_vault(old[0],'sufficiently strong passphrase')['groups']),1)
                self.assertEqual(len(read_vault(old[0],'sufficiently strong passphrase')['wallets']),2)

    def test_independent_seed_per_asset_and_backward_compat(self):
        try:vf.load_crypto()
        except RuntimeError:self.skipTest('bip-utils unavailable in offline test environment')
        with tempfile.TemporaryDirectory() as d:
            pw='a very strong passphrase 123456'
            paths=create_vaults(d,['BTC','ETH','USDT-TRX','USDC-BASE'],1,12,pw)
            data=read_vault(paths[0],pw)
            self.assertEqual(len(data['groups']),4)
            self.assertEqual(len({x['mnemonic'] for x in data['groups']}),4)
            self.assertEqual([x['coin'] for x in public_wallets(paths[0],pw)],['BTC','ETH','USDT-TRX','USDC-BASE'])
            self.assertEqual([x['underlying_coin'] for x in data['wallets']],['BTC','ETH','TRX','ETH'])
            with self.assertRaises(ValueError):create_vaults(d,['BTC','ETH'],1,12,pw,import_seed=vf.generate_bip39(12))
            group=create_vaults(d,['BTC','ETH'],1,12,pw,strategy='Shared BIP39 seed (advanced)')
            self.assertEqual(len(read_vault(group[0],pw)['groups']),1)
            with self.assertRaises(Exception):read_vault(paths[0],'bad')

if __name__=='__main__':unittest.main()
