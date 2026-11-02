import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TERM = ROOT/'Termux'
LINUX = ROOT/'CLI'/'Linux'

class FullTermuxPortTests(unittest.TestCase):
    def test_same_wallet_modules(self):
        names=('vaultforge.py','wallet_core.py','vault_bridge.py','transfer_engine.py',
               'bitcoin_vault.py','mesh_chat.py','file_transfer.py','security_center.py',
               'node_manager.py','chat_history.py','connection_diagnostics.py')
        for name in names:
            self.assertTrue((TERM/'app'/name).is_file(), name)
            ast.parse((TERM/'app'/name).read_text(encoding='utf-8'))
        for name in names:
            if name != 'node_manager.py':
                self.assertEqual((TERM/'app'/name).read_bytes(), (LINUX/name).read_bytes(), name)
    def test_full_ui_is_preserved(self):
        src=(TERM/'app'/'vaultforge.py').read_text()
        for mode in ('wc.create_wallets()', 'bridge.send_from_vault()', 'btc.bitcoin_send()',
                     'te.monero_transfer()', 'security.security_menu()', 'mesh_connect_menu()'):
            self.assertIn(mode,src)
    def test_native_fail_closed(self):
        installer=(TERM/'INSTALL_TERMUX.sh').read_text()
        self.assertIn('--full',installer)
        self.assertIn('exit 1',installer)
        self.assertNotIn('uv python install',installer)
        self.assertNotIn('pip install --upgrade pip',installer)
        self.assertIn('--system-site-packages',installer)
    def test_boot_avoids_systemd(self):
        src=(TERM/'app'/'node_manager.py').read_text()
        self.assertIn("/ 'boot'",src)
        self.assertIn("'start-vaultforge-mesh'",src)
        self.assertIn('Termux:Boot',src)
    def test_linux_fallback_exists(self):
        self.assertIn('proot-distro login ubuntu', (TERM/'START_PROOT_UBUNTU.sh').read_text())
        self.assertIn('install_linux.sh', (TERM/'INSTALL_PROOT_UBUNTU.sh').read_text())
    def test_connect_uses_chat_mode(self):
        src=(TERM/'CONNECT_TERMUX.sh').read_text()
        self.assertIn('vaultforge.py" chat --listen',src)

if __name__ == '__main__': unittest.main()
