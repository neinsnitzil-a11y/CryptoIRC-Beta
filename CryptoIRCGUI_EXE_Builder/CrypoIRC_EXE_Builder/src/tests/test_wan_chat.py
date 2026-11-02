import json, os, tempfile, time, unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from core.peer_network import Identity
from core.wan_chat import (contact_card, validate_card, seal, open_envelope, WANContacts,
                           WANClient, request_headers, validate_server_url)
try:
    from fastapi.testclient import TestClient
    from server.relay import create_app
except ImportError:
    # GUI-only installations do not need server-side FastAPI/httpx packages.
    TestClient = None
    create_app = None


class WanChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        self.alice=Identity(ed25519.Ed25519PrivateKey.generate())
        self.bob=Identity(ed25519.Ed25519PrivateKey.generate())
        self.alice_card=contact_card(self.alice,'Alice')
        self.bob_card=contact_card(self.bob,'Bob')
        self.app=create_app(base/'server.sqlite3') if create_app else None
        if self.app:self.addCleanup(self.app.state.db.close)
        self.server=TestClient(self.app) if TestClient is not None else None

    def _req(self,identity,method,path,data=None):
        if self.server is None:self.skipTest('FastAPI/httpx relay test dependencies not installed')
        from core.wan_chat import canonical
        body=canonical(data) if data is not None else b''
        headers=request_headers(identity,method,path,body)
        if data is not None:headers['Content-Type']='application/json'
        return self.server.request(method,path,content=body if data is not None else None,headers=headers)

    def register(self):
        for i,c in ((self.alice,self.alice_card),(self.bob,self.bob_card)):
            r=self._req(i,'POST','/v1/register',{'card':c})
            self.assertEqual(r.status_code,200,r.text)

    def test_contact_cards_signature_and_identity(self):
        self.assertEqual(validate_card(self.alice_card),self.alice.fingerprint)
        forged=dict(self.alice_card);forged['nickname']='Attacker'
        with self.assertRaises(Exception):validate_card(forged)

    def test_envelope_encrypted_and_wrong_receiver(self):
        encrypted=seal(self.alice,self.bob_card,'Hello from another country!')
        self.assertNotIn('Hello from',json.dumps(encrypted))
        self.assertEqual(open_envelope(self.bob,self.alice_card,encrypted)['text'],'Hello from another country!')
        with self.assertRaises(Exception):open_envelope(self.alice,self.alice_card,encrypted)
        modified=dict(encrypted);modified['ciphertext']=encrypted['ciphertext'][:-4]+'dead'
        with self.assertRaises(Exception):open_envelope(self.bob,self.alice_card,modified)

    def test_unsafe_secrets_rejected(self):
        for content in ('my private key is here','my seed phrase is somewhere'):
            with self.assertRaises(ValueError):seal(self.alice,self.bob_card,content)

    def test_contacts_pinned_and_persisted(self):
        contacts=WANContacts(self.temp.name)
        contacts.trust(self.bob_card)
        self.assertEqual(WANContacts(self.temp.name).cards[self.bob.fingerprint],self.bob_card)
        changed=dict(self.bob_card);changed['enc_pub']=self.alice_card['enc_pub']
        with self.assertRaises(Exception):contacts.trust(changed)

    def test_public_relay_requires_https(self):
        self.assertEqual(validate_server_url('http://127.0.0.1:8765'),'http://127.0.0.1:8765')
        self.assertEqual(validate_server_url('https://chat.example.org/'),'https://chat.example.org')
        for url in ('http://chat.example.org','https://user:pass@chat.example.org','https://chat.example.org/path'):
            with self.assertRaises(ValueError):validate_server_url(url)

    def test_offline_store_forward_with_presence_and_rooms(self):
        self.register()
        a=self.alice; b=self.bob
        # Person in another country can be offline; only encrypted payload is queued.
        msg=seal(a,self.bob_card,'Offline message for Bob',kind='message')
        sent=self._req(a,'POST','/v1/send',{'envelope':msg})
        self.assertEqual(sent.status_code,200,sent.text)
        self.assertEqual(sent.json()['settlement'],'NONE')
        inbox=self._req(b,'GET','/v1/inbox')
        self.assertEqual(inbox.status_code,200,inbox.text)
        self.assertEqual(len(inbox.json()['envelopes']),1)
        self.assertEqual(open_envelope(b,self.alice_card,inbox.json()['envelopes'][0])['text'],'Offline message for Bob')
        # Exactly-once app-side acknowledgement.
        self.assertEqual(self._req(b,'POST','/v1/ack',{'ids':[msg['id']]}).status_code,200)
        self.assertEqual(self._req(b,'GET','/v1/inbox').json()['envelopes'],[])
        # Global rooms can be joined without direct LAN connections.
        self.assertEqual(self._req(a,'POST','/v1/room/join',{'room':'#general'}).status_code,200)
        self.assertEqual(self._req(b,'POST','/v1/room/join',{'room':'#general'}).status_code,200)
        members=self._req(a,'GET','/v1/room/members?room=#general')
        # URLs with '#' require encoded #, just as a real browser would.
        self.assertNotEqual(members.status_code,200)
        members=self._req(a,'GET','/v1/room/members?room=%23general')
        self.assertEqual(members.status_code,200,members.text)
        self.assertEqual(len(members.json()['users']),2)

    def test_replay_auth_and_no_wallet_content(self):
        self.register()
        from core.wan_chat import canonical
        b=canonical({}); headers=request_headers(self.alice,'POST','/v1/heartbeat',b)
        r=self.server.post('/v1/heartbeat',content=b,headers=headers)
        self.assertEqual(r.status_code,200,r.text)
        repeated=self.server.post('/v1/heartbeat',content=b,headers=headers)
        self.assertEqual(repeated.status_code,401)
        public=self._req(self.alice,'GET','/v1/directory').json()
        self.assertEqual(len(public['users']),2)
        self.assertNotIn('seed',json.dumps(public).lower())

if __name__=='__main__':unittest.main()
