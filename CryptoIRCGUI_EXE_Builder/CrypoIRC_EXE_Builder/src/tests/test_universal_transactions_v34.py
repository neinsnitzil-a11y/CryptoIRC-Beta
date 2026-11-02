"""Phase 8: risk-oriented tests of the cross-chain monitoring projection."""
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

from universal_transactions import (
    UniversalTxJournal, TxSnapshot, ProjectionError, exact_units, display_units,
    snapshot_btc, snapshot_chain, sync_existing,
)
from btc_phase1 import BitcoinJournal
from chain_journal import ChainJournal


class UniversalTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.j=UniversalTxJournal(self.path/'universal.sqlite3')

    def sample(self,**changes):
        data=dict(chain='EVM',network='11155111',backend_id='a'*32,
                  source='0x'+'a'*40,destination='0x'+'b'*40,asset='ETH',
                  amount_units='123456789012345678',decimals=18,
                  max_fee_units='400000000000000',status='UNKNOWN',tx_hash='0x'+'c'*64,
                  confirmations=0)
        data.update(changes)
        return TxSnapshot(**data)

    def test_exact_units_no_float_rounding(self):
        self.assertEqual(exact_units('0.00000001',8),'1')
        self.assertEqual(exact_units(Decimal('0.123456789123456789'),18),'123456789123456789')
        self.assertEqual(display_units('1',8),'0.00000001')
        with self.assertRaises(ProjectionError):exact_units(0.1,8)
        with self.assertRaises(ProjectionError):exact_units('0.000000001',8)
        with self.assertRaises(ProjectionError):exact_units('NaN',18)
        with self.assertRaises(ProjectionError):exact_units('Infinity',18)
        with self.assertRaises(ProjectionError):exact_units('-2',18)
        with self.assertRaises(ProjectionError):exact_units('1',37)

    def test_unknown_never_coerced_to_failure_or_success(self):
        self.assertTrue(self.j.ingest(self.sample()))
        self.assertEqual(self.j.list()[0]['status'],'UNKNOWN')
        self.assertEqual(self.j.summary()['review'],1)
        self.assertEqual(self.j.summary()['confirmed'],0)

    def test_idempotent_reloads(self):
        self.assertTrue(self.j.ingest(self.sample()))
        self.assertFalse(self.j.ingest(self.sample()))
        self.assertEqual(self.j.verify_events()['events'],1)
        j2=UniversalTxJournal(self.j.path)
        self.assertEqual(len(j2.list()),1)
        self.assertFalse(j2.ingest(self.sample()))

    def test_backend_conflicting_payment_fields_rejected(self):
        self.j.ingest(self.sample())
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(destination='0x'+'f'*40))
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(amount_units='200'))
        self.assertEqual(self.j.verify_events()['events'],1)

    def test_transaction_hash_change_must_be_reviewed(self):
        self.j.ingest(self.sample())
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(tx_hash='0x'+'d'*64,status='PENDING'))
        self.assertEqual(self.j.list()[0]['status'],'UNKNOWN')

    def test_confirmation_requires_hash_and_positive_count(self):
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(status='CONFIRMED',tx_hash=''))
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(status='CONFIRMED',confirmations=0))
        self.j.ingest(self.sample(status='CONFIRMED',confirmations=12))
        self.assertEqual(self.j.summary()['confirmed'],1)
        self.j.ingest(self.sample(status='REORG_REVIEW',confirmations=0))
        self.assertEqual(self.j.summary()['confirmed'],0)
        self.assertEqual(self.j.summary()['review'],1)

    def test_terminal_state_cannot_be_casually_reopened(self):
        self.j.ingest(self.sample(status='CANCELLED',tx_hash=''))
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(status='PENDING'))

    def test_local_history_hash_check_detects_tamper(self):
        self.j.ingest(self.sample())
        self.j.ingest(self.sample(status='PENDING'))
        self.assertEqual(self.j.verify_events()['events'],2)
        with closing(sqlite3.connect(self.j.path)) as c:
            c.execute('UPDATE events SET payload=? WHERE serial=1',('{}',))
            c.commit()
        with self.assertRaises(ProjectionError):self.j.verify_events()

    def test_snapshot_projection_detects_tamper(self):
        self.j.ingest(self.sample())
        with closing(sqlite3.connect(self.j.path)) as c:
            c.execute('UPDATE snapshots SET data=?',('{}',))
            c.commit()
        with self.assertRaises(ProjectionError):self.j.verify_events()

    def test_paths_do_not_allow_symlinks(self):
        target=self.path/'legit.sqlite3';target.touch()
        link=self.path/'link.sqlite3'
        try:link.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest('Symlink creation restricted')
        with self.assertRaises(ProjectionError):UniversalTxJournal(link)

    def test_unknown_or_unsupported_chain_rejected(self):
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(chain='SOL'))
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(status='PAID'))
        with self.assertRaises(ProjectionError):self.j.ingest(self.sample(decimals=100))

    def test_btc_adapter_does_not_persist_psbt_or_raw(self):
        btc=BitcoinJournal(self.path/'btc.sqlite3')
        ident=btc.insert('regtest','mywallet','bcrt1qtest',50000,200,'secret-psbt-not-to-export',[['bcrt1qtest','0.0005']])
        btc.update(ident,('PREPARED',),'SIGNED',signed_raw='secret-signed-raw-not-to-export')
        self.j.ingest(snapshot_btc(btc.list()[0]))
        raw=self.j.path.read_bytes()
        self.assertNotIn(b'secret-psbt-not-to-export',raw)
        self.assertNotIn(b'secret-signed-raw-not-to-export',raw)
        self.assertEqual(self.j.list()[0]['amount_units'],'50000')

    def test_xmr_adapter_does_not_store_wallet_payload(self):
        c=ChainJournal(self.path/'chain.sqlite3')
        ident=c.new(chain='XMR',network='stagenet',source='walletaddr',destination='recipient',asset='XMR',
                    amount_units='1000000000000',max_fee_units='10000000000',payload={'hidden':'NO-PERSIST-TO-PROJECTION'})
        c.transition(ident,('PREPARING',),'PREPARED',tx_hash='f'*64)
        self.j.ingest(snapshot_chain(c.get(ident)))
        self.assertNotIn(b'NO-PERSIST-TO-PROJECTION',self.j.path.read_bytes())
        self.assertEqual(self.j.list()[0]['decimals'],12)

    def test_concurrent_ingest_is_idempotent(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            result=list(pool.map(self.j.ingest,[self.sample() for _ in range(25)]))
        self.assertEqual(sum(result),1)
        self.assertEqual(self.j.verify_events()['events'],1)

    def test_two_networks_never_coalesce(self):
        self.j.ingest(self.sample())
        self.j.ingest(self.sample(network='1'))
        self.assertEqual(len(self.j.list()),2)

    def test_sync_from_both_existing_journals_durable(self):
        btc=BitcoinJournal(self.path/'btc.sqlite3')
        ident=btc.insert('regtest','mywallet','bcrt1qtest',25000,300,'psbt',[])
        chain=ChainJournal(self.path/'chain.sqlite3')
        chain.new(chain='EVM',network='11155111',source='0x'+'a'*40,destination='0x'+'b'*40,
                  asset='ETH',amount_units='5',max_fee_units='90',nonce=1)
        result=sync_existing(projection=self.j,btc=btc,chains=chain)
        self.assertEqual(result['imported'],2)
        self.assertEqual(len(result['rows']),2)
        again=sync_existing(projection=self.j,btc=btc,chains=chain)
        self.assertEqual(again['imported'],0)
        self.assertEqual(again['integrity']['events'],2)
        btc.update(ident,('PREPARED',),'BROADCASTING',txid='e'*64)
        result=sync_existing(projection=self.j,btc=btc,chains=chain)
        self.assertEqual(result['imported'],1)
        self.assertEqual(self.j.verify_events()['events'],3)

    def test_bad_source_row_reports_warning_but_keeps_valid_rows(self):
        btc=BitcoinJournal(self.path/'btc.sqlite3')
        btc.insert('regtest','w','dest',100,0,'psbt',[])
        chain=ChainJournal(self.path/'chain.sqlite3')
        fake=type('Fake',(),{'list':lambda self,limit=100:[{'chain':'SOL'}]})()
        result=sync_existing(projection=self.j,btc=btc,chains=fake)
        self.assertEqual(result['imported'],1)
        self.assertEqual(len(result['errors']),1)

if __name__=='__main__':unittest.main()
