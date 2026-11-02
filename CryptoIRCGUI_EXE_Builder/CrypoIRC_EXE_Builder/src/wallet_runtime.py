"""Secret-safe wallet runtime diagnostics and frozen executable smoke test.

Error summaries NEVER include exception messages, arguments, traceback values,
wallet addresses, seeds, passwords, or OS absolute paths.
"""
from __future__ import annotations
import tempfile
import re
from pathlib import Path

_ALLOWED_FRAMES = {'vaultforge.py', 'extended_wallets.py', 'professional_ui.py',
                   'crypto.py', 'backend.py', 'wallet_runtime.py'}


def wallet_error_code(exc: BaseException) -> str:
    seen = set()
    chain = []
    current = exc
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(e, (ImportError, ModuleNotFoundError)) or type(e).__name__ == 'CryptoDependencyUnavailable' for e in chain):
        return 'WLT-DEPENDENCY'
    if any(isinstance(e, PermissionError) for e in chain):
        return 'WLT-STORAGE-ACCESS'
    if any(isinstance(e, (OSError,)) for e in chain):
        return 'WLT-STORAGE-IO'
    if any(isinstance(e, (AttributeError, KeyError, TypeError)) for e in chain):
        return 'WLT-INCOMPATIBLE-CHAIN'
    if any(isinstance(e, ValueError) for e in chain):
        return 'WLT-VALIDATION'
    return 'WLT-RUNTIME'


def wallet_error_summary(exc: BaseException) -> str:
    """Only class names and fixed, checked-in code locations, never exception text."""
    code = wallet_error_code(exc)
    frames = []
    current = exc
    checked = set()
    while isinstance(current, BaseException) and id(current) not in checked:
        checked.add(id(current))
        tb = current.__traceback__
        while tb is not None:
            frame = tb.tb_frame
            filename = Path(frame.f_code.co_filename).name
            if filename in _ALLOWED_FRAMES:
                frames.append((filename, frame.f_code.co_name, tb.tb_lineno))
            tb = tb.tb_next
        current = current.__cause__ or current.__context__
    hint = {
        'WLT-DEPENDENCY': 'A cryptography module may be missing from this executable.',
        'WLT-STORAGE-ACCESS': 'The selected storage folder was not writable.',
        'WLT-STORAGE-IO': 'The storage device or file operation failed.',
        'WLT-INCOMPATIBLE-CHAIN': 'Wallet derivation or a bundled module was incompatible.',
        'WLT-VALIDATION': 'An input or wallet parameter was rejected.',
        'WLT-RUNTIME': 'Wallet generation stopped unexpectedly.',
    }[code]
    frame_text = ' / '.join(f'{file}:{line} ({fn})' for file, fn, line in frames[-3:]) or 'unavailable'
    # Only allow known package import prefixes, never exception messages or
    # arbitrary text from a wallet file. A missing-module name is public data.
    allowed = ('bip_utils', 'argon2', 'cryptography', 'coincurve', 'cbor2',
               'ecdsa', 'ed25519_blake2b', 'sr25519', 'x25519', 'nacl',
               'Crypto', 'Cryptodome', 'pytoniq_core', 'eth_utils',
               'eth_account', 'web3', 'py_ecc')
    dependency = None
    chain = []
    cursor = exc
    visited = set()
    while isinstance(cursor, BaseException) and id(cursor) not in visited:
        visited.add(id(cursor))
        chain.append(cursor)
        cursor = cursor.__cause__ or cursor.__context__
    for error in chain:
        candidate = getattr(error, 'module_name', None) or (getattr(error, 'name', None)
                                                            if isinstance(error, ModuleNotFoundError) else None)
        if (isinstance(candidate, str) and len(candidate) <= 100 and
            re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*', candidate) and
            candidate.split('.')[0] in allowed):
            dependency = candidate
            break
    module_line = f'\nMissing component: {dependency}' if code == 'WLT-DEPENDENCY' and dependency else ''
    return f'{code} | {type(exc).__name__}\n{hint}{module_line}\nCode location: {frame_text}\n\nNo recovery words or passwords were recorded.'


def test_wallet_runtime() -> int:
    """Used by the frozen desktop EXE and normal Python alike; offline, temp-only.

    A missing frozen module, broken derivation, or bad encryption blocks the
    installer. Nothing is funded, broadcast or written to user wallet storage.
    """
    from core.extended_wallets import create_vaults
    from backend import read_vault
    from core import vaultforge as vf
    vf.load_crypto()
    password = 'NON-PRODUCTION-smoke-test-password-only'
    cases = ['USDT-ETH', 'USDT-TRX', 'USDT-SOL', 'USDC-BASE', 'BTC']
    with tempfile.TemporaryDirectory(prefix='nocturne-wallet-selftest-') as d:
        for code in cases:
            created = create_vaults(d, [code], 1, 12, password)
            if len(created) != 1:
                raise RuntimeError('TEST_CREATION_COUNT')
            data = read_vault(created[0], password)
            entry = data['wallets'][0]
            if entry['coin'] != code or not isinstance(entry['address'], str) or not entry['address']:
                raise RuntimeError('TEST_ADDRESS_INVALID')
            # Remove only the brand-new temporary test vault; never user data.
            Path(created[0]).unlink()
    return len(cases)
