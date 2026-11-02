"""Sandbox-only double-entry settlement and reconciliation engine.

DESIGN LIMITS: not a bank, custodian, financial account, payment processor, or
production ledger. No live money and no untrusted client-initiated settlement.
Must remain server-only and require real regulated provider APIs before launch.
"""
from __future__ import annotations
import hashlib, json, re, sqlite3, threading, time, uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

CURRENCIES={'USD':2,'EUR':2,'GBP':2,'CAD':2,'AUD':2,'INR':2,'JPY':0,'KRW':0,'KWD':3}
MAX_MINOR=10**12

class FinanceError(ValueError):pass

def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True)

def minor_units(raw, code):
    if code not in CURRENCIES:raise FinanceError('Currency not supported in sandbox accounting')
    try:dec=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError):raise FinanceError('Invalid money amount') from None
    if not dec.is_finite() or dec<=0:raise FinanceError('Amount must be finite and positive')
    unit=Decimal(10)**CURRENCIES[code]
    if dec*unit != (dec*unit).to_integral_value():raise FinanceError('Invalid decimal precision')
    n=int(dec*unit)
    if n>MAX_MINOR:raise FinanceError('Sandbox transaction limit exceeded')
    return n

class SandboxLedger:
    """Transactional reference controls. Use a dedicated protected server DB ONLY.

    Journal sign convention: Debit positive, credit negative, per asset/liability
    account. Provider clearing is an asset; customer_balance is a liability.
    No user-written manual journals, no live account provisioning.
    """
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(self.path),isolation_level=None,timeout=15,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=15000')
        self.lock=threading.RLock()
        self.db.executescript("""
CREATE TABLE IF NOT EXISTS accounts (
 id TEXT PRIMARY KEY, currency TEXT NOT NULL, class TEXT NOT NULL,
 CHECK(class IN ('customer_liability','provider_clearing')));
CREATE TABLE IF NOT EXISTS intents (
 id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
 fingerprint TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES accounts(id),
 provider TEXT NOT NULL, provider_ref TEXT UNIQUE NOT NULL,
 currency TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
 status TEXT NOT NULL CHECK(status IN ('pending','settled','failed','reversed')),
 created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS journals (
 id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES intents(id),
 action TEXT NOT NULL CHECK(action IN ('settlement','reversal')),
 created INTEGER NOT NULL, UNIQUE(intent_id,action));
CREATE TABLE IF NOT EXISTS postings (
 journal_id TEXT NOT NULL REFERENCES journals(id), account_id TEXT NOT NULL REFERENCES accounts(id),
 currency TEXT NOT NULL, delta INTEGER NOT NULL, PRIMARY KEY(journal_id,account_id),
 CHECK(delta != 0));
CREATE TABLE IF NOT EXISTS provider_events (
 provider TEXT NOT NULL, event_id TEXT NOT NULL, intent_id TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL, created INTEGER NOT NULL,
 PRIMARY KEY(provider,event_id));
CREATE TABLE IF NOT EXISTS audit (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, utc INTEGER NOT NULL,
 operation TEXT NOT NULL, detail TEXT NOT NULL, prev_hash TEXT NOT NULL,
 entry_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
 id INTEGER PRIMARY KEY AUTOINCREMENT, audit_seq INTEGER NOT NULL UNIQUE REFERENCES audit(seq),
 event_type TEXT NOT NULL, public_payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','leased','delivered','dead')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
 next_attempt INTEGER NOT NULL, lease_token TEXT, lease_until INTEGER,
 delivered_at INTEGER);
CREATE INDEX IF NOT EXISTS outbox_ready ON outbox(status, next_attempt);
CREATE TABLE IF NOT EXISTS reconciliation_runs (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, statement_id TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, actor TEXT NOT NULL, created INTEGER NOT NULL,
 exception_count INTEGER NOT NULL, UNIQUE(provider, statement_id));
CREATE TABLE IF NOT EXISTS reconciliation_exceptions (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES reconciliation_runs(id),
 ref_sha256 TEXT NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open'
 CHECK(state IN ('open','acknowledged','resolved')),
 maker TEXT, checker TEXT, note TEXT NOT NULL DEFAULT '', modified INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS recon_open ON reconciliation_exceptions(state, run_id);

""")
    def close(self):self.db.close()
    def _begin(self):self.db.execute('BEGIN IMMEDIATE')
    def _append_audit(self,op,details):
        prev=self.db.execute('SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        prior=prev['entry_hash'] if prev else '0'*64
        now=int(time.time())
        content=canonical({'utc':now,'operation':op,'detail':details,'prev_hash':prior})
        digest=hashlib.sha256(content.encode()).hexdigest()
        cur=self.db.execute('INSERT INTO audit(utc,operation,detail,prev_hash,entry_hash) VALUES(?,?,?,?,?)',
                        (now,op,canonical(details),prior,digest))
        # Transactional outbox: no network I/O, funds movement, or secrets.
        # The outbox row commits or rolls back together with the journal/audit record.
        payload=canonical({'audit_seq':cur.lastrowid,'event_type':op,'audit_hash':digest})
        self.db.execute('INSERT INTO outbox(audit_seq,event_type,public_payload,next_attempt) VALUES(?,?,?,?)',
                        (cur.lastrowid,op,payload,now))
    def create_intent(self,*,customer_id,provider,provider_ref,currency,amount,idempotency_key):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{3,72}',customer_id):raise FinanceError('Invalid account identifier')
        if provider not in ('sandbox-stripe','sandbox-paypal','sandbox-bank'):raise FinanceError('Live processors disabled')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{5,120}',provider_ref):raise FinanceError('Invalid provider reference')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{12,128}',idempotency_key):raise FinanceError('Invalid idempotency key')
        cents=minor_units(amount,currency)
        acc='customer:'+customer_id+':'+currency
        intent_body={'customer_id':customer_id,'provider':provider,'provider_ref':provider_ref,'currency':currency,'amount_minor':cents}
        fp=hashlib.sha256(canonical(intent_body).encode()).hexdigest()
        with self.lock:
            self._begin()
            try:
                existing=self.db.execute('SELECT * FROM intents WHERE idempotency_key=?',(idempotency_key,)).fetchone()
                if existing:
                    if existing['fingerprint']!=fp:raise FinanceError('Idempotency conflict: request details changed')
                    self.db.commit();return dict(existing)
                own_ref=self.db.execute('SELECT id FROM intents WHERE provider_ref=?',(provider_ref,)).fetchone()
                if own_ref:raise FinanceError('Provider reference already belongs to a transaction')
                self.db.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?)',(acc,currency,'customer_liability'))
                self.db.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?)',('clearing:'+provider+':'+currency,currency,'provider_clearing'))
                id_=str(uuid.uuid4())
                self.db.execute('INSERT INTO intents VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (id_,idempotency_key,fp,acc,provider,provider_ref,currency,cents,'pending',int(time.time())))
                self._append_audit('intent.created',{'intent_id':id_,'provider':provider,'currency':currency,'minor':cents})
                self.db.commit()
                return dict(self.db.execute('SELECT * FROM intents WHERE id=?',(id_,)).fetchone())
            except BaseException:self.db.rollback();raise
    def _journal(self,record,action):
        id_=str(uuid.uuid4())
        self.db.execute('INSERT INTO journals VALUES(?,?,?,?)',(id_,record['id'],action,int(time.time())))
        value=record['amount_minor'] if action=='settlement' else -record['amount_minor']
        # Debit clearing asset, credit customer liability; reverse for refund.
        rows=[('clearing:'+record['provider']+':'+record['currency'],value),
              (record['account_id'],-value)]
        assert sum(v for _,v in rows)==0
        self.db.executemany('INSERT INTO postings VALUES(?,?,?,?)',
            [(id_,acc,record['currency'],delta) for acc,delta in rows])
    def record_authenticated_event(self,*,provider,event_id,intent_id,provider_ref,currency,minor,status,payload_sha256):
        """Use only after transport's provider signature, timestamp and body verified.
        Passing this method from a client is insecure; this is a server-internal API.
        Provider verified status is treated as an input from trusted middleware.
        """
        if not re.fullmatch(r'[a-zA-Z0-9_-]{6,128}',event_id):raise FinanceError('Bad event ID')
        if status not in ('settled','failed','reversed'):raise FinanceError('Unrecognized provider state')
        if not re.fullmatch(r'[a-f0-9]{64}',payload_sha256):raise FinanceError('Event digest required')
        with self.lock:
            self._begin()
            try:
                record=self.db.execute('SELECT * FROM intents WHERE id=?',(intent_id,)).fetchone()
                if record is None:raise FinanceError('Unknown payment intent')
                if provider!=record['provider'] or provider_ref!=record['provider_ref'] or currency!=record['currency'] or type(minor) is not int or minor!=record['amount_minor']:
                    raise FinanceError('Provider event does not match intent')
                old=self.db.execute('SELECT payload_sha256 FROM provider_events WHERE provider=? AND event_id=?',(provider,event_id)).fetchone()
                if old:
                    if old['payload_sha256']!=payload_sha256:raise FinanceError('Replayed event ID with different body')
                    self.db.commit();return dict(record)
                old_state=record['status']
                allowed={'pending':('settled','failed'), 'settled':('reversed',), 'failed':(), 'reversed':()}
                if status!=old_state and status not in allowed[old_state]:raise FinanceError('Illegal payment state transition')
                self.db.execute('INSERT INTO provider_events VALUES(?,?,?,?,?)',
                                (provider,event_id,intent_id,payload_sha256,int(time.time())))
                if old_state!=status:
                    if status=='settled':self._journal(record,'settlement')
                    if status=='reversed':self._journal(record,'reversal')
                    self.db.execute('UPDATE intents SET status=? WHERE id=?',(status,intent_id))
                self._append_audit('provider.event',{'event_id_sha256':hashlib.sha256(event_id.encode()).hexdigest(),
                                      'intent_id':intent_id,'from':old_state,'to':status})
                self.db.commit()
                return dict(self.db.execute('SELECT * FROM intents WHERE id=?',(intent_id,)).fetchone())
            except BaseException:self.db.rollback();raise
    def verify_integrity(self):
        problems=[]
        prev='0'*64
        for r in self.db.execute('SELECT * FROM audit ORDER BY seq'):
            if r['prev_hash']!=prev:problems.append('Audit chain broken at entry '+str(r['seq']))
            calculated=hashlib.sha256(canonical({'utc':r['utc'],'operation':r['operation'],
                         'detail':json.loads(r['detail']),'prev_hash':r['prev_hash']}).encode()).hexdigest()
            if calculated!=r['entry_hash']:problems.append('Audit entry altered: '+str(r['seq']))
            prev=r['entry_hash']
        for r in self.db.execute('SELECT a.seq, a.operation,a.entry_hash,o.id,o.event_type,o.public_payload FROM audit a LEFT JOIN outbox o ON a.seq=o.audit_seq'):
            if r['id'] is None:
                problems.append('Missing durable outbox audit link '+str(r['seq']))
                continue
            expected=canonical({'audit_seq':r['seq'],'event_type':r['operation'],'audit_hash':r['entry_hash']})
            if r['event_type']!=r['operation'] or r['public_payload']!=expected:
                problems.append('Outbox audit linkage mismatch '+str(r['seq']))
        for r in self.db.execute('SELECT j.id AS id,SUM(p.delta) AS net,COUNT(p.delta) AS n FROM journals j LEFT JOIN postings p ON p.journal_id=j.id GROUP BY j.id'):
            if r['n']!=2 or r['net']!=0:problems.append('Unbalanced journal '+r['id'])
        for r in self.db.execute('SELECT p.account_id AS id FROM postings p JOIN accounts a ON a.id=p.account_id WHERE p.currency!=a.currency'):
            problems.append('Currency mismatch '+r['id'])
        for r in self.db.execute('SELECT id,status FROM intents'):
            n=self.db.execute('SELECT action FROM journals WHERE intent_id=?',(r['id'],)).fetchall()
            acts={x['action'] for x in n}
            correct={'pending':set(),'failed':set(),'settled':{'settlement'},'reversed':{'settlement','reversal'}}[r['status']]
            if acts!=correct or len(n)!=len(correct):problems.append('Intent/journal mismatch '+r['id'])
        return problems
    def customer_balance(self,customer_id,currency):
        if currency not in CURRENCIES:raise FinanceError('Unsupported currency')
        acc='customer:'+customer_id+':'+currency
        row=self.db.execute('SELECT COALESCE(SUM(p.delta),0) AS amount FROM postings p WHERE account_id=?',(acc,)).fetchone()
        return -row['amount'] # liability credit is positive customer displayed balance
    def reconcile(self,provider_records):
        """Reconcile authoritative provider records supplied by separate adapter.
        Returns exceptions, never edits balances based on imported data alone.
        """
        errors=[]
        for ext in provider_records:
            ref=ext.get('provider_ref')
            rec=self.db.execute('SELECT * FROM intents WHERE provider_ref=?',(ref,)).fetchone()
            if not rec:errors.append({'provider_ref':ref,'error':'missing_internal_intent'});continue
            if rec['provider']!=ext.get('provider') or rec['currency']!=ext.get('currency') or rec['amount_minor']!=ext.get('minor'):
                errors.append({'provider_ref':ref,'error':'amount_currency_or_provider_mismatch'});continue
            if rec['status']!=ext.get('status'):
                errors.append({'provider_ref':ref,'error':'status_mismatch','ledger_status':rec['status']})
        return errors
