import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wallet_core as vf


class CryptoAndStorageTests(unittest.TestCase):
    def test_30_unique_coins(self):
        self.assertEqual(len(vf.COINS), 30)
        self.assertEqual(len({x[0] for x in vf.COINS}), 30)
        self.assertEqual(vf.COINS[-1][0], "XMR")

    def test_encrypt_decrypt_and_integrity(self):
        secret = {"format": "VaultForge-Unlocked-v1", "groups": [
            {"scheme": "test", "mnemonic": "FAKE TEST SECRET", "passphrase": ""}], "wallets": []}
        encrypted = vf.encrypt_payload(secret, "this is a unit test password")
        self.assertNotIn(b"FAKE TEST SECRET", encrypted)
        self.assertEqual(vf.decrypt_payload(encrypted, "this is a unit test password"), secret)
        with self.assertRaises(Exception):
            vf.decrypt_payload(encrypted, "incorrect password")
        broken = bytearray(encrypted)
        obj = __import__('json').loads(encrypted)
        from base64 import b64decode, b64encode
        ct = bytearray(b64decode(obj["ciphertext_b64"]))
        ct[-1] ^= 1
        obj["ciphertext_b64"] = b64encode(ct).decode()
        with self.assertRaises(Exception):
            vf.decrypt_payload(__import__('json').dumps(obj).encode(), "this is a unit test password")

    def test_save_and_rotate(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "wallets"
            secret = {"format": "VaultForge-Unlocked-v1", "groups": [], "wallets": []}
            p = vf.write_new_vault(folder, secret, "initial-unit-test-password")
            self.assertEqual(vf.decrypt_payload(p.read_bytes(), "initial-unit-test-password"), secret)
            vf.update_password(p, secret, "new-unit-test-password")
            with self.assertRaises(Exception):
                vf.decrypt_payload(p.read_bytes(), "initial-unit-test-password")
            self.assertEqual(vf.decrypt_payload(p.read_bytes(), "new-unit-test-password"), secret)
            if os.name != "nt":
                self.assertEqual(p.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
