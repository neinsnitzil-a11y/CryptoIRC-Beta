"""Mesh 2.7.2 client tests: authenticated roster refresh, reconnect and preferences."""
import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mesh_chat as mesh
import vaultforge


class RosterRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.nodes = []
        self.sec = patch('security_center.load_settings', return_value={'mode': 'direct', 'port': 9050})
        self.sec.start()

    async def asyncTearDown(self):
        for node in self.nodes:
            await node.stop()
        self.sec.stop()
        self.tmp.cleanup()

    async def node(self, nick, *, relay=False, offline=False):
        path = self.root / nick
        ident = mesh.create_account(path, nick, 'secure secret password')
        node = mesh.MeshNode(ident, path, notify=lambda _:None, relay_mode=relay, offline_only=offline)
        self.nodes.append(node)
        with redirect_stdout(io.StringIO()):
            await node.start('127.0.0.1', 0)
        return node

    async def until(self, pred):
        async def poll():
            while not pred():
                await asyncio.sleep(0.03)
        await asyncio.wait_for(poll(), 3)

    async def test_signed_roster_refresh_works_with_old_intro_protocol(self):
        relay = await self.node('relay', relay=True)
        alice = await self.node('alice')
        bob = await self.node('bobby')
        ep = f'127.0.0.1:{relay.current_port}'
        await alice.connect(ep)
        await bob.connect(ep)
        await alice.announce()
        await bob.announce()
        await self.until(lambda: len(alice.remote_users()) == 2 and len(bob.remote_users()) == 2)
        self.assertEqual({u[0] for u in alice.remote_users()}, {'relay','bobby'})
        self.assertTrue(all(u[1] != alice.ident.keyid for u in alice.remote_users()))
        with redirect_stdout(io.StringIO()) as out:
            await alice.command('/refresh')
        self.assertIn('[REFRESH]', out.getvalue())
        self.assertEqual(len(alice.links), 1)
        self.assertEqual(len(alice.remote_users()), 2)
        # Refresh requests must stay in the older v2.7.1 frame vocabulary.
        self.assertNotIn('roster_request', out.getvalue())

    async def test_refresh_no_links_and_throttled(self):
        alice = await self.node('alice')
        with redirect_stdout(io.StringIO()) as out:
            await alice.command('/refresh')
            await alice.command('/refresh')
            await alice.command('/status')
        result = out.getvalue()
        self.assertIn('No authenticated remote peer', result)
        self.assertIn('allow 5 seconds', result)
        self.assertIn('DISCONNECTED', result)

    async def test_manual_connect_remembers_reconnect_endpoint(self):
        relay = await self.node('relay', relay=True)
        alice = await self.node('alice')
        ep = f'127.0.0.1:{relay.current_port}'
        with redirect_stdout(io.StringIO()):
            await alice.command('/connect ' + ep)
        await self.until(lambda: len(alice.links) == 1)
        self.assertEqual(alice.retry_targets, [ep])
        self.assertTrue(alice.auto_reconnect)
        for link in tuple(alice.links): link.close()
        await self.until(lambda: not alice.links)
        with redirect_stdout(io.StringIO()):
            await alice.command('/reconnect')
        await self.until(lambda: len(alice.links) == 1)

    async def test_no_auto_reconnect_in_offline_or_opt_out(self):
        offline = await self.node('alice', offline=True)
        offline.remember_retry('127.0.0.1:7777')
        self.assertFalse(offline.retry_targets)
        other = await self.node('bobby')
        other.allow_auto_reconnect = False
        other.remember_retry('127.0.0.1:7777')
        self.assertFalse(other.retry_targets)
        with redirect_stdout(io.StringIO()) as out:
            await offline.command('/reconnect')
        self.assertIn('disabled', out.getvalue())


class AutoConnectPreferenceTests(unittest.TestCase):
    def test_configure_and_login_auto_aws(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(mesh, 'secure_root', return_value=root), \
                 patch('builtins.input', side_effect=['19', '18.188.145.207:6667', 'y']), \
                 patch.object(vaultforge, 'run_mesh_chat') as run, \
                 redirect_stdout(io.StringIO()):
                vaultforge.mesh_connect_menu()
            self.assertFalse(run.called)
            saved = mesh.secure_load(root / 'client_preferences.json')
            self.assertTrue(saved['aws_auto_connect'])
            with patch.object(mesh, 'secure_root', return_value=root), \
                 patch('builtins.input', side_effect=['18']), \
                 patch.object(vaultforge, 'run_mesh_chat') as run, \
                 redirect_stdout(io.StringIO()):
                vaultforge.mesh_connect_menu()
            self.assertEqual(run.call_args.args[0],
                             ['--listen', '127.0.0.1:0', '--peer', '18.188.145.207:6667'])

    def test_disabled_auto_connect_never_dials(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mesh, 'secure_root', return_value=Path(d)), \
                 patch('builtins.input', return_value='18'), \
                 patch.object(vaultforge, 'run_mesh_chat') as run, \
                 redirect_stdout(io.StringIO()) as out:
                vaultforge.mesh_connect_menu()
            self.assertFalse(run.called)
            self.assertIn('Disabled', out.getvalue())

    def test_cli_source_version(self):
        self.assertIn('2.7.2', vaultforge.VERSION)
