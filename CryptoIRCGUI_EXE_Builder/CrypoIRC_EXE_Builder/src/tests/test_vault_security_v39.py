"""Phase 12 security regression suite. Uses test records WITHOUT mnemonic secrets."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import vaultforge as vf
from vault_security import inspect_vault, backup_encrypted_vault, rotate_vault_with_backup

OLD='original test-only passphrase 1234'
NEW='new test-only passphrase 5678'
PAYLOAD={'format':'VaultForge-Unlocked-v1','groups':[],'wallets':[], 'test':'no secrets here'}

class VaultSecurityTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory(prefix='nocturne_phase12_')
        self.addCleanup(self.dir.cleanup)
        self.folder=Path(self.dir.name)
        self.vault_dir=self.folder/'working';self.vault_dir.mkdir()
        self.backup_dir=self.folder/'backups';self.backup_dir.mkdir()
        self.vault=vf.write_new_vault(self.vault_dir,PAYLOAD,OLD)
        self.backup=self.backup_dir/'encrypted-rollback.vault'

    def test_authenticated_header_and_no_seed_export(self):
        result=inspect_vault(self.vault,OLD)
        self.assertTrue(result.authenticated)
        self.assertFalse(result.recovery_verified)
        self.assertIn('Argon2id',result.encrypted_format)
        self.assertEqual(len(result.encrypted_digest),64)
        self.assertNotIn(OLD,str(result))

    def test_wrong_password_never_touches_files(self):
        before=self.vault.read_bytes()
        with self.assertRaises(Exception):backup_encrypted_vault(self.vault,self.backup,'wrong pass')
        self.assertFalse(self.backup.exists())
        with self.assertRaises(Exception):rotate_vault_with_backup(self.vault,'wrong pass',NEW,self.backup)
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.vault.read_bytes(),before)

    def test_backup_exact_cipher_and_authentication(self):
        result=backup_encrypted_vault(self.vault,self.backup,OLD)
        self.assertTrue(result.authenticated)
        self.assertEqual(self.backup.read_bytes(),self.vault.read_bytes())
        self.assertEqual(vf.decrypt_payload(self.backup.read_bytes(),OLD),PAYLOAD)

    def test_existing_backup_never_overwritten(self):
        self.backup.write_text('important previous backup')
        with self.assertRaises(ValueError):backup_encrypted_vault(self.vault,self.backup,OLD)
        self.assertEqual(self.backup.read_text(),'important previous backup')

    def test_reject_source_dir_and_source_itself(self):
        with self.assertRaises(ValueError):backup_encrypted_vault(self.vault,self.vault,OLD)
        with self.assertRaises(ValueError):backup_encrypted_vault(self.vault,self.vault_dir/'copy.vault',OLD)

    def test_non_vault_file_rejected(self):
        with self.assertRaises(ValueError):inspect_vault(self.folder/'fake.txt',OLD)
        with self.assertRaises(ValueError):backup_encrypted_vault(self.vault,self.backup.with_suffix('.txt'),OLD)

    def test_symlink_backup_refused(self):
        try:self.backup.symlink_to(self.vault)
        except (OSError,NotImplementedError):self.skipTest('Symlink capability unavailable')
        with self.assertRaises(ValueError):backup_encrypted_vault(self.vault,self.backup,OLD)

    def test_password_rotation_preserves_original_in_backup(self):
        old=self.vault.read_bytes()
        info=rotate_vault_with_backup(self.vault,OLD,NEW,self.backup)
        self.assertTrue(info.authenticated)
        self.assertEqual(self.backup.read_bytes(),old)
        self.assertNotEqual(self.vault.read_bytes(),old)
        self.assertEqual(vf.decrypt_payload(self.vault.read_bytes(),NEW),PAYLOAD)
        self.assertEqual(vf.decrypt_payload(self.backup.read_bytes(),OLD),PAYLOAD)
        with self.assertRaises(Exception):vf.decrypt_payload(self.vault.read_bytes(),OLD)
        with self.assertRaises(Exception):vf.decrypt_payload(self.backup.read_bytes(),NEW)

    def test_weak_or_identical_password_rejected(self):
        for new in ['tiny',OLD]:
            with self.subTest(new=new):
                with self.assertRaises(ValueError):rotate_vault_with_backup(self.vault,OLD,new,self.backup)
        self.assertFalse(self.backup.exists())

    def test_encryption_failure_keeps_source_and_verified_backup(self):
        original=self.vault.read_bytes()
        with patch.object(vf,'encrypt_payload',side_effect=ValueError('test-only failure')):
            with self.assertRaises(ValueError):rotate_vault_with_backup(self.vault,OLD,NEW,self.backup)
        self.assertEqual(self.vault.read_bytes(),original)
        self.assertEqual(self.backup.read_bytes(),original)

    def test_permission_warning_on_posix(self):
        if os.name=='nt':self.skipTest('POSIX permission flags only')
        os.chmod(self.vault,0o644)
        self.assertIn('REVIEW:',inspect_vault(self.vault,OLD).permission_status)

    def test_tampered_authenticated_backup_rejected(self):
        backup_encrypted_vault(self.vault,self.backup,OLD)
        data=bytearray(self.backup.read_bytes())
        i=data.index(b'ciphertext_b64')+30
        data[i]=ord('A') if data[i]!=ord('A') else ord('B')
        self.backup.write_bytes(data)
        with self.assertRaises(Exception):inspect_vault(self.backup,OLD)

    def test_backup_is_never_placed_inside_source_tree(self):
        project=Path(__file__).resolve().parents[2]
        with self.assertRaises(ValueError):backup_encrypted_vault(self.vault,project/'bad.vault',OLD)

    def test_legacy_cli_routes_rotation_through_rollback(self):
        from core import vaultforge
        import inspect
        cli_src=inspect.getsource(vaultforge.menu)
        self.assertIn('rotate_vault_with_backup',cli_src)
        self.assertNotIn('update_password(path, payload, password)',cli_src)

    def test_rotation_file_format_still_v1(self):
        rotate_vault_with_backup(self.vault,OLD,NEW,self.backup)
        self.assertEqual(vf.decrypt_payload(self.vault.read_bytes(),NEW)['format'],'VaultForge-Unlocked-v1')
        self.assertEqual(vf.decrypt_payload(self.backup.read_bytes(),OLD)['format'],'VaultForge-Unlocked-v1')

if __name__=='__main__':unittest.main()
