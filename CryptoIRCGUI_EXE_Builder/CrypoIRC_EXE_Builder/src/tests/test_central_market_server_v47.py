"""Offline contract/security tests of central market read-only GUI feed."""
import unittest, io, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_server_client import ServerMarketFeed, validate_service_url

class TestCentralMarket(unittest.TestCase):
    def test_https_only_and_no_credentials(self):
        for url in ('http://markets.example.com','https://name:pass@markets.example.com',
                    'https://markets.example.com:8787','https://markets.example.com/evil',
                    'https://127.0.0.1','https://markets.example.com?a=b'):
            with self.subTest(url=url),self.assertRaises(ValueError):validate_service_url(url)
        self.assertEqual(validate_service_url('https://markets.example.com/'),'https://markets.example.com')

    def test_no_service_has_no_auth_credentials(self):
        self.assertFalse(ServerMarketFeed(url='').configured)

    def test_read_only_bars_and_quote_contract(self):
        class Reply:
            status=200
            def __init__(self,blob):self.blob=blob
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return self.blob
        class Fake:
            urls=[]
            def open(self,req,timeout):
                self.urls.append(req.full_url)
                self_headers={k.lower():v for k,v in req.header_items()}
                assert not any('secret' in h.lower() or 'key' in h.lower() or 'bearer' in h.lower() for h in self_headers)
                bar={'t':'2026-10-31T00:00:00+00:00','o':100,'h':110,'l':95,'c':104,'v':88}
                data={'mode':'licensed','source':'ALPACA-IEX','bar':bar} if '/latest' in req.full_url else {'mode':'licensed','source':'ALPACA-IEX','bars':[bar]}
                return Reply(json.dumps(data).encode('utf-8'))
        fake=Fake()
        feed=ServerMarketFeed('https://markets.example.com',opener=fake)
        bars=feed.bars('AAPL','stock',limit=30)
        self.assertEqual(bars[0].close,104)
        quote,src,mode=feed.latest('AAPL','stock')
        self.assertEqual((src,mode),('ALPACA-IEX','licensed'))
        self.assertEqual(quote.close,104)
        self.assertTrue(all(s.startswith('https://markets.example.com/api/v1/') for s in fake.urls))

    def test_reject_fake_unknown_status(self):
        class Reply:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return b'{"mode":"real","bars":[]}'
        class Fake:
            def open(self,*a,**k):return Reply()
        with self.assertRaises(ValueError):ServerMarketFeed('https://markets.example.com',opener=Fake()).bars('AAPL','stock',limit=20)

if __name__=='__main__':unittest.main()
