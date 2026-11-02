"""Loopback-only, TEST-ONLY partner checkout service (standalone backend).

Run in an isolated Python service environment, never bundle in desktop EXE.
Requires explicit sandbox keys, approved-code JSON and random bearer token.
Deploying on a VPS, running live keys and exposing users require additional
production authentication, TLS, KYC/partner approval and security review.
"""
from __future__ import annotations
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit
import hmac
import json
import os
from .moonpay_partner import signed_sandbox_buy_url, PartnerError

MAX_BODY=4096

def build_handler(config: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,format,*args):
            # Don't log URLs, addresses, tokens or request bodies.
            return
        def do_POST(self):
            if self.path!='/v1/sandbox/moonpay/buy':
                self.send_error(404);return
            token=self.headers.get('Authorization','')
            expected=config.get('access_token','')
            if len(expected)<32 or not hmac.compare_digest(token,'Bearer '+expected):
                self.send_error(401);return
            if self.headers.get('Content-Type','').split(';',1)[0]!='application/json':
                self.send_error(415);return
            try:
                length=int(self.headers.get('Content-Length','-1'))
                if length<=0 or length>MAX_BODY:raise ValueError()
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError()
                keys={'asset','address','fiat','amount'}
                if set(data)!=keys:raise ValueError()
                url=signed_sandbox_buy_url(**data,
                    publishable_key=config['publishable_key'],
                    secret_key=config['secret_key'],approved_codes=config['approved_codes'])
            except (ValueError,KeyError,PartnerError,TypeError):
                self.send_error(400,'Invalid or unsupported sandbox request');return
            payload=json.dumps({'mode':'sandbox','provider':'moonpay','checkout_url':url,
                'payment_status':'NOT_STARTED'}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return Handler

def serve_loopback(port:int=18440):
    if not (1024<=int(port)<=65535):raise ValueError('Invalid listen port')
    config={
      'publishable_key':os.environ.get('NOCTURNE_MOONPAY_PK_TEST',''),
      'secret_key':os.environ.get('NOCTURNE_MOONPAY_SK_TEST',''),
      'approved_codes':json.loads(os.environ.get('NOCTURNE_MOONPAY_APPROVED_ROUTES','{}')),
      'access_token':os.environ.get('NOCTURNE_PARTNER_SANDBOX_TOKEN',''),
    }
    if not (config['publishable_key'].startswith('pk_test_') and
            config['secret_key'].startswith('sk_test_') and
            len(config['access_token'])>=32 and config['approved_codes']):
        raise RuntimeError('Sandbox partner credentials, access token and approved routes are required')
    server=ThreadingHTTPServer(('127.0.0.1',int(port)),build_handler(config))
    try:server.serve_forever(poll_interval=.2)
    finally:server.server_close()

if __name__=='__main__':
    serve_loopback(int(os.environ.get('NOCTURNE_PARTNER_PORT','18440')))
