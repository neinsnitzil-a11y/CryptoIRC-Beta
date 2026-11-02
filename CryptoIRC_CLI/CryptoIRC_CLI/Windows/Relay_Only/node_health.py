#!/usr/bin/env python3
"""Real authenticated encrypted handshake health check for local VaultForge relay."""
from __future__ import annotations
import asyncio
import argparse
from pathlib import Path
import tempfile
import sys

# Python -I excludes the script directory from imports.
ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path: sys.path.insert(0, ROOT)

async def verify(port: int):
    from mesh_chat import create_account, MeshNode
    with tempfile.TemporaryDirectory(prefix='vaultforge-health-') as temp:
        root=Path(temp)
        ident=create_account(root, 'HealthProbe', 'Only-a-local-ephemeral-health-check-identity')
        node=MeshNode(ident, root, notify=lambda _: None)
        await node.start('127.0.0.1',0)
        try:
            await asyncio.wait_for(node.connect(f'127.0.0.1:{port}'),timeout=12)
            if not node.links:
                raise RuntimeError('No encrypted peer link established')
            link=next(iter(node.links))
            print(f'[MESH HANDSHAKE OK] Authenticated encrypted relay identity: {link.keyid}')
            print('[VERIFY] Compare this fingerprint via the SSH console before trusting the first Windows connection.')
            return 0
        finally:
            await node.stop()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=6667)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Invalid port')
    try:return asyncio.run(verify(args.port))
    except Exception as exc:
        print(f'[MESH HANDSHAKE FAILED] {type(exc).__name__}: {exc}')
        print('[ACTION] Check the service logs and confirm correct protocol/port; a TCP listener alone is insufficient.')
        return 1
if __name__=='__main__':raise SystemExit(main())
