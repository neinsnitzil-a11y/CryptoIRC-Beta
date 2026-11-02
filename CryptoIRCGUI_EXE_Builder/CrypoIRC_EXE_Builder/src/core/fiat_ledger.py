"""Offline encrypted FIAT ledger; NOT a bank account, e-money account, or payment rail.

The only operations are writing user-entered entries and calculating balances.
There is intentionally no bank account number or fiat receiving address generation.
"""
from __future__ import annotations
import json, os, secrets
from decimal import Decimal, InvalidOperation
from pathlib import Path
from datetime import datetime,timezone
from . import vaultforge as vf
from .assets import FIAT
from .exchange_engine import CURRENCY_CATALOG

CODES={c for c,_ in FIAT}
MAX_ENTRIES=10000

def read(path: str|Path,password: str) -> dict:
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.suffix!='.fiat':
        raise ValueError('Invalid .fiat account file')
    data=vf.decrypt_payload(p.read_bytes(),password)
    if data.get('format')!='Crypto-Fiat-Ledger-v1' or data.get('currency') not in CODES:
        raise ValueError('Not a supported fiat ledger')
    if not isinstance(data.get('entries'),list) or len(data['entries'])>MAX_ENTRIES:
        raise ValueError('Invalid ledger contents')
    return data

def new(folder: str,currency: str,name: str,password: str) -> str:
    if currency not in CODES:raise ValueError('Unknown fiat currency')
    if len(password)<14:raise ValueError('Password requires 14+ characters')
    name=name.strip()
    if not (1<=len(name)<=80):raise ValueError('Account label must be 1–80 characters')
    folder=vf.secure_dir(Path(folder).expanduser().resolve())
    data={'format':'Crypto-Fiat-Ledger-v1','currency':currency,'label':name,
          'created_utc':datetime.now(timezone.utc).isoformat(),'entries':[],
          'notice':'Manual offline bookkeeping ONLY, not a bank or provider-backed wallet'}
    p=folder / ('fiat_'+secrets.token_hex(10)+'.fiat')
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
    if hasattr(os,'O_NOFOLLOW'):flags |= os.O_NOFOLLOW
    fd=os.open(p,flags,0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(vf.encrypt_payload(data,password));f.flush();os.fsync(f.fileno())
    except BaseException:
        p.unlink(missing_ok=True);raise
    return str(p)

def balance(data: dict) -> Decimal:
    return sum((Decimal(e['amount']) for e in data['entries']),Decimal('0'))

def append(path:str|Path,password:str,kind:str,amount:str,memo:str) -> dict:
    if kind not in ('Money in','Money out','Adjustment +','Adjustment -'):
        raise ValueError('Unknown entry kind')
    try:value=Decimal(amount)
    except (InvalidOperation,ValueError):raise ValueError('Invalid amount')
    if not value.is_finite() or not Decimal('0.00')<value<=Decimal('1000000000000'):
        raise ValueError('Amount must be positive and finite')
    if len(memo)>200:raise ValueError('Memo must be at most 200 characters')
    d=read(path,password)
    prec=CURRENCY_CATALOG[d['currency']]['precision']
    if value != value.quantize(Decimal(1).scaleb(-prec)):
        raise ValueError(f'{d["currency"]} requires no more than {prec} decimal places')
    if len(d['entries'])>=MAX_ENTRIES:raise ValueError('Ledger entry limit reached')
    if kind in ('Money out','Adjustment -'):value=-value
    d['entries'].append({'utc':datetime.now(timezone.utc).isoformat(),'kind':kind,
                         'amount':str(value),'memo':memo.strip()})
    # Atomic replacement without ever writing unencrypted data.
    vf.update_password(Path(path),d,password)
    return d
