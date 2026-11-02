"""Experimental WAN chat using signed public contact cards + per-recipient E2E encryption.

This is NOT a cryptocurrency signing API or financial transfer mechanism. No wallet
keys, recovery phrases, payment credentials, or fiat balances are accessed here.
The relaying server has access to contact metadata, public identities, room names,
network addresses, and traffic times, but not the message plaintext.
"""
from __future__ import annotations
import hashlib, json, os, re, time, uuid
from pathlib import Path
from urllib.parse import urlparse, quote
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.peer_network import Identity, _safe_chat
from core.lan_chat import check_room, check_nick

FP = re.compile(r'^[0-9a-f]{64}$')
HEX32 = re.compile(r'^[0-9a-f]{64}$')
ID = re.compile(r'^[a-f0-9-]{36}$')
MAX_TEXT = 1000


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def raw_public(pub):
    return pub.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)


def encrypt_key(identity: Identity):
    # Separate domain-specific X25519 secret from the existing P2P signing key.
    # This deterministic static key means compromise of identity key compromises
    # old chats: the protocol does NOT offer forward secrecy against that event.
    raw = identity.key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,
                                     serialization.NoEncryption())
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                   info=b'CRYPTO-WAN-chat-x25519-v1').derive(raw)
    return x25519.X25519PrivateKey.from_private_bytes(derived)


def contact_card(identity, nickname):
    nick=check_nick(nickname)
    card={'version':1,'nickname':nick,'sign_pub':identity.public.hex(),
          'enc_pub':raw_public(encrypt_key(identity).public_key()).hex()}
    card['signature']=identity.key.sign(canonical(card)).hex()
    return card


def validate_card(card):
    if not isinstance(card,dict) or set(card)!={'version','nickname','sign_pub','enc_pub','signature'}:
        raise ValueError('Bad public contact card')
    if card['version']!=1:raise ValueError('Unsupported contact card')
    check_nick(card['nickname'])
    signing=bytes.fromhex(card['sign_pub']);enc=bytes.fromhex(card['enc_pub']);sig=bytes.fromhex(card['signature'])
    if len(signing)!=32 or len(enc)!=32 or len(sig)!=64:raise ValueError('Bad contact key')
    ed25519.Ed25519PublicKey.from_public_bytes(signing).verify(sig,canonical({k:v for k,v in card.items() if k!='signature'}))
    return hashlib.sha256(signing).hexdigest()


def validate_server_url(url, via_tor=False):
    parsed=urlparse(str(url).strip())
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Relay URL must contain only a scheme, hostname, and optional port')
    if parsed.scheme=='https' and parsed.hostname and not parsed.hostname.endswith('.onion'):
        return str(url).strip().rstrip('/')
    if (via_tor and parsed.scheme=='http' and parsed.hostname and
            re.fullmatch(r'[a-z2-7]{56}\.onion',parsed.hostname)):
        return str(url).strip().rstrip('/')
    if parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1'):
        return str(url).strip().rstrip('/')
    raise ValueError('Public relay requires verified HTTPS; plaintext HTTP only for localhost development')


def request_headers(identity, method, path, body=b'', at=None, nonce=None):
    at=str(int(time.time() if at is None else at)); nonce=nonce or str(uuid.uuid4())
    digest=hashlib.sha256(body).hexdigest()
    data=canonical({'method':method.upper(),'path':path,'digest':digest,'time':at,'nonce':nonce})
    return {'X-CRYPTO-Identity':identity.public.hex(), 'X-CRYPTO-Time':at,
            'X-CRYPTO-Nonce':nonce, 'X-CRYPTO-Signature':identity.key.sign(data).hex()}


def _shared_key(private, public_raw, salt):
    exchange=private.exchange(x25519.X25519PublicKey.from_public_bytes(public_raw))
    return HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,
                info=b'CRYPTO-WAN-ENVELOPE-V1').derive(exchange)


def seal(identity, recipient_card, text, room='', kind='message'):
    recipient=validate_card(recipient_card)
    if kind not in ('message','room','payment_request'):raise ValueError('Unsupported message type')
    _safe_chat(text)
    if room:check_room(room)
    if kind=='room' and not room:raise ValueError('Room required')
    if kind!='room' and room:raise ValueError('Room not permitted for this message type')
    sender=hashlib.sha256(identity.public).hexdigest()
    msg_id=str(uuid.uuid4())
    eph=x25519.X25519PrivateKey.generate()
    salt=hashlib.sha256((msg_id+sender+recipient).encode('ascii')).digest()
    nonce=os.urandom(12)
    aad=canonical({'id':msg_id,'from':sender,'to':recipient,'v':1})
    plaintext=canonical({'type':kind,'room':room,'text':text})
    ciphertext=AESGCM(_shared_key(eph,bytes.fromhex(recipient_card['enc_pub']),salt)).encrypt(nonce,plaintext,aad)
    envelope={'id':msg_id,'from':sender,'to':recipient,'ephemeral':raw_public(eph.public_key()).hex(),
              'nonce':nonce.hex(),'ciphertext':ciphertext.hex(),'created':int(time.time()),'v':1}
    envelope['signature']=identity.key.sign(canonical(envelope)).hex()
    return envelope


def open_envelope(identity, sender_card, envelope):
    sender_fp=validate_card(sender_card)
    if not isinstance(envelope,dict) or set(envelope)!={'id','from','to','ephemeral','nonce','ciphertext','created','v','signature'}:
        raise ValueError('Invalid encrypted envelope structure')
    if envelope['v']!=1 or sender_fp!=envelope['from'] or envelope['to']!=identity.fingerprint:
        raise ValueError('Incorrect sender/recipient or version')
    if len(canonical(envelope))>8000:raise ValueError('Envelope too large')
    uuid.UUID(envelope['id'])
    ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(sender_card['sign_pub'])).verify(
        bytes.fromhex(envelope['signature']),canonical({k:v for k,v in envelope.items() if k!='signature'}))
    salt=hashlib.sha256((envelope['id']+sender_fp+identity.fingerprint).encode('ascii')).digest()
    aad=canonical({'id':envelope['id'],'from':sender_fp,'to':identity.fingerprint,'v':1})
    decoded=AESGCM(_shared_key(encrypt_key(identity),bytes.fromhex(envelope['ephemeral']),salt)).decrypt(
        bytes.fromhex(envelope['nonce']),bytes.fromhex(envelope['ciphertext']),aad)
    value=json.loads(decoded)
    if set(value)!={'type','room','text'} or value['type'] not in ('message','room','payment_request'):
        raise ValueError('Unsupported decrypted chat content')
    _safe_chat(value['text'])
    if value['type']=='room':check_room(value['room'])
    elif value['room']:raise ValueError('Unexpected room')
    return value


class WANContacts:
    """Public verified contact cards only. Never store wallet details."""
    def __init__(self, folder):
        self.path=Path(folder).expanduser()/'wan_contacts.json'
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.cards={}
        if self.path.is_file():
            if self.path.stat().st_size>100000:raise ValueError('Contact database too large')
            rows=json.loads(self.path.read_text('utf8'))
            if not isinstance(rows,dict):raise ValueError('Invalid contacts')
            for fp,card in rows.items():
                if validate_card(card)!=fp:raise ValueError('Tampered contact database')
                self.cards[fp]=card

    def trust(self,card):
        fp=validate_card(card)
        if fp not in self.cards and len(self.cards)>=200:raise ValueError('Too many trusted contacts')
        if fp in self.cards and self.cards[fp]['enc_pub']!=card['enc_pub']:
            raise ValueError('Encryption key changed: identity verification required')
        self.cards[fp]=card
        self._save();return fp

    def _save(self):
        tmp=self.path.with_suffix('.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(self.cards,f,sort_keys=True);f.flush();os.fsync(f.fileno())
        os.replace(tmp,self.path)
        if os.name!='nt':self.path.chmod(0o600)


class WANClient:
    def __init__(self,identity,nickname,base_url,session=None,via_tor=False):
        import requests
        self.identity=identity
        self.card=contact_card(identity,nickname)
        self.url=validate_server_url(base_url,via_tor=via_tor)
        self.session=session or requests.Session()
        self.session.trust_env=False # Prevent ambient proxy settings/credential leaks.
        if via_tor:
            try: import socks
            except ImportError as e:raise RuntimeError('PySocks required for Tor; refusing direct fallback') from e
            self.session.proxies={'http':'socks5h://127.0.0.1:9050',
                                  'https':'socks5h://127.0.0.1:9050'}

    def request(self,method,path,data=None):
        body=canonical(data) if data is not None else b''
        headers=request_headers(self.identity,method,path,body)
        if data is not None:headers['Content-Type']='application/json'
        result=self.session.request(method,self.url+path,data=body if data is not None else None,
                                    headers=headers,timeout=10,allow_redirects=False)
        if result.status_code!=200:
            raise ConnectionError(f'Relay rejected request: HTTP {result.status_code} {result.text[:140]}')
        return result.json()

    def register(self):return self.request('POST','/v1/register',{'card':self.card})
    def heartbeat(self):return self.request('POST','/v1/heartbeat',{})
    def directory(self):return self.request('GET','/v1/directory')
    def join(self,room):return self.request('POST','/v1/room/join',{'room':check_room(room)})
    def leave(self,room):return self.request('POST','/v1/room/leave',{'room':check_room(room)})
    def members(self,room):return self.request('GET','/v1/room/members?room='+quote(check_room(room),safe=''))
    def send(self,envelope):return self.request('POST','/v1/send',{'envelope':envelope})
    def inbox(self):return self.request('GET','/v1/inbox')
    def ack(self,ids):return self.request('POST','/v1/ack',{'ids':ids})
