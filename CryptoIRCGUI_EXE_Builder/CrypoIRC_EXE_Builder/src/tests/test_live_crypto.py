from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import live_crypto
from core.transfer import TransferError

class FakeBitcoinRPC:
    calls=[]
    def __init__(self,base_url,cookie_path,wallet=None):
        self.wallet=wallet
    def call(self,method,*args):
        self.calls.append((self.wallet,method,args))
        if method=='getblockchaininfo':return {'chain':'main','initialblockdownload':False,'blocks':950000,'verificationprogress':1.0}
        if method=='listwallets':return ['existing']
        if method=='getwalletinfo':return {'private_keys_enabled':True}
        if method=='createwallet':return {'name':args[0]}
        if method=='gettransaction':return {'confirmations':3,'amount':'0.01'}
        if method=='walletpassphrase':return None
        if method=='walletlock':return None
        if method=='backupwallet':
            Path(args[0]).write_bytes(b'synthetic-backup'+b'0'*200)
            return None
        raise ValueError(method)

class LiveCryptoTests(unittest.TestCase):
    def setUp(self):
        FakeBitcoinRPC.calls=[]
        self.patch=patch.object(live_crypto,'BitcoinRPC',FakeBitcoinRPC);self.patch.start()
    def tearDown(self):self.patch.stop()
    def test_verified_mainnet_wallet_inventory(self):
        result=live_crypto.node_summary('http://127.0.0.1:8332','/tmp/x')
        self.assertEqual(result['height'],950000)
        self.assertEqual(result['wallets'],['existing'])
    def test_create_encrypted_descriptor_wallet(self):
        out=live_crypto.create_encrypted_core_wallet('http://127.0.0.1:8332','/tmp/x','mycore','a'*20)
        self.assertEqual(out['wallet'],'mycore')
        create=[x for x in FakeBitcoinRPC.calls if x[1]=='createwallet']
        self.assertEqual(create[0][2][3],'a'*20)
        self.assertTrue(create[0][2][5])
    def test_no_unsafe_names_or_short_passphrases(self):
        for name in ('../wallet','C:/keys','', '123', 'wallet name'):
            with self.assertRaises(TransferError):live_crypto.create_encrypted_core_wallet('http://127.0.0.1:8332','/tmp/x',name,'a'*16)
        with self.assertRaises(TransferError):live_crypto.create_encrypted_core_wallet('http://127.0.0.1:8332','/tmp/x','new','short')
    def test_mainnet_only(self):
        class TestNet(FakeBitcoinRPC):
            def call(self,method,*args):
                if method=='getblockchaininfo':return {'chain':'test','blocks':10}
                return super().call(method,*args)
        with patch.object(live_crypto,'BitcoinRPC',TestNet):
            with self.assertRaises(TransferError):live_crypto.node_summary('http://127.0.0.1:8332','/tmp/x')
    def test_backup_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'corewallet.dat'
            path=live_crypto.backup_core_wallet('http://127.0.0.1:8332','/tmp/x','existing',str(target))
            self.assertEqual(path,target);self.assertTrue(path.is_file())
            with self.assertRaises(TransferError):live_crypto.backup_core_wallet('http://127.0.0.1:8332','/tmp/x','existing',str(target))
    def test_transaction_status(self):
        r=live_crypto.wallet_transaction_status('http://127.0.0.1:8332','/tmp/x','existing','a'*64)
        self.assertEqual(r['status'],'CONFIRMED')
    def test_temporary_unlock(self):
        self.assertTrue(live_crypto.wallet_unlock_temporarily('http://127.0.0.1:8332','/tmp/x','existing','passphrase'))
        self.assertEqual(FakeBitcoinRPC.calls[-1][1],'walletpassphrase')

class BitcoinSigningLockTests(unittest.TestCase):
    def test_encrypted_core_wallet_is_locked_after_broadcast_attempt(self):
        from unittest.mock import patch
        import backend
        from decimal import Decimal
        calls=[]
        class FakeRPC:
            def __init__(self,*a,**k):pass
            def call(self,method,*params):
                calls.append(method)
                if method=='walletprocesspsbt':return {'psbt':'signed'}
                if method=='finalizepsbt':return {'complete':True,'hex':'deadbeef'}
                if method=='decoderawtransaction':return {'vout':[]}
                if method=='testmempoolaccept':return [{'allowed':True}]
                if method=='sendrawtransaction':return 'a'*64
                if method=='walletlock':return None
                raise ValueError(method)
        plan=backend.SendPlan('btc','BTC','Bitcoin mainnet','wallet','bc1x',Decimal('0.01'),Decimal('0.00001'),'BTC','',
                              {'url':'http://127.0.0.1:8332','cookie':'/tmp/no','wallet':'wallet','psbt':'unsigned','outputs':[]})
        with patch.object(backend.tx,'BitcoinRPC',FakeRPC),\
             patch('live_crypto.wallet_unlock_temporarily',return_value=True),\
             patch.object(backend.tx,'verify_bitcoin_outputs',return_value=[]):
            self.assertEqual(backend.commit_btc(plan,'this-is-test-only'),'a'*64)
        self.assertEqual(calls[-1],'walletlock')

    def test_encrypted_core_wallet_is_locked_even_after_failure(self):
        from unittest.mock import patch
        import backend
        from decimal import Decimal
        calls=[]
        class FakeRPC:
            def __init__(self,*a,**k):pass
            def call(self,method,*params):
                calls.append(method)
                if method=='walletprocesspsbt':raise ValueError('simulated signing error')
                if method=='walletlock':return None
        plan=backend.SendPlan('btc','BTC','Bitcoin mainnet','wallet','bc1x',Decimal('0.01'),Decimal('0.00001'),'BTC','',
                              {'url':'http://127.0.0.1:8332','cookie':'/tmp/no','wallet':'wallet','psbt':'unsigned','outputs':[]})
        with patch.object(backend.tx,'BitcoinRPC',FakeRPC),\
             patch('live_crypto.wallet_unlock_temporarily',return_value=True):
            with self.assertRaises(ValueError):backend.commit_btc(plan,'test-passphrase')
        self.assertEqual(calls[-1],'walletlock')
