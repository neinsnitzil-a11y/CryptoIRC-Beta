"""Safe operator CLI for synthetic operational checks, not a payment daemon."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import tempfile
from pathlib import Path

from .backup import create_backup, verify_backup, restore_to_new_database
from .ledger import SandboxLedger
from .operations import SandboxOperations


def main(argv=None):
    ap = argparse.ArgumentParser(description='NOCTURNE v2.3 - SANDBOX operations only')
    ap.add_argument('command', choices=['demo', 'health', 'backup', 'verify-backup', 'restore'])
    ap.add_argument('--database', default='')
    ap.add_argument('--file', default='', help='Backup output for backup; source for verify/restore')
    ap.add_argument('--destination', default='', help='New database path for restore')
    a = ap.parse_args(argv)
    if a.command == 'restore':
        if not a.file or not a.destination: ap.error('--file and --destination required')
        print(json.dumps(restore_to_new_database(a.file, a.destination), indent=2))
        return 0
    if a.command == 'verify-backup':
        if not a.file: ap.error('--file required')
        print(json.dumps(verify_backup(a.file), indent=2))
        return 0
    if a.command != 'demo' and not a.database:
        ap.error('--database required for health or backup')
    with tempfile.TemporaryDirectory(prefix='nocturne-ops-') as folder:
        path = a.database or str(Path(folder) / 'synthetic.sqlite3')
        ledger = SandboxLedger(path)
        try:
            ops = SandboxOperations(ledger, {'test_reconciler': 'reconciler', 'test_checker': 'reviewer'})
            if a.command == 'demo':
                ledger.create_intent(customer_id='synthetic_customer', provider='sandbox-bank',
                    provider_ref='ref_' + secrets.token_hex(8), currency='USD', amount='1.25',
                    idempotency_key='demo_' + secrets.token_hex(12))
                message = ops.claim_outbox('demo_worker')
                if message:
                    ops.acknowledge_delivery(message['id'], message['lease_token'])
                print('SANDBOX SAMPLE -- no actual bank balance or funds')
                print(json.dumps(ops.health(), indent=2))
            elif a.command == 'health':
                print(json.dumps(ops.health(), indent=2))
            elif a.command == 'backup':
                if not a.file: ap.error('--file required')
                print(json.dumps(create_backup(ledger, a.file), indent=2))
            return 0
        finally:
            ledger.close()

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print('OPERATION BLOCKED:', type(error).__name__, str(error), file=sys.stderr)
        raise SystemExit(1)
