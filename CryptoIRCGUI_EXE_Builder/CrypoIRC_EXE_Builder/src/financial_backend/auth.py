"""Server-side login building blocks: Argon2id, TOTP, lockout, short session expiry.

Use only on a separately deployed backend over verified TLS with CSRF protection,
server-side secrets management and external penetration testing. Not deployed by
or packaged into the NOCTURNE desktop installer.
"""
from __future__ import annotations
import base64,hashlib,hmac,secrets,struct,time
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

HASHER=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2)

class LoginDenied(ValueError):pass

def enroll_totp():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')

def totp_code(secret, step=None):
    try:
        raw=base64.b32decode(secret.upper()+'='*((-len(secret))%8),casefold=True)
        if len(raw)<20:raise ValueError('Secret too short')
    except Exception:raise LoginDenied('Invalid authenticator secret') from None
    counter=int(time.time()//30 if step is None else step)
    mac=hmac.new(raw,struct.pack('>Q',counter),hashlib.sha1).digest()
    offset=mac[-1]&15
    number=(struct.unpack('>I',mac[offset:offset+4])[0]&0x7fffffff)%1000000
    return f'{number:06d}'

class SessionAuth:
    """Instance for one operator in test/dev environment; in production use shared DB
    sessions with per-identity transactional rate limiting and hashed token storage.
    """
    def __init__(self,password,totp_secret):
        if len(password)<16:raise ValueError('Use at least 16 characters')
        self.password_hash=HASHER.hash(password)
        self.totp_secret=totp_secret
        self.failures=0
        self.blocked_until=0
        self.sessions={}
        self.last_step=-1
    def login(self,password,code,now=None):
        now=time.time() if now is None else now
        if now<self.blocked_until:raise LoginDenied('Temporarily locked')
        valid=False
        try:valid=HASHER.verify(self.password_hash,password)
        except (VerifyMismatchError,VerificationError):pass
        current=int(now//30)
        matched=next((s for s in (current-1,current,current+1) if
                      hmac.compare_digest(totp_code(self.totp_secret,s),str(code)) and s>self.last_step),None)
        if not valid or matched is None:
            self.failures+=1
            if self.failures>=5:self.blocked_until=now+min(3600,30*2**min(self.failures-5,6))
            raise LoginDenied('Invalid credentials')
        self.last_step=matched
        self.failures=0;self.blocked_until=0
        raw=secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(raw.encode()).hexdigest()]=now+900
        return raw
    def check(self,token,now=None):
        now=time.time() if now is None else now
        key=hashlib.sha256(str(token).encode()).hexdigest()
        until=self.sessions.get(key,0)
        if now>=until:
            self.sessions.pop(key,None)
            raise LoginDenied('Session expired')
        return True
    def logout(self,token):
        key=hashlib.sha256(str(token).encode()).hexdigest()
        self.sessions.pop(key,None)
