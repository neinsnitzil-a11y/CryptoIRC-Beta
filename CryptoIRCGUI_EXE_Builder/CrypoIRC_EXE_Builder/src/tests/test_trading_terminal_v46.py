"""No network and no real-money operations. Must pass independently of Alpaca keys."""
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_terminal import (parse_symbol,positive,Bar,ema,rsi,demo_bars,
                             AlpacaMarketFeed,PaperLedger,Watchlist)


class MarketDataTests(unittest.TestCase):
    def test_stock_and_crypto_validation(self):
        self.assertEqual(parse_symbol('aapl','stock'),'AAPL')
        self.assertEqual(parse_symbol('btc/usd','crypto'),'BTC/USD')
        for sym,kind in [('BTC/USD','stock'),('AAPL','crypto'),('../x','stock'),('ETH/../USD','crypto')]:
            with self.assertRaises(ValueError):parse_symbol(sym,kind)

    def test_invalid_money_and_candles(self):
        for value in ['0','-1','nan','Infinity','1e9999','abc']:
            with self.assertRaises(ValueError):positive(value)
        with self.assertRaises(ValueError):Bar.parse(dict(t='2026-01-01T00:00:00Z',o=10,h=9,l=8,c=11,v=2))

    def test_indicators_and_demo_is_synthetic(self):
        candles=demo_bars('BTC/USD','crypto',count=80)
        self.assertEqual(len(candles),80)
        self.assertTrue(all(x.high>=x.close>=x.low for x in candles))
        self.assertEqual(len(ema([x.close for x in candles],12)),80)
        self.assertIsNone(rsi([x.close for x in candles])[0])
        self.assertTrue(0<=rsi([x.close for x in candles])[-1]<=100)

    def test_alpaca_endpoints_and_provider_auth_requirements(self):
        feed=AlpacaMarketFeed('testid','testsecret')
        calls=[]
        def fake(path,params):
            calls.append((path,params))
            sym=params['symbols'];return {'bars':{sym:[{'t':'2026-01-01T00:00:00Z','o':10,'h':12,'l':9,'c':11,'v':8}]}}
        with patch.object(feed,'_get',side_effect=fake):
            self.assertEqual(feed.bars('AAPL','stock',limit=20)[0].close,11)
            self.assertEqual(feed.bars('BTC/USD','crypto',limit=20)[0].close,11)
        self.assertEqual(calls[0][0],'/v2/stocks/bars')
        self.assertEqual(calls[0][1]['feed'],'iex')
        self.assertEqual(calls[1][0],'/v1beta3/crypto/us/bars')
        with self.assertRaises(RuntimeError):AlpacaMarketFeed('','').bars('AAPL','stock',limit=20)


class PaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.path=Path(self.tmp.name)
        self.ledger=PaperLedger(self.path/'paper.db',starting_cash='1000')
        self.when=datetime.now(timezone.utc)

    def tearDown(self):self.tmp.cleanup()

    def order(self,**options):
        kwargs=dict(symbol='BTC/USD',asset_type='crypto',side='BUY',quantity='2',quote_price='100',
                    observed_at=self.when.isoformat(),source='SIMULATED-DEMO',now=self.when)
        kwargs.update(options)
        return self.ledger.execute(**kwargs)

    def test_buy_sell_cash_and_basis_survive_restart(self):
        self.order()
        self.assertEqual(self.ledger.cash(),Decimal('800'))
        self.assertEqual(self.ledger.positions()[0][2],Decimal('2'))
        self.order(side='SELL',quantity='1',quote_price='120')
        self.assertEqual(self.ledger.cash(),Decimal('920'))
        self.assertEqual(self.ledger.positions()[0][3],Decimal('100'))
        again=PaperLedger(self.path/'paper.db')
        self.assertEqual(again.cash(),Decimal('920'))
        self.assertEqual(len(again.orders()),2)

    def test_insufficient_funds_and_short_selling_rejected(self):
        with self.assertRaises(ValueError):self.order(quantity='50')
        with self.assertRaises(ValueError):self.order(side='SELL')
        self.assertEqual(self.ledger.cash(),Decimal('1000'))
        self.assertEqual(self.ledger.orders(),[])

    def test_price_staleness_and_unrecognized_sources_rejected(self):
        with self.assertRaises(ValueError):self.order(observed_at=(self.when-timedelta(minutes=5)).isoformat())
        with self.assertRaises(ValueError):self.order(source='unverified')
        self.assertEqual(self.ledger.orders(),[])

    def test_no_overdraw_when_order_rolls_back(self):
        self.order(quantity='5')
        with self.assertRaises(ValueError):self.order(quantity='6')
        self.assertEqual(self.ledger.cash(),Decimal('500'))
        self.assertEqual(len(self.ledger.orders()),1)

    def test_watchlist_preservation_and_deduplication(self):
        watch=Watchlist(self.path/'watch.json')
        self.assertIn(('stock','AAPL'),watch.get())
        watch.put([('stock','msft'),('stock','MSFT'),('crypto','BTC/USD')])
        self.assertEqual(watch.get(),[('stock','MSFT'),('crypto','BTC/USD')])

    def test_no_brokerage_or_wallet_access_in_paper_ledger(self):
        self.assertNotIn('vault',str(self.ledger.path).lower())
        self.order()
        content=' '.join(str(x) for x in self.ledger.orders())
        self.assertIn('SIMULATED-DEMO',content)


if __name__=='__main__':unittest.main()
