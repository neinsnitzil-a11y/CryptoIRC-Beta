"""Phase 7 token reader tests use synthetic node responses, never real funds."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace
from token_infrastructure import (TOKEN_CODES,EVM_TOKEN_NETWORKS,SOL_TOKENS,TRON_TOKENS,
    make_spec,TokenRegistry,read_spl_token,read_trc20_token,read_evm_token,
    _units_to_decimal,TokenSpec,read_token_balance)
from core.transfer import TransferError
from chain_expansion import BASE58


def enc58(payload):
    i=int.from_bytes(payload,'big');s=''
    while i:i,r=divmod(i,58);s=BASE58[r]+s
    return BASE58[0]*(len(payload)-len(payload.lstrip(b'\0')))+s

def trxaddr(payload):
    data=b'\x41'+payload
    return enc58(data+hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4])

class TokenInfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.owner=enc58(bytes(range(1,33)))
        self.mint=enc58(bytes(range(32,64)))
        self.genesis=enc58(bytes(range(33,65)))
        self.trx=trxaddr(bytes(range(20)))
        self.contract=trxaddr(bytes(range(1,21)))
        self.evm='0x'+'ab'*20

    def test_all_catalog_codes_and_route_identification(self):
        self.assertEqual(len(TOKEN_CODES),12)
        self.assertEqual(set(TOKEN_CODES),set(EVM_TOKEN_NETWORKS)|SOL_TOKENS|TRON_TOKENS)
        for code,net in EVM_TOKEN_NETWORKS.items():
            spec=make_spec(code,net,self.evm,6)
            self.assertEqual(spec.network,net)
            self.assertEqual(spec.protocol,'ERC20')
            self.assertIsInstance(spec.chain_id,int)
            self.assertNotEqual(spec.attestation,'OFFICIAL_ISSUER_VERIFIED')
        for code in SOL_TOKENS:
            spec=make_spec(code,'devnet',self.mint,6,genesis=self.genesis)
            self.assertEqual(spec.protocol,'SPL')
        self.assertEqual(make_spec('USDT-TRX','shasta',self.contract,6).protocol,'TRC20')

    def test_cross_chain_wrong_identifier_and_precision(self):
        errors=[('USDT-ETH','BNB',self.evm,6,''),
                ('USDT-SOL','devnet',self.evm,6,self.genesis),
                ('USDT-TRX','shasta',self.evm,6,''),
                ('USDT-TRX','main',self.contract,6,''),
                ('USDC-SOL','mainnet',self.mint,6,''),
                ('USDT-ETH','ETH',self.evm,37,''),
                ('USDT-ETH','ETH',self.evm,True,''),
                ('USDT-ETH','ETH',self.evm,6,self.genesis)]
        for code,net,addr,places,gen in errors:
            with self.subTest(code=code,net=net),self.assertRaises(TransferError):
                make_spec(code,net,addr,places,genesis=gen)
        self.assertEqual(_units_to_decimal(1,18),'0.000000000000000001')
        self.assertEqual(_units_to_decimal(1234567,6),'1.234567')
        with self.assertRaises(TransferError):_units_to_decimal(True,6)
        with self.assertRaises(TransferError):_units_to_decimal(-1,6)

    def test_token_registry_persistence_and_explicit_repin(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pins.sqlite'
            pin=make_spec('USDT-ETH','ETH',self.evm,6)
            reg=TokenRegistry(path);reg.pin(pin)
            self.assertEqual(TokenRegistry(path).get('USDT-ETH','ETH'),pin)
            reg.pin(pin)  # idempotent
            with self.assertRaisesRegex(TransferError,'Unpin|Remove'):
                reg.pin(make_spec('USDT-ETH','ETH','0x'+'cd'*20,6))
            self.assertEqual(TokenRegistry(path).get('USDT-ETH','ETH'),pin)
            self.assertIsNone(reg.get('USDT-ETH','BNB'))
            reg.unpin('USDT-ETH','ETH')
            self.assertIsNone(TokenRegistry(path).get('USDT-ETH','ETH'))

    def test_spl_multiple_accounts_frozen_and_finalized(self):
        spec=make_spec('USDC-SOL','devnet',self.mint,6,genesis=self.genesis)
        calls=[]
        def account(amount,owner=None,mint=None,dec=6):
            return {'account':{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
                'data':{'program':'spl-token','parsed':{'info':{
                'mint':mint or self.mint,'owner':owner or self.owner,'state':'frozen',
                'tokenAmount':{'amount':amount,'decimals':dec}}}}}}
        response={'result':{'context':{'slot':128},'value':[account('1'),account('1299999')]}}
        def fake(url,payload):
            calls.append((payload['method'],payload['params']))
            return {'result':self.genesis} if payload['method']=='getGenesisHash' else response
        b=read_spl_token(spec,self.owner,'https://example.org',transport=fake)
        self.assertEqual(b.amount,'1.3');self.assertEqual(b.block_or_slot,128)
        self.assertFalse(b.spendable)
        self.assertEqual(calls[1][0],'getTokenAccountsByOwner')
        self.assertEqual(calls[1][1][1],{'mint':self.mint})
        self.assertEqual(calls[1][1][2]['commitment'],'finalized')
        response['result']['value']=[account('1',owner=self.mint)]
        with self.assertRaises(TransferError):read_spl_token(spec,self.owner,'https://example.org',transport=fake)
        response['result']['value']=[account('1',dec=9)]
        with self.assertRaises(TransferError):read_spl_token(spec,self.owner,'https://example.org',transport=fake)
        response['result']['value']=[]
        b=read_spl_token(spec,self.owner,'https://example.org',transport=fake)
        self.assertEqual(b.amount,'0')

    def test_spl_rejects_forged_cluster_or_slot(self):
        spec=make_spec('USDT-SOL','devnet',self.mint,6,genesis=self.genesis)
        def bad(url,payload):return {'result':'wrong'}
        with self.assertRaisesRegex(TransferError,'genesis'):
            read_spl_token(spec,self.owner,'https://node.example',transport=bad)
        def bad_slot(url,payload):
            return {'result':self.genesis} if payload['method']=='getGenesisHash' else {'result':{'context':{'slot':True},'value':[]}}
        with self.assertRaises(TransferError):read_spl_token(spec,self.owner,'https://node.example',transport=bad_slot)

    def test_tron_solidified_contract_amount_and_decimals(self):
        spec=make_spec('USDT-TRX','shasta',self.contract,6)
        observed=[]
        def fake(url,payload):
            observed.append((url,payload))
            n=6 if payload['function_selector']=='decimals()' else 123456789
            return {'result':{'result':True},'constant_result':[f'{n:064x}']}
        b=read_trc20_token(spec,self.trx,'https://api.shasta.trongrid.io',transport=fake)
        self.assertEqual(b.amount,'123.456789')
        self.assertEqual(len(observed),2)
        self.assertTrue(all('/walletsolidity/triggerconstantcontract' in u for u,p in observed))
        self.assertEqual(observed[1][1]['parameter'],bytes(range(20)).hex().rjust(64,'0'))
        self.assertFalse(b.spendable)
        def mismatch(url,payload):return {'result':{'result':True},'constant_result':[f'{8:064x}']}
        with self.assertRaisesRegex(TransferError,'decimals'):
            read_trc20_token(spec,self.trx,'https://api.shasta.trongrid.io',transport=mismatch)
        def bogus(url,payload):return {'result':{'result':False},'constant_result':[f'{6:064x}']}
        with self.assertRaises(TransferError):read_trc20_token(spec,self.trx,'https://api.shasta.trongrid.io',transport=bogus)

    def test_evm_correct_chain_metadata_and_code(self):
        spec=make_spec('USDC-BASE','BASE',self.evm,6)
        funcs=SimpleNamespace(
            decimals=lambda:SimpleNamespace(call=lambda:6),
            symbol=lambda:SimpleNamespace(call=lambda:'USDC'),
            balanceOf=lambda a:SimpleNamespace(call=lambda:123456))
        eth=Mock()
        eth.chain_id=8453;eth.block_number=900
        eth.get_code.return_value=b'\x60\x80';eth.get_balance.return_value=10**16
        eth.contract.return_value=SimpleNamespace(functions=funcs)
        w3=Mock(eth=eth);w3.is_address.return_value=True;w3.to_checksum_address.side_effect=lambda a:a
        b=read_evm_token(spec,'0x'+'cd'*20,'https://node.example',w3=w3)
        self.assertEqual(b.amount,'0.123456');self.assertEqual(b.gas_units,10**16)
        self.assertEqual(b.block_or_slot,900)
        self.assertFalse(b.spendable)
        eth.chain_id=1
        with self.assertRaises(TransferError):read_evm_token(spec,'0x'+'cd'*20,'https://node.example',w3=w3)
        eth.chain_id=8453
        funcs.decimals=lambda:SimpleNamespace(call=lambda:18)
        with self.assertRaisesRegex(TransferError,'decimals'):
            read_evm_token(spec,'0x'+'cd'*20,'https://node.example',w3=w3)
        funcs.decimals=lambda:SimpleNamespace(call=lambda:6)
        funcs.symbol=lambda:SimpleNamespace(call=lambda:'FAKE')
        with self.assertRaisesRegex(TransferError,'symbol'):
            read_evm_token(spec,'0x'+'cd'*20,'https://node.example',w3=w3)

if __name__=='__main__':unittest.main()
