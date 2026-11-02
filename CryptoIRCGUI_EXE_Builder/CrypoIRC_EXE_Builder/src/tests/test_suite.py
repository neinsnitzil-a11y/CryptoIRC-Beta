import json, sys, tempfile, unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend
from core import vaultforge as vf, transfer as tx


class StorageSafetyTests(unittest.TestCase):
    def test_vault_decrypt_is_compatible(self):
        payload={'format':'VaultForge-Unlocked-v1','groups':[],'wallets':[]}
        with tempfile.TemporaryDirectory() as t:
            p=vf.write_new_vault(Path(t),payload,'a long test password 123')
            self.assertEqual(backend.read_vault(str(p),'a long test password 123'),payload)
            with self.assertRaises(Exception):backend.read_vault(str(p),'incorrect')
    def test_public_registry_only(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(backend,'HOME',Path(t)),patch.object(backend,'REGISTRY',Path(t)/'r.json'):
                backend.save_registry(['C:/drive/abc.vault'],[{'label':'Test','coin':'BTC','address':'bc1qtest','mnemonic':'NEVER_WRITE_ME'}])
                raw=(Path(t)/'r.json').read_text()
                self.assertNotIn('mnemonic',raw)
                self.assertNotIn('NEVER_WRITE_ME',raw)
                self.assertEqual(backend.load_registry()[0],['C:/drive/abc.vault'])
    def test_read_refuses_plaintext_and_symlinks(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'wallet.vault';p.write_text('{"mnemonic":"do not import"}')
            with self.assertRaises(Exception):backend.read_vault(str(p),'x')
            link=Path(t)/'link.vault'
            try:link.symlink_to(p)
            except (OSError,NotImplementedError):return
            with self.assertRaises(ValueError):backend.read_vault(str(link),'x')
    @patch.object(vf, 'load_crypto')
    def test_import_guards(self, mock_load):
        with self.assertRaises(ValueError):
            backend.build_wallets('/tmp/foo',['BTC','XMR'],1,24,'long password 123456','', 'random words')
        with self.assertRaises(ValueError):
            backend.build_wallets('/tmp/foo',['BTC'],21,24,'long password 123456')
    def test_public_address_basic_check(self):
        self.assertFalse(backend.verify_public_address('ETH','0x123'))
        self.assertFalse(backend.verify_public_address('BTC','not-an-address'))
        self.assertTrue(backend.verify_public_address('ETH','0x'+'1'*40))


class TransferSafetyTests(unittest.TestCase):
    def plan(self):
        return backend.SendPlan('btc','BTC','Bitcoin mainnet','s','bc1q12345678',Decimal('0.1'),Decimal('0.00001'), 'BTC','', {})
    def test_challenge_contains_amount_symbol_and_suffix(self):
        self.assertEqual(self.plan().challenge,'SEND 0.1 BTC 12345678')
    def test_single_use_even_if_rpc_times_out(self):
        plan=self.plan()
        with patch.object(backend,'commit_btc',side_effect=TimeoutError('ambiguous')) as f:
            with self.assertRaises(TimeoutError):backend.execute_plan(plan)
            with self.assertRaises(tx.TransferError):backend.execute_plan(plan)
            self.assertEqual(f.call_count,1)
    def test_btc_invalid_outputs_rejected(self):
        rpc=MagicMock();rpc.call.return_value={'ismine':False}
        raw={'vout':[{'value':'1.0','scriptPubKey':{'address':'bc1qattacker'}}]}
        with self.assertRaises(tx.TransferError):tx.verify_bitcoin_outputs(rpc,raw,'bc1qrecipient',Decimal('0.4'))
    def test_no_external_http_rpc(self):
        with self.assertRaises(tx.TransferError):tx.safe_loopback_url('http://example.com:8332')
        with self.assertRaises(tx.TransferError):tx.safe_evm_rpc_url('http://example.com:8545')
    def test_amount_precision(self):
        for invalid in ['0','1e4','-2','0.0000000001','nan']:
            with self.assertRaises(tx.TransferError):tx.amount_decimal(invalid,8)
        self.assertEqual(tx.amount_decimal('0.00000001',8),Decimal('0.00000001'))
    def test_evm_has_no_unverified_chain(self):
        with self.assertRaises(tx.TransferError):backend.evm_w3('MADEUP','https://example.com')
    def test_evm_vault_coin_mappings(self):
        self.assertEqual(backend.EVM_TO_VAULT['BNB'],'BSC')
        self.assertEqual(backend.EVM_TO_VAULT['BASE'],'ETH')
        self.assertNotIn('XMR',backend.EVM_TO_VAULT)

if __name__=='__main__':unittest.main()

class NetworkPreparationTests(unittest.TestCase):
    def test_btc_funded_psbt_preview_before_send(self):
        fake=MagicMock()
        fake.call.side_effect=lambda method,*args: {
            'validateaddress':{'isvalid':True},
            'walletcreatefundedpsbt':{'psbt':'UNSIGNED','fee':Decimal('0.00001')},
            'decodepsbt':{'tx':{'vout':[{'value':Decimal('0.10'),'scriptPubKey':{'address':'recipient'}}]}},
        }[method]
        with patch.object(backend,'btc_wallets',return_value=['mywallet']), patch.object(tx,'BitcoinRPC',return_value=fake):
            plan=backend.prepare_btc('http://127.0.0.1:8332','/tmp/cookie','mywallet','recipient','0.1','0.0005')
        self.assertEqual(plan.kind,'btc')
        self.assertEqual(plan.amount,Decimal('0.1'))
        self.assertEqual(plan.fee,Decimal('0.00001'))
        self.assertNotIn('sendrawtransaction',[call.args[0] for call in fake.call.call_args_list])
    def test_xmr_preparation_does_not_relay(self):
        fake=MagicMock()
        fake.call.side_effect=lambda method,*args: {
            'validate_address':{'valid':True,'nettype':'mainnet'},
            'get_balance':{'unlocked_balance':5*10**12},
            'transfer':{'fee':10**9,'tx_metadata':'FAKE','amount':10**12,'tx_hash':'tx'},
        }[method]
        with patch.object(backend,'xmr_rpc',return_value=(fake,{'wallet_type':'normal'})):
            plan=backend.prepare_xmr('http://127.0.0.1:18082','u','pw','receiver','1','0.01')
        self.assertEqual(plan.kind,'xmr')
        self.assertEqual(plan.fee,Decimal('0.001'))
        self.assertEqual(fake.call.call_args_list[-1].args[0],'transfer')
        self.assertTrue(fake.call.call_args_list[-1].args[1]['do_not_relay'])
        self.assertNotIn('relay_tx',[call.args[0] for call in fake.call.call_args_list])
