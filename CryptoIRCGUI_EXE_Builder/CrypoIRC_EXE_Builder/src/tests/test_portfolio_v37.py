"""Phase 10: synthetic RPC tests only, not real-money validation."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portfolio_engine import (amount, wallet_identity, distinct_accounts, Observation, summarize,
                              query_account, PortfolioError, public_activity)
from unified_wallet import account_from_record


def account(kind='watch_only',asset='ETH',network='ETH',address='0x'+'a'*40,source='watch_only',label='Test'):
    return account_from_record(dict(kind=kind,asset=asset,network=network,address=address,source=source,label=label))


def fake_balance(currency='ETH',total='1.25',available='1.20'):
    return SimpleNamespace(currency=currency,total=total,available=available,height='75',
                           source='test_rpc',pending_note='No signer proof')

class PortfolioTests(unittest.TestCase):
    def test_reject_float_inexact_negative_nan(self):
        for val in [1.1, True, -1, 'NaN', 'Infinity', 'oops']:
            with self.subTest(val=val),self.assertRaises(PortfolioError):amount(val)
        self.assertEqual(amount('0.00000000000000000001'),Decimal('0.00000000000000000001'))

    def test_btc_core_aliases_cannot_double_count(self):
        a=account('btc_core','BTC','main','bc1qfirst','wallet-A')
        b=account('btc_core','BTC','main','bc1qsecond','wallet-A')
        self.assertEqual(len(distinct_accounts([a,b])),1)
        self.assertEqual(wallet_identity(a),wallet_identity(b))

    def test_watch_only_and_keystore_same_address_deduplicate(self):
        a=account()
        b=account('evm_keystore',source='/tmp/wallet.json')
        self.assertEqual(len(distinct_accounts([a,b])),1)
        self.assertEqual(distinct_accounts([a,b])[0].kind,'evm_keystore')

    def test_networks_not_combined(self):
        a=account(network='ETH');b=account(network='ARB')
        o1=Observation.from_snapshot(a,fake_balance(),observed=100)
        o2=Observation.from_snapshot(b,fake_balance(),observed=100)
        result=summarize([a,b],{wallet_identity(a):o1,wallet_identity(b):o2},now=110)
        self.assertEqual(len(result['groups']),2)
        self.assertEqual([g['reported_total'] for g in result['groups']],[Decimal('1.25')]*2)

    def test_stale_never_aggregates_with_live(self):
        a=account(address='0x'+'1'*40);b=account(address='0x'+'2'*40)
        observations={wallet_identity(a):Observation.from_snapshot(a,fake_balance(),observed=200),
                      wallet_identity(b):Observation.from_snapshot(b,fake_balance(),observed=10)}
        s=summarize([a,b],observations,now=200)
        self.assertEqual(s['stale'],1)
        self.assertIsNone(s['groups'][0]['reported_total'])
        self.assertIsNone(s['groups'][0]['reported_available'])

    def test_unavailable_is_not_zero(self):
        a=account();s=summarize([a],{},now=10)
        self.assertIsNone(s['rows'][0]['total'])
        self.assertEqual(s['rows'][0]['state'],'UNAVAILABLE')
        self.assertIsNone(s['groups'][0]['reported_total'])

    def test_wrong_chain_or_available_more_than_total_rejected(self):
        a=account('btc_core','BTC','regtest','bcrt','mywallet')
        with self.assertRaises(PortfolioError):Observation.from_snapshot(a,fake_balance('ETH'))
        with self.assertRaises(PortfolioError):Observation.from_snapshot(a,fake_balance('BTC','1','2'))

    def test_exact_integer_btc_balance_and_network_check(self):
        a=account('btc_core','BTC','regtest','bcrt1q','wallet-A')
        def rpc_factory(url,cookie,wallet=None):
            root=Mock()
            def call(method,*args):
                if method=='getblockchaininfo':
                    return dict(chain='regtest',blocks=100,headers=100,initialblockdownload=False,verificationprogress=1)
                if method=='listwallets':return ['wallet-A']
                if method=='getaddressinfo':return {'ismine':True}
                if method=='getbalances':return {'mine':{'trusted':Decimal('0.10000001'),'untrusted_pending':Decimal('0.00000001'),'immature':Decimal('0')}}
                raise ValueError('unexpected RPC '+method)
            root.call.side_effect=call
            return root
        s=query_account(a,{'btc_url':'http://127.0.0.1:18443','btc_cookie':'/tmp/cookie'},btc_factory=rpc_factory)
        self.assertEqual(s.total,'0.10000002')
        self.assertEqual(s.available,'0.10000001')
        def wrong(url,cookie,wallet=None):
            rpc=rpc_factory(url,cookie,wallet)
            old=rpc.call.side_effect
            rpc.call.side_effect=lambda method,*args: dict(chain='main',blocks=100,headers=100,initialblockdownload=False,verificationprogress=1) if method=='getblockchaininfo' else old(method,*args)
            return rpc
        with self.assertRaises(Exception):query_account(a,{'btc_url':'http://127.0.0.1:18443','btc_cookie':'/tmp/cookie'},btc_factory=wrong)

    def test_monero_account_mismatch_rejects_before_balance(self):
        a=account('xmr_rpc','XMR','stagenet','moneroaddress','local_wallet_rpc')
        rpc=Mock();rpc.call.side_effect=lambda method,*args: (dict(network_type='stagenet',wallet_block_height=5,daemon_block_height=5) if method=='get_wallet_info' else dict(height=5) if method=='get_height' else
            dict(address='wrongaddress') if method=='get_address' else dict(valid=True,nettype='stagenet'))
        with self.assertRaises(PortfolioError):query_account(a,{'xmr_url':'http://127.0.0.1:38082'},xmr_factory=lambda *x:rpc)
        self.assertNotIn('get_balance',[c.args[0] for c in rpc.call.call_args_list])

    def test_monero_scan_lag_rejected(self):
        a=account('xmr_rpc','XMR','stagenet','moneroaddress','local_wallet_rpc')
        rpc=Mock();rpc.call.return_value={'network_type':'stagenet','wallet_block_height':3,'daemon_block_height':44}
        with self.assertRaises(PortfolioError):query_account(a,{'xmr_url':'http://127.0.0.1:38082'},xmr_factory=lambda *x:rpc)
        self.assertNotIn('get_balance',[x.args[0] for x in rpc.call.call_args_list])

    def test_monero_atomic_precision_correct(self):
        a=account('xmr_rpc','XMR','stagenet','moneroaddress','local_wallet_rpc')
        def call(method,*args):
            return {'get_wallet_info':{'network_type':'stagenet','wallet_block_height':8,'daemon_block_height':8},'get_height':{'height':8},'get_address':{'address':'moneroaddress'},
                    'validate_address':{'valid':True,'nettype':'stagenet'},
                    'get_balance':{'balance':1000000000001,'unlocked_balance':1}}[method]
        rpc=Mock();rpc.call.side_effect=call
        snap=query_account(a,{'xmr_url':'http://127.0.0.1:38082'},xmr_factory=lambda *x:rpc)
        self.assertEqual(snap.total,'1.000000000001');self.assertEqual(snap.available,'1E-12')

    def test_evm_mismatched_network_and_tokens_blocked(self):
        a=account('evm_keystore','ETH','ETH',source='/tmp/key')
        with self.assertRaises(PortfolioError):query_account(a,{'evm_code':'ARB','evm_url':'https://example'})
        t=account('watch_only','USDT-ETH','ETH')
        with self.assertRaises(PortfolioError):query_account(t,{'evm_code':'ETH','evm_url':'https://example'})
        result=query_account(a,{'evm_code':'ETH','evm_url':'https://example'},evm_reader=lambda c,url,addr:fake_balance())
        self.assertEqual(result.currency,'ETH')

    def test_local_activity_only_matches_account_and_network(self):
        a=account('evm_keystore','ETH','ETH')
        base={'chain':'EVM','network':'1','source':a.address,'asset':'ETH'}
        h=[base,dict(base,network='42161'),dict(base,source='0x'+'b'*40),dict(base,chain='BTC')]
        self.assertEqual(public_activity(h,a),[base])
        self.assertEqual(public_activity(h,account('evm_keystore','ARB','ARB')),[dict(base,network='42161')])

    def test_observation_identity_mismatch_rejected(self):
        a=account();b=account(address='0x'+'b'*40)
        obs=Observation.from_snapshot(a,fake_balance(),observed=10)
        with self.assertRaises(PortfolioError):summarize([b],{wallet_identity(b):obs},now=15)

if __name__=='__main__':unittest.main()
