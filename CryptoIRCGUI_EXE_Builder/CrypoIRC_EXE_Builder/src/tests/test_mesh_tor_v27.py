import copy
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from core.peer_network import Identity, PeerHub
from core.mesh_network import MeshRouter, _verify_packet, MESH_VERSION
from core.tor_controller import TorController


class MeshTests(unittest.TestCase):
    def test_mesh_three_nodes_e2e_relay_and_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            ids=[Identity.open(Path(td)/str(n),'correct horse battery staple',create=True) for n in range(3)]
            events=[[],[],[]]
            hubs=[PeerHub(ids[i],events[i].append,lambda _:True,nickname=['Alice','Relay','Charlie'][i]) for i in range(3)]
            try:
                for h in hubs:h.mesh.enable(True)
                hubs[1].listen('127.0.0.1',0)
                port=hubs[1].listen_port
                hubs[0].connect('127.0.0.1',port,ids[1].fingerprint)
                hubs[2].connect('127.0.0.1',port,ids[1].fingerprint)
                deadline=time.monotonic()+5
                while ids[2].fingerprint not in dict(hubs[0].mesh.online()) and time.monotonic()<deadline:
                    for h in hubs:h.mesh.announce()
                    time.sleep(.05)
                self.assertIn(ids[2].fingerprint,dict(hubs[0].mesh.online()))
                packet_id=hubs[0].mesh.send_message(ids[2].fingerprint,'Hello across two hops')
                deadline=time.monotonic()+5
                while not any(e.get('event')=='mesh_message' for e in events[2]) and time.monotonic()<deadline:time.sleep(.03)
                delivered=[e for e in events[2] if e.get('event')=='mesh_message']
                self.assertEqual(len(delivered),1)
                self.assertEqual(delivered[0]['text'],'Hello across two hops')
                self.assertFalse(any(e.get('event')=='mesh_message' for e in events[1]),'Relay cannot read content')
                packet=hubs[0].mesh.send_message(ids[2].fingerprint,'Only once')
                self.assertNotEqual(packet_id,packet)
            finally:
                for h in hubs:h.close()

    def test_tampered_signed_packet_and_hop_expiration(self):
        with tempfile.TemporaryDirectory() as td:
            alice=Identity.open(td,'correct horse battery staple',create=True)
            out=[]
            router=MeshRouter(alice,lambda:[],lambda *a:None,out.append,'Alice')
            router.enable(True)
            p={'type':'mesh','version':MESH_VERSION,'kind':'presence','packet_id': '12345678-1234-4234-8234-123456789123',
               'created':int(time.time()),'hops':3,'author_pub':alice.public.hex(),
               'mesh_pub':'00'*32,'nick':'Alice'}
            from core.mesh_network import _signed
            _signed(alice,p)
            self.assertEqual(_verify_packet(p),alice.fingerprint)
            tampered=copy.deepcopy(p);tampered['nick']='Mallory'
            with self.assertRaises(Exception):_verify_packet(tampered)
            expired=copy.deepcopy(p);expired['created']-=10000
            with self.assertRaises(ValueError):_verify_packet(expired)
            broken=copy.deepcopy(p);broken['hops']=17
            with self.assertRaises(ValueError):_verify_packet(broken)

    def test_mesh_cannot_send_without_verified_presence(self):
        with tempfile.TemporaryDirectory() as td:
            a=Identity.open(td,'correct horse battery staple',create=True)
            m=MeshRouter(a,lambda:[],lambda *a:None,lambda *a:None)
            with self.assertRaises(RuntimeError):m.send_message('a'*64,'hi')
            m.enable(True)
            with self.assertRaises(ValueError):m.send_message('a'*64,'hi')
            with self.assertRaises(ValueError):m.send_message('a'*64,'seed phrase')

class TorControllerTests(unittest.TestCase):
    def test_no_unverified_tor_binary_will_launch(self):
        with tempfile.TemporaryDirectory() as d:
            t=TorController(Path(d)/'state')
            with self.assertRaises((FileNotFoundError,RuntimeError)):
                t.start(executable=str(Path(d)/'not-real-tor'),peer_port=25000)
            self.assertEqual(t.status(),'OFF')
            with self.assertRaises((FileNotFoundError,ValueError)):t.set_binary(str(Path(d)/'malware.exe'))

    def test_installed_tor_config_is_local_only(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            tor=Path(d)/('tor.exe' if os.name=='nt' else 'tor')
            tor.write_text('#!/bin/sh\necho "Bootstrapped 100%"\nsleep 5\n')
            if os.name!='nt':tor.chmod(0o700)
            if os.name=='nt':return  # no fake shell executable under Windows
            ctrl=TorController(Path(d)/'state')
            ctrl.set_binary(str(tor))
            try:
                ctrl.start(peer_port=25555)
                deadline=time.monotonic()+2
                while not ctrl.bootstrapped and time.monotonic()<deadline:time.sleep(.04)
                self.assertTrue(ctrl.bootstrapped)
                config=(Path(d)/'state'/'torrc').read_text()
                self.assertIn('SocksPort 127.0.0.1:',config)
                self.assertIn('HiddenServicePort 25555 127.0.0.1:25555',config)
                self.assertNotIn('0.0.0.0:',config)
            finally:ctrl.stop()
            self.assertEqual(ctrl.status(),'OFF')

if __name__=='__main__':unittest.main()
