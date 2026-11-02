"""Offline end-to-end encrypted attachment and node manager regression tests."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import mesh_chat as mesh
import node_manager as manager
from file_transfer import FileTransfers, MAX_FILE_BYTES, safe_filename


class FileValidation(unittest.TestCase):
    def test_safe_names(self):
        self.assertEqual(safe_filename('../hello.png'), 'hello.png')
        self.assertEqual(safe_filename('a\\b.png'), 'b.png')
        with self.assertRaises(ValueError):
            safe_filename('..')

    def test_node_config_keeps_private_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = mesh.secure_root(Path(tmp) / 'chat')
            class Args:
                mode='lan'; name='LocalNode'; listen='127.0.0.1:7777'; peer=[]; yes=False
            with patch.object(manager, 'storage', return_value=root):
                manager.configure(Args())
                cfg = manager.load_config()
                self.assertEqual(cfg['mode'], 'lan')
                self.assertNotIn('password', (root / 'node.json').read_text())
                self.assertNotIn('password', (root / 'accounts.json').read_text())
                if manager.os.name != 'nt':
                    self.assertEqual((root / 'node.secret').stat().st_mode & 0o777, 0o600)
                with self.assertRaises(ValueError):
                    manager.configure(Args())


class EncryptedFileNetwork(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.alice=mesh.create_account(root/'alice','alice','long secret alice password')
        self.bob=mesh.create_account(root/'bob','bobby','long secret bobby password')
        self.relay=mesh.create_account(root/'relay','relay','long secret relay password')
        self.aa=mesh.MeshNode(self.alice, root/'alice', notify=lambda _:None)
        self.bb=mesh.MeshNode(self.bob, root/'bob', notify=lambda _:None)
        self.rr=mesh.MeshNode(self.relay, root/'relay', notify=lambda _:None)
        self.patch=patch('security_center.load_settings',return_value={'mode':'direct','port':9050})
        self.patch.start()
        for node in (self.aa,self.bb,self.rr):
            await node.start('127.0.0.1',0)
        await self.aa.connect(f'127.0.0.1:{self.rr.current_port}')
        await self.bb.connect(f'127.0.0.1:{self.rr.current_port}')
        for node in (self.aa,self.bb,self.rr):
            await node.announce()
        async def ready():
            while self.bob.keyid not in self.aa.presence:
                await asyncio.sleep(.02)
        await asyncio.wait_for(ready(),4)

    async def asyncTearDown(self):
        for n in (self.aa,self.bb,self.rr):
            await n.stop()
        self.patch.stop()
        self.tmp.cleanup()

    async def test_file_e2e_over_relay_and_manual_accept(self):
        source=Path(self.tmp.name)/'photo.png'
        data=b'fake PNG test content'*50
        source.write_bytes(data)
        await self.aa.files.send(self.bob.keyid,str(source))
        async def received():
            while not any('content' in t for t in self.bb.files.pending.values()):
                await asyncio.sleep(.02)
        await asyncio.wait_for(received(),5)
        self.assertFalse(self.rr.files.pending)
        file_id=next(iter(self.bb.files.pending))
        self.assertFalse((self.bb.root/'downloads'/'photo.png').exists())
        stored=self.bb.files.accept(file_id)
        self.assertEqual(stored.read_bytes(),data)

    async def test_oversize_or_missing_files_rejected(self):
        with self.assertRaises(ValueError):
            await self.aa.files.send(self.bob.keyid, str(Path(self.tmp.name)/'absent.txt'))
        huge=Path(self.tmp.name)/'huge.bin'
        with huge.open('wb') as f:
            f.truncate(MAX_FILE_BYTES+1)
        with self.assertRaises(ValueError):
            await self.aa.files.send(self.bob.keyid, str(huge))
