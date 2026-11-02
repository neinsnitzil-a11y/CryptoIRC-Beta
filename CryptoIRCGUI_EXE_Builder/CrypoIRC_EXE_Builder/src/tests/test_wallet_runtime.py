import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from wallet_runtime import wallet_error_code, wallet_error_summary, test_wallet_runtime as run_wallet_smoke
from core import vaultforge as vf

class WalletRuntimeTests(unittest.TestCase):
    def test_exception_does_not_expose_secrets_or_paths(self):
        secret = 'abandon ' * 11 + 'about'
        try:
            raise RuntimeError('private path C:/Users/SecretFolder and seed: '+secret)
        except RuntimeError as exc:
            message = wallet_error_summary(exc)
        self.assertIn('WLT-RUNTIME', message)
        self.assertNotIn(secret.strip(), message)
        self.assertNotIn('SecretFolder', message)
        self.assertNotIn('C:/Users', message)

    def test_module_missing_is_classified(self):
        try:
            try: raise ModuleNotFoundError('bip_utils missing')
            except ModuleNotFoundError as exc: raise RuntimeError('secret here') from exc
        except RuntimeError as exc:
            self.assertEqual(wallet_error_code(exc), 'WLT-DEPENDENCY')
            self.assertNotIn('secret here', wallet_error_summary(exc))

    def test_allowlisted_missing_module_is_reported_without_secret(self):
        from core.vaultforge import CryptoDependencyUnavailable
        try:
            try:
                raise ModuleNotFoundError('sensitive-value-do-not-print', name='bip_utils.utils.crypto')
            except ModuleNotFoundError as inner:
                raise CryptoDependencyUnavailable('bip_utils') from inner
        except CryptoDependencyUnavailable as exc:
            summary = wallet_error_summary(exc)
        self.assertIn('WLT-DEPENDENCY', summary)
        self.assertIn('Missing component: bip_utils', summary)
        self.assertNotIn('sensitive-value', summary)

    def test_unknown_module_details_not_leaked(self):
        try:
            raise ModuleNotFoundError('secret-text', name='private_wallet_seed_123')
        except ModuleNotFoundError as exc:
            summary = wallet_error_summary(exc)
        self.assertNotIn('private_wallet_seed_123', summary)
        self.assertNotIn('secret-text', summary)

    def test_storage_failure_is_classified(self):
        self.assertEqual(wallet_error_code(PermissionError('private /path')),'WLT-STORAGE-ACCESS')

    def test_full_wallet_runtime_in_source(self):
        try: vf.load_crypto()
        except RuntimeError: self.skipTest('bip-utils unavailable in isolated test environment')
        self.assertEqual(run_wallet_smoke(),5)

    def test_builder_requires_frozen_binary_smoke(self):
        import build_release
        source=(build_release.ROOT/'build_release.py').read_text(encoding='utf-8')
        self.assertIn("'--wallet-self-test'",source)
        self.assertIn('frozen.returncode != 0',source)
        self.assertIn('report.startswith',source)
        self.assertNotIn('print(frozen.stderr)',source)
        self.assertIn('installer blocked',source)

if __name__=='__main__':unittest.main()
