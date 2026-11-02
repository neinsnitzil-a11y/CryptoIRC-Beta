"""Desktop remote roster controls and authenticated refresh across a relay."""
from __future__ import annotations
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
if str(SRC / 'vaultmesh') not in sys.path: sys.path.insert(0, str(SRC / 'vaultmesh'))
from mesh_gui import remote_user_rows, should_auto_connect
from mesh_bridge import Session
import mesh_chat as mesh


class DesktopRosterControls(unittest.TestCase):
    def test_remote_list_does_not_show_local_user(self):
        self.assertEqual(remote_user_rows([{'nick': 'Local', 'id': 'a', 'rooms': 'you'},
                                          {'nick': 'Alice', 'id': 'b', 'rooms': '#general'}]),
                         [{'nick': 'Alice', 'id': 'b', 'rooms': '#general'}])
        self.assertEqual(remote_user_rows([{'nick': 'Local', 'rooms': 'you'}]), [])

    def test_auto_connect_only_when_signed_in_online_mode_and_endpoint(self):
        self.assertTrue(should_auto_connect(True, True, 'WAN / AWS', '18.188.145.207:6667'))
        self.assertTrue(should_auto_connect(True, True, 'Tor required', 'somenode.onion:7777'))
        self.assertFalse(should_auto_connect(False, True, 'WAN / AWS', 'example:7777'))
        self.assertFalse(should_auto_connect(True, False, 'WAN / AWS', 'example:7777'))
        self.assertFalse(should_auto_connect(True, True, 'Offline LAN', '18.188.145.207:6667'))
        self.assertFalse(should_auto_connect(True, True, 'WAN / AWS', ' '))


class SignedPresenceRefresh(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.nodes = []

    async def asyncTearDown(self):
        for node in reversed(self.nodes): await node.stop()
        self.tmp.cleanup()

    async def start(self, nick, relay=False):
        path = self.root / nick
        ident = mesh.create_account(path,nick, 'test-private-long-password-not-for-money')
        node = mesh.MeshNode(ident,path,notify=lambda _: None,relay_mode=relay)
        await node.start('127.0.0.1',0)
        self.nodes.append(node)
        return node

    async def until(self, fn):
        async def poll():
            while not fn(): await asyncio.sleep(.02)
        await asyncio.wait_for(poll(),5)

    async def test_refresh_replays_authenticated_remote_presence(self):
        relay = await self.start('Relay',relay=True)
        alice = await self.start('Alice')
        bob = await self.start('Bobby')
        addr = f'127.0.0.1:{relay.current_port}'
        await alice.connect(addr)
        await bob.connect(addr)
        await self.until(lambda: bob.ident.keyid in alice.presence and bob.ident.keyid in relay.signed_presence)
        # Simulate a GUI roster that missed a peer's initial signed presence.
        alice.presence.pop(bob.ident.keyid,None)
        alice.signed_presence.pop(bob.ident.keyid,None)
        # A genuinely missed announcement also has no de-duplication record.
        signed = relay.signed_presence[bob.ident.keyid]
        alice.seen.pop(bob.ident.keyid + ':' + signed['id'], None)
        session = Session(self.root/'Desktop')
        session.node = alice
        await session.execute({'action':'refresh_roster'})
        await self.until(lambda: bob.ident.keyid in alice.presence)
        snap = session.snapshot()
        self.assertTrue(snap['connected'])
        self.assertIn(bob.ident.keyid,{u['id'] for u in snap['users']})
        self.assertEqual(len(remote_user_rows(snap['users'])),2) # relay and Bobby

    async def test_refresh_without_remote_links_does_not_create_fake_users(self):
        alice = await self.start('Alice')
        session = Session(self.root/'Desktop')
        session.node = alice
        await session.execute({'action':'refresh_roster'})
        snapshot = session.snapshot()
        self.assertFalse(snapshot['connected'])
        self.assertEqual(remote_user_rows(snapshot['users']),[])

if __name__ == '__main__': unittest.main()
