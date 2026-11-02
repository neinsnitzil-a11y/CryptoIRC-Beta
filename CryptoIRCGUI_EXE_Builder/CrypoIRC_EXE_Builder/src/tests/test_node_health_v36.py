"""Isolated synthetic node checks; does not assert mainnet financial readiness."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from node_health import (probe_bitcoin, probe_evm, probe_solana, probe_xrp,
                         select_read_endpoint, BalanceFreshness, NodeHealth)
from core.transfer import TransferError
from tests.test_token_infrastructure_v35 import enc58


class NodeHealthTests(unittest.TestCase):
    def test_bitcoin_synced_regtest_and_wrong_chain(self):
        rpc=Mock();rpc.call.return_value={'chain':'regtest','blocks':3,'headers':3,
                                           'verificationprogress':1.0,'initialblockdownload':False}
        result=probe_bitcoin('http://127.0.0.1:18443','/tmp/cookie','regtest',rpc_factory=lambda *a:rpc,clock=lambda:100)
        self.assertEqual(result.state,'READY')
        self.assertEqual(result.height,3)
        with self.assertRaisesRegex(TransferError,'mismatch'):
            probe_bitcoin('http://127.0.0.1:18443','/tmp/cookie','main',rpc_factory=lambda *a:rpc)

    def test_bitcoin_ibd_and_header_gap_not_ready(self):
        state={'chain':'regtest','blocks':3,'headers':3,'verificationprogress':0.4,'initialblockdownload':True}
        fake=Mock();fake.call.side_effect=lambda _:state
        self.assertEqual(probe_bitcoin('http://127.0.0.1:18443','/tmp/c','regtest',rpc_factory=lambda *a:fake).state,'SYNCING')
        state['initialblockdownload']=False;state['headers']=4
        self.assertEqual(probe_bitcoin('http://127.0.0.1:18443','/tmp/c','regtest',rpc_factory=lambda *a:fake).state,'SYNCING')
        state['headers']=2
        with self.assertRaisesRegex(TransferError,'inconsistent'):
            probe_bitcoin('http://127.0.0.1:18443','/tmp/c','regtest',rpc_factory=lambda *a:fake)

    def test_bitcoin_mainnet_stale_tip(self):
        fake=Mock();fake.call.return_value={'chain':'main','blocks':10,'headers':10,
                'verificationprogress':1,'initialblockdownload':False,'time':100}
        self.assertEqual(probe_bitcoin('http://127.0.0.1:8332','/tmp/c','main',rpc_factory=lambda *a:fake,clock=lambda:5000).state,'STALE')
        self.assertEqual(probe_bitcoin('http://127.0.0.1:8332','/tmp/c','main',rpc_factory=lambda *a:fake,clock=lambda:150).state,'READY')

    def test_evm_chain_id_head_and_lag(self):
        states={'eth_chainId':'0xaa36a7','eth_syncing':False,'eth_blockNumber':'0xa',
                'eth_getBlockByNumber':{'number':'0xa','timestamp':'0x3e8'}}
        def rpc(url,obj):return {'result':states[obj['method']]}
        status=probe_evm('https://rpc.example',11155111,transport=rpc,clock=lambda:1010)
        self.assertEqual(status.state,'READY')
        self.assertEqual(status.height,10)
        states['eth_chainId']='0x1'
        with self.assertRaisesRegex(TransferError,'chain ID'):
            probe_evm('https://rpc.example',11155111,transport=rpc)
        states['eth_chainId']='0xaa36a7';states['eth_syncing']={'currentBlock':'0xa'}
        self.assertEqual(probe_evm('https://rpc.example',11155111,transport=rpc,clock=lambda:1010).state,'SYNCING')
        states['eth_syncing']=False
        self.assertEqual(probe_evm('https://rpc.example',11155111,transport=rpc,clock=lambda:5000).state,'STALE')
        states['eth_getBlockByNumber']['number']='0x9'
        with self.assertRaisesRegex(TransferError,'Inconsistent'):
            probe_evm('https://rpc.example',11155111,transport=rpc,clock=lambda:1010)

    def test_solana_pinned_genesis_health(self):
        genesis=enc58(bytes(range(1,33)))
        states={'getGenesisHash':genesis,'getHealth':'ok','getSlot':1234}
        def rpc(url,obj):return {'result':states[obj['method']]}
        s=probe_solana('https://sol.example',genesis,transport=rpc,clock=lambda:100)
        self.assertTrue(s.ready)
        states['getHealth']='behind'
        self.assertEqual(probe_solana('https://sol.example',genesis,transport=rpc).state,'SYNCING')
        states['getGenesisHash']='different'
        with self.assertRaisesRegex(TransferError,'genesis'):
            probe_solana('https://sol.example',genesis,transport=rpc)

    def test_xrp_requires_independent_identity(self):
        info={'server_state':'full','validated_ledger':{'seq':111,'age':2}}
        def rpc(url,obj):return {'result':{'info':info}}
        s=probe_xrp('https://xrpl.example',1,transport=rpc,clock=lambda:100)
        self.assertEqual(s.state,'UNVERIFIED')
        info['network_id']=1
        self.assertTrue(probe_xrp('https://xrpl.example',1,transport=rpc,clock=lambda:100).ready)
        info['network_id']=2
        with self.assertRaisesRegex(TransferError,'mismatch'):
            probe_xrp('https://xrpl.example',1,transport=rpc)
        info['network_id']=1;info['validated_ledger']['age']=200
        self.assertEqual(probe_xrp('https://xrpl.example',1,transport=rpc).state,'STALE')

    def test_only_read_only_failover_and_same_identity(self):
        primary='https://primary.example';backup='https://backup.example'
        calls=[]
        def probe(url):
            calls.append(url)
            if url == primary:raise TransferError('offline')
            return NodeHealth('EVM','1',url,100,1010,'READY','test')
        r=select_read_endpoint((primary,backup),probe,expected_identity='1')
        self.assertEqual(r.endpoint,backup)
        self.assertEqual(calls,[primary,backup])
        with self.assertRaisesRegex(TransferError,'No healthy'):
            select_read_endpoint((primary,backup),probe,expected_identity='56')

    def test_failover_rejects_stale_and_height_divergence(self):
        one='https://one.example';two='https://two.example'
        def probe(url):return NodeHealth('EVM','1',url,10 if url==one else 999,0,'READY','')
        self.assertEqual(select_read_endpoint((one,two),probe,expected_identity='1').endpoint,two)
        with self.assertRaises(TransferError):
            select_read_endpoint((one,),lambda e:NodeHealth('EVM','1',e,0,0,'STALE',''),expected_identity='1')
        with self.assertRaises(TransferError):
            select_read_endpoint((one,one),probe,expected_identity='1')
        with self.assertRaises(TransferError):
            select_read_endpoint(('http://not-local:8832',),probe,expected_identity='1')

    def test_balance_freshness_does_not_cross_endpoint_or_identity(self):
        gate=BalanceFreshness(100,'1','https://a.example')
        self.assertTrue(gate.usable(now=180,identity='1',endpoint='https://a.example'))
        self.assertFalse(gate.usable(now=191,identity='1',endpoint='https://a.example'))
        self.assertFalse(gate.usable(now=110,identity='56',endpoint='https://a.example'))
        self.assertFalse(gate.usable(now=110,identity='1',endpoint='https://b.example'))
        self.assertFalse(gate.usable(now=99,identity='1',endpoint='https://a.example'))

if __name__=='__main__':unittest.main()

class BalanceUiRaceTests(unittest.TestCase):
    def test_old_account_result_never_overwrites_current_balance(self):
        from tkinter import Tcl, StringVar
        from live_balance_ui import LiveBalanceUI
        t=Tcl()
        class Fake:pass
        a=Fake();a.lb_closed=False;a.lb_epoch=1;a.lb_inflight=True;a.lb_queued_refresh=False
        a.lb_balance=StringVar(master=t,value='QUERYING');a.lb_secondary=StringVar(master=t,value='')
        a.lb_last_good_monotonic=10;a.lb_last_good_settings={'node':'old'}
        a._lb_settings=lambda:{'node':'new'}
        a.root=type('Root',(),{'after':lambda *args:None})()
        a.lb_refresh=lambda:None
        result=type('Snapshot',(),{'currency':'ETH','available':'123','total':'123'})()
        LiveBalanceUI._lb_deliver(a,1,result,False,{'node':'old'})
        self.assertIn('UNAVAILABLE',a.lb_balance.get())
        self.assertNotIn('123',a.lb_balance.get())
        self.assertIsNone(a.lb_last_good_monotonic)

    def test_expired_balance_marked_stale(self):
        from tkinter import Tcl, StringVar
        from live_balance_ui import LiveBalanceUI
        t=Tcl()
        class Fake:pass
        a=Fake();a.lb_closed=False;a.lb_enabled=False;a.lb_inflight=False;a.lb_interval_ms=30000;a._lb_tick=lambda:None
        a.lb_last_good_monotonic=-100;a.lb_last_good_settings={'node':'a'}
        a.lb_balance=StringVar(master=t,value='100 BTC');a.lb_secondary=StringVar(master=t,value='')
        a._lb_settings=lambda:{'node':'a'}
        a.root=type('Root',(),{'after':lambda *args:None})()
        LiveBalanceUI._lb_tick(a)
        self.assertIn('STALE',a.lb_balance.get())
        self.assertIsNone(a.lb_last_good_monotonic)
