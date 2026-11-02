"""Tests are mocked; they do NOT verify real Tor circuits or blockchain sends."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import sys

import security_center as sc
import wallet_core as wc


class NetworkPrivacyTests(unittest.TestCase):
    def test_default_direct(self):
        with tempfile.TemporaryDirectory() as td, patch.object(sc, 'settings_path', return_value=Path(td)/'state.json'):
            self.assertEqual(sc.load_settings()['mode'], 'direct')

    def test_tor_round_trip_config(self):
        with tempfile.TemporaryDirectory() as td, patch.object(sc, 'settings_path', return_value=Path(td)/'state.json'):
            sc.save_settings('tor', 9150)
            self.assertEqual(sc.load_settings(), {'mode': 'tor', 'port': 9150})
            self.assertNotEqual(sc.settings_path().stat().st_size, 0)
            if os.name != 'nt':
                self.assertEqual(sc.settings_path().stat().st_mode & 0o777, 0o600)

    def test_corrupt_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'state.json'
            p.write_text('{garbage')
            with patch.object(sc, 'settings_path', return_value=p):
                with self.assertRaises(sc.PrivacyError): sc.load_settings()

    def test_bad_port_rejected(self):
        with self.assertRaises(sc.PrivacyError): sc.save_settings('tor', 12345)

    def test_sock_probe_connection_refused_not_direct(self):
        with patch.object(sc.socket, 'create_connection', side_effect=OSError('refused')):
            with self.assertRaisesRegex(sc.PrivacyError, 'no direct fallback'): sc.socks5_probe(9050)

    def test_socks_unexpected_handshake_rejected(self):
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        sock.recv.return_value = b'\x05\xff'
        with patch.object(sc.socket, 'create_connection', return_value=sock):
            with self.assertRaisesRegex(sc.PrivacyError, 'handshake'): sc.socks5_probe(9050)

    def test_onion_core_accepted(self):
        rpc = Mock()
        rpc.call.side_effect = lambda method: ({'networks':[{'name':'onion','proxy':'127.0.0.1:9050'}]} if method=='getnetworkinfo' else [{'network':'onion'}])
        with patch.object(sc, 'load_settings', return_value={'mode':'tor','port':9050}), patch.object(sc, 'socks5_probe'):
            sc.verify_bitcoin_tor(rpc)

    def test_core_clearnet_peer_blocked(self):
        rpc = Mock()
        rpc.call.side_effect = lambda method: ({'networks':[{'name':'onion','proxy':'127.0.0.1:9050'}]} if method=='getnetworkinfo' else [{'network':'onion'},{'network':'ipv4'}])
        with patch.object(sc, 'load_settings', return_value={'mode':'tor','port':9050}), patch.object(sc, 'socks5_probe'):
            with self.assertRaisesRegex(sc.PrivacyError, 'non-onion'): sc.verify_bitcoin_tor(rpc)

    def test_core_no_proxy_blocked(self):
        rpc = Mock()
        rpc.call.return_value = {'networks':[{'name':'onion','proxy':''}]}
        with patch.object(sc, 'load_settings', return_value={'mode':'tor','port':9050}), patch.object(sc, 'socks5_probe'):
            with self.assertRaisesRegex(sc.PrivacyError, 'does not report'): sc.verify_bitcoin_tor(rpc)

    def test_tor_monero_is_not_silently_direct(self):
        with patch.object(sc, 'load_settings', return_value={'mode':'tor','port':9050}):
            with self.assertRaisesRegex(sc.PrivacyError, 'blocks Monero'): sc.require_monero_external_tor_verified()

    def test_http_evm_blocked_in_tor_mode(self):
        with patch.object(sc, 'http_session_for_evm', return_value=Mock()):
            with self.assertRaisesRegex(sc.PrivacyError, 'HTTPS endpoint'): sc.evm_http_provider('http://127.0.0.1:8545')

    def test_tor_session_has_socks5h_and_no_system_proxy(self):
        with patch.object(sc, 'load_settings', return_value={'mode':'tor','port':9050}), \
             patch.object(sc, 'socks5_probe'), \
             patch.dict(sys.modules, {'socks':Mock()}):
            session = sc.http_session_for_evm()
        self.assertFalse(session.trust_env)
        self.assertEqual(session.proxies['https'], 'socks5h://127.0.0.1:9050')

    def test_evm_provider_receives_tor_session(self):
        fake_web3 = Mock()
        session = Mock()
        with patch.object(sc, 'http_session_for_evm', return_value=session), \
             patch.dict(sys.modules, {'web3':fake_web3}):
            sc.evm_http_provider('https://rpc.example.org')
        self.assertEqual(fake_web3.Web3.HTTPProvider.call_args.kwargs['session'], session)

    def test_no_silent_direct_if_tor_proxy_down(self):
        with patch.object(sc,'load_settings',return_value={'mode':'tor','port':9050}), \
             patch.object(sc,'socks5_probe',side_effect=sc.PrivacyError('offline')):
            with self.assertRaises(sc.PrivacyError):
                sc.http_session_for_evm()

    def test_evm_session_no_env_proxy(self):
        with patch.object(sc, 'load_settings', return_value={'mode':'tor','port':9150}), patch.object(sc, 'socks5_probe'):
            try:
                sess = sc.http_session_for_evm()
            except sc.PrivacyError:
                self.skipTest('PySocks/requests unavailable in test runner')
            self.assertFalse(sess.trust_env)
            self.assertEqual(sess.proxies['https'], 'socks5h://127.0.0.1:9150')
            self.assertEqual(sess.proxies['http'], 'socks5h://127.0.0.1:9150')


class RotationTests(unittest.TestCase):
    def test_seed_rotation_cancel_preserves_old(self):
        old = {'format':'VaultForge-Unlocked-v1', 'wallets':[{'coin':'BTC', 'address':'bc1old'}], 'groups':[]}
        with patch('vault_bridge.unlock_selected', return_value=(Path('/fake/old.vault'), old)), \
             patch('builtins.input', return_value='CANCEL'), patch.object(wc, 'choose_writable_storage') as new_dir:
            self.assertIsNone(sc.rotate_seeds_to_new_vault())
            new_dir.assert_not_called()

    def test_rotation_creates_new_file_not_old(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            old_path = folder/'old.vault'
            old = {'format':'VaultForge-Unlocked-v1',
                   'wallets':[{'coin':'BTC','address':'bc1OLD', 'derivation':"m/84'/0'/0'/0/0", 'seed_group':0}],
                   'groups':[{'scheme':'bip39','mnemonic':'old '*12,'passphrase':''}]}
            old_bytes = b'previous encrypted ciphertext'
            old_path.write_bytes(old_bytes)
            incoming = iter(['CREATE NEW WALLET', '', 'n'])
            saved = {}
            def write_mock(directory, payload, password):
                saved['payload'] = payload
                self.assertEqual(password, 'secure-test-password')
                dest = directory/'new.vault'
                dest.write_bytes(b'new encrypted ciphertext')
                return dest
            with patch('vault_bridge.unlock_selected', return_value=(old_path, old)), \
                 patch('builtins.input', side_effect=incoming), \
                 patch.object(wc, 'choose_writable_storage', return_value=folder), \
                 patch.object(wc, 'ask_yes_no', return_value=False), \
                 patch.object(wc, 'new_password', return_value='secure-test-password'), \
                 patch.object(wc, 'generate_bip39', return_value='new '*24), \
                 patch.object(wc, 'derive_coin', return_value={'coin':'BTC','address':'bc1NEW','derivation':"m/84'/0'/0'/0/0"}), \
                 patch.object(wc, 'write_new_vault', side_effect=write_mock), \
                 patch.object(wc, 'decrypt_payload', side_effect=lambda blob, pwd: saved['payload']):
                self.assertEqual(sc.rotate_seeds_to_new_vault(), folder/'new.vault')
            self.assertEqual(old_path.read_bytes(), old_bytes)
            self.assertEqual(saved['payload']['wallets'][0]['address'], 'bc1NEW')
            self.assertEqual(saved['payload']['groups'][0]['mnemonic'], 'new '*24)
            self.assertTrue((folder/'new.vault').exists())

    def test_rotation_rejects_same_address(self):
        old = {'format':'VaultForge-Unlocked-v1', 'wallets':[{'coin':'BTC', 'address':'bc1SAME'}], 'groups':[]}
        with tempfile.TemporaryDirectory() as td, \
             patch('vault_bridge.unlock_selected', return_value=(Path(td)/'old.vault', old)), \
             patch('builtins.input', side_effect=['CREATE NEW WALLET','']), \
             patch.object(wc,'choose_writable_storage', return_value=Path(td)), \
             patch.object(wc,'ask_yes_no', return_value=False), \
             patch.object(wc,'new_password', return_value='testpasswordpassword'), \
             patch.object(wc,'generate_bip39', return_value='new '*24), \
             patch.object(wc,'derive_coin', return_value={'coin':'BTC','address':'bc1SAME'}), \
             patch.object(wc,'write_new_vault') as writer:
            with self.assertRaisesRegex(RuntimeError, 'matches a previous address'):
                sc.rotate_seeds_to_new_vault()
            writer.assert_not_called()

    def test_password_rotation_preserves_old_on_failed_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'old.vault'
            path.write_bytes(b'old_encrypted')
            with patch.object(wc,'encrypt_payload',return_value=b'new_encrypted'), \
                 patch.object(wc,'decrypt_payload',return_value={'not':'original'}):
                with self.assertRaisesRegex(RuntimeError, 'verification failed'):
                    wc.update_password(path, {'original':True}, 'new secure password')
            self.assertEqual(path.read_bytes(), b'old_encrypted')
            self.assertFalse(list(Path(td).glob('.rotate_*')))

    def test_password_rotation_verified_replace(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'old.vault'
            path.write_bytes(b'old_encrypted')
            payload = {'format':'VaultForge-Unlocked-v1'}
            with patch.object(wc,'encrypt_payload',return_value=b'new_encrypted'), \
                 patch.object(wc,'decrypt_payload',return_value=payload):
                wc.update_password(path,payload,'new secure password')
            self.assertEqual(path.read_bytes(), b'new_encrypted')

if __name__ == '__main__': unittest.main()
