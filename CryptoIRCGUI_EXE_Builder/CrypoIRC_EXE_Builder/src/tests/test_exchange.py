import unittest, sys, os, time
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import exchange_engine as fx

class FXTests(unittest.TestCase):
 def setUp(self):fx._fx_cache.clear(); fx._crypto_cache.clear()
 def test_iso_catalog(self):
  self.assertTrue(len(fx.FIAT_CODES)>=150)
  for c in ['USD','EUR','GBP','INR','JPY','KWD']:
   self.assertIn(c,fx.FIAT_CODES)
 def test_invalid_amounts(self):
  for val in ['nan','inf','-0.1','0','','1e400']:
   with self.subTest(val=val),self.assertRaises(fx.ExchangeError):fx.positive_amount(val,'USD')
 def test_currency_specific_decimals(self):
  with self.assertRaises(fx.ExchangeError):fx.positive_amount('1.01','JPY')
  self.assertEqual(fx.positive_amount('1.001','KWD'),Decimal('1.001'))
  with self.assertRaises(fx.ExchangeError):fx.positive_amount('1.0001','KWD')
 def test_same_currency_no_http(self):
  with patch.object(fx,'_https_json',side_effect=AssertionError('unexpected network')):
   q=fx.fiat_estimate('5.50','GBP','GBP')
  self.assertEqual(q.estimated_amount,Decimal('5.50'))
 def test_quoted_cross_pair(self):
  with patch.object(fx,'_https_json',return_value={
   'result':'success','base_code':'INR','rates':{'USD':0.0125},
   'time_last_update_unix':int(time.time()),'time_last_update_utc':'today',}):
   q=fx.fiat_estimate('8000','INR','USD')
  self.assertEqual(q.estimated_amount,Decimal('100.0000'))
  self.assertIn('NOT an executable',q.notice)
 def test_wrong_base_fail_closed(self):
  with patch.object(fx,'_https_json',return_value={
   'result':'success','base_code':'EUR','rates':{'USD':1.1},
   'time_last_update_unix':int(time.time())}):
   with self.assertRaises(fx.ExchangeError):fx.fiat_estimate('5','GBP','USD')
 def test_stale_rates_fail_closed(self):
  with patch.object(fx,'_https_json',return_value={
   'result':'success','base_code':'GBP','rates':{'USD':1.1},
   'time_last_update_unix':int(time.time())-900000}):
   with self.assertRaises(fx.ExchangeError):fx.fiat_estimate('5','GBP','USD')
 def test_bad_rate_fail_closed(self):
  with patch.object(fx,'_https_json',return_value={
   'result':'success','base_code':'INR','rates':{'USD':-2},
   'time_last_update_unix':int(time.time())}):
   with self.assertRaises(fx.ExchangeError):fx.fiat_estimate('5','INR','USD')
 def test_crypto_quote(self):
  with patch.object(fx,'_https_json',return_value={'bitcoin':{'usd':50000,'last_updated_at':int(time.time())}}):
   q=fx.crypto_estimate('500','USD','BTC')
  self.assertEqual(q.estimated_amount,Decimal('0.01'))
  self.assertIn('NOT a card purchase',q.notice)
 def test_crypto_stale_quote(self):
  with patch.object(fx,'_https_json',return_value={'bitcoin':{'usd':50000,'last_updated_at':int(time.time())-3600}}):
   with self.assertRaises(fx.ExchangeError):fx.crypto_estimate('500','USD','BTC')
 def test_missing_crypto_mapping_fail_closed(self):
  with self.assertRaises(fx.ExchangeError):fx.crypto_estimate('25','USD','FAKE')
 def test_fixed_provider_urls(self):
  for u in list(fx.FIAT_PROVIDERS.values())+list(fx.CRYPTO_ONRAMPS.values()):
   self.assertTrue(u.startswith('https://'))

if __name__=='__main__':unittest.main()

class ExpandedFiatLedgerTests(unittest.TestCase):
 def test_inr_jpy_kwd_local_ledgers(self):
  import tempfile
  from core import fiat_ledger
  with tempfile.TemporaryDirectory() as d:
   pw='sample password at least fourteen chars'
   j=fiat_ledger.new(d,'JPY','Yen bookkeeping',pw)
   fiat_ledger.append(j,pw,'Money in','125','manual observation')
   with self.assertRaises(ValueError):fiat_ledger.append(j,pw,'Money in','1.50','bad')
   k=fiat_ledger.new(d,'KWD','Dinar bookkeeping',pw)
   fiat_ledger.append(k,pw,'Money in','1.123','manual observation')
   with self.assertRaises(ValueError):fiat_ledger.append(k,pw,'Money in','1.1234','bad')
   self.assertEqual(fiat_ledger.balance(fiat_ledger.read(k,pw)),Decimal('1.123'))
