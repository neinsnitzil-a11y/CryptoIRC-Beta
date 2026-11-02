"""Actual local network checks for the VaultForge-compatible desktop chat engine.

No network calls to AWS, no actual wallets, and no real-money transactions.
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]
MESH=SRC/'vaultmesh'
if str(MESH) not in sys.path:sys.path.insert(0,str(MESH))
import mesh_chat as vc
from mesh_gui import worker_command


class GuiMeshTransport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='nocturne-mesh-e2e-')
        self.home=Path(self.tmp.name)
        self.nodes=[]

    async def asyncTearDown(self):
        for node in reversed(self.nodes):
            await node.stop()
        self.tmp.cleanup()

    async def node(self,nick,**kwargs):
        folder=self.home/nick
        ident=vc.create_account(folder,nick,'long-unrelated-test-password-xyz')
        node=vc.MeshNode(ident,folder,notify=lambda _: None,**kwargs)
        await node.start('127.0.0.1',0)
        self.nodes.append(node)
        return node

    async def test_gui_and_cli_mesh_use_same_wire_protocol(self):
        relay=await self.node('Relay',relay_mode=True)
        alice=await self.node('Alice')
        bobby=await self.node('Bobby')
        target=f'127.0.0.1:{relay.current_port}'
        await alice.connect(target)
        await bobby.connect(target)
        await asyncio.sleep(0.3)
        await alice.send_chat('A signed channel message from the desktop UI')
        for _ in range(30):
            if any('signed channel message' in row[2] for row in bobby.inbox):break
            await asyncio.sleep(0.1)
        self.assertTrue(any('signed channel message' in row[2] for row in bobby.inbox))
        self.assertEqual(alice.pins[target],relay.ident.keyid)
        self.assertEqual(bobby.pins[target],relay.ident.keyid)

    async def test_relay_persists_public_history_for_later_join(self):
        relay=await self.node('Relay',relay_mode=True)
        alice=await self.node('Alice')
        await alice.connect(f'127.0.0.1:{relay.current_port}')
        await alice.send_chat('Message sent before Clara joined')
        await asyncio.sleep(0.3)
        self.assertTrue(relay.history.entries('#general'))
        clara=await self.node('Clara')
        await clara.connect(f'127.0.0.1:{relay.current_port}')
        for _ in range(30):
            if clara.history.entries('#general'):break
            await asyncio.sleep(0.1)
        self.assertTrue(any('before Clara joined' in r['data']['text'] for r in clara.history.entries('#general')))

    async def test_signed_public_node_directory(self):
        relay=await self.node('Relay',relay_mode=True,advertise='18.188.145.207:6667')
        user=await self.node('Alice')
        await user.connect(f'127.0.0.1:{relay.current_port}')
        for _ in range(30):
            if user.listed_public():break
            await asyncio.sleep(0.1)
        self.assertTrue(any(row[2]=='18.188.145.207:6667' and row[1]==relay.ident.keyid for row in user.listed_public()))

    async def test_encrypted_file_offer_requires_accept(self):
        relay=await self.node('Relay',relay_mode=True)
        alice=await self.node('Alice')
        bobby=await self.node('Bobby')
        await alice.connect(f'127.0.0.1:{relay.current_port}')
        await bobby.connect(f'127.0.0.1:{relay.current_port}')
        for _ in range(40):
            if bobby.ident.keyid in alice.boxkeys and bobby.ident.keyid in alice.presence:break
            await asyncio.sleep(0.1)
        original=b'not a real wallet secret - only harmless test attachment data'
        path=self.home/'sample.jpg'
        path.write_bytes(original)
        await alice.files.send(bobby.ident.keyid,str(path))
        for _ in range(40):
            if any('content' in tx for tx in bobby.files.pending.values()):break
            await asyncio.sleep(0.1)
        self.assertTrue(any('content' in tx for tx in bobby.files.pending.values()))
        self.assertFalse((bobby.root/'downloads'/'sample.jpg').exists())
        ident=next(iter(bobby.files.pending))
        dest=bobby.files.accept(ident)
        self.assertEqual(dest.read_bytes(),original)
        self.assertFalse((relay.root/'downloads'/'sample.jpg').exists())

    async def test_offline_mode_refuses_public_address(self):
        local=await self.node('OfflineUser',offline_only=True)
        with self.assertRaisesRegex(ValueError,'OFFLINE'):
            await local.connect('18.188.145.207:6667')


class GuiSourceChecks(unittest.TestCase):
    def test_desktop_launches_independent_worker(self):
        cmd=worker_command()
        self.assertTrue('--mesh-bridge' in cmd or cmd[-1].endswith('mesh_bridge.py'))
    def test_chat_runtime_does_not_import_wallet_logic(self):
        text=(MESH/'security_center.py').read_text(encoding='utf-8')
        self.assertNotIn('import wallet_core',text)
        self.assertNotIn('import transfer_engine',text)
    def test_builder_bundles_worker_modules(self):
        spec=(SRC/'CRYPTO_NOCTURNE.spec').read_text(encoding='utf-8')
        self.assertIn("'vaultmesh'",spec)
        self.assertIn('mesh_bridge', (SRC/'crypto.py').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
