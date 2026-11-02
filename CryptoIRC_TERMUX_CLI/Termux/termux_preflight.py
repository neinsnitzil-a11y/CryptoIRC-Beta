#!/usr/bin/env python3
"""Fail-closed runtime check. Does not create wallets, sign, or call the network."""
from __future__ import annotations
import argparse, importlib, os, pathlib, sys

def check(full=True):
    modules = ['cryptography', 'argon2.low_level', 'socks', 'prompt_toolkit']
    if full:
        modules += ['bip_utils', 'coincurve', 'eth_account', 'web3', 'requests']
    failed=[]
    for module in modules:
        try:
            importlib.import_module(module)
            print(f'[OK] {module}')
        except Exception as exc:
            print(f'[MISSING] {module}: {type(exc).__name__}: {exc}')
            failed.append(module)
    if failed:
        print('[BLOCKED] Install unmet native dependencies before claiming full wallet capability.')
        return 1
    if full:
        # Load all local CLI modules; no secrets accessed, no transactions sent.
        app = pathlib.Path(__file__).resolve().parent/'app'
        sys.path.insert(0,str(app))
        try:
            import vaultforge, wallet_core, transfer_engine, bitcoin_vault, vault_bridge, mesh_chat
            wallet_core.load_crypto()
            assert len(wallet_core.COINS) == 30
            print('[OK] Full CLI imports and 30-coin format registry')
        except Exception as exc:
            print(f'[BLOCKED] Full CLI module check: {type(exc).__name__}: {exc}')
            return 1
    print('[CHECK] Static imports passed. Live wallet send/receive, transactions and mesh network are NOT verified here.')
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--full',action='store_true')
    p.add_argument('--chat-only',action='store_true')
    args=p.parse_args()
    raise SystemExit(check(full=not args.chat_only))
