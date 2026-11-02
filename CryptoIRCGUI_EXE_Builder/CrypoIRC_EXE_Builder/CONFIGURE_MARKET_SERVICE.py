"""Publisher-only helper. Bake public HTTPS market-service address into client release."""
from pathlib import Path
import json, sys
from urllib.parse import urlsplit

root=Path(__file__).resolve().parent
p=root/'src'/'data'/'market_server.json'
if not p.is_file():raise SystemExit('Expected src/data/market_server.json')
value=(sys.argv[1] if len(sys.argv)>1 else input('HTTPS market server URL (e.g. https://markets.example.com): ')).strip().rstrip('/')
u=urlsplit(value)
if not (u.scheme=='https' and u.hostname and u.path in ('','/') and not u.query and not u.fragment and not u.username and not u.password and (not u.port or u.port==443)):
    raise SystemExit('Use an HTTPS origin on port 443; do not include credentials or paths')
p.write_text(json.dumps({'base_url':value,'description':'Public HTTPS market data service. No API keys.'},indent=2)+'\n',encoding='utf-8')
print('Publisher default saved to',p)
print('Build new installer with BUILD_WINDOWS.bat to distribute URL to all clients.')
