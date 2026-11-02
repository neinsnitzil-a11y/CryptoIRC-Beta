"""No real funds or remote RPC requests in these tests."""
from unittest import TestCase
from unittest.mock import patch
import live_balances
from live_balance_ui import LiveBalanceUI
from datetime import datetime
from types import SimpleNamespace

class FakeBitcoin:
    def __init__(self,*a,**k):self.wallet=a[2] if len(a)>2 else None
    def call(self,method,*args):
        if method=='listwallets':return ['Alice']
        if method=='getbalances':return {'mine':{'trusted':0.85,'untrusted_pending':0.12,'immature':0.03}}
        raise ValueError(method)

class BalanceTests(TestCase):
    def test_btc_core_wallet_and_pending_with_fee_accounted_by_node(self):
        with patch('live_crypto.checked_node',return_value=(FakeBitcoin(),{'blocks':101234})),\
             patch('core.transfer.BitcoinRPC',FakeBitcoin):
            r=live_balances.snapshot_btc('http://127.0.0.1:8332','/tmp/ignored','Alice')
        self.assertEqual((r.available,r.total,r.secondary),('0.85','1.00','0.12'))
        self.assertEqual(r.secondary_label,'Untrusted pending')
        self.assertEqual(r.height,'101234')
        with patch('live_crypto.checked_node',return_value=(FakeBitcoin(),{'blocks':1})):
            with self.assertRaises(Exception):live_balances.snapshot_btc('http://127.0.0.1:8332','/tmp/x','OTHER')

    def test_no_network_snapshot_is_never_zero(self):
        with patch('live_crypto.checked_node',side_effect=ConnectionError('offline')):
            with self.assertRaises(ConnectionError): live_balances.snapshot_btc('http://127.0.0.1:8332','x','Alice')

    def test_monero_unlocked_and_locked_separate(self):
        class RPC:
            def call(self,method,*args):return {'balance':900_000_000_000,'unlocked_balance':700_000_000_000}
        with patch('backend.xmr_rpc',return_value=(RPC(),{'wallet_block_height':100})):
            r=live_balances.snapshot_xmr('http://127.0.0.1:18082','','')
        self.assertEqual((r.available,r.total,r.secondary),('0.7','0.9','0.2'))

    def test_evm_chain_rpc_balance(self):
        class W3:
            class eth:
                block_number=201
                @staticmethod
                def get_balance(a,stage):return 2*10**18
        class Web3:
            @staticmethod
            def is_address(s):return s.startswith('0x') and len(s)==42
            @staticmethod
            def to_checksum_address(s):return s
        with patch('backend.evm_w3',return_value=W3()),patch.dict('sys.modules',{'web3':SimpleNamespace(Web3=Web3)}):
            r=live_balances.snapshot_evm('ETH','https://rpc.example','0x'+'1'*40)
        self.assertEqual(r.available,'2')
        self.assertEqual(r.height,'201')

    def test_no_false_success_status_for_sent_transaction(self):
        class Fake:
            def __init__(self):
                from tkinter import Tcl
                root=Tcl()
                from tkinter import StringVar
                self.lb_source=StringVar(master=root,value='')
                self.lb_address=StringVar(master=root,value='')
                self.lb_contract=StringVar(master=root,value='')
                self.lb_tracking=StringVar(master=root,value='')
                self.lb_balance=StringVar(master=root,value='')
                self.evm_code=StringVar(master=root,value='ETH')
                self.lb_enabled=False
                self.lb_epoch=0
                self.lb_refresh=lambda:None
        fake=Fake()
        plan=type('Plan',(),{'kind':'evm','source':'0x'+'1'*40,'context':{'code':'ETH','token_addr':None}})()
        LiveBalanceUI.lb_after_send(fake,plan,'0x'+'9'*64)
        self.assertIn('SUBMITTED',fake.lb_tracking.get())
        self.assertNotIn('CONFIRMED',fake.lb_tracking.get())
        self.assertTrue(fake.lb_enabled)

    def test_btc_vault_not_mistaken_for_core_wallet(self):
        class Fake:
            def __init__(self):
                from tkinter import Tcl,StringVar
                root=Tcl()
                self.lb_balance=StringVar(master=root,value='')
        fake=Fake()
        LiveBalanceUI.lb_use_public_row(fake,{'coin':'BTC','address':'bc1qexample'})
        self.assertIn('NOT connected',fake.lb_balance.get())
