"""Read-only Nocturne market service client. Never contains trading credentials.

Public service must be HTTPS with provider-authorized distribution rights.
No silent downgrade to HTTP, no synthetic data disguised as live.
"""
from __future__ import annotations
import json
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from market_terminal import Bar, parse_symbol, TIMEFRAMES


def validate_service_url(raw: str) -> str:
    raw = (raw or '').strip().rstrip('/')
    p = urlsplit(raw)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password or
            p.query or p.fragment or p.path not in ('', '/')):
        raise ValueError('Market service must be an HTTPS origin without credentials, path or query')
    if p.hostname.lower() in ('localhost', '127.0.0.1', '0.0.0.0'):
        raise ValueError('Market service requires publicly verifiable HTTPS; local test clients use a test subclass')
    if p.port and p.port != 443:
        raise ValueError('Market service must use HTTPS port 443')
    return raw


def _config_paths():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return [base/'data'/'market_server.json',Path(__file__).resolve().parent/'data'/'market_server.json']


def configured_server_url() -> str:
    for path in _config_paths():
        if path.is_file():
            try:
                raw=json.loads(path.read_text(encoding='utf-8'))
                return validate_service_url(raw.get('base_url','')) if raw.get('base_url') else ''
            except (ValueError,OSError,TypeError,KeyError):
                return ''
    return ''


class ServerMarketFeed:
    """Simple bounded HTTPS poller for central market feed; never sends broker keys."""
    def __init__(self, url: str | None = None, *, opener=None):
        self.url = validate_service_url(url or configured_server_url()) if (url or configured_server_url()) else ''
        self.opener = opener or build_opener(ProxyHandler({}))
        self.last_mode = None
        self.last_source = None

    @property
    def configured(self): return bool(self.url)

    def _get(self, endpoint: str, params: dict):
        if not self.url: raise RuntimeError('No trusted Nocturne market server configured in application release')
        request = Request(self.url + '/api/v1/' + endpoint + '?' + urlencode(params),headers={
            'User-Agent':'CRYPTO-NOCTURNE-MarketClient/1.0', 'Accept':'application/json'})
        with self.opener.open(request,timeout=8) as response:
            if response.status != 200:raise RuntimeError('Market server HTTP failure')
            body=response.read(1_500_001)
        if len(body)>1_500_000:raise ValueError('Oversized market data response')
        obj=json.loads(body)
        if not isinstance(obj,dict) or obj.get('mode') not in ('licensed','demo'):
            raise ValueError('Unrecognized market data source')
        self.last_mode = obj['mode']
        self.last_source = str(obj.get('source','NOCTURNE SERVER'))[:80]
        return obj

    def bars(self,symbol,asset_type,timeframe='1Min',limit=180):
        symbol=parse_symbol(symbol,asset_type)
        if timeframe not in TIMEFRAMES or not 20<=limit<=500:raise ValueError('Unsupported bars request')
        obj=self._get('bars',{'symbol':symbol,'market':asset_type,'timeframe':timeframe,'limit':limit})
        raw=obj.get('bars')
        if not isinstance(raw,list) or len(raw)>500:raise ValueError('Invalid bars response')
        return [Bar.parse(b) for b in raw]

    def latest(self,symbol,asset_type):
        symbol=parse_symbol(symbol,asset_type)
        obj=self._get('latest',{'symbol':symbol,'market':asset_type})
        return Bar.parse(obj['bar']), obj.get('source','NOCTURNE SERVER'), obj['mode']
