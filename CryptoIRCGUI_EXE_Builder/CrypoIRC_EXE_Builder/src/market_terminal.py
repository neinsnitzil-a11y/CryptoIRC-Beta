"""CRYPTO NOCTURNE market terminal: market data and isolated PAPER-ONLY trading.

No wallet, fiat ledger, payment, or brokerage execution API is accessed here.
Market data is obtained from user-configured Alpaca credentials; the demo feed
is explicitly synthetic. All trade orders are locally simulated in SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import math
import os
import random
import re
import sqlite3
import threading
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, ProxyHandler

STOCK_RE = re.compile(r'^[A-Z][A-Z0-9.\-]{0,11}$')
CRYPTO_RE = re.compile(r'^[A-Z0-9]{2,12}/[A-Z0-9]{2,8}$')
TIMEFRAMES = {'1Min': 60, '5Min': 300, '15Min': 900, '1Hour': 3600, '1Day': 86400}
DEFAULT_STOCKS = ('AAPL', 'MSFT', 'NVDA', 'TSLA', 'SPY')
DEFAULT_CRYPTO = ('BTC/USD', 'ETH/USD', 'SOL/USD')


def parse_symbol(symbol: str, asset_type: str) -> str:
    symbol = symbol.strip().upper()
    if asset_type not in ('stock', 'crypto'):
        raise ValueError('Choose stock or crypto')
    if not (STOCK_RE if asset_type == 'stock' else CRYPTO_RE).fullmatch(symbol):
        raise ValueError('Invalid symbol format for selected market')
    return symbol


def positive(value, *, max_value='1000000000000') -> Decimal:
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError('Enter a numeric amount') from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal(max_value):
        raise ValueError('Amount must be finite, positive and within limits')
    return amount


@dataclass(frozen=True)
class Bar:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def parse(cls, data: dict):
        values = [float(data[k]) for k in ('o', 'h', 'l', 'c', 'v')]
        o, h, l, c, v = values
        if not all(math.isfinite(n) for n in values) or min(o, h, l, c) <= 0 or v < 0:
            raise ValueError('Invalid or non-finite OHLCV')
        if h < max(o, c, l) or l > min(o, c, h):
            raise ValueError('Inconsistent OHLC range')
        stamp = str(data['t'])
        datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        return cls(stamp, o, h, l, c, v)


def ema(values: list[float], period: int) -> list[float]:
    if period < 1:
        raise ValueError('Period must be positive')
    out = []
    last = None
    weight = 2 / (period + 1)
    for v in values:
        last = v if last is None else (v * weight + last * (1 - weight))
        out.append(last)
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period + 1:
        return out
    gains = [max(0, values[i] - values[i - 1]) for i in range(1, len(values))]
    losses = [max(0, values[i - 1] - values[i]) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    def calc():
        if avg_loss == 0:
            return 100.0 if avg_gain else 50.0
        return 100 - 100 / (1 + avg_gain / avg_loss)
    out[period] = calc()
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = calc()
    return out


class AlpacaMarketFeed:
    """Read-only TLS Alpaca REST feed, not a brokerage/order API.

    Credentials are passed from the process environment rather than written to
    the application database or source. HTTP system proxy is deliberately not
    used to avoid unknowingly sending access keys to a third-party proxy.
    """
    BASE = 'https://data.alpaca.markets'

    def __init__(self, key: str | None = None, secret: str | None = None):
        self.key = key if key is not None else os.getenv('ALPACA_API_KEY', '')
        self.secret = secret if secret is not None else os.getenv('ALPACA_API_SECRET', '')
        self.opener = build_opener(ProxyHandler({}))

    @property
    def configured(self):
        return bool(self.key and self.secret)

    def _get(self, path, params):
        if not self.configured:
            raise RuntimeError('Alpaca market-data keys not configured; choose DEMO or set ALPACA_API_KEY / ALPACA_API_SECRET')
        url = self.BASE + path + '?' + urlencode(params)
        req = Request(url, headers={
            'APCA-API-KEY-ID': self.key,
            'APCA-API-SECRET-KEY': self.secret,
            'Accept': 'application/json',
            'User-Agent': 'CryptoNocturne-MarketTerminal/4.6.0',
        })
        with self.opener.open(req, timeout=8) as response:
            if response.status != 200:
                raise RuntimeError(f'Market data HTTP status {response.status}')
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('Response exceeded size limit')
        return json.loads(body)

    def bars(self, symbol: str, asset_type: str, timeframe: str = '1Min', limit: int = 180) -> list[Bar]:
        symbol = parse_symbol(symbol, asset_type)
        if timeframe not in TIMEFRAMES or not 20 <= limit <= 500:
            raise ValueError('Unsupported timeframe or limit')
        # End at present; chart represents available licensed feed coverage.
        end = datetime.now(timezone.utc)
        lookback = (limit * TIMEFRAMES[timeframe] * (5 if asset_type == 'stock' else 2))
        start = end - timedelta(seconds=max(lookback, 86400))
        common = dict(timeframe=timeframe, limit=limit, start=start.isoformat(), end=end.isoformat(), sort='asc')
        if asset_type == 'stock':
            body = self._get('/v2/stocks/bars', dict(common, symbols=symbol, feed='iex', adjustment='raw'))
        else:
            body = self._get('/v1beta3/crypto/us/bars', dict(common, symbols=symbol))
        raw = body.get('bars', {}).get(symbol, [])
        if not isinstance(raw, list):
            raise ValueError('Unexpected bar response')
        # Only one page is retrieved. The GUI clearly labels it the latest loaded window.
        return [Bar.parse(item) for item in raw][-limit:]

    def latest(self, symbol: str, asset_type: str) -> Bar:
        symbol = parse_symbol(symbol, asset_type)
        if asset_type == 'stock':
            body = self._get('/v2/stocks/bars/latest', {'symbols':symbol,'feed':'iex'})
        else:
            body = self._get('/v1beta3/crypto/us/latest/bars', {'symbols':symbol})
        raw = body.get('bars', {}).get(symbol)
        if not raw:
            raise ValueError('No latest bar available for this market / subscription')
        return Bar.parse(raw)


def demo_bars(symbol: str, asset_type: str, *, timeframe='1Min', count=180) -> list[Bar]:
    """Deterministic synthetic candles for UI demonstration, NEVER real quotes."""
    symbol = parse_symbol(symbol, asset_type)
    if timeframe not in TIMEFRAMES:
        raise ValueError('Unsupported timeframe')
    rng = random.Random(f'NOCTURNE_DEMO_{symbol}_{timeframe}')
    base = 240.0 if asset_type == 'stock' else 42000.0
    now = datetime.now(timezone.utc)
    step = TIMEFRAMES[timeframe]
    start = int(now.timestamp() // step * step) - count * step
    out = []
    for index in range(count):
        movement = rng.uniform(-0.006, .006) + math.sin(index / 24) * .0007
        close = base * (1 + movement)
        high = max(base,close)*(1+rng.random()*.003)
        low = min(base,close)*(1-rng.random()*.003)
        out.append(Bar(datetime.fromtimestamp(start+index*step,timezone.utc).isoformat(),base,high,low,close,rng.uniform(10,1200)))
        base = close
    return out


class PaperLedger:
    """Isolated cash-only paper broker simulation, no margin and no short sales."""
    def __init__(self, path: Path, *, starting_cash='100000.00'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock = threading.RLock()
        self.starting_cash = positive(starting_cash)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS paper_settings (name TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS paper_positions (
                    symbol TEXT NOT NULL, asset_type TEXT NOT NULL, qty TEXT NOT NULL,
                    cost_basis TEXT NOT NULL, PRIMARY KEY(symbol,asset_type));
                CREATE TABLE IF NOT EXISTS paper_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                    symbol TEXT NOT NULL, asset_type TEXT NOT NULL, side TEXT NOT NULL,
                    qty TEXT NOT NULL, price TEXT NOT NULL, notional TEXT NOT NULL,
                    data_source TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO paper_settings VALUES (?,?)',('cash',str(self.starting_cash)))

    @contextmanager
    def _connect(self):
        db=sqlite3.connect(str(self.path),timeout=5)
        try:
            db.execute('PRAGMA busy_timeout=5000')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def cash(self) -> Decimal:
        with self._lock, self._connect() as db:
            return Decimal(db.execute("SELECT value FROM paper_settings WHERE name='cash'").fetchone()[0])

    def positions(self):
        with self._lock, self._connect() as db:
            rows=db.execute('SELECT symbol,asset_type,qty,cost_basis FROM paper_positions ORDER BY symbol').fetchall()
        return [(s,a,Decimal(q),Decimal(cost)) for s,a,q,cost in rows]

    def orders(self, limit=30):
        with self._lock, self._connect() as db:
            return db.execute('SELECT at,symbol,asset_type,side,qty,price,notional,data_source FROM paper_orders ORDER BY id DESC LIMIT ?', (min(200,max(1,limit)),)).fetchall()

    def execute(self, *,symbol,asset_type,side,quantity,quote_price,observed_at,source,now=None):
        symbol=parse_symbol(symbol,asset_type)
        if side not in ('BUY','SELL'):
            raise ValueError('Unsupported side')
        qty=positive(quantity, max_value='100000000')
        price=positive(quote_price)
        timestamp = datetime.fromisoformat(str(observed_at).replace('Z','+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError('Quote requires UTC timezone')
        now = now or datetime.now(timezone.utc)
        if timestamp > now + timedelta(seconds=10) or now-timestamp>timedelta(seconds=120):
            raise ValueError('Quote is stale or invalid; refresh before paper order')
        if source not in ('SIMULATED-DEMO','ALPACA-IEX','ALPACA-CRYPTO'):
            raise ValueError('Unrecognized quote source')
        notional=qty*price
        with self._lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cash=Decimal(db.execute("SELECT value FROM paper_settings WHERE name='cash'").fetchone()[0])
            row=db.execute('SELECT qty,cost_basis FROM paper_positions WHERE symbol=? AND asset_type=?',(symbol,asset_type)).fetchone()
            held, basis = (Decimal(row[0]),Decimal(row[1])) if row else (Decimal(0), Decimal(0))
            if side == 'BUY':
                if notional > cash:
                    raise ValueError('Insufficient paper cash')
                new_cash=cash-notional
                new_held=held+qty
                new_basis=basis+notional
            else:
                if qty>held:
                    raise ValueError('Insufficient paper holdings; short sales disabled')
                new_cash=cash+notional
                new_held=held-qty
                new_basis=(basis*(new_held/held)) if new_held else Decimal(0)
            db.execute('UPDATE paper_settings SET value=? WHERE name=?',(str(new_cash),'cash'))
            if new_held:
                db.execute('INSERT INTO paper_positions VALUES(?,?,?,?) ON CONFLICT(symbol,asset_type) DO UPDATE SET qty=excluded.qty,cost_basis=excluded.cost_basis',
                           (symbol,asset_type,str(new_held),str(new_basis)))
            else:
                db.execute('DELETE FROM paper_positions WHERE symbol=? AND asset_type=?',(symbol,asset_type))
            db.execute('INSERT INTO paper_orders(at,symbol,asset_type,side,qty,price,notional,data_source) VALUES(?,?,?,?,?,?,?,?)',
                       (now.isoformat(),symbol,asset_type,side,str(qty),str(price),str(notional),source))
        return dict(symbol=symbol,side=side,qty=qty,price=price,notional=notional,cash=new_cash)


class Watchlist:
    def __init__(self, path: Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()

    def get(self):
        with self._lock:
            if not self.path.exists():
                return [('stock',sym) for sym in DEFAULT_STOCKS]+[('crypto',sym) for sym in DEFAULT_CRYPTO]
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,list) or len(data)>100:
                raise ValueError('Invalid watchlist')
            return [(item['type'],parse_symbol(item['symbol'],item['type'])) for item in data]

    def put(self, entries):
        entries=list(dict.fromkeys((kind,parse_symbol(symbol,kind)) for kind,symbol in entries))
        if len(entries)>100:
            raise ValueError('Watchlist full (100 symbols)')
        target=self.path.with_name(self.path.name+'.tmp')
        with self._lock:
            target.write_text(json.dumps([{'type':k,'symbol':s} for k,s in entries],indent=2),encoding='utf-8')
            os.replace(target,self.path)
