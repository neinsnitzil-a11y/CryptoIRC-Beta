"""Bridge old VaultForge .vault files to the conservative EVM transfer engine.

Never writes plaintext seeds, BIP39 passphrases or private keys to disk.
Bitcoin vault spending is implemented separately in bitcoin_vault.py. Monero still uses a separate wallet RPC.
"""
from __future__ import annotations

import re
from pathlib import Path

import wallet_core as wc
import transfer_engine as te

# The encrypted wallet's derivation is chain-specific. Refuse implicit cross-chain
# selection: the user must choose a matching saved entry.
VAULT_EVM = {
    'ETH': 'ETH',
    'ETC': 'ETC',
    'BSC': 'BNB',
    'POLYGON': 'POL',
    'AVAXC': 'AVAX',
    'ARB': 'ARB',
    'OP': 'OP',
}
SEND_EVM = frozenset({'ETH', 'ETC', 'BNB', 'POL', 'AVAX'})


def validate_payload(payload: dict) -> None:
    if (not isinstance(payload, dict) or payload.get('format') != 'VaultForge-Unlocked-v1'
            or not isinstance(payload.get('wallets'), list)
            or not isinstance(payload.get('groups'), list)):
        raise ValueError('Not a compatible decrypted VaultForge vault payload.')
    if len(payload['wallets']) > 1000 or len(payload['groups']) > 100:
        raise ValueError('Vault has unexpectedly many records.')


def available_evm(payload: dict, *, sending: bool = False) -> list[tuple[dict, str]]:
    validate_payload(payload)
    wallets = []
    for entry in payload['wallets']:
        if not isinstance(entry, dict):
            continue
        network = VAULT_EVM.get(entry.get('coin'))
        if network and (not sending or network in SEND_EVM):
            wallets.append((entry, network))
    return wallets


def derive_evm_vault_key(payload: dict, entry: dict) -> bytes:
    """Re-derive the original exact BIP44 account, validate address, fail closed.

    Importing arbitrary wallet files is dangerous; do not trust stored addresses,
    paths, network names, or seed group indices without verifying them.
    """
    validate_payload(payload)
    if not any(e is entry for e in payload['wallets']):
        raise ValueError('The entry does not belong to the selected unlocked vault.')
    code = entry.get('coin')
    if code not in VAULT_EVM:
        raise ValueError('This asset does not have an integrated vault signer.')
    coin = wc.COIN_BY_CODE[code]
    path = entry.get('derivation', '')
    if not isinstance(path, str) or not re.fullmatch(r"m/44'/[0-9]+'/0'/0/0", path):
        raise ValueError('Unrecognized account derivation path. Refusing to sign.')
    idx = entry.get('seed_group')
    if type(idx) is not int or not 0 <= idx < len(payload['groups']):
        raise ValueError('Seed group index is invalid.')
    group = payload['groups'][idx]
    if not isinstance(group, dict) or group.get('scheme') != 'bip39':
        raise ValueError('The selected account must have a BIP39 seed group.')
    mnemonic = wc.validate_phrase('bip39', group.get('mnemonic', ''))
    passphrase = group.get('passphrase', '')
    if not isinstance(passphrase, str):
        raise ValueError('Invalid BIP39 passphrase in vault.')
    try:
        from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes
        from eth_account import Account
    except ImportError as exc:
        raise RuntimeError('Signing dependencies unavailable. Run the unified installer.') from exc
    seed = Bip39SeedGenerator(mnemonic).Generate(passphrase)
    engine = Bip44.FromSeed(seed, getattr(Bip44Coins, coin[3]))
    node = engine.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    expected_path = f"m/44'/{engine.CoinConf().CoinIndex()}'/0'/0/0"
    if path != expected_path:
        raise ValueError('Saved derivation path does not match this coin configuration.')
    key = node.PrivateKey().Raw().ToBytes()
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError('Derived EVM key has invalid length.')
    expected = entry.get('address', '')
    if not isinstance(expected, str) or not expected.lower().startswith('0x'):
        raise ValueError('Vault address is not an EVM 0x address.')
    calculated = Account.from_key(key).address
    if calculated.lower() != expected.lower() or node.PublicKey().ToAddress().lower() != expected.lower():
        raise ValueError('Signing key does not match saved public address. REFUSING.')
    return key


def select_vault_file() -> Path:
    """Accept existing vaults, including ones on USB/custom directories."""
    default = Path.home() / 'VaultForge' / 'wallets'
    raw = input(f'Vault path, or directory [{default}]: ').strip()
    chosen = Path(raw).expanduser() if raw else default
    if chosen.is_symlink():
        raise ValueError('Refusing symlinked vault path.')
    if chosen.is_dir():
        candidates = sorted((p for p in chosen.glob('*.vault') if p.is_file() and not p.is_symlink()), reverse=True)
        if not candidates:
            raise ValueError(f'No .vault files found in {chosen}')
        print("\nChoose the correct wallet FILE, not just the correct password.")
        print("File #1 is the newest by filename; older files may have different passwords.")
        for n, path in enumerate(candidates, 1):
            label = "  [NEWEST]" if n == 1 else ""
            print(f' {n:2}. {path.name}{label}')
        selected = wc.number('Choose vault', 1, len(candidates), 1)
        chosen = candidates[selected - 1]
    if chosen.suffix.lower() != '.vault' or not chosen.is_file() or chosen.is_symlink():
        raise ValueError('Select an existing regular .vault file.')
    return chosen


def unlock_selected() -> tuple[Path, dict]:
    path = select_vault_file()
    payload = wc.unlock(path)
    validate_payload(payload)
    return path, payload


def pick_evm(payload: dict, *, sending: bool = False) -> tuple[dict, str]:
    eligible = available_evm(payload, sending=sending)
    if not eligible:
        raise ValueError('No matching vault EVM accounts. For BTC/XMR use their external RPC wallet menu.')
    print('\nVault EVM accounts (each entry retains its original derivation path):')
    for n, (entry, network) in enumerate(eligible, 1):
        print(f"  {n:2}. {entry['coin']:8} -> {network:5}  {entry.get('address', '(missing)')}")
    number = wc.number('Choose account', 1, len(eligible))
    return eligible[number - 1]


def send_from_vault(*, token_mode: bool = False) -> None:
    path, payload = unlock_selected()
    entry, network = pick_evm(payload, sending=True)
    print(f'\nVAULT: {path.name} | {entry["coin"]} | {entry["address"]}')
    print('Only the exact chosen saved account may sign. No seed/private key export is required.')
    print('Production use is NOT independently audited or live-transfer-verified.')
    if input('Type CONTINUE to review a possible real transfer: ').strip() != 'CONTINUE':
        print('Canceled without signing.')
        return
    key = derive_evm_vault_key(payload, entry)
    # Keep transaction construction, fee estimation, explicit user approval and
    # broadcasting in one shared engine; no different hidden send path.
    te.evm_transfer(token_mode, vault_entry=entry, vault_key=key, forced_network=network)
