"""Deterministic safety tests. No blockchains, keys, servers, or funds involved."""
import builtins
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transfer_engine as t


class TestAmounts(unittest.TestCase):
    def test_valid_btc_sat(self):
        self.assertEqual(t.units(t.amount_decimal('0.00000001', 8), 8), 1)
        self.assertEqual(t.units(t.amount_decimal('0.00123456', 8), 8), 123456)

    def test_valid_xmr_piconero(self):
        self.assertEqual(t.units(t.amount_decimal('0.000000000001', 12), 12), 1)

    def test_invalid_amounts(self):
        for raw in ('', '0', '-1', '1e10', '.4', '+1', ' 1e-3 ', 'nan', 'inf', '1,000', '0.000000001'):
            with self.subTest(raw=raw):
                with self.assertRaises(t.TransferError):
                    t.amount_decimal(raw, 8)

    def test_exact_float(self):
        self.assertEqual(t.float_exact(Decimal('0.12345678')), 0.12345678)
        with self.assertRaises(t.TransferError):
            t.float_exact(Decimal('999999999.12345678'))


class TestNetworkSafety(unittest.TestCase):
    def test_loopback(self):
        self.assertEqual(t.safe_loopback_url('http://127.0.0.1:8332'), 'http://127.0.0.1:8332')
        self.assertEqual(t.safe_loopback_url('http://[::1]:18082'), 'http://[::1]:18082')
        for url in ('https://127.0.0.1:8332', 'http://localhost:8332', 'http://127.0.0.2:8332',
                    'http://192.168.1.1:8332', 'http://127.0.0.1:8332/wallet',
                    'http://alice:pw@127.0.0.1:8332', 'http://127.0.0.1:8332/?a=b'):
            with self.subTest(url=url):
                with self.assertRaises(t.TransferError):
                    t.safe_loopback_url(url)

    def test_evm_https(self):
        self.assertEqual(t.safe_evm_rpc_url('https://rpc.example.org/api'), 'https://rpc.example.org/api')
        self.assertEqual(t.safe_evm_rpc_url('http://127.0.0.1:8545'), 'http://127.0.0.1:8545')
        for url in ('http://rpc.example.org', 'http://localhost:8545', 'ftp://example.org',
                    'https://alice:pw@example.org', 'https://example.org/#private'):
            with self.subTest(url=url):
                with self.assertRaises(t.TransferError):
                    t.safe_evm_rpc_url(url)

    def test_keystore_reject_plaintext(self):
        with tempfile.TemporaryDirectory() as temp:
            filename = Path(temp) / 'unsafe.json'
            filename.write_text('{"address":"' + 'a'*40 + '","private_key":"' + 'b'*64 + '"}')
            with self.assertRaises(t.TransferError):
                t.load_keystore_header(filename)


class FakeBitcoin:
    def __init__(self, mine):
        self.mine = mine
    def call(self, method, *args):
        if method != 'getaddressinfo':
            raise AssertionError('Unexpected Bitcoin Core method')
        return {'ismine': args[0] in self.mine}


class TestBitcoinPSBT(unittest.TestCase):
    def setUp(self):
        self.dest = 'bc1q' + 'a' * 38
        self.change = 'bc1q' + 'b' * 38
        self.amount = Decimal('0.1')
    def tx(self, outputs):
        return {'vout': [{'value': str(val), 'scriptPubKey': {'address': address}}
                         for address, val in outputs]}

    def test_valid_destination_and_change(self):
        tx = self.tx([(self.dest, self.amount), (self.change, Decimal('0.02'))])
        self.assertEqual(len(t.verify_bitcoin_outputs(FakeBitcoin({self.change}), tx, self.dest, self.amount)), 2)

    def test_refuse_unauthorized_second_recipient(self):
        tx = self.tx([(self.dest, self.amount), ('bc1q' + 'c'*38, Decimal('0.02'))])
        with self.assertRaises(t.TransferError):
            t.verify_bitcoin_outputs(FakeBitcoin({self.change}), tx, self.dest, self.amount)

    def test_refuse_destination_amount_change(self):
        tx = self.tx([(self.dest, Decimal('0.099')), (self.change, Decimal('0.02'))])
        with self.assertRaises(t.TransferError):
            t.verify_bitcoin_outputs(FakeBitcoin({self.change}), tx, self.dest, self.amount)

    def test_refuse_op_return(self):
        tx = {'vout': [{'value':'0.1','scriptPubKey':{'address':self.dest}},
                       {'value':'0','scriptPubKey':{'type':'nulldata'}}]}
        with self.assertRaises(t.TransferError):
            t.verify_bitcoin_outputs(FakeBitcoin({self.change}), tx, self.dest, self.amount)


class TestAuthorization(unittest.TestCase):
    def test_wrong_challenge_refuses(self):
        with patch('builtins.input', return_value='SEND'):
            self.assertFalse(t.confirm_send('bc1q' + 'x'*38, Decimal('0.1'), 'BTC'))
    def test_exact_challenge(self):
        with patch('builtins.input', return_value='SEND 0.1 BTC xxxxxxxx'):
            self.assertTrue(t.confirm_send('bc1q' + 'x'*38, Decimal('0.1'), 'BTC'))
    def test_prepare_requires_keyword(self):
        with patch('builtins.input', return_value='no'):
            self.assertFalse(t.confirm_prepare())


if __name__ == '__main__':
    unittest.main()
