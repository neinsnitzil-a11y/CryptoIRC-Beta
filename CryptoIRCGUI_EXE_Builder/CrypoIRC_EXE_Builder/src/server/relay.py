"""Optional self-hosted encrypted envelope relay for CRYPTO WAN chat.

SERVER HAS NO CHAT DECRYPTION KEYS AND DOES NOT INTERACT WITH WALLET FILES.
Deploy behind a real HTTPS reverse proxy; development HTTP is localhost only.
This demonstration relay is NOT security audited or hardened for public deployment.
"""
from __future__ import annotations
import hashlib,json,os,re,sqlite3,threading,time,uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from cryptography.hazmat.primitives.asymmetric import ed25519
from core.wan_chat import canonical, validate_card
from core.lan_chat import check_room

ONLINE_SECONDS=65
MAX_MAIL=150
MAX_ROOMS=8
MAX_ROOM_USERS=32
KEEP_SECONDS=7*24*3600


def create_app(db_path=None):
    db_path=str(db_path or os.getenv('CRYPTO_RELAY_DATABASE','relay_chat.sqlite3'))
    Path(db_path).parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(db_path,check_same_thread=False,timeout=6)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS people(fp TEXT PRIMARY KEY, card TEXT NOT NULL, lastseen INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS rooms(fp TEXT NOT NULL, room TEXT NOT NULL, PRIMARY KEY (fp,room));
      CREATE TABLE IF NOT EXISTS mail(id TEXT PRIMARY KEY,sender TEXT NOT NULL,recipient TEXT NOT NULL,
          payload TEXT NOT NULL,created INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS auth_nonces(fp TEXT NOT NULL,nonce TEXT NOT NULL,at INTEGER NOT NULL,
          PRIMARY KEY (fp,nonce));
      CREATE INDEX IF NOT EXISTS mail_recipient ON mail(recipient,created);
    ''')
    conn.commit()
    lock=threading.RLock()
    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            conn.close()
    app=FastAPI(title='CRYPTO encrypted chat relay (experimental)',docs_url=None,
                redoc_url=None,lifespan=lifespan)
    app.state.db=conn

    @app.middleware('http')
    async def size_limit(req, call_next):
        if int(req.headers.get('content-length','0'))>11000:
            raise HTTPException(413,'Request too large')
        return await call_next(req)

    def prune(now):
        conn.execute('DELETE FROM mail WHERE created < ?', (now-KEEP_SECONDS,))
        conn.execute('DELETE FROM auth_nonces WHERE at < ?', (now-300,))
        conn.execute('DELETE FROM people WHERE lastseen < ?', (now-30*24*3600,))
        conn.execute('DELETE FROM rooms WHERE fp NOT IN (SELECT fp FROM people)')

    async def auth(req):
        body=await req.body()
        if len(body)>11000:raise HTTPException(413,'Body too large')
        pubhex=req.headers.get('x-crypto-identity','')
        timestamp=req.headers.get('x-crypto-time','')
        nonce=req.headers.get('x-crypto-nonce','')
        signature=req.headers.get('x-crypto-signature','')
        if not re.fullmatch('[0-9a-f]{64}',pubhex) or not re.fullmatch('[0-9]{10}',timestamp):
            raise HTTPException(401,'Invalid identity headers')
        if not re.fullmatch('[0-9a-f-]{36}',nonce) or not re.fullmatch('[0-9a-f]{128}',signature):
            raise HTTPException(401,'Invalid authentication')
        now=int(time.time()); ts=int(timestamp)
        if abs(now-ts)>120:raise HTTPException(401,'Clock skew too large')
        path=req.url.path+('?' + req.url.query if req.url.query else '')
        material=canonical({'method':req.method,'path':path,'digest':hashlib.sha256(body).hexdigest(),
                            'time':timestamp,'nonce':nonce})
        try:ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubhex)).verify(
            bytes.fromhex(signature),material)
        except Exception:raise HTTPException(401,'Signature invalid')
        fp=hashlib.sha256(bytes.fromhex(pubhex)).hexdigest()
        with lock:
            try:
                conn.execute('INSERT INTO auth_nonces VALUES (?,?,?)',(fp,nonce,ts))
                prune(now)
                conn.commit()
            except sqlite3.IntegrityError:raise HTTPException(401,'Repeated request')
            if req.url.path!='/v1/register':
                row=conn.execute('SELECT card FROM people WHERE fp=?',(fp,)).fetchone()
                if not row or json.loads(row[0])['sign_pub']!=pubhex:
                    raise HTTPException(401,'Unregistered identity')
                conn.execute('UPDATE people SET lastseen=? WHERE fp=?',(now,fp))
                conn.commit()
        return fp

    @app.get('/health')
    def health():return {'status':'up','wallet_access':False,'storage':'encrypted envelopes'}

    @app.post('/v1/register')
    async def register(req:Request):
        fp=await auth(req)
        try:card=(await req.json())['card'];verified=validate_card(card)
        except Exception:raise HTTPException(400,'Invalid signed public card')
        if verified!=fp:raise HTTPException(403,'Card does not belong to requester')
        now=int(time.time())
        with lock:
            existing=conn.execute('SELECT card FROM people WHERE fp=?',(fp,)).fetchone()
            if existing and json.loads(existing[0])['enc_pub']!=card['enc_pub']:
                raise HTTPException(409,'Identity encryption key changed')
            conn.execute('INSERT OR REPLACE INTO people VALUES (?,?,?)',(fp,json.dumps(card),now))
            conn.commit()
        return {'registered':True,'fingerprint':fp,'online':True}

    @app.post('/v1/heartbeat')
    async def heartbeat(req:Request):
        await auth(req)
        return {'ok':True}

    @app.get('/v1/directory')
    async def directory(req:Request):
        await auth(req)
        cutoff=int(time.time())-ONLINE_SECONDS
        with lock:
            users=[{'fingerprint':fp,'card':json.loads(card),'online':ts>=cutoff}
                   for fp,card,ts in conn.execute('SELECT fp,card,lastseen FROM people ORDER BY lastseen DESC LIMIT 200')]
        return {'users':users,'presence_note':'Relay-observed heartbeat; not proof user is at keyboard'}

    @app.post('/v1/room/join')
    async def join(req:Request):
        fp=await auth(req)
        try:room=check_room((await req.json())['room'])
        except Exception:raise HTTPException(400,'Invalid room')
        with lock:
            if conn.execute('SELECT COUNT(*) FROM rooms WHERE fp=?',(fp,)).fetchone()[0]>=MAX_ROOMS:
                if not conn.execute('SELECT 1 FROM rooms WHERE fp=? AND room=?',(fp,room)).fetchone():
                    raise HTTPException(400,'Room limit reached')
            if conn.execute('SELECT COUNT(*) FROM rooms WHERE room=?',(room,)).fetchone()[0]>=MAX_ROOM_USERS:
                if not conn.execute('SELECT 1 FROM rooms WHERE fp=? AND room=?',(fp,room)).fetchone():
                    raise HTTPException(400,'Room full')
            conn.execute('INSERT OR IGNORE INTO rooms VALUES (?,?)',(fp,room));conn.commit()
        return {'joined':room}

    @app.post('/v1/room/leave')
    async def leave(req:Request):
        fp=await auth(req)
        try:room=check_room((await req.json())['room'])
        except Exception:raise HTTPException(400,'Invalid room')
        with lock:
            conn.execute('DELETE FROM rooms WHERE fp=? AND room=?',(fp,room));conn.commit()
        return {'left':room}

    @app.get('/v1/room/members')
    async def members(req:Request):
        fp=await auth(req)
        try:room=check_room(req.query_params['room'])
        except Exception:raise HTTPException(400,'Invalid room')
        with lock:
            if not conn.execute('SELECT 1 FROM rooms WHERE fp=? AND room=?',(fp,room)).fetchone():
                raise HTTPException(403,'Join the room first')
            rows=conn.execute('''SELECT p.fp,p.card,p.lastseen FROM rooms r JOIN people p ON r.fp=p.fp
                                 WHERE r.room=? LIMIT ?''',(room,MAX_ROOM_USERS)).fetchall()
        return {'room':room,'users':[{'fingerprint':a,'card':json.loads(b),'online':c>=int(time.time())-ONLINE_SECONDS}
                                     for a,b,c in rows]}

    @app.post('/v1/send')
    async def send(req:Request):
        fp=await auth(req)
        try:e=(await req.json())['envelope']
        except Exception:raise HTTPException(400,'Missing encrypted envelope')
        if not isinstance(e,dict) or set(e)!={'id','from','to','ephemeral','nonce','ciphertext','created','v','signature'}:
            raise HTTPException(400,'Wrong envelope fields')
        if e.get('from')!=fp or e.get('v')!=1 or not re.fullmatch('[a-f0-9]{64}',str(e.get('to',''))):
            raise HTTPException(403,'Invalid sender, target or version')
        try:
            uuid.UUID(e['id'])
            if abs(int(time.time())-e['created'])>120:raise ValueError('Stale message')
            if not 1<=len(bytes.fromhex(e['ciphertext']))<=5000:raise ValueError('Message size')
            if len(bytes.fromhex(e['ephemeral']))!=32 or len(bytes.fromhex(e['nonce']))!=12:raise ValueError('Crypto fields')
            ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(req.headers['x-crypto-identity'])).verify(
                bytes.fromhex(e['signature']),canonical({k:v for k,v in e.items() if k!='signature'}))
        except Exception:raise HTTPException(400,'Invalid signed envelope')
        with lock:
            if not conn.execute('SELECT 1 FROM people WHERE fp=?',(e['to'],)).fetchone():
                raise HTTPException(404,'Recipient not registered')
            if conn.execute('SELECT COUNT(*) FROM mail WHERE recipient=?',(e['to'],)).fetchone()[0]>=MAX_MAIL:
                raise HTTPException(429,'Recipient inbox full')
            try:
                conn.execute('INSERT INTO mail VALUES (?,?,?,?,?)',(e['id'],fp,e['to'],json.dumps(e),int(time.time())))
                conn.commit()
            except sqlite3.IntegrityError:raise HTTPException(409,'Duplicate message ID')
        return {'queued':True,'id':e['id'],'settlement':'NONE'}

    @app.get('/v1/inbox')
    async def inbox(req:Request):
        fp=await auth(req)
        with lock:
            rows=conn.execute('SELECT payload FROM mail WHERE recipient=? ORDER BY created ASC LIMIT 40',(fp,)).fetchall()
        return {'envelopes':[json.loads(row[0]) for row in rows]}

    @app.post('/v1/ack')
    async def ack(req:Request):
        fp=await auth(req)
        try:ids=(await req.json())['ids']
        except Exception:raise HTTPException(400,'Missing ids')
        if not isinstance(ids,list) or len(ids)>40 or any(not isinstance(x,str) or len(x)>50 for x in ids):
            raise HTTPException(400,'Invalid IDs')
        with lock:
            conn.executemany('DELETE FROM mail WHERE recipient=? AND id=?',[(fp,x) for x in ids]);conn.commit()
        return {'acknowledged':len(ids)}

    return app

app=create_app()
