"""Read-only six-chain adapter regression tests. No funds or real nodes used."""
import hashlib
import unittest
from decimal import Decimal
from unittest.mock import Mock

from chain_expansion import (
    COINS, NETWORKS, Balance, BASE58, RIPPLE58, b58decode, validate_address,
    amount_from_units, safe_rpc_endpoint, read_utxo_balance,
    read_solana, read_tron, read_xrp, read_balance,
)
from core.transfer import TransferError
from asset_capabilities import CAPABILITIES


def enc58(data, alphabet=BASE58):
    n=int.from_bytes(data,'big');out=''
    while n:
        n,rem=divmod(n,58);out=alphabet[rem]+out
    return alphabet[0]*(len(data)-len(data.lstrip(b'\0')))+out


def addr58(payload,alphabet=BASE58):
    check=hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return enc58(payload+check,alphabet)

class ChainExpansionTests(unittest.TestCase):
    def setUp(self):
        self.sol=enc58(bytes(range(1,33)))
        self.gen=enc58(bytes(range(32,64)))
        self.trx=addr58(b'\x41'+bytes(range(20)))
        self.xrp=addr58(b'\0'+bytes(range(20)),RIPPLE58)

    def test_selections_and_read_only_capabilities(self):
        self.assertEqual(len(COINS),6)
        for c in COINS:
            self.assertFalse(CAPABILITIES[c].can_spend_if_connected)
            self.assertIn('read-only',CAPABILITIES[c].sign_method)
            self.assertIn('mainnet' if c not in ('LTC','DOGE','BCH') else 'main',NETWORKS[c])

    def test_base58_and_xrp_roundtrip(self):
        self.assertEqual(len(b58decode(self.sol)),32)
        self.assertEqual(validate_address('SOL',self.sol),self.sol)
        self.assertEqual(validate_address('TRX',self.trx),self.trx)
        self.assertEqual(validate_address('XRP',self.xrp),self.xrp)

    def test_checksum_failure_and_wrong_chain(self):
        for a,addr in [('TRX',self.trx),('XRP',self.xrp)]:
            with self.assertRaises(TransferError):validate_address(a,addr[:-1]+('a' if addr[-1]!='a' else 'b'))
        with self.assertRaises(TransferError):validate_address('TRX',self.xrp)
        with self.assertRaises(TransferError):validate_address('SOL',self.sol[:-1])
        with self.assertRaises(TransferError):validate_address('XRP','X'+self.xrp[1:])
        with self.assertRaises(TransferError):validate_address('SOL','\t'+self.sol)

    def test_solana_finalized_genesis_pin(self):
        calls=[]
        def fake(url,body):
            calls.append(body['method'])
            if body['method']=='getGenesisHash':return {'result':self.gen}
            return {'result':{'context':{'slot':900},'value':1234500000}}
        b=read_solana('devnet',self.sol,'https://api.devnet.solana.com',expected_genesis=self.gen,transport=fake)
        self.assertEqual(b.confirmed,'1.2345');self.assertEqual(b.height,900)
        self.assertEqual(calls,['getGenesisHash','getBalance'])
        self.assertFalse(b.spendable)
        with self.assertRaisesRegex(TransferError,'genesis hash'):
            read_solana('devnet',self.sol,'https://api.devnet.solana.com',transport=fake)
        with self.assertRaisesRegex(TransferError,'genesis hash'):
            read_solana('devnet',self.sol,'https://api.devnet.solana.com',expected_genesis='incorrect',transport=fake)
        self.assertEqual(calls[-2:],['getGenesisHash','getGenesisHash'])

    def test_solana_rejects_bad_slot_or_balance(self):
        def fake(url,body):
            return {'result':self.gen} if body['method']=='getGenesisHash' else {'result':{'context':{'slot':True},'value':100}}
        with self.assertRaises(TransferError):read_solana('devnet',self.sol,'https://api.devnet.solana.com',expected_genesis=self.gen,transport=fake)

    def test_tron_solidified_balance(self):
        b=read_tron('shasta',self.trx,'https://api.shasta.trongrid.io',transport=lambda url,body:{'address':self.trx,'balance':20250000})
        self.assertEqual(b.confirmed,'20.25');self.assertIn('UNVERIFIED',b.state)
        self.assertFalse(b.spendable)
        with self.assertRaises(TransferError):read_tron('shasta',self.trx,'https://node.example',transport=lambda a,b:{})

    def test_xrp_validated_balance_and_account_required(self):
        body={'result':{'validated':True,'ledger_index':1024,'account_data':{'Account':self.xrp,'Balance':'12000000'}}}
        b=read_xrp('testnet',self.xrp,'https://s.altnet.rippletest.net:51234',transport=lambda u,p:body)
        self.assertEqual(b.confirmed,'12');self.assertEqual(b.height,1024)
        self.assertIn('reserve',b.note)
        body['result']['validated']=False
        with self.assertRaises(TransferError):read_xrp('testnet',self.xrp,'https://example.org',transport=lambda u,p:body)
        body['result']['validated']=True;body['result']['account_data']['Account']=self.trx
        with self.assertRaises(TransferError):read_xrp('testnet',self.xrp,'https://example.org',transport=lambda u,p:body)

    def test_coin_node_owned_utxos_only(self):
        rpc=Mock();rpc.call.side_effect=lambda method,*params: {
          'getblockchaininfo':{'chain':'test','blocks':42,'initialblockdownload':False},
          'listwallets':['mine'],
          'validateaddress':{'isvalid':True,'ismine':True},
          'listunspent':[{'address':'L123456789ABCDEFGHJKLMNPQRSTUVWXYZ','amount':'1.23450000'},
                         {'address':'L123456789ABCDEFGHJKLMNPQRSTUVWXYZ','amount':'0.00000100'}],
        }[method]
        factory=Mock(return_value=rpc)
        b=read_utxo_balance('LTC','test','L123456789ABCDEFGHJKLMNPQRSTUVWXYZ','http://127.0.0.1:19332','/tmp/.cookie','mine',rpc_factory=factory)
        self.assertEqual(b.confirmed,'1.23450100');self.assertEqual(b.height,42)
        self.assertFalse(b.spendable)
        self.assertEqual(factory.call_count,2)
        rpc.call.side_effect=lambda m,*args: {'getblockchaininfo':{'chain':'main','blocks':2,'initialblockdownload':False}}[m]
        with self.assertRaises(TransferError):read_utxo_balance('LTC','test','L123456789ABCDEFGHJKLMNPQRSTUVWXYZ','http://127.0.0.1:19332','/tmp/.cookie','mine',rpc_factory=factory)

    def test_wrong_coin_wallet_ownership(self):
        rpc=Mock();rpc.call.side_effect=lambda m,*a:{'getblockchaininfo':{'chain':'test','blocks':50,'initialblockdownload':False},'listwallets':['mine'],'validateaddress':{'isvalid':True,'ismine':False}}[m]
        with self.assertRaisesRegex(TransferError,'not owned'):
            read_utxo_balance('DOGE','test','D123456789ABCDEFGHJKLMNPQRSTUVWXYZ','http://127.0.0.1:22555','/tmp/.cookie','mine',rpc_factory=Mock(return_value=rpc))

    def test_url_fail_closed(self):
        for url in ('http://example.com:8332','http://192.168.1.1:8332','file:///etc/passwd','https://x.example/a%2Fb',
                    'https://user:pass@example.org','https://api.example?secret=1','https://api.example#fragment'):
            with self.subTest(url=url),self.assertRaises(TransferError):safe_rpc_endpoint(url)
        self.assertEqual(safe_rpc_endpoint('https://node.example'),'https://node.example')
        self.assertEqual(safe_rpc_endpoint('http://127.0.0.1:8090'),'http://127.0.0.1:8090')

    def test_amount_exact_and_negative_rejected(self):
        self.assertEqual(amount_from_units(123456789,9),'0.123456789')
        for amt in (-1,True,'100',10**27):
            with self.assertRaises(TransferError):amount_from_units(amt,9)

    def test_read_balance_unsupported(self):
        with self.assertRaises(TransferError):read_balance('NOTACOIN','test','abc','https://node.example')

if __name__=='__main__':unittest.main()
