"""Regression for the GUI-worker's missing retry registration method."""
from __future__ import annotations
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

SRC = Path(__file__).resolve().parents[1]
for path in (SRC, SRC / 'vaultmesh'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
import mesh_chat as mesh
from mesh_bridge import Session


class RetryRegistration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.nodes = []

    async def asyncTearDown(self):
        for node in reversed(self.nodes):
            await node.stop()
        self.tmp.cleanup()

    async def node(self, name, offline=False):
        root = self.root/name
        ident = mesh.create_account(root, name, 'long-password-for-test-12345678')
        node = mesh.MeshNode(ident, root, notify=lambda _: None, offline_only=offline)
        await node.start('127.0.0.1', 0)
        self.nodes.append(node)
        return node

    async def test_worker_connect_remembers_once_and_does_not_remove_saved_hosts(self):
        relay = await self.node('Relay')
        user = await self.node('Alice')
        endpoint = '127.0.0.1:' + str(relay.current_port)
        session = Session(self.root / 'worker')
        session.node = user
        user.relay_add('example.org:6667', 'Community server')
        with patch('mesh_bridge.emit'):
            await session.execute({'action': 'connect', 'endpoint': endpoint})
        self.assertEqual(user.retry_targets, [endpoint])
        user.remember_retry(endpoint)
        self.assertEqual(user.retry_targets, [endpoint])
        self.assertTrue(user.auto_reconnect)
        self.assertIn('example.org:6667', [x['endpoint'] for x in user.relay_rows()])

    async def test_offline_mode_never_reconnects(self):
        user = await self.node('Offline', offline=True)
        user.remember_retry('127.0.0.1:6667')
        self.assertEqual(user.retry_targets, [])
        self.assertFalse(user.auto_reconnect)

    async def test_verify_then_rotate_does_not_raise_stale_attribute_error(self):
        user = await self.node('Alice')
        endpoint = '127.0.0.1:6667'
        old, new = 'aaaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbbb'
        user.pins[endpoint] = old
        mesh.secure_save(user.pins_path, user.pins)
        user.replace_trusted_fingerprint(endpoint, old, new)
        self.assertEqual(user.pins[endpoint], new)
        self.assertEqual(mesh.secure_load(user.pins_path)[endpoint], new)


if __name__ == '__main__':
    unittest.main()
