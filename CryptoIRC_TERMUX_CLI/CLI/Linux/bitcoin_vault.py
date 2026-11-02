"""Vault-backed BTC P2WPKH receive/balance/send through a local Bitcoin Core node.

PREVIEW: Core signs with the matching in-memory WIF over loopback RPC; Core does
not import a wallet, but the Core process temporarily receives secret key data.
Never connect this RPC service to the internet. Confirm signing semantics using
Bitcoin Core signet before risking mainnet funds.

Scope: original BIP84 external index-0 address only; change returns to that same
address (address reuse). No imported Core wallet or third-party block explorer.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import hashlib
import os
from pathlib import Path
import re

import vault_bridge as bridge
import wallet_core as wc
import transfer_engine as te

SAT = Decimal('0.00000001')
MAX_RATE = Decimal('500')  # maximum sat/vbyte selectable in this preview
MAX_INPUTS = 40
MIN_CHANGE = 1000  # satoshis, conservative threshold to avoid dust
BTC_TXID = re.compile(r'[0-9a-fA-F]{64}\Z')


@dataclass(frozen=True)
class Identity:
    address: str
    script_hex: str
    wif: str | None  # only derive on send, never print, log, or persist
    chain: str


def require_btc_entry(payload: dict) -> dict:
    bridge.validate_payload(payload)
    matches = [w for w in payload['wallets'] if isinstance(w, dict) and w.get('coin') == 'BTC']
    if len(matches) != 1:
        raise te.TransferError('Selected vault must contain exactly one BTC account. Choose the correct .vault file.')
    return matches[0]


def derive_identity(payload: dict, entry: dict, chain: str = 'main', *, signing: bool = False) -> Identity:
    """Cross-check stored mainnet address + path against mnemonic before allowing signing.

    For signet/testnet, use m/84'/1'/0'/0/0 with the SAME mnemonic; this is a
    separate TEST address, and NEVER the stored mainnet bc1 address.
    """
    bridge.validate_payload(payload)
    if not any(w is entry for w in payload['wallets']):
        raise te.TransferError('BTC account is not part of this unlocked vault.')
    if entry.get('coin') != 'BTC' or entry.get('derivation') != "m/84'/0'/0'/0/0":
        raise te.TransferError('Unexpected Bitcoin derivation path. Cannot sign.')
    index = entry.get('seed_group')
    if type(index) is not int or index < 0 or index >= len(payload['groups']):
        raise te.TransferError('Bitcoin seed group is invalid.')
    group = payload['groups'][index]
    if not isinstance(group, dict) or group.get('scheme') != 'bip39':
        raise te.TransferError('BTC requires a BIP39 seed group.')
    mnemonic = wc.validate_phrase('bip39', group.get('mnemonic', ''))
    passphrase = group.get('passphrase')
    if not isinstance(passphrase, str):
        raise te.TransferError('BTC seed passphrase is invalid.')
    if chain not in ('main', 'signet', 'test', 'testnet4'):
        raise te.TransferError('Unsupported Bitcoin chain.')
    try:
        from bip_utils import Bip39SeedGenerator, Bip84, Bip84Coins, Bip44Changes
    except ImportError as exc:
        raise te.TransferError('bip_utils unavailable: run the VaultForge Python 3.12 installer.') from exc
    seed = Bip39SeedGenerator(mnemonic).Generate(passphrase)

    def node_for(coin):
        return Bip84.FromSeed(seed, coin).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)

    main_node = node_for(Bip84Coins.BITCOIN)
    if main_node.PublicKey().ToAddress() != entry.get('address'):
        raise te.TransferError('BTC mnemonic/passphrase does not derive the saved mainnet address. REFUSING.')
    node = main_node if chain == 'main' else node_for(Bip84Coins.BITCOIN_TESTNET)
    pubkey = node.PublicKey().RawCompressed().ToBytes()
    sha = hashlib.sha256(pubkey).digest()
    try:
        h160 = hashlib.new('ripemd160', sha).digest()
    except ValueError as exc:
        raise te.TransferError('RIPEMD-160 unavailable on this Python installation.') from exc
    if len(pubkey) != 33:
        raise te.TransferError('Invalid compressed public key.')
    # Native SegWit v0 P2WPKH scriptPubKey, same address that bip_utils derived.
    return Identity(node.PublicKey().ToAddress(), '0014' + h160.hex(),
                    node.PrivateKey().ToWif() if signing else None, chain)


def get_rpc(chain_choice: str = 'main') -> te.BitcoinRPC:
    defaults = {'main': '8332', 'signet': '38332', 'test': '18332', 'testnet4': '48332'}
    if chain_choice not in defaults:
        raise te.TransferError('Unsupported Bitcoin network.')
    rpc_url = te.safe_loopback_url(te.prompt('Bitcoin Core localhost RPC address', 'http://127.0.0.1:' + defaults[chain_choice]))
    base = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / 'Bitcoin' if os.name == 'nt' else Path.home() / '.bitcoin'
    subfolder = {'main': '', 'signet': 'signet', 'test': 'testnet3', 'testnet4': 'testnet4'}[chain_choice]
    cookie_default = base / subfolder / '.cookie'
    cookie = Path(te.prompt('Bitcoin Core RPC cookie path', str(cookie_default)))
    rpc = te.BitcoinRPC(rpc_url, cookie)
    check_node(rpc, chain_choice)
    import security_center as security
    security.verify_bitcoin_tor(rpc)
    return rpc


def check_node(rpc, expected: str = 'main') -> dict:
    info = rpc.call('getblockchaininfo')
    if not isinstance(info, dict) or info.get('chain') != expected:
        raise te.TransferError(f'Wrong Bitcoin network: expected {expected}, got {info.get("chain") if isinstance(info, dict) else "unknown"}.')
    if info.get('initialblockdownload') or int(info.get('blocks', 0)) < 1:
        raise te.TransferError('Bitcoin Core is not fully synchronized. Cannot verify spendable BTC.')
    if (Decimal(str(info.get('verificationprogress', 0))) < Decimal('0.999')):
        raise te.TransferError('Bitcoin Core has not fully verified the blockchain.')
    if int(info.get('headers', info['blocks'])) - int(info['blocks']) > 2:
        raise te.TransferError('Bitcoin Core is still catching up with block headers.')
    return info


def btc_to_sat(value) -> int:
    try:
        d = Decimal(str(value))
        sat = d / SAT
        if not d.is_finite() or d < 0 or sat != sat.to_integral_value():
            raise ValueError('Non-satoshi Bitcoin amount from node.')
        return int(sat)
    except (ArithmeticError, ValueError) as exc:
        raise te.TransferError('Invalid exact Bitcoin amount returned from node.') from exc


def sat_to_btc(sat: int) -> Decimal:
    return sat * SAT


def scan_utxos(rpc, identity: Identity) -> tuple[list[dict], int]:
    """Only confirmed, unspent *chain* UTXOs; verify each against mempool spends.

    Note: this cannot show pending incoming payments and does not scan address
    history or previously used BIP84 indices beyond the original 0/0 address.
    """
    print('[SCAN] Scanning the synchronized Bitcoin Core UTXO set; this may take several minutes.')
    info = check_node(rpc, identity.chain)
    scan = rpc.call('scantxoutset', 'start', [f'addr({identity.address})'])
    if not isinstance(scan, dict) or scan.get('success') is not True:
        raise te.TransferError('Bitcoin UTXO scan did not complete successfully.')
    height = int(scan.get('height', -1))
    if height < int(info['blocks']) - 2:
        raise te.TransferError('Bitcoin UTXO scan is stale. Try again after node synchronization.')
    raw = scan.get('unspents')
    if not isinstance(raw, list) or len(raw) > 500:
        raise te.TransferError('Unexpected number of UTXOs; this preview supports at most 500 for scanning.')
    available = []
    seen = set()
    for utxo in raw:
        if not isinstance(utxo, dict) or utxo.get('scriptPubKey', '').lower() != identity.script_hex:
            raise te.TransferError('UTXO does not belong to the derived BTC address.')
        txid = utxo.get('txid')
        vout = utxo.get('vout')
        if not isinstance(txid, str) or not BTC_TXID.fullmatch(txid) or type(vout) is not int or not 0 <= vout < 100000:
            raise te.TransferError('Bitcoin Core returned an invalid UTXO reference.')
        if (txid, vout) in seen:
            raise te.TransferError('Duplicate Bitcoin UTXO returned by node.')
        seen.add((txid, vout))
        sats = btc_to_sat(utxo.get('amount', -1))
        if sats == 0:
            continue
        # Scans include outputs already spent by UNCONFIRMED mempool transactions.
        live = rpc.call('gettxout', txid, vout, True)
        if live is None:
            continue
        if not isinstance(live, dict) or live.get('scriptPubKey', {}).get('hex', '').lower() != identity.script_hex:
            raise te.TransferError('Bitcoin UTXO changed or mismatches derived script.')
        if btc_to_sat(live.get('value', -1)) != sats:
            raise te.TransferError('Bitcoin UTXO amount mismatch.')
        confirmations = int(live.get('confirmations', 0))
        if live.get('coinbase') and confirmations < 101:
            continue
        if confirmations < 1:
            continue
        available.append({'txid': txid, 'vout': vout, 'sats': sats, 'scriptPubKey': identity.script_hex,
                          'confirmations': confirmations})
    return available, height


def build_payment_plan(utxos: list[dict], amount_sat: int, sat_per_vbyte: Decimal,
                       max_fee_sat: int) -> dict:
    """Conservative one-address coin selection, with static upper-bound vsize.

    Core's testmempoolaccept must independently verify fee and signature.
    Change returns to this *same* receiving address; no hidden change derivation.
    """
    if not isinstance(amount_sat, int) or amount_sat < 1000:
        raise te.TransferError('BTC amount must be at least 1000 satoshis in this preview.')
    if sat_per_vbyte <= 0 or sat_per_vbyte > MAX_RATE:
        raise te.TransferError('Fee rate must be >0 and <=500 sat/vbyte.')
    if max_fee_sat <= 0:
        raise te.TransferError('Maximum fee must be positive.')
    chosen = []
    total = 0
    # Largest confirmed UTXOs first to keep input count and fees low.
    for utxo in sorted(utxos, key=lambda u: u['sats'], reverse=True):
        if len(chosen) >= MAX_INPUTS:
            break
        chosen.append(utxo)
        total += utxo['sats']
        # P2WPKH input upper bound ~69 vB, outputs conservatively ~43 vB,
        # ~11 vB overhead; later decoderawtransaction/testmempoolaccept enforce actual.
        expected_fee = int((sat_per_vbyte * (11 + 69 * len(chosen) + 86)).to_integral_value(rounding=ROUND_CEILING))
        if total >= amount_sat + expected_fee:
            break
    if not chosen:
        raise te.TransferError('No spendable confirmed Bitcoin UTXOs found at this address.')
    rate_fee = int((sat_per_vbyte * (11 + 69 * len(chosen) + 86)).to_integral_value(rounding=ROUND_CEILING))
    if total < amount_sat + rate_fee:
        raise te.TransferError('Insufficient confirmed BTC for amount plus estimated fee.')
    change = total - amount_sat - rate_fee
    fee = rate_fee
    if 0 < change < MIN_CHANGE:
        fee += change
        change = 0
    if fee > max_fee_sat:
        raise te.TransferError(f'Estimated fee {sat_to_btc(fee):f} BTC exceeds your limit {sat_to_btc(max_fee_sat):f}.')
    return {'utxos': chosen, 'amount_sat': amount_sat, 'fee_sat': fee,
            'change_sat': change, 'total_sat': total, 'rate': sat_per_vbyte}


def inspect_transaction(rpc, raw_hex: str, plan: dict, recipient: str,
                        own_address: str, *, expected_vin: list | None = None) -> dict:
    decoded = rpc.call('decoderawtransaction', raw_hex)
    if not isinstance(decoded, dict):
        raise te.TransferError('Cannot decode Bitcoin transaction.')
    planned_inputs = {(u['txid'].lower(), u['vout']) for u in plan['utxos']}
    vin = decoded.get('vin', [])
    try:
        inputs = {(v['txid'].lower(), v['vout']) for v in vin}
    except (KeyError, TypeError, AttributeError) as exc:
        raise te.TransferError('Malformed Bitcoin transaction inputs.') from exc
    if len(vin) != len(planned_inputs) or inputs != planned_inputs:
        raise te.TransferError('Bitcoin transaction inputs changed unexpectedly.')
    if expected_vin is not None:
        # Signing adds txinwitness fields; compare only the spending intent.
        def intent(v):
            return (v.get('txid'), v.get('vout'), v.get('sequence'),
                    (v.get('scriptSig') or {}).get('hex', ''))
        if [intent(v) for v in vin] != [intent(v) for v in expected_vin]:
            raise te.TransferError('Signed Bitcoin transaction sequence or inputs changed.')
    amounts = {}
    for v in decoded.get('vout', []):
        script = v.get('scriptPubKey') or {}
        addr = script.get('address')
        if not addr or addr not in (recipient, own_address) or addr in amounts:
            raise te.TransferError('Unexpected, missing or duplicate Bitcoin output. REFUSING.')
        amounts[addr] = btc_to_sat(v.get('value', -1))
    expected = {recipient: plan['amount_sat']}
    if plan['change_sat']:
        expected[own_address] = plan['change_sat']
    if recipient == own_address or amounts != expected:
        raise te.TransferError('Bitcoin transaction amount or destination changed. REFUSING.')
    if sum(u['sats'] for u in plan['utxos']) - sum(amounts.values()) != plan['fee_sat']:
        raise te.TransferError('Bitcoin transaction fee changed. REFUSING.')
    return decoded


def fee_rate_from_node(rpc) -> Decimal | None:
    estimate = rpc.call('estimatesmartfee', 6)
    if not isinstance(estimate, dict) or estimate.get('feerate') is None:
        return None
    rate = (Decimal(str(estimate['feerate'])) * Decimal('100000')).quantize(Decimal('0.1'), rounding=ROUND_CEILING)
    return rate if 0 < rate <= MAX_RATE else None


def choose_test_chain() -> str:
    raw = te.prompt('Bitcoin network [main/signet/testnet4]', 'main').lower()
    if raw not in ('main', 'signet', 'testnet4'):
        raise te.TransferError('Choose main, signet or testnet4.')
    return raw


def bitcoin_receive() -> None:
    path, payload = bridge.unlock_selected()
    entry = require_btc_entry(payload)
    # Display mainnet from vault and verify public address independently.
    identity = derive_identity(payload, entry, 'main')
    print(f'\n[BITCOIN RECEIVE] Vault: {path.name}')
    print(f'  Bitcoin MAINNET BIP84 receiving address: {identity.address}')
    print('  Path: m/84\'/0\'/0\'/0/0 (single address in this preview)')
    print('  IMPORTANT: Send BTC mainnet ONLY to this address. Verify against independent wallet software.')
    print('  The address is safe to share; never share recovery words, BIP39 passphrase or vault password.')
    print('  Funds remain your responsibility. No network contact was made to show the address.')


def bitcoin_balance() -> None:
    path, payload = bridge.unlock_selected()
    entry = require_btc_entry(payload)
    chain = choose_test_chain()
    identity = derive_identity(payload, entry, chain)
    print(f'\n[BITCOIN {chain.upper()}] Vault: {path.name}; address: {identity.address}')
    if chain != 'main':
        print('[TEST ONLY] This is NOT your saved bc1 mainnet receive address.')
    rpc = get_rpc(chain)
    utxos, height = scan_utxos(rpc, identity)
    print(f'Confirmed, currently unspent: {sat_to_btc(sum(u["sats"] for u in utxos)):f} BTC')
    print(f'Confirmed UTXOs: {len(utxos)}; scanned Bitcoin Core block height: {height}')
    print('Does NOT include incoming mempool payments, historical transactions, or other derivation paths.')


def bitcoin_send() -> None:
    path, payload = bridge.unlock_selected()
    entry = require_btc_entry(payload)
    chain = choose_test_chain()
    # Verify the stored mainnet address before constructing the transaction.
    identity = derive_identity(payload, entry, chain)
    print(f'\n[BITCOIN SEND] Vault: {path.name}; {chain.upper()} address: {identity.address}')
    print('Requires your own synced local Bitcoin Core NODE, not a separate wallet.')
    print('SECURITY: Bitcoin Core temporarily receives the private key via LOCAL RPC to sign.')
    print('Do not enable remote RPC, rpc debug-parameter logging, or expose the cookie.')
    print('WARNING: This is an unaudited preview. Signet is recommended first.')
    if chain == 'main' and te.prompt('Type MAINNET to enable real-value BTC sending') != 'MAINNET':
        print('Canceled: mainnet sending authorization not provided.')
        return
    rpc = get_rpc(chain)
    destination = te.required('Destination BTC address for this exact network')
    if destination == identity.address or not rpc.call('validateaddress', destination).get('isvalid'):
        raise te.TransferError('Invalid destination for this network, or destination equals your own source address.')
    amount = te.amount_input('Amount BTC to send', 8)
    max_fee = te.amount_input('Maximum TOTAL miner fee BTC', 8, '0.0005')
    amount_sat = btc_to_sat(amount)
    max_fee_sat = btc_to_sat(max_fee)
    suggested = fee_rate_from_node(rpc)
    default = str(suggested) if suggested is not None else '5'
    raw_rate = te.prompt('Fee rate (satoshis per virtual byte; maximum 500)', default)
    try:
        sat_rate = Decimal(raw_rate)
    except Exception as exc:
        raise te.TransferError('Invalid BTC fee rate.') from exc
    if not sat_rate.is_finite() or sat_rate <= 0 or sat_rate > MAX_RATE:
        raise te.TransferError('BTC fee rate must be between 0 and 500 sat/vbyte.')
    print('Selecting confirmed UTXOs from your saved address...')
    utxos, height = scan_utxos(rpc, identity)
    plan = build_payment_plan(utxos, amount_sat, sat_rate, max_fee_sat)
    print(f'\n[BITCOIN PRE-SIGN REVIEW] network={chain}; height={height}')
    print(f'  From:      {identity.address}')
    print(f'  Recipient: {destination}')
    print(f'  Amount:    {amount:f} BTC')
    print(f'  Fee max:   {max_fee:f} BTC')
    print(f'  Fee plan:  {sat_to_btc(plan["fee_sat"]):f} BTC at target {sat_rate} sat/vB')
    print(f'  Change:    {sat_to_btc(plan["change_sat"]):f} BTC (returns to SAME original address)')
    print('  This preview reuses its receiving address for change, reducing privacy.')
    if not te.confirm_prepare():
        print('Canceled before transaction construction.')
        return
    inputs = [{'txid': u['txid'], 'vout': u['vout'], 'sequence': 0xfffffffd} for u in plan['utxos']]
    outputs = [{destination: te.float_exact(sat_to_btc(amount_sat))}]
    if plan['change_sat']:
        outputs.append({identity.address: te.float_exact(sat_to_btc(plan['change_sat']))})
    raw = rpc.call('createrawtransaction', inputs, outputs)
    unsigned = inspect_transaction(rpc, raw, plan, destination, identity.address)
    if not te.confirm_send(destination, amount, 'BTC'):
        print('Canceled: never signed or broadcast.')
        return
    # Critical: only send the derived WIF to YOUR OWN loopback Bitcoin Core node.
    prevouts = [{'txid': u['txid'], 'vout': u['vout'], 'scriptPubKey': u['scriptPubKey'],
                 'amount': te.float_exact(sat_to_btc(u['sats']))} for u in plan['utxos']]
    # Derive the secret as late as possible: only after the user authorizes sending.
    signer = derive_identity(payload, entry, chain, signing=True)
    if (signer.address, signer.script_hex) != (identity.address, identity.script_hex) or not signer.wif:
        raise te.TransferError('BTC signer mismatch; nothing signed.')
    signed = rpc.call('signrawtransactionwithkey', raw, [signer.wif], prevouts, 'ALL')
    if not isinstance(signed, dict) or signed.get('complete') is not True or not signed.get('hex'):
        raise te.TransferError('Bitcoin Core could not fully sign the BTC inputs. Nothing broadcast.')
    signed_hex = signed['hex']
    finalized = inspect_transaction(rpc, signed_hex, plan, destination, identity.address, expected_vin=unsigned['vin'])
    if unsigned.get('txid') != finalized.get('txid'):
        raise te.TransferError('Signed SegWit transaction ID differs from unsigned transaction. REFUSING.')
    if (unsigned.get('locktime'), unsigned.get('version')) != (finalized.get('locktime'), finalized.get('version')):
        raise te.TransferError('Signed transaction header changed. REFUSING.')
    limits = str((MAX_RATE / Decimal('100000')).quantize(Decimal('0.00000001')))
    check = rpc.call('testmempoolaccept', [signed_hex], limits)
    if not isinstance(check, list) or len(check) != 1 or check[0].get('allowed') is not True:
        raise te.TransferError('Bitcoin Core rejected the transaction: ' + str(check[0].get('reject-reason') if isinstance(check, list) and check else 'unknown'))
    node_fee = btc_to_sat(check[0].get('fees', {}).get('base', -1))
    if node_fee != plan['fee_sat'] or node_fee > max_fee_sat:
        raise te.TransferError('Bitcoin Core reports unexpected fee. Not broadcast.')
    vsize = check[0].get('vsize')
    if not isinstance(vsize, int) or vsize <= 0 or Decimal(node_fee) / vsize > MAX_RATE:
        raise te.TransferError('Bitcoin Core reports unexpected transaction size or excessive fee rate.')
    print(f'\n[PRE-BROADCAST] Node accepted unsigned intent and signed transaction. TXID: {finalized["txid"]}')
    print(f'Exact Core-confirmed fee: {sat_to_btc(node_fee):f} BTC; vsize: {vsize}')
    if te.prompt('Type BROADCAST to send the approved transaction') != 'BROADCAST':
        print('Canceled: signed transaction was NOT broadcast.')
        return
    # Keep Core's own fee rate guard active. Never disable using zero.
    try:
        txid = rpc.call('sendrawtransaction', signed_hex, limits)
    except te.TransferError:
        print(f'[UNKNOWN BROADCAST STATUS] TXID: {finalized["txid"]}')
        print('Look up this TXID in your local Bitcoin Core before attempting ANY retry.')
        raise
    if not isinstance(txid, str) or txid.lower() != finalized['txid'].lower():
        raise te.TransferError('Broadcast returned a different txid. Verify the signed txid in Core; do not retry.')
    print(f'[SUBMITTED] Bitcoin {chain.upper()} TXID: {txid}')
    print('Submitted is not confirmed. Monitor confirmations; do NOT blindly rebroadcast.')


def bitcoin_status() -> None:
    chain = choose_test_chain()
    rpc = get_rpc(chain)
    txid = te.required('Bitcoin transaction ID (64 hex characters)')
    if not BTC_TXID.fullmatch(txid):
        raise te.TransferError('Invalid Bitcoin transaction ID.')
    try:
        obj = rpc.call('getrawtransaction', txid, True)
    except te.TransferError:
        try:
            rpc.call('getmempoolentry', txid)
            print('[PENDING] Transaction currently in Bitcoin Core mempool; 0 confirmations.')
        except te.TransferError:
            print('[UNKNOWN] Node cannot locate transaction. This does NOT prove failure.')
            print('Bitcoin Core may need txindex=1 to check historical transactions not in a loaded wallet.')
        return
    if not isinstance(obj, dict):
        raise te.TransferError('Invalid transaction status response.')
    conf = obj.get('confirmations')
    print(f'TXID: {txid}; network: {chain}; confirmations: {conf if conf is not None else 0}')
    print('Confirmations may be reversed by a reorganization; there is no automatic recovery.')
