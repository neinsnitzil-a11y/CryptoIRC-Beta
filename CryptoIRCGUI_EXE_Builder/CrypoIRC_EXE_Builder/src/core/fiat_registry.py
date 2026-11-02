"""Stores only local file paths; never ledger balances or private information."""
import json,os,secrets
from pathlib import Path
from . import fiat_ledger
HOME=Path.home()/'.crypto_creating_wallets'
FILE=HOME/'fiat_paths.json'

def load():
    if not FILE.exists(): return []
    if FILE.stat().st_size>250_000:raise ValueError('Oversize fiat registry')
    d=json.loads(FILE.read_text(encoding='utf-8'))
    if d.get('version')!=1 or not isinstance(d.get('paths'),list):raise ValueError('Invalid fiat registry')
    return [p for p in d['paths'] if isinstance(p,str) and len(p)<4096]

def save(paths):
    HOME.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=HOME/('.fiat_registry_'+secrets.token_hex(8))
    payload=json.dumps({'version':1,'paths':sorted(set(paths))}).encode('utf-8')
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,'wb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
        os.replace(tmp,FILE)
    finally:tmp.unlink(missing_ok=True)
