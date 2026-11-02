"""Experimental opt-in multihop mesh over existing authenticated P2P sessions.

Only chat messages and public signed presence are allowed. Each message is
end-to-end AES-GCM encrypted to an X25519 recipient key that is independently
bound to a signed Ed25519 peer identity. Transit devices never see plaintext.

THIS IS NOT an audited anonymity system: routing fingerprints are visible to
relays. No automatic wallet, fiat, settlement, or RPC messages are supported.
"""
from __future__ import annotations
import hashlib
import json
import threading
import time
import uuid
from collections import deque
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from core.peer_network import _raw_priv, _raw_pub, _safe_chat

MESH_VERSION = 2
MAX_HOPS = 3
MAX_PEERS = 128
MAX_AGE = 600
MAX_PACKET_BYTES = 4200


def encoded(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def immutable(packet):
    return {k:v for k,v in packet.items() if k not in ('hops', 'signature')}


def mesh_private(identity):
    seed = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b'CRYPTO-MESH-IDENTITY-X25519-V1').derive(_raw_priv(identity.key))
    return x25519.X25519PrivateKey.from_private_bytes(seed)


def mesh_public(identity):
    return _raw_pub(mesh_private(identity).public_key()).hex()


def _verify_packet(packet, now=None):
    if not isinstance(packet, dict) or packet.get('type') != 'mesh':
        raise ValueError('Not a mesh packet')
    if len(encoded(packet)) > MAX_PACKET_BYTES:
        raise ValueError('Mesh frame size exceeded')
    kind = packet.get('kind')
    if kind == 'presence':
        allowed = {'type','version','kind','packet_id','created','hops','author_pub',
                   'mesh_pub','nick','signature'}
    elif kind == 'message':
        allowed = {'type','version','kind','packet_id','created','hops','author_pub',
                   'recipient','ephemeral_pub','nonce','ciphertext','signature'}
    else:
        allowed = {'type','version','kind','packet_id','created','hops','author_pub',
                   'recipient','ack_for','signature'}
    if kind not in ('presence','message','ack') or set(packet) != allowed:
        raise ValueError('Unsupported mesh frame')
    if packet['version'] != MESH_VERSION or type(packet['hops']) is not int or not 0 <= packet['hops'] <= MAX_HOPS:
        raise ValueError('Unsupported mesh version or hop count')
    if str(uuid.UUID(packet['packet_id'])) != packet['packet_id']:
        raise ValueError('Invalid mesh packet id')
    now = int(time.time()) if now is None else int(now)
    if type(packet['created']) is not int or not now - MAX_AGE <= packet['created'] <= now + 60:
        raise ValueError('Expired or future mesh frame')
    pub = bytes.fromhex(packet['author_pub'])
    if len(pub) != 32: raise ValueError('Invalid mesh author')
    ed25519.Ed25519PublicKey.from_public_bytes(pub).verify(
        bytes.fromhex(packet['signature']), encoded(immutable(packet)))
    fingerprint = hashlib.sha256(pub).hexdigest()
    if kind == 'presence':
        mp = bytes.fromhex(packet['mesh_pub'])
        if len(mp)!=32 or not (1 <= len(packet['nick']) <= 32):
            raise ValueError('Invalid peer advertisement')
        if not all(c.isalnum() or c in '_- ' for c in packet['nick']):
            raise ValueError('Invalid peer nickname')
    else:
        if not isinstance(packet['recipient'],str) or len(packet['recipient'])!=64:
            raise ValueError('Invalid mesh target')
        int(packet['recipient'],16)
        if kind == 'message':
            if len(bytes.fromhex(packet['ephemeral_pub']))!=32 or len(bytes.fromhex(packet['nonce']))!=12:
                raise ValueError('Invalid mesh envelope')
            if not 16 <= len(bytes.fromhex(packet['ciphertext'])) <= 1024:
                raise ValueError('Invalid message size')
        else:
            if str(uuid.UUID(packet['ack_for'])) != packet['ack_for']:
                raise ValueError('Invalid acknowledged message ID')
    return fingerprint


def _signed(identity, packet):
    packet['signature'] = identity.key.sign(encoded(immutable(packet))).hex()
    return packet


class MeshRouter:
    def __init__(self, identity, peers, send, emit, nickname='CryptoUser'):
        self.identity, self.peers, self.send, self.emit = identity, peers, send, emit
        self.nickname=nickname
        self.enabled=False
        self.directory={}  # authenticated public identity -> signed X25519 public key
        self.announcements={}
        self.seen=set();self.seen_fifo=deque()
        self.lock=threading.RLock()
        self.rate={}
        self.outgoing={}  # message ID -> authenticated recipient and time; no message plaintext
        self.rx_packets=0
        self.rejected_packets=0

    def enable(self, on=True):
        with self.lock:
            self.enabled=bool(on)
            if not on:
                self.directory.clear();self.announcements.clear();self.seen.clear();self.seen_fifo.clear();self.outgoing.clear();self.rate.clear()
        if on:self.announce()

    def _remember(self, packet_id):
        with self.lock:
            if packet_id in self.seen:return False
            self.seen.add(packet_id);self.seen_fifo.append(packet_id)
            while len(self.seen_fifo)>2048:self.seen.discard(self.seen_fifo.popleft())
            return True

    def _fanout(self, packet, skip=None):
        if packet['hops']<=0:return
        forwarded = dict(packet);forwarded['hops']-=1
        for peer in self.peers():
            if peer == skip:continue
            try:self.send(peer,forwarded)
            except (ValueError, OSError, ConnectionError):pass

    def announce(self):
        if not self.enabled:return
        packet=_signed(self.identity, {'type':'mesh','version':MESH_VERSION,'kind':'presence',
            'packet_id':str(uuid.uuid4()),'created':int(time.time()),'hops':MAX_HOPS,
            'author_pub':self.identity.public.hex(),'mesh_pub':mesh_public(self.identity),
            'nick':self.nickname})
        self._remember(packet['packet_id'])
        self._fanout(dict(packet,hops=packet['hops']+1))  # transmit up to MAX_HOPS

    def on_new_peer(self, fingerprint):
        if not self.enabled:return
        self.announce()
        with self.lock:cached=list(self.announcements.values())
        for p in cached:
            if p['hops']>0:
                try:self.send(fingerprint,dict(p,hops=p['hops']-1))
                except (ValueError, OSError, ConnectionError):pass

    def online(self):
        with self.lock:
            now=time.time()
            # Signed presence is short-lived; expire old peer routes.
            for fp in list(self.directory):
                if now-self.directory[fp]['seen']>=MAX_AGE:
                    self.directory.pop(fp,None)
                    self.announcements.pop(fp,None)
            self._expire_outgoing(time.time())
            return sorted((fp, record['nick']) for fp, record in self.directory.items())

    def _expire_outgoing(self, now):
        for msg_id, record in list(self.outgoing.items()):
            if now - record['created'] > MAX_AGE:
                self.outgoing.pop(msg_id, None)

    def send_message(self, recipient, text):
        if not self.enabled:raise RuntimeError('Mesh network is disabled')
        text=_safe_chat(text)
        if len(text)>500:raise ValueError('Mesh message maximum is 500 characters')
        with self.lock:record=self.directory.get(recipient)
        if not record or time.time()-record['seen']>MAX_AGE:
            raise ValueError('Recipient has not been discovered through signed mesh presence')
        eph=x25519.X25519PrivateKey.generate()
        shared=eph.exchange(x25519.X25519PublicKey.from_public_bytes(bytes.fromhex(record['key'])))
        key=HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                 info=b'CRYPTO-MESH-MESSAGE-V1').derive(shared)
        packet_id=str(uuid.uuid4())
        aad=encoded({'from':self.identity.fingerprint,'to':recipient,'id':packet_id})
        import os
        nonce=os.urandom(12)
        ciphertext=AESGCM(key).encrypt(nonce,encoded({'text':text}),aad)
        packet=_signed(self.identity,{'type':'mesh','version':MESH_VERSION,'kind':'message',
            'packet_id':packet_id,'created':int(time.time()),'hops':MAX_HOPS,
            'author_pub':self.identity.public.hex(),'recipient':recipient,
            'ephemeral_pub':_raw_pub(eph.public_key()).hex(),
            'nonce':nonce.hex(),'ciphertext':ciphertext.hex()})
        with self.lock:
            self._expire_outgoing(time.time())
            if len(self.outgoing) >= 512:
                raise RuntimeError('Too many mesh messages awaiting delivery; retry later')
            self.outgoing[packet_id] = {'recipient':recipient, 'created':time.time()}
        self._remember(packet_id)
        # direct neighbours can carry it even if recipient is not adjacent
        self._fanout(dict(packet,hops=packet['hops']+1))
        return packet_id

    def receive(self, sender, packet):
        if not self.enabled:return
        fp=_verify_packet(packet)
        with self.lock:
            now=time.monotonic()
            # Bound rate-map memory even when identities disconnect/reconnect.
            if len(self.rate)>256:
                self.rate={k:v for k,v in self.rate.items() if now-v[0]<60}
            if sender not in self.rate and len(self.rate)>=512:
                self.rejected_packets+=1
                raise ValueError('Too many mesh sender identities')
            timestamp, count=self.rate.get(sender,(now,0))
            if now-timestamp>60:timestamp,count=now,0
            count+=1;self.rate[sender]=(timestamp,count)
            if count>120:
                self.rejected_packets+=1
                raise ValueError('Mesh peer rate limit exceeded')
            self.rx_packets+=1
        if not self._remember(packet['packet_id']):return
        if packet['kind']=='presence':
            if fp!=self.identity.fingerprint:
                with self.lock:
                    if fp not in self.directory and len(self.directory)>=MAX_PEERS:return
                    self.directory[fp]={'key':packet['mesh_pub'],'nick':packet['nick'],
                                        'seen':time.time()}
                    self.announcements[fp]=packet
                self.emit({'event':'mesh_presence','fingerprint':fp,'nick':packet['nick']})
        elif packet['kind']=='message' and packet['recipient']==self.identity.fingerprint:
            eph=x25519.X25519PublicKey.from_public_bytes(bytes.fromhex(packet['ephemeral_pub']))
            key=HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                     info=b'CRYPTO-MESH-MESSAGE-V1').derive(mesh_private(self.identity).exchange(eph))
            aad=encoded({'from':fp,'to':self.identity.fingerprint,'id':packet['packet_id']})
            plaintext=json.loads(AESGCM(key).decrypt(bytes.fromhex(packet['nonce']),
                         bytes.fromhex(packet['ciphertext']),aad))
            if set(plaintext) != {'text'}:raise ValueError('Invalid decrypted mesh message')
            text=_safe_chat(plaintext['text'])
            self.emit({'event':'mesh_message','fingerprint':fp,'text':text})
            # An ACK proves delivery to the authenticated endpoint, NOT human reading,
            # on-chain settlement or an offline receipt. It carries no plaintext.
            acknowledgement = _signed(self.identity, {
                'type':'mesh','version':MESH_VERSION,'kind':'ack',
                'packet_id':str(uuid.uuid4()),'created':int(time.time()),
                'hops':MAX_HOPS,'author_pub':self.identity.public.hex(),
                'recipient':fp,'ack_for':packet['packet_id']})
            self._remember(acknowledgement['packet_id'])
            self._fanout(dict(acknowledgement,hops=MAX_HOPS+1))
        elif packet['kind']=='ack' and packet['recipient']==self.identity.fingerprint:
            with self.lock:
                self._expire_outgoing(time.time())
                record=self.outgoing.get(packet['ack_for'])
                if record and record['recipient']==fp:
                    self.outgoing.pop(packet['ack_for'], None)
                    valid_receipt=True
                else:
                    valid_receipt=False
            if valid_receipt:
                self.emit({'event':'mesh_delivered','fingerprint':fp,'packet_id':packet['ack_for']})
        if packet['hops']>0 and packet.get('recipient')!=self.identity.fingerprint:
            self._fanout(packet,skip=sender)
