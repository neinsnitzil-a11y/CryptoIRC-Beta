#!/usr/bin/env python3
"""VaultForge SecureTransfer — conservative, interactive self-custody transfer utility.

Not an audited financial application. Never accepts mnemonics or raw private keys.
Bitcoin: locally running Bitcoin Core wallet, PSBT / RPC.
Monero: locally running monero-wallet-rpc, prepare then relay.
EVM: standard encrypted Ethereum V3 keystore, client-side signing.
"""
from __future__ import annotations

import argparse
import base64
from decimal import Decimal, InvalidOperation
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

VERSION = '1.0.0'
SATOSHI = Decimal('0.00000001')
PICONERO = Decimal('0.000000000001')
COIN_NETWORKS = {
    'ETH': ('Ethereum', 1, 'ETH'),
    'ETC': ('Ethereum Classic', 61, 'ETC'),
    'BNB': ('BNB Smart Chain', 56, 'BNB'),
    'POL': ('Polygon PoS', 137, 'POL'),
    'AVAX': ('Avalanche C-Chain', 43114, 'AVAX'),
    'ARB': ('Arbitrum One', 42161, 'ETH'),
    'OP': ('OP Mainnet', 10, 'ETH'),
    'BASE': ('Base', 8453, 'ETH'),
    'GNO': ('Gnosis', 100, 'xDAI'),
    'CELO': ('Celo', 42220, 'CELO'),
}
# Token contracts are NOT embedded: always choose the intended chain and independently verify contract address.
ERC20_ABI = [
    {'constant': True, 'inputs': [], 'name': 'decimals', 'outputs': [{'type':'uint8'}], 'type':'function'},
    {'constant': True, 'inputs': [], 'name': 'symbol', 'outputs': [{'type':'string'}], 'type':'function'},
    {'constant': True, 'inputs': [{'name':'owner','type':'address'}], 'name': 'balanceOf', 'outputs': [{'type':'uint256'}], 'type':'function'},
    {'constant': False, 'inputs': [{'name':'to','type':'address'},{'name':'value','type':'uint256'}], 'name': 'transfer', 'outputs': [{'type':'bool'}], 'type':'function'},
]

class TransferError(Exception):
    pass


def amount_decimal(value: str, places: int, label: str = 'amount') -> Decimal:
    s = str(value).strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', s):
        raise TransferError(f'{label}: enter a positive decimal number (not exponential notation).')
    try:
        d = Decimal(s)
        if not d.is_finite() or d <= 0 or d.as_tuple().exponent < -places:
            raise TransferError(f'{label} must be positive with at most {places} decimal places.')
        if d >= Decimal('1000000000000'):
            raise TransferError(f'{label} exceeds the safety limit.')
        return d
    except InvalidOperation as e:
        raise TransferError('Invalid amount.') from e


def units(d: Decimal, places: int) -> int:
    n = d * (10 ** places)
    if n != n.to_integral_value():
        raise TransferError('Too many decimal places for the asset.')
    return int(n)


def prompt(label: str, default: str | None = None) -> str:
    suffix = f' [{default}]' if default is not None else ''
    x = input(f'{label}{suffix}: ').strip()
    return x if x else (default if default is not None else '')


def required(label: str) -> str:
    value = prompt(label)
    if not value:
        raise TransferError(f'{label} is required.')
    if any(ord(c) < 32 for c in value):
        raise TransferError('Control characters rejected.')
    return value


def amount_input(label: str, places: int, default: str | None = None) -> Decimal:
    return amount_decimal(prompt(label, default), places, label)


def confirm_send(address: str, amount: Decimal, symbol: str) -> bool:
    """No implicit send: full amount, asset and address suffix must be typed."""
    expected = f'SEND {amount:f} {symbol} {address[-8:]}'
    print('\nTO BROADCAST, type this EXACT line by hand (never blindly paste):')
    print(f'  {expected}')
    return input('Authorization: ').strip() == expected


def confirm_prepare() -> bool:
    return input('Type PREPARE to construct an unbroadcast transaction: ').strip() == 'PREPARE'


def safe_loopback_url(value: str) -> str:
    u = urlsplit(value.strip())
    if u.scheme != 'http' or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
        raise TransferError('Local wallet RPC must be a plain http://127.0.0.1:PORT URL, without credentials or path.')
    if u.hostname not in ('127.0.0.1', '::1') or not u.port:
        raise TransferError('Local RPC must use numeric loopback address (127.0.0.1 or [::1]).')
    return f'http://{u.netloc}'


def safe_evm_rpc_url(value: str) -> str:
    u = urlsplit(value.strip())
    if not u.hostname or u.username or u.password or u.fragment:
        raise TransferError('Invalid RPC URL or embedded username/password.')
    if u.scheme == 'https':
        return value.strip()
    if u.scheme == 'http' and u.hostname in ('127.0.0.1', '::1'):
        return value.strip()
    raise TransferError('Only HTTPS RPCs or local loopback HTTP RPCs are permitted.')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TransferError('RPC redirects are forbidden.')


class BitcoinRPC:
    def __init__(self, base_url: str, cookie_path: Path, wallet: str | None = None):
        self.base = safe_loopback_url(base_url)
        try:
            cookie = cookie_path.expanduser().read_text(encoding='utf-8').strip()
        except OSError as e:
            raise TransferError(f'Cannot read Bitcoin Core RPC cookie: {e}') from e
        if ':' not in cookie:
            raise TransferError('Invalid Bitcoin Core cookie file.')
        self.auth = 'Basic ' + base64.b64encode(cookie.encode()).decode()
        self.url = self.base + (f'/wallet/{quote(wallet, safe="")}' if wallet else '')
        self.opener = build_opener(NoRedirect())

    def call(self, method: str, *params: Any):
        payload = json.dumps({'jsonrpc': '1.0', 'id': 'vaultforge', 'method': method, 'params': list(params)})
        req = Request(self.url, data=payload.encode(), method='POST', headers={
            'Authorization': self.auth, 'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with self.opener.open(req, timeout=25) as res:
                raw = res.read(2_000_000)
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            raise TransferError(f'Bitcoin Core RPC connection failed for {method}: {e}') from e
        try:
            obj = json.loads(raw, parse_float=Decimal)
        except (ValueError, TypeError) as e:
            raise TransferError('Bitcoin Core RPC returned invalid JSON.') from e
        if obj.get('error'):
            raise TransferError(f'Bitcoin Core {method}: {obj["error"]}')
        return obj.get('result')


def float_exact(d: Decimal) -> float:
    """Abort rather than silently round a Bitcoin transfer amount."""
    f = float(d)
    if Decimal(str(f)) != d:
        raise TransferError('Amount cannot be serialized without precision loss. Try a smaller transfer.')
    return f


def bitcoin_outputs(tx: dict) -> list[tuple[str | None, Decimal]]:
    outputs = []
    for out in tx.get('vout', []):
        script = out.get('scriptPubKey') or {}
        addr = script.get('address')
        if not addr and isinstance(script.get('addresses'), list) and len(script['addresses']) == 1:
            addr = script['addresses'][0]
        outputs.append((addr, Decimal(str(out['value']))))
    if not outputs:
        raise TransferError('Bitcoin PSBT has no outputs.')
    return outputs


def verify_bitcoin_outputs(rpc: BitcoinRPC, tx: dict, recipient: str, amount: Decimal) -> list:
    outs = bitcoin_outputs(tx)
    paid = 0
    for address, value in outs:
        if address == recipient:
            paid += value
        else:
            if not address:
                raise TransferError('Unexpected non-address output in transaction.')
            info = rpc.call('getaddressinfo', address)
            if not info.get('ismine'):
                raise TransferError('Unexpected output not owned by your Bitcoin wallet: refusing.')
    if paid != amount:
        raise TransferError('Bitcoin transaction recipient amount mismatch!')
    return outs


def bitcoin_transfer():
    print('\nBITCOIN — Bitcoin Core wallet PSBT signing (mainnet only)')
    print('Requires locally running, synced Bitcoin Core with the desired wallet loaded.')
    home = Path.home()
    cookie_default = str(home / ('AppData/Roaming/Bitcoin/.cookie' if os.name == 'nt' else '.bitcoin/.cookie'))
    rpcurl = safe_loopback_url(prompt('Bitcoin Core RPC address', 'http://127.0.0.1:8332'))
    cookie = Path(prompt('Bitcoin Core cookie path', cookie_default))
    root = BitcoinRPC(rpcurl, cookie)
    chain = root.call('getblockchaininfo')
    if chain.get('chain') != 'main':
        raise TransferError('Bitcoin Core must be on Bitcoin mainnet; refusing other networks.')
    if chain.get('initialblockdownload'):
        raise TransferError('Bitcoin Core is still synchronizing.')
    wallet_names = root.call('listwallets')
    print('Loaded wallets:', ', '.join(wallet_names) or '(none)')
    name = required('Exact loaded wallet name')
    if name not in wallet_names:
        raise TransferError('Wallet not currently loaded in Bitcoin Core.')
    rpc = BitcoinRPC(rpcurl, cookie, name)
    rpc.call('getwalletinfo')
    destination = required('Recipient Bitcoin mainnet address')
    if not rpc.call('validateaddress', destination).get('isvalid'):
        raise TransferError('Invalid Bitcoin address.')
    amount = amount_input('BTC to send', 8)
    max_fee = amount_input('Maximum total fee in BTC (safety cap)', 8, '0.0005')
    wallet_balance = rpc.call('getbalances').get('mine', {}).get('trusted', 'unknown')
    print(f'Confirmed available wallet balance (trusted): {wallet_balance} BTC')
    print(f'\nProposed: {amount:f} BTC -> {destination}\nFee hard limit: {max_fee:f} BTC')
    if not confirm_prepare():
        print('Cancelled before construction.'); return
    # Bitcoin Core selects inputs/change. Never subtract fees from recipient amount.
    funded = rpc.call('walletcreatefundedpsbt', [], [{destination: float_exact(amount)}], 0,
                      {'replaceable': True})
    fee = Decimal(str(funded['fee']))
    if fee <= 0 or fee > max_fee:
        raise TransferError(f'Calculated fee {fee:f} BTC violates maximum {max_fee:f} BTC. Not signed.')
    decoded = rpc.call('decodepsbt', funded['psbt'])
    original = verify_bitcoin_outputs(rpc, decoded['tx'], destination, amount)
    print('\n[BITCOIN PRE-BROADCAST REVIEW]')
    print(f'  Network: Bitcoin MAINNET\n  Sending wallet: {name}\n  Recipient: {destination}')
    print(f'  Amount: {amount:f} BTC\n  Estimated miner fee: {fee:f} BTC')
    print(f'  Total approximate debit: {amount+fee:f} BTC')
    for idx, (addr, val) in enumerate(original):
        print(f'  Output {idx}: {addr} — {val:f} BTC ' + ('[RECIPIENT]' if addr == destination else '[CHANGE]'))
    print('  This tool does not auto-unlock your Bitcoin wallet or access its recovery phrase.')
    if not confirm_send(destination, amount, 'BTC'):
        print('Cancelled: PSBT was not signed or broadcast.'); return
    signed = rpc.call('walletprocesspsbt', funded['psbt'])
    finalized = rpc.call('finalizepsbt', signed['psbt'])
    if not finalized.get('complete') or not finalized.get('hex'):
        raise TransferError('Wallet could not fully sign the PSBT (watch-only/hardware signing may require external steps). NOT broadcast.')
    raw_tx = finalized['hex']
    final_tx = rpc.call('decoderawtransaction', raw_tx)
    final_outputs = verify_bitcoin_outputs(rpc, final_tx, destination, amount)
    if final_outputs != original:
        raise TransferError('Signed transaction outputs changed! NOT broadcast.')
    mempool = rpc.call('testmempoolaccept', [raw_tx])
    if not mempool or not mempool[0].get('allowed'):
        raise TransferError('Bitcoin Core mempool test rejected transaction: ' + str(mempool))
    txid = rpc.call('sendrawtransaction', raw_tx)
    print(f'\n[SUBMITTED] Bitcoin TXID: {txid}\nConfirm it in Bitcoin Core; submission is not final confirmation.')


class MoneroRPC:
    def __init__(self, base_url: str, username: str, password: str):
        self.base = safe_loopback_url(base_url)
        try:
            import requests
            from requests.auth import HTTPDigestAuth
        except ImportError as e:
            raise TransferError('Missing requests dependency. Run the installer.') from e
        self.requests = requests
        self.auth = HTTPDigestAuth(username, password) if username else None
        self.url = self.base + '/json_rpc'

    def call(self, method: str, params: dict | None = None) -> dict:
        body = {'jsonrpc': '2.0', 'id': 'vaultforge', 'method': method,
                'params': params if params is not None else {}}
        try:
            response = self.requests.post(self.url, json=body, auth=self.auth,
                                          timeout=(4, 45), allow_redirects=False)
            if response.status_code != 200:
                raise TransferError(f'Monero RPC HTTP status {response.status_code}; check local wallet RPC login.')
            if len(response.content) > 2_000_000:
                raise TransferError('Monero RPC response unexpectedly large.')
            decoded = response.json()
        except self.requests.RequestException as e:
            raise TransferError(f'Monero wallet RPC connection failed for {method}: {e}') from e
        except ValueError as e:
            raise TransferError('Invalid Monero RPC JSON response.') from e
        if decoded.get('error'):
            raise TransferError(f'Monero RPC {method}: {decoded["error"]}')
        if not isinstance(decoded.get('result'), dict):
            raise TransferError('Unexpected Monero RPC result.')
        return decoded['result']


def monero_transfer():
    print('\nMONERO — local monero-wallet-rpc (native XMR, mainnet only)')
    url = safe_loopback_url(prompt('monero-wallet-rpc address', 'http://127.0.0.1:18082'))
    username = prompt('Wallet RPC authentication username (blank only if auth disabled)')
    password = getpass.getpass('Wallet RPC password (not saved): ') if username else ''
    if not username:
        print('WARNING: unauthenticated wallet RPC is risky, even on loopback. Prefer --rpc-login.')
    rpc = MoneroRPC(url, username, password)
    info = rpc.call('get_wallet_info')
    if info.get('network_type', '').lower() != 'mainnet':
        raise TransferError('Only Monero mainnet wallet RPC supported.')
    if info.get('wallet_type', '').lower() in ('watch only', 'background'):
        raise TransferError('This Monero wallet cannot sign transfers.')
    height, daemon_height = info.get('wallet_block_height'), info.get('daemon_block_height')
    if isinstance(height, int) and isinstance(daemon_height, int) and height + 5 < daemon_height:
        raise TransferError('Monero wallet is not sufficiently synced.')
    destination = required('Recipient Monero mainnet address (no alias/domain)')
    valid = rpc.call('validate_address', {'address': destination, 'any_net_type': False,
                                          'allow_openalias': False})
    if not valid.get('valid') or valid.get('nettype') != 'mainnet':
        raise TransferError('Invalid Monero MAINNET destination.')
    amount = amount_input('XMR to send', 12)
    max_fee = amount_input('Maximum network fee (XMR)', 12, '0.01')
    available = int(rpc.call('get_balance', {'account_index': 0}).get('unlocked_balance', 0))
    print(f'Unlocked balance: {Decimal(available)/10**12:f} XMR')
    if units(amount, 12) >= available:
        raise TransferError('Not enough unlocked balance (including fees).')
    print(f'\nProposed: {amount:f} XMR -> {destination}\nFee hard limit: {max_fee:f} XMR')
    print('Preparing may reserve outputs within your wallet until refreshed; it does NOT broadcast.')
    if not confirm_prepare():
        print('Cancelled before construction.'); return
    planned = rpc.call('transfer', {
        'destinations': [{'address': destination, 'amount': units(amount, 12)}],
        'account_index': 0, 'priority': 1, 'do_not_relay': True,
        'get_tx_metadata': True, 'unlock_time': 0,
    })
    fee_atomic = planned.get('fee')
    metadata = planned.get('tx_metadata')
    if not isinstance(fee_atomic, int) or fee_atomic <= 0 or not metadata:
        raise TransferError('Monero wallet did not return a valid prepared transaction / fee / metadata. NOT broadcast.')
    fee = Decimal(fee_atomic) / 10**12
    if fee > max_fee or units(amount, 12) + fee_atomic > available:
        raise TransferError(f'Monero actual fee {fee:f} XMR exceeds cap or available balance. NOT broadcast.')
    if int(planned.get('amount', -1)) != units(amount, 12):
        raise TransferError('Monero wallet reported an unexpected sent amount. NOT broadcast.')
    tx_hash = planned.get('tx_hash')
    print('\n[MONERO PRE-BROADCAST REVIEW]')
    print(f'  Network: XMR MAINNET\n  Recipient: {destination}\n  Amount: {amount:f} XMR')
    print(f'  Wallet-calculated miner fee: {fee:f} XMR\n  Maximum debit: {amount+fee:f} XMR')
    if tx_hash:
        print(f'  Prepared transaction hash: {tx_hash}')
    if not confirm_send(destination, amount, 'XMR'):
        print('Cancelled: prepared transaction was NOT relayed.'); return
    sent = rpc.call('relay_tx', {'hex': metadata})
    if not sent.get('tx_hash'):
        raise TransferError('Monero relay returned no transaction hash; check wallet history.')
    print(f'\n[SUBMITTED] Monero TXID: {sent["tx_hash"]}\nCheck Monero wallet RPC for confirmations.')


def load_keystore_header(path: Path) -> tuple[dict, str]:
    try:
        if path.stat().st_size > 1_000_000:
            raise TransferError('Keystore file unexpectedly large.')
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise TransferError(f'Cannot read Ethereum V3 keystore: {e}') from e
    addr = data.get('address')
    if not isinstance(addr, str) or not re.fullmatch(r'(0x)?[0-9a-fA-F]{40}', addr):
        raise TransferError('Keystore is missing a valid Ethereum address field.')
    if 'crypto' not in data and 'Crypto' not in data:
        raise TransferError('Not an encrypted Ethereum V3 keystore. Raw keys and seed files are not supported.')
    return data, '0x' + addr.removeprefix('0x')


def evm_fee_params(w3, gas: int) -> tuple[dict, int]:
    block = w3.eth.get_block('latest')
    base = block.get('baseFeePerGas')
    if base is not None:
        try:
            priority = int(w3.eth.max_priority_fee)
        except Exception:
            priority = min(max(int(w3.eth.gas_price) // 10, 1_000_000), 3_000_000_000)
        if priority < 0:
            raise TransferError('Invalid network priority fee.')
        max_fee = int(base) * 2 + priority
        if max_fee <= 0:
            raise TransferError('Invalid EVM gas pricing.')
        return {'type': 2, 'maxPriorityFeePerGas': priority, 'maxFeePerGas': max_fee}, gas * max_fee
    gas_price = int(w3.eth.gas_price)
    if gas_price <= 0:
        raise TransferError('Invalid EVM gas price.')
    return {'gasPrice': gas_price}, gas * gas_price


def evm_transfer(token_mode: bool = False):
    try:
        from web3 import Web3
        from eth_account import Account
    except ImportError as e:
        raise TransferError('web3/eth-account missing. Run the installer.') from e
    print('\nEVM — encrypted Ethereum V3 keystore, local signing, mainnets only')
    print('Select network carefully: an identical 0x address can exist on different chains.')
    codes = list(COIN_NETWORKS)
    for i, code in enumerate(codes, 1):
        network, chainid, currency = COIN_NETWORKS[code]
        print(f'  {i:2d}. {code:7s} {network:24s} (chain {chainid}, gas {currency})')
    choice = required('Network number or code').upper()
    if choice.isdecimal() and 1 <= int(choice) <= len(codes):
        choice = codes[int(choice)-1]
    if choice not in COIN_NETWORKS:
        raise TransferError('Unsupported EVM network. Cannot send cross-chain.')
    network, chainid, gas_symbol = COIN_NETWORKS[choice]
    rpcurl = safe_evm_rpc_url(required('Your trusted RPC HTTPS URL (or local HTTP)'))
    w3 = Web3(Web3.HTTPProvider(rpcurl, request_kwargs={'timeout': 20}))
    if not w3.is_connected():
        raise TransferError('Cannot reach EVM RPC endpoint.')
    actual_chainid = int(w3.eth.chain_id)
    if actual_chainid != chainid:
        raise TransferError(f'Wrong chain! Selected chain {chainid}, RPC reports {actual_chainid}. NOT proceeding.')
    ks_path = Path(required('Encrypted Ethereum V3 keystore JSON path')).expanduser()
    ks_data, raw_address = load_keystore_header(ks_path)
    source = Web3.to_checksum_address(raw_address)
    destination = required('Destination 0x wallet address (not ENS)')
    if not Web3.is_address(destination):
        raise TransferError('Invalid recipient EVM address.')
    destination = Web3.to_checksum_address(destination)
    if destination == source:
        raise TransferError('Source and destination are the same address.')
    contract_address = None
    contract = None
    fn = None
    decimals = 18
    if token_mode:
        token_address = required('Verified ERC-20 contract 0x address for THIS chain')
        if not Web3.is_address(token_address):
            raise TransferError('Invalid ERC-20 contract address.')
        contract_address = Web3.to_checksum_address(token_address)
        if not w3.eth.get_code(contract_address):
            raise TransferError('No contract deployed at token address on this chain.')
        contract = w3.eth.contract(address=contract_address, abi=ERC20_ABI)
        decimals = int(contract.functions.decimals().call())
        if not 0 <= decimals <= 36:
            raise TransferError('Contract returned unsafe token decimals.')
        symbol = str(contract.functions.symbol().call())
        if not re.fullmatch(r'[\w.+-]{1,24}', symbol):
            raise TransferError('Contract symbol is not safely displayable.')
        print(f'  Token contract says symbol = {symbol}, decimals = {decimals}; VERIFY CONTRACT INDEPENDENTLY.')
        if prompt('Type VERIFIED CONTRACT after checking a trusted explorer') != 'VERIFIED CONTRACT':
            print('Cancelled: token contract not verified.'); return
        asset_symbol = symbol
    else:
        # Intentionally refuse value transfers to EVM contracts without an explicit integration.
        if w3.eth.get_code(destination):
            raise TransferError('Recipient is a contract; native coin transfers to contracts are not supported by this safety-first tool.')
        asset_symbol = gas_symbol
    amount = amount_input('Asset amount to send', decimals)
    total_units = units(amount, decimals)
    if total_units >= 2**256:
        raise TransferError('Amount exceeds EVM integer limit.')
    balance_wei = int(w3.eth.get_balance(source))
    nonce = int(w3.eth.get_transaction_count(source, 'pending'))
    # EVM token transfers send 0 native coin and invoke ERC20 transfer(address,uint256) only.
    if token_mode:
        token_balance = int(contract.functions.balanceOf(source).call())
        if total_units > token_balance:
            raise TransferError('Insufficient token balance.')
        # Construct only the explicitly specified ERC-20 transfer function.
        # Avoid build_transaction() defaults that can silently inject gas pricing.
        tx = {'from': source, 'to': contract_address, 'value': 0,
              'nonce': nonce, 'chainId': chainid,
              'data': contract.encode_abi('transfer', args=[destination, total_units])}
        if tx.get('to', '').lower() != contract_address.lower():
            raise TransferError('ERC-20 transaction target differs from verified token contract.')
        gas_estimate = int(w3.eth.estimate_gas({'from': source, 'to': contract_address,
                                                'value': 0, 'data': tx['data']}))
    else:
        if total_units > balance_wei:
            raise TransferError('Insufficient native-coin balance.')
        tx = {'from': source, 'to': destination, 'value': total_units,
              'nonce': nonce, 'chainId': chainid}
        gas_estimate = int(w3.eth.estimate_gas({'from': source, 'to': destination, 'value': total_units}))
    if gas_estimate < 21000 or gas_estimate > 500_000:
        raise TransferError(f'Unexpected gas estimate {gas_estimate}; manual wallet review required.')
    gas = min(500_000, (gas_estimate * 12 + 9) // 10)
    fee_fields, max_gas_cost = evm_fee_params(w3, gas)
    tx.update(fee_fields)
    tx['gas'] = gas
    native_cost = max_gas_cost + (0 if token_mode else total_units)
    if balance_wei < native_cost:
        raise TransferError('Insufficient native balance to pay amount + MAXIMUM possible gas.')
    max_network_fee = Decimal(max_gas_cost) / Decimal(10**18)
    user_limit = amount_input(f'Maximum acceptable gas fee in {gas_symbol}', 18, '0.01')
    if max_network_fee > user_limit:
        raise TransferError(f'Gas fee cap exceeded: at most {max_network_fee:f} {gas_symbol} vs {user_limit:f}.')
    print('\n[EVM PRE-BROADCAST REVIEW]')
    print(f'  Network: {network} (chain ID {chainid})\n  From: {source}\n  To: {destination}')
    if token_mode:
        print(f'  ERC-20 contract: {contract_address} (contract claims {asset_symbol}/{decimals} decimals)')
        print('  Token behavior may include transfer fees/freezes; only this exact transfer method is requested.')
    print(f'  Amount: {amount:f} {asset_symbol}\n  Account nonce: {nonce}')
    print(f'  Gas estimate: {gas_estimate}; gas limit: {gas}\n  Maximum gas debit: {max_network_fee:f} {gas_symbol}')
    print('  The RPC endpoint learns your public account/address and observes your transaction.')
    print('  Signing only requires the encrypted keystore password; never paste a recovery phrase or raw key.')
    if not confirm_send(destination, amount, asset_symbol):
        print('Cancelled before password entry/signing.'); return
    pw = getpass.getpass('Ethereum V3 keystore password (hidden; never saved): ')
    try:
        private_key = Account.decrypt(ks_data, pw)
    except (ValueError, KeyError, TypeError) as e:
        raise TransferError('Keystore password/decryption failed. NOT broadcast.') from e
    acct = Account.from_key(private_key)
    if acct.address.lower() != source.lower():
        raise TransferError('Decrypted keystore public address does not match preview. NOT broadcast.')
    # 'from' is used for RPC estimation only; eth-account signs a transaction
    # that contains no from field (sender is recovered from its signature).
    signable_tx = {k: v for k, v in tx.items() if k != 'from'}
    signed = acct.sign_transaction(signable_tx)
    recovered = Account.recover_transaction(signed.raw_transaction)
    if recovered.lower() != source.lower():
        raise TransferError('Signed transaction sender mismatch. NOT broadcast.')
    txhash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    print(f'\n[SUBMITTED] {network} TX hash: {txhash}\nTrack it on a trusted chain explorer. Submission is not confirmation.')


def main_menu():
    print(f'\nVaultForge SecureTransfer v{VERSION}')
    print('Not audited. No auto-sends, no seed-phrase entry, no cross-chain bridging.')
    while True:
        print('\n1. Send BTC (Bitcoin Core PSBT)')
        print('2. Send XMR (monero-wallet-rpc prepare + relay)')
        print('3. Send EVM native coin (ETH, BNB, POL, etc.)')
        print('4. Send ERC-20 token (specified contract on EVM chain)')
        print('5. View networks and security notice')
        print('0. Exit')
        choice = prompt('Select')
        try:
            if choice == '0':
                print('Closed.'); return
            elif choice == '1': bitcoin_transfer()
            elif choice == '2': monero_transfer()
            elif choice == '3': evm_transfer(False)
            elif choice == '4': evm_transfer(True)
            elif choice == '5':
                print('BTC, XMR, ' + ', '.join(COIN_NETWORKS.keys()) + '; ERC-20 on EVM chains (verified contract).')
                print('Never send across chains, import a seed into this transfer tool, or approve an unknown contract.')
                print('A USB storage device is not a secure hardware wallet. Use a verified hardware signer for larger sums.')
                print('VaultForge .vault files are NOT loaded/signed by this program. Restore via verified compatible wallet first.')
            else: print('Choose 0–5.')
        except (TransferError, ValueError, KeyError) as e:
            print(f'\n[STOP — NOTHING FURTHER BROADCAST BY THIS STEP] {e}')
        except KeyboardInterrupt:
            print('\nInterrupted. If a broadcast was underway, check wallet history before retrying.')
        except Exception as e:
            # Network failures after a send attempt can be ambiguous: a transaction
            # may have reached the network despite a timeout/error to this client.
            print(f'\n[ERROR] {type(e).__name__}: {e}')
            print('If a broadcast may have started, check the original wallet and chain explorer BEFORE retrying.')


def main():
    parser = argparse.ArgumentParser(description='VaultForge SecureTransfer — interactive transfer guard')
    parser.add_argument('--list-networks', action='store_true')
    args = parser.parse_args()
    if args.list_networks:
        print('BTC — Bitcoin Core; XMR — monero-wallet-rpc; EVM:')
        for name, (network, chain, sym) in COIN_NETWORKS.items():
            print(f'{name:6s}  {network:22s}  chain ID {chain:6d}  gas {sym}')
        return
    try:
        main_menu()
    except (EOFError, KeyboardInterrupt):
        print('\nExited.')


if __name__ == '__main__':
    main()
