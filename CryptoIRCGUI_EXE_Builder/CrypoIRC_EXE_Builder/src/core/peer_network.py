"""CRYPTO P2P v2.0: authenticated, encrypted, opt-in direct peer sessions.

Messages only contain public receiving data and *requests*, NEVER payment settlement
or wallet credentials. Experimental protocol; not third-party audited. No discovery
or central service, no automatic direct fallback if Tor is selected.
"""
from __future__ import annotations
import base64
import csv
from functools import lru_cache
import hashlib
import json
import os
import re
import socket
import struct
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from core.lan_chat import check_nick, check_room

from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

VERSION = 'CRYPTO-P2P-V2'
MAX_FRAME = 16 * 1024
MAX_MESSAGE = 12 * 1024
FINGERPRINT_RE = re.compile(r'^[0-9a-f]{64}$')
CODE_RE = re.compile(r'^[A-Z0-9]{2,12}$')
NETWORK_RE = re.compile(r'^[a-zA-Z0-9 ()_\-./]{0,56}$')
ADDRESS_RE = re.compile(r'^[^\x00-\x1f\x7f]{1,256}$')
PROVIDERS = ('Bitcoin', 'Monero', 'Ethereum', 'USDT', 'USDC', 'Solana',
             'PayPal', 'Stripe', 'Square', 'Cash App', 'Venmo', 'Wise',
             'Revolut', 'Zelle', 'ACH / bank', 'Wire / SWIFT',
             'Apple Pay', 'Google Pay', 'Adyen', 'Braintree', 'Klarna',
             'Other cryptocurrency', 'Other provider')


def _raw_pub(key):
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _raw_priv(key):
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())


def _json_bytes(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True, ensure_ascii=True).encode('ascii')


def _fingerprint(public):
    return hashlib.sha256(public).hexdigest()


def _derive_password(password, salt):
    if not isinstance(password, str) or not password:
        raise ValueError('Nonempty identity password required')
    return hash_secret_raw(password.encode('utf-8'), salt, time_cost=3,
                           memory_cost=65536, parallelism=2, hash_len=32, type=Type.ID)


def _save_identity(path, private_key, password):
    salt, nonce = os.urandom(16), os.urandom(12)
    key = _derive_password(password, salt)
    payload = AESGCM(key).encrypt(nonce, _raw_priv(private_key), b'CRYPTO-P2P-IDENTITY-V1')
    record = {'version': 1, 'kdf': 'argon2id', 'salt': salt.hex(),
              'nonce': nonce.hex(), 'ciphertext': payload.hex()}
    # Fail if identity already exists: never overwrite keys that identify contacts.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'): flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps(record, sort_keys=True));f.flush();os.fsync(f.fileno())
    except BaseException:
        try: path.unlink(missing_ok=True)
        except OSError: pass
        raise


def _read_identity(path, password):
    obj = json.loads(path.read_text('utf-8'))
    if obj.get('version') != 1 or obj.get('kdf') != 'argon2id':
        raise ValueError('Unsupported identity file format')
    try:
        key = _derive_password(password, bytes.fromhex(obj['salt']))
        raw = AESGCM(key).decrypt(bytes.fromhex(obj['nonce']),
                                  bytes.fromhex(obj['ciphertext']), b'CRYPTO-P2P-IDENTITY-V1')
        if len(raw) != 32: raise ValueError('Invalid identity bytes')
        return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    except (ValueError, KeyError) as exc:
        raise ValueError('Cannot unlock identity') from exc
    except Exception as exc:
        raise ValueError('Identity password incorrect or file damaged') from exc


class Identity:
    def __init__(self, private_key):
        self.key = private_key
        self.public = _raw_pub(private_key.public_key())
        self.fingerprint = _fingerprint(self.public)

    @classmethod
    def open(cls, folder, password, create=False):
        folder = Path(folder).expanduser().resolve()
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != 'nt': folder.chmod(0o700)
        path = folder / 'peer_identity.enc'
        if create:
            if len(password) < 12: raise ValueError('Use an identity password of at least 12 characters')
            key = ed25519.Ed25519PrivateKey.generate()
            _save_identity(path, key, password)
        else:
            if not path.is_file(): raise FileNotFoundError('Create a peer identity first')
            key = _read_identity(path, password)
        return cls(key)


def validate_request(method, amount, currency, destination, network='', memo=''):
    if method not in PROVIDERS: raise ValueError('Choose a supported payment method')
    currency = str(currency).strip().upper()
    if not CODE_RE.fullmatch(currency): raise ValueError('Invalid currency/asset code')
    try: value = Decimal(str(amount).strip())
    except (InvalidOperation, ValueError): raise ValueError('Invalid amount')
    if not value.is_finite() or value <= 0 or value > Decimal('1000000000000'):
        raise ValueError('Amount must be positive and finite')
    # This is a payment request, not a funding action or verified deposit.
    if value.as_tuple().exponent < -18: raise ValueError('Excessive decimal precision')
    network = str(network).strip()
    if not NETWORK_RE.fullmatch(network): raise ValueError('Invalid network name')
    destination = str(destination).strip()
    if not ADDRESS_RE.fullmatch(destination): raise ValueError('Provide public address or payment handle only')
    if '://' in destination or any(k in destination.lower() for k in (
            'seed phrase', 'private key', 'mnemonic', 'recovery phrase')):
        raise ValueError('Links, credentials and recovery words are not allowed as destinations')
    memo = str(memo).strip()
    if len(memo) > 160 or any(ord(c)<32 for c in memo): raise ValueError('Invalid memo')
    return {'type': 'payment_request', 'request_id': str(uuid.uuid4()),
            'method': method, 'amount': format(value, 'f'), 'currency': currency,
            'network': network, 'destination': destination, 'memo': memo,
            'status': 'REQUESTED_NOT_PAID'}


@lru_cache(maxsize=1)
def _bip39_words():
    path=Path(__file__).resolve().parent.parent/'data'/'2048_BIP_39_words.csv'
    try:
        with path.open(newline='',encoding='utf-8') as source:
            return frozenset(row['Word'].strip() for row in csv.DictReader(source)
                             if row.get('Word'))
    except (OSError, UnicodeError, ValueError):
        return frozenset()


def _safe_chat(text):
    if not isinstance(text,str) or not 1<=len(text)<=1000:
        raise ValueError('Chat message must contain 1–1000 characters')
    if any(ord(c)<32 and c not in '\t\n' for c in text):
        raise ValueError('Unsafe control character')
    # Block obvious secrets. Not a substitute for user caution or a content audit.
    if re.search(r'(?i)(seed phrase|recovery phrase|private key|api[_ -]?secret|cvv|bank password|mnemonic)',text):
        raise ValueError('Potential financial secret; chat will not transmit it')
    if re.search(r'(?<![a-zA-Z0-9])[a-fA-F0-9]{64}(?![a-zA-Z0-9])',text):
        raise ValueError('64-hex secret-like material is not allowed in chat')
    # Common payment-card PANs with a valid Luhn checksum cannot be posted.
    for candidate in re.findall(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)',text):
        digits=re.sub(r'\D','',candidate)
        if 13<=len(digits)<=19:
            total=0
            for i,d in enumerate(map(int,digits[::-1])):
                if i%2:d=d*2-9 if d*2>9 else d*2
                total+=d
            if total%10==0:raise ValueError('Payment card number detected; message blocked')
    # XMR-style 25-word recovery text is deliberately treated conservatively.
    if re.fullmatch(r'[a-zA-Z]+(?:[ \t]+[a-zA-Z]+){24}',text.strip()):
        raise ValueError('25-word phrase detected; message blocked')
    words=re.findall(r'[a-z]+', text.lower())
    dictionary=_bip39_words()
    if dictionary:
        for i in range(max(0,len(words)-11)):
            if all(w in dictionary for w in words[i:i+12]):
                raise ValueError('12 consecutive BIP39 seed words detected; message blocked')
    return text


def make_channel_message(identity, room, text):
    room=check_room(room); text=_safe_chat(text)
    payload={'type':'channel_message','channel':room,'text':text,
             'author_pub':identity.public.hex(),'message_id':str(uuid.uuid4())}
    payload['signature']=identity.key.sign(_json_bytes(payload)).hex()
    return payload


def _author_of(obj):
    try:
        pub=bytes.fromhex(obj['author_pub'])
        sig=bytes.fromhex(obj['signature'])
        if len(pub)!=32 or len(sig)!=64:raise ValueError('Malformed chat signature')
        ed25519.Ed25519PublicKey.from_public_bytes(pub).verify(
            sig,_json_bytes({k:v for k,v in obj.items() if k!='signature'}))
        return _fingerprint(pub)
    except Exception as exc:
        raise ValueError('Invalid chat author signature') from exc


def _verify_message(obj):
    if not isinstance(obj, dict): raise ValueError('Malformed peer message')
    msg_type = obj.get('type')
    if msg_type == 'payment_request':
        if set(obj) != {'type','request_id','method','amount','currency','network','destination','memo','status'}:
            raise ValueError('Unsupported request fields')
        if str(uuid.UUID(obj['request_id'])) != obj['request_id']: raise ValueError('Bad request ID')
        if obj['status'] != 'REQUESTED_NOT_PAID': raise ValueError('Untrusted payment status')
        data = validate_request(obj['method'], obj['amount'], obj['currency'],
                                obj['destination'], obj['network'], obj['memo'])
        for k in ('amount', 'currency', 'network', 'destination', 'memo'):
            if data[k] != obj[k]: raise ValueError('Invalid canonical request data')
    elif msg_type == 'message':
        if set(obj) != {'type','text'}: raise ValueError('Bad private message')
        _safe_chat(obj['text'])
    elif msg_type == 'profile':
        if set(obj)!={'type','nick'}:raise ValueError('Invalid profile')
        check_nick(obj['nick'])
    elif msg_type in ('channel_join','channel_part'):
        if set(obj)!={'type','channel'}:raise ValueError('Invalid channel event')
        check_room(obj['channel'])
    elif msg_type == 'channel_message':
        if set(obj) != {'type','channel','text','author_pub','message_id','signature'}:
            raise ValueError('Invalid chat frame')
        check_room(obj['channel']);_safe_chat(obj['text'])
        if str(uuid.UUID(obj['message_id'])) != obj['message_id']:
            raise ValueError('Bad chat message id')
        _author_of(obj)
    elif msg_type == 'roster':
        if set(obj) != {'type','users'} or not isinstance(obj['users'],list) or len(obj['users'])>25:
            raise ValueError('Invalid roster')
        seen=set()
        for user in obj['users']:
            if not isinstance(user,dict) or set(user)!={'fingerprint','nick','channels'}:
                raise ValueError('Invalid roster entry')
            fp=user['fingerprint']
            if not isinstance(fp,str) or not FINGERPRINT_RE.fullmatch(fp) or fp in seen:
                raise ValueError('Invalid roster fingerprint')
            seen.add(fp);check_nick(user['nick'])
            if not isinstance(user['channels'],list) or len(user['channels'])>8:
                raise ValueError('Invalid roster channels')
            for room in user['channels']:check_room(room)
    elif msg_type == 'mesh':
        # Complete checks (signature, expiry and hop count) happen inside mesh router.
        from core.mesh_network import _verify_packet
        _verify_packet(obj)
    elif msg_type in ('ping', 'pong'):
        if set(obj) != {'type'}: raise ValueError('Invalid keepalive')
    else: raise ValueError('Unsupported peer message')
    return obj


def _recv_exact(sock, n):
    out = bytearray()
    while len(out) < n:
        part = sock.recv(n-len(out))
        if not part: raise ConnectionError('Peer disconnected')
        out.extend(part)
    return bytes(out)


def _read_packet(sock):
    size = struct.unpack('!I', _recv_exact(sock, 4))[0]
    if not 0 < size <= MAX_FRAME: raise ValueError('Frame exceeds limit')
    return _recv_exact(sock, size)


def _write_packet(sock, data):
    if not 0 < len(data) <= MAX_FRAME: raise ValueError('Frame exceeds limit')
    sock.sendall(struct.pack('!I',len(data))+data)


def _hello(identity, role, ephemeral, nonce):
    data = {'v': VERSION, 'role': role, 'identity': identity.public.hex(),
            'ephemeral': _raw_pub(ephemeral.public_key()).hex(), 'nonce': nonce.hex()}
    data['signature'] = identity.key.sign(_json_bytes(data)).hex()
    return data


def _parse_hello(buf, role):
    try:
        msg = json.loads(buf)
        if set(msg) != {'v','role','identity','ephemeral','nonce','signature'}:
            raise ValueError('Unrecognized handshake fields')
        if msg['v'] != VERSION or msg['role'] != role: raise ValueError('Wrong protocol/role')
        identity_pub = bytes.fromhex(msg['identity'])
        ephemeral_pub = bytes.fromhex(msg['ephemeral'])
        nonce = bytes.fromhex(msg['nonce'])
        sig = bytes.fromhex(msg['signature'])
        if len(identity_pub)!=32 or len(ephemeral_pub)!=32 or len(nonce)!=24 or len(sig)!=64:
            raise ValueError('Malformed handshake')
        ed25519.Ed25519PublicKey.from_public_bytes(identity_pub).verify(
            sig, _json_bytes({k:v for k,v in msg.items() if k!='signature'}))
        return msg, _fingerprint(identity_pub)
    except Exception as exc:
        raise ValueError('Peer authentication failed') from exc


class Session:
    def __init__(self, sock, fingerprint, tx_key, rx_key, on_message, on_close):
        self.sock=sock; self.fingerprint=fingerprint
        self.tx=AESGCM(tx_key);self.rx=AESGCM(rx_key)
        self.tx_count=0;self.rx_count=0
        self.tx_lock=threading.Lock();self.closed=threading.Event()
        self.on_message=on_message;self.on_close=on_close
        self.last_seen=time.monotonic()
        self._seen=set();self._seen_order=[]

    def send(self, obj):
        if self.closed.is_set(): raise ConnectionError('Peer offline')
        _verify_message(obj)
        plain=_json_bytes(obj)
        if len(plain)>MAX_MESSAGE: raise ValueError('Message too long')
        with self.tx_lock:
            if self.tx_count >= 2**64: raise OverflowError('Nonce exhausted')
            nonce=b'\x00\x00\x00\x00'+self.tx_count.to_bytes(8,'big')
            data=self.tx.encrypt(nonce,plain,VERSION.encode())
            # Never risk AES-GCM nonce reuse after a partial network write.
            self.tx_count += 1
            try:_write_packet(self.sock,data)
            except BaseException:
                self.close()
                raise

    def loop(self):
        try:
            while not self.closed.is_set():
                ct=_read_packet(self.sock)
                nonce=b'\x00\x00\x00\x00'+self.rx_count.to_bytes(8,'big')
                obj=json.loads(self.rx.decrypt(nonce, ct, VERSION.encode()))
                self.rx_count+=1
                _verify_message(obj)
                self.last_seen=time.monotonic()
                if obj['type']=='ping': self.send({'type':'pong'})
                elif obj['type']!='pong':
                    if obj['type']=='payment_request':
                        rid=obj['request_id']
                        if rid in self._seen: continue
                        self._seen.add(rid);self._seen_order.append(rid)
                        if len(self._seen_order)>1000: self._seen.discard(self._seen_order.pop(0))
                    self.on_message(self.fingerprint,obj)
        except (OSError, ConnectionError, ValueError, TypeError): pass
        except Exception: pass
        finally:
            self.close()
            self.on_close(self.fingerprint,self)

    def close(self):
        if self.closed.is_set(): return
        self.closed.set()
        try: self.sock.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        try: self.sock.close()
        except OSError: pass


def handshake(sock, identity, is_client, approve=None, expected=None, on_message=None, on_close=None):
    """Requires outbound fingerprint pinning; inbound human approval. No TOFU auto-accept."""
    ephemeral=x25519.X25519PrivateKey.generate()
    mine=_hello(identity,'client' if is_client else 'server',ephemeral,os.urandom(24))
    sock.settimeout(110)
    if is_client:
        if not FINGERPRINT_RE.fullmatch(str(expected or '')):
            raise ValueError('Expected peer fingerprint (64 hex) required')
        _write_packet(sock,_json_bytes(mine))
        theirs, peer_fp = _parse_hello(_read_packet(sock),'server')
        if peer_fp != expected: raise ValueError('Peer fingerprint mismatch: connection refused')
        client,server=mine,theirs
    else:
        theirs, peer_fp = _parse_hello(_read_packet(sock),'client')
        if approve is None or not approve(peer_fp): raise PermissionError('Incoming peer not approved')
        _write_packet(sock,_json_bytes(mine))
        client,server=theirs,mine
    peer_ephemeral=x25519.X25519PublicKey.from_public_bytes(bytes.fromhex(theirs['ephemeral']))
    shared=ephemeral.exchange(peer_ephemeral)
    salt=hashlib.sha256(_json_bytes(client)+_json_bytes(server)).digest()
    keys=HKDF(algorithm=hashes.SHA256(),length=64,salt=salt,info=VERSION.encode()).derive(shared)
    tx,rx=(keys[:32],keys[32:]) if is_client else (keys[32:],keys[:32])
    sock.settimeout(50)  # Idle or stalled connections expire; no infinite read.
    session=Session(sock,peer_fp,tx,rx,on_message or (lambda *_:None),on_close or (lambda *_:None))
    session.inbound=not is_client
    return session


class PeerHub:
    def __init__(self, identity, event_callback, approve_callback, nickname="CryptoUser"):
        self.nickname=check_nick(nickname)
        self.rooms={"#general"}
        self.identity=identity
        self.event_callback=event_callback
        self.approve_callback=approve_callback
        self.sessions={}
        self.profiles={}
        self.remote_roster={}
        self._recent_chat=set()
        self._recent_order=[]
        self._lock=threading.RLock()
        self._listener=None
        self.tor_only=False
        self._tor_ready=lambda:False
        self._pending=threading.BoundedSemaphore(6)
        self._stop=threading.Event()
        self._ping_thread=threading.Thread(target=self._ping_loop,daemon=True)
        self._ping_thread.start()
        from core.mesh_network import MeshRouter
        self.mesh=MeshRouter(identity,self.peers,self.send,self.event_callback,self.nickname)

    def _emit(self, event, **kwargs):
        self.event_callback({'event':event,**kwargs})

    def require_tor(self, enabled, ready=None):
        # Enforced at the connection manager, not only in Tkinter controls.
        self.tor_only=bool(enabled)
        self._tor_ready=ready if enabled and callable(ready) else (lambda:False)
        if enabled:
            with self._lock:
                to_close=[s for s in self.sessions.values()
                          if getattr(s,'transport','direct') not in ('tor-outbound','onion-local')]
            for session in to_close:session.close()
            if getattr(self, 'bind_host', None)=='0.0.0.0':self.stop_listener()

    def is_tor_peer(self, fingerprint):
        with self._lock:
            session=self.sessions.get(fingerprint)
            return bool(session and not session.closed.is_set() and
                        getattr(session,'transport','direct') in ('tor-outbound','onion-local'))

    def peers(self):
        with self._lock:
            return sorted(fp for fp,s in self.sessions.items() if not s.closed.is_set())

    def _on_message(self, fp, obj):
        # Traffic already in flight is rejected if the Tor daemon becomes unavailable.
        if self.tor_only and (not self._tor_ready() or not self.is_tor_peer(fp)):
            with self._lock: session=self.sessions.get(fp)
            if session:session.close()
            return
        msg_type=obj['type']
        if msg_type=='mesh':
            try:self.mesh.receive(fp,obj)
            except (ValueError,TypeError,KeyError) as exc:
                self._emit('error',detail='Invalid mesh frame: '+type(exc).__name__)
            return
        if msg_type=='profile':
            with self._lock:
                self.profiles.setdefault(fp,{'nick':obj['nick'],'rooms':{'#general'}})['nick']=obj['nick']
            self._broadcast_roster()
            return
        if msg_type in ('channel_join','channel_part'):
            with self._lock:
                state=self.profiles.setdefault(fp,{'nick':None,'rooms':{'#general'}})
                if msg_type=='channel_join':
                    if len(state['rooms'])>=8 and obj['channel'] not in state['rooms']:return
                    state['rooms'].add(obj['channel'])
                else:state['rooms'].discard(obj['channel'])
            self._broadcast_roster()
            return
        if msg_type=='roster':
            with self._lock:
                session=self.sessions.get(fp)
                if not session or session.inbound:
                    if session:session.close()
                    return
            # Roster is a CLAIM made by a directly authenticated peer (the hub).
            # It does not independently verify the identity of relayed members.
            with self._lock:
                self.remote_roster[fp]=obj['users']
            self._emit('roster',fingerprint=fp,users=obj['users'])
            return
        if msg_type=='channel_message':
            author=_author_of(obj)
            with self._lock:
                if obj['message_id'] in self._recent_chat:return
                # A direct participant must never impersonate a remote author.
                # A relayed author is only accepted from our outbound hub session.
                sess=self.sessions.get(fp)
                if author!=fp and (not sess or sess.inbound):return
                self._recent_chat.add(obj['message_id'])
                self._recent_order.append(obj['message_id'])
                if len(self._recent_order)>2000:
                    self._recent_chat.discard(self._recent_order.pop(0))
                forward=[(key,session) for key,session in self.sessions.items()
                         if key!=fp and session.inbound and not session.closed.is_set()
                         and obj['channel'] in self.profiles.get(key,{}).get('rooms',set())]
            if obj['channel'] in self.rooms:
                self._emit('chat',fingerprint=author,via=fp,data=obj)
            # The LAN host relays channel traffic hop-to-hop, never wallet secrets.
            for _,session in forward:
                try:self._send_session(session,obj)
                except Exception:session.close()
            return
        self._emit('message',fingerprint=fp,data=obj)

    def roster(self):
        with self._lock:
            users=[{'fingerprint':self.identity.fingerprint,'nick':self.nickname,
                    'channels':sorted(self.rooms)}]
            for fp,state in sorted(self.profiles.items()):
                if fp in self.sessions and not self.sessions[fp].closed.is_set() and state['nick'] is not None:
                    users.append({'fingerprint':fp,'nick':state['nick'],
                                  'channels':sorted(state['rooms'])})
            return users[:25]

    def _broadcast_roster(self):
        obj={'type':'roster','users':self.roster()}
        with self._lock:
            recipients=[s for s in self.sessions.values() if s.inbound and not s.closed.is_set()]
        for sess in recipients:
            try:self._send_session(sess,obj)
            except Exception:sess.close()
        self._emit('roster',fingerprint=self.identity.fingerprint,users=obj['users'])

    def set_nickname(self,name):
        self.nickname=check_nick(name)
        with self._lock:sessions=list(self.sessions.values())
        for session in sessions:
            try:self._send_session(session,{'type':'profile','nick':self.nickname})
            except Exception:session.close()
        self._broadcast_roster()

    def join_room(self,room):
        room=check_room(room)
        if len(self.rooms)>=8 and room not in self.rooms:
            raise ValueError('Join at most eight rooms')
        self.rooms.add(room)
        with self._lock:sessions=list(self.sessions.values())
        for sess in sessions:self._send_session(sess,{'type':'channel_join','channel':room})
        self._broadcast_roster()

    def part_room(self,room):
        room=check_room(room)
        self.rooms.discard(room)
        with self._lock:sessions=list(self.sessions.values())
        for sess in sessions:self._send_session(sess,{'type':'channel_part','channel':room})
        self._broadcast_roster()

    def send_channel(self,room,text):
        if room not in self.rooms:raise ValueError('Join the channel before posting')
        obj=make_channel_message(self.identity,room,text)
        with self._lock:
            peers=[s for fp,s in self.sessions.items() if not s.closed.is_set()
                   and (not s.inbound or room in self.profiles.get(fp,{}).get('rooms',set()))]
        if not peers:raise ConnectionError('No connected peers')
        for sess in peers:self._send_session(sess,obj)
        self._emit('local_chat',data=obj)
        return obj


    def _on_close(self, fp, session):
        with self._lock:
            if self.sessions.get(fp) is session:
                del self.sessions[fp]
                self.profiles.pop(fp,None)
                self.remote_roster.pop(fp,None)
                self._emit('offline', fingerprint=fp)
        self._broadcast_roster()

    def _register(self, session):
        with self._lock:
            if len(self.sessions)>=24 and session.fingerprint not in self.sessions:
                session.close()
                raise ConnectionError('Room has reached its 24-peer connection limit')
            previous=self.sessions.get(session.fingerprint)
            if previous: previous.close()
            self.sessions[session.fingerprint]=session
            # Roster members are published only after their authenticated profile arrives.
            self.profiles[session.fingerprint]={'nick':None,'rooms':{'#general'}}
        self._emit('online',fingerprint=session.fingerprint)
        threading.Thread(target=session.loop,daemon=True).start()
        try:
            self._send_session(session,{'type':'profile','nick':self.nickname})
            for room in sorted(self.rooms):self._send_session(session,{'type':'channel_join','channel':room})
        except Exception:session.close()
        self._broadcast_roster()
        if self.mesh.enabled:self.mesh.on_new_peer(session.fingerprint)

    def listen(self, host='127.0.0.1', port=19420):
        if self.tor_only and host!='127.0.0.1':
            raise PermissionError('Tor-only mode cannot bind a LAN-facing listener')
        if host not in ('127.0.0.1','0.0.0.0'):
            raise ValueError('Only local loopback or explicit LAN bind supported')
        port=int(port)
        if port != 0 and not 1024 <= port <= 65535: raise ValueError('Invalid listen port')
        if self._listener: raise RuntimeError('Already listening')
        self.bind_host=host;self.listen_port=port
        sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:
            sock.bind((host,port))
        except OSError:
            sock.close()
            raise
        self.listen_port=sock.getsockname()[1]
        sock.listen(8);sock.settimeout(0.5)
        self._listener=sock
        threading.Thread(target=self._accept_loop,args=(sock,),daemon=True).start()
        self._emit('listening', host=host,port=self.listen_port)

    def _accept_loop(self,listener):
        while not self._stop.is_set() and self._listener is listener:
            try: client,_=listener.accept()
            except socket.timeout: continue
            except OSError: break
            if not self._pending.acquire(blocking=False):
                client.close();continue
            threading.Thread(target=self._accept_one,args=(client,),daemon=True).start()

    def _accept_one(self,sock):
        try:
            if self.tor_only and sock.getpeername()[0] not in ('127.0.0.1','::1'):
                raise PermissionError('Tor-only P2P requires a local onion-service connection')
            session=handshake(sock,self.identity,False,approve=self.approve_callback,
                              on_message=self._on_message,on_close=self._on_close)
            session.transport='onion-local' if self.tor_only else 'direct'
            if self.tor_only and not self._tor_ready():
                raise ConnectionError('Tor daemon is not ready')
            self._register(session)
        except Exception as e:
            self._emit('error', detail=type(e).__name__+': '+str(e)[:90])
            try: sock.close()
            except OSError: pass
        finally:
            self._pending.release()

    def connect(self,host,port,expected_fingerprint,via_tor=False,proxy_host='127.0.0.1',proxy_port=9050):
        host=str(host).strip()
        if not host or any(c in host for c in '/:@\\') or len(host)>253:
            raise ValueError('Invalid destination hostname')
        port=int(port)
        if not 1<=port<=65535:raise ValueError('Invalid port')
        if not FINGERPRINT_RE.fullmatch(expected_fingerprint):
            raise ValueError('Enter the exact peer fingerprint')
        if self.tor_only and (not via_tor or not self._tor_ready()):
            raise PermissionError('Tor-only mode blocks direct or unready connections')
        if via_tor:
            if proxy_host not in ('127.0.0.1','localhost','::1'):
                raise ValueError('Tor SOCKS proxy must be local; remote proxy refused')
            if not re.fullmatch(r'[a-z2-7]{56}\.onion',host):
                raise ValueError('Tor mode requires a v3 .onion address; direct fallback forbidden')
            try: import socks
            except ImportError: raise RuntimeError('Install PySocks for Tor mode; direct connection refused')
            sock=socks.socksocket()
            # SOCKS authentication acts as Tor stream-isolation context, not
            # proof of identity; the signed handshake authenticates the peer.
            sock.set_proxy(socks.SOCKS5,proxy_host,int(proxy_port),rdns=True,
                           username=os.urandom(12).hex(), password=os.urandom(12).hex())
        else:
            if host.endswith('.onion'): raise ValueError('Onion addresses require Tor mode')
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            sock.settimeout(15);sock.connect((host,port))
            sess=handshake(sock,self.identity,True,expected=expected_fingerprint,
                           on_message=self._on_message,on_close=self._on_close)
            sess.transport='tor-outbound' if via_tor else 'direct'
            if self.tor_only and not self._tor_ready():
                raise ConnectionError('Tor became unavailable before peer registration')
            self._register(sess)
            return expected_fingerprint
        except BaseException:
            sock.close()
            raise

    def _send_session(self, session, message):
        if session.closed.is_set():raise ConnectionError('Peer is offline')
        if self.tor_only and (not self._tor_ready() or
                getattr(session,'transport','direct') not in ('tor-outbound','onion-local')):
            raise PermissionError('Tor-only P2P is unavailable; direct fallback blocked')
        session.send(message)

    def send(self,fp,obj):
        with self._lock: sess=self.sessions.get(fp)
        if not sess or sess.closed.is_set(): raise ConnectionError('Peer is not connected')
        if self.tor_only and (not self._tor_ready() or
                getattr(sess,'transport','direct') not in ('tor-outbound','onion-local')):
            raise PermissionError('Tor-only P2P is unavailable; direct fallback blocked')
        self._send_session(sess,obj)

    def _ping_loop(self):
        while not self._stop.wait(15):
            with self._lock: sessions=list(self.sessions.values())
            for s in sessions:
                try:self._send_session(s,{'type':'ping'})
                except Exception:s.close()

    def fail_closed(self):
        # Leave Tor-only policy engaged. Require a deliberate reconnect after
        # the daemon recovers; do not silently reopen a direct listener.
        self.stop_listener()
        with self._lock:sessions=list(self.sessions.values())
        for session in sessions:session.close()

    def stop_listener(self):
        listener=self._listener;self._listener=None
        if listener:
            try:listener.close()
            except OSError:pass
        self._emit('listener_stopped')

    def close(self):
        self._stop.set();self.stop_listener()
        with self._lock:
            sessions=list(self.sessions.values());self.sessions.clear()
        for s in sessions:s.close()
