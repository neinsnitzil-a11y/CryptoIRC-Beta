import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.peer_network import Identity, PeerHub, validate_request, _verify_message, handshake


class PeerTests(unittest.TestCase):
    def test_identity_encrypted_persistence_and_no_plaintext(self):
        with tempfile.TemporaryDirectory() as d:
            a=Identity.open(d,'very-strong-passphrase-001',create=True)
            f=Path(d)/'peer_identity.enc'
            data=f.read_bytes()
            self.assertNotIn(a.key.private_bytes_raw(),data)
            self.assertNotIn('very-strong-passphrase-001'.encode(),data)
            self.assertEqual(a.fingerprint,Identity.open(d,'very-strong-passphrase-001').fingerprint)
            with self.assertRaises(ValueError): Identity.open(d,'wrong-passphrase')
            with self.assertRaises(FileExistsError): Identity.open(d,'other-long-passphrase-2',create=True)

    def test_strict_request_and_no_secrets(self):
        req=validate_request('USDT','1.20','USDT','0x1111111111111111111111111111111111111111','Ethereum')
        self.assertEqual(req['status'],'REQUESTED_NOT_PAID')
        _verify_message(req)
        for amount in ['0','-1','NaN','Infinity','1e2000']:
            with self.assertRaises(ValueError):validate_request('USDT',amount,'USDT','0x123')
        with self.assertRaises(ValueError):validate_request('PayPal','1','USD','seed phrase do not share')
        with self.assertRaises(ValueError):validate_request('PayPal','1','USD','https://phishing.site')
        req['status']='PAID'
        with self.assertRaises(ValueError):_verify_message(req)
        with self.assertRaises(ValueError):_verify_message({'type':'send_funds','amount':'100'})

    def test_loopback_authenticated_encrypted_exchange(self):
        with tempfile.TemporaryDirectory() as d:
            a=Identity.open(Path(d)/'alice','abcdefghijklmnop',create=True)
            b=Identity.open(Path(d)/'bob','abcdefghijklmnop',create=True)
            received=[];done=threading.Event();authorized=[]
            sa,sb=socket.socketpair()
            out={}
            def server():
                try:
                    out['server']=handshake(sb,b,False,approve=lambda fp:(authorized.append(fp) or True),
                            on_message=lambda fp,m:(received.append(m),done.set()))
                    out['server'].loop()
                except Exception as e:out['server_error']=e
            t=threading.Thread(target=server,daemon=True);t.start()
            client=handshake(sa,a,True,expected=b.fingerprint)
            client.send({'type':'message','text':'hello bob'})
            self.assertTrue(done.wait(5))
            self.assertEqual(received[0]['text'],'hello bob')
            self.assertEqual(authorized,[a.fingerprint])
            req=validate_request('PayPal','23.99','GBP','@test')
            # Sending the same id twice does not create duplicate requests
            done.clear();client.send(req);client.send(req)
            self.assertTrue(done.wait(3))
            time.sleep(0.15)
            self.assertEqual(sum(1 for m in received if m.get('type')=='payment_request'),1)
            client.close()
            out['server'].close()
            t.join(2)

    def test_fingerprint_pin_rejects_impostor(self):
        with tempfile.TemporaryDirectory() as d:
            a=Identity.open(Path(d)/'a','abcdefghijklmnop',create=True)
            b=Identity.open(Path(d)/'b','abcdefghijklmnop',create=True)
            c=Identity.open(Path(d)/'c','abcdefghijklmnop',create=True)
            sa,sb=socket.socketpair()
            def server():
                try: handshake(sb,b,False,approve=lambda _:True)
                except Exception:pass
                finally:sb.close()
            t=threading.Thread(target=server,daemon=True);t.start()
            with self.assertRaises(ValueError): handshake(sa,a,True,expected=c.fingerprint)
            sa.close();t.join(2)

    def test_tor_fail_closed_and_no_unguarded_onion(self):
        with tempfile.TemporaryDirectory() as d:
            identity=Identity.open(d,'abcdefghijklmnop',create=True)
            hub=PeerHub(identity,lambda *_:None,lambda *_:False)
            with self.assertRaises(ValueError):hub.connect('127.0.0.1',19420,'a'*64,via_tor=True)
            with self.assertRaises(ValueError):hub.connect('a'*56+'.onion',19420,'a'*64,via_tor=False)
            hub.close()

    def test_multiple_peers_on_local_listener(self):
        with tempfile.TemporaryDirectory() as d:
            hosts=[]
            ids=[Identity.open(Path(d)/str(i),'abcdefghijklmnop',create=True) for i in range(3)]
            h0=PeerHub(ids[0],lambda event:hosts.append(event),lambda fp:True)
            h1=PeerHub(ids[1],lambda event:None,lambda fp:True)
            h2=PeerHub(ids[2],lambda event:None,lambda fp:True)
            try:
                s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
                h0.listen('127.0.0.1',port)
                self.assertEqual(h1.connect('127.0.0.1',port,ids[0].fingerprint),ids[0].fingerprint)
                self.assertEqual(h2.connect('127.0.0.1',port,ids[0].fingerprint),ids[0].fingerprint)
                end=time.monotonic()+3
                while len(h0.peers())<2 and time.monotonic()<end:time.sleep(.02)
                self.assertEqual(set(h0.peers()),{ids[1].fingerprint,ids[2].fingerprint})
            finally:h0.close();h1.close();h2.close()

if __name__=='__main__':unittest.main()
