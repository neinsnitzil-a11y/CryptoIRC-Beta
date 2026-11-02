"""Sandbox-only operator utility: never requests card, bank, or wallet secrets."""
from __future__ import annotations
import argparse,json,secrets,tempfile,time
from pathlib import Path
from .events import handle_test_event,sign_test_event
from .ledger import SandboxLedger

def main():
    p=argparse.ArgumentParser(description='CRYPTO NOCTURNE sandbox financial controls (NO REAL FUNDS)')
    p.add_argument('command',choices=['demo','verify'])
    p.add_argument('--database',default='')
    a=p.parse_args()
    if not a.database and a.command!='demo':p.error('--database required for verify')
    with tempfile.TemporaryDirectory(prefix='crypto-sandbox-') as temporary:
        path=a.database or str(Path(temporary)/'sandbox.sqlite3')
        ledger=SandboxLedger(path)
        if a.command=='demo':
            r=ledger.create_intent(customer_id='sample_user',provider='sandbox-stripe',
                provider_ref='sb_'+secrets.token_hex(12),currency='USD',amount='19.95',
                idempotency_key='demo_'+secrets.token_hex(12))
            event={'provider':r['provider'],'event_id':'evt_'+secrets.token_hex(12),'intent_id':r['id'],
                'provider_ref':r['provider_ref'],'currency':'USD','minor':r['amount_minor'],'status':'settled'}
            key=secrets.token_bytes(32);now=int(time.time())
            handle_test_event(ledger,event,sign_test_event(key,event,now),key,now)
            print('SANDBOX ONLY / NOT REAL MONEY')
            print('Simulated balance in minor units:',ledger.customer_balance('sample_user','USD'))
        problems=ledger.verify_integrity()
        print('Ledger integrity:', 'PASS' if not problems else 'FAILED: '+str(problems))
        ledger.close()
        return 1 if problems else 0
if __name__=='__main__':raise SystemExit(main())
