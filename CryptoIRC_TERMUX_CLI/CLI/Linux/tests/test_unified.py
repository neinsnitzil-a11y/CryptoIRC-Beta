"""Unified integration tests; never connect to a blockchain or use real funds."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vaultforge as app
import vault_bridge as bridge
import wallet_core as wc
import transfer_engine as te


class UnifiedCliTests(unittest.TestCase):
    def test_network_catalog(self):
        with redirect_stdout(io.StringIO()) as buf:
            rc = app.main(['--list-networks'])
        self.assertEqual(rc, 0)
        self.assertIn('ETH', buf.getvalue())
        self.assertIn('encrypted-vault BIP84', buf.getvalue())

    def test_menu_starts_and_exits_without_dependencies(self):
        with patch('builtins.input', return_value='0'), redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(app.main([]), 0)
        self.assertIn('ENCRYPTED WALLETS + TRANSFERS', buf.getvalue())

    def test_legacy_vault_decrypts_using_new_program(self):
        payload = {'format':'VaultForge-Unlocked-v1', 'wallets': [], 'groups': []}
        with tempfile.TemporaryDirectory() as d:
            p = wc.write_new_vault(Path(d), payload, 'integration-test-password')
            self.assertEqual(wc.decrypt_payload(p.read_bytes(), 'integration-test-password'), payload)
            bridge.validate_payload(payload)

    def test_supported_vault_accounts_explicitly_mapped(self):
        entries = [{'coin':'BTC','address':'btc'}, {'coin':'ETH','address':'0x00'},
                   {'coin':'BSC','address':'0x11'}, {'coin':'OP','address':'0x22'},
                   {'coin':'XMR','address':'xmr'}]
        payload = {'format':'VaultForge-Unlocked-v1', 'groups':[], 'wallets':entries}
        self.assertEqual([n for _, n in bridge.available_evm(payload)], ['ETH','BNB','OP'])
        self.assertEqual([n for _, n in bridge.available_evm(payload, sending=True)], ['ETH','BNB'])
        self.assertNotIn('OP', bridge.SEND_EVM)
        self.assertNotIn('ARB', bridge.SEND_EVM)

    def test_refuse_unknown_or_detached_account(self):
        entry = {'coin':'ETH', 'address':'0x'+'a'*40,
                 'derivation':"m/44'/60'/0'/0/0", 'seed_group':0}
        payload = {'format':'VaultForge-Unlocked-v1', 'groups':[{'scheme':'bip39','mnemonic':'test','passphrase':''}],
                   'wallets':[entry]}
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            bridge.derive_evm_vault_key(payload, dict(entry))
        previous = entry['derivation']
        try:
            entry['derivation'] = "m/44'/60'/3'/0/0"
            with self.assertRaisesRegex(ValueError, 'derivation'):
                bridge.derive_evm_vault_key(payload, entry)
        finally:
            entry['derivation'] = previous
        with self.assertRaisesRegex(ValueError, 'BIP39'):
            bridge.derive_evm_vault_key(dict(payload, groups=[{'scheme':'monero'}]), entry)

    def test_vault_transfer_needs_confirmation_before_deriving(self):
        entry = {'coin':'ETH','address':'0x'+'a'*40}
        payload = {'format':'VaultForge-Unlocked-v1','wallets':[entry],'groups':[]}
        with patch.object(bridge, 'unlock_selected', return_value=(Path('fake.vault'), payload)), \
             patch.object(bridge, 'pick_evm', return_value=(entry,'ETH')), \
             patch.object(bridge, 'derive_evm_vault_key') as sign, \
             patch.object(te, 'evm_transfer') as transfer, \
             patch('builtins.input', return_value='NO'), redirect_stdout(io.StringIO()):
            bridge.send_from_vault()
        sign.assert_not_called()
        transfer.assert_not_called()

    def test_transfer_engine_vault_uses_forced_network_and_blocks_l2(self):
        # Stub modules only for this early pre-network test, no RPC access.
        from types import ModuleType
        fake_web3 = ModuleType('web3'); fake_web3.Web3 = object()
        fake_account = ModuleType('eth_account'); fake_account.Account = object()
        with patch.dict(sys.modules, {'web3':fake_web3,'eth_account':fake_account}), \
             patch('builtins.input', return_value='OP'), \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(te.TransferError, 'L2 sending disabled'):
                te.evm_transfer(False, vault_entry={'address':'0x'+'a'*40}, vault_key=b'x'*32, forced_network='OP')


if __name__ == '__main__':
    unittest.main()
