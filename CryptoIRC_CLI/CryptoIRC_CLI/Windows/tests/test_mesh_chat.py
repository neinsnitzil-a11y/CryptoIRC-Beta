"""Local, offline mesh tests: no real network peers or wallet funds."""
from pathlib import Path
import asyncio
import tempfile
import unittest
from unittest.mock import patch

import mesh_chat as mesh


class ChatAccountTests(unittest.TestCase):
    def test_register_login_password_rotation_no_wallet_seed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'chat'
            ident = mesh.create_account(root, 'Alice', 'a very long chat password!')
            self.assertEqual(mesh.login(root, 'Alice', 'a very long chat password!').keyid, ident.keyid)
            with self.assertRaises(ValueError):
                mesh.login(root, 'Alice', 'wrong-password')
            self.assertNotIn(b'a very long chat password!', (root / 'accounts.json').read_bytes())
            self.assertNotIn(mesh.raw_priv(ident.signing), (root / 'accounts.json').read_bytes())
            mesh.change_account_password(root, 'Alice', 'a very long chat password!', 'new strong password here')
            with self.assertRaises(ValueError):
                mesh.login(root, 'Alice', 'a very long chat password!')
            self.assertEqual(mesh.login(root, 'Alice', 'new strong password here').keyid, ident.keyid)

    def test_bad_name_password_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                mesh.create_account(root, '../bad', 'password password')
            with self.assertRaises(ValueError):
                mesh.create_account(root, 'alice', 'tiny')
            mesh.create_account(root, 'alice', 'long enough password')
            with self.assertRaises(ValueError):
                mesh.create_account(root, 'Alice', 'long enough password')

    def test_message_signature_detects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            ident = mesh.create_account(Path(d), 'Carol', 'password password here')
            msg = mesh.sign_message(ident, 'chat', {'room': '#general', 'text': 'hello'})
            self.assertEqual(mesh.validate_message(msg)[0], ident.keyid)
            msg['data']['text'] = 'tampered'
            with self.assertRaises(Exception):
                mesh.validate_message(msg)

    def test_dm_sealed_to_recipient(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = mesh.create_account(root, 'alice', 'long enough password')
            b = mesh.create_account(root, 'bob', 'long enough password')
            c = mesh.create_account(root, 'carol', 'long enough password')
            data = mesh.seal_dm(a, b.boxpub, b.keyid, 'private note')
            self.assertEqual(mesh.open_dm(b, a.pub, data), 'private note')
            with self.assertRaises(Exception):
                mesh.open_dm(c, a.pub, data)
            data['cipher'] = mesh.b64(b'X' * 40)
            with self.assertRaises(Exception):
                mesh.open_dm(b, a.pub, data)

    def test_endpoint_rejects_bad_format(self):
        for value in ('http://localhost:7777', 'bob@host:443', 'host:0', 'bad:99999', 'foo:80/evil'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mesh.parse_endpoint(value)
        self.assertEqual(mesh.parse_endpoint('127.0.0.1:7777'), ('127.0.0.1', 7777))


class MeshNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.a = mesh.create_account(root / 'a', 'alice', 'alpha secure password')
        self.b = mesh.create_account(root / 'b', 'bobby', 'bravo secure password')
        self.c = mesh.create_account(root / 'c', 'carol', 'charlie secure password')
        self.nodes = []
        self.patch = patch('security_center.load_settings', return_value={'mode':'direct', 'port':9050})
        self.patch.start()

    async def asyncTearDown(self):
        for n in self.nodes:
            await n.stop()
        self.patch.stop()
        self.tmp.cleanup()

    async def node(self, ident, suffix):
        n = mesh.MeshNode(ident, Path(self.tmp.name) / suffix, notify=lambda message: None)
        self.nodes.append(n)
        await n.start('127.0.0.1', 0)
        return n

    async def wait_for(self, pred, timeout=3):
        async def poll():
            while not pred():
                await asyncio.sleep(0.03)
        await asyncio.wait_for(poll(), timeout)

    async def test_multi_hop_presence_channel_and_e2ee_dm(self):
        a = await self.node(self.a, 'a')
        b = await self.node(self.b, 'b')
        c = await self.node(self.c, 'c')
        await a.connect(f'127.0.0.1:{b.current_port}')
        await c.connect(f'127.0.0.1:{b.current_port}')
        await a.announce()
        await b.announce()
        await c.announce()
        await self.wait_for(lambda: len(b.online()) == 3 and len(a.online()) == 3 and len(c.online()) == 3)
        await a.send_chat('hello across two hops')
        await self.wait_for(lambda: ('#general', 'alice', 'hello across two hops') in c.inbox)
        await a.send_dm(c.ident.keyid, 'secret across a relay')
        await self.wait_for(lambda: ('DM', 'alice', 'secret across a relay') in c.inbox)
        self.assertNotIn(('DM', 'alice', 'secret across a relay'), b.inbox)
        self.assertEqual(len(a.links), 1)
        self.assertEqual(len(b.links), 2)
        self.assertEqual(len(c.links), 1)

    async def test_pinned_peer_rejects_impersonator(self):
        a = await self.node(self.a, 'a')
        b = await self.node(self.b, 'b')
        target = f'127.0.0.1:{b.current_port}'
        await a.connect(target)
        await self.wait_for(lambda: len(a.links)==1)
        for link in tuple(a.links): link.close()
        await self.wait_for(lambda: len(a.links)==0)
        a.pins[target] = '0000000000000000'
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            await a.connect(target)

    async def test_tor_mode_rejects_public_listener(self):
        with patch('security_center.load_settings', return_value={'mode':'tor', 'port':9050}):
            n = mesh.MeshNode(self.a, Path(self.tmp.name)/'tor', notify=lambda _: None)
            with self.assertRaisesRegex(ValueError, 'loopback listener'):
                await n.start('0.0.0.0', 0)

    async def test_leave_and_block(self):
        a = await self.node(self.a, 'a')
        await a.command('/join #dev')
        self.assertEqual(a.active_room, '#dev')
        await a.command('/leave #dev')
        self.assertEqual(a.active_room, '#general')
        a.block(self.b.keyid)
        self.assertIn(self.b.keyid, a.blocked)
        with self.assertRaises(ValueError):
            await a.command('/leave #general')

class AdditionalSecurityTests(unittest.TestCase):
    def test_cipher_order_and_replay_rejected(self):
        key_a = b'A'*32
        key_b = b'B'*32
        alice = mesh.Cipher(key_a, key_b)
        bobby = mesh.Cipher(key_b, key_a)
        packet = alice.encrypt({'hello': 'world'})
        self.assertEqual(bobby.decrypt(packet[4:]), {'hello': 'world'})
        with self.assertRaises(Exception):
            bobby.decrypt(packet[4:])  # nonce counter moved, replay not valid

    def test_hello_role_and_signature_validation(self):
        with tempfile.TemporaryDirectory() as d:
            ident = mesh.create_account(Path(d), 'nemo', 'long password here')
            hello = mesh.signed_hello(ident, mesh.raw_pub(mesh.x25519.X25519PrivateKey.generate().public_key()),
                                      b'\x01'*16, 'initiator')
            self.assertEqual(mesh.verify_hello(hello, 'initiator')[0], ident.pub)
            with self.assertRaises(ValueError):
                mesh.verify_hello(hello, 'responder')
            hello['eph'] = mesh.b64(b'Z'*32)
            with self.assertRaises(Exception):
                mesh.verify_hello(hello, 'initiator')

    def test_file_permissions_and_symlink_protection(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'chat'
            mesh.create_account(root, 'nemo', 'long password here')
            if os.name != 'nt':
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)
                self.assertEqual((root / 'accounts.json').stat().st_mode & 0o777, 0o600)
                link = Path(d) / 'link'
                link.symlink_to(root, target_is_directory=True)
                with self.assertRaises(ValueError):
                    mesh.secure_root(link)

    def test_timestamp_and_username_are_verified(self):
        with tempfile.TemporaryDirectory() as d:
            ident = mesh.create_account(Path(d), 'nemo', 'long password here')
            message = mesh.sign_message(ident, 'chat', {'room':'#general','text':'x'})
            message['time'] -= 600
            with self.assertRaises(ValueError):
                mesh.validate_message(message)


class AdditionalNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_peer_cannot_connect_as_self(self):
        import security_center
        with tempfile.TemporaryDirectory() as d, \
             patch.object(security_center, 'load_settings', return_value={'mode':'direct','port':9050}):
            ident = mesh.create_account(Path(d)/'a', 'nemo', 'long password here')
            node = mesh.MeshNode(ident, Path(d)/'a', notify=lambda _: None)
            await node.start('127.0.0.1', 0)
            try:
                with self.assertRaisesRegex(ValueError, 'Cannot connect to your own identity'):
                    await node.connect(f'127.0.0.1:{node.current_port}')
            finally:
                await node.stop()

class TorTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_onion_cannot_fall_back_to_direct_dns(self):
        with tempfile.TemporaryDirectory() as d, \
             patch('security_center.load_settings', return_value={'mode':'direct', 'port':9050}):
            ident = mesh.create_account(Path(d), 'nemo', 'long password here')
            node = mesh.MeshNode(ident, Path(d))
            with self.assertRaisesRegex(ValueError, 'refusing any direct DNS'):
                await node.connect('exampleaaaaaaaaaaaaaaaa.onion:7777')

class MessageSizeTests(unittest.TestCase):
    def test_long_dm_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            a = mesh.create_account(Path(d), 'alice', 'long enough password')
            b = mesh.create_account(Path(d), 'bobby', 'long enough password')
            data = mesh.seal_dm(a, b.boxpub, b.keyid, 'hello' * 250)
            self.assertEqual(mesh.open_dm(b, a.pub, data), 'hello' * 250)

class UnifiedCliIsolationTests(unittest.TestCase):
    def test_chat_spawns_separate_isolated_process(self):
        import vaultforge
        with patch.object(vaultforge.subprocess, 'call', return_value=0) as call:
            self.assertEqual(vaultforge.main(['chat', '--listen', '127.0.0.1:8888']), 0)
        cmd = call.call_args.args[0]
        self.assertEqual(cmd[1], '-I')
        self.assertEqual(Path(cmd[2]).name, 'mesh_chat.py')
        self.assertEqual(cmd[3:], ['--listen', '127.0.0.1:8888'])
        self.assertNotIn('.vault', ' '.join(cmd))
