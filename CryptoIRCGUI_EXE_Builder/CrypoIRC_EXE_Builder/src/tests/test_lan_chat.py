import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.lan_chat import ContactBook, safe_discovery_packet, DISCOVERY_MARK, check_nick, check_room
from core.peer_network import Identity, PeerHub, _verify_message, _safe_chat, make_channel_message


def eventually(check, timeout=4.0):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        if check():return True
        time.sleep(0.035)
    return False


class LanChatTests(unittest.TestCase):
    def test_discovery_rejects_untrusted_and_wallet_data(self):
        fp='a'*64
        packet=json.dumps({'app':DISCOVERY_MARK,'fingerprint':fp,'nick':'Alice',
                           'port':19420}).encode()
        self.assertEqual(safe_discovery_packet(packet,'192.168.1.22')['fingerprint'],fp)
        self.assertIsNone(safe_discovery_packet(packet,'8.8.8.8'))
        self.assertIsNone(safe_discovery_packet(packet,'127.0.0.1'))
        self.assertIsNone(safe_discovery_packet(packet,'192.168.1.22',own_fingerprint=fp))
        self.assertIsNone(safe_discovery_packet(packet[:-1]+b',"vault":"secret"}','192.168.1.22'))
        obj=json.loads(packet);obj['seed']='totally-private'
        self.assertIsNone(safe_discovery_packet(json.dumps(obj).encode(),'10.1.2.3'))

    def test_contacts_only_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            book=ContactBook(tmp)
            book.remember('b'*64,'Alice_01')
            self.assertEqual(ContactBook(tmp).entries,{'b'*64:'Alice_01'})
            self.assertNotIn('private',book.path.read_text().lower())
            with self.assertRaises(ValueError):book.remember('c'*64,'my seed phrase')
            with self.assertRaises(ValueError):check_nick('../path')
            with self.assertRaises(ValueError):check_room('general')
            book.remove('b'*64);self.assertEqual(ContactBook(tmp).entries,{})

    def test_seed_and_secret_content_blocked(self):
        with self.assertRaises(ValueError):_safe_chat('seed phrase: hello')
        with self.assertRaises(ValueError):_safe_chat('abandon ability able about above absent absorb abstract absurd abuse access accident')
        with self.assertRaises(ValueError):_safe_chat('f'*64)
        self.assertEqual(_safe_chat('Hi #general!'), 'Hi #general!')

    def test_signed_chat_does_not_allow_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity=Identity.open(tmp,'abcdefghijklmno',create=True)
            msg=make_channel_message(identity,'#general','Hello')
            _verify_message(msg)
            msg['text']='fake'
            with self.assertRaises(ValueError):_verify_message(msg)

    def test_unannounced_peers_are_not_visible_in_roster(self):
        # A completed handshake does not mean the nickname/profile has arrived.
        # Previously an unverified generic 'Peer' placeholder leaked into rosters,
        # making the GUI and cross-platform test nondeterministic.
        with tempfile.TemporaryDirectory() as tmp:
            identity=Identity.open(tmp, 'abcdefghijklmno', create=True)
            hub=PeerHub(identity, lambda e: None, lambda _: True, nickname='HostUser')
            class PendingSession:
                def __init__(self): self.closed=threading.Event()
                def close(self): self.closed.set()
            try:
                peer='f'*64
                with hub._lock:
                    hub.sessions[peer]=PendingSession()
                    hub.profiles[peer]={'nick':None, 'rooms':{'#general'}}
                self.assertEqual([x['nick'] for x in hub.roster()], ['HostUser'])
                with hub._lock:
                    hub.profiles[peer]['nick']='BobChat'
                self.assertEqual({x['nick'] for x in hub.roster()}, {'HostUser','BobChat'})
            finally:
                hub.close()

    def test_rooms_roster_and_relay_on_lan_listener(self):
        # Multiple installations. TCP listener accepts a non-localhost IPv4
        # destination, simulating LAN reachability in a single test container.
        with tempfile.TemporaryDirectory() as d:
            ids=[Identity.open(Path(d)/str(i),'abcdefghijklmno',create=True) for i in range(3)]
            logs=[[] for _ in range(3)]
            hubs=[PeerHub(ids[i],lambda e,k=i:logs[k].append(e),lambda _:True,
                          nickname=('HostUser','AliceChat','BobChat')[i]) for i in range(3)]
            try:
                s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
                hubs[0].listen('0.0.0.0',port)
                self.assertEqual(hubs[0].bind_host,'0.0.0.0')
                # 127.0.0.2 deliberately is NOT the literal localhost address.
                hubs[1].connect('127.0.0.2',port,ids[0].fingerprint)
                hubs[2].connect('127.0.0.2',port,ids[0].fingerprint)
                self.assertTrue(eventually(lambda:len(hubs[0].peers())==2))
                self.assertTrue(eventually(lambda:any(x.get('event')=='roster' and len(x['users'])==3
                                               for x in logs[1])))
                self.assertEqual({x['nick'] for x in hubs[0].roster()},
                                 {'HostUser','AliceChat','BobChat'})
                hubs[1].send_channel('#general','Hello LAN folks')
                self.assertTrue(eventually(lambda:any(x.get('event')=='chat'
                    and x['data']['text']=='Hello LAN folks' and x['fingerprint']==ids[1].fingerprint
                    for x in logs[2])))
                # On the receiving side, the directly connected hub is the relay,
                # not the independently trusted identity of the channel speaker.
                report=next(x for x in logs[2] if x.get('event')=='chat')
                self.assertEqual(report['via'],ids[0].fingerprint)
                hubs[2].join_room('#help');hubs[1].join_room('#help')
                self.assertTrue(eventually(lambda:'#help' in hubs[0].profiles[ids[2].fingerprint]['rooms']))
                hubs[1].send_channel('#help','Help channel available')
                self.assertTrue(eventually(lambda:any(x.get('event')=='chat' and
                    x['data']['text']=='Help channel available' for x in logs[2])))
                hubs[2].part_room('#help')
                self.assertTrue(eventually(lambda:'#help' not in hubs[0].profiles[ids[2].fingerprint]['rooms']))
                hubs[1].send_channel('#help','Not visible to Bob')
                time.sleep(.2)
                self.assertFalse(any(x.get('event')=='chat' and
                    x['data']['text']=='Not visible to Bob' for x in logs[2]))
                hubs[1].send(ids[0].fingerprint,{'type':'message','text':'direct private'})
                self.assertTrue(eventually(lambda:any(x.get('event')=='message' and
                    x['data'].get('text')=='direct private' for x in logs[0])))
                self.assertFalse(any(x.get('event')=='message' and
                    x['data'].get('text')=='direct private' for x in logs[2]))
            finally:
                for h in hubs:h.close()

if __name__=='__main__': unittest.main()
