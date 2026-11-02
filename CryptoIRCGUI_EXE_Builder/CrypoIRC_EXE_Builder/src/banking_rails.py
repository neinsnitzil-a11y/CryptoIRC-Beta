"""Phase 11: non-custodial desktop requests and loopback sandbox gateway client.

No bank credentials, account numbers, real fiat balance, money movement, or
provider webhook authorizations are accepted from the desktop application.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import closing
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

class RailError(ValueError): pass

CURRENCIES = {'USD':2, 'EUR':2, 'GBP':2, 'CAD':2, 'AUD':2, 'JPY':0}
FLOWS = {'DEPOSIT','WITHDRAWAL'}
LOCAL_STATUSES = {'DRAFT','SUBMITTED_TO_SANDBOX','CANCELLED','NEEDS_REVIEW'}
MAX_MINOR = 10**11
ID_RE = re.compile(r'[A-Za-z0-9_-]{8,100}\Z')


def minor_units(value, currency):
    if currency not in CURRENCIES: raise RailError('Unsupported fiat currency')
    if type(value) is not str or len(value)>40: raise RailError('Invalid amount')
    try: amount=Decimal(value)
    except (InvalidOperation, ValueError): raise RailError('Invalid amount') from None
    scale=10**CURRENCIES[currency]
    units=amount*scale
    if not amount.is_finite() or units!=units.to_integral_value() or not 1<=units<=MAX_MINOR:
        raise RailError('Amount must have valid precision and be positive')
    return int(units)


def printable_amount(minor,currency):
    if currency not in CURRENCIES or type(minor) is not int or minor<0: raise RailError('Invalid amount')
    precision=CURRENCIES[currency]
    return f'{Decimal(minor).scaleb(-precision):.{precision}f}'


def validate_reference(reference):
    # User-facing local label. Never accept actual bank routing/account numbers.
    if type(reference) is not str or not 1<=len(reference)<=48 or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9 ._-]{0,47}',reference):
        raise RailError('Use a public account label, not bank account or routing numbers')
    if len(re.sub(r'\D','',reference))>=8:
        raise RailError('Do not enter bank account numbers')
    return reference


class RailRequests:
    """DESKTOP ONLY: can never store a provider settlement or update a balance."""
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with closing(self._db()) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS rails_requests(
                id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, flow TEXT NOT NULL,
                currency TEXT NOT NULL, minor INTEGER NOT NULL, label TEXT NOT NULL,
                status TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL)''')
    def _db(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        return con
    def create(self,*,flow,currency,amount,label,key=None):
        if flow not in FLOWS:raise RailError('Invalid rail flow')
        m=minor_units(amount,currency)
        label=validate_reference(label)
        key=key or str(uuid.uuid4())
        if not ID_RE.fullmatch(key): raise RailError('Invalid idempotency key')
        uid=str(uuid.uuid4()); now=int(time.time())
        with closing(self._db()) as con:
            with con:
                con.execute('BEGIN IMMEDIATE')
                found=con.execute('SELECT * FROM rails_requests WHERE key=?',(key,)).fetchone()
                if found:
                    if (found['flow'],found['currency'],found['minor'],found['label'])!=(flow,currency,m,label):
                        raise RailError('Idempotency key reused for different transfer')
                    return dict(found)
                con.execute('INSERT INTO rails_requests VALUES(?,?,?,?,?,?,?,?,?)',
                            (uid,key,flow,currency,m,label,'DRAFT',now,now))
                return dict(con.execute('SELECT * FROM rails_requests WHERE id=?',(uid,)).fetchone())
    def list(self,limit=30):
        with closing(self._db()) as con:
            return [dict(r) for r in con.execute('SELECT * FROM rails_requests ORDER BY created DESC, id DESC LIMIT ?',
                (min(max(1,int(limit)),100),))]
    def get(self,uid):
        with closing(self._db()) as con:
            r=con.execute('SELECT * FROM rails_requests WHERE id=?',(uid,)).fetchone()
            return dict(r) if r else None
    def state(self,uid,status):
        if status not in {'SUBMITTED_TO_SANDBOX','CANCELLED','NEEDS_REVIEW'}:
            raise RailError('Client cannot assert settlement or completion')
        with closing(self._db()) as con:
            with con:
                con.execute('BEGIN IMMEDIATE')
                row=con.execute('SELECT status FROM rails_requests WHERE id=?',(uid,)).fetchone()
                if not row:raise RailError('Unknown request')
                before=row['status']
                if before=='CANCELLED' or (status=='SUBMITTED_TO_SANDBOX' and before not in ('DRAFT','SUBMITTED_TO_SANDBOX')):
                    raise RailError('Invalid local transition')
                con.execute('UPDATE rails_requests SET status=?,updated=? WHERE id=?',(status,int(time.time()),uid))


class SandboxRailsClient:
    """Explicitly loopback only. No live provider/customer credentials in EXE."""
    def __init__(self,endpoint,token):
        u=urlsplit(endpoint)
        if (u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost')
            or u.username or u.password or u.path not in ('','/') or u.query or u.fragment
            or not u.port):
            raise RailError('Sandbox gateway must be a local loopback HTTP service')
        if type(token) is not str or len(token)<32: raise RailError('Missing sandbox gateway access token')
        self.root=f'http://127.0.0.1:{u.port}'
        self.token=token
    def _request(self,method,path,payload=None):
        data=None if payload is None else json.dumps(payload,separators=(',',':')).encode('utf-8')
        req=Request(self.root+path,data=data,method=method,
            headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=5) as r:
                if r.status!=200:raise RailError('Gateway unavailable')
                raw=r.read(16000)
                obj=json.loads(raw)
                if not isinstance(obj,dict) or obj.get('environment')!='sandbox':raise RailError('Unexpected response')
                return obj
        except (OSError, ValueError) as exc:
            raise RailError('Sandbox gateway unavailable or rejected request') from None
    def create(self,request):
        return self._request('POST','/v1/sandbox/rails/intents',
            {k:request[k] for k in ('id','flow','currency','minor','label')})
    def status(self,uid):
        if not ID_RE.fullmatch(uid):raise RailError('Invalid request ID')
        return self._request('GET','/v1/sandbox/rails/intents/'+uid)
