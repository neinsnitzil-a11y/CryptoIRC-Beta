"""Protocol hardening tests. Synthetic P2P identities; no wallet keys or Tor service."""
import copy
import os
import tempfile
import threading
import time
import unittest
from collections import deque
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from core.mesh_network import MeshRouter, _signed, _verify_packet, MESH_VERSION
from core.peer_network import Identity, PeerHub
from core.tor_controller import TorController


class MeshReceiptTests(unittest.TestCase):
    def setUp(self):
        self.ids=[Identity(ed25519.Ed25519PrivateKey.generate()) for _ in range(3)]
        self.events=[[] for _ in self.ids]
        self.pending=deque()
        self.fp=[ident.fingerprint for ident in self.ids]
        routes={0:[1],1:[0,2],2:[1]}
        self.nodes=[]
        for i,ident in enumerate(self.ids):
            def sender(to,packet,origin=i):
                self.pending.append((to,self.fp[origin],copy.deepcopy(packet)))
            node=MeshRouter(ident,lambda idx=i:[self.fp[x] for x in routes[idx]],
                            sender,self.events[i].append,['Alice','Relay','Bob'][i])
            self.nodes.append(node)
        for node in self.nodes:node.enable(True)
        self.pump()

    def pump(self):
        counts=0
        while self.pending:
            to, sender, packet=self.pending.popleft()
            self.nodes[self.fp.index(to)].receive(sender,packet)
            counts+=1
            if counts>200:raise AssertionError('Routing loop')

    def test_ack_returns_across_two_hops_only_after_decryption(self):
        mid=self.nodes[0].send_message(self.fp[2],'Protected test message')
        self.assertFalse(any(e.get('event')=='mesh_delivered' for e in self.events[0]))
        self.pump()
        self.assertEqual([e['text'] for e in self.events[2] if e.get('event')=='mesh_message'],
                         ['Protected test message'])
        self.assertFalse(any(e.get('event')=='mesh_message' for e in self.events[1]))
        ack=[e for e in self.events[0] if e.get('event')=='mesh_delivered']
        self.assertEqual([e['packet_id'] for e in ack],[mid])
        self.assertEqual(self.nodes[0].outgoing,{})

    def test_forged_ack_from_wrong_authenticated_identity_is_ignored(self):
        mid=self.nodes[0].send_message(self.fp[2],'Safe')
        self.pending.clear() # no delivery happened
        ack=_signed(self.ids[1], {'type':'mesh','version':MESH_VERSION,'kind':'ack',
            'packet_id':'12345678-1234-4234-8234-123456789123',
            'created':int(time.time()),'hops':2,'author_pub':self.ids[1].public.hex(),
            'recipient':self.fp[0],'ack_for':mid})
        self.nodes[0].receive(self.fp[1],ack)
        self.assertFalse([e for e in self.events[0] if e.get('event')=='mesh_delivered'])
        self.assertIn(mid,self.nodes[0].outgoing)
        forged=copy.deepcopy(ack);forged['ack_for']='12345678-1234-4234-8234-123456789111'
        with self.assertRaises(Exception):_verify_packet(forged)

    def test_ack_tracking_expires_and_disable_scrubs(self):
        mid=self.nodes[0].send_message(self.fp[2],'Hello')
        with self.nodes[0].lock:self.nodes[0].outgoing[mid]['created']-=1000
        self.nodes[0].online()
        self.assertNotIn(mid,self.nodes[0].outgoing)
        self.nodes[0].send_message(self.fp[2],'Hello again')
        self.nodes[0].enable(False)
        self.assertEqual(self.nodes[0].outgoing,{})

    def test_malformed_ack_rejected(self):
        p=_signed(self.ids[2],{'type':'mesh','version':MESH_VERSION,'kind':'ack',
            'packet_id':'12345678-1234-4234-8234-123456789123','created':int(time.time()),
            'hops':3,'author_pub':self.ids[2].public.hex(),
            'recipient':self.fp[0], 'ack_for':'not-uuid'})
        with self.assertRaises(ValueError):_verify_packet(p)


class P2PTransportPolicyTests(unittest.TestCase):
    def setUp(self):
        self.identity=Identity(ed25519.Ed25519PrivateKey.generate())
        self.hub=PeerHub(self.identity, lambda e:None, lambda fp:True)
    def tearDown(self):self.hub.close()

    def test_tor_only_blocks_direct_connect_and_lan_bind_at_transport(self):
        self.hub.require_tor(True, lambda:True)
        with self.assertRaises(PermissionError):
            self.hub.connect('127.0.0.1',443,'a'*64,via_tor=False)
        with self.assertRaises(PermissionError):self.hub.listen('0.0.0.0',19420)
        self.assertEqual(self.hub.peers(),[])

    def test_daemon_loss_blocks_outgoing_sends_and_closes_listener(self):
        ready={'value':True}
        self.hub.require_tor(True,lambda:ready['value'])
        self.hub.listen('127.0.0.1',0)
        self.assertIsNotNone(self.hub._listener)
        ready['value']=False
        with self.assertRaises(PermissionError):
            self.hub.connect('a'*56+'.onion',19420,'b'*64,via_tor=True)
        self.hub.fail_closed()
        self.assertIsNone(self.hub._listener)
        self.assertTrue(self.hub.tor_only,'Fail-closed cannot turn on direct transport')

    def test_tor_only_blocks_channel_broadcast_and_profile_controls(self):
        class FakeSession:
            inbound=False
            transport='direct'
            def __init__(self):self.closed=threading.Event();self.sent=[]
            def send(self,obj):self.sent.append(obj)
            def close(self):self.closed.set()
        fake=FakeSession()
        self.hub.require_tor(True,lambda:False)
        with self.hub._lock:self.hub.sessions['a'*64]=fake
        with self.assertRaises(PermissionError):
            self.hub.send_channel('#general','No direct traffic')
        with self.assertRaises(PermissionError):
            self.hub.join_room('#private')
        self.assertEqual(fake.sent,[])

    def test_tor_only_blocks_direct_session_messages(self):
        class FakeSession:
            def __init__(self):
                self.transport='direct';self.closed=threading.Event();self.sent=[]
            def send(self,obj):self.sent.append(obj)
            def close(self):self.closed.set()
        fake=FakeSession()
        with self.hub._lock:self.hub.sessions['a'*64]=fake
        self.hub.require_tor(True,lambda:True)
        self.assertTrue(fake.closed.is_set())
        with self.assertRaises(ConnectionError):self.hub.send('a'*64,{'type':'ping'})


class TorStartupSafetyTests(unittest.TestCase):
    def test_filename_must_be_tor_even_through_start_parameter(self):
        with tempfile.TemporaryDirectory() as td:
            evil=Path(td)/'shell.exe';evil.write_text('simulated')
            tor=TorController(Path(td)/'state')
            with self.assertRaises(ValueError):tor.start(executable=str(evil))
            self.assertEqual(tor.status(),'OFF')

    @unittest.skipIf(os.name=='nt','Unix symlink semantics')
    def test_refuses_symlinked_torrc_without_overwriting_target(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            tor=root/'tor';tor.write_text('#!/bin/sh\necho fake\n');tor.chmod(0o700)
            cfg=root/'state';cfg.mkdir()
            outside=root/'untouched';outside.write_text('NEVER OVERWRITE')
            (cfg/'torrc').symlink_to(outside)
            ctl=TorController(cfg)
            with self.assertRaises(ValueError):ctl.start(executable=str(tor))
            self.assertEqual(outside.read_text(),'NEVER OVERWRITE')

    @unittest.skipIf(os.name=='nt','Newlines in Unix directory names')
    def test_rejects_torrc_injection_from_config_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            tor=root/'tor';tor.write_text('#!/bin/sh\necho fake\n');tor.chmod(0o700)
            ctl=TorController(root/'invalid\nHiddenServicePort 80 1.1.1.1:80')
            with self.assertRaises(ValueError):ctl.start(executable=str(tor))


if __name__=='__main__':unittest.main()
