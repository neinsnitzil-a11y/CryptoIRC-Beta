"""Local .vault security controls. No network, logging, key export or format migration.

Encrypted-file copies are only one layer of recovery: users still MUST verify
seed recovery independently. This module never asserts a backup is spendable.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import secrets
import stat

from core import vaultforge as vf

@dataclass(frozen=True)
class VaultCheck:
    encrypted_format: str
    file_bytes: int
    encrypted_digest: str
    authenticated: bool
    permission_status: str
    recovery_verified: bool = False


def _vault_file(path: str | Path) -> Path:
    p=Path(path).expanduser().absolute()
    if p.suffix.lower() != '.vault' or p.is_symlink():
        raise ValueError('Select a regular, non-symlink .vault file')
    info=p.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= vf.MAX_VAULT_BYTES:
        raise ValueError('Vault file is missing, empty or invalid')
    return p


def _read_vault_bytes(path: Path) -> bytes:
    flags=os.O_RDONLY | getattr(os,'O_BINARY',0) | getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path, flags)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= vf.MAX_VAULT_BYTES:
            raise ValueError('Invalid encrypted vault file')
        with os.fdopen(fd,'rb',closefd=False) as fp:
            data=fp.read(vf.MAX_VAULT_BYTES+1)
        if not data or len(data)>vf.MAX_VAULT_BYTES:
            raise ValueError('Invalid vault size')
        return data
    finally:
        os.close(fd)


def _authenticate(blob: bytes, password: str) -> dict:
    payload=vf.decrypt_payload(blob,password)
    if (not isinstance(payload,dict) or payload.get('format')!='VaultForge-Unlocked-v1'
            or not isinstance(payload.get('groups'),list)
            or not isinstance(payload.get('wallets'),list)):
        raise ValueError('Encrypted wallet content is incompatible')
    return payload


def inspect_vault(path: str | Path, password: str) -> VaultCheck:
    """Authenticate existing ciphertext without returning plaintext or secrets."""
    p=_vault_file(path)
    blob=_read_vault_bytes(p)
    _authenticate(blob,password)
    # Windows ACLs and exFAT media cannot be assessed reliably via POSIX mode bits.
    if os.name=='nt':
        permissions='Windows ACLs: not automatically verified (review file Security tab)'
    else:
        mode=stat.S_IMODE(p.stat().st_mode)
        permissions=('REVIEW: vault is group/other accessible' if mode & 0o077 else
                     'Owner-only mode (ACL and backup policy still require review)')
    return VaultCheck('VaultForge v1 / Argon2id / AES-256-GCM',len(blob),
                      hashlib.sha256(blob).hexdigest(),True,permissions)


def _backup_target(source: Path, dest: str | Path) -> Path:
    p=Path(dest).expanduser().absolute()
    if p.suffix.lower() != '.vault' or p==source or p.is_symlink() or p.exists():
        raise ValueError('Choose a NEW encrypted .vault filename')
    if p.parent.is_symlink() or not p.parent.is_dir():
        raise ValueError('Backup directory must already exist and not be a symbolic link')
    if p.parent == source.parent:
        raise ValueError('Choose a different backup folder from the working vault')
    # Do not accidentally distribute an encrypted backup with the application's code.
    project_root=Path(__file__).resolve().parent.parent
    if p==project_root or project_root in p.parents:
        raise ValueError('Never back up wallet files into the application/build folder')
    return p


def _exclusive_write(dest:Path, blob:bytes) -> None:
    flags=(os.O_WRONLY|os.O_CREAT|os.O_EXCL| getattr(os,'O_BINARY',0)
           |getattr(os,'O_NOFOLLOW',0))
    fd=os.open(dest,flags,0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(blob)
            f.flush();os.fsync(f.fileno())
    except BaseException:
        try:dest.unlink(missing_ok=True)
        except OSError:pass
        raise


def backup_encrypted_vault(source: str | Path, backup: str | Path, password: str) -> VaultCheck:
    """Create an exclusive, authenticated, byte-for-byte encrypted backup.

    Never uses a plaintext temporary file. Existing destinations are not changed.
    """
    src=_vault_file(source)
    target=_backup_target(src,backup)
    before=_read_vault_bytes(src)
    _authenticate(before,password)  # fail before writing if password is wrong
    _exclusive_write(target,before)
    try:
        saved=_read_vault_bytes(target)
        if saved!=before:
            raise ValueError('Backup verification failed')
        _authenticate(saved,password)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return inspect_vault(target,password)


def rotate_vault_with_backup(source: str | Path, old_password: str,
                             new_password: str, backup: str | Path) -> VaultCheck:
    """Verify old password, preserve encrypted rollback copy, rotate atomically.

    Never silently replaces a pre-existing backup. No plain backup ever written.
    """
    src=_vault_file(source)
    if not isinstance(new_password,str) or len(new_password)<14:
        raise ValueError('New encryption password must contain at least 14 characters')
    if new_password == old_password:
        raise ValueError('Choose a different password when rotating')
    old=_read_vault_bytes(src)
    payload=_authenticate(old,old_password)
    backup_encrypted_vault(src,backup,old_password)
    updated=vf.encrypt_payload(payload,new_password)
    # Verify the new encryption before touching the existing vault.
    if _authenticate(updated,new_password)!=payload:
        raise ValueError('New encryption self-check failed')
    tmp=src.with_name('.vault_rotation_'+secrets.token_hex(12))
    try:
        _exclusive_write(tmp,updated)
        if _authenticate(_read_vault_bytes(tmp),new_password)!=payload:
            raise ValueError('Temporary encrypted vault could not be verified')
        # Avoid replacing vault changed concurrently since initial authentication.
        if _read_vault_bytes(src)!=old:
            raise ValueError('Vault changed during rotation; original preserved')
        os.replace(tmp,src)
    finally:
        tmp.unlink(missing_ok=True)
    return inspect_vault(src,new_password)
