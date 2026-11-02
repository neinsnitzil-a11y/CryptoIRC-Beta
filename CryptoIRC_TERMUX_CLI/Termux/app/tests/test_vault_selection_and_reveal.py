"""Offline UX and original encrypted-vault compatibility regression tests."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wallet_core as wc
import vault_bridge as bridge
import vaultforge as cli

PAYLOAD = {
    'format': 'VaultForge-Unlocked-v1',
    'groups': [{'scheme':'bip39', 'mnemonic':'alpha bravo charlie', 'passphrase':'sample'}],
    'wallets': [{'coin':'BTC', 'address':'test-only-address', 'derivation':"m/84'/0'/0'/0/0", 'seed_group':0}]
}


class VaultSelectionAndRevealTests(unittest.TestCase):
    def test_saved_vault_unlocks_with_correct_password_and_old_format(self):
        with tempfile.TemporaryDirectory() as root:
            file = wc.write_new_vault(Path(root), PAYLOAD, 'test-password-created-before-unification')
            with patch.object(wc.getpass, 'getpass', return_value='test-password-created-before-unification'), \
                 redirect_stdout(io.StringIO()) as out:
                self.assertEqual(wc.unlock(file), PAYLOAD)
            self.assertIn('[UNLOCKED]', out.getvalue())
            self.assertIn('DIFFERENT password', out.getvalue())

    def test_correct_password_for_different_vault_will_not_unlock(self):
        with tempfile.TemporaryDirectory() as root:
            old = wc.write_new_vault(Path(root), PAYLOAD, 'older-password-must-be-kept')
            new = wc.write_new_vault(Path(root), PAYLOAD, 'new-password-different')
            with patch.object(wc.getpass, 'getpass', return_value='new-password-different'), \
                 redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'selected vault'):
                    wc.unlock(old)
                self.assertEqual(wc.unlock(new), PAYLOAD)

    def test_reveal_yes_then_exact_reveal(self):
        with patch('builtins.input', side_effect=['yes', 'REVEAL', '']), \
             patch.object(wc, 'clear_screen'), redirect_stdout(io.StringIO()) as out:
            wc.reveal_seed_groups(PAYLOAD['groups'])
        self.assertIn("'yes' is not the required confirmation", out.getvalue())
        self.assertIn('alpha', out.getvalue())

    def test_reveal_wrong_input_does_not_show_phrase(self):
        with patch('builtins.input', return_value='no'), \
             redirect_stdout(io.StringIO()) as out:
            wc.reveal_seed_groups(PAYLOAD['groups'])
        self.assertIn('[NOT SHOWN]', out.getvalue())
        self.assertNotIn('alpha', out.getvalue())

    def test_selecting_newest_is_clearly_labeled_and_no_password_is_requested(self):
        with tempfile.TemporaryDirectory() as root:
            d=Path(root)
            old = d / 'vault_20261028T192648Z_old.vault'
            new = d / 'vault_20261029T185321Z_new.vault'
            old.write_bytes(b'only testing selection')
            new.write_bytes(b'only testing selection')
            with patch('builtins.input', side_effect=[str(d), '1']), \
                 redirect_stdout(io.StringIO()) as out:
                self.assertEqual(bridge.select_vault_file(), new)
            self.assertIn('[NEWEST]', out.getvalue())

    def test_incompatible_file_format_does_not_ask_for_password(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'wrong.vault'
            file.write_text(json.dumps({'format':'Unrelated-Format'}), encoding='utf-8')
            with patch.object(wc.getpass, 'getpass') as gp:
                with self.assertRaisesRegex(ValueError, 'password was not checked'):
                    wc.unlock(file)
            gp.assert_not_called()

    def test_btc_only_vault_gives_read_only_menu_diagnostic_not_evm_rpc(self):
        with patch.object(bridge, 'unlock_selected', return_value=(Path('test.vault'), PAYLOAD)), \
             patch.object(cli, 'connect_evm') as connect, \
             redirect_stdout(io.StringIO()) as out:
            cli.read_balance()
        connect.assert_not_called()
        self.assertIn('[NOT AN EVM WALLET]', out.getvalue())
        self.assertIn('cannot check BTC/SOL', out.getvalue())


if __name__ == '__main__':
    unittest.main()
