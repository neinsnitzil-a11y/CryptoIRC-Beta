"""Offline regression tests for write-permission errors and protected yes/no choices."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wallet_core as wc


class StorageRecoveryTests(unittest.TestCase):
    def test_preflight_creates_and_removes_vault_extension_probe(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / 'wallets'
            self.assertEqual(wc.verify_writable_storage(folder), folder)
            self.assertTrue(folder.is_dir())
            self.assertEqual(list(folder.iterdir()), [])

    def test_preflight_permission_denied_allows_new_user_selected_location(self):
        with tempfile.TemporaryDirectory() as root:
            blocked, allowed = Path(root) / 'blocked', Path(root) / 'allowed'
            real_open = wc.os.open
            def guarded_open(path, *args, **kwargs):
                if str(path).startswith(str(blocked)):
                    raise PermissionError(13, 'Permission denied', str(path))
                return real_open(path, *args, **kwargs)
            with patch.object(wc, 'choose_storage', side_effect=[blocked, allowed]), \
                 patch.object(wc.os, 'open', side_effect=guarded_open), \
                 patch.object(wc, 'ask_yes_no', return_value=True), \
                 redirect_stdout(io.StringIO()) as out:
                self.assertEqual(wc.choose_writable_storage(), allowed)
            self.assertIn('[STORAGE BLOCKED]', out.getvalue())
            self.assertIn('Controlled Folder Access', out.getvalue())
            self.assertEqual(list(blocked.iterdir()), [])
            self.assertEqual(list(allowed.iterdir()), [])

    def test_invalid_answer_does_not_silently_disable_passphrase(self):
        with patch('builtins.input', side_effect=['hellofriend', 'yes']), \
             redirect_stdout(io.StringIO()) as out:
            self.assertTrue(wc.ask_yes_no('Use BIP39 passphrase? [y/N]: '))
        self.assertIn('Please enter y or n', out.getvalue())
        self.assertNotIn('hellofriend', out.getvalue())

    def test_write_failure_retries_same_seed_in_alternate_folder(self):
        with tempfile.TemporaryDirectory() as root:
            first, second = Path(root) / 'first', Path(root) / 'second'
            original = wc.write_new_vault
            attempts = []
            def first_fails(folder, payload, password):
                attempts.append(payload['groups'][0]['mnemonic'])
                if folder == first:
                    raise PermissionError(13, 'Permission denied', str(first / 'blocked.vault'))
                return original(folder, payload, password)
            # User chooses coin #19=SOL, one wallet, 12 words, no extra
            # passphrase, new seed, then approves retry into another location.
            answers = iter(['19', '', '1', 'n', 'n', 'y', 'n'])
            with patch.object(wc, 'choose_writable_storage', side_effect=[first, second]), \
                 patch.object(wc, 'write_new_vault', side_effect=first_fails), \
                 patch.object(wc, 'generate_bip39', return_value='TEST MNEMONIC NOT A REAL SEED') as gen, \
                 patch.object(wc, 'derive_coin', return_value={'coin':'SOL','address':'test-address','derivation':"m/44'/501'/0'/0/0"}), \
                 patch.object(wc.getpass, 'getpass', side_effect=['long_password_for_tests', 'long_password_for_tests']), \
                 patch('builtins.input', side_effect=lambda *a: next(answers)), \
                 redirect_stdout(io.StringIO()) as out:
                wc.create_wallets()
            self.assertEqual(attempts, ['TEST MNEMONIC NOT A REAL SEED']*2)
            gen.assert_called_once()
            self.assertEqual(len(list(second.glob('*.vault'))), 1)
            self.assertIn('[SAVE BLOCKED]', out.getvalue())
            self.assertIn('[SAVED]', out.getvalue())
            p = next(second.glob('*.vault'))
            self.assertEqual(wc.decrypt_payload(p.read_bytes(), 'long_password_for_tests')['groups'][0]['mnemonic'], 'TEST MNEMONIC NOT A REAL SEED')

    def test_stops_before_generating_seed_when_storage_not_writable(self):
        with patch.object(wc, 'choose_storage', side_effect=PermissionError(13, 'Permission denied')), \
             patch.object(wc, 'ask_yes_no', return_value=False), \
             patch.object(wc, 'generate_bip39') as generate, \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'No seed has been generated'):
                wc.create_wallets()
        generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
