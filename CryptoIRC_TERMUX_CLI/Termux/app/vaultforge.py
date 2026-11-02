#!/usr/bin/env python3
"""VaultForge Unified CLI: one encrypted wallet manager and transfer interface.

EXPERIMENTAL SELF-CUSTODY SOFTWARE. Use test funds and independent verification.
No hidden online service, no external wallet custody, no seed upload.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys

# -I (isolated) removes the script directory from sys.path on Python 3.12+.
# Import only the bundled, same-directory modules; do not import from the CWD.
_BUNDLE_DIR = str(Path(__file__).resolve().parent)
if _BUNDLE_DIR not in sys.path:
    sys.path.insert(0, _BUNDLE_DIR)

import wallet_core as wc
import transfer_engine as te
import vault_bridge as bridge
import bitcoin_vault as btc
import security_center as security
import subprocess

VERSION = '2.8.2-enter-default'


def run_mesh_chat(args: list[str]) -> int:
    """Run untrusted peer-network parsing in a separate OS process from wallets."""
    executable = Path(__file__).resolve().with_name('mesh_chat.py')
    return subprocess.call([sys.executable, '-I', str(executable), *args])



def mesh_connect_menu() -> None:
    """User-facing network modes; mesh keys and peer traffic run in a child process."""
    import mesh_chat as mesh

    pins = mesh.secure_load(mesh.secure_root() / 'known_peers.json')
    remembered = sorted(addr for addr in pins if isinstance(addr, str))
    root = mesh.secure_root()
    prefs_path = root / 'client_preferences.json'
    prefs = mesh.secure_load(prefs_path)
    # Keep the old preference as a saved host when migrating to the new relay list.
    remembered_host = prefs.get('aws_endpoint', '')
    catalog = mesh.load_relay_hosts(root)
    if isinstance(remembered_host, str) and remembered_host and not any(
            row['endpoint'] == remembered_host for row in catalog['hosts']):
        try:
            mesh.parse_endpoint(remembered_host)
            catalog['hosts'].append({'endpoint': remembered_host, 'label': 'Previous custom relay'})
            mesh.save_relay_hosts(root, catalog)
        except ValueError:
            pass
    aws_pref = catalog['active']
    if not isinstance(aws_pref, str):
        aws_pref = mesh.DEFAULT_BOOTSTRAP
    try:
        mesh.parse_endpoint(aws_pref)
    except ValueError:
        aws_pref = mesh.DEFAULT_BOOTSTRAP
    enabled_pref = prefs.get('aws_auto_connect') is True
    print('\nVAULTFORGE MESH COMMUNICATIONS — SELECT MODE')
    print(f' 1. CONNECT TO AWS / EXISTING SERVER  (Hit Enter for default {aws_pref})')
    print(' 2. RECONNECT TO SAVED TRUSTED PEERS')
    print(' 3. LOCAL PRIVATE CHAT (offline; only this device)')
    print(' 4. ADVANCED: custom listener and remote peer')
    print(' 5. CONNECT TO A USER-HOSTED P2P RELAY')
    print(' 6. HOST A PUBLIC/REMOTE MESH RELAY')
    print(' 7. HOST OFFLINE LAN MESH (no internet required)')
    print(' 8. SCAN LAN & CONNECT (discover local peers)')
    print(' 9. SCAN LAN ONLY (no login needed)')
    print('10. SET UP BACKGROUND NODE — AWS, laptop LAN or Tor')
    print('11. START NODE IN BACKGROUND')
    print('12. STOP BACKGROUND NODE')
    print('13. NODE STATUS')
    print('14. ENABLE NODE AUTOSTART (login/reboot with service config)')
    print('15. CONNECT TO PEER THROUGH TOR (SOCKS5h)')
    print('16. SCAN PUBLIC NODES (signed opt-in listings)')
    print('17. DIAGNOSE AWS / REMOTE TCP CONNECTION')
    print('18. CHAT LOGIN + AUTO-CONNECT TO CONFIGURED AWS')
    print('19. CONFIGURE SAVED AWS AUTO-CONNECT + ENDPOINT')
    print(f'    Auto-connect preference: {"ON" if enabled_pref else "OFF"}; endpoint: {aws_pref}')
    print(' 0. Back')
    choice = input('Select: ').strip()
    if choice == '0':
        return
    if choice in ('1', '5'):
        default = aws_pref if choice == '1' else ''
        print('\n[CONNECT] Enter a public IPv4 or DNS name and the TCP port.')
        print('AWS uses the EC2 PUBLIC IP (not 172.31.x.x).')
        if choice == '1':
            print('Default AWS endpoint can change if the EC2 public IP changes.')
        prompt = (f'Peer HOST:PORT [Hit Enter for default {default}]: '
                  if default else 'Peer HOST:PORT: ')
        raw = input(prompt).strip()
        entered = raw or default
        if choice == '1' and not raw and default:
            print(f'[DEFAULT] Using saved AWS relay {default}')
        if not entered:
            print('[CANCEL] No peer endpoint supplied.')
            return
        if '://' in entered or '/' in entered or '@' in entered or any(c.isspace() for c in entered):
            raise ValueError('Enter only hostname/IP and optional :port (no URL or username).')
        if ':' not in entered:
            entered += ':6667'
        mesh.parse_endpoint(entered)
        print(f'[CONNECTING] Peer {entered}; local outgoing connection only.')
        run_mesh_chat(['--listen', '127.0.0.1:0', '--peer', entered])
    elif choice == '18':
        if not enabled_pref:
            print('[AUTO CONNECT] Disabled. Choose 19 first to enable and approve an AWS endpoint.')
            return
        print('[AUTO CONNECT] Login locally, then connect to ' + aws_pref)
        run_mesh_chat(['--listen', '127.0.0.1:0', '--peer', aws_pref])
    elif choice == '19':
        entered = input(f'AWS endpoint [{aws_pref}]: ').strip() or aws_pref
        mesh.parse_endpoint(entered)
        enable = input('Auto-connect to this endpoint when choosing menu 18? [y/N]: ').strip().lower()
        if enable not in ('y', 'yes', 'n', 'no', ''):
            raise ValueError('Answer y or n')
        mesh.secure_save(prefs_path, {'aws_endpoint': entered, 'aws_auto_connect': enable in ('y', 'yes')})
        catalog = mesh.load_relay_hosts(root)
        if not any(row['endpoint'] == entered for row in catalog['hosts']):
            catalog['hosts'].append({'endpoint': entered, 'label': 'Configured AWS relay'})
        catalog['active'] = entered
        mesh.save_relay_hosts(root, catalog)
        print('[SAVED] Local client preference only; no wallet passwords or chat secrets saved.')
        print('[INFO] Choose 18 next time to sign in and automatically connect to AWS.')
    elif choice == '2':
        if not remembered:
            print('[NOT CONNECTED] No saved trusted endpoints; choose option 1 or 5 first.')
            return
        print('[RECONNECT] Previously pinned peers: ' + ', '.join(remembered))
        run_mesh_chat(['--listen', '127.0.0.1:0'])
    elif choice == '3':
        print('[OFFLINE] Loopback-only local chat. No internet or remote peers.')
        run_mesh_chat(['--listen', '127.0.0.1:0', '--no-auto-connect', '--offline'])
    elif choice == '4':
        listen = input('Local listening address [127.0.0.1:7777]: ').strip() or '127.0.0.1:7777'
        mesh.parse_endpoint(listen)
        print('Remote peer is optional. For AWS use the EC2 public IP:6667.')
        peer = input('Remote peer HOST:PORT [blank = saved peers]: ').strip()
        if peer:
            mesh.parse_endpoint(peer)
        run_mesh_chat(['--listen', listen] + (['--peer', peer] if peer else []))
    elif choice == '6':
        port = input('Relay TCP port [6667]: ').strip() or '6667'
        if not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError('Invalid TCP port')
        print('[HOST] Requires an inbound firewall rule; verify identity fingerprints.')
        print('[HOST] Use an AWS security group to restrict client IPs until audited.')
        run_mesh_chat(['--listen', f'0.0.0.0:{port}', '--relay', '--no-auto-connect'])
    elif choice == '7':
        port = input('LAN TCP port [7777]: ').strip() or '7777'
        if not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError('Invalid TCP port')
        print('[OFFLINE LAN] UDP discovery 48877, TCP port ' + port + '; no WAN required.')
        print('[OFFLINE LAN] Only users on the same reachable LAN can discover this host.')
        run_mesh_chat(['--listen', f'0.0.0.0:{port}', '--offline', '--no-auto-connect', '--lan'])
    elif choice == '8':
        print('[SCAN] Join local LAN chat and scan; then type /connect 1 for a discovered peer.')
        run_mesh_chat(['--listen', '0.0.0.0:7778', '--offline', '--no-auto-connect', '--lan'])
    elif choice == '9':
        run_mesh_chat(['--scan'])
    elif choice in ('10', '11', '12', '13', '14'):
        ops = {'10':'setup', '11':'start', '12':'stop', '13':'status', '14':'autostart'}
        params = [ops[choice]]
        if choice == '10':
            print('WAN needs open inbound TCP/firewall; LAN works without internet; Tor mode requires a Tor onion service for inbound connections.')
            mode = input('Node type [lan/wan/tor] (default lan): ').strip().lower() or 'lan'
            if mode not in ('lan', 'wan', 'tor'):
                raise ValueError('Choose lan, wan or tor')
            name = input('Node identity name [VaultRelay]: ').strip() or 'VaultRelay'
            params += ['--mode', mode, '--name', name]
        result = subprocess.call([sys.executable, '-I', str(Path(__file__).with_name('node_manager.py')), *params])
        if result:
            print(f'[NODE] Action exited with status {result}')
    elif choice == '16':
        import asyncio
        source = input('Bootstrap HOST:PORT [18.227.91.173:6667]: ').strip() or mesh.DEFAULT_BOOTSTRAP
        mesh.parse_endpoint(source)
        print('[PUBLIC DIRECTORY] Connecting to an authenticated bootstrap (not scanning random public IPs).')
        rows, failures = asyncio.run(mesh.scan_public([source]))
        for failure in failures:
            print('[SCAN ERROR] ' + failure)
        mesh.show_public_nodes(rows)
        if rows:
            selected = input('Connect to public node number [Enter = return]: ').strip()
            if selected:
                if not selected.isdecimal() or not 1 <= int(selected) <= len(rows):
                    raise ValueError('Invalid public node number')
                nick, fingerprint, endpoint = rows[int(selected) - 1]
                print(f'[UNVERIFIED ENDPOINT] {nick}@{fingerprint} {endpoint}')
                if input('Type CONNECT to connect: ').strip() == 'CONNECT':
                    run_mesh_chat(['--listen', '127.0.0.1:0', '--peer', endpoint])
    elif choice == '17':
        from connection_diagnostics import probe_endpoint
        address = input('AWS / remote HOST:PORT [18.227.91.173:6667]: ').strip() or mesh.DEFAULT_BOOTSTRAP
        probe_endpoint(address)
    elif choice == '15':
        target = input('Tor-routed mesh peer HOST:PORT (requires Tor SOCKS5 locally): ').strip()
        mesh.parse_endpoint(target)
        run_mesh_chat(['--listen', '127.0.0.1:0', '--peer', target, '--tor'])
    else:
        print('Select an option 0-19.')


def header() -> None:
    print('=' * 68)
    print(f' VAULTFORGE  {VERSION}  |  ENCRYPTED WALLETS + TRANSFERS')
    print('=' * 68)
    print('EXPERIMENTAL / NOT AUDITED / DO NOT USE WITH SIGNIFICANT FUNDS')
    print('30 address formats; vault-backed BTC + selected EVM networks.')
    print('Vault BTC requires your own fully synced local Bitcoin Core node; Monero requires wallet RPC.')
    print('Mesh chat: experimental P2P network with opt-in signed public-node discovery (not standard IRC).')


def diagnostics() -> bool:
    packages = ('bip_utils', 'argon2', 'cryptography', 'web3', 'eth_account', 'requests')
    print('Dependency diagnostics:')
    ready = True
    for name in packages:
        found = importlib.util.find_spec(name) is not None
        print(f'  {name:15} {"OK" if found else "MISSING"}')
        ready &= found
    print('Send-mode tests are NOT evidence of real transaction success.')
    return ready


def show_vaults() -> None:
    folder = input(f'Vault directory [{Path.home() / "VaultForge" / "wallets"}]: ').strip()
    parent = Path(folder).expanduser() if folder else Path.home() / 'VaultForge' / 'wallets'
    if parent.is_symlink() or not parent.is_dir():
        print('Directory does not exist or is a symbolic link.')
        return
    paths = sorted(p for p in parent.glob('*.vault') if p.is_file() and not p.is_symlink())
    print(f'Found {len(paths)} encrypted vault file(s):')
    for path in paths:
        print(f'  {path.name} ({path.stat().st_size:,} bytes)')


def wallet_action(action: str) -> None:
    path, payload = bridge.unlock_selected()
    if action == 'addresses':
        wc.print_wallets(payload)
    elif action == 'seeds':
        wc.reveal_seed_groups(payload['groups'])
    elif action == 'backup':
        wc.backup_check(payload)
    elif action == 'rotate':
        print('Password rotation re-encrypts the same original seeds and addresses.')
        if input('Type ROTATE to begin: ').strip() != 'ROTATE':
            print('Canceled.')
            return
        password = wc.new_password()
        wc.update_password(path, payload, password)
        print('[SAVED] Vault re-encrypted. Unlock once more to verify the new password.')


def choose_network() -> tuple[str, str, int, str]:
    print('\nEVM networks (balance/transaction lookup only; no signing):')
    codes = list(te.COIN_NETWORKS)
    for n, code in enumerate(codes, 1):
        name, chainid, coin = te.COIN_NETWORKS[code]
        print(f' {n:2}. {code:5} {name:22} chain={chainid} gas={coin}')
    choice = te.required('Network number or code').upper()
    if choice.isdecimal() and 1 <= int(choice) <= len(codes):
        choice = codes[int(choice) - 1]
    if choice not in te.COIN_NETWORKS:
        raise te.TransferError('Unknown EVM network.')
    name, chainid, symbol = te.COIN_NETWORKS[choice]
    return choice, name, chainid, symbol


def connect_evm(chainid: int):
    try:
        from web3 import Web3
    except ImportError as exc:
        raise te.TransferError('web3 is missing. Run the unified installer.') from exc
    url = te.safe_evm_rpc_url(te.required('Trusted HTTPS EVM RPC URL (or local HTTP)'))
    w3 = security.evm_http_provider(url)
    if not w3.is_connected():
        raise te.TransferError('RPC cannot be reached.')
    if int(w3.eth.chain_id) != chainid:
        raise te.TransferError(f'Wrong chain: RPC {w3.eth.chain_id}, expected {chainid}.')
    return w3


def read_balance() -> None:
    _, payload = bridge.unlock_selected()
    if not bridge.available_evm(payload):
        saved = ', '.join(sorted({entry.get('coin', '?') for entry in payload.get('wallets', [])}))
        print(f'[NOT AN EVM WALLET] Selected vault contains: {saved or "no accounts"}.')
        print('Menu 7 can only check supported EVM accounts; it cannot check BTC/SOL balances.')
        print('Do not import funds or generate another wallet just to use this menu option.')
        return
    entry, mapped = bridge.pick_evm(payload)
    print(f'Checking {entry["coin"]} vault address on {mapped} chain.')
    _, name, chainid, symbol = (mapped, *te.COIN_NETWORKS[mapped])
    w3 = connect_evm(chainid)
    from web3 import Web3
    address = entry.get('address', '')
    if not Web3.is_address(address):
        raise te.TransferError('Invalid saved EVM address.')
    wei = int(w3.eth.get_balance(Web3.to_checksum_address(address)))
    print(f'  Address : {address}\n  Network : {name}\n  Native balance: {Decimal(wei)/Decimal(10**18):f} {symbol}')
    print('Pending transactions, tokens and cross-chain assets are not included.')


def check_transaction() -> None:
    _, name, chainid, _ = choose_network()
    w3 = connect_evm(chainid)
    raw_hash = te.required('Transaction hash (0x followed by 64 hex characters)')
    import re
    if not re.fullmatch(r'0x[0-9a-fA-F]{64}', raw_hash):
        raise te.TransferError('Invalid transaction hash.')
    from web3.exceptions import TransactionNotFound
    try:
        receipt = w3.eth.get_transaction_receipt(raw_hash)
    except TransactionNotFound:
        print(f'No receipt yet on {name}. May be pending, dropped, or unknown to this RPC.')
        return
    status = 'SUCCESS (execution)' if int(receipt['status']) == 1 else 'REVERTED / FAILED'
    included = int(receipt['blockNumber'])
    head = int(w3.eth.block_number)
    depth = max(0, head - included + 1)
    print(f'Network: {name}\nHash: {raw_hash}\nStatus: {status}')
    print(f'Block: {included}; current block: {head}; observed confirmations: {depth}')
    print('RPC confirmation counts do NOT guarantee finality or reorg safety.')


def main_menu() -> None:
    header()
    while True:
        print('''\nWALLETS
  1. Create / restore encrypted 30-coin wallet set
  2. List encrypted .vault files
  3. Unlock vault, show public receiving addresses
  4. Reveal recovery phrases (explicit authorization)
  5. Verify paper recovery backup
  6. Change encrypted vault password

BALANCES + TRANSFERS
  7. Check saved EVM wallet's native balance (read only)
  8. Send EVM native currency directly from encrypted vault
  9. Send ERC-20 directly from encrypted vault
 10. Check EVM transaction receipt / confirmations

BITCOIN — DIRECTLY FROM AN ENCRYPTED BTC VAULT
 11. Show BTC receiving address (offline)
 12. Check confirmed BTC balance via Bitcoin Core
 13. SPEND BTC — Send from SAME encrypted vault via Bitcoin Core
 14. Check BTC transaction confirmations

OTHER TRANSFERS
 15. Send Monero via LOCAL monero-wallet-rpc (external signer)
 16. EVM send with separate encrypted V3 keystore (legacy mode)
 17. ERC-20 send with separate encrypted V3 keystore (legacy mode)
 18. Legacy BTC send via separate Bitcoin Core wallet
 19. Diagnostics / supported network list

SECURITY + PRIVACY
 20. SECURITY CENTER — Tor routing, new seeds, password, permissions

MESH COMMUNICATIONS
 21. MESH CHAT — node hosting, LAN scan, Tor connections, encrypted files and images
  0. Exit''')
        try:
            choice = input('Choose: ').strip()
            if choice == '0':
                print('Closed. Keep your recovery words offline.')
                break
            elif choice == '1': wc.create_wallets()
            elif choice == '2': show_vaults()
            elif choice == '3': wallet_action('addresses')
            elif choice == '4': wallet_action('seeds')
            elif choice == '5': wallet_action('backup')
            elif choice == '6': wallet_action('rotate')
            elif choice == '7': read_balance()
            elif choice == '8': bridge.send_from_vault()
            elif choice == '9': bridge.send_from_vault(token_mode=True)
            elif choice == '10': check_transaction()
            elif choice == '11': btc.bitcoin_receive()
            elif choice == '12': btc.bitcoin_balance()
            elif choice == '13': btc.bitcoin_send()
            elif choice == '14': btc.bitcoin_status()
            elif choice == '15': te.monero_transfer()
            elif choice == '16': te.evm_transfer(False)
            elif choice == '17': te.evm_transfer(True)
            elif choice == '18': te.bitcoin_transfer()
            elif choice == '20': security.security_menu()
            elif choice == '21':
                mesh_connect_menu()
            elif choice == '19':
                diagnostics()
                print('Vault EVM direct-send networks: ' + ', '.join(sorted(bridge.SEND_EVM)))
                print('Network privacy mode: ' + security.load_settings()['mode'].upper())
                print('Direct vault BTC: local synced Bitcoin Core node; confirmed BIP84 index-0 UTXOs only.')
                print('Legacy Core BTC / monero-wallet-rpc XMR still need their independently managed wallets.')
                print('All advertised 30 coins can derive addresses if bip_utils supports their networks; NOT all can be spent here.')
            else: print('Choose a valid menu number.')
        except (ValueError, OSError, KeyError, te.TransferError, RuntimeError) as exc:
            print(f'\n[STOP] {exc}')
        except (KeyboardInterrupt, EOFError):
            print('\nCanceled. If a broadcast was attempted, verify its tx hash before retrying.')
            return
        except Exception as exc:
            # Do not dump tracebacks from a live wallet session to screens or logs.
            print(f'\n[ERROR] {type(exc).__name__}. Operation stopped.')
            print('If a broadcast was attempted, inspect wallet/node history before retrying.')


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'chat':
        return run_mesh_chat(argv[1:])
    parser = argparse.ArgumentParser(
        description='VaultForge Unified encrypted wallet + transfer CLI',
        epilog='Quick Bitcoin actions: spend-btc, receive-btc, btc-balance, btc-status. '
               'All spending actions require interactive approval and a local synced Bitcoin Core node. '
               'Mesh: chat --listen 127.0.0.1:7777 --peer EC2_PUBLIC_IP:6667',
    )
    parser.add_argument('command', nargs='?',
                        choices=('spend-btc', 'send-btc', 'receive-btc', 'btc-balance', 'btc-status'),
                        help='optional direct Bitcoin action (no secrets on the command line)')
    parser.add_argument('--self-test', action='store_true', help='run generator crypto test (requires dependencies)')
    parser.add_argument('--diagnostics', action='store_true', help='report dependency availability without network access')
    parser.add_argument('--list-networks', action='store_true', help='list RPC/send networks')
    args = parser.parse_args(argv)
    if args.command:
        actions = {
            'spend-btc': btc.bitcoin_send,
            'send-btc': btc.bitcoin_send,
            'receive-btc': btc.bitcoin_receive,
            'btc-balance': btc.bitcoin_balance,
            'btc-status': btc.bitcoin_status,
        }
        try:
            header()
            actions[args.command]()
            return 0
        except (te.TransferError, ValueError, OSError, RuntimeError, KeyError) as exc:
            print(f'[STOP] {exc}', file=sys.stderr)
            return 2
        except (KeyboardInterrupt, EOFError):
            print('[CANCELED] If broadcast was attempted, check the TXID before retrying.', file=sys.stderr)
            return 130
    if args.diagnostics:
        return 0 if diagnostics() else 1
    if args.list_networks:
        for code, (name, chainid, sym) in te.COIN_NETWORKS.items():
            supported = ('vault-sign (EVM)' if code in bridge.SEND_EVM else
                         'receipt/lookup only' if code in ('ARB', 'OP', 'BASE') else
                         'keystore/lookup only')
            print(f'{code:5} chain={chainid:6} {name:22} {sym:5} {supported}')
        print('BTC: encrypted-vault BIP84 send/receive + local Bitcoin Core full node; legacy Core wallet mode also available.')
        print('XMR: Monero external wallet RPC.')
        return 0
    if args.self_test:
        wc.self_test()
        return 0
    main_menu()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, ImportError) as exc:
        print(f'[FATAL] {exc}', file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print('\nCanceled.')
        sys.exit(130)
