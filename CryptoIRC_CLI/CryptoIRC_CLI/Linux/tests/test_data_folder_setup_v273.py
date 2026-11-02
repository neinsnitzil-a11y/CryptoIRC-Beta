"""Data-folder creation without network, identities, or wallet modification."""
from pathlib import Path
import os, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
class DataFolderSetup(unittest.TestCase):
    def test_bash_syntax(self):
        for path in (ROOT/'PREPARE_DATA_DIRS.sh',ROOT/'Relay_Only/PREPARE_DATA_DIRS.sh'):
            p=subprocess.run(['bash','-n',str(path)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
    def test_installers_invoke_initializer(self):
        self.assertIn('PREPARE_DATA_DIRS.sh" client', (ROOT/'install_linux.sh').read_text())
        self.assertIn('PREPARE_DATA_DIRS.sh" relay', (ROOT/'Relay_Only/install.sh').read_text())
        self.assertIn('PREPARE_DATA_DIRS.sh relay', (ROOT/'Relay_Only/AWS_QUICK_SETUP.sh').read_text())
    def test_helper_root_protection(self):
        text=(ROOT/'PREPARE_DATA_DIRS.sh').read_text()
        self.assertIn('EUID == 0',text)
        self.assertIn('Refusing symlink',text)
        self.assertNotIn('node.secret', text.split('for dir in "${folders[@]}"; do')[0])
    def test_relay_and_client_modes_are_distinct(self):
        text=(ROOT/'PREPARE_DATA_DIRS.sh').read_text()
        self.assertIn('if [[ "$mode" == client ]]',text)
        self.assertIn('"$base/wallets"',text)
    def test_missing_node_blocks_fresh_setup_with_existing_accounts(self):
        text=(ROOT/'Relay_Only/AWS_QUICK_SETUP.sh').read_text()
        self.assertIn('Existing chat data but no node.json',text)
        self.assertIn('node.secret',text)
if __name__ == '__main__':unittest.main()
