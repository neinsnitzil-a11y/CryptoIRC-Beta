"""Local UI regressions for AWS connection flow. No external connections."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import vaultforge
import mesh_chat

class ConnectAwsUiTests(unittest.TestCase):
    def test_connect_public_ip_defaults_to_actual_server_port(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh_chat, 'secure_root', return_value=Path(d)):
                with patch('builtins.input', side_effect=['1','198.51.100.8']):
                    with patch.object(vaultforge, 'run_mesh_chat') as launch:
                        with redirect_stdout(io.StringIO()):
                            vaultforge.mesh_connect_menu()
        launch.assert_called_once_with(['--listen','127.0.0.1:0','--peer','198.51.100.8:6667'])

    def test_port_override(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh_chat, 'secure_root', return_value=Path(d)):
                with patch('builtins.input', side_effect=['1','example.net:7777']):
                    with patch.object(vaultforge, 'run_mesh_chat') as launch:
                        with redirect_stdout(io.StringIO()):
                            vaultforge.mesh_connect_menu()
        launch.assert_called_once_with(['--listen','127.0.0.1:0','--peer','example.net:7777'])

    def test_blank_entry_uses_saved_aws_preset(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh_chat, 'secure_root', return_value=Path(d)):
                with patch('builtins.input', side_effect=['1','']):
                    with patch.object(vaultforge, 'run_mesh_chat') as launch:
                        with redirect_stdout(io.StringIO()):
                            vaultforge.mesh_connect_menu()
        launch.assert_called_once_with(['--listen','127.0.0.1:0','--peer','18.227.91.173:6667'])

    def test_enter_defaults_are_explicit_in_menu_and_prompt(self):
        captured=[]
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh_chat, 'secure_root', return_value=Path(d)):
                with patch('builtins.input', side_effect=lambda prompt: captured.append(prompt) or ('1' if len(captured)==1 else '')):
                    with patch.object(vaultforge, 'run_mesh_chat') as launch:
                        out=io.StringIO()
                        with redirect_stdout(out):
                            vaultforge.mesh_connect_menu()
        self.assertIn('Hit Enter for default 18.227.91.173:6667', out.getvalue())
        self.assertIn('Hit Enter for default 18.227.91.173:6667', captured[1])
        self.assertIn('[DEFAULT] Using saved AWS relay 18.227.91.173:6667', out.getvalue())
        launch.assert_called_once_with(['--listen','127.0.0.1:0','--peer','18.227.91.173:6667'])

    def test_reconnect_requires_pins(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh_chat, 'secure_root', return_value=Path(d)):
                with patch('builtins.input', side_effect=['2']):
                    with patch.object(vaultforge, 'run_mesh_chat') as launch:
                        with redirect_stdout(io.StringIO()):
                            vaultforge.mesh_connect_menu()
        launch.assert_not_called()

    def test_connect_rejects_urls(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh_chat, 'secure_root', return_value=Path(d)):
                with patch('builtins.input', side_effect=['1','http://example.com:6667']):
                    with patch.object(vaultforge, 'run_mesh_chat') as launch:
                        with redirect_stdout(io.StringIO()):
                            with self.assertRaisesRegex(ValueError, 'hostname'):
                                vaultforge.mesh_connect_menu()
        launch.assert_not_called()

    def test_local_host_does_not_require_public_listen(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh_chat, 'secure_root', return_value=Path(d)):
                with patch('builtins.input', side_effect=['3']):
                    with patch.object(vaultforge, 'run_mesh_chat') as launch:
                        with redirect_stdout(io.StringIO()):
                            vaultforge.mesh_connect_menu()
        launch.assert_called_once_with(['--listen','127.0.0.1:0','--no-auto-connect','--offline'])

if __name__ == '__main__':
    unittest.main()
