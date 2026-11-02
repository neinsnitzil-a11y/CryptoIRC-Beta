"""VaultForge network privacy & safe new-wallet rotation (experimental).

Tor mode is an opt-in fail-closed policy for SUPPORTED network paths only.
It is NOT an anonymous wallet, Tor installer, or blockchain-privacy guarantee.
"""
from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import stat
from datetime import datetime, timezone

import wallet_core as wc


class PrivacyError(RuntimeError):
    pass


def settings_path() -> Path:
    return Path.home() / 'VaultForge' / 'network-security.json'


def load_settings() -> dict:
    path = settings_path()
    if path.is_symlink():
        raise PrivacyError('Network-settings file is a symlink; refusing to follow it.')
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {'mode': 'direct', 'port': 9050}
    if len(raw) > 4096:
        raise PrivacyError('Network settings unexpectedly large.')
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PrivacyError('Invalid network settings: refusing to fall back to direct network.') from exc
    if not isinstance(obj, dict) or obj.get('mode') not in ('direct', 'tor') or type(obj.get('port')) is not int or obj['port'] not in (9050, 9150):
        raise PrivacyError('Invalid network settings: refusing to fall back to direct network.')
    return {'mode': obj['mode'], 'port': obj['port']}


def save_settings(mode: str, port: int) -> None:
    if mode not in ('direct', 'tor') or port not in (9050, 9150):
        raise PrivacyError('Unsupported privacy mode or SOCKS port.')
    path = settings_path()
    if path.is_symlink() or path.parent.is_symlink():
        raise PrivacyError('Refusing symlinked security settings path.')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        os.chmod(path.parent, 0o700)
    temp = path.with_name('.network-security-' + secrets.token_hex(8))
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'mode': mode, 'port': port}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def socks5_probe(port: int, timeout: float = 2.0) -> None:
    """Checks a local SOCKS5 server is reachable. Does NOT prove it is Tor."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b'\x05\x01\x00')
            response = sock.recv(2)
    except OSError as exc:
        raise PrivacyError(f'Tor-required mode blocked: no local SOCKS5 proxy on 127.0.0.1:{port}. Start Tor; no direct fallback.') from exc
    if response != b'\x05\x00':
        raise PrivacyError('Tor-required mode blocked: SOCKS5 handshake failed (proxy not ready).')


def tor_required() -> bool:
    return load_settings()['mode'] == 'tor'


def http_session_for_evm():
    """A requests Session for web3 HTTPProvider; no environment proxy bypass."""
    settings = load_settings()
    if settings['mode'] != 'tor':
        return None
    socks5_probe(settings['port'])
    try:
        import requests
        import socks  # requests[socks] / PySocks installed by requirements
    except ImportError as exc:
        raise PrivacyError('Tor mode needs requests and PySocks; rerun the installer. No direct fallback.') from exc
    session = requests.Session()
    session.trust_env = False
    proxy = f'socks5h://127.0.0.1:{settings["port"]}'
    session.proxies.update({'http': proxy, 'https': proxy})
    return session


def evm_http_provider(url: str):
    # Validate URL independently to ensure TLS is required off loopback.
    import transfer_engine as te
    safe_url = te.safe_evm_rpc_url(url)
    session = http_session_for_evm()
    if session is not None and safe_url.startswith('http://'):
        raise PrivacyError('Tor-required EVM mode needs a trusted HTTPS endpoint; local HTTP cannot be sent over a remote Tor exit.')
    if session is None:
        # Disable environment proxy injection in direct mode as well.
        import requests
        session = requests.Session()
        session.trust_env = False
    from web3 import Web3
    return Web3(Web3.HTTPProvider(safe_url, request_kwargs={'timeout': 20}, session=session))


def verify_bitcoin_tor(rpc) -> None:
    """Fail-closed check of the Core node's CURRENT P2P behavior.

    Does not establish anonymity or verify connections made before this call.
    RPC stays loopback and MUST never be forwarded to Tor exit nodes.
    """
    settings = load_settings()
    if settings['mode'] != 'tor':
        return
    socks5_probe(settings['port'])
    net = rpc.call('getnetworkinfo')
    if not isinstance(net, dict) or not isinstance(net.get('networks'), list):
        raise PrivacyError('Bitcoin Core Tor status unavailable; refusing network operation.')
    onion = next((n for n in net['networks'] if n.get('name') == 'onion'), None)
    proxy = onion.get('proxy', '') if isinstance(onion, dict) else ''
    if not isinstance(proxy, str) or proxy not in (f'127.0.0.1:{settings["port"]}', f'[::1]:{settings["port"]}'):
        raise PrivacyError('Bitcoin Core does not report the required Tor onion proxy. Configure bitcoin.conf first.')
    peers = rpc.call('getpeerinfo')
    if not isinstance(peers, list) or not peers:
        raise PrivacyError('Bitcoin Core has no verified Tor peers; refusing rather than assuming connectivity.')
    if any(not isinstance(p, dict) or p.get('network') != 'onion' for p in peers):
        raise PrivacyError('Bitcoin Core has non-onion peers; Tor-required policy refuses this node.')
    print('[TOR CHECK] Bitcoin Core currently reports onion proxy and onion-only peers.')
    print('This is a point-in-time configuration check, NOT proof of anonymity or a network-wide firewall.')


def require_monero_external_tor_verified() -> None:
    if tor_required():
        raise PrivacyError('Tor-required mode blocks Monero transfers: VaultForge cannot verify the external Monero daemon/network transport. Configure and independently verify your daemon before using direct mode; no automatic downgrade.')


def tor_menu() -> None:
    info = load_settings()
    print(f'\nNETWORK PRIVACY: {info["mode"].upper()} (SOCKS port {info["port"]})')
    print('1) Enable Tor-required routing (fail closed)')
    print('2) Return to direct routing (explicit user confirmation)')
    print('3) Check local SOCKS5 service')
    print('0) Back')
    selected = input('Choose: ').strip()
    if selected == '1':
        port_text = input('Tor SOCKS port [9050; Tor Browser usually uses 9150]: ').strip()
        port = 9150 if port_text == '9150' else 9050 if port_text in ('', '9050') else None
        if port is None:
            raise PrivacyError('Only 9050 and 9150 are supported to avoid accidental remote proxies.')
        socks5_probe(port)
        print('Only a SOCKS5 handshake was verified. Ensure the process is genuine Tor.')
        print('EVM RPC uses socks5h; BTC requires Core P2P onion proxy + onion-only peers.')
        print('Monero external wallet-RPC sends are blocked in Tor-required mode.')
        if input('Type ENABLE TOR to save fail-closed policy: ').strip() == 'ENABLE TOR':
            save_settings('tor', port)
            print('[SAVED] Tor-required policy enabled.')
    elif selected == '2':
        print('WARNING: direct mode exposes your connection IP to network endpoints.')
        if input('Type ENABLE DIRECT to permit direct connections: ').strip() == 'ENABLE DIRECT':
            save_settings('direct', info['port'])
            print('[SAVED] Direct routing selected.')
    elif selected == '3':
        socks5_probe(info['port'])
        print('[OK] Local SOCKS5 responds, but its identity/Tor circuits are NOT authenticated by this check.')


def rotate_seeds_to_new_vault() -> Path | None:
    """New seed == NEW wallet; never mutate the existing vault or claim funds move."""
    import vault_bridge as bridge
    old_path, old = bridge.unlock_selected()
    bridge.validate_payload(old)
    coin_codes = [w['coin'] for w in old['wallets']]
    if len(coin_codes) != len(set(coin_codes)) or not coin_codes or any(c not in wc.COIN_BY_CODE for c in coin_codes):
        raise ValueError('Cannot safely rotate unsupported/duplicate vault accounts.')
    print('\n[CRITICAL] New recovery phrases produce NEW ADDRESSES.')
    print('Existing cryptocurrency stays at the OLD addresses until transferred.')
    print('This operation will NOT move funds, revoke old seeds, or delete the original vault.')
    print('Back up and verify the new phrase before transferring funds using a separately verified wallet.')
    print('Old vault remains essential for recovery and pending transactions.')
    if input('Type CREATE NEW WALLET to continue: ').strip() != 'CREATE NEW WALLET':
        print('Canceled; original wallet unchanged.')
        return None
    folder = wc.choose_writable_storage()
    has_bip = any(c != 'XMR' for c in coin_codes)
    size = 24
    if has_bip:
        length = input('New seed length [1=12 words, 2=24 words] (default 2): ').strip()
        if length not in ('', '1', '2'):
            raise ValueError('Choose 1 or 2 only.')
        size = 12 if length == '1' else 24
    passphrase = ''
    if has_bip and wc.ask_yes_no('Protect new seed with an additional BIP39 passphrase? [y/N]: '):
        passphrase = getpass.getpass('NEW BIP39 passphrase (hidden): ')
        if not passphrase:
            raise ValueError('An empty additional passphrase does not provide additional protection.')
        if not hmac.compare_digest(passphrase, getpass.getpass('Repeat new BIP39 passphrase: ')):
            raise ValueError('BIP39 passphrases do not match.')
    password = wc.new_password()
    groups, entries = [], []
    if has_bip:
        phrase = wc.generate_bip39(size)
        groups.append({'scheme': 'bip39', 'mnemonic': phrase, 'passphrase': passphrase})
        for code in coin_codes:
            if code != 'XMR':
                item = wc.derive_coin(code, phrase, passphrase)
                item['seed_group'] = 0
                entries.append(item)
    if 'XMR' in coin_codes:
        xmr_phrase = wc.generate_monero()
        groups.append({'scheme': 'monero', 'mnemonic': xmr_phrase, 'passphrase': ''})
        item = wc.derive_coin('XMR', xmr_phrase, '')
        item['seed_group'] = len(groups) - 1
        entries.append(item)
    prior = {(w['coin'], w['address']) for w in old['wallets']}
    if any((w['coin'], w['address']) in prior for w in entries):
        raise RuntimeError('New account unexpectedly matches a previous address. NOT SAVED.')
    fingerprint = hashlib.sha256('|'.join(f'{w["coin"]}:{w["address"]}' for w in old['wallets']).encode()).hexdigest()[:16]
    payload = {'format': 'VaultForge-Unlocked-v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
               'wallets': entries, 'groups': groups,
               'rotation_from_public_fingerprint': fingerprint,
               'warnings': ['NEW WALLET, old assets NOT moved', 'Old vault remains necessary until funds migrate',
                            'New phrase/passphrase must be independently backed up and restored']}
    # Keep the SAME new seed in memory if the filesystem fails, just like initial
    # wallet creation; never silently generate another phrase on retry.
    while True:
        try:
            path = wc.write_new_vault(folder, payload, password)
            if wc.decrypt_payload(path.read_bytes(), password) != payload:
                raise RuntimeError('New vault failed save verification; DO NOT USE its addresses.')
            break
        except OSError as exc:
            print('[SAVE BLOCKED] New wallet not confirmed saved; old vault unchanged.')
            if not wc.ask_yes_no('Retry SAME newly generated wallet in another folder? [Y/n]: ', default=True):
                raise RuntimeError('New seed was not confirmed saved. Never fund new addresses.') from exc
            folder = wc.choose_writable_storage()
    print(f'[NEW WALLET SAVED] {path.name}')
    for w in entries:
        print(f'  {w["coin"]:8} {w["address"]}')
    print('Original unchanged:', old_path.name)
    print('Do not send funds until you independently restore/verify these new addresses.')
    if wc.ask_yes_no('Reveal NEW recovery phrase(s) privately now? [y/N]: '):
        wc.reveal_seed_groups(groups, first_run=True)
    return path


def vault_permissions_audit() -> None:
    import vault_bridge as bridge
    path = bridge.select_vault_file()
    print(f'\n[VAULT SECURITY] {path.name}')
    if path.is_symlink() or not path.is_file():
        raise PrivacyError('Not a safe regular vault file.')
    if os.name == 'nt':
        print('Windows: inspect file/folder ACLs and Windows Defender. chmod does not enforce ACL isolation.')
    else:
        mode = stat.S_IMODE(path.stat().st_mode)
        parent = stat.S_IMODE(path.parent.stat().st_mode)
        print(f'Encrypted file mode: {mode:04o}; containing directory mode: {parent:04o}')
        if (mode & 0o077) or (parent & 0o077):
            print('[WARN] Other accounts may access the vault or folder.')
            if input('Type HARDEN to set file=0600, folder=0700: ').strip() == 'HARDEN':
                os.chmod(path, 0o600)
                os.chmod(path.parent, 0o700)
                print('[OK] Applied Unix file permissions (filesystem ACLs may still differ).')
        else:
            print('[OK] Unix owner-only permissions appear to be configured.')
    print('Use full-disk encryption and offline independent backups; software wallets are not hardware wallets.')


def security_menu() -> None:
    while True:
        print('\nSECURITY CENTER')
        print(' 1. Tor / direct network privacy mode')
        print(' 2. Generate fresh wallet + new recovery seed(s) (NO funds moved)')
        print(' 3. Audit encrypted-vault file permissions')
        print(' 4. Change existing vault encryption password (same seeds/addresses)')
        print(' 5. Verify paper recovery backup')
        print(' 0. Back')
        choice = input('Choose: ').strip()
        if choice == '0': return
        if choice == '1': tor_menu()
        elif choice == '2': rotate_seeds_to_new_vault()
        elif choice == '3': vault_permissions_audit()
        elif choice == '4':
            import vault_bridge as bridge
            path, payload = bridge.unlock_selected()
            print('Password change does NOT rotate recovery phrases or move funds.')
            if input('Type ROTATE PASSWORD to authorize: ').strip() == 'ROTATE PASSWORD':
                new_pass = wc.new_password()
                wc.update_password(path, payload, new_pass)
                print('[SAVED] Re-encrypted. Unlock this vault again with your NEW password.')
        elif choice == '5':
            import vault_bridge as bridge
            _, payload = bridge.unlock_selected()
            wc.backup_check(payload)
        else: print('Choose a valid menu option.')
