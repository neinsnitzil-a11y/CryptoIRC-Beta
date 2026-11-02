"""IRC-inspired LAN chat helpers. Discovery is UNTRUSTED, consent-based local metadata.

No wallet information is ever read by this module. Chat sessions use the existing
experimental authenticated P2P transport; rooms are peer-relayed, not end-to-end.
"""
from __future__ import annotations
import ipaddress
import json
import os
import re
import socket
import struct
import threading
import time
from pathlib import Path

DISCOVERY_PORT = 19421
DISCOVERY_GROUP = '239.255.42.99'
DISCOVERY_MARK = 'CRYPTO-LAN-DISCOVERY-V1'
FP = re.compile(r'^[0-9a-f]{64}$')
NICK = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{1,19}$')
ROOM = re.compile(r'^#[a-z][a-z0-9_-]{0,23}$')


def check_nick(nick):
    if not isinstance(nick, str) or not NICK.fullmatch(nick):
        raise ValueError('Nickname must be 2-20 letters, digits, _ or -, beginning with a letter')
    return nick


def check_room(room):
    if not isinstance(room, str) or not ROOM.fullmatch(room):
        raise ValueError('Room must be # followed by up to 24 lowercase letters, digits, - or _')
    return room


def is_local_ip(ip):
    try:
        addr = ipaddress.ip_address(ip)
        return isinstance(addr, ipaddress.IPv4Address) and (
            addr.is_private or addr.is_link_local) and not addr.is_loopback
    except ValueError:
        return False


def safe_discovery_packet(data, remote_ip, own_fingerprint=''):
    """Never trust a discovery beacon as evidence of identity or user approval."""
    if not is_local_ip(remote_ip) or len(data) > 450: return None
    try:
        obj=json.loads(data)
        if not isinstance(obj,dict) or set(obj) != {'app','nick','fingerprint','port'}: return None
        if obj['app']!=DISCOVERY_MARK or not FP.fullmatch(obj['fingerprint']):return None
        if obj['fingerprint']==own_fingerprint:return None
        check_nick(obj['nick'])
        if type(obj['port']) is not int or not 1024 <= obj['port'] <= 65535:return None
        return {'ip':remote_ip,'port':obj['port'],'fingerprint':obj['fingerprint'],
                'nickname':obj['nick']}
    except (ValueError, TypeError, KeyError, UnicodeDecodeError):
        return None


class ContactBook:
    """Public fingerprints & user-assigned aliases only. Never stores wallet data."""
    def __init__(self, folder):
        self.path=Path(folder).expanduser()/ 'chat_contacts.json'
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if os.name!='nt':self.path.parent.chmod(0o700)
        self.entries={}
        if self.path.exists():
            if self.path.stat().st_size > 65536:raise ValueError('Contacts file too large')
            raw=json.loads(self.path.read_text('utf-8'))
            if not isinstance(raw,dict):raise ValueError('Invalid contacts file')
            for fp,label in raw.items():
                if FP.fullmatch(fp) and isinstance(label,str) and NICK.fullmatch(label):
                    self.entries[fp]=label

    def remember(self, fingerprint, alias):
        if not FP.fullmatch(fingerprint):raise ValueError('Invalid full fingerprint')
        check_nick(alias)
        if len(self.entries)>=256 and fingerprint not in self.entries:
            raise ValueError('Too many contacts')
        self.entries[fingerprint]=alias
        self._write()

    def remove(self,fingerprint):
        self.entries.pop(fingerprint,None);self._write()

    def _write(self):
        content=json.dumps(self.entries,sort_keys=True,indent=2)
        tmp=self.path.with_name(self.path.name+'.tmp')
        flags=os.O_CREAT | os.O_WRONLY | os.O_TRUNC
        if hasattr(os,'O_NOFOLLOW'):flags |= os.O_NOFOLLOW
        fd=os.open(tmp, flags,0o600)
        try:
            with os.fdopen(fd,'w',encoding='utf8') as out:
                out.write(content);out.flush();os.fsync(out.fileno())
            os.replace(tmp,self.path)
            if os.name!='nt':self.path.chmod(0o600)
        finally:
            if tmp.exists():tmp.unlink()


class LANDiscovery:
    """Multicast, link-scoped announcements. Explicit opt-in and no wallet metadata.

    Multicast may be blocked by AP isolation/firewalls. Manual IP still works.
    This is a proprietary discovery packet, NOT mDNS/RFC6762.
    """
    def __init__(self, fingerprint, nickname, listen_port, callback, advertise=True):
        if not FP.fullmatch(fingerprint):raise ValueError('Invalid identity')
        self.fp=fingerprint; self.nickname=check_nick(nickname)
        self.port=int(listen_port)
        if not 1024<=self.port<=65535:raise ValueError('Invalid port')
        self.callback=callback
        self.advertise=bool(advertise)
        self._stop=threading.Event()
        self._thread=None
        self.sock=None

    def _packet(self):
        return json.dumps({'app':DISCOVERY_MARK,'fingerprint':self.fp,
                           'nick':self.nickname,'port':self.port},
                          separators=(',',':')).encode('ascii')

    def start(self):
        if self._thread is not None:raise RuntimeError('Discovery already active')
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            # Exclusive UDP listener failures mean discovery is unavailable, not a reason to bypass auth.
            sock.bind(('',DISCOVERY_PORT))
            sock.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,
                            struct.pack('4s4s',socket.inet_aton(DISCOVERY_GROUP),socket.inet_aton('0.0.0.0')))
            sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,1)
            sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_LOOP,1)
            sock.settimeout(0.8)
            self.sock=sock
            self._thread=threading.Thread(target=self._loop,daemon=True)
            self._thread.start()
        except BaseException:
            sock.close();raise

    def _loop(self):
        next_announce=0.0
        while not self._stop.is_set():
            if self.advertise and time.monotonic() >= next_announce:
                try:self.sock.sendto(self._packet(),(DISCOVERY_GROUP,DISCOVERY_PORT))
                except OSError:pass
                next_announce=time.monotonic()+8
            try:raw,(ip,_) = self.sock.recvfrom(1024)
            except socket.timeout:continue
            except OSError:break
            record=safe_discovery_packet(raw,ip,self.fp)
            if record:self.callback(record)

    def stop(self):
        self._stop.set()
        if self.sock:
            try:self.sock.close()
            except OSError:pass
        self.sock=None
