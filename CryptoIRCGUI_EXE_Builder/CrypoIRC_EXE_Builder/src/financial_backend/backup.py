"""Verified sandbox SQLite backups with no overwrite or secret handling.

CAUTION: Backups are NOT encrypted here. Only synthetic sandbox identifiers
may enter this database. Real financial/account databases need protected,
encrypted backup storage and tested off-site disaster-recovery procedures.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

from .ledger import SandboxLedger, FinanceError


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        while chunk := handle.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _inspect(path):
    """Verify contents on an isolated temporary copy; never mutate the source."""
    with tempfile.TemporaryDirectory(prefix='nocturne-backup-check-') as d:
        scratch = Path(d) / 'inspection.sqlite3'
        with closing(sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(str(scratch))) as dst:
                src.backup(dst)
        store = SandboxLedger(scratch)
        try:
            status = store.db.execute('PRAGMA integrity_check').fetchone()[0]
            issues = store.verify_integrity()
            if status != 'ok' or issues:
                raise FinanceError('Backup accounting/integrity verification failed')
            return {'sqlite_integrity': 'ok', 'journal_integrity': 'ok'}
        finally:
            store.close()


def create_backup(store: SandboxLedger, destination: str | Path):
    target = Path(destination).expanduser().absolute()
    manifest = target.with_name(target.name + '.manifest.json')
    if target.exists() or manifest.exists():
        raise FinanceError('Refusing to overwrite backup or manifest')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Temporary backing file is in the same directory for an atomic rename.
    fd, filename = tempfile.mkstemp(prefix='.nocturne-backup-', suffix='.tmp', dir=target.parent)
    os.close(fd)
    scratch = Path(filename)
    try:
        with store.lock:
            with closing(sqlite3.connect(str(scratch))) as dst:
                store.db.backup(dst)  # SQLite online backup also handles WAL.
        _inspect(scratch)
        digest = _sha256(scratch)
        details = {'format': 'NOCTURNE-SANDBOX-BACKUP-v1', 'name': target.name,
                   'sha256': digest, 'bytes': scratch.stat().st_size,
                   'created_utc': int(time.time()), 'encrypted': False,
                   'contains_real_funds': False}
        if os.name != 'nt': os.chmod(scratch, 0o600)
        if target.exists(): raise FinanceError('Backup destination appeared while writing')
        os.replace(scratch, target)
        try:
            with manifest.open('x', encoding='utf-8') as out:
                json.dump(details, out, sort_keys=True, indent=2)
            if os.name != 'nt': os.chmod(manifest, 0o600)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return details
    finally:
        scratch.unlink(missing_ok=True)


def verify_backup(source: str | Path):
    source = Path(source).expanduser().absolute()
    manifest = source.with_name(source.name + '.manifest.json')
    if not source.is_file() or not manifest.is_file():
        raise FinanceError('Backup and its manifest are both required')
    try:
        data = json.loads(manifest.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise FinanceError('Invalid backup manifest') from exc
    if data.get('format') != 'NOCTURNE-SANDBOX-BACKUP-v1' or data.get('name') != source.name:
        raise FinanceError('Unknown or mismatched backup manifest')
    if data.get('sha256') != _sha256(source) or data.get('bytes') != source.stat().st_size:
        raise FinanceError('Backup checksum mismatch; recovery blocked')
    return _inspect(source)


def restore_to_new_database(source: str | Path, destination: str | Path):
    """Restore without ever replacing an existing DB; requires manual review."""
    source = Path(source).expanduser().absolute()
    dest = Path(destination).expanduser().absolute()
    verify_backup(source)
    if dest.exists() or any(dest.with_name(dest.name + s).exists() for s in ('-wal', '-shm')):
        raise FinanceError('Refusing to overwrite existing database or WAL files')
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix='.nocturne-restore-', suffix='.tmp', dir=dest.parent)
    os.close(fd)
    tmp = Path(filename)
    try:
        with closing(sqlite3.connect(f'file:{source.resolve().as_posix()}?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(str(tmp))) as dst:
                src.backup(dst)
        _inspect(tmp)
        if os.name != 'nt': os.chmod(tmp, 0o600)
        if dest.exists(): raise FinanceError('Destination appeared during restore')
        os.replace(tmp, dest)
        return {'restored_to': str(dest), 'verified': True,
                'note': 'SANDBOX ONLY: No financial payments performed'}
    finally:
        tmp.unlink(missing_ok=True)
