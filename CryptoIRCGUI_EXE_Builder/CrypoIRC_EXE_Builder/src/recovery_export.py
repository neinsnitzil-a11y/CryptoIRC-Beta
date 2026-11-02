"""Opt-in plaintext recovery export. Never log, upload, auto-export or overwrite secrets."""
from __future__ import annotations
import os
import re
from pathlib import Path


def suggested_filename(asset: str, wallet_number: int, group_number: int) -> str:
    tag = re.sub(r'[^A-Za-z0-9_-]', '_', asset.upper())[:26] or 'WALLET'
    return f'CRYPTO_RECOVERY_{tag}_W{wallet_number}_G{group_number}.txt'


def format_backup_text(*, asset: str, scheme: str, words: list[str], extra_passphrase_used: bool) -> str:
    if len(words) not in (12, 24, 25) or any(not isinstance(w, str) or not w.isalpha() for w in words):
        raise ValueError('Invalid recovery word data')
    # Monero is a separate format, not BIP39.
    title = 'Monero 25-word mnemonic' if len(words) == 25 else 'BIP39 mnemonic'
    lines = [
        'CRYPTO NOCTURNE // PRIVATE RECOVERY BACKUP',
        'HIGHLY SENSITIVE UNENCRYPTED TEXT — anyone with the phrase can potentially spend funds.',
        'Keep OFFLINE. Do not email, cloud sync, message, or screenshot this file.',
        '',
        f'Asset: {asset}',
        f'Recovery format: {title} ({scheme})',
        f'Word count: {len(words)}',
        'Words in EXACT order:',
        '',
    ]
    lines += [f'{i:02d}. {word}' for i, word in enumerate(words, 1)]
    lines += [
        '',
        'BIP39 additional passphrase used: ' + ('YES — NOT INCLUDED; BACK UP SEPARATELY' if extra_passphrase_used else 'NO'),
        'Encrypted vault password: NOT INCLUDED',
        'Backup status: NOT VERIFIED — restore independently with a trusted compatible wallet.',
        'Verify the restored receiving address before transferring funds.',
        '',
    ]
    return '\n'.join(lines)


def save_plaintext_backup(destination: str | Path, *, asset: str, scheme: str,
                          words: list[str], extra_passphrase_used: bool) -> Path:
    """Write a user-selected .txt once, refusing collisions/symlinks; no silent fallback."""
    path=Path(destination)
    if path.suffix.lower() != '.txt':
        raise ValueError('Choose a .txt destination')
    if path.exists() or path.is_symlink():
        raise FileExistsError('Destination exists; choose a new filename')
    # Create exclusively to avoid overwriting any existing backup.
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os, 'O_BINARY', 0)|getattr(os, 'O_NOFOLLOW', 0)
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            f.write(format_backup_text(asset=asset,scheme=scheme,words=words,
                                       extra_passphrase_used=extra_passphrase_used))
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:path.unlink(missing_ok=True)
        except OSError:pass
        raise
    return path
