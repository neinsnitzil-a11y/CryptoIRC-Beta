"""Trust-rotation behavior, 2.7.6: detect automatically, never accept automatically."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import mesh_chat as mesh


class TrustRotation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)
        self.nodes=[]
        self.setting=patch('security_center.load_settings', return_value={'mode':'direct','port':9050})
        self.setting.start()

    async def asyncTearDown(self):
        for n in reversed(self.nodes): await n.stop()
        self.setting.stop()
        self.temp.cleanup()

    async def node(self, name):
        home=self.path/name
        identity=mesh.create_account(home,name,'long-password-not-wallet-123456')
        node=mesh.MeshNode(identity,home,notify=lambda x:None)
        await node.start('127.0.0.1',0)
        self.nodes.append(node)
        return node

    async def test_auto_detect_without_changing_pin(self):
        server=await self.node('Server')
        client=await self.node('Client')
        endpoint=f'127.0.0.1:{server.current_port}'
        old='f704e415f7ffc6dd'
        client.pins[endpoint]=old
        mesh.secure_save(client.pins_path,client.pins)
        with self.assertRaises(mesh.PeerIdentityChanged) as caught:
            await client.connect(endpoint)
        exc=caught.exception
        self.assertEqual((exc.endpoint,exc.pinned,exc.presented),(endpoint,old,server.ident.keyid))
        self.assertEqual(mesh.secure_load(client.pins_path)[endpoint],old)
        self.assertFalse(client.links)

    async def test_explicit_rotation_then_connect_and_preserve_other_peers(self):
        server=await self.node('Server')
        client=await self.node('Client')
        endpoint=f'127.0.0.1:{server.current_port}'
        original='f704e415f7ffc6dd'
        client.pins.update({endpoint:original,'others.example:6667':'1234567890abcdef'})
        mesh.secure_save(client.pins_path,client.pins)
        with self.assertRaisesRegex(ValueError,'changed'):
            client.replace_trusted_fingerprint(endpoint,'ffffffffffffffff',server.ident.keyid)
        self.assertEqual(mesh.secure_load(client.pins_path)[endpoint],original)
        client.replace_trusted_fingerprint(endpoint,original,server.ident.keyid)
        self.assertEqual(mesh.secure_load(client.pins_path)['others.example:6667'],'1234567890abcdef')
        backups=list(client.root.glob('known_peers.pre-rotation-*.json'))
        self.assertEqual(len(backups),1)
        self.assertEqual(mesh.secure_load(backups[0])[endpoint],original)
        await client.connect(endpoint)
        self.assertEqual(len(client.links),1)
        self.assertEqual(next(iter(client.links)).keyid,server.ident.keyid)

    async def test_user_cancel_leaves_pin_untouched(self):
        server=await self.node('Server')
        client=await self.node('Client')
        endpoint=f'127.0.0.1:{server.current_port}'
        client.pins[endpoint]='f704e415f7ffc6dd'
        mesh.secure_save(client.pins_path,client.pins)
        exc=mesh.PeerIdentityChanged(endpoint,client.pins[endpoint],server.ident.keyid)
        with patch('sys.stdin.isatty',return_value=True), patch('builtins.input',return_value=''):
            self.assertFalse(await client.offer_trust_rotation(exc))
        self.assertEqual(mesh.secure_load(client.pins_path)[endpoint],'f704e415f7ffc6dd')

    async def test_user_verified_prompt_rotation(self):
        server=await self.node('Server')
        client=await self.node('Client')
        endpoint=f'127.0.0.1:{server.current_port}'
        client.pins[endpoint]='f704e415f7ffc6dd'
        mesh.secure_save(client.pins_path,client.pins)
        exc=mesh.PeerIdentityChanged(endpoint,client.pins[endpoint],server.ident.keyid)
        with patch('sys.stdin.isatty',return_value=True), patch('builtins.input',return_value='YES'):
            self.assertTrue(await client.offer_trust_rotation(exc))
        self.assertEqual(mesh.secure_load(client.pins_path)[endpoint],server.ident.keyid)

if __name__ == '__main__': unittest.main()
