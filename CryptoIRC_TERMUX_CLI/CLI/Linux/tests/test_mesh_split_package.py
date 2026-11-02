"""Validate platform separation and independent installers after packaging."""
from pathlib import Path
import unittest

class PlatformSplitContractTests(unittest.TestCase):
    def test_full_install_has_menu_and_platform_launcher(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / 'vaultforge.py').is_file())
        self.assertTrue((root / 'mesh_chat.py').is_file())
        self.assertTrue((root / 'install_runtime.py').is_file())
        self.assertTrue((root / 'install_linux.sh').is_file() or (root / 'INSTALL_WINDOWS.bat').is_file())

    def test_discovery_requires_explicit_lan(self):
        text = (Path(__file__).resolve().parents[1] / 'mesh_chat.py').read_text()
        self.assertIn("parser.add_argument('--lan'", text)
        self.assertIn("parser.add_argument('--offline'", text)
        self.assertIn("parser.add_argument('--scan'", text)
        self.assertIn('LanDiscoveryResponder', text)

if __name__ == '__main__':
    unittest.main()
