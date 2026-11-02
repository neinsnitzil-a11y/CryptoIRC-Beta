"""Offline validation of BTC vault-backed path. Node signing is mocked, not live tested."""
from decimal import Decimal
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bitcoin_vault as btc
import vaultforge
import transfer_engine as te

TXID = 'a' * 64
ADDR = 'bc1qfrom11111111111111111111111111111111111111111'
TO = 'bc1qto2222222222222222222222222222222222222222'
SCRIPT = '0014' + 'fe' * 20
IDENTITY = btc.Identity(ADDR, SCRIPT, 'fakeWIFneverLogged', 'main')
UTXO = {'txid': TXID, 'vout': 1, 'sats': 200_000, 'scriptPubKey': SCRIPT, 'confirmations': 5}
INFO = {'chain':'main','blocks':1000,'headers':1000,'verificationprogress':0.999999,'initialblockdownload':False}

class MockNode:
    def __init__(self, *, evil=False, changed_fee=False, reject=False):
        self.events=[]
        self.evil=evil
        self.changed_fee=changed_fee
        self.reject=reject
        self.broadcast=False
    def call(self, name, *args):
        self.events.append((name, args))
        if name == 'getblockchaininfo': return INFO
        if name == 'scantxoutset':
            return {'success':True,'height':1000,'unspents':[dict(UTXO, amount='0.00200000', height=996)]}
        if name == 'gettxout':
            return {'value':'0.00200000','scriptPubKey': {'hex':SCRIPT}, 'confirmations':5}
        if name == 'validateaddress': return {'isvalid': True}
        if name == 'estimatesmartfee': return {'feerate':'0.00010000'}  # 10 sats/vB
        if name == 'createrawtransaction': return 'unsigned'
        if name == 'decoderawtransaction':
            signed = args[0] == 'signed'
            plan=self.plan
            outs=[{'value':str(btc.sat_to_btc(plan['amount_sat'])), 'scriptPubKey':{'address':('bc1qEVIL' if self.evil and signed else TO)}}]
            if plan['change_sat']:
                outs.append({'value':str(btc.sat_to_btc(plan['change_sat'])), 'scriptPubKey': {'address':ADDR}})
            vin=[{'txid':TXID,'vout':1,'sequence':0xfffffffd,'scriptSig': {'hex':''}}]
            if signed: vin[0]['txinwitness']=['sig', 'pub']
            return {'version':2,'locktime':0,'txid':'b'*64, 'vin':vin,'vout':outs}
        if name == 'signrawtransactionwithkey': return {'complete':True,'hex':'signed'}
        if name == 'testmempoolaccept':
            if self.reject: return [{'allowed':False,'reject-reason':'bad-txns-inputs-missingorspent'}]
            fee=self.plan['fee_sat'] + (1 if self.changed_fee else 0)
            return [{'allowed':True,'vsize':180,'fees':{'base':str(btc.sat_to_btc(fee))}}]
        if name == 'sendrawtransaction':
            self.broadcast=True
            return 'b'*64
        raise AssertionError(name)

class VaultBtcTests(unittest.TestCase):
    def test_menu_btc_is_integrated(self):
        with patch('builtins.input', return_value='0'), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(vaultforge.main([]), 0)
        self.assertIn('Show BTC receiving address', out.getvalue())
        self.assertIn('SPEND BTC — Send from SAME encrypted vault', out.getvalue())

    def test_wrong_chain_fails_closed(self):
        node = MockNode()
        with self.assertRaisesRegex(te.TransferError,'Wrong Bitcoin network'):
            btc.check_node(type('Bad', (), {'call':lambda self, _:dict(INFO,chain='signet')})(), 'main')

    def test_scanned_ownership_and_confirmed_only(self):
        node=MockNode()
        us, height = btc.scan_utxos(node, IDENTITY)
        self.assertEqual(us[0]['sats'], 200_000)
        self.assertEqual(height, 1000)
        node.call=lambda name,*args: {'success':True,'height':1000,'unspents':[dict(UTXO,scriptPubKey='00',amount='0.002')] } if name=='scantxoutset' else (INFO if name=='getblockchaininfo' else None)
        with self.assertRaisesRegex(te.TransferError,'does not belong'):
            btc.scan_utxos(node, IDENTITY)

    def test_mempool_spent_utxo_filtered(self):
        node=MockNode()
        orig=node.call
        node.call=lambda name,*args: None if name=='gettxout' else orig(name,*args)
        self.assertEqual(btc.scan_utxos(node, IDENTITY)[0], [])

    def test_fees_and_satoshi_precision(self):
        self.assertEqual(btc.btc_to_sat('0.00000001'),1)
        with self.assertRaises(te.TransferError):btc.btc_to_sat('0.000000001')
        plan=btc.build_payment_plan([UTXO], 100_000, Decimal('10'), 20_000)
        self.assertEqual(plan['total_sat'], 200_000)
        self.assertEqual(plan['fee_sat']+plan['change_sat']+100_000,200_000)
        with self.assertRaisesRegex(te.TransferError,'exceeds your limit'):
            btc.build_payment_plan([UTXO], 100_000, Decimal('10'), 1)
        with self.assertRaisesRegex(te.TransferError,'Fee rate'):
            btc.build_payment_plan([UTXO], 100_000, Decimal('501'), 20_000)
        with self.assertRaisesRegex(te.TransferError,'Insufficient'):
            btc.build_payment_plan([UTXO], 2_000_000, Decimal('10'), 20_000)

    def _send(self, responses, *, evil=False, changed_fee=False, reject=False):
        node=MockNode(evil=evil,changed_fee=changed_fee,reject=reject)
        plan=btc.build_payment_plan([UTXO], 100_000, Decimal('10'), 50_000)
        node.plan=plan
        payload={'format':'VaultForge-Unlocked-v1','wallets':[{'coin':'BTC'}],'groups':[]}
        # prompt chain / network mainnet consent / destination / amount / fee cap / rate / PREPARE / SEND / BROADCAST
        inputs=iter(responses)
        with patch('bitcoin_vault.bridge.unlock_selected',return_value=(Path('vault.vault'),payload)),\
             patch('bitcoin_vault.require_btc_entry',return_value=payload['wallets'][0]),\
             patch('bitcoin_vault.derive_identity',return_value=IDENTITY),\
             patch('bitcoin_vault.get_rpc',return_value=node),\
             patch('bitcoin_vault.scan_utxos',return_value=([UTXO],1000)),\
             patch('builtins.input',side_effect=lambda label='':next(inputs)),\
             redirect_stdout(io.StringIO()):
            btc.bitcoin_send()
        return node

    def _answers(self, final='BROADCAST'):
        return ['main','MAINNET',TO,'0.001','0.0005','10','PREPARE',f'SEND 0.001 BTC {TO[-8:]}',final]

    def test_no_mainnet_authorization_no_sign(self):
        node=self._send(['main','NO'])
        self.assertFalse(node.broadcast)
        self.assertEqual(node.events,[])

    def test_no_prepare_no_sign(self):
        a=self._answers(); a[6]='NO'
        node=self._send(a)
        self.assertFalse(node.broadcast)
        self.assertFalse(any(name=='signrawtransactionwithkey' for name,_ in node.events))

    def test_no_send_authorization_no_sign(self):
        a=self._answers(); a[7]='NO'
        node=self._send(a)
        self.assertFalse(node.broadcast)
        self.assertFalse(any(name=='signrawtransactionwithkey' for name,_ in node.events))

    def test_signed_output_tampered_blocks_broadcast(self):
        with self.assertRaisesRegex(te.TransferError,'Unexpected'):
            self._send(self._answers(), evil=True)

    def test_node_fee_discrepancy_blocks_broadcast(self):
        with self.assertRaisesRegex(te.TransferError,'unexpected fee'):
            self._send(self._answers(), changed_fee=True)

    def test_mempool_rejection_blocks_broadcast(self):
        with self.assertRaisesRegex(te.TransferError,'rejected'):
            self._send(self._answers(), reject=True)

    def test_cancel_at_final_broadcast(self):
        node=self._send(self._answers('CANCEL'))
        self.assertFalse(node.broadcast)
        self.assertTrue(any(name=='signrawtransactionwithkey' for name,_ in node.events))

    def test_receive_does_not_request_signing_key(self):
        payload={'format':'VaultForge-Unlocked-v1','wallets':[{'coin':'BTC'}],'groups':[]}
        calls=[]
        def fake_derive(payload, entry, chain, *, signing=False):
            calls.append((chain, signing))
            return IDENTITY
        with patch('bitcoin_vault.bridge.unlock_selected',return_value=(Path('vault.vault'),payload)), \
             patch('bitcoin_vault.require_btc_entry',return_value=payload['wallets'][0]), \
             patch('bitcoin_vault.derive_identity',side_effect=fake_derive), \
             redirect_stdout(io.StringIO()):
            btc.bitcoin_receive()
        self.assertEqual(calls,[('main',False)])

    def test_send_requests_derived_signing_key(self):
        node=MockNode()
        payload={'format':'VaultForge-Unlocked-v1','wallets':[{'coin':'BTC'}],'groups':[]}
        calls=[]
        def fake_derive(payload, entry, chain, *, signing=False):
            calls.append((chain, signing))
            return IDENTITY
        with patch('bitcoin_vault.bridge.unlock_selected',return_value=(Path('vault.vault'),payload)), \
             patch('bitcoin_vault.require_btc_entry',return_value=payload['wallets'][0]), \
             patch('bitcoin_vault.derive_identity',side_effect=fake_derive), \
             patch('builtins.input',side_effect=['main','NO']), redirect_stdout(io.StringIO()):
            btc.bitcoin_send()
        self.assertEqual(calls,[('main',False)])

    def test_immature_coinbase_is_not_spendable(self):
        node=MockNode()
        orig=node.call
        node.call=lambda name,*args: dict(orig(name,*args),coinbase=True,confirmations=75) if name=='gettxout' else orig(name,*args)
        self.assertEqual(btc.scan_utxos(node,IDENTITY)[0],[])

    def test_wallet_rpc_disables_environment_proxy(self):
        import transfer_engine as transfer
        import tempfile
        from urllib.request import ProxyHandler
        with tempfile.TemporaryDirectory() as tmp:
            cookie=Path(tmp)/'.cookie'
            cookie.write_text('__cookie__:example',encoding='utf-8')
            with patch('transfer_engine.build_opener') as opener:
                transfer.BitcoinRPC('http://127.0.0.1:8332', cookie)
            handlers=opener.call_args.args
            self.assertTrue(isinstance(handlers[0],ProxyHandler))
            self.assertEqual(handlers[0].proxies,{})

    def test_mock_success_path_broadcasts_only_after_checks(self):
        node=self._send(self._answers())
        self.assertTrue(node.broadcast)
        names=[name for name,args in node.events]
        self.assertLess(names.index('createrawtransaction'), names.index('signrawtransactionwithkey'))
        self.assertLess(names.index('signrawtransactionwithkey'), names.index('testmempoolaccept'))
        self.assertLess(names.index('testmempoolaccept'), names.index('sendrawtransaction'))
        signing=[args for name,args in node.events if name=='signrawtransactionwithkey'][0]
        self.assertEqual(signing[1], ['fakeWIFneverLogged'])

if __name__=='__main__': unittest.main()
