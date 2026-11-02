"""Optional real Bitcoin Core REGTEST end-to-end integration test.

Run with: python src/tests/bitcoin_core_regtest_e2e.py
Requires `bitcoind` on PATH (or BITCOIND_EXE set to verified local binary).
Starts a temporary isolated REGTEST node, mines valueless regtest blocks,
creates two encrypted Core wallets, signs/relays, confirms and checks restore.
Never connects to Bitcoin mainnet; never handles real assets.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from btc_phase1 import BitcoinPhaseOne, BitcoinJournal, NodeConfig
from core.transfer import BitcoinRPC


def available_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]


def main():
    binary=os.environ.get('BITCOIND_EXE') or shutil.which('bitcoind')
    if not binary or not Path(binary).is_file():
        print('[NOT RUN] Bitcoin Core bitcoind is not installed. Set BITCOIND_EXE to the official verified executable.')
        return 2
    with tempfile.TemporaryDirectory(prefix='nocturne-regtest-phase1-') as temp:
        datadir=Path(temp)/'node'
        datadir.mkdir()
        walletdir=datadir/'wallets';walletdir.mkdir()
        rpcport=available_port();port=available_port()
        args=[str(binary),f'-datadir={datadir}','-regtest','-server=1','-listen=0',
              '-dnsseed=0','-discover=0','-upnp=0','-natpmp=0',
              '-rpcbind=127.0.0.1','-rpcallowip=127.0.0.1',f'-rpcport={rpcport}',
              f'-port={port}', '-fallbackfee=0.0002','-txindex=1','-printtoconsole=0',
              f'-walletdir={walletdir}']
        proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            cookie=datadir/'regtest'/'.cookie'
            rpc_url=f'http://127.0.0.1:{rpcport}'
            root=None
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError('Bitcoin Core regtest daemon exited before startup.')
                if cookie.is_file():
                    try:
                        root=BitcoinRPC(rpc_url,cookie)
                        if root.call('getblockchaininfo').get('chain')=='regtest':break
                    except Exception:pass
                time.sleep(.15)
            else:raise RuntimeError('Bitcoin Core regtest failed to start.')
            alice='nocturne_alice';bob='nocturne_bob'
            pw='Nocturne-TEST-only-wallet-password!'
            for name in (alice,bob):
                root.call('createwallet',name,False,False,pw,False,True,False)
            alice_rpc=BitcoinRPC(rpc_url,cookie,alice)
            bob_rpc=BitcoinRPC(rpc_url,cookie,bob)
            alice_addr=alice_rpc.call('getnewaddress','phase-one-mining','bech32')
            bob_addr=bob_rpc.call('getnewaddress','phase-one-receive','bech32')
            # Mine 111 blocks to mature enough coinbase outputs.
            root.call('generatetoaddress',111,alice_addr)
            svc=BitcoinPhaseOne(NodeConfig(rpc_url,str(cookie),'regtest'),BitcoinJournal(Path(temp)/'journal.sqlite3'))
            assert svc.balance(alice)['trusted']!='0', 'Mining funds did not mature'
            backup=Path(temp)/'alice_backup.dat'
            alice_rpc.call('backupwallet',str(backup))
            assert backup.is_file() and backup.stat().st_size>100
            preview=svc.prepare(alice,bob_addr,'1.00000000','0.00100000')
            assert preview['amount']=='1.00000000'
            authorization=f'SEND 1.00000000 BTC {bob_addr[-8:]}'
            result=svc.sign_and_broadcast(preview['id'],authorization,pw)
            assert result['status']=='PENDING',result
            root.call('generatetoaddress',1,alice_addr)
            settled=svc.reconcile(preview['id'])
            assert settled['status']=='CONFIRMED',settled
            bob_bal=svc.balance(bob)
            assert bob_bal['trusted']=='1.00000000',bob_bal
            restored=svc.restore_test(alice,str(backup))
            assert restored['addresses_verified']>0
            print('[PASS] REGTEST: encrypted wallets, mined funds, PSBT send, confirmation, balance, backup restore')
            print('TXID: '+result['txid']+' (REGTEST ONLY — no real funds)')
            return 0
        finally:
            try:
                if root is not None:
                    root.call('stop')
                proc.wait(timeout=15)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        # This is a developer-only regtest suite and never prints seed material.
        print('[FAILED] REGTEST integration: '+type(exc).__name__+' — '+str(exc))
        sys.exit(1)
