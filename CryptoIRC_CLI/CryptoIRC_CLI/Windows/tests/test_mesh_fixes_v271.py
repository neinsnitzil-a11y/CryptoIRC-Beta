"""End-to-end mesh checks: signed roster replay, room membership, DM and encrypted room files."""
from pathlib import Path
import asyncio
import tempfile
import unittest
import sys
SRC=Path(__file__).resolve().parents[1]
MESH=SRC/'vaultmesh'
if str(MESH) not in sys.path:sys.path.insert(0,str(MESH))
import mesh_chat as mesh

class MeshRoutingFixes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.root=Path(self.work.name)
        self.nodes=[]
    async def asyncTearDown(self):
        for n in reversed(self.nodes): await n.stop()
        self.work.cleanup()
    async def start(self,name,**kwargs):
        path=self.root/name
        ident=mesh.create_account(path,name,'a long random test password 1234')
        n=mesh.MeshNode(ident,path,notify=lambda m:None,**kwargs)
        await n.start('127.0.0.1',0)
        self.nodes.append(n)
        return n
    async def wait_until(self,predicate, seconds=4):
        async def check():
            while not predicate():await asyncio.sleep(.02)
        await asyncio.wait_for(check(),seconds)

    async def test_late_joiner_immediately_receives_signed_online_roster(self):
        relay=await self.start('Relay',relay_mode=True)
        alice=await self.start('Alice')
        url=f'127.0.0.1:{relay.current_port}'
        await alice.connect(url)
        await self.wait_until(lambda:alice.ident.keyid in relay.signed_presence)
        bob=await self.start('Bobby')
        await bob.connect(url)
        await self.wait_until(lambda:alice.ident.keyid in bob.presence)
        self.assertIn(alice.ident.keyid,{k for _,k,_ in bob.online()})
        self.assertEqual(bob.presence[alice.ident.keyid]['nick'],'Alice')

    async def test_create_join_dm_and_encrypted_room_upload(self):
        relay=await self.start('Relay',relay_mode=True)
        alice=await self.start('Alice')
        bob=await self.start('Bobby')
        carol=await self.start('Carol')
        url=f'127.0.0.1:{relay.current_port}'
        for node in (alice,bob,carol):await node.connect(url)
        bob.rooms.add('#design');bob.active_room='#design';await bob.announce()
        await self.wait_until(lambda:'#design' in alice.visible_rooms())
        self.assertEqual(alice.visible_rooms()['#design'],1)
        alice.rooms.add('#design');alice.active_room='#design';await alice.announce()
        await self.wait_until(lambda:bob.ident.keyid in alice.online_room_recipients('#design'))
        self.assertEqual(alice.online_room_recipients('#design'),[bob.ident.keyid])
        await alice.send_dm(bob.ident.keyid,'private test')
        await self.wait_until(lambda:('DM','Alice','private test') in bob.inbox)
        with self.assertRaisesRegex(ValueError,'yourself'):
            await alice.send_dm(alice.ident.keyid,'bad')
        path=self.root/'photo.png';path.write_bytes(b'original image bytes')
        await alice.files.send_room('#design',str(path))
        await self.wait_until(lambda:any('content' in f for f in bob.files.pending.values()))
        self.assertFalse(relay.files.pending)
        self.assertFalse(carol.files.pending)
        tid=next(iter(bob.files.pending))
        self.assertEqual(bob.files.accept(tid).read_bytes(),b'original image bytes')

    async def test_cannot_room_upload_without_members_or_join(self):
        alice=await self.start('Alice')
        f=self.root/'photo.png';f.write_bytes(b'test')
        with self.assertRaisesRegex(ValueError,'No other ONLINE'):
            await alice.files.send_room('#general',str(f))
        with self.assertRaisesRegex(ValueError,'Join the channel'):
            await alice.files.send_room('#unknown',str(f))

if __name__=='__main__':unittest.main()
