"""Chat-only privacy configuration: no wallet or blockchain dependencies."""
from pathlib import Path
import json
import socket

class PrivacyError(RuntimeError):
    pass

def load_settings():
    path = Path.home() / 'VaultForge' / 'network-security.json'
    if path.is_symlink():
        raise PrivacyError('Refusing symlinked privacy settings')
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {'mode':'direct','port':9050}
    if len(raw) > 4096:
        raise PrivacyError('Privacy settings too large')
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise PrivacyError('Invalid privacy settings; no direct fallback') from exc
    if not isinstance(data,dict) or data.get('mode') not in ('direct','tor') or type(data.get('port')) is not int or data['port'] not in (9050,9150):
        raise PrivacyError('Invalid privacy settings; no direct fallback')
    return {'mode':data['mode'],'port':data['port']}

def socks5_probe(port, timeout=2.0):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b'\x05\x01\x00')
            result=sock.recv(2)
    except OSError as exc:
        raise PrivacyError('Local SOCKS5 proxy unavailable, refusing direct fallback') from exc
    if result!=b'\x05\x00':
        raise PrivacyError('SOCKS5 handshake refused')
