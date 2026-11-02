"""No real payments, personal credentials, or blockchain keys in these tests."""
import tempfile
import unittest
import time
from pathlib import Path

from financial_backend.ledger import SandboxLedger, FinanceError
from financial_backend.events import handle_test_event, sign_test_event
from financial_backend.operations import SandboxOperations, MAX_ATTEMPTS
from financial_backend.backup import create_backup, verify_backup, restore_to_new_database
from security_gates import release_status


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.ledger=SandboxLedger(self.base/'sandbox.sqlite3')
        self.ops=SandboxOperations(self.ledger,{
            'maker_one':'reconciler','checker_two':'reviewer','audit_three':'auditor',
            'nobody_user':'guest'})
        self.intent=self.ledger.create_intent(customer_id='customer_test',provider='sandbox-stripe',
            provider_ref='provider_ref_123456',currency='USD',amount='12.34',
            idempotency_key='idem_repeat_key_123456')
    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def settle(self):
        body={'provider':'sandbox-stripe','event_id':'event_settlement_one','intent_id':self.intent['id'],
              'provider_ref':'provider_ref_123456','currency':'USD','minor':1234,'status':'settled'}
        stamp=int(time.time());secret=b'only-sandbox-hmac-secret-long-enough'
        handle_test_event(self.ledger,body,sign_test_event(secret,body,stamp),secret,stamp)
        return body

    def test_outbox_atomic_with_initial_intent(self):
        entries=self.ledger.db.execute('SELECT * FROM outbox').fetchall()
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]['event_type'],'intent.created')
        self.assertEqual(self.ops.queue_summary()['pending'],1)

    def test_failed_intent_does_not_enqueue(self):
        before=self.ops.queue_summary()['pending']
        with self.assertRaises(FinanceError):
            self.ledger.create_intent(customer_id='bad#id',provider='sandbox-stripe',
                provider_ref='provider_ref_234567',currency='USD',amount='1',idempotency_key='idem_key_123456')
        self.assertEqual(self.ops.queue_summary()['pending'],before)

    def test_idempotency_no_duplicate_outbox(self):
        self.ledger.create_intent(customer_id='customer_test',provider='sandbox-stripe',
            provider_ref='provider_ref_123456',currency='USD',amount='12.34',
            idempotency_key='idem_repeat_key_123456')
        self.assertEqual(self.ops.queue_summary()['pending'],1)

    def test_settlement_outbox_and_balanced_journal(self):
        self.settle()
        self.assertEqual(self.ops.queue_summary()['pending'],2)
        self.assertEqual(self.ledger.customer_balance('customer_test','USD'),1234)
        self.assertEqual(self.ledger.verify_integrity(),[])

    def test_claim_and_ack_and_lease_token(self):
        work=self.ops.claim_outbox('worker_one',now=int(time.time()),lease_seconds=10)
        self.assertEqual(work['attempts'],1)
        self.assertNotIn('customer',str(work['payload']))
        with self.assertRaises(FinanceError):self.ops.acknowledge_delivery(work['id'],'badtoken')
        self.assertEqual(self.ops.acknowledge_delivery(work['id'],work['lease_token']),'delivered')
        self.assertIsNone(self.ops.claim_outbox('worker_one'))

    def test_concurrent_claim_does_not_duplicate(self):
        w1=self.ops.claim_outbox('worker_one',lease_seconds=20)
        w2=self.ops.claim_outbox('worker_two',lease_seconds=20)
        self.assertIsNotNone(w1)
        self.assertIsNone(w2)

    def test_expired_lease_redelivery(self):
        t=int(time.time())
        w1=self.ops.claim_outbox('worker_one',now=t,lease_seconds=5)
        w2=self.ops.claim_outbox('worker_two',now=t+6,lease_seconds=5)
        self.assertEqual(w1['id'],w2['id'])
        with self.assertRaises(FinanceError):self.ops.acknowledge_delivery(w1['id'],w1['lease_token'],now=t+6)
        self.assertEqual(self.ops.acknowledge_delivery(w2['id'],w2['lease_token'],now=t+7),'delivered')

    def test_retry_dead_letter_does_not_change_balance(self):
        t=int(time.time())
        for i in range(MAX_ATTEMPTS):
            w=self.ops.claim_outbox('worker_one',now=t,lease_seconds=5)
            self.assertIsNotNone(w)
            status=self.ops.record_delivery_failure(w['id'],w['lease_token'],now=t+1)
            t+=100
        self.assertEqual(status,'dead')
        self.assertEqual(self.ops.queue_summary()['dead'],1)
        self.assertIsNone(self.ops.claim_outbox('worker_one',now=t))
        self.assertEqual(self.ledger.customer_balance('customer_test','USD'),0)

    def test_reconciliation_and_idempotent_statement(self):
        records=[{'provider':'sandbox-stripe','provider_ref':'provider_ref_123456',
                  'currency':'USD','minor':1234,'status':'settled'}]
        x=self.ops.record_reconciliation(actor='maker_one',provider='sandbox-stripe',
                statement_id='statement_one',provider_records=records)
        y=self.ops.record_reconciliation(actor='maker_one',provider='sandbox-stripe',
                statement_id='statement_one',provider_records=records)
        self.assertEqual(x['id'],y['id'])
        self.assertEqual(x['exception_count'],1)
        with self.assertRaises(FinanceError):
            self.ops.record_reconciliation(actor='maker_one',provider='sandbox-stripe',
                statement_id='statement_one',provider_records=[{**records[0],'minor':1235}])

    def test_duplicate_provider_records_rejected(self):
        item={'provider':'sandbox-stripe','provider_ref':'provider_ref_123456','currency':'USD','minor':1234,'status':'pending'}
        with self.assertRaises(FinanceError):
            self.ops.record_reconciliation(actor='maker_one',provider='sandbox-stripe',
                statement_id='statement_two',provider_records=[item,item])

    def test_case_maker_checker_and_no_ledger_adjustment(self):
        self.ops.record_reconciliation(actor='maker_one',provider='sandbox-stripe',
            statement_id='statement_three',provider_records=[{'provider':'sandbox-stripe','provider_ref':'provider_ref_123456',
                'currency':'USD','minor':1234,'status':'settled'}])
        case=self.ops.list_exceptions(actor='audit_three')[0]
        with self.assertRaises(FinanceError):
            self.ops.resolve_exception(actor='checker_two',exception_id=case['id'],note='Reviewed and accepted test mismatch')
        self.ops.acknowledge_exception(actor='maker_one',exception_id=case['id'],note='Reviewed provider sandbox statement')
        self.ops.resolve_exception(actor='checker_two',exception_id=case['id'],note='Reviewed independent sandbox evidence')
        self.assertEqual(self.ops.list_exceptions(actor='audit_three',state='resolved')[0]['state'],'resolved')
        self.assertEqual(self.ledger.customer_balance('customer_test','USD'),0)

    def test_role_gate_and_invalid_notes(self):
        with self.assertRaises(FinanceError):
            self.ops.record_reconciliation(actor='nobody_user',provider='sandbox-stripe',
                statement_id='statement_four',provider_records=[])
        with self.assertRaises(FinanceError):self.ops.list_exceptions(actor='nobody_user')
        self.ops.record_reconciliation(actor='maker_one',provider='sandbox-stripe',
                statement_id='statement_five',provider_records=[{'provider':'sandbox-stripe','provider_ref':'missing_ref_123456',
                'currency':'USD','minor':1234,'status':'settled'}])
        case=self.ops.list_exceptions(actor='maker_one')[0]
        with self.assertRaises(FinanceError):
            self.ops.acknowledge_exception(actor='maker_one',exception_id=case['id'],note='ok')

    def test_backup_restore_integrity_and_no_overwrite(self):
        self.settle()
        backup=self.base/'db-backup.bin'
        info=create_backup(self.ledger,backup)
        self.assertEqual(info['encrypted'],False)
        self.assertEqual(verify_backup(backup)['journal_integrity'],'ok')
        restored=self.base/'restored.sqlite3'
        restore_to_new_database(backup,restored)
        with self.assertRaises(FinanceError):restore_to_new_database(backup,restored)
        r=SandboxLedger(restored)
        try:
            self.assertEqual(r.customer_balance('customer_test','USD'),1234)
            self.assertEqual(r.verify_integrity(),[])
        finally:r.close()

    def test_queue_survives_process_reopen(self):
        now=int(time.time())
        first=self.ops.claim_outbox('worker_one',now=now,lease_seconds=5)
        self.ledger.close()
        self.ledger=SandboxLedger(self.base/'sandbox.sqlite3')
        self.ops=SandboxOperations(self.ledger,{'maker_one':'reconciler','checker_two':'reviewer','audit_three':'auditor'})
        second=self.ops.claim_outbox('worker_two',now=now+6,lease_seconds=5)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(self.ops.acknowledge_delivery(second['id'],second['lease_token'],now=now+7),'delivered')
        self.assertFalse(self.ledger.verify_integrity())

    def test_outbox_tamper_detected(self):
        self.ledger.db.execute("UPDATE outbox SET public_payload='{}' WHERE id=1")
        self.assertTrue(any('Outbox' in p for p in self.ledger.verify_integrity()))

    def test_backup_handles_closed_on_windows(self):
        # SQLite's `with connection` only commits/rolls back: it does not close.
        # Windows refuses to delete open temporary SQLite files (WinError 32).
        import sqlite3
        from unittest.mock import patch
        from financial_backend import backup as backup_mod
        real_connect=sqlite3.connect
        opened=[]
        class TrackedConnection(sqlite3.Connection):
            def close(self):
                self._closed_explicitly = True
                super().close()
        def connect(*args, **kwargs):
            kwargs['factory']=TrackedConnection
            conn=real_connect(*args, **kwargs)
            conn._closed_explicitly=False
            opened.append(conn)
            return conn
        dest=self.base/'handle_check.bin'
        with patch.object(backup_mod.sqlite3, 'connect', side_effect=connect):
            create_backup(self.ledger,dest)
            verify_backup(dest)
            restore_to_new_database(dest,self.base/'handle_restored.sqlite3')
        self.assertTrue(opened)
        self.assertTrue(all(conn._closed_explicitly for conn in opened),
                        'Each temporary SQLite connection must explicitly close')

    def test_corrupted_backup_rejected(self):
        b=self.base/'backup.bin';create_backup(self.ledger,b)
        with b.open('ab') as stream:stream.write(b'corrupt')
        with self.assertRaises(FinanceError):verify_backup(b)

    def test_no_live_operations_or_audit_claims(self):
        health=self.ops.health()
        self.assertFalse(health['production_ready'])
        self.assertFalse(health['live_payments_enabled'])
        self.assertTrue(health['journal_integrity_ok'])
        self.assertEqual(release_status()['release'],'BLOCKED')

if __name__=='__main__':unittest.main()
