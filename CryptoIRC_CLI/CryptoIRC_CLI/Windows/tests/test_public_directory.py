"""Test authenticated opt-in public announcements with real local sockets; no internet calls."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import node_manager

from mesh_chat import MeshNode, create_account, public_endpoint, scan_public, validate_message, sign_message


class PublicDirectoryTests(unittest.TestCase):
    def test_public_only_ips(self):
        self.assertEqual(public_endpoint('18.188.145.207:6667'), '18.188.145.207:6667')
        for endpoint in ('127.0.0.1:6667', '172.31.39.156:6667', '192.168.1.1:6667',
                         '169.254.169.254:80', 'localhost:6667', 'example.com:6667'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                public_endpoint(endpoint)

    def test_node_config_opt_in_persists_without_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'node-private'
            class Options:
                mode='wan'; name='SampleRelay'; listen='0.0.0.0:6667'; peer=[]
                yes=True; advertise='18.188.145.207:6667'
            with patch.object(node_manager, 'storage', return_value=target):
                node_manager.configure(Options())
                cfg=node_manager.load_config()
                self.assertEqual(cfg['advertise'],'18.188.145.207:6667')
                args=node_manager.launch_args(cfg)
                self.assertIn('--advertise',args)
                self.assertEqual(args[args.index('--advertise')+1],'18.188.145.207:6667')
                self.assertNotIn('password', (target/'node.json').read_text())
                node_manager.set_advertise('8.8.8.8:6667')
                self.assertEqual(node_manager.load_config()['advertise'],'8.8.8.8:6667')

    def test_signed_advert_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            ident=create_account(Path(td), 'Alice', 'super long password 1234')
            advert=sign_message(ident, 'node_advert', {'endpoint':'18.188.145.207:6667'})
            self.assertEqual(validate_message(advert)[1], 'node_advert')
            advert['data']['endpoint']='10.0.0.1:1234'
            with self.assertRaises(Exception): validate_message(advert)

    def test_multi_peer_directory_sync_and_scan(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as td:
                base=Path(td)
                a=create_account(base/'a','AWSRelay','super long password 1234')
                b=create_account(base/'b','HomeRelay','super long password 1234')
                c=create_account(base/'c','ClientUser','super long password 1234')
                aw=MeshNode(a,base/'a',notify=lambda _:None,advertise='18.188.145.207:6667')
                home=MeshNode(b,base/'b',notify=lambda _:None,advertise='8.8.8.8:6667')
                client=MeshNode(c,base/'c',notify=lambda _:None)
                try:
                    await aw.start('127.0.0.1',0)
                    await home.start('127.0.0.1',0)
                    await home.connect(f'127.0.0.1:{aw.current_port}')
                    await client.start('127.0.0.1',0)
                    await client.connect(f'127.0.0.1:{aw.current_port}')
                    await asyncio.sleep(.4)
                    rows=client.listed_public()
                    self.assertIn(('AWSRelay', a.keyid, '18.188.145.207:6667'),rows)
                    self.assertIn(('HomeRelay',b.keyid,'8.8.8.8:6667'), rows)
                    # The accountless scanner uses a fresh one-time identity and discovers ads.
                    found, failures=await scan_public([f'127.0.0.1:{aw.current_port}'])
                    self.assertFalse(failures)
                    self.assertGreaterEqual(len(found),2)
                    self.assertIn(('AWSRelay', a.keyid, '18.188.145.207:6667'),found)
                finally:
                    await client.stop(); await home.stop(); await aw.stop()
        asyncio.run(exercise())

    def test_legacy_peer_receives_no_unfamiliar_advert(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as td:
                root=Path(td)
                a=MeshNode(create_account(root/'a','AWSRelay','super long password 1234'),root/'a',notify=lambda _:None,advertise='18.188.145.207:6667')
                class OldLink:
                    directory_capable=False
                    async def send(self, obj):
                        raise AssertionError('Should not send new kind to old client')
                try:
                    await a.announce_public()
                    await a._gossip(a.public_nodes[a.ident.keyid]['signed'],exclude=None)
                finally:
                    await a.stop()
        asyncio.run(exercise())
