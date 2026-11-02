"""Chat-only privacy policy used by VaultForge's mesh transport.

This module deliberately excludes wallet and transaction functionality.
Defaults to direct mode; --tor forces the mesh's SOCKS5h path to fail closed.
"""
from __future__ import annotations
import json
from pathlib import Path
import socket


class PrivacyError(RuntimeError):
    pass


def load_settings():
    path=Path.home() / 'VaultForge' / 'network-security.json'
    if path.is_symlink():
        raise PrivacyError('Network settings symlink prohibited')
    try:
        raw=path.read_bytes()
    except FileNotFoundError:
        return {'mode':'direct','port':9050}
    if len(raw)>4096:raise PrivacyError('Network settings too large')
    try: obj=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as exc:raise PrivacyError('Invalid network privacy settings') from exc
    if not isinstance(obj,dict) or obj.get('mode') not in ('direct','tor') or type(obj.get('port')) is not int or obj['port'] not in (9050,9150):
        raise PrivacyError('Invalid network privacy settings')
    return {'mode':obj['mode'],'port':obj['port']}


def socks5_probe(port, timeout=2):
    if port not in (9050,9150):raise PrivacyError('Unsupported local SOCKS port')
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=timeout) as sock:
            sock.settimeout(timeout);sock.sendall(b'\x05\x01\x00');response=sock.recv(2)
    except OSError as exc:
        raise PrivacyError('Tor mode blocked: no local SOCKS5 listener; refusing direct fallback') from exc
    if response!=b'\x05\x00':raise PrivacyError('SOCKS5 handshake rejected')
