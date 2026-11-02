"""LAN discovery, offline fail-closed guards and menu functionality."""
import asyncio
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mesh_chat as m
import vaultforge as v


class LocalNetworkingUnitTests(unittest.TestCase):
    def test_offline_lan_ipv4_ipv6_only(self):
        for ip in ('10.0.1.4', '192.168.1.2', '172.31.39.156', '127.0.0.1',
                   '169.254.9.10', 'localhost', '::1', 'fc00::1', 'fe80::1'):
            self.assertTrue(m.is_lan_host(ip), ip)
        for ip in ('18.188.145.207', '8.8.8.8', 'example.org', 'abc.onion',
                   '0.0.0.0', '255.255.255.255', '192.0.2.3'):
            self.assertFalse(m.is_lan_host(ip), ip)

    def test_client_connection_modes_menu(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(m, 'secure_root', return_value=Path(d)):
                cases = [(['5', '198.51.100.2:8000'], ['--listen', '127.0.0.1:0', '--peer', '198.51.100.2:8000']),
                         (['6', ''], ['--listen', '0.0.0.0:6667', '--relay', '--no-auto-connect']),
                         (['7', ''], ['--listen', '0.0.0.0:7777', '--offline', '--no-auto-connect', '--lan']),
                         (['8'], ['--listen', '0.0.0.0:7778', '--offline', '--no-auto-connect', '--lan']),
                         (['9'], ['--scan'])]
                for answers, expected in cases:
                    with self.subTest(answers=answers), patch('builtins.input', side_effect=answers):
                        with patch.object(v, 'run_mesh_chat') as launch, contextlib.redirect_stdout(io.StringIO()):
                            v.mesh_connect_menu()
                        launch.assert_called_once_with(expected)

    def test_aws_preset_and_custom_endpoint(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m, 'secure_root', return_value=Path(d)):
            with patch('builtins.input', side_effect=['1','']), patch.object(v,'run_mesh_chat') as launch, contextlib.redirect_stdout(io.StringIO()):
                v.mesh_connect_menu()
            launch.assert_called_once_with(['--listen', '127.0.0.1:0', '--peer', '18.188.145.207:6667'])


class LanDiscoveryNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_signed_discovery_matches_running_local_peer(self):
        with tempfile.TemporaryDirectory() as d:
            who = m.create_account(Path(d), 'Alice', 'super_secure_password_Alice')
            node = m.MeshNode(who, Path(d), notify=lambda msg: None, offline_only=True, lan_discovery=True)
            await node.start('127.0.0.1', 0)
            try:
                self.assertIsNotNone(node.discovery_transport)
                results = await m.scan_lan(.15, ('127.0.0.1',))
                self.assertTrue(any(r[0] == 'Alice' and r[1] == who.keyid and r[2] == f'127.0.0.1:{node.current_port}' for r in results), results)
            finally:
                await node.stop()

    async def test_offline_rejects_public_peer_before_dns_or_socket(self):
        with tempfile.TemporaryDirectory() as d:
            who = m.create_account(Path(d), 'Alice', 'super_secure_password_Alice')
            node = m.MeshNode(who, Path(d), notify=lambda msg: None, offline_only=True)
            with patch('asyncio.open_connection') as sock:
                with self.assertRaisesRegex(ValueError, 'OFFLINE'):
                    await node.connect('18.188.145.207:6667')
                with self.assertRaisesRegex(ValueError, 'OFFLINE'):
                    await node.connect('example.org:6667')
                sock.assert_not_called()

    async def test_two_offline_lan_peers_exchange_messages(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            alice = m.MeshNode(m.create_account(Path(a),'Alice','long_alice_password123'), Path(a), notify=lambda _: None, offline_only=True)
            bob = m.MeshNode(m.create_account(Path(b),'Bobby','long_bobby_password123'), Path(b), notify=lambda _: None, offline_only=True)
            await alice.start('127.0.0.1', 0)
            await bob.start('127.0.0.1', 0)
            try:
                await alice.connect(f'127.0.0.1:{bob.current_port}')
                await asyncio.sleep(.1)
                await alice.send_chat('Hello from an offline LAN')
                await asyncio.sleep(.1)
                self.assertTrue(any('Hello from an offline LAN' in str(line) for line in bob.inbox))
            finally:
                await alice.stop()
                await bob.stop()


if __name__ == '__main__':
    unittest.main()
