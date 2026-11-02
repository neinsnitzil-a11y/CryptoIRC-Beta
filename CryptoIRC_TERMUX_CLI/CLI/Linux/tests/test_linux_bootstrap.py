"""Linux bootstrap hardening tests (offline; never download or access wallets)."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'install_linux.sh'


class LinuxBootstrapTests(unittest.TestCase):
    def test_bash_syntax(self):
        result = subprocess.run(['bash', '-n', str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_binary_is_pinned_and_checksum_verification_precedes_execution(self):
        content = SCRIPT.read_text()
        self.assertIn('UV_VERSION=\'0.13.6\'', content)
        self.assertIn('f29c3e94ffabd7e6f3ba521dba169a9b7ec12100bf3257087f0f24f6123f3645', content)
        self.assertIn('sha256sum --check --status', content)
        self.assertLess(content.index('sha256sum --check --status'), content.index('install -m 700'))

    def test_downloads_have_timeout_and_alternate_release_source(self):
        script = SCRIPT.read_text()
        self.assertIn('--max-time 120', script)
        self.assertIn('--connect-timeout 12', script)
        self.assertIn('URL_GITHUB=', script)
        self.assertIn('URL_MIRROR=', script)
        self.assertIn('timeout 360', script)

    def test_prefer_local_python_before_uv(self):
        text = SCRIPT.read_text()
        self.assertLess(text.index('for candidate in python3.12; do'), text.index('UV_VERSION='))
        self.assertIn('exec "$resolved" install_runtime.py', text)

    def test_refuses_root_and_does_not_run_network_shell_installer(self):
        text = SCRIPT.read_text()
        self.assertIn('(( EUID == 0 ))', text)
        self.assertNotIn('UV_UNMANAGED_INSTALL=', text)
        self.assertNotIn('sh "$DOWNLOAD"', text)
        self.assertNotIn('curl | sh', text)

    @unittest.skipUnless(os.geteuid() == 0 and shutil.which('runuser'), 'needs root to test privilege downgrade')
    def test_rejects_root_early_without_network(self):
        result = subprocess.run(['bash', str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Do not run this installer with sudo', result.stderr)
        self.assertNotIn('Downloading', result.stdout)


if __name__ == '__main__':
    unittest.main()
