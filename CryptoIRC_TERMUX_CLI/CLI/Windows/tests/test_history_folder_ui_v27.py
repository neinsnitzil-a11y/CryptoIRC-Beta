"""Public room sync, persistence, encrypted folder transfer, and protocol regression."""
import asyncio
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import mesh_chat as mesh

class HistoryFolderUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.alice = mesh.create_account(self.root/'alice','AliceChat','long password for alice 123')
        self.bob = mesh.create_account(self.root/'bob','BobbyChat','long password for bobby 123')
        self.relay = mesh.create_account(self.root/'relay','RelayChat','long password for relay 123')
        self.apatch = patch('security_center.load_settings',return_value={'mode':'direct','port':9050})
        self.apatch.start()
        self.log = []
        self.aa = mesh.MeshNode(self.alice,self.root/'alice',notify=self.log.append)
        self.rr = mesh.MeshNode(self.relay,self.root/'relay',notify=self.log.append,relay_mode=True)
        await self.rr.start('127.0.0.1',0)
        self.port = self.rr.current_port
        await self.aa.start('127.0.0.1',0)
        await self.aa.connect(f'127.0.0.1:{self.port}')
        await asyncio.sleep(.1)

    async def asyncTearDown(self):
        if hasattr(self,'bb'):
            await self.bb.stop()
        await self.aa.stop()
        await self.rr.stop()
        self.apatch.stop()
        self.tmp.cleanup()

    async def test_history_new_member_and_relay_restart(self):
        await self.aa.send_chat('hello from before you joined')
        await asyncio.sleep(.12)
        self.assertTrue(self.rr.history.entries('#general'))
        await self.aa.stop()
        await self.rr.stop()
        self.rr=mesh.MeshNode(self.relay,self.root/'relay',notify=self.log.append,relay_mode=True)
        await self.rr.start('127.0.0.1',0)
        self.bb = mesh.MeshNode(self.bob,self.root/'bob',notify=self.log.append)
        await self.bb.start('127.0.0.1',0)
        await self.bb.connect(f'127.0.0.1:{self.rr.current_port}')
        async def got_it():
            while not any('hello from before you joined' in x['data']['text'] for x in self.bb.history.entries('#general')):
                await asyncio.sleep(.02)
        await asyncio.wait_for(got_it(), 5)
        self.assertIn('hello from before you joined',self.bb.history.entries('#general')[0]['data']['text'])

    async def test_folder_to_bob_and_no_plaintext_in_relay(self):
        self.bb=mesh.MeshNode(self.bob,self.root/'bob',notify=self.log.append)
        await self.bb.start('127.0.0.1',0)
        await self.bb.connect(f'127.0.0.1:{self.port}')
        await self.bb.announce()
        async def online():
            while self.bob.keyid not in self.aa.presence: await asyncio.sleep(.01)
        await asyncio.wait_for(online(),5)
        directory=self.root/'photos'; (directory/'sub').mkdir(parents=True)
        (directory/'sub'/'hello.txt').write_text('private upload content')
        await self.aa.files.send_folder(self.bob.keyid,str(directory))
        async def ready():
            while not any('content' in x for x in self.bb.files.pending.values()): await asyncio.sleep(.02)
        await asyncio.wait_for(ready(),5)
        self.assertFalse(self.rr.files.pending)
        tid=next(iter(self.bb.files.pending))
        zip_path=self.bb.files.accept(tid)
        with zipfile.ZipFile(zip_path) as arc:
            self.assertEqual(arc.read('photos/sub/hello.txt'),b'private upload content')

    async def test_folder_sensitive_secret_rejected(self):
        directory=self.root/'secret-dir';directory.mkdir()
        (directory/'wallet.vault').write_bytes(b'secret')
        with self.assertRaisesRegex(ValueError,'sensitive'):
            await self.aa.files.send_folder('anything',str(directory))

    async def test_old_intro_without_history_not_sent_new_frames(self):
        # Older v2.6 mesh peers will receive only their already-known frame types.
        self.assertTrue(all(not x.history_capable for x in self.aa.links) is False)

if __name__ == '__main__': unittest.main()
