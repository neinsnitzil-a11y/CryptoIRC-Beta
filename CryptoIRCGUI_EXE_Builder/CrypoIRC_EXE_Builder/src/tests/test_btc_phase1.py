"""Deterministic BTC Phase 1 safety regression tests (no real funds)."""
from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
from btc_phase1 import BitcoinPhaseOne, BitcoinJournal, NodeConfig, _sat
from core.transfer import TransferError

DEST='bcrt1q'+('p'*38)
CHANGE='bcrt1q'+('c'*38)
TXID='a'*64

class Node:
    chain='regtest'
    confirmations=0
    tx_visible=True
    ambiguous=False
    sends=0
    locked=False
    restored=[]
    mismatch=False
    def __init__(self,*args):
        self.wallet=args[2] if len(args)>2 else None
    def call(self,method,*params):
        if method=='getblockchaininfo':
            return {'chain':self.chain,'initialblockdownload':False,'blocks':125,'headers':125,'verificationprogress':1}
        if method=='listwallets':return ['alice','bob']
        if method=='listwalletdir':return {'wallets':[{'name':'alice'},{'name':'bob'}]}
        if method=='createwallet':return {'name':params[0]}
        if method=='getwalletinfo':return {'private_keys_enabled':True,'external_signer':False,'scanning':False,'descriptors':True}
        if method=='getbalances':return {'mine':{'trusted':Decimal('1.2'),'untrusted_pending':Decimal('0.0'),'immature':Decimal('0')}}
        if method=='getnewaddress':return DEST
        if method=='getaddressinfo':return {'ismine':params[0] in (DEST, CHANGE),'iswatchonly':False}
        if method=='validateaddress':return {'isvalid':params[0] == DEST}
        if method=='walletcreatefundedpsbt':
            self.__class__.locked=bool(params[3].get('lockUnspents'))
            return {'psbt':'PSBT','fee':Decimal('0.00002000')}
        if method=='decodepsbt':return {'tx':self.tx()}
        if method=='walletprocesspsbt':return {'psbt':'SIGNED'}
        if method=='finalizepsbt':return {'complete':True,'hex':'beef'}
        if method=='decoderawtransaction':
            d=self.tx();d['txid']=TXID;return d
        if method=='testmempoolaccept':return [{'allowed':True}]
        if method=='walletpassphrase':return None
        if method=='walletlock':return None
        if method=='lockunspent':self.__class__.locked=False;return True
        if method=='sendrawtransaction':
            self.__class__.sends+=1
            if self.ambiguous: raise TimeoutError('network timeout')
            return TXID
        if method=='gettransaction':
            if not self.tx_visible:raise Exception('transaction not found')
            return {'confirmations':self.confirmations}
        if method=='listreceivedbyaddress':return [{'address':DEST}]
        if method=='restorewallet':
            self.__class__.restored.append(params[0]);return {'name':params[0]}
        if method=='unloadwallet':return {'warnings':[]}
        raise AssertionError(method)
    def tx(self):
        return {'vin':[{'txid':'b'*64,'vout':0}],
                'vout':[{'value':Decimal('0.1'),'scriptPubKey':{'address':DEST}},
                        {'value':Decimal('1.09998'),'scriptPubKey':{'address':CHANGE}}]}

class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal=BitcoinJournal(Path(self.temp.name)/'transactions.sqlite3')
        Node.chain='regtest';Node.confirmations=0;Node.tx_visible=True;Node.ambiguous=False;Node.sends=0;Node.locked=False;Node.restored=[];Node.mismatch=False
        self.s=BitcoinPhaseOne(NodeConfig('http://127.0.0.1:18443','/unused','regtest'),self.journal,Node)
    def prep(self):return self.s.prepare('alice',DEST,'0.10000000','0.00010000')
    def sign(self, ident):return self.s.sign_and_broadcast(ident,'SEND 0.10000000 BTC '+DEST[-8:])

    def test_health_regtest_default_and_sync(self):
        self.assertEqual(self.s.health()['network'],'regtest')
    def test_mainnet_requires_explicit_matching_network(self):
        with self.assertRaises(TransferError):BitcoinPhaseOne(NodeConfig('http://127.0.0.1:8332','/unused','main'),self.journal,Node).health()
        with self.assertRaises(TransferError):NodeConfig('http://127.0.0.1:8332','/unused','test').validate()
    def test_regtest_create_encrypted_descriptor_wallet(self):
        result=self.s.create_encrypted_wallet('nocturne_test','correct-horse-battery-123')
        self.assertEqual(result['wallet'],'nocturne_test')
        self.assertTrue(result['backup_required'])
        with self.assertRaises(TransferError):self.s.create_encrypted_wallet('alice','correct-horse-battery-123')
        with self.assertRaises(TransferError):self.s.create_encrypted_wallet('test','weak')

    def test_addresses_from_core_are_owned(self):
        self.assertEqual(self.s.receiving_address('alice'),DEST)
    def test_prepare_is_durable_and_reserves_utxo(self):
        r=self.prep();self.assertTrue(Node.locked)
        new=BitcoinJournal(self.journal.path)
        self.assertEqual(new.get(r['id'])['amount_sats'],10_000_000)
        self.assertEqual(new.get(r['id'])['status'],'PREPARED')
    def test_concurrent_second_send_blocked(self):
        self.prep()
        with self.assertRaises(TransferError):self.prep()
    def test_cancel_releases_reserved_outpoints(self):
        r=self.prep();self.s.cancel(r['id'])
        self.assertFalse(Node.locked)
        self.assertEqual(self.journal.get(r['id'])['status'],'CANCELLED')
    def test_wrong_authorization_does_not_sign(self):
        r=self.prep()
        with self.assertRaises(TransferError):self.s.sign_and_broadcast(r['id'],'SEND PLEASE')
        self.assertEqual(Node.sends,0)
    def test_sign_broadcast_reconcile_confirmation(self):
        r=self.prep();out=self.sign(r['id'])
        self.assertEqual(out['status'],'PENDING');self.assertEqual(out['txid'],TXID)
        Node.confirmations=2
        got=self.s.reconcile(r['id'])
        self.assertEqual(got['status'],'CONFIRMED');self.assertEqual(got['confirmations'],2)
        self.assertEqual(Node.sends,1)
    def test_double_click_cannot_resend(self):
        r=self.prep();self.sign(r['id'])
        with self.assertRaises(TransferError):self.sign(r['id'])
        self.assertEqual(Node.sends,1)
    def test_timeout_means_unknown_never_retry_automatically(self):
        r=self.prep();Node.ambiguous=True
        out=self.sign(r['id']);self.assertEqual(out['status'],'UNKNOWN');self.assertEqual(Node.sends,1)
        with self.assertRaises(TransferError):self.sign(r['id'])
        Node.tx_visible=False
        self.assertEqual(self.s.reconcile(r['id'])['status'],'UNKNOWN')
        self.assertEqual(Node.sends,1)
    def test_reconnect_after_restart_reconcile(self):
        r=self.prep();Node.ambiguous=True;self.sign(r['id'])
        svc=BitcoinPhaseOne(self.s.cfg,BitcoinJournal(self.journal.path),Node)
        Node.tx_visible=True
        self.assertEqual(svc.reconcile(r['id'])['status'],'PENDING')
    def test_reorg_confirmation_rolls_back(self):
        r=self.prep();self.sign(r['id']);Node.confirmations=3
        self.s.reconcile(r['id']);Node.confirmations=0
        self.assertEqual(self.s.reconcile(r['id'])['status'],'PENDING')
    def test_node_conflict(self):
        r=self.prep();self.sign(r['id']);Node.confirmations=-1
        self.assertEqual(self.s.reconcile(r['id'])['status'],'CONFLICTED')
    def test_regtest_restore_only(self):
        out=self.s.restore_test('alice','/tmp/backup.dat')
        self.assertEqual(out['addresses_verified'],1)
        self.assertTrue(out['restored_wallet_name'].startswith('nocturne_restore_'))
        main=BitcoinPhaseOne(NodeConfig('http://127.0.0.1:8332','/unused','main'),self.journal,Node)
        with self.assertRaises(TransferError):main.restore_test('alice','/tmp/backup.dat')
    def test_amount_requires_exact_satoshis(self):
        with self.assertRaises(TransferError):_sat(Decimal('0.000000001'))
    def test_secret_not_in_journal(self):
        r=self.prep();self.s.sign_and_broadcast(r['id'],'SEND 0.10000000 BTC '+DEST[-8:],'test-secret-passphrase')
        blob=self.journal.path.read_bytes()
        self.assertNotIn(b'test-secret-passphrase',blob)
    def test_fee_cap_rejects_and_releases_lock(self):
        with self.assertRaises(TransferError):self.s.prepare('alice',DEST,'0.10000000','0.00000001')
        self.assertFalse(Node.locked)
        self.assertFalse(self.journal.list())

    def test_finalized_output_tamper_blocks_broadcast(self):
        class Tamper(Node):
            def call(self,method,*params):
                if method=='decoderawtransaction':
                    result=super().call(method,*params)
                    result['vout'][0]['value']=Decimal('0.2')
                    return result
                return super().call(method,*params)
        r=self.prep()
        svc=BitcoinPhaseOne(self.s.cfg,self.journal,Tamper)
        with self.assertRaises(TransferError):svc.sign_and_broadcast(r['id'],'SEND 0.10000000 BTC '+DEST[-8:])
        self.assertEqual(Node.sends,0)

    def test_wrong_change_address_rejected_and_utxo_unlocked(self):
        class Evil(Node):
            def call(self,m,*a):
                if m=='getaddressinfo':return {'ismine':False}
                return super().call(m,*a)
        svc=BitcoinPhaseOne(self.s.cfg,self.journal,Evil)
        with self.assertRaises(TransferError):svc.prepare('alice',DEST,'0.1','0.0001')
        self.assertFalse(Node.locked)
    def test_fails_closed_if_node_not_synced(self):
        class Slow(Node):
            def call(self,m,*a):
                if m=='getblockchaininfo':return {'chain':'regtest','initialblockdownload':True,'blocks':10}
                return super().call(m,*a)
        svc=BitcoinPhaseOne(self.s.cfg,self.journal,Slow)
        with self.assertRaises(TransferError):svc.health()

if __name__=='__main__':unittest.main()
