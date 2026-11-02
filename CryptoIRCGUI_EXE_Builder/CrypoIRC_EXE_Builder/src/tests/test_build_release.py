"""Build hygiene tests; no cryptographic or payment operations."""
import tempfile
from pathlib import Path
import unittest
import build_release as b

class BuildReleaseTests(unittest.TestCase):
    def test_required_assets(self):
        self.assertTrue((b.ROOT/'brand_assets'/'tor_round.png').is_file())
        self.assertTrue((b.ROOT/'brand_assets'/'CRYPTO_NOCTURNE.ico').is_file())
        self.assertTrue((b.ROOT/'data'/'iso4217_catalog.json').is_file())

    def test_source_scan_finds_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'sub').mkdir()
            (p/'sub'/'seed_backup.vault').write_text('fake')
            (p/'.env').write_text('TEST_SECRET=fake')
            (p/'build').mkdir()
            (p/'build'/'hidden.key').write_text('ignore generated output')
            found=b.scan_sources_for_secrets(p)
            self.assertEqual(found,['.env','sub/seed_backup.vault'])

    def test_verified_public_ca_bundle_is_not_a_private_key(self):
        # Legitimate certifi HTTPS roots are public certificates shipped by
        # PyInstaller. The scanner must accept that exact public bundle.
        import certifi
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            target=root/'_internal'/'certifi'/'cacert.pem'
            target.parent.mkdir(parents=True)
            target.write_bytes(Path(certifi.where()).read_bytes())
            self.assertEqual(b.scan_distribution_for_secrets(root), [])
            self.assertEqual(b.scan_sources_for_secrets(root), ['_internal/certifi/cacert.pem'])

    def test_other_pems_and_spoofed_ca_bundle_remain_blocked(self):
        import certifi
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            public=root/'_internal'/'certifi'/'cacert.pem'
            public.parent.mkdir(parents=True)
            public.write_bytes(Path(certifi.where()).read_bytes())
            private=root/'_internal'/'wallet-private.pem'
            private.write_text('-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----')
            self.assertEqual(b.scan_distribution_for_secrets(root), ['_internal/wallet-private.pem'])
            public.write_bytes(b'-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----')
            self.assertEqual(b.scan_distribution_for_secrets(root),
                             ['_internal/certifi/cacert.pem','_internal/wallet-private.pem'])

    def test_external_dependency_tests_and_server_data_not_mistaken_for_our_backend(self):
        from release_security import distribution_audit
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'CRYPTO_NOCTURNE.exe').write_bytes(b'stub for audit test')
            (root/'_internal/qrcode/tests').mkdir(parents=True)
            (root/'_internal/qrcode/tests/test_example.py').write_text('')
            (root/'_internal/somelib/server').mkdir(parents=True)
            (root/'_internal/somelib/server/metadata.json').write_text('{}')
            self.assertGreater(distribution_audit(root), 0)

    def test_real_backend_relay_tests_and_wallet_secrets_still_blocked(self):
        from release_security import distribution_audit, ReleaseBlocked
        for forbidden in ('_internal/financial_backend/ledger.py',
                          '_internal/server/relay.py',
                          '_internal/tests/test_wallet.py',
                          '_internal/vendor/private.vault',
                          '_internal/vendor/seed.key'):
            with self.subTest(forbidden=forbidden), tempfile.TemporaryDirectory() as d:
                root=Path(d)
                (root/'CRYPTO_NOCTURNE.exe').write_bytes(b'stub')
                file=root/forbidden
                file.parent.mkdir(parents=True)
                file.write_text('sensitive')
                with self.assertRaises(ReleaseBlocked):
                    distribution_audit(root)

    def test_pyinstaller_filters_dependency_tests(self):
        spec=(b.ROOT/'CRYPTO_NOCTURNE.spec').read_text(encoding='utf-8')
        self.assertIn('filter_submodules=_production_submodule', spec)
        self.assertIn('include_py_files=False', spec)
        self.assertIn('exclude_datas=', spec)
        self.assertIn("'financial_backend'",spec)
        self.assertIn("'server'",spec)

    def test_installer_checks_frozen_wallet_again(self):
        source=(b.ROOT/'build_release.py').read_text(encoding='utf-8')
        installer_section=source.split('def build_installer():')[1].split('def build_portable():')[0]
        self.assertIn('verify_frozen_wallet_runtime()', installer_section)
        self.assertIn('distribution_audit', installer_section)

    def test_builder_offers_opt_in_installer_launch_only_on_success(self):
        source=(b.ROOT/'builder_gui.py').read_text(encoding='utf-8')
        self.assertIn('Launch Inno Setup installer after a successful build', source)
        self.assertIn("ok and self.launch_requested", source)
        self.assertIn("os.startfile(str(installer))", source)
        self.assertIn("('full','installer')", source)

    def test_build_spec_includes_native_wallet_extensions(self):
        spec=(b.ROOT/'CRYPTO_NOCTURNE.spec').read_text(encoding='utf-8')
        self.assertIn("'coincurve'", spec)
        self.assertIn("'sr25519'", spec)
        self.assertIn("'ed25519_blake2b'", spec)
        self.assertIn('extra_binaries.extend', spec)

    def test_installer_reuses_distribution_audit(self):
        # The EXE and installer may not disagree about secret detection.
        source=(b.ROOT/'build_release.py').read_text(encoding='utf-8')
        self.assertIn('distribution_audit(OUTPUT_ROOT/\'dist\'/APP_NAME)', source)

    def test_installer_only_copies_approved_bundle(self):
        script=(b.ROOT/'installer.iss').read_text(encoding='utf-8')
        self.assertIn('dist\\CRYPTO_NOCTURNE\\*',script)
        self.assertNotIn('Source: "*"',script)
        self.assertIn('PrivilegesRequired=lowest',script)
        self.assertNotIn('[UninstallDelete]',script)

    def test_specs_include_art_and_data(self):
        script=(b.ROOT/'CRYPTO_NOCTURNE.spec').read_text(encoding='utf-8')
        self.assertIn("'brand_assets'",script)
        self.assertIn("'data'",script)
        self.assertIn('COLLECT(',script)

    def test_no_wallet_secret_in_source(self):
        self.assertEqual(b.scan_sources_for_secrets(),[])

if __name__=='__main__':unittest.main()
