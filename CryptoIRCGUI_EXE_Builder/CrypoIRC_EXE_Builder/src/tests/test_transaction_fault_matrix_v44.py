"""Phase 17 transaction-level regression matrix. All simulated; no live funds."""
import copy
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from btc_phase1 import BitcoinPhaseOne,BitcoinJournal,NodeConfig
from chain_journal import ChainJournal
from evm_phase2 import EVMPhaseTwo
from xmr_phase3 import MoneroPhaseThree
from universal_transactions import UniversalTxJournal,TxSnapshot,ProjectionError
from core.transfer import TransferError
from qa_runtime import QAError,assess,validate_report,export_report
from test_btc_phase1 import Node,DEST,TXID
from test_phase23 import FakeWeb3,FakeMonero,A,B,X


class PaymentFaultMatrix(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='v44-qa-')
        self.addCleanup(temp.cleanup)
        self.work=Path(temp.name)
        Node.chain='regtest';Node.ambiguous=False;Node.sends=0;Node.confirmations=0;Node.tx_visible=True;Node.locked=False

    def _btc(self):
        db=self.work/'btc.sqlite3'
        cfg=NodeConfig('http://127.0.0.1:18443','/unused','regtest')
        return BitcoinPhaseOne(cfg,BitcoinJournal(db),Node)

    def test_btc_broadcast_timeout_recovered_after_restart_without_resending(self):
        service=self._btc()
        tx=service.prepare('alice',DEST,'0.10000000','0.00010000')
        Node.ambiguous=True
        result=service.sign_and_broadcast(tx['id'],'SEND 0.10000000 BTC '+DEST[-8:])
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(Node.sends,1)
        recovered=self._btc()
        self.assertEqual(recovered.journal.get(tx['id'])['status'],'UNKNOWN')
        with self.assertRaises(TransferError):recovered.sign_and_broadcast(tx['id'],'SEND 0.10000000 BTC '+DEST[-8:])
        self.assertEqual(Node.sends,1)
        Node.ambiguous=False;Node.confirmations=2
        self.assertEqual(recovered.reconcile(tx['id'])['status'],'CONFIRMED')

    def test_btc_double_click_and_second_intent_blocked(self):
        service=self._btc();tx=service.prepare('alice',DEST,'0.1','0.0001')
        with self.assertRaises(TransferError):service.prepare('alice',DEST,'0.1','0.0001')
        service.sign_and_broadcast(tx['id'],'SEND 0.10000000 BTC '+DEST[-8:])
        with self.assertRaises(TransferError):service.sign_and_broadcast(tx['id'],'SEND 0.10000000 BTC '+DEST[-8:])
        self.assertEqual(Node.sends,1)

    def test_btc_confirmation_reorg_and_conflict_are_not_final_success(self):
        service=self._btc();tx=service.prepare('alice',DEST,'0.1','0.0001')
        service.sign_and_broadcast(tx['id'],'SEND 0.10000000 BTC '+DEST[-8:])
        Node.confirmations=8
        self.assertEqual(service.reconcile(tx['id'])['status'],'CONFIRMED')
        Node.confirmations=0
        self.assertEqual(service.reconcile(tx['id'])['status'],'PENDING')
        Node.confirmations=-1
        self.assertEqual(service.reconcile(tx['id'])['status'],'CONFLICTED')

    def test_btc_wrong_node_network_is_rejected(self):
        Node.chain='main'
        with self.assertRaises(TransferError):self._btc().health()

    def _evm(self):
        chain=ChainJournal(self.work/'chain.sqlite3')
        ks=self.work/'wallet.json'
        ks.write_text(json.dumps({'address':A[2:],'crypto':{'ciphertext':'dummy'}}))
        network=FakeWeb3()
        return EVMPhaseTwo('SEPOLIA','https://rpc.example.invalid',chain,network),ks,network

    def test_evm_nonce_reserved_across_new_service_instances(self):
        service,ks,network=self._evm()
        tx=service.prepare(ks,B,'0.001','0.002')
        reloaded=EVMPhaseTwo('SEPOLIA','https://rpc.example.invalid',ChainJournal(self.work/'chain.sqlite3'),network)
        with self.assertRaises(TransferError):reloaded.prepare(ks,B,'0.001','0.002')
        self.assertEqual(reloaded.journal.get(tx['id'])['nonce'],4)

    def test_evm_wrong_chain_and_reverted_receipt(self):
        service,ks,network=self._evm()
        tx=service.prepare(ks,B,'0.001','0.002')
        service.journal.transition(tx['id'],('PREPARED',),'BROADCASTING',tx_hash='0x'+'e'*64)
        service.journal.transition(tx['id'],('BROADCASTING',),'PENDING')
        network.eth.chain_id=1
        with self.assertRaises(TransferError):service.reconcile(tx['id'])
        network.eth.chain_id=11155111
        network.eth.receipt={'status':0,'blockHash':bytes.fromhex('f'*64),'blockNumber':99,'logs':[]}
        self.assertEqual(service.reconcile(tx['id'])['status'],'REVERTED')

    def test_evm_unknown_receipt_is_not_falsely_confirmed(self):
        service,ks,network=self._evm()
        tx=service.prepare(ks,B,'0.001','0.002')
        service.journal.transition(tx['id'],('PREPARED',),'BROADCASTING',tx_hash='0x'+'e'*64)
        service.journal.transition(tx['id'],('BROADCASTING',),'UNKNOWN')
        self.assertEqual(service.reconcile(tx['id'])['status'],'UNKNOWN')
        self.assertEqual(ChainJournal(self.work/'chain.sqlite3').get(tx['id'])['status'],'UNKNOWN')

    def test_monero_restart_never_relays_prepared_transaction(self):
        journal=ChainJournal(self.work/'chain.sqlite3');rpc=FakeMonero()
        service=MoneroPhaseThree('http://127.0.0.1:18082','test','secret',journal,rpc)
        tx=service.prepare(X,'1','0.05')
        recovered=MoneroPhaseThree('http://127.0.0.1:18082','test','secret',ChainJournal(journal.path),rpc)
        with self.assertRaises(TransferError):recovered.relay(tx['id'],'SEND 1 XMR '+X[-8:])
        self.assertEqual(rpc.relay_count,0)
        self.assertEqual(recovered.journal.get(tx['id'])['status'],'UNSPENDABLE')
        self.assertNotIn(b'abcdef123456',journal.path.read_bytes())

    def test_monero_outgoing_history_mismatch_requires_review(self):
        journal=ChainJournal(self.work/'chain.sqlite3');rpc=FakeMonero()
        service=MoneroPhaseThree('http://127.0.0.1:18082','test','secret',journal,rpc)
        tx=service.prepare(X,'1','0.05')
        service.relay(tx['id'],'SEND 1 XMR '+X[-8:])
        original=rpc.call
        def mismatch(method,arg=None):
            if method=='get_transfer_by_txid':
                return {'transfer':{'txid':'f'*64,'type':'out','amount':42,'confirmations':100}}
            return original(method,arg)
        rpc.call=mismatch
        self.assertEqual(service.reconcile(tx['id'])['status'],'REQUIRES_REVIEW')

    def test_universal_journal_detects_locally_modified_transaction(self):
        projected=UniversalTxJournal(self.work/'universal.sqlite3')
        tx=TxSnapshot(chain='EVM',network='11155111',backend_id='a'*32,
                      source=A,destination=B,asset='ETH',amount_units='1000',decimals=18,
                      max_fee_units='2000',status='UNKNOWN',tx_hash='0x'+'f'*64,
                      confirmations=0)
        projected.ingest(tx)
        with closing(sqlite3.connect(projected.path)) as db:
            db.execute("UPDATE snapshots SET data='{}'")
            db.commit()
        with self.assertRaises(ProjectionError):projected.verify_events()


class QAReleaseGates(unittest.TestCase):
    def test_absent_evidence_cannot_create_production_approval(self):
        source=Path(__file__).resolve().parents[1]
        report=assess(source=source,run_tests=False)
        self.assertFalse(report['production_ready'])
        self.assertEqual(report['release_status'],'BLOCKED')
        self.assertEqual(report['summary']['PASS_LOCAL'],1)
        self.assertTrue(all(g['status']=='BLOCKED_EXTERNAL' for g in report['gates'] if g['kind']=='external'))
        self.assertTrue(validate_report(report))

    def test_source_and_real_money_not_equated(self):
        report=assess(source=Path(__file__).resolve().parents[1],run_tests=False)
        self.assertEqual(next(g for g in report['gates'] if g['id']=='BTC_REGTEST')['status'],'NOT_RUN')
        self.assertEqual(next(g for g in report['gates'] if g['id']=='BTC_MAINNET')['status'],'BLOCKED_EXTERNAL')
        self.assertEqual(report['independently_certified_assets'],0)

    def test_external_attestation_cannot_be_forged_with_local_report(self):
        report=assess(source=Path(__file__).resolve().parents[1],run_tests=False)
        fake=copy.deepcopy(report)
        target=next(g for g in fake['gates'] if g['id']=='CRYPTO_AUDIT')
        target['status']='PASS_LOCAL'
        with self.assertRaises(QAError):validate_report(fake)

    def test_report_hash_is_not_signature_and_tamper_detected(self):
        report=assess(source=Path(__file__).resolve().parents[1],run_tests=False)
        report['tests']['regression']['total']=999
        with self.assertRaises(QAError):validate_report(report)

    def test_export_refuses_writing_into_release_project(self):
        report=assess(source=Path(__file__).resolve().parents[1],run_tests=False)
        project_root=Path(__file__).resolve().parents[2]
        with self.assertRaises(QAError):
            export_report(report,project_root/'accidental-qa-evidence.json')
        self.assertFalse((project_root/'accidental-qa-evidence.json').exists())

    def test_export_never_overwrites_and_does_not_store_private_material(self):
        report=assess(source=Path(__file__).resolve().parents[1],run_tests=False)
        with tempfile.TemporaryDirectory() as scratch:
            output=Path(scratch)/'qa.json'
            export_report(report,output)
            data=json.loads(output.read_text())
            self.assertTrue(validate_report(data))
            self.assertNotIn('private_key',output.read_text().lower())
            with self.assertRaises(QAError):export_report(report,output)
