"""v3.2 public account boundary and signer-binding regression tests (no live funds)."""
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock

from unified_wallet import (
    UnifiedAccountRegistry, account_from_record, from_vault_rows, from_watch_rows,
    register_bitcoin_core, register_monero_rpc, inspect_evm_account,
    inspect_btc_account, inspect_xmr_account, inspect_vault_evm_account,
)


class UnifiedWalletTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=UnifiedAccountRegistry(Path(self.tmp.name)/'accounts.json')

    def core(self):
        return register_bitcoin_core('testwallet','regtest','bcrt1qexample_public_test_address')

    def test_core_registration_requires_explicit_network(self):
        with self.assertRaises(ValueError):register_bitcoin_core('a','testnet','bc1q123')
        with self.assertRaises(ValueError):register_bitcoin_core('a','main','bc1q123\nsecret')

    def test_registry_public_only_and_does_not_persist_verification(self):
        a=replace(self.core(),status='TESTED',details='balance 123 BTC',can_receive=True,can_spend=True,signer_proven=True)
        self.store.add(a)
        stored=json.loads(self.store.path.read_text())
        self.assertEqual(stored['schema'],1)
        self.assertEqual(len(stored['accounts']),1)
        self.assertEqual(set(stored['accounts'][0]),{'kind','asset','network','address','source','label'})
        self.assertNotIn('TESTED',self.store.path.read_text())
        after=self.store.list()[0]
        self.assertFalse(after.can_spend)
        self.assertFalse(after.signer_proven)
        self.assertEqual(after.status,'UNVERIFIED')

    def test_registry_idempotent_and_remove(self):
        a=self.core()
        self.store.add(a);self.store.add(a)
        self.assertEqual(len(self.store.list()),1)
        self.store.remove(a.id)
        self.assertEqual(self.store.list(),[])

    def test_registry_rejects_vault_persistence(self):
        entry=from_vault_rows('/tmp/demo.vault',[{'coin':'ETH','address':'0x'+'1'*40,'network':'ETH'}])[0]
        self.assertFalse(entry.can_spend)
        with self.assertRaises(ValueError):self.store.add(entry)

    def test_registry_does_not_trust_forged_verification_fields(self):
        a=self.core().public_record()
        a.update({'status':'CERTIFIED','can_spend':True,'signer_proven':True,'private_key':'DO NOT STORE'})
        self.store.add(account_from_record(a))
        saved=self.store.path.read_text()
        self.assertNotIn('CERTIFIED',saved)
        self.assertNotIn('DO NOT STORE',saved)
        self.assertFalse(self.store.list()[0].can_spend)

    def test_registry_blocks_symlink(self):
        try:
            self.store.path.symlink_to(Path(self.tmp.name)/'missing.json')
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation unavailable without Windows developer permissions')
        with self.assertRaises(ValueError):self.store.add(self.core())

    def test_watch_only_never_spendable(self):
        accounts=from_watch_rows([{'coin':'BTC','address':'bc1q_public','label':'Cold watch'}])
        self.assertEqual(len(accounts),1)
        self.assertFalse(accounts[0].signer_proven)
        self.assertFalse(accounts[0].can_spend)

    def test_xmr_network_must_be_explicit(self):
        with self.assertRaises(ValueError):register_monero_rpc('main','public_address')

    def test_bitcoin_rpc_verifies_exact_address_not_just_wallet(self):
        a=self.core()
        rpc=Mock();rpc.call.side_effect=lambda method,*args: (
            {'ismine':False,'iswatchonly':False} if method=='getaddressinfo' else {'private_keys_enabled':True})
        svc=Mock();svc.wallet_rpc.return_value=rpc
        with self.assertRaisesRegex(Exception,'not spendably owned'):
            inspect_btc_account(a,'http://127.0.0.1:18443','cookie',service_factory=lambda:svc)
        self.assertFalse(a.signer_proven)

    def test_bitcoin_rpc_watch_only_never_spendable(self):
        a=self.core()
        rpc=Mock()
        rpc.call.side_effect=lambda method,*args: (
            {'ismine':True,'iswatchonly':False} if method=='getaddressinfo' else
            {'private_keys_enabled':False,'external_signer':False})
        svc=Mock();svc.wallet_rpc.return_value=rpc
        svc.balance.return_value={'trusted':'0','untrusted_pending':'0'}
        checked=inspect_btc_account(a,'http://127.0.0.1:18443','cookie',service_factory=lambda:svc)
        self.assertFalse(checked.can_spend)
        self.assertTrue(checked.can_receive)

    def test_bitcoin_rpc_connected_signer_not_independent_recovery(self):
        a=self.core()
        rpc=Mock()
        rpc.call.side_effect=lambda method,*args: (
            {'ismine':True,'iswatchonly':False} if method=='getaddressinfo' else
            {'private_keys_enabled':True,'external_signer':False})
        svc=Mock();svc.wallet_rpc.return_value=rpc
        svc.balance.return_value={'trusted':'1.0','untrusted_pending':'0.1'}
        checked=inspect_btc_account(a,'http://127.0.0.1:18443','cookie',service_factory=lambda:svc)
        self.assertTrue(checked.can_spend)
        self.assertTrue(checked.signer_proven)
        self.assertIn('BACKUP NOT VERIFIED',checked.status)

    def test_monero_address_swap_rejected(self):
        a=register_monero_rpc('stagenet','public_address')
        svc=Mock();svc.health.return_value={'address':'another_wallet'}
        with self.assertRaisesRegex(Exception,'identity changed'):
            inspect_xmr_account(a,'http://127.0.0.1:38082','','',service_factory=lambda:svc)

    def test_monero_wallet_rpc_does_not_claim_signing(self):
        a=register_monero_rpc('stagenet','public_address')
        svc=Mock();svc.health.return_value={'address':'public_address'}
        svc.balance.return_value={'unlocked':'0','total':'0'}
        checked=inspect_xmr_account(a,'http://127.0.0.1:38082','','',service_factory=lambda:svc)
        self.assertTrue(checked.can_receive)
        self.assertFalse(checked.can_spend)

    def test_evm_metadata_never_proves_password_or_recovery(self):
        addr='0x'+'a'*40
        a=account_from_record({'kind':'evm_keystore','asset':'ETH','network':'SEPOLIA',
                'address':addr,'source':str(Path(self.tmp.name)/'v3.json'),'label':'Test'})
        Path(a.source).write_text('{}')
        svc=Mock();svc.health.return_value={'chain_id':11155111}
        svc.balance.return_value={'block':100,'native':'0.2','gas_asset':'ETH'}
        checked=inspect_evm_account(a,'https://rpc.example',keystore_header=lambda _:({},addr),
                service_factory=lambda *args:svc)
        self.assertTrue(checked.can_receive)
        self.assertFalse(checked.signer_proven)
        self.assertFalse(checked.can_spend)
        self.assertIn('PASSWORD NOT PROVEN',checked.status)

    def test_evm_swapped_keystore_rejected(self):
        a=account_from_record({'kind':'evm_keystore','asset':'ETH','network':'SEPOLIA',
                'address':'0x'+'a'*40,'source':str(Path(self.tmp.name)/'v3.json'),'label':'Test'})
        Path(a.source).write_text('{}')
        with self.assertRaisesRegex(Exception,'address changed'):
            inspect_evm_account(a,'https://rpc.example',keystore_header=lambda _:({},'0x'+'b'*40))

    def test_legacy_vault_derived_address_matching(self):
        from types import SimpleNamespace
        a=from_vault_rows('/tmp/safe.vault', [{'coin':'ETH','address':'0x'+'2'*40,'network':'ETH'}])[0]
        called=[]
        def derive(chain, path, password, asset):
            called.append((chain,path,asset))
            return a.address
        def balance(chain,url,address):
            self.assertEqual(chain,'ETH')
            self.assertEqual(address,a.address)
            return SimpleNamespace(available='0.5',currency='ETH',height='100')
        updated=inspect_vault_evm_account(a,'temporary-test-only','https://rpc.example',
                        signer_factory=derive,balance_reader=balance)
        self.assertEqual(called,[('ETH','/tmp/safe.vault','ETH')])
        self.assertTrue(updated.can_receive)
        self.assertFalse(updated.can_spend)
        self.assertFalse(updated.signer_proven)
        self.assertIn('RECOVERY NOT VERIFIED',updated.status)

    def test_legacy_vault_wrong_address_rejected(self):
        a=from_vault_rows('/tmp/safe.vault', [{'coin':'ETH','address':'0x'+'2'*40,'network':'ETH'}])[0]
        with self.assertRaisesRegex(Exception,'did not reproduce'):
            inspect_vault_evm_account(a,'temporary-test-only','https://rpc.example',
                 signer_factory=lambda *args:'0x'+'9'*40,
                 balance_reader=lambda *args:self.fail('Do not query network after signer mismatch'))

    def test_unsupported_vault_chain_not_confused_with_evm(self):
        a=from_vault_rows('/tmp/safe.vault', [{'coin':'LTC','address':'Lpublicaddress','network':'LTC'}])[0]
        with self.assertRaisesRegex(Exception,'No verified EVM vault signing route'):
            inspect_vault_evm_account(a,'test','https://rpc.example')

    def test_invalid_evm_asset_chain_rejected(self):
        with self.assertRaises(ValueError):account_from_record({
            'kind':'evm_keystore','asset':'BTC','network':'ETH','address':'0x'+'a'*40,
            'source':'wallet.json','label':'Bad'})

if __name__=='__main__':unittest.main()
