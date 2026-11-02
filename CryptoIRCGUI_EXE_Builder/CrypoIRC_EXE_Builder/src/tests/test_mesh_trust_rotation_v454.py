"""Verified relay key rotation in GUI worker; no wallet data and no AWS network calls."""
from __future__ import annotations
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1]
for loc in (SRC, SRC / 'vaultmesh'):
    if str(loc) not in sys.path: sys.path.insert(0, str(loc))
import mesh_chat as mesh
from mesh_bridge import Session
from mesh_gui import MeshGUI


class GuiTrustRotation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.nodes=[]

    async def asyncTearDown(self):
        for node in reversed(self.nodes):
            await node.stop()
        self.tmp.cleanup()

    async def node(self,nick):
        root=self.base/nick
        ident=mesh.create_account(root,nick,'long-password-for-test-not-wallet-12345')
        node=mesh.MeshNode(ident,root,notify=lambda _msg:None)
        await node.start('127.0.0.1',0)
        self.nodes.append(node)
        return node

    async def test_reject_old_pin_then_rotate_to_verified_key_then_connect(self):
        relay=await self.node('Relay')
        alice=await self.node('Alice')
        other='another.host:6667'
        endpoint=f'127.0.0.1:{relay.current_port}'
        old='f704e415f7ffc6dd'
        alice.pins.update({endpoint:old,other:'1234567890abcdef'})
        mesh.secure_save(alice.pins_path,alice.pins)
        with self.assertRaisesRegex(ValueError,'Peer identity changed'):
            await alice.connect(endpoint)
        self.assertFalse(alice.links)
        session=Session(self.base/'worker')
        session.node=alice
        with patch('mesh_bridge.emit') as emit:
            await session.execute({'action':'peer_trust_status','endpoint':endpoint})
            emit.assert_called_once_with('trust_status',endpoint=endpoint,pinned=old)
        with patch('mesh_bridge.emit') as emit:
            await session.execute({'action':'replace_peer_trust','endpoint':endpoint,
                                   'previous_id':old,'verified_id':relay.ident.keyid})
            emit.assert_called_once_with('trust_updated',endpoint=endpoint,
                                         old_id=old,new_id=relay.ident.keyid)
        self.assertEqual(alice.pins[endpoint],relay.ident.keyid)
        self.assertEqual(alice.pins[other],'1234567890abcdef')
        self.assertEqual(mesh.secure_load(alice.pins_path)[endpoint],relay.ident.keyid)
        backup=list(alice.root.glob('known_peers.pre-rotation-*.json'))
        self.assertEqual(len(backup),1)
        self.assertEqual(mesh.secure_load(backup[0])[endpoint],old)
        await session.execute({'action':'connect','endpoint':endpoint})
        self.assertTrue(alice.links)
        self.assertEqual(next(iter(alice.links)).keyid,relay.ident.keyid)

    async def test_cannot_change_pin_if_old_value_changed_or_user_not_logged_in(self):
        node=await self.node('Alice')
        session=Session(self.base/'worker')
        endpoint='127.0.0.1:6667'
        with self.assertRaisesRegex(ValueError,'Register or log in'):
            await session.execute({'action':'peer_trust_status','endpoint':endpoint})
        session.node=node
        node.pins[endpoint]='f704e415f7ffc6dd'
        with self.assertRaisesRegex(ValueError,'Saved trust changed'):
            await session.execute({'action':'replace_peer_trust','endpoint':endpoint,
                                   'previous_id':'aaaaaaaaaaaaaaaa','verified_id':'9aca2e4a28878448'})
        self.assertEqual(node.pins[endpoint],'f704e415f7ffc6dd')
        with self.assertRaisesRegex(ValueError,'16-character hex'):
            await session.execute({'action':'replace_peer_trust','endpoint':endpoint,
                                   'previous_id':'f704e415f7ffc6dd','verified_id':'unsafe'})
        self.assertEqual(node.pins[endpoint],'f704e415f7ffc6dd')
        with self.assertRaisesRegex(ValueError,'identical'):
            await session.execute({'action':'replace_peer_trust','endpoint':endpoint,
                                   'previous_id':'f704e415f7ffc6dd','verified_id':'f704e415f7ffc6dd'})
        self.assertFalse(list(node.root.glob('known_peers.pre-rotation-*.json')))

    async def test_reject_change_while_link_connected(self):
        relay=await self.node('Relay')
        node=await self.node('Alice')
        endpoint=f'127.0.0.1:{relay.current_port}'
        await node.connect(endpoint)
        session=Session(self.base/'worker')
        session.node=node
        with self.assertRaisesRegex(ValueError,'Disconnect the current peer'):
            await session.execute({'action':'replace_peer_trust','endpoint':endpoint,
                'previous_id':relay.ident.keyid,'verified_id':'9aca2e4a28878448'})
        self.assertEqual(node.pins[endpoint],relay.ident.keyid)

    def test_gui_has_explicit_trust_control(self):
        self.assertTrue(callable(MeshGUI._mesh_request_relay_trust))
        self.assertTrue(callable(MeshGUI._mesh_verify_relay_trust))

if __name__=='__main__':unittest.main()
