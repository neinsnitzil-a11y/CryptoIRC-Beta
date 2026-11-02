"""VaultForge Mesh Chat — experimental authenticated peer mesh / IRC-style CLI.

NOT the IRC wire protocol. Local passwords never travel across the mesh.
Link encryption uses authenticated X25519+Ed25519+HKDF+AES-GCM.
Public room messages are visible to intermediate routing nodes; DMs are end-to-end encrypted.
This protocol is newly developed and NOT independently audited.
"""
from __future__ import annotations

import argparse
import ipaddress
import tempfile
import asyncio
import base64
from collections import deque
from dataclasses import dataclass, field
from getpass import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import sys
import struct
import time
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from argon2.low_level import hash_secret_raw, Type

# Isolated mode (-I) intentionally hides the script directory from Python imports.
_BUNDLE = str(Path(__file__).resolve().parent)
if _BUNDLE not in sys.path:
    sys.path.insert(0, _BUNDLE)

class PeerIdentityChanged(ValueError):
    """An authenticated handshake produced a different key than the pinned key.

    The presented fingerprint is untrusted until verified separately with the
    operator. Never auto-pin it on a mismatch.
    """
    def __init__(self, endpoint: str, pinned: str, presented: str):
        self.endpoint = endpoint
        self.pinned = pinned
        self.presented = presented
        super().__init__(f'Peer identity changed for {endpoint}: expected {pinned}, got {presented}. Refusing connection.')


PROTOCOL = 'vaultforge-mesh-1'
MAX_FRAME = 16384
MAX_MESSAGE = 1500
MAX_PEERS = 24
PRESENCE_INTERVAL = 10
PRESENCE_EXPIRE = 40
MAX_AGE = 120
NAME = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{2,23}$')
ROOM = re.compile(r'^#[a-zA-Z0-9_-]{1,32}$')
DEFAULT_ROOM = '#general'
DISCOVERY_PORT = 48877
DISCOVERY_MAGIC = 'vaultforge-mesh-lan-v1'
DEFAULT_BOOTSTRAP = '18.227.91.173:6667'  # User-configurable community bootstrap; not guaranteed online.
MAX_PUBLIC_NODES = 48
PUBLIC_NODE_TTL = 65  # Seconds without a fresh signed advertisement.



def is_lan_host(host: str) -> bool:
    """Offline/LAN mode permits IP literals on private/link-local/loopback ranges only."""
    if host.lower() == 'localhost':
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False  # No DNS lookup in offline mode.
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in ipaddress.ip_network(r) for r in
                   ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
                    '127.0.0.0/8', '169.254.0.0/16'))
    return address.is_loopback or address.is_link_local or address in ipaddress.ip_network('fc00::/7')


class LanDiscoveryResponder(asyncio.DatagramProtocol):
    """Respond only to opt-in local UDP discovery, never publish credentials."""
    def __init__(self, node):
        self.node = node
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not is_lan_host(addr[0]) or len(data) > 512:
            return
        try:
            msg = json.loads(data)
            if msg.get('type') != 'discover' or msg.get('magic') != DISCOVERY_MAGIC:
                return
            nonce = msg['nonce']
            if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{24}', nonce):
                return
            response = {'type': 'here', 'magic': DISCOVERY_MAGIC, 'nonce': nonce,
                        'port': self.node.current_port, 'nick': self.node.ident.nick,
                        'pub': b64(self.node.ident.pub), 'time': int(time.time())}
            response['sig'] = b64(self.node.ident.signing.sign(canon(response)))
            self.transport.sendto(canon(response), addr)
        except (ValueError, KeyError, TypeError, OSError, OverflowError):
            return


class LanDiscoveryClient(asyncio.DatagramProtocol):
    def __init__(self, nonce):
        self.nonce = nonce
        self.results = {}

    def datagram_received(self, data, addr):
        if len(data) > 1024 or not is_lan_host(addr[0]):
            return
        try:
            msg = json.loads(data)
            if msg.get('type') != 'here' or msg.get('magic') != DISCOVERY_MAGIC or msg.get('nonce') != self.nonce:
                return
            pub = un64(msg['pub'], 32)
            sig = un64(msg['sig'], 64)
            unsigned = {k: v for k, v in msg.items() if k != 'sig'}
            ed25519.Ed25519PublicKey.from_public_bytes(pub).verify(sig, canon(unsigned))
            if not NAME.fullmatch(msg['nick']) or type(msg['port']) is not int or not 1 <= msg['port'] <= 65535:
                return
            if type(msg['time']) is not int or abs(time.time() - msg['time']) > 30:
                return
            endpoint = f'{addr[0]}:{msg["port"]}'
            self.results[endpoint] = (msg['nick'], fingerprint(pub), endpoint)
        except (ValueError, KeyError, TypeError, OverflowError, Exception):
            return


async def scan_lan(timeout: float = 1.5, targets: tuple[str, ...] = ('255.255.255.255', '127.0.0.1')) -> list[tuple[str, str, str]]:
    """Opt-in local UDP discovery; not an internet-wide port/network scan."""
    nonce = secrets.token_hex(12)
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: LanDiscoveryClient(nonce), local_addr=('0.0.0.0', 0), allow_broadcast=True)
    try:
        request = canon({'type': 'discover', 'magic': DISCOVERY_MAGIC, 'nonce': nonce})
        for target in targets:
            if not is_lan_host(target) and target != '255.255.255.255':
                raise ValueError('LAN scan target must be a private/local IP address')
            transport.sendto(request, (target, DISCOVERY_PORT))
        await asyncio.sleep(max(0.05, min(timeout, 5.0)))
        return sorted(protocol.results.values(), key=lambda r: (r[0].lower(), r[2]))[:64]
    finally:
        transport.close()


def show_discovered(peers: list[tuple[str, str, str]]) -> None:
    print('\nLAN PEER DISCOVERY (only peers that opted into LAN discovery)')
    if not peers:
        print('[EMPTY] No LAN peers responded. Confirm both devices are on the same LAN,')
        print('        LAN hosting is enabled, and UDP port 48877 is allowed on the host.')
    for i, (nick, ident, endpoint) in enumerate(peers, 1):
        print(f'  {i}. {nick}@{ident}  {endpoint}')
    print('Results are advertisements; verify peer fingerprints out-of-band before trusting.\n')




def public_endpoint(value: str) -> str:
    """Only literal globally routable IP endpoints may enter the public directory.

    No DNS names, loopback, RFC1918, cloud metadata, link-local or onion targets.
    A node's signed claim is NOT proof its port is actually reachable.
    """
    host, port = parse_endpoint(value)
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError('Public node announcements require a numeric public IP address') from exc
    if not address.is_global:
        raise ValueError('A public node must advertise a globally routable IP, not private/loopback space')
    return f'[{address}]:{port}' if address.version == 6 else f'{address}:{port}'


def show_public_nodes(rows: list[tuple[str, str, str]]) -> None:
    print('\nPUBLIC VAULTFORGE MESH NODES (signed opt-in announcements)')
    if not rows:
        print('[EMPTY] No public nodes were advertised by your connected bootstrap peers.')
        print('[HELP] AWS must be running and configured with --advertise PUBLIC_IP:PORT.')
        print('[HELP] User-hosted nodes must connect to a shared bootstrap and opt in to publishing.')
    for i, (name, key, endpoint) in enumerate(rows, 1):
        print(f' {i:2}. {name}@{key}  {endpoint}')
    print('Claims are signed but NOT independently verified as reachable or safe.')
    print('Check the fingerprint independently before trusting a node.\n')


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode('ascii')


def un64(s: str, size: int | None = None) -> bytes:
    limit = 512 if size is not None else 10000
    if not isinstance(s, str) or len(s) > limit:
        raise ValueError('Invalid binary field')
    value = base64.b64decode(s, validate=True)
    if size is not None and len(value) != size:
        raise ValueError('Incorrect key length')
    return value


def canon(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('utf-8')


def fingerprint(pub: bytes) -> str:
    return hashlib.sha256(pub).hexdigest()[:16]


def raw_pub(key: Any) -> bytes:
    return key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)


def raw_priv(key: Any) -> bytes:
    return key.private_bytes(encoding=serialization.Encoding.Raw,
                             format=serialization.PrivateFormat.Raw,
                             encryption_algorithm=serialization.NoEncryption())


def secure_root(root: Path | None = None) -> Path:
    root = root or Path.home() / 'VaultForge' / 'mesh_chat'
    if root.is_symlink() or root.parent.is_symlink():
        raise ValueError('Chat storage may not be a symlink')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        os.chmod(root, 0o700)
    return root


def secure_save(path: Path, obj: dict) -> None:
    if path.is_symlink():
        raise ValueError('Refusing symlink storage file')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name('.' + path.name + '.' + secrets.token_hex(6))
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(canon(obj))
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
        if os.name != 'nt':
            os.chmod(path, 0o600)
    finally:
        tmp.unlink(missing_ok=True)


def secure_load(path: Path, max_size: int = 500000) -> dict:
    if path.is_symlink():
        raise ValueError('Refusing symlink storage file')
    if not path.exists():
        return {}
    if path.stat().st_size > max_size:
        raise ValueError('Storage file too large')
    obj = json.loads(path.read_text('utf-8'))
    if not isinstance(obj, dict):
        raise ValueError('Invalid storage file')
    return obj


def _kdf(password: str, salt: bytes) -> bytes:
    return hash_secret_raw(password.encode('utf-8'), salt, time_cost=3,
                           memory_cost=65536, parallelism=1, hash_len=32, type=Type.ID)


@dataclass
class Identity:
    nick: str
    signing: ed25519.Ed25519PrivateKey
    exchange: x25519.X25519PrivateKey

    @property
    def pub(self) -> bytes:
        return raw_pub(self.signing.public_key())

    @property
    def keyid(self) -> str:
        return fingerprint(self.pub)

    @property
    def boxpub(self) -> bytes:
        return raw_pub(self.exchange.public_key())


def create_account(root: Path, nick: str, password: str) -> Identity:
    if not NAME.fullmatch(nick):
        raise ValueError('Nickname must be 3-24 characters: letters, numbers, _ or -; start with letter')
    if len(password) < 14:
        raise ValueError('Chat password must have at least 14 characters')
    root = secure_root(root)
    path = root / 'accounts.json'
    accounts = secure_load(path)
    if nick.lower() in accounts:
        raise ValueError('This username already exists on this device')
    signing = ed25519.Ed25519PrivateKey.generate()
    exchange = x25519.X25519PrivateKey.generate()
    identity = Identity(nick, signing, exchange)
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    secret = raw_priv(signing) + raw_priv(exchange)
    key = _kdf(password, salt)
    encrypted = AESGCM(key).encrypt(nonce, secret, f'{PROTOCOL}|{nick.lower()}'.encode())
    accounts[nick.lower()] = {'nick': nick, 'pub': b64(identity.pub), 'boxpub': b64(identity.boxpub),
                              'salt': b64(salt), 'nonce': b64(nonce), 'ciphertext': b64(encrypted),
                              'kdf': 'argon2id-3-65536-1'}
    secure_save(path, accounts)
    return identity


def login(root: Path, nick: str, password: str) -> Identity:
    record = secure_load(secure_root(root) / 'accounts.json').get(nick.lower())
    if not isinstance(record, dict):
        raise ValueError('Unknown local chat account or incorrect password')
    if record.get('kdf') != 'argon2id-3-65536-1':
        raise ValueError('Unsupported chat account format')
    try:
        plain = AESGCM(_kdf(password, un64(record['salt'], 16))).decrypt(
            un64(record['nonce'], 12), un64(record['ciphertext']),
            f'{PROTOCOL}|{nick.lower()}'.encode())
        if len(plain) != 64:
            raise ValueError('Invalid key material')
        ident = Identity(record['nick'], ed25519.Ed25519PrivateKey.from_private_bytes(plain[:32]),
                         x25519.X25519PrivateKey.from_private_bytes(plain[32:]))
        if not hmac.compare_digest(ident.pub, un64(record['pub'], 32)) or \
           not hmac.compare_digest(ident.boxpub, un64(record['boxpub'], 32)):
            raise ValueError('Chat identity key mismatch')
        return ident
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise ValueError('Unknown local chat account or incorrect password') from exc
    except Exception as exc:
        raise ValueError('Unable to unlock chat account (incorrect password or damaged account)') from exc


def change_account_password(root: Path, nick: str, old: str, new: str) -> None:
    ident = login(root, nick, old)
    if len(new) < 14:
        raise ValueError('New password must be at least 14 characters')
    path = secure_root(root) / 'accounts.json'
    accounts = secure_load(path)
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    secret = raw_priv(ident.signing) + raw_priv(ident.exchange)
    record = accounts[nick.lower()]
    record.update({'salt': b64(salt), 'nonce': b64(nonce), 'ciphertext': b64(AESGCM(_kdf(new, salt)).encrypt(
        nonce, secret, f'{PROTOCOL}|{nick.lower()}'.encode()))})
    secure_save(path, accounts)


def sign_message(ident: Identity, kind: str, data: dict) -> dict:
    payload = {'kind': kind, 'origin': b64(ident.pub), 'nick': ident.nick, 'time': int(time.time()),
               'id': secrets.token_hex(12), 'data': data}
    payload['sig'] = b64(ident.signing.sign(canon(payload)))
    return payload


def validate_message(item: dict, *, allow_expired: bool = False) -> tuple[str, str]:
    if not isinstance(item, dict) or set(item) != {'kind', 'origin', 'nick', 'time', 'id', 'data', 'sig'}:
        raise ValueError('Invalid gossip envelope')
    pub = un64(item['origin'], 32)
    if not NAME.fullmatch(item['nick']) or not isinstance(item['data'], dict) or \
       not isinstance(item['id'], str) or not re.fullmatch('[0-9a-f]{24}', item['id']) or \
       type(item['time']) is not int or (not allow_expired and abs(int(time.time()) - item['time']) > MAX_AGE):
        raise ValueError('Invalid message metadata or expired message')
    unsigned = {k: v for k, v in item.items() if k != 'sig'}
    ed25519.Ed25519PublicKey.from_public_bytes(pub).verify(un64(item['sig'], 64), canon(unsigned))
    if item['kind'] not in ('presence', 'chat', 'dm', 'file_start', 'file_chunk', 'node_advert'):
        raise ValueError('Unknown message type')
    return fingerprint(pub), item['kind']


def seal_dm(sender: Identity, recipient_boxpub: bytes, to_id: str, text: str) -> dict:
    ephemeral = x25519.X25519PrivateKey.generate()
    eph_pub = raw_pub(ephemeral.public_key())
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(sender.pub + eph_pub).digest(),
             info=b'vaultforge-mesh-dm-v1').derive(
                 ephemeral.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_boxpub)))
    nonce = secrets.token_bytes(12)
    aad = sender.pub + to_id.encode('ascii')
    return {'to': to_id, 'eph': b64(eph_pub), 'nonce': b64(nonce),
            'cipher': b64(AESGCM(k).encrypt(nonce, text.encode('utf-8'), aad))}


def open_dm(recipient: Identity, sender_pub: bytes, data: dict) -> str:
    if data['to'] != recipient.keyid:
        raise ValueError('Not intended for this account')
    eph = un64(data['eph'], 32)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(sender_pub + eph).digest(),
               info=b'vaultforge-mesh-dm-v1').derive(recipient.exchange.exchange(
                   x25519.X25519PublicKey.from_public_bytes(eph)))
    return AESGCM(key).decrypt(un64(data['nonce'], 12), un64(data['cipher']),
                               sender_pub + recipient.keyid.encode('ascii')).decode('utf-8')


def signed_hello(ident: Identity, eph: bytes, nonce: bytes, role: str) -> dict:
    obj = {'protocol': PROTOCOL, 'role': role, 'pub': b64(ident.pub), 'eph': b64(eph), 'nonce': b64(nonce)}
    obj['sig'] = b64(ident.signing.sign(b'vaultforge-mesh-handshake-v1|' + canon(obj)))
    return obj


def verify_hello(obj: dict, expected_role: str) -> tuple[bytes, bytes]:
    if not isinstance(obj, dict) or obj.get('protocol') != PROTOCOL or obj.get('role') != expected_role or \
       set(obj) != {'protocol', 'role', 'pub', 'eph', 'nonce', 'sig'}:
        raise ValueError('Unrecognized mesh handshake')
    pub = un64(obj['pub'], 32)
    eph = un64(obj['eph'], 32)
    un64(obj['nonce'], 16)
    ed25519.Ed25519PublicKey.from_public_bytes(pub).verify(
        un64(obj['sig'], 64), b'vaultforge-mesh-handshake-v1|' + canon({k: v for k, v in obj.items() if k != 'sig'}))
    return pub, eph


async def _hello_read(reader: asyncio.StreamReader) -> dict:
    data = await asyncio.wait_for(reader.readline(), 8)
    if len(data) > 2048 or not data.endswith(b'\n'):
        raise ValueError('Invalid handshake length')
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError('Bad handshake')
    return obj


async def handshake(ident: Identity, reader: asyncio.StreamReader,
                    writer: asyncio.StreamWriter, initiator: bool) -> tuple[bytes, 'Cipher']:
    eph = x25519.X25519PrivateKey.generate()
    nonce = secrets.token_bytes(16)
    mine = signed_hello(ident, raw_pub(eph.public_key()), nonce,
                        'initiator' if initiator else 'responder')
    if initiator:
        writer.write(canon(mine) + b'\n')
        await writer.drain()
        theirs = await _hello_read(reader)
        remote_pub, remote_eph = verify_hello(theirs, 'responder')
        first, second = mine, theirs
    else:
        theirs = await _hello_read(reader)
        remote_pub, remote_eph = verify_hello(theirs, 'initiator')
        writer.write(canon(mine) + b'\n')
        await writer.drain()
        first, second = theirs, mine
    if hmac.compare_digest(remote_pub, ident.pub):
        raise ValueError('Cannot connect to your own identity')
    material = HKDF(algorithm=hashes.SHA256(), length=64,
                    salt=hashlib.sha256(canon(first) + canon(second)).digest(),
                    info=b'vaultforge-mesh-transport-v1').derive(
                        eph.exchange(x25519.X25519PublicKey.from_public_bytes(remote_eph)))
    tx, rx = (material[:32], material[32:]) if initiator else (material[32:], material[:32])
    return remote_pub, Cipher(tx, rx)


class Cipher:
    def __init__(self, tx: bytes, rx: bytes):
        self.tx, self.rx = AESGCM(tx), AESGCM(rx)
        self.sent = 0
        self.received = 0

    def encrypt(self, obj: dict) -> bytes:
        raw = canon(obj)
        if len(raw) > MAX_FRAME - 64 or self.sent >= 2**64 - 1:
            raise ValueError('Frame too large or counter exhausted')
        nonce = self.sent.to_bytes(12, 'big')
        cipher = self.tx.encrypt(nonce, raw, b'VFM-v1')
        self.sent += 1
        return struct.pack('!I', len(cipher)) + cipher

    def decrypt(self, data: bytes) -> dict:
        nonce = self.received.to_bytes(12, 'big')
        raw = self.rx.decrypt(nonce, data, b'VFM-v1')
        self.received += 1
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError('Invalid frame')
        return obj


@dataclass(eq=False)
class Link:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    cipher: Cipher
    pub: bytes
    endpoint: str
    nick: str = ''
    directory_capable: bool = False
    history_capable: bool = False
    history_requests: deque = field(default_factory=deque)
    sent_window: deque = field(default_factory=deque)
    tx_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def keyid(self) -> str:
        return fingerprint(self.pub)

    async def send(self, obj: dict) -> None:
        async with self.tx_lock:
            self.writer.write(self.cipher.encrypt(obj))
            await asyncio.wait_for(self.writer.drain(), 10)

    async def receive(self) -> dict:
        length = struct.unpack('!I', await self.reader.readexactly(4))[0]
        if not 16 <= length <= MAX_FRAME:
            raise ValueError('Rejected oversized frame')
        data = await self.reader.readexactly(length)
        return self.cipher.decrypt(data)

    def close(self) -> None:
        self.writer.close()



# Relay endpoints are local preferences, NOT claims of authenticated identity.
# First contact records a TOFU pin; changes to an existing pin fail closed.
PRIMARY_RELAY = '18.227.91.173:6667'
LEGACY_RELAY = '18.188.145.207:6667'


def load_relay_hosts(root: Path) -> dict:
    """Persistent relay list with one-time migration of saved TOFU identities."""
    root = Path(root)
    saved = secure_load(root / 'relay_hosts.json')
    if isinstance(saved.get('hosts'), list):
        entries = saved['hosts']
    else:
        entries = [
            {'endpoint': PRIMARY_RELAY, 'label': 'Primary AWS 2 TB'},
            {'endpoint': LEGACY_RELAY, 'label': 'Previous AWS'},
        ]
        # Only import legacy fingerprints during first migration. Removing a
        # host from the directory must never delete its separately stored pin.
        entries += [{'endpoint': addr, 'label': 'Previously trusted host'}
                    for addr in secure_load(root / 'known_peers.json')]
    rows, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        addr = entry.get('endpoint', '')
        try:
            parse_endpoint(addr)
        except (ValueError, TypeError):
            continue
        if addr not in seen and len(rows) < 64:
            rows.append({'endpoint': addr, 'label': str(entry.get('label') or addr)[:64]})
            seen.add(addr)
    if not rows:
        rows = [{'endpoint': PRIMARY_RELAY, 'label': 'Primary AWS 2 TB'}]
    active = saved.get('active', PRIMARY_RELAY)
    if active not in {x['endpoint'] for x in rows}:
        active = rows[0]['endpoint']
    return {'active': active, 'hosts': rows}


def save_relay_hosts(root: Path, catalog: dict) -> None:
    hosts = catalog.get('hosts', [])
    if not isinstance(hosts, list) or not 1 <= len(hosts) <= 64:
        raise ValueError('Relay directory must contain 1-64 hosts')
    clean, seen = [], set()
    for entry in hosts:
        if not isinstance(entry, dict):
            raise ValueError('Invalid relay entry')
        addr = entry.get('endpoint')
        parse_endpoint(addr)
        if addr in seen:
            raise ValueError('Duplicate host entry')
        label = str(entry.get('label', addr)).strip()[:64]
        clean.append({'endpoint': addr, 'label': label or addr})
        seen.add(addr)
    if catalog.get('active') not in seen:
        raise ValueError('The active relay must exist in the host directory')
    secure_save(Path(root) / 'relay_hosts.json', {'active': catalog['active'], 'hosts': clean})


class MeshNode:
    def __init__(self, ident: Identity, root: Path, notify=print, offline_only: bool = False, lan_discovery: bool = False, tor_mode: bool = False, advertise: str = '', relay_mode: bool = False):
        self.ident = ident
        self.relay_mode = relay_mode
        self.offline_only = offline_only
        self.tor_mode = tor_mode
        self.lan_discovery = lan_discovery
        self.advertise = public_endpoint(advertise) if advertise else ''
        if self.advertise and (offline_only or tor_mode):
            raise ValueError('Public node directory publishing requires WAN mode, not LAN-only or Tor-only mode')
        self.public_nodes: dict[str, dict] = {}
        self.discovery_transport = None
        self.scan_results = []
        self.retry_targets: list[str] = []
        self.auto_reconnect = False
        # Explicit opt-out prevents unexpected WAN calls in offline/privacy modes.
        self.allow_auto_reconnect = not offline_only
        self.retry_after: dict[str, float] = {}
        self.retry_delay: dict[str, float] = {}
        self.last_roster_refresh = 0.0
        self.root = secure_root(root)
        from chat_history import ChannelHistory
        self.history = ChannelHistory(self.root, validate_message, secure_load, secure_save, all_rooms=relay_mode)
        self.history_seen = set()
        self.file_tasks = set()
        self.notify = notify
        self.rooms: set[str] = {DEFAULT_ROOM}
        self.active_room = DEFAULT_ROOM
        self.links: set[Link] = set()
        self.presence: dict[str, dict] = {}
        # Retain only recently signed presence for new authenticated peers.
        # Never synthesize another user's online state from unverified metadata.
        self.signed_presence: dict[str, dict] = {}
        self.seen: dict[str, float] = {}
        self.known_keys: dict[str, bytes] = {ident.keyid: ident.pub}
        self.boxkeys: dict[str, bytes] = {ident.keyid: ident.boxpub}
        self.names: dict[str, str] = {ident.keyid: ident.nick}
        self.inbox: list[tuple[str, str, str]] = []
        from file_transfer import FileTransfers
        self.files = FileTransfers(self)
        self.server = None
        self.tick_task = None
        self.pending_handshakes = asyncio.Semaphore(8)
        self.current_port = 0
        self.pins_path = self.root / 'known_peers.json'
        self.pins = secure_load(self.pins_path)
        self.relay_hosts = load_relay_hosts(self.root)
        self.block_path = self.root / 'blocked.json'
        self.blocked = set(secure_load(self.block_path).get('ids', []))

    def audit_activity(self, event: str, **fields) -> None:
        """Relay-only, validated event metadata for journald; never decrypt/log DMs.

        Channel bodies are included ONLY if the operator enabled the local
        owner-only log_room_text.enabled flag. No wallet keys or passwords.
        """
        if not self.relay_mode:
            return
        record = {'event': event, **fields}
        self.notify('[MESH EVENT] ' + json.dumps(record, ensure_ascii=True, separators=(',', ':')))

    def _room_text_logging(self) -> bool:
        flag = self.root / 'log_room_text.enabled'
        try:
            st = flag.lstat()
            return (stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and
                    (st.st_mode & 0o077) == 0)
        except (OSError, AttributeError):
            return False


    def relay_rows(self) -> list[dict]:
        """Current authenticated link status, never guessed from a saved entry."""
        return [dict(row, state=('CONNECTED' if any(
            link.endpoint == row['endpoint'] for link in self.links) else 'DISCONNECTED'),
            active=row['endpoint'] == self.relay_hosts['active'],
            trusted=self.pins.get(row['endpoint'], '')) for row in self.relay_hosts['hosts']]

    def relay_add(self, endpoint: str, label: str = '') -> None:
        parse_endpoint(endpoint)
        catalog = {'active': self.relay_hosts['active'],
                   'hosts': [dict(x) for x in self.relay_hosts['hosts']]}
        if not any(x['endpoint'] == endpoint for x in catalog['hosts']):
            catalog['hosts'].append({'endpoint': endpoint, 'label': (label or endpoint)[:64]})
        elif label:
            for row in catalog['hosts']:
                if row['endpoint'] == endpoint:
                    row['label'] = label[:64]
        save_relay_hosts(self.root, catalog)
        self.relay_hosts = catalog

    def relay_select(self, endpoint: str) -> None:
        parse_endpoint(endpoint)
        if not any(x['endpoint'] == endpoint for x in self.relay_hosts['hosts']):
            raise ValueError('Add the host to your directory first')
        catalog = {'active': endpoint, 'hosts': [dict(x) for x in self.relay_hosts['hosts']]}
        save_relay_hosts(self.root, catalog)
        self.relay_hosts = catalog

    def relay_remove(self, endpoint: str) -> None:
        if endpoint == self.relay_hosts['active']:
            raise ValueError('Select a different active host before removal')
        catalog = {'active': self.relay_hosts['active'],
                   'hosts': [dict(x) for x in self.relay_hosts['hosts'] if x['endpoint'] != endpoint]}
        save_relay_hosts(self.root, catalog)
        self.relay_hosts = catalog
        # Do not delete known_peers pins, keys, accounts, histories or downloads.
        # Disconnection is explicit and host removal only removes a menu entry.

    def show_relays(self) -> None:
        print('\nSAVED MESH RELAYS / HOSTS — LIVE AUTHENTICATED STATUS')
        for i, row in enumerate(self.relay_rows(), 1):
            mark = 'ACTIVE' if row['active'] else 'saved'
            trust = 'pinned' if row['trusted'] else 'first-contact TOFU'
            print(f" {i:>2}. [{mark}] [{row['state']}] {row['label']}  {row['endpoint']} ({trust})")
        print('Saved hosts are not assumed reachable. /servers connect N connects to one; /servers select N sets default.\n')

    def online(self) -> list[tuple[str, str, str]]:
        now = time.monotonic()
        users = [(self.ident.nick, self.ident.keyid, 'you')]
        for key, value in self.presence.items():
            if value['online'] and now - value['last_seen'] < PRESENCE_EXPIRE and key not in self.blocked:
                users.append((value['nick'], key, ','.join(value['rooms'])))
        return sorted(users, key=lambda entry: (entry[0].lower(), entry[1]))

    def visible_rooms(self) -> dict[str, int]:
        """Only channels advertised by reachable, fresh and authenticated users."""
        counts: dict[str, int] = {room: 0 for room in self.rooms}
        for room in self.rooms:
            counts[room] += 1
        now = time.monotonic()
        for key, presence in self.presence.items():
            if key in self.blocked or not presence['online'] or now - presence['last_seen'] >= PRESENCE_EXPIRE:
                continue
            for room in presence['rooms']:
                counts[room] = counts.get(room, 0) + 1
        return counts

    def online_room_recipients(self, room: str) -> list[str]:
        """Signed presence is necessary; room membership is an opt-in announcement."""
        if room not in self.rooms or not ROOM.fullmatch(room):
            raise ValueError('Join the channel before sending a room attachment')
        now = time.monotonic()
        return sorted(key for key, item in self.presence.items()
                      if key != self.ident.keyid and key not in self.blocked
                      and item['online'] and room in item['rooms']
                      and key in self.boxkeys and now - item['last_seen'] < PRESENCE_EXPIRE)

    def _register_public(self, item: dict) -> bool:
        keyid, kind = validate_message(item)
        if kind != 'node_advert' or keyid in self.blocked:
            return False
        endpoint = item['data'].get('endpoint')
        if not isinstance(endpoint, str) or len(endpoint) > 100:
            raise ValueError('Invalid public node endpoint')
        endpoint = public_endpoint(endpoint)
        # A signed advertisement authenticates the *publisher*, not ownership of an IP.
        if keyid not in self.public_nodes and len(self.public_nodes) >= MAX_PUBLIC_NODES:
            self.prune_public()
            if len(self.public_nodes) >= MAX_PUBLIC_NODES:
                return False
        self.public_nodes[keyid] = {'nick': item['nick'], 'endpoint': endpoint,
                                    'seen': time.monotonic(), 'signed': item}
        return True

    def prune_public(self) -> None:
        now = time.monotonic()
        for key, row in list(self.public_nodes.items()):
            if now - row['seen'] > PUBLIC_NODE_TTL or key in self.blocked:
                del self.public_nodes[key]

    def listed_public(self) -> list[tuple[str, str, str]]:
        self.prune_public()
        return sorted([(row['nick'], key, row['endpoint']) for key, row in self.public_nodes.items()],
                      key=lambda r: (r[0].lower(), r[1]))

    async def announce_public(self) -> None:
        if not self.advertise:
            return
        item = sign_message(self.ident, 'node_advert', {'endpoint': self.advertise})
        self._register_public(item)
        await self._gossip(item)

    def remote_users(self) -> list[tuple[str, str, str]]:
        """Other *authenticated*, recently announced identities, never local accounts."""
        return [entry for entry in self.online() if entry[1] != self.ident.keyid]

    def show_users(self) -> None:
        print('\nONLINE USERS (authenticated presence; reachable mesh only)')
        print(f'  LOCAL ACCOUNT: {self.ident.nick}@{self.ident.keyid} (you)')
        remotes = self.remote_users()
        print(f'  REMOTE USERS: {len(remotes)}')
        for nick, key, rooms in remotes:
            print(f'    {nick}@{key}  rooms: {rooms or "none"}')
        if not self.links:
            print('  [LOCAL ONLY] Not connected to any relay/peer. Run /connect HOST:PORT.')
        elif not remotes:
            print('  [WAITING] Encrypted links exist, but no other fresh signed user presence yet.')
        print(f'  Authenticated direct connections: {len(self.links)}')
        print('  Note: this is NOT a global user directory or a list of offline accounts.\n')

    def show_connection_status(self) -> None:
        print('\nMESH CONNECTION STATUS')
        print(f'  Identity: {self.ident.nick}@{self.ident.keyid}')
        print(f'  Direct encrypted links: {len(self.links)}')
        print(f"  Active saved relay: {self.relay_hosts['active']}")
        print(f'  Remote signed online identities: {len(self.remote_users())}')
        print(f'  Auto-reconnect: {"enabled" if self.auto_reconnect and self.allow_auto_reconnect else "disabled"}')
        if self.retry_targets:
            print('  Saved session retry endpoints: ' + ', '.join(self.retry_targets))
        if not self.links:
            print('  [DISCONNECTED] This session has no remote peers. Local login is not an AWS login.')
        else:
            for link in sorted(self.links, key=lambda p: p.keyid):
                print(f'  [CONNECTED] {link.nick or "peer"}@{link.keyid} via {link.endpoint}')
        print()

    async def refresh_online(self, *, force: bool = False) -> None:
        """Request fresh roster via the existing authenticated intro/gossip frames.

        Compatible with 2.7.1 relays. No new wire frame type, no replay bypass,
        and no unauthenticated directory. A peer only replays fresh signed presence.
        """
        now = time.monotonic()
        if not force and now - self.last_roster_refresh < 5:
            print('[REFRESH] Please allow 5 seconds between roster requests.')
            return
        self.last_roster_refresh = now
        self._expire()
        if not self.links:
            print('[REFRESH] No authenticated remote peer. Use /connect HOST:PORT or /reconnect.')
            self.show_users()
            return
        await self.announce(True)
        for link in tuple(self.links):
            try:
                # Current/older relays answer their existing intro frame by
                # replaying recent signed presence. Duplicates remain rejected.
                await link.send({'type': 'intro', 'nick': self.ident.nick,
                                 'rooms': sorted(self.rooms),
                                 'features': ['public-directory-v1', 'channel-history-v1']})
            except (OSError, ConnectionError, asyncio.TimeoutError):
                link.close()
        print('[REFRESH] Requested current signed user presence from authenticated peers.')
        # UI remains usable while asynchronous responses arrive.
        self.show_users()

    def remember_retry(self, endpoint: str) -> None:
        """Only remember endpoints the user explicitly connected to."""
        parse_endpoint(endpoint)
        self.relay_add(endpoint)
        if not self.allow_auto_reconnect or self.offline_only:
            return
        if endpoint not in self.retry_targets and len(self.retry_targets) < MAX_PEERS:
            self.retry_targets.append(endpoint)
        self.auto_reconnect = bool(self.retry_targets)
        self.retry_after.pop(endpoint, None)
        self.retry_delay.pop(endpoint, None)

    async def start(self, host: str = '127.0.0.1', port: int = 0) -> None:
        if not (0 <= port <= 65535):
            raise ValueError('Port must be 0-65535')
        import security_center
        settings = security_center.load_settings()
        if (settings['mode'] == 'tor' or self.tor_mode) and not self.offline_only and host not in ('127.0.0.1', '::1', 'localhost'):
            raise ValueError('Tor-required mode allows a loopback listener only; forward a Tor hidden service to localhost')
        self.server = await asyncio.start_server(self._accept, host=host, port=port, limit=2048)
        self.current_port = self.server.sockets[0].getsockname()[1]
        if self.lan_discovery:
            if host in ('127.0.0.1', 'localhost', '::1'):
                self.notify('[LAN] Discovery replies enabled; listener is loopback-only and not available to other computers.')
            try:
                loop = asyncio.get_running_loop()
                self.discovery_transport, _ = await loop.create_datagram_endpoint(
                    lambda: LanDiscoveryResponder(self), local_addr=('0.0.0.0', DISCOVERY_PORT))
                self.notify(f'[LAN] Signed UDP discovery listening on {DISCOVERY_PORT}. Use /scan on another local peer.')
            except OSError as exc:
                self.notify(f'[LAN] Discovery unavailable: {exc}; direct /connect still works.')
        self.tick_task = asyncio.create_task(self._heartbeat())
        self.notify(f'[MESH] Listening on {host}:{self.current_port} (encrypted authenticated peer links)')
        self.show_users()
        await self.announce_public()

    async def stop(self) -> None:
        if self.links:
            await self.announce(False)
        if self.tick_task:
            self.tick_task.cancel()
            await asyncio.gather(self.tick_task, return_exceptions=True)
            self.tick_task = None
        for link in tuple(self.links):
            link.close()
        if self.discovery_transport:
            self.discovery_transport.close()
            self.discovery_transport = None
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _heartbeat(self):
        tick = 0
        while True:
            await self.announce(True)
            await self.announce_public()
            self._expire()
            self.prune_public()
            tick += 1
            if tick % 6 == 0:
                try:
                    self.history.prune()
                except OSError as exc:
                    self.notify(f'[HISTORY] Cleanup warning: {exc}')
            if tick % 3 == 0 and self.auto_reconnect and self.allow_auto_reconnect:
                for endpoint in self.retry_targets[:MAX_PEERS]:
                    if any(link.endpoint == endpoint for link in self.links):
                        self.retry_after.pop(endpoint, None)
                        self.retry_delay.pop(endpoint, None)
                        continue
                    now = time.monotonic()
                    if now < self.retry_after.get(endpoint, 0):
                        continue
                    try:
                        await self.connect(endpoint)
                        self.retry_after.pop(endpoint, None)
                        self.retry_delay.pop(endpoint, None)
                        self.notify(f'[RECONNECTED] {endpoint}; refreshing online roster')
                        await self.refresh_online(force=True)
                    except (ValueError, OSError) as exc:
                        delay = min(300.0, self.retry_delay.get(endpoint, 15.0) * 2)
                        self.retry_delay[endpoint] = delay
                        self.retry_after[endpoint] = now + delay
                        self.notify(f'[RETRY] {endpoint}: unavailable; next attempt in {int(delay)}s ({type(exc).__name__}: {str(exc).strip() or repr(exc)})')
            await asyncio.sleep(PRESENCE_INTERVAL)

    def _expire(self):
        now = time.monotonic()
        for key, item in list(self.presence.items()):
            if now - item['last_seen'] > PRESENCE_EXPIRE:
                self.presence.pop(key, None)
                self.signed_presence.pop(key, None)
                self.notify(f'[OFFLINE] {item["nick"]}@{key}')
                self.audit_activity('user_offline', nick=item['nick'], fingerprint=key, reason='presence_timeout')
        if len(self.seen) > 5000:
            self.seen = dict(sorted(((key, ts) for key, ts in self.seen.items()
                                     if now - ts < MAX_AGE), key=lambda pair: pair[1])[-5000:])

    async def announce(self, online: bool = True) -> None:
        data = {'rooms': sorted(self.rooms), 'online': online, 'boxpub': b64(self.ident.boxpub)}
        await self._gossip(sign_message(self.ident, 'presence', data))

    async def _gossip(self, item: dict, exclude: Link | None = None, ttl: int = 6) -> None:
        envelope = {'type': 'gossip', 'ttl': ttl, 'message': item}
        for link in tuple(self.links):
            if link is exclude or (item.get('kind') == 'node_advert' and not link.directory_capable):
                continue
            try:
                await link.send(envelope)
            except (ConnectionError, OSError, asyncio.TimeoutError):
                link.close()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        remote = writer.get_extra_info('peername')
        if self.offline_only and (not remote or not is_lan_host(remote[0])):
            writer.close()
            return
        if len(self.links) >= MAX_PEERS:
            writer.close()
            return
        async with self.pending_handshakes:
            await self._setup(reader, writer, False, 'incoming')

    async def connect(self, target: str) -> None:
        host, port = parse_endpoint(target)
        if self.offline_only and not is_lan_host(host):
            raise ValueError('OFFLINE mode forbids public IPs, hostnames, DNS, and Tor; use private LAN IPs only')
        import security_center
        settings = security_center.load_settings()
        if host.lower().endswith('.onion') and settings['mode'] != 'tor' and not self.tor_mode:
            raise ValueError('Onion peer addresses require Tor-required mode; refusing any direct DNS lookup')
        try:
            if (settings['mode'] == 'tor' or self.tor_mode) and not self.offline_only and host not in ('127.0.0.1', '::1', 'localhost'):
                security_center.socks5_probe(settings['port'])
                import socks
                sock = await asyncio.to_thread(socks.create_connection, (host, port), 15,
                                               proxy_type=socks.SOCKS5, proxy_addr='127.0.0.1',
                                               proxy_port=settings['port'], proxy_rdns=True)
                sock.setblocking(False)
                reader, writer = await asyncio.wait_for(asyncio.open_connection(sock=sock, limit=2048), 15)
            else:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, limit=2048), 15)
        except (OSError, asyncio.TimeoutError) as exc:
            raise ValueError(f'Cannot reach peer {target}: {str(exc).strip() or ("TCP connection timed out" if isinstance(exc, asyncio.TimeoutError) else repr(exc))}') from exc
        await self._setup(reader, writer, True, target)

    def replace_trusted_fingerprint(self, endpoint: str, previous: str, verified: str) -> None:
        """Rotate one TOFU pin only on a caller's explicit out-of-band verification.

        Saves an owner-private backup; fails closed if a pin changed in the meantime.
        """
        parse_endpoint(endpoint)
        if not re.fullmatch(r'[0-9a-f]{16}', verified):
            raise ValueError('Verified fingerprint must be exactly 16 lowercase hexadecimal characters')
        if not re.fullmatch(r'[0-9a-f]{16}', previous):
            raise ValueError('Previous fingerprint must be exactly 16 lowercase hexadecimal characters')
        current = self.pins.get(endpoint)
        if current != previous:
            raise ValueError('The saved peer fingerprint has changed; review its current value first')
        if current == verified:
            raise ValueError('The new fingerprint is identical to the existing pin')
        if any(link.endpoint == endpoint for link in self.links):
            raise ValueError('Disconnect the current peer link before updating trust')
        backup = self.root / ('known_peers.pre-rotation-' + secrets.token_hex(5) + '.json')
        secure_save(backup, dict(self.pins))
        updated = dict(self.pins)
        updated[endpoint] = verified
        secure_save(self.pins_path, updated)
        self.pins = updated
        self.retry_after.pop(endpoint, None)
        self.retry_delay.pop(endpoint, None)
        self.notify(f'[TRUST UPDATED] {endpoint}: {previous} -> {verified}; old pins backed up. Reconnect to verify handshake.')

    async def _setup(self, reader, writer, initiating: bool, endpoint: str):
        try:
            pub, cipher = await asyncio.wait_for(handshake(self.ident, reader, writer, initiating), 12)
            peer_id = fingerprint(pub)
            if peer_id in self.blocked:
                raise ValueError('Blocked peer identity')
            if initiating:
                saved = self.pins.get(endpoint)
                if saved is not None and saved != peer_id:
                    raise PeerIdentityChanged(endpoint, saved, peer_id)
                if saved is None:
                    self.pins[endpoint] = peer_id
                    secure_save(self.pins_path, self.pins)
                    self.notify(f'[FIRST CONTACT] Trust-on-first-use: pinned {endpoint} to {peer_id}. Verify fingerprint out-of-band.')
            if any(link.pub == pub for link in self.links):
                raise ValueError('Peer already connected')
            link = Link(reader, writer, cipher, pub, endpoint)
            self.links.add(link)
            self.known_keys[peer_id] = pub
            self.notify(f'[CONNECTED] peer @{peer_id}, encrypted; {len(self.links)} direct link(s)')
            self.audit_activity('peer_connected', peer=peer_id, direction='outgoing' if initiating else 'incoming', links=len(self.links))
            await link.send({'type': 'intro', 'nick': self.ident.nick, 'rooms': sorted(self.rooms),
                             'features': ['public-directory-v1', 'channel-history-v1']})
            # Sync current *signed* presence: no user registry or passwords are sent.
            await link.send({'type': 'gossip', 'ttl': 1,
                             'message': sign_message(self.ident, 'presence',
                                                     {'rooms': sorted(self.rooms), 'online': True,
                                                      'boxpub': b64(self.ident.boxpub)})})
            asyncio.create_task(self._receive_loop(link))
        except Exception as exc:
            self.notify(f'[PEER REJECTED] {endpoint}: {type(exc).__name__}: {exc}')
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            if initiating:
                if isinstance(exc, PeerIdentityChanged):
                    raise
                raise ValueError(f'Peer connection failed: {exc}') from exc

    async def _receive_loop(self, link: Link) -> None:
        try:
            while True:
                frame = await link.receive()
                now = time.monotonic()
                link.sent_window.append(now)
                while link.sent_window and now - link.sent_window[0] > 10:
                    link.sent_window.popleft()
                if len(link.sent_window) > 80:
                    raise ValueError('Peer exceeded rate limit')
                if frame.get('type') == 'intro':
                    nick = frame.get('nick')
                    if not isinstance(nick, str) or not NAME.fullmatch(nick):
                        raise ValueError('Invalid peer name')
                    link.nick = nick
                    self.names[link.keyid] = nick
                    features = frame.get('features', [])
                    link.directory_capable = isinstance(features, list) and 'public-directory-v1' in features
                    link.history_capable = isinstance(features, list) and 'channel-history-v1' in features
                    # Existing clients already understand signed gossip frames.
                    # Replay only fresh signed presence, bounded to prevent a flood.
                    # This makes a just-connected client see users already at the relay
                    # without waiting for all those users' next heartbeat.
                    now_epoch = int(time.time())
                    now_mono = time.monotonic()
                    sent = 0
                    for uid, signed in list(self.signed_presence.items()):
                        if sent >= 32:
                            break
                        known = self.presence.get(uid)
                        if (uid == link.keyid or uid in self.blocked or not known or
                                not known['online'] or now_mono - known['last_seen'] >= PRESENCE_EXPIRE or
                                abs(now_epoch - signed['time']) > MAX_AGE):
                            continue
                        await link.send({'type':'gossip','ttl':1,'message':signed})
                        sent += 1
                    if link.history_capable and not self.relay_mode:
                        await self.request_history(self.active_room, only=link)
                    if link.directory_capable:
                        # Do not send new wire frames to older 2.5 nodes: they would disconnect.
                        self.prune_public()
                        records = [row['signed'] for row in list(self.public_nodes.values())[:20]]
                        if records:
                            await link.send({'type': 'node_records', 'records': records})
                elif frame.get('type') == 'node_records' and link.directory_capable:
                    records = frame.get('records')
                    if not isinstance(records, list) or len(records) > 20:
                        raise ValueError('Invalid node directory response')
                    for record in records:
                        try:
                            self._register_public(record)
                        except (ValueError, TypeError, KeyError, AttributeError):
                            continue
                elif frame.get('type') == 'history_request' and link.history_capable:
                    await self._history_request(frame, link)
                elif frame.get('type') == 'history_batch' and link.history_capable:
                    self._history_batch(frame, link)
                elif frame.get('type') == 'gossip':
                    await self._incoming(frame, link)
                else:
                    raise ValueError('Unknown network frame')
        except (asyncio.IncompleteReadError, ConnectionError, OSError, asyncio.CancelledError):
            pass
        except Exception as exc:
            self.notify(f'[PEER ERROR] @{link.keyid}: {type(exc).__name__}')
        finally:
            self.links.discard(link)
            link.close()
            self.notify(f'[DISCONNECTED] @{link.keyid}')
            self.audit_activity('peer_disconnected', peer=link.keyid, links=len(self.links))

    async def _incoming(self, frame: dict, link: Link) -> None:
        item = frame.get('message')
        ttl = frame.get('ttl')
        if type(ttl) is not int or not 0 <= ttl <= 6:
            raise ValueError('Invalid relay TTL')
        user_id, kind = validate_message(item)
        if user_id in self.blocked or user_id == self.ident.keyid:
            return
        key = user_id + ':' + item['id']
        if key in self.seen:
            return
        self.seen[key] = time.monotonic()
        self.known_keys[user_id] = un64(item['origin'], 32)
        self.names[user_id] = item['nick']
        data = item['data']
        if kind == 'presence':
            rooms = data.get('rooms')
            online = data.get('online')
            if not isinstance(rooms, list) or len(rooms) > 12 or \
               any(not isinstance(r, str) or not ROOM.fullmatch(r) for r in rooms) or type(online) is not bool:
                raise ValueError('Invalid peer presence')
            boxpub = un64(data.get('boxpub'), 32)
            self.boxkeys[user_id] = boxpub
            prev = self.presence.get(user_id)
            if prev is None and online:
                self.notify(f'[ONLINE] {item["nick"]}@{user_id} joined the mesh')
                self.audit_activity('user_online', nick=item['nick'], fingerprint=user_id, rooms=rooms)
            if prev is not None and not online:
                self.notify(f'[OFFLINE] {item["nick"]}@{user_id}')
                self.audit_activity('user_offline', nick=item['nick'], fingerprint=user_id, reason='signed_offline')
            self.presence[user_id] = {'nick': item['nick'], 'rooms': rooms, 'online': online,
                                      'last_seen': time.monotonic()}
            if online:
                self.signed_presence[user_id] = item
            else:
                self.signed_presence.pop(user_id, None)
        elif kind == 'node_advert':
            self._register_public(item)
        elif kind == 'chat':
            room, msg = data.get('room'), data.get('text')
            if not isinstance(room, str) or not ROOM.fullmatch(room) or \
               not isinstance(msg, str) or not 1 <= len(msg) <= MAX_MESSAGE:
                raise ValueError('Invalid chat message')
            if self.relay_mode:
                fields = {'nick': item['nick'], 'fingerprint': user_id, 'room': room, 'characters': len(msg)}
                if self._room_text_logging():
                    fields['text'] = msg
                self.audit_activity('room_message', **fields)
            if room in self.rooms or self.relay_mode:
                try:
                    self.history.append(item)
                except (ValueError, OSError) as exc:
                    self.notify(f'[HISTORY] Unable to save public-room history: {exc}')
            if room in self.rooms and not self.relay_mode:
                self.inbox.append((room, item['nick'], msg))
                self.notify(f'[{room}] {item["nick"]}@{user_id}: {msg}')
        elif kind in ('file_start', 'file_chunk'):
            if kind == 'file_start':
                self.audit_activity('encrypted_file_offer', nick=item['nick'], fingerprint=user_id, recipient=data.get('to', 'unknown'))
            try:
                self.files.receive(item, kind, user_id)
            except (ValueError, KeyError, TypeError) as exc:
                self.notify(f'[FILE REJECTED] {type(exc).__name__}: {exc}')
        elif kind == 'dm':
            self.audit_activity('encrypted_dm', nick=item['nick'], fingerprint=user_id, recipient=data.get('to', 'unknown'))
            if data.get('to') == self.ident.keyid:
                try:
                    message = open_dm(self.ident, un64(item['origin'], 32), data)
                    if not 1 <= len(message) <= MAX_MESSAGE:
                        raise ValueError('Invalid DM size')
                    self.inbox.append(('DM', item['nick'], message))
                    if not self.relay_mode:
                        self.notify(f'[PRIVATE DM] {item["nick"]}@{user_id}: {message}')
                except Exception:
                    self.notify('[SECURITY] Rejected unreadable private message')
        if ttl > 0:
            await self._gossip(item, exclude=link, ttl=ttl - 1)

    def background_file_send(self, awaitable):
        async def worker():
            try:
                await awaitable
            except (OSError, ValueError, RuntimeError) as exc:
                self.notify(f'[FILE ERROR] {exc}')
        task = asyncio.create_task(worker())
        self.file_tasks.add(task)
        task.add_done_callback(self.file_tasks.discard)
        self.notify('[FILE] Preparing encrypted transfer in background; you can continue chatting.')

    async def request_history(self, room: str, only=None):
        if room not in self.rooms or not ROOM.fullmatch(room):
            return
        for peer in list(self.links):
            if only is not None and peer is not only:
                continue
            if peer.history_capable:
                try:
                    await peer.send({'type': 'history_request', 'room': room, 'limit': 25})
                except (ConnectionError, OSError, asyncio.TimeoutError):
                    peer.close()

    async def _history_request(self, frame: dict, link: Link):
        room, limit = frame.get('room'), frame.get('limit')
        if not isinstance(room, str) or not ROOM.fullmatch(room) or type(limit) is not int or not 1 <= limit <= 25:
            raise ValueError('Invalid channel history request')
        now = time.monotonic()
        while link.history_requests and now - link.history_requests[0] > 30:
            link.history_requests.popleft()
        if len(link.history_requests) >= 6:
            raise ValueError('History request rate exceeded')
        link.history_requests.append(now)
        records = self.history.entries(room, limit)
        # Four signed messages per frame keep responses within the 16-KiB frame cap.
        for n in range(0, len(records), 4):
            await link.send({'type': 'history_batch', 'room': room, 'records': records[n:n+4]})

    def _history_batch(self, frame: dict, link: Link):
        room, records = frame.get('room'), frame.get('records')
        if not isinstance(room, str) or room not in self.rooms or not ROOM.fullmatch(room) or not isinstance(records, list) or len(records) > 4:
            raise ValueError('Invalid history response')
        for item in records:
            if not isinstance(item, dict) or item.get('kind') != 'chat':
                continue
            try:
                user, kind = validate_message(item, allow_expired=True)
                if kind != 'chat' or user in self.blocked or item['data'].get('room') != room:
                    continue
                if not self.history.append(item):
                    continue
                self.notify('[HISTORY] ' + self.history.format(item))
            except (ValueError, TypeError, KeyError, OSError):
                continue

    async def send_chat(self, text: str) -> None:
        if not 1 <= len(text) <= MAX_MESSAGE:
            raise ValueError(f'Chat message must be 1-{MAX_MESSAGE} characters')
        item = sign_message(self.ident, 'chat', {'room': self.active_room, 'text': text})
        if len(canon({'type':'gossip', 'ttl':6, 'message':item})) > MAX_FRAME - 64:
            raise ValueError('Message too large when encoded for transport')
        self.history.append(item)
        self.inbox.append((self.active_room, self.ident.nick, text))
        self.notify(f'[{self.active_room}] {self.ident.nick}@{self.ident.keyid} (you): {text}')
        await self._gossip(item)

    async def send_dm(self, target: str, text: str) -> None:
        if not 1 <= len(text) <= MAX_MESSAGE:
            raise ValueError('DM exceeds message limit')
        if target == self.ident.keyid or target == f'{self.ident.nick}@{self.ident.keyid}':
            raise ValueError('Cannot direct-message yourself; clear recipient to send to a room')
        matches = [key for key, nick in self.names.items()
                   if key == target or f'{nick}@{key}' == target or (nick.lower() == target.lower() and key != self.ident.keyid)]
        matches = [key for key in matches if key in self.boxkeys and key not in self.blocked
                   and key != self.ident.keyid and key in self.presence
                   and self.presence[key]['online']
                   and time.monotonic() - self.presence[key]['last_seen'] < PRESENCE_EXPIRE]
        if len(matches) != 1:
            raise ValueError('Recipient not found or nickname ambiguous. Use the ID from /users')
        keyid = matches[0]
        data = seal_dm(self.ident, self.boxkeys[keyid], keyid, text)
        item = sign_message(self.ident, 'dm', data)
        if len(canon({'type':'gossip', 'ttl':6, 'message':item})) > MAX_FRAME - 64:
            raise ValueError('Private message too large when encoded for transport')
        self.notify(f'[PRIVATE DM] to {self.names.get(keyid, "peer")}@{keyid}: {text}')
        await self._gossip(item)

    def block(self, user_id: str) -> None:
        if not re.fullmatch(r'[0-9a-f]{16}', user_id) or user_id == self.ident.keyid:
            raise ValueError('Use a valid peer ID from /users')
        self.blocked.add(user_id)
        secure_save(self.block_path, {'ids': sorted(self.blocked)})
        for link in tuple(self.links):
            if link.keyid == user_id:
                link.close()
        self.notify(f'[BLOCKED] @{user_id}')

    async def offer_trust_rotation(self, changed: PeerIdentityChanged) -> bool:
        """Interactive-only: show automatic detection, require independent verification."""
        print(f'\n[RELAY IDENTITY CHANGE DETECTED] {changed.endpoint}')
        print(f'  Previously pinned: {changed.pinned}')
        print(f'  Server now presents: {changed.presented} (NOT YET TRUSTED)')
        print('[SECURITY] A changed fingerprint could be an impersonation.')
        print('[SECURITY] Verify the NEW value on the server console or with its operator,')
        print('           through an independent trusted channel BEFORE accepting.')
        if not sys.stdin.isatty():
            print(f'[ACTION] Once verified, use /rotate {changed.endpoint} {changed.presented}')
            return False
        try:
            reply = await asyncio.to_thread(input, 'After verifying the new identity on the ACTUAL server console, type YES (Enter cancels): ')
        except (EOFError, KeyboardInterrupt):
            return False
        if reply.strip().upper() != 'YES':
            print('[UNCHANGED] Original trust pin remains intact; connection blocked.')
            return False
        self.replace_trusted_fingerprint(changed.endpoint, changed.pinned, changed.presented)
        print('[VERIFIED] Replaced the pin for that endpoint only; reconnecting ...')
        return True

    async def command(self, line: str) -> bool:
        if not line.startswith('/'):
            await self.send_chat(line)
            return True
        parts = line.strip().split(maxsplit=2)
        cmd = parts[0].lower()
        if cmd in ('/servers', '/hosts', '/relays'):
            if len(parts) == 1 or parts[1] in ('list', 'ls', 'status'):
                self.show_relays()
            elif parts[1] == 'add' and len(parts) >= 3:
                bits = parts[2].split(maxsplit=1)
                self.relay_add(bits[0], bits[1] if len(bits) > 1 else '')
                self.show_relays()
            elif parts[1] in ('select', 'remove', 'connect') and len(parts) >= 3:
                dest = parts[2].strip()
                rows = self.relay_rows()
                if dest.isdecimal():
                    i = int(dest)
                    if not 1 <= i <= len(rows):
                        raise ValueError('No host with that number')
                    dest = rows[i-1]['endpoint']
                if parts[1] == 'select':
                    self.relay_select(dest)
                elif parts[1] == 'remove':
                    self.relay_remove(dest)
                else:
                    try:
                        await self.connect(dest)
                    except PeerIdentityChanged as changed:
                        if not await self.offer_trust_rotation(changed):
                            return True
                        await self.connect(dest)
                    self.remember_retry(dest)
                    await self.refresh_online(force=True)
                self.show_relays()
            else:
                print('Usage: /servers [list | add HOST:PORT [LABEL] | select N | connect N | remove N]')
            return True
        if cmd in ('/quit', '/exit'):
            return False
        if cmd in ('/help', '/?'):
            print('''\n/help                    Show commands
/users                   Local identity + authenticated REMOTE online users
/online                  Show remote online users (not stored accounts)
/refresh                 Request updated remote roster from connected peers
/status                  Show AWS/peer link and reconnection status
/servers                 Persistent host directory with LIVE link status
/servers add HOST:PORT NAME   Remember any self-hosted or community relay
/servers select N        Make numbered saved server the login default
/servers connect N       Connect to an additional saved relay (no reset)
/servers remove N        Remove menu entry; keep fingerprints and files
/reconnect               Retry previously manually connected peers now
/peers                   Show connected direct peers
/trust                   List saved endpoint identity pins
/unpin HOST:PORT         Remove saved identity pin (requires confirmation)
/rotate HOST:PORT ID     Replace pin after INDEPENDENTLY verifying new ID
/history [#ROOM]         Show saved public-channel history and request peer sync
/connect HOST:PORT       Join a peer mesh via an authenticated encrypted link
/scan                   Find discoverable peers on your LAN (no internet required)
/public                 List nodes advertised by the connected public mesh
/connectpublic N        Connect to advertised public node N after explicit review
/connect N              Connect to result N from the last LAN scan
/join #CHANNEL           Create/join a room visible to connected peers
/create #CHANNEL         Alias to create/join a room
/leave #CHANNEL          Leave a room (cannot leave your only room)
/rooms                   List your joined rooms
/msg USER@ID MESSAGE     End-to-end encrypted direct message
/sendfile USER@ID PATH   Encrypted file/image offer to an online peer (max 4 MiB)
/upload USER@ID PATH     Upload a file OR folder via encrypted P2P transfer
/uploadroom #ROOM PATH   Encrypt and offer file/folder to each online room member
/share USER@ID PATH      Alias for /upload (spaces in PATH are supported)
/sendfolder USER@ID DIR  Compress folder into ZIP and offer encrypted transfer
/downloads               Show your local folder for accepted attachments
/files or /inbox         List incoming offers numbered (READY/RECEIVING)
/download NUMBER         Accept and save a ready file by displayed number or full ID
/accept ID              Existing exact-ID save command (still supported)
/downloads or /saved     List files already saved in your private downloads folder
/reject NUMBER           Discard incoming offer by number or exact ID
/whoami                  Your login identity and fingerprint
/block ID                Block a user identity locally
/quit                    Disconnect and log out\nPlain text sends to your active channel. Room chat is encrypted per hop, not end-to-end.\n''')
        elif cmd in ('/users', '/who'):
            self.show_users()
        elif cmd in ('/online', '/remote'):
            print('\nREMOTE ONLINE USERS (signed; recently reachable):')
            for nick, key, rooms in self.remote_users():
                print(f'  {nick}@{key}  rooms: {rooms or "none"}')
            print(f'  {len(self.remote_users())} remote online; {len(self.links)} encrypted link(s)\n')
        elif cmd in ('/refresh', '/refreshonline', '/refreshusers'):
            await self.refresh_online()
        elif cmd == '/status':
            self.show_connection_status()
        elif cmd == '/reconnect':
            if not self.allow_auto_reconnect or self.offline_only:
                print('[RECONNECT] Automatic WAN connection disabled in this mode.')
            elif not self.retry_targets:
                print('[RECONNECT] No prior manually approved peer. Use /connect HOST:PORT.')
            else:
                for endpoint in self.retry_targets[:MAX_PEERS]:
                    if any(link.endpoint == endpoint for link in self.links):
                        continue
                    try:
                        await self.connect(endpoint)
                        self.retry_after.pop(endpoint, None)
                        self.retry_delay.pop(endpoint, None)
                        print(f'[RECONNECTED] {endpoint}')
                    except (ValueError, OSError) as exc:
                        print(f'[RECONNECT] {endpoint}: {exc}')
                if self.links:
                    await self.refresh_online(force=True)
            self.show_connection_status()
        elif cmd == '/peers':
            for lnk in sorted(self.links, key=lambda p: p.keyid):
                print(f'  {lnk.nick or "peer"}@{lnk.keyid}  {lnk.endpoint}')
            print(f'  {len(self.links)} direct peer(s)')
        elif cmd == '/trust':
            print('Known peers (TOFU pins; verify fingerprints independently):')
            for addr, key in sorted(self.pins.items()):
                print(f'  {addr} => {key}')
        elif cmd == '/rotate' and len(parts) >= 3:
            endpoint, verified = parts[1], parts[2].strip().lower()
            previous = self.pins.get(endpoint)
            if not previous:
                raise ValueError('No saved pin for endpoint; use /trust to inspect it')
            if not re.fullmatch(r'[0-9a-f]{16}', verified):
                raise ValueError('New fingerprint must be exactly 16 hexadecimal characters')
            print(f'[TRUST REVIEW] {endpoint}  old={previous}  proposed={verified}')
            print('Verify the proposed fingerprint on the server console BEFORE continuing.')
            confirmation = await asyncio.to_thread(input, f'Type TRUST {verified} if independently verified: ')
            if confirmation.strip() == f'TRUST {verified}':
                self.replace_trusted_fingerprint(endpoint, previous, verified)
                print('[TRUST] Updated. Use /connect ' + endpoint)
            else:
                print('[UNCHANGED] Pin remains as it was.')
        elif cmd == '/unpin' and len(parts) >= 2:
            endpoint = parts[1]
            if endpoint not in self.pins:
                raise ValueError('Endpoint has no saved identity pin')
            if input(f'Type UNPIN {endpoint} to forget its identity: ').strip() == f'UNPIN {endpoint}':
                del self.pins[endpoint]
                secure_save(self.pins_path, self.pins)
                print('[UNPINNED] Only reconnect after independently verifying peer fingerprint.')
        elif cmd == '/history':
            room = parts[1].lower() if len(parts) >= 2 else self.active_room
            if not ROOM.fullmatch(room) or room not in self.rooms:
                raise ValueError('Join the public channel first: /join #room')
            rows = self.history.entries(room)
            for row in rows:
                print('  ' + self.history.format(row))
            print(f'[HISTORY] {len(rows)} saved messages from {room}; requesting recent messages from connected peers...')
            await self.request_history(room)
        elif cmd in ('/public', '/scanpublic'):
            show_public_nodes(self.listed_public())
        elif cmd == '/connectpublic' and len(parts) >= 2:
            rows = self.listed_public()
            if not parts[1].isdecimal() or not 1 <= int(parts[1]) <= len(rows):
                raise ValueError('Choose a numbered result from /public')
            nick, keyid, endpoint = rows[int(parts[1]) - 1]
            print(f'[UNVERIFIED NODE] {nick}@{keyid}  {endpoint}')
            print('Advertising does not prove this is the claimed operator or a reachable server.')
            if input('Type CONNECT to try this node: ').strip() == 'CONNECT':
                await self.connect(endpoint)
                self.remember_retry(endpoint)
                await self.refresh_online(force=True)
        elif cmd == '/scan':
            self.scan_results = await scan_lan()
            show_discovered(self.scan_results)
        elif cmd == '/connect' and len(parts) >= 2:
            peer = parts[1]
            if peer.isdecimal():
                index = int(peer)
                if not 1 <= index <= len(self.scan_results):
                    raise ValueError('No matching scan result. Run /scan first.')
                peer = self.scan_results[index - 1][2]
            try:
                await self.connect(peer)
            except PeerIdentityChanged as changed:
                if not await self.offer_trust_rotation(changed):
                    return True
                await self.connect(peer)
            self.remember_retry(peer)
            await self.refresh_online(force=True)
        elif cmd in ('/join', '/create', '/createroom') and len(parts) >= 2:
            room = parts[1].lower()
            if not ROOM.fullmatch(room) or (len(self.rooms) >= 12 and room not in self.rooms):
                raise ValueError('Invalid channel or too many joined channels')
            self.rooms.add(room)
            self.active_room = room
            await self.announce()
            self.notify(f'[JOINED] {room}; loading saved history...')
            for row in self.history.entries(room):
                self.notify('[HISTORY] ' + self.history.format(row))
            await self.request_history(room)
        elif cmd == '/leave' and len(parts) >= 2:
            room = parts[1].lower()
            if room not in self.rooms or len(self.rooms) == 1:
                raise ValueError('Cannot leave that room (keep at least one joined)')
            self.rooms.remove(room)
            if self.active_room == room:
                self.active_room = sorted(self.rooms)[0]
            await self.announce()
        elif cmd == '/rooms':
            print('Rooms in reachable mesh (not a worldwide directory):')
            for room, count in sorted(self.visible_rooms().items()):
                print(f'  {room}  {count} online  ' + ('[joined]' if room in self.rooms else '[join: /join '+room+']'))
            print('Active room: ' + self.active_room)
        elif cmd == '/msg' and len(parts) == 3:
            await self.send_dm(parts[1], parts[2])
        elif cmd in ('/sendfile', '/share', '/upload') and len(parts) == 3:
            target, source = parts[1], parts[2]
            self.background_file_send(self.files.send_folder(target, source) if Path(source).expanduser().is_dir() else self.files.send(target, source))
        elif cmd in ('/uploadroom', '/sendroom') and len(parts) == 3:
            self.background_file_send(self.files.send_room(parts[1].lower(), parts[2]))
        elif cmd == '/sendfolder' and len(parts) == 3:
            self.background_file_send(self.files.send_folder(parts[1], parts[2]))
        elif cmd in ('/files', '/inbox'):
            rows = self.files.offer_rows()
            print('\nINCOMING FILES — encrypted offers; only complete files can be saved')
            for index, tx in enumerate(rows, 1):
                state = 'READY' if tx['ready'] else 'RECEIVING'
                print(f'  {index:>2}. [{state}] {tx["name"]} ({tx["size"]} bytes) '
                      f'from {tx["sender"]} | ID {tx["id"]}')
            if not rows:
                print('  No pending file offers. The sender must be online and complete the transfer.')
            else:
                print('  Download: /download NUMBER   (or /download FULL_ID)')
                print('  Reject:   /reject NUMBER     (or /reject FULL_ID)')
            print('  File offers expire; ask the sender to resend if an offer disappears.\n')
        elif cmd in ('/download', '/accept'):
            if len(parts) < 2:
                print('[FILES] Run /files to view numbered incoming offers, then /download NUMBER')
            else:
                tid = self.files.resolve_offer(parts[1])
                print(f'[SAVED] {self.files.accept(tid)}')
                print('[SAFETY] Downloads are not opened or ZIP-extracted automatically.')
        elif cmd == '/reject' and len(parts) >= 2:
            tid = self.files.resolve_offer(parts[1])
            del self.files.pending[tid]
            print('[REJECTED] Incoming file offer discarded')
        elif cmd in ('/downloads', '/saved'):
            from file_transfer import list_saved_downloads
            folder = self.root / 'downloads'
            print('[DOWNLOADS] ' + str(folder) + ' (accepted encrypted transfers only)')
            rows = list_saved_downloads(self.root)
            for i, row in enumerate(rows, 1):
                print(f'  {i:>2}. {row["name"]} ({row["size"]} bytes)')
            if not rows:
                print('  No accepted files saved yet. Run /files then /download NUMBER.')
            print('  Archives stay ZIP files and are NEVER automatically extracted.')
        elif cmd == '/whoami':
            print(f'Chat account: {self.ident.nick}@{self.ident.keyid}\nPublic identity fingerprint: {hashlib.sha256(self.ident.pub).hexdigest()}')
        elif cmd == '/block' and len(parts) >= 2:
            self.block(parts[1])
        else:
            print('Unknown command; type /help')
        return True


def parse_endpoint(value: str, *, allow_zero: bool = False) -> tuple[str, int]:
    if not isinstance(value, str) or len(value) > 280 or '/' in value or '@' in value:
        raise ValueError('Expected HOST:PORT (no URL or credentials)')
    if value.startswith('['):
        match = re.fullmatch(r'\[([0-9a-fA-F:]+)\]:(\d{1,5})', value)
        if not match:
            raise ValueError('Invalid IPv6 endpoint')
        host, port = match.groups()
    else:
        if value.count(':') != 1:
            raise ValueError('Expected HOST:PORT')
        host, port = value.rsplit(':', 1)
        if not re.fullmatch(r'[a-zA-Z0-9.-]{1,253}', host):
            raise ValueError('Invalid hostname')
    if not port.isdecimal() or not (0 if allow_zero else 1) <= int(port) <= 65535:
        raise ValueError('Invalid port')
    if int(port) == 0 and host not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Ephemeral port 0 allowed only for localhost listeners')
    return host, int(port)


async def console_session(identity: Identity, root: Path, host: str, port: int, peer: list[str],
                          relay: bool = False, offline_only: bool = False, lan_discovery: bool = False,
                          initial_scan: bool = False, tor_mode: bool = False, advertise: str = '',
                          disable_auto_reconnect: bool = False):
    node = MeshNode(identity, root, offline_only=offline_only, lan_discovery=lan_discovery, tor_mode=tor_mode, advertise=advertise, relay_mode=relay)
    await node.start(host, port)
    node.allow_auto_reconnect = not (offline_only or disable_auto_reconnect)
    try:
        for address in peer:
            try:
                # Explicit --peer hosts remain in the persistent menu after a restart.
                if not relay:
                    node.relay_add(address)
                print(f'[CONNECTING] Remote peer {address} ...')
                await node.connect(address)
            except PeerIdentityChanged as changed:
                if not relay and await node.offer_trust_rotation(changed):
                    await node.connect(address)
                else:
                    print(f'[CONNECT ERROR] {changed}')
            except ValueError as exc:
                print(f'[CONNECT ERROR] {exc}')
        node.retry_targets = list(dict.fromkeys(peer))[:MAX_PEERS] if node.allow_auto_reconnect else []
        node.auto_reconnect = node.allow_auto_reconnect and bool(node.retry_targets)
        if node.links:
            await node.refresh_online(force=True)
        if initial_scan:
            node.scan_results = await scan_lan()
            show_discovered(node.scan_results)
            if node.scan_results:
                print('[TIP] Run /connect 1 to connect to the first discovered peer.')
        if peer and not node.links:
            print('[NOT CONNECTED] No remote peer is reachable. Only your own account is online locally.')
            print('[HELP] Check the AWS EC2 public IP, inbound TCP firewall PORT, and relay listener.')
            print('[RETRY] Inside chat use /connect YOUR_AWS_PUBLIC_IP:6667 (or the server actual port).')
        elif node.links:
            print(f'[CONNECTED] {len(node.links)} remote peer link(s). Use /users or /peers.')
        else:
            print('[LOCAL ONLY] No remote endpoint selected; /connect HOST:PORT joins a server.')
        print('\nType /help for commands. /upload USER@ID PATH shares files or folders; /files and /accept ID receive them.')
        print('Use /refresh for fresh online users, /online for remote users, and /status for connection health.')
        print('Public-room history is saved locally; upgraded relays provide previous messages on joining.')
        for item in node.history.entries(node.active_room, 20):
            print('[HISTORY] ' + node.history.format(item))
        if relay:
            print('[RELAY] Headless mesh node active; press Ctrl+C to shut down.')
            await asyncio.Event().wait()
            return
        # prompt_toolkit redraws the input line as asynchronous peer messages arrive.
        # The built-in fallback remains available in minimal/offline environments.
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.patch_stdout import patch_stdout
            from prompt_toolkit.history import InMemoryHistory
            use_live = sys.stdin.isatty() and sys.stdout.isatty()
            session = PromptSession(history=InMemoryHistory()) if use_live else None
        except ImportError:
            session = None
        from contextlib import nullcontext
        with patch_stdout() if session is not None else nullcontext():
            while True:
                try:
                    if session is not None:
                        line = await session.prompt_async(f'{node.active_room}> ')
                    else:
                        line = await asyncio.to_thread(input, f'{node.active_room}> ')
                    if line.strip() and not await node.command(line.strip()):
                        break
                except (EOFError, KeyboardInterrupt):
                    break
                except (ValueError, OSError) as exc:
                    print(f'[CHAT ERROR] {exc}')
    finally:
        await node.stop()


def account_menu(root: Path) -> Identity | None:
    print('\nVAULTFORGE MESH — LOCAL CHAT ACCOUNT')
    print('Chat passwords and private identity keys NEVER enter wallet vaults or peer messages.')
    accounts = secure_load(secure_root(root) / 'accounts.json')
    print('Local users: ' + (', '.join(sorted(accounts)) if accounts else 'none'))
    print(' 1) Create a new user\n 2) Log in\n 3) Change chat password\n 0) Back')
    selected = input('Choice: ').strip()
    if selected == '1':
        nick = input('New username: ').strip()
        pw = getpass('New chat password (14+ chars): ')
        if pw != getpass('Repeat chat password: '):
            raise ValueError('Passwords did not match')
        ident = create_account(root, nick, pw)
        print(f'[CREATED] {nick}@{ident.keyid}. Verify this fingerprint with peers out-of-band.')
        return ident
    if selected == '2':
        nick = input('Username: ').strip()
        ident = login(root, nick, getpass('Chat password: '))
        print(f'[LOGIN] {ident.nick}@{ident.keyid}')
        return ident
    if selected == '3':
        nick = input('Username: ').strip()
        old = getpass('Current chat password: ')
        new = getpass('New chat password (14+ chars): ')
        if new != getpass('Repeat new password: '):
            raise ValueError('Passwords did not match')
        change_account_password(root, nick, old, new)
        print('[OK] Chat password changed (wallet password unchanged).')
    return None


async def scan_public(sources: list[str] | None = None, *, tor_mode: bool = False):
    """Authenticated query of opt-in public-node announcements, not a port scan.

    Temporary identity is deleted on completion; no private wallet keys are touched.
    Returns ([(name, fingerprint, endpoint), ...], connection errors).
    """
    sources = sources or [DEFAULT_BOOTSTRAP]
    with tempfile.TemporaryDirectory(prefix='vf-public-nodes-') as td:
        path = Path(td)
        guest = create_account(path, 'PublicScanner', secrets.token_urlsafe(30))
        node = MeshNode(guest, path, notify=lambda _: None, tor_mode=tor_mode)
        await node.start('127.0.0.1', 0)
        failures = []
        try:
            for source in sources[:8]:
                try:
                    await node.connect(source)
                except (OSError, ValueError) as exc:
                    failures.append(f'{source}: {exc}')
            if node.links:
                await asyncio.sleep(0.8)
            else:
                failures.append('No bootstrap accepted an authenticated encrypted connection. Check AWS and TCP 6667.')
            return node.listed_public(), failures
        finally:
            await node.stop()


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='VaultForge authenticated encrypted P2P mesh IRC-style chat')
    parser.add_argument('--listen', default='127.0.0.1:7777', help='local listen HOST:PORT; default 127.0.0.1:7777')
    parser.add_argument('--peer', action='append', default=[], help='connect to an existing peer HOST:PORT (repeatable)')
    parser.add_argument('--advertise', default='', help='opt-in public WAN node listing PUBLIC_IP:PORT (relay only)')
    parser.add_argument('--scan-public', action='store_true', help='query signed public-node announcements from configured bootstrap peers, no account required')
    parser.add_argument('--bootstrap', action='append', default=[], help='public directory bootstrap HOST:PORT (repeatable)')
    parser.add_argument('--relay', action='store_true', help='run as a headless authenticated bootstrap/relay node')
    parser.add_argument('--lan', action='store_true', help='opt in to local signed UDP peer discovery')
    parser.add_argument('--offline', action='store_true', help='LAN-only: reject public IPs, hostnames and automatic WAN reconnect')
    parser.add_argument('--scan', action='store_true', help='scan discoverable LAN peers (no account required)')
    parser.add_argument('--no-auto-connect', action='store_true', help='do not reconnect to previously trusted peers')
    parser.add_argument('--root', default='', help=argparse.SUPPRESS)
    parser.add_argument('--node-account', default='', help=argparse.SUPPRESS)
    parser.add_argument('--password-file', default='', help=argparse.SUPPRESS)
    parser.add_argument('--assume-listen', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--tor', action='store_true', help='require local SOCKS5 proxy for all outbound WAN peers; never fallback direct')
    opt = parser.parse_args(args)
    if opt.relay and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    root = secure_root(Path(opt.root).expanduser() if opt.root else None)
    try:
        if opt.scan:
            show_discovered(asyncio.run(scan_lan()))
            return 0
        if opt.scan_public:
            if opt.offline:
                raise ValueError('Public directory scanning requires internet; use --scan for offline LAN peers')
            nodes, failures = asyncio.run(scan_public(opt.bootstrap or [DEFAULT_BOOTSTRAP], tor_mode=opt.tor))
            if failures:
                for f in failures: print('[BOOTSTRAP] ' + f)
            show_public_nodes(nodes)
            return 0 if nodes else 2
        if bool(opt.node_account) != bool(opt.password_file):
            raise ValueError('Background nodes require both account and password file')
        if opt.advertise and (not opt.relay or opt.offline or opt.tor):
            raise ValueError('--advertise requires a public WAN --relay node')
        if opt.advertise:
            public_endpoint(opt.advertise)
        if opt.tor and opt.offline:
            raise ValueError('Offline LAN and Tor outbound routing cannot be enabled together')
        if opt.node_account:
            secret_path = Path(opt.password_file).expanduser().resolve()
            if secret_path.is_symlink() or not secret_path.is_file():
                raise ValueError('Node password file is missing or a symlink')
            if os.name != 'nt' and (secret_path.stat().st_mode & 0o077):
                raise ValueError('Node secret file must be owner-only (chmod 600)')
            if secret_path.stat().st_size > 4096:
                raise ValueError('Node secret file too large')
            ident = login(root, opt.node_account, secret_path.read_text().rstrip('\r\n'))
        else:
            ident = account_menu(root)
        if ident is None:
            return 0
        host, port = parse_endpoint(opt.listen, allow_zero=True)
        if host not in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
            print('[WARNING] Non-loopback listen address: peer connections may be exposed to the internet.')
        if host == '0.0.0.0':
            if opt.offline:
                print('[LAN ONLY] Binds all local network interfaces. Do not port-forward this port.')
                if not (opt.assume_listen and opt.node_account) and input('Type LAN LISTEN to proceed: ').strip() != 'LAN LISTEN':
                    return 0
            else:
                print('[WARNING] Public interfaces: only do this deliberately and after configuring a firewall.')
                if not (opt.assume_listen and opt.node_account) and input('Type PUBLIC LISTEN to proceed: ').strip() != 'PUBLIC LISTEN':
                    return 0
        # Previously *manually trusted* peer endpoints reconnect when starting a chat session; no
        # untrusted address is ever accepted from network messages for auto-dial.
        catalog = load_relay_hosts(root)
        destinations = (opt.peer if opt.peer else ([] if opt.no_auto_connect or opt.offline or opt.relay
                        else [catalog['active']]))
        if destinations and not opt.peer:
            print(f'[AUTO CONNECT] Connecting to {len(destinations)} saved active relay(s).')
        if opt.offline and any(not is_lan_host(parse_endpoint(x)[0]) for x in destinations):
            raise ValueError('Offline mode cannot connect to a public peer')
        asyncio.run(console_session(ident, root, host, port, destinations, opt.relay,
                                    offline_only=opt.offline, lan_discovery=opt.lan or opt.offline,
                                    initial_scan=opt.lan and not opt.relay, tor_mode=opt.tor,
                                    advertise=opt.advertise,
                                    disable_auto_reconnect=opt.no_auto_connect))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'[MESH ERROR] {exc}')
        return 2
    except (EOFError, KeyboardInterrupt):
        print('\nChat canceled.')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
