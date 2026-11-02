"""RPC-faked Phase 2/3 tests. NO live money or signed credentials."""
import tempfile, unittest, json
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
from chain_journal import ChainJournal
from core.transfer import TransferError
from evm_phase2 import EVMPhaseTwo
from xmr_phase3 import MoneroPhaseThree

A='0x'+'a'*40;B='0x'+'b'*40;T='0x'+'c'*40
X='4'+'A'*94

class FakeToken:
    def __init__(self):
        class Functions:
            @staticmethod
            def decimals():return type('Call',(),{'call':lambda self:6})()
            @staticmethod
            def symbol():return type('Call',(),{'call':lambda self:'USDT'})()
            @staticmethod
            def balanceOf(who):return type('Call',(),{'call':lambda self:5_000_000})()
        self.functions=Functions()
    def encode_abi(self,*args,**kwargs):return '0xa9059cbb'+'0'*64

class FakeEth:
    def __init__(self):self.chain_id=11155111;self.block_number=100;self.pending_nonce=4;self.receipt=None;self.max_priority_fee=1_000_000_000
    def get_transaction_count(self,*a):return self.pending_nonce
    def estimate_gas(self,*a):return 21000
    def get_block(self,*a):return {'baseFeePerGas':20_000_000_000}
    def get_balance(self,*a):return 10**18
    def get_code(self,*a):return b'\x01'
    def contract(self,*a,**kwargs):return FakeToken()
    def get_transaction_receipt(self,*a):return self.receipt

class FakeWeb3:
    def __init__(self):self.eth=FakeEth()
    @staticmethod
    def is_address(a):return isinstance(a,str) and a.startswith('0x') and len(a)==42
    @staticmethod
    def to_checksum_address(a):return a

class FakeMonero:
    def __init__(self):self.prepared=[];self.relay_count=0;self.missing=False
    def call(self,m,p=None):
        if m=='get_height':return {'height':1000}
        if m=='get_address':return {'address':X}
        if m=='validate_address':return {'valid':True,'nettype':'mainnet'}
        if m=='get_balance':return {'balance':4*10**12,'unlocked_balance':3*10**12}
        if m=='create_address':return {'address':X,'address_index':2}
        if m=='get_transfers':return {'in':[{'txid':'a'*64,'amount':10**12,'confirmations':12}]}
        if m=='transfer':
            self.prepared.append(p)
            return {'tx_hash':'f'*64,'tx_metadata':'abcdef123456','fee':10**10,'amount':10**12}
        if m=='relay_tx':self.relay_count+=1;return {'tx_hash':'f'*64}
        if m=='get_transfer_by_txid':
            if self.missing:raise TransferError('Not found')
            return {'transfer':{'txid':'f'*64,'type':'out','amount':10**12,'confirmations':12}}
        raise ValueError(m)

class Phase23Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.j=ChainJournal(Path(self.temp.name)/'chain.sqlite3')
        self.web=FakeWeb3()
        self.ks=Path(self.temp.name)/'v3.json';self.ks.write_text(json.dumps({'address':A[2:],'crypto':{'ciphertext':'fake'}}))
    def evm(self):return EVMPhaseTwo('SEPOLIA','https://rpc.example.com',self.j,self.web)
    def xmr(self):
        self.rpc=FakeMonero();return MoneroPhaseThree('http://127.0.0.1:18082','user','test',self.j,self.rpc)
    def test_evm_native_prepare_and_nonce_reservation(self):
        x=self.evm();a=x.prepare(self.ks,B,'0.005','0.002')
        self.assertEqual(a['status'],'PREPARED');self.assertEqual(a['nonce'],4)
        self.assertEqual(a['amount_units'],'5000000000000000')
        with self.assertRaises(TransferError):x.prepare(self.ks,B,'0.1','0.01')
        x.cancel(a['id'])
        self.assertEqual(x.prepare(self.ks,B,'0.01','0.003')['nonce'],4)
    def test_evm_wrong_chain_blocked(self):
        self.web.eth.chain_id=1
        with self.assertRaises(TransferError):self.evm().prepare(self.ks,B,'0.01','0.01')
    def test_evm_token_contract_metadata_must_match(self):
        x=self.evm()
        with self.assertRaises(TransferError):x.prepare(self.ks,B,'1','0.01',token_contract=T,expected_symbol='FAKE',expected_decimals=6)
        row=x.prepare(self.ks,B,'1','0.01',token_contract=T,expected_symbol='USDT',expected_decimals=6)
        self.assertEqual(row['asset'],'USDT');self.assertEqual(row['amount_units'],'1000000')
    def test_evm_rpc_pending_and_finality(self):
        x=self.evm();row=x.prepare(self.ks,B,'0.005','0.002')
        self.j.transition(row['id'],('PREPARED',),'BROADCASTING',tx_hash='0x'+'f'*64)
        self.j.transition(row['id'],('BROADCASTING',),'UNKNOWN')
        self.assertEqual(x.reconcile(row['id'])['status'],'UNKNOWN')
        self.web.eth.receipt={'blockHash':bytes.fromhex('1'*64),'status':1,'blockNumber':99}
        self.assertEqual(x.reconcile(row['id'])['status'],'PENDING')
        self.web.eth.block_number=110
        self.assertEqual(x.reconcile(row['id'])['status'],'CONFIRMED')
        self.web.eth.receipt={'blockHash':bytes.fromhex('2'*64),'status':1,'blockNumber':100}
        self.assertEqual(x.reconcile(row['id'])['status'],'REORG_REVIEW')
    def test_monero_prepared_not_relayed_without_confirmation(self):
        x=self.xmr();row=x.prepare(X,'1','0.05')
        self.assertEqual(row['status'],'PREPARED');self.assertTrue(self.rpc.prepared[0]['do_not_relay'])
        with self.assertRaises(TransferError):x.relay(row['id'],'NO')
        self.assertEqual(self.rpc.relay_count,0)
        signed=x.relay(row['id'],'SEND 1 XMR '+X[-8:])
        self.assertEqual(signed['status'],'PENDING');self.assertEqual(self.rpc.relay_count,1)
        self.assertEqual(x.reconcile(row['id'])['status'],'CONFIRMED')
    def test_monero_restart_loses_metadata_and_cannot_relay(self):
        x=self.xmr();row=x.prepare(X,'1','0.05')
        new=MoneroPhaseThree(x.url,'user','test',self.j,self.rpc)
        with self.assertRaises(TransferError):new.relay(row['id'],'SEND 1 XMR '+X[-8:])
        self.assertEqual(self.j.get(row['id'])['status'],'UNSPENDABLE')
    def test_monero_locked_funds_and_fee_cap(self):
        x=self.xmr();self.assertEqual(x.balance()['locked'],'1')
        with self.assertRaises(TransferError):x.prepare(X,'2.99','0.05')
    def test_monero_invalid_wallet_network(self):
        class WrongMonero(FakeMonero):
            def call(self,m,p=None):
                if m=='validate_address':return {'valid':True,'nettype':'testnet'}
                return super().call(m,p)
        x=MoneroPhaseThree('http://127.0.0.1:18082','x','y',self.j,WrongMonero())
        with self.assertRaises(TransferError):x.health()
    def test_journal_does_not_contain_relay_metadata(self):
        x=self.xmr();x.prepare(X,'1','0.05')
        self.assertNotIn(b'abcdef123456',self.j.path.read_bytes())

if __name__=='__main__':unittest.main()

class AdditionalPhase23Tests(Phase23Tests):
    """Network outcomes beyond the nominal send path."""
    def test_evm_token_receipt_missing_transfer_event_requires_review(self):
        x=self.evm();row=x.prepare(self.ks,B,'1','0.02',token_contract=T,expected_symbol='USDT',expected_decimals=6)
        self.j.transition(row['id'],('PREPARED',),'BROADCASTING',tx_hash='0x'+'f'*64)
        self.j.transition(row['id'],('BROADCASTING',),'PENDING')
        self.web.eth.receipt={'status':1,'blockHash':bytes.fromhex('a'*64),'blockNumber':100,'logs':[]}
        self.assertEqual(x.reconcile(row['id'])['status'],'REQUIRES_REVIEW')
    def test_monero_incoming_record_does_not_confirm_outgoing(self):
        x=self.xmr();row=x.prepare(X,'1','0.05')
        x.relay(row['id'],'SEND 1 XMR '+X[-8:])
        orig=self.rpc.call
        def wrong(m,p=None):
            if m=='get_transfer_by_txid':return {'transfer':{'txid':'f'*64,'type':'in','amount':10**12,'confirmations':99}}
            return orig(m,p)
        self.rpc.call=wrong
        self.assertEqual(x.reconcile(row['id'])['status'],'REQUIRES_REVIEW')
    def test_monero_restore_public_identity(self):
        x=self.xmr()
        self.assertTrue(x.check_restored_address(X)['address_matches'])
        with self.assertRaises(TransferError):x.check_restored_address('4'+'B'*94)

class StagenetPhase3Tests(Phase23Tests):
    def test_xmr_stagenet_must_match_selected_network(self):
        class StagenetRPC(FakeMonero):
            def call(self,m,p=None):
                if m=='validate_address':return {'valid':True,'nettype':'stagenet'}
                return super().call(m,p)
        rpc=StagenetRPC()
        s=MoneroPhaseThree('http://127.0.0.1:18082','u','p',self.j,rpc,network='stagenet')
        self.assertEqual(s.health()['network'],'stagenet')
        row=s.prepare(X,'1','0.05');self.assertEqual(row['network'],'stagenet')
        other=MoneroPhaseThree('http://127.0.0.1:18082','u','p',self.j,FakeMonero(),network='mainnet')
        with self.assertRaises(TransferError):other.cancel(row['id'])

    def test_evm_token_balance_reads_actual_contract(self):
        bal=self.evm().balance(A,T)
        self.assertEqual(bal['token_balance'],'5')
        self.assertEqual(bal['token_symbol'],'USDT')

class EvmBroadcastTests(Phase23Tests):
    def _fake_account_module(self):
        import types
        module=types.ModuleType('eth_account')
        class Account:
            @staticmethod
            def decrypt(*args):return b'\x22'*32
            @staticmethod
            def from_key(key):
                class Wallet:
                    address=A
                    def sign_transaction(self,tx):
                        return types.SimpleNamespace(raw_transaction=b'fake signed bytes',hash=bytes.fromhex('f'*64))
                return Wallet()
            @staticmethod
            def recover_transaction(data):return A
        module.Account=Account
        return module

    def test_sign_broadcast_journal_then_no_second_send(self):
        import sys,types
        x=self.evm();row=x.prepare(self.ks,B,'0.01','0.005')
        calls=[]
        def send(raw):calls.append(raw);return bytes.fromhex('f'*64)
        self.web.eth.send_raw_transaction=send
        with patch.dict(sys.modules,{'eth_account':self._fake_account_module()}):
            sent=x.submit(row['id'],'SEND 0.01 ETH '+B[-8:],self.ks,'dummy')
        self.assertEqual(sent['status'],'PENDING');self.assertEqual(sent['tx_hash'],'0x'+'f'*64)
        with self.assertRaises(TransferError):
            with patch.dict(sys.modules,{'eth_account':self._fake_account_module()}):
                x.submit(row['id'],'SEND 0.01 ETH '+B[-8:],self.ks,'dummy')
        self.assertEqual(len(calls),1)

    def test_broadcast_timeout_stays_unknown_and_never_resigns(self):
        import sys
        x=self.evm();row=x.prepare(self.ks,B,'0.01','0.005')
        def timeout(raw):raise TimeoutError('ambiguous')
        self.web.eth.send_raw_transaction=timeout
        with patch.dict(sys.modules,{'eth_account':self._fake_account_module()}):
            with self.assertRaises(TransferError):x.submit(row['id'],'SEND 0.01 ETH '+B[-8:],self.ks,'dummy')
        self.assertEqual(self.j.get(row['id'])['status'],'UNKNOWN')
        self.assertEqual(self.j.get(row['id'])['tx_hash'],'0x'+'f'*64)

    def test_evm_revert_is_not_success(self):
        x=self.evm();row=x.prepare(self.ks,B,'0.01','0.005')
        self.j.transition(row['id'],('PREPARED',),'BROADCASTING',tx_hash='0x'+'f'*64)
        self.web.eth.receipt={'status':0,'blockHash':bytes.fromhex('a'*64),'blockNumber':100}
        self.assertEqual(x.reconcile(row['id'])['status'],'REVERTED')
