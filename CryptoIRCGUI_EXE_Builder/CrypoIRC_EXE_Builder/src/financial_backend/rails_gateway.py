"""ISOLATED TEST-ONLY bank/payment-rails gateway.

Not a bank, payment processor, or provider adapter. Never installed in the
customer EXE. No API in this module can transfer or credit real money.
"""
from __future__ import annotations
import hashlib,hmac,json,os,re,sqlite3,time
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

class GatewayError(ValueError): pass
EVENT_TYPES={'test.deposit.settled':'TEST_SETTLED',
             'test.withdrawal.paid':'TEST_PAID',
             'test.payment.failed':'TEST_FAILED',
             'test.payment.returned':'TEST_RETURNED',
             'test.payment.processing':'TEST_PROCESSING'}
EVENT_RE=re.compile('[A-Za-z0-9_-]{8,100}\\Z')
ALLOWED={'TEST_PENDING':{'TEST_PROCESSING','TEST_SETTLED','TEST_PAID','TEST_FAILED'},
         'TEST_PROCESSING':{'TEST_SETTLED','TEST_PAID','TEST_FAILED','TEST_RETURNED'},
         'TEST_SETTLED':{'TEST_RETURNED'}, 'TEST_PAID':{'TEST_RETURNED'},
         'TEST_FAILED':set(), 'TEST_RETURNED':set()}

class SandboxRailLedger:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with closing(self._db()) as con:
            with con:
                con.execute('''CREATE TABLE IF NOT EXISTS intents(
                    id TEXT PRIMARY KEY,flow TEXT NOT NULL,currency TEXT NOT NULL,
                    minor INTEGER NOT NULL,label_fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL,
                    provider_ref TEXT NOT NULL DEFAULT '')''')
                con.execute('''CREATE TABLE IF NOT EXISTS events(
                    event_id TEXT PRIMARY KEY,intent_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,created INTEGER NOT NULL)''')
    def _db(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        return con
    def create(self,rec):
        from banking_rails import ID_RE,FLOWS,CURRENCIES,MAX_MINOR,validate_reference
        if type(rec) is not dict or set(rec)!={'id','flow','currency','minor','label'}:raise GatewayError('Invalid intent')
        if type(rec['id']) is not str or not ID_RE.fullmatch(rec['id']):raise GatewayError('Invalid ID')
        if rec['flow'] not in FLOWS or rec['currency'] not in CURRENCIES or type(rec['minor']) is not int or not 1<=rec['minor']<=MAX_MINOR:
            raise GatewayError('Invalid intent attributes')
        label=validate_reference(rec['label'])
        fingerprint=hashlib.sha256(label.encode()).hexdigest()
        now=int(time.time())
        with closing(self._db()) as con:
            with con:
                con.execute('BEGIN IMMEDIATE')
                old=con.execute('SELECT * FROM intents WHERE id=?',(rec['id'],)).fetchone()
                if old:
                    if (old['flow'],old['currency'],old['minor'],old['label_fingerprint'])!=(rec['flow'],rec['currency'],rec['minor'],fingerprint):
                        raise GatewayError('Conflicting idempotent request')
                    return self._public(old)
                con.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,?,?,?)',
                    (rec['id'],rec['flow'],rec['currency'],rec['minor'],fingerprint,'TEST_PENDING',now,now,''))
                return self._public(con.execute('SELECT * FROM intents WHERE id=?',(rec['id'],)).fetchone())
    @staticmethod
    def _public(r):
        return {k:r[k] for k in ('id','flow','currency','minor','state','created','updated') }|{'environment':'sandbox','real_funds_transferred':False}
    def get(self,uid):
        if not EVENT_RE.fullmatch(uid):raise GatewayError('Invalid ID')
        with closing(self._db()) as con:
            r=con.execute('SELECT * FROM intents WHERE id=?',(uid,)).fetchone()
            if not r:raise GatewayError('Unknown intent')
            return self._public(r)
    def accept_event(self,raw,header,secret,now=None):
        if type(raw) is not bytes or len(raw)>16_384 or not raw:raise GatewayError('Invalid event body')
        if type(secret) is not str or len(secret)<32:raise GatewayError('Missing event secret')
        if type(header) is not str or len(header)>1024:raise GatewayError('Missing event signature')
        parts={}
        for item in header.split(','):
            part=item.strip().split('=',1)
            if len(part)==2:parts.setdefault(part[0],[]).append(part[1])
        stamps=parts.get('t',[]);signatures=parts.get('v1',[])
        if len(stamps)!=1 or not stamps[0].isdigit() or not signatures:raise GatewayError('Invalid event signature')
        stamp=int(stamps[0]);current=int(time.time() if now is None else now)
        if abs(current-stamp)>300:raise GatewayError('Stale event')
        expected=hmac.new(secret.encode(),str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        if not any(re.fullmatch('[a-f0-9]{64}',sig) and hmac.compare_digest(expected,sig) for sig in signatures):
            raise GatewayError('Event authentication failed')
        try:event=json.loads(raw)
        except (ValueError,UnicodeError):raise GatewayError('Invalid signed event') from None
        if type(event) is not dict or set(event)!={'event_id','intent_id','type','currency','minor','provider_ref','environment'} or event.get('environment')!='sandbox':
            raise GatewayError('Invalid event schema')
        if not all(type(event[k]) is str and EVENT_RE.fullmatch(event[k]) for k in ('event_id','intent_id','provider_ref')):
            raise GatewayError('Invalid signed references')
        etype=event['type']
        if etype not in EVENT_TYPES or type(event['minor']) is not int or event['minor']<1:raise GatewayError('Invalid event type/amount')
        digest=hashlib.sha256(raw).hexdigest()
        with closing(self._db()) as con:
            with con:
                con.execute('BEGIN IMMEDIATE')
                duplicate=con.execute('SELECT * FROM events WHERE event_id=?',(event['event_id'],)).fetchone()
                if duplicate:
                    if duplicate['payload_sha256']!=digest or duplicate['intent_id']!=event['intent_id']:
                        raise GatewayError('Event replay with changed content')
                    return self._public(con.execute('SELECT * FROM intents WHERE id=?',(duplicate['intent_id'],)).fetchone())
                old=con.execute('SELECT * FROM intents WHERE id=?',(event['intent_id'],)).fetchone()
                if not old:raise GatewayError('Event does not reference an existing intent')
                if old['currency']!=event['currency'] or old['minor']!=event['minor']:
                    raise GatewayError('Currency or amount mismatch — manual reconciliation required')
                state=EVENT_TYPES[etype]
                if state=='TEST_SETTLED' and old['flow']!='DEPOSIT':raise GatewayError('Deposit event on withdrawal')
                if state=='TEST_PAID' and old['flow']!='WITHDRAWAL':raise GatewayError('Payout event on deposit')
                if state not in ALLOWED.get(old['state'],set()):raise GatewayError('Invalid financial state transition')
                if old['provider_ref'] and old['provider_ref']!=event['provider_ref']:
                    raise GatewayError('Different provider reference')
                con.execute('UPDATE intents SET state=?,updated=?,provider_ref=? WHERE id=?',
                    (state,current,event['provider_ref'],old['id']))
                con.execute('INSERT INTO events VALUES(?,?,?,?)',(event['event_id'],old['id'],digest,current))
                return self._public(con.execute('SELECT * FROM intents WHERE id=?',(old['id'],)).fetchone())


    def accept_stripe_test_event(self,raw,header,endpoint_secret,internal_secret,now=None):
        """Ingest a real Stripe *test-mode* webhook after raw-body signature verification.

        This records provider TEST evidence, not fiat custody or blockchain credit.
        No desktop API can call this method without a separately deployed backend.
        """
        from .stripe_test_adapter import verify_stripe_signature
        from .ledger import FinanceError
        try: evt=verify_stripe_signature(raw,header,endpoint_secret,now=now)
        except FinanceError:raise GatewayError('Stripe test webhook not authenticated') from None
        kinds={'payment_intent.processing':'test.payment.processing',
               'payment_intent.succeeded':'test.deposit.settled',
               'payment_intent.payment_failed':'test.payment.failed'}
        kind=kinds.get(evt.get('type'))
        obj=(evt.get('data') or {}).get('object')
        if (not kind or evt.get('livemode') is not False or type(obj) is not dict
            or obj.get('object')!='payment_intent' or obj.get('livemode') is not False):
            raise GatewayError('Only authenticated Stripe TEST payment-intent events are supported')
        expected={'payment_intent.processing':'processing',
                  'payment_intent.succeeded':'succeeded',
                  'payment_intent.payment_failed':'requires_payment_method'}
        if obj.get('status')!=expected[evt['type']]:raise GatewayError('Inconsistent payment-intent state')
        request_id=(obj.get('metadata') or {}).get('nocturne_rail_intent_id')
        event_id=evt.get('id'); ref=obj.get('id')
        if not all(type(v) is str and EVENT_RE.fullmatch(v) for v in (request_id,event_id,ref)):
            raise GatewayError('Missing bound payment references')
        amount=obj.get('amount_received') if kind=='test.deposit.settled' else obj.get('amount')
        currency=obj.get('currency')
        if type(amount) is not int or amount<=0 or type(currency) is not str or not re.fullmatch('[a-z]{3}',currency):
            raise GatewayError('Invalid verified payment amounts')
        normalized={'event_id':event_id,'intent_id':request_id,'type':kind,
                    'currency':currency.upper(),'minor':amount,'provider_ref':ref,
                    'environment':'sandbox'}
        if kind=='test.deposit.settled' and obj.get('amount_received')!=obj.get('amount'):
            raise GatewayError('Partial payment requires manual reconciliation')
        payload=json.dumps(normalized,separators=(',',':')).encode()
        stamped=int(time.time() if now is None else now)
        mac=hmac.new(internal_secret.encode(),str(stamped).encode()+b'.'+payload,hashlib.sha256).hexdigest()
        return self.accept_event(payload,f't={stamped},v1={mac}',internal_secret,now=stamped)


def make_handler(ledger,token,webhook_secret,stripe_test_secret=""):
    if len(token)<32 or len(webhook_secret)<32:raise GatewayError('Secure test credentials required')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass # URLs or refs must never enter logs
        def _response(self,code,result):
            data=json.dumps(result,separators=(',',':')).encode()
            self.send_response(code)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
        def _auth(self):
            supplied=self.headers.get('Authorization','')
            return hmac.compare_digest(supplied,'Bearer '+token)
        def do_GET(self):
            if not self._auth():self._response(401,{'error':'Unauthorized'});return
            path=urlsplit(self.path).path
            if not path.startswith('/v1/sandbox/rails/intents/'):
                self._response(404,{'error':'Not found'});return
            try:record=ledger.get(path.rsplit('/',1)[1]);self._response(200,record)
            except GatewayError:self._response(404,{'error':'Not found'})
        def do_POST(self):
            path=urlsplit(self.path).path
            if path not in ('/v1/sandbox/rails/intents','/v1/sandbox/rails/events','/v1/sandbox/rails/stripe-test-webhook'):
                self._response(404,{'error':'Not found'});return
            if path.endswith('intents') and not self._auth():self._response(401,{'error':'Unauthorized'});return
            try:
                length=int(self.headers.get('Content-Length','-1'))
                if length<1 or length>16_384:raise GatewayError('Invalid length')
                raw=self.rfile.read(length)
                if path.endswith('intents'):
                    rec=ledger.create(json.loads(raw));self._response(200,rec)
                elif path.endswith('stripe-test-webhook'):
                    if not stripe_test_secret:
                        self._response(404,{'error':'Not available'});return
                    rec=ledger.accept_stripe_test_event(raw,self.headers.get('Stripe-Signature',''),stripe_test_secret,webhook_secret)
                    self._response(200,rec)
                else:
                    rec=ledger.accept_event(raw,self.headers.get('X-Nocturne-Test-Signature',''),webhook_secret)
                    self._response(200,rec)
            except (GatewayError,TypeError,ValueError,KeyError,UnicodeError):
                self._response(400,{'error':'Invalid sandbox request'})
    return Handler


def serve_loopback(port=18450):
    token=os.environ.get('NOCTURNE_RAILS_TOKEN','')
    secret=os.environ.get('NOCTURNE_RAILS_TEST_WEBHOOK_SECRET','')
    if len(token)<32 or len(secret)<32:raise RuntimeError('Set separate random server-only sandbox secrets (32+ characters)')
    db=Path(os.environ.get('NOCTURNE_RAILS_DB',str(Path.home()/'.crypto_nocturne'/'rails_sandbox.sqlite3')))
    stripe_test_secret=os.environ.get('NOCTURNE_STRIPE_TEST_WEBHOOK_SECRET','')
    if stripe_test_secret and not (stripe_test_secret.startswith('whsec_') and len(stripe_test_secret)>=24):
        raise RuntimeError('Stripe test webhook signing secret is invalid')
    server=ThreadingHTTPServer(('127.0.0.1',int(port)),make_handler(SandboxRailLedger(db),token,secret,stripe_test_secret))
    try:server.serve_forever(poll_interval=.2)
    finally:server.server_close()

if __name__=='__main__':serve_loopback(int(os.environ.get('NOCTURNE_RAILS_PORT','18450')))
