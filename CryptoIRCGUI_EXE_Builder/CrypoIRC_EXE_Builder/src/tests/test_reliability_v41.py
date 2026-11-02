"""Phase 14 deterministic operational reliability tests. No wallet/financial secrets."""
import json
import sqlite3
from contextlib import closing
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reliability_runtime import ReliabilityQueue, ReliabilityError, MAX_ATTEMPTS

class ReliabilityPhase14Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='nocturne_rel41_')
        self.addCleanup(t.cleanup)
        self.folder=Path(t.name)
        self.journal=self.folder/'operations.sqlite3'
        self.r=ReliabilityQueue(self.journal,observation_dir=self.folder)

    def test_no_arbitrary_tasks_and_no_payloads(self):
        for name in ('send_btc','broadcast_tx','payout','wallet_unlock','execute_sql'):
            with self.subTest(name=name),self.assertRaises(ReliabilityError):self.r.enqueue(name)
        jobs=self.r.stats()['recent']
        self.assertEqual(jobs,[])

    def test_first_job_and_coalesced_duplicate(self):
        one,created=self.r.enqueue('database_integrity',now=100)
        two,created2=self.r.enqueue('database_integrity',now=100)
        self.assertTrue(created)
        self.assertFalse(created2)
        self.assertEqual(one,two)
        self.assertEqual(self.r.stats()['counts']['queued'],1)

    def test_atomic_concurrent_claim_single_owner(self):
        self.r.enqueue('database_integrity',now=100)
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims=list(pool.map(lambda _:self.r.claim(now=100),range(16)))
        claimed=[x for x in claims if x is not None]
        self.assertEqual(len(claimed),1)
        self.assertEqual(self.r.stats()['counts']['leased'],1)

    def test_stale_lease_recovers_after_restart_not_before(self):
        jid,_=self.r.enqueue('transaction_review',now=100)
        lease=self.r.claim(now=100,lease_seconds=10)
        self.assertIsNone(ReliabilityQueue(self.journal,observation_dir=self.folder).claim(now=109))
        reopened=ReliabilityQueue(self.journal,observation_dir=self.folder)
        successor=reopened.claim(now=110)
        self.assertEqual(successor['id'],jid)
        self.assertNotEqual(successor['lease_token'],lease['lease_token'])
        with self.assertRaises(ReliabilityError):self.r.complete(lease,'ok',now=111)
        reopened.complete(successor,'no_transaction_data',now=111)
        self.assertEqual(reopened.stats()['counts']['done'],1)

    def test_backoff_dead_letter_and_no_forged_completion(self):
        self.r.enqueue('database_integrity',now=100)
        for attempt in range(1,MAX_ATTEMPTS+1):
            lease=self.r.claim(now=100+attempt*100)
            self.assertIsNotNone(lease)
            with self.assertRaises(ReliabilityError):
                self.r.complete({**lease,'lease_token':'forged'},'ok',now=100+attempt*100)
            state=self.r.fail(lease,now=100+attempt*100)
        self.assertEqual(state,'dead')
        self.assertEqual(self.r.stats()['counts']['dead'],1)
        self.assertIsNone(self.r.claim(now=999))

    def test_automatic_dead_letter_when_expired_last_lease(self):
        self.r.enqueue('database_integrity',now=100)
        for i in range(MAX_ATTEMPTS):
            lease=self.r.claim(now=100+100*i,lease_seconds=5)
            self.assertIsNotNone(lease)
        self.assertIsNone(self.r.claim(now=100+100*MAX_ATTEMPTS))
        self.assertEqual(self.r.stats()['counts']['dead'],1)

    def test_integrity_and_diagnostics_are_read_only(self):
        result=self.r.integrity_scan()
        self.assertEqual(result['operations'],'ok')
        self.assertEqual(result['universal_transactions.sqlite3'],'not_configured')
        self.assertEqual(self.r.transaction_review()['status'],'no_transaction_data')
        self.r.enqueue('database_integrity',now=100)
        done=self.r.run_one(now=100)
        self.assertEqual(done['status'],'ok')
        self.assertEqual(self.r.stats()['counts']['done'],1)

    def test_transaction_review_flags_unknown_without_addresses(self):
        target=self.folder/'universal_transactions.sqlite3'
        with closing(sqlite3.connect(target)) as con:
            con.execute('CREATE TABLE snapshots (data TEXT)')
            con.executemany('INSERT INTO snapshots VALUES(?)',[(json.dumps({'status':s,'address':'secret_address'}),)
                for s in ('CONFIRMED','UNKNOWN','REORG_REVIEW')])
            con.commit()
        self.r.enqueue('transaction_review',now=99)
        status=self.r.run_one(now=99)
        self.assertEqual(status['status'],'attention_required')
        self.assertEqual(status['details']['attention_count'],2)
        self.assertNotIn('secret_address',str(status))
        with closing(sqlite3.connect(self.journal)) as conn:
            self.assertNotIn('secret_address',str(conn.execute('SELECT * FROM jobs').fetchall()))

    def test_corrupt_projection_flags_attention(self):
        (self.folder/'universal_transactions.sqlite3').write_bytes(b'bad database')
        self.assertEqual(self.r.integrity_scan()['universal_transactions.sqlite3'],'unavailable')
        self.r.enqueue('database_integrity',now=100)
        self.assertEqual(self.r.run_one(now=100)['status'],'integrity_failed')

    def test_verified_backup_and_repeated_no_overwrite(self):
        self.r.enqueue('database_integrity',now=100)
        backup=self.folder/'backup'/'jobs.sqlite3';backup.parent.mkdir()
        result=self.r.backup(backup)
        self.assertTrue(result['verified'])
        self.assertEqual(len(result['sha256']),64)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with self.assertRaises(ReliabilityError):self.r.backup(backup)

    def test_no_sneaky_file_or_backup_to_project(self):
        bad=self.folder/'file.txt'
        with self.assertRaises(ReliabilityError):self.r.backup(bad)
        project=Path(__file__).resolve().parents[2]
        with self.assertRaises(ReliabilityError):self.r.backup(project/'should_never_create.sqlite3')
        self.assertFalse((project/'should_never_create.sqlite3').exists())

    def test_operational_data_survives_reopen_without_payloads(self):
        self.r.enqueue('transaction_review',now=100)
        reopened=ReliabilityQueue(self.journal,observation_dir=self.folder)
        self.assertEqual(reopened.stats()['counts']['queued'],1)
        self.assertEqual(reopened.run_one(now=100)['status'],'no_transaction_data')
        again=ReliabilityQueue(self.journal,observation_dir=self.folder)
        self.assertEqual(again.stats()['counts']['done'],1)

    def test_refuse_invalid_symlink_db(self):
        shortcut=self.folder/'shortcut.sqlite3'
        try:shortcut.symlink_to(self.journal)
        except (OSError,NotImplementedError):self.skipTest('symlink unsupported')
        with self.assertRaises(ReliabilityError):ReliabilityQueue(shortcut)

    def test_bad_result_cannot_be_persisted(self):
        self.r.enqueue('database_integrity',now=100)
        lease=self.r.claim(now=100)
        with self.assertRaises(ReliabilityError):self.r.complete(lease,'private key: insecure',now=100)
        self.assertEqual(self.r.stats()['counts']['leased'],1)

if __name__=='__main__':unittest.main()
