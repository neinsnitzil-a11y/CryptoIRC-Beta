"""GUI identity rotation remains fail-closed without typing an untrusted fingerprint.

The detected value is supplied by the untrusted peer and must be checked
independently against the administrator's server console before two approvals.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch, MagicMock
from mesh_gui import MeshGUI


class AutoPrompt(unittest.TestCase):
    def setUp(self):
        self.gui = MeshGUI.__new__(MeshGUI)
        self.gui.mesh_var_endpoint = MagicMock()
        self.gui.mesh_var_endpoint.get.return_value = '18.188.145.207:6667'
        self.gui.root = MagicMock()
        self.sent = []
        self.messages = []
        self.gui._mesh_send = lambda *a, **kw: self.sent.append((a, kw))
        self.gui._mesh_log = self.messages.append
        self.data = {'endpoint': '18.188.145.207:6667',
                     'pinned': 'f704e415f7ffc6dd',
                     'detected': '9aca2e4a28878448'}

    @patch('mesh_gui.messagebox.askyesno', return_value=False)
    @patch('mesh_gui.simpledialog.askstring')
    def test_cancel_no_trust_update(self, manual_input, confirm):
        self.gui._mesh_verify_relay_trust(self.data)
        self.assertFalse(self.sent)
        self.assertIn(self.data['detected'], confirm.call_args.args[1])
        confirm.assert_called_once()
        manual_input.assert_not_called()

    @patch('mesh_gui.messagebox.askyesno', side_effect=[True, False])
    @patch('mesh_gui.simpledialog.askstring')
    def test_second_confirmation_cancel_keeps_old_pin(self, manual_input, confirm):
        self.gui._mesh_verify_relay_trust(self.data)
        self.assertFalse(self.sent)
        self.assertEqual(confirm.call_count, 2)
        manual_input.assert_not_called()

    @patch('mesh_gui.messagebox.askyesno')
    @patch('mesh_gui.simpledialog.askstring')
    def test_invalid_detected_value_blocked(self, manual_input, confirm):
        data = dict(self.data, detected='ffffffffffffffff;malformed')
        self.gui._mesh_verify_relay_trust(data)
        self.assertFalse(self.sent)
        self.assertTrue(any('Invalid fingerprint' in x for x in self.messages))
        confirm.assert_not_called()
        manual_input.assert_not_called()

    @patch('mesh_gui.messagebox.askyesno', side_effect=[True, True])
    @patch('mesh_gui.simpledialog.askstring')
    def test_explicitly_verified_value_is_passed_to_worker(self, manual_input, confirm):
        self.gui._mesh_verify_relay_trust(self.data)
        self.assertEqual(self.sent, [(('replace_peer_trust',), {
            'endpoint': '18.188.145.207:6667',
            'previous_id': 'f704e415f7ffc6dd',
            'verified_id': '9aca2e4a28878448'})])
        self.assertEqual(confirm.call_count, 2)
        manual_input.assert_not_called()

    @patch('mesh_gui.messagebox.askyesno')
    def test_stale_endpoint_change_blocks_rotation(self, confirm):
        self.gui.mesh_var_endpoint.get.return_value = '18.227.91.173:6667'
        self.gui._mesh_verify_relay_trust(self.data)
        self.assertFalse(self.sent)
        confirm.assert_not_called()


if __name__ == '__main__':
    unittest.main()
