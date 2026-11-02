#!/usr/bin/env python3
"""VaultForge TCP reachability preflight. Never transmits wallet secrets or chat credentials.

Plain TCP success means only that the port accepts a connection; the mesh still must
authenticate and establish an encrypted peer session afterward.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import socket
import sys

DEFAULT_AWS='18.188.145.207:6667'

def endpoint_parts(endpoint: str) -> tuple[str,int]:
    if not endpoint or len(endpoint)>280 or any(x in endpoint for x in '/@ \\'):
        raise ValueError('Provide HOST:PORT, not a URL or username')
    if endpoint.startswith('['):
        close=endpoint.find(']')
        if close<1 or endpoint[close+1:close+2]!=':':
            raise ValueError('Invalid IPv6 endpoint')
        host, port=endpoint[1:close],endpoint[close+2:]
    else:
        if endpoint.count(':')!=1:raise ValueError('Provide HOST:PORT')
        host, port=endpoint.rsplit(':',1)
    if not host or not port.isdecimal() or not 1<=int(port)<=65535:
        raise ValueError('Invalid HOST or TCP port')
    return host,int(port)

def tor_policy():
    settings=Path.home()/'VaultForge'/'network-security.json'
    if settings.is_symlink():return 'invalid'
    try:
        obj=json.loads(settings.read_text())
    except FileNotFoundError:
        return 'direct'
    except (OSError, UnicodeError, ValueError):
        return 'invalid'
    if not isinstance(obj,dict) or obj.get('mode') not in ('tor','direct'):
        return 'invalid'
    return obj['mode']

def probe_endpoint(endpoint: str, *, timeout: float = 4, verbose: bool = True, policy: str | None = None) -> bool:
    host,port=endpoint_parts(endpoint)
    policy = policy or tor_policy()
    if policy!='direct':
        if verbose:
            print('[PRIVACY] Direct TCP diagnostic blocked because Tor-required mode is enabled or settings are invalid.')
            print('[ACTION] Connect through Tor using Mesh Chat option 15; no direct network fallback.')
        return False
    if verbose:print(f'[CHECK] Testing TCP reachability to {host}:{port} (timeout {timeout:g}s)...')
    try:
        with socket.create_connection((host,port),timeout=timeout): pass
    except socket.gaierror as exc:
        if verbose:print(f'[DNS ERROR] Could not resolve host: {exc}. Use the EC2 public IPv4 address or fix DNS.')
    except ConnectionRefusedError:
        if verbose:print(f'[REFUSED] Server reachable, but no service accepted TCP {port}. Check systemd, listener, and firewall.')
    except (TimeoutError,socket.timeout):
        if verbose:print(f'[TIMEOUT] TCP {port} unreachable. Check EC2 security group inbound rules, Ubuntu UFW, network ACLs, and EC2 running state.')
    except OSError as exc:
        if verbose:print(f'[NETWORK ERROR] {type(exc).__name__}: {exc}')
    else:
        if verbose:
            print(f'[TCP OPEN] {host}:{port} accepts connections.')
            print('[NEXT] Chat will verify the peer identity and encrypted handshake; TCP alone does NOT prove a working mesh node.')
        return True
    return False

def main(argv=None):
    parser=argparse.ArgumentParser(description='Non-secret TCP diagnostics for VaultForge AWS or user-hosted mesh')
    parser.add_argument('endpoint',nargs='?',default=DEFAULT_AWS)
    parser.add_argument('--timeout',type=float,default=4)
    parser.add_argument('--connect',action='store_true',help='after reachable TCP, launch encrypted chat with ephemeral localhost listener')
    args=parser.parse_args(argv)
    if not 0.2<=args.timeout<=30:parser.error('Timeout must be 0.2..30 seconds')
    try:
        ok=probe_endpoint(args.endpoint,timeout=args.timeout)
    except ValueError as exc:
        print(f'[INPUT ERROR] {exc}')
        return 2
    if not ok:return 1
    if args.connect:
        import subprocess
        executable=Path(__file__).resolve().with_name('mesh_chat.py')
        return subprocess.call([sys.executable,'-I',str(executable),'--listen','127.0.0.1:0','--peer',args.endpoint])
    return 0

if __name__=='__main__':
    raise SystemExit(main())
