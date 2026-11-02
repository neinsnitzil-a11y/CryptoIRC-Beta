"""Live, mainnet-only Bitcoin Core wallet operations for CRYPTO NOCTURNE.

Real transactions are signed by the user's *local Bitcoin Core* wallet, not
by a VaultForge BTC seed. This module must never import or accept BIP39 phrases.
A normal Bitcoin Core descriptor wallet uses Bitcoin Core's OWN backup file.
Do not infer a Bitcoin Core wallet is recoverable from a VaultForge .vault.
"""
from __future__ import annotations
import re
from pathlib import Path
from decimal import Decimal
from core.transfer import BitcoinRPC, TransferError, safe_loopback_url

WALLET_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,47}\Z")

def checked_node(url: str, cookie: str):
    rpc = BitcoinRPC(safe_loopback_url(url), Path(cookie))
    info = rpc.call('getblockchaininfo')
    if not isinstance(info, dict) or info.get('chain') != 'main':
        raise TransferError('Bitcoin Core is not connected to mainnet. No funds action allowed.')
    if info.get('initialblockdownload'):
        raise TransferError('Bitcoin Core is still downloading blocks. Balances and spends unavailable.')
    if not isinstance(info.get('blocks'), int):
        raise TransferError('Bitcoin Core has not returned a verified chain height.')
    return rpc, info

def node_summary(url: str, cookie: str) -> dict:
    rpc, info = checked_node(url, cookie)
    names = rpc.call('listwallets')
    if not isinstance(names, list):
        raise TransferError('Bitcoin Core did not return its loaded wallets.')
    return {'network':'Bitcoin mainnet', 'height':info['blocks'],
            'wallets':names, 'node_state':'SYNCED',
            'verification_progress':float(info.get('verificationprogress',0))}

def create_encrypted_core_wallet(url: str, cookie: str, name: str, password: str) -> dict:
    """Creates an encrypted descriptor wallet on the user's local Core node.

    Cannot generate a BIP39 recovery phrase; backupwallet is mandatory to
    prepare a recoverable Bitcoin Core wallet backup separately.
    """
    if not WALLET_NAME.fullmatch(name):
        raise TransferError('Wallet name: 1-48 letters, numbers, underscores or hyphens; start with a letter.')
    if not isinstance(password, str) or len(password) < 14 or len(password)>512:
        raise TransferError('Bitcoin Core wallet passphrase must have 14-512 characters.')
    rpc, _ = checked_node(url, cookie)
    if name in rpc.call('listwallets'):
        raise TransferError('A loaded wallet already uses that name.')
    # Core v25+ RPC: name, disable_private_keys, blank, passphrase,
    # avoid_reuse, descriptors, load_on_startup
    result = rpc.call('createwallet',name,False,False,password,False,True,True)
    if not isinstance(result,dict) or result.get('name')!=name:
        raise TransferError('Bitcoin Core did not confirm the created wallet name.')
    info = BitcoinRPC(url,Path(cookie),name).call('getwalletinfo')
    if not info.get('private_keys_enabled',False):
        raise TransferError('Bitcoin Core wallet is watch-only; cannot spend. Do not fund.')
    return {'wallet':name,'encrypted':True,'backup_required':True}

def backup_core_wallet(url: str, cookie: str, wallet: str, destination: str) -> Path:
    rpc,_ = checked_node(url,cookie)
    if wallet not in rpc.call('listwallets'):
        raise TransferError('Wallet is not loaded in Bitcoin Core.')
    path = Path(destination).expanduser().resolve()
    application_tree = Path(__file__).resolve().parent.parent
    if path == application_tree or application_tree in path.parents:
        raise TransferError('Backups must be saved OUTSIDE the application/installer source folder.')
    if path.suffix.lower() not in ('.dat','.bak'):
        raise TransferError('Select a backup destination ending in .dat or .bak.')
    if path.exists():
        raise TransferError('Backup destination already exists; refusing overwrite.')
    if not path.parent.is_dir():
        raise TransferError('Backup destination folder does not exist.')
    # Requires Bitcoin Core running on the same computer because it writes the file.
    result=BitcoinRPC(url,Path(cookie),wallet).call('backupwallet', str(path))
    if result is not None or not path.is_file() or path.stat().st_size < 100:
        raise TransferError('Backup was not verified on disk. DO NOT FUND this wallet.')
    return path

def wallet_transaction_status(url: str, cookie: str, wallet: str, txid: str) -> dict:
    if not isinstance(txid,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',txid):
        raise TransferError('Enter a full 64-character Bitcoin transaction ID.')
    rpc,_=checked_node(url,cookie)
    if wallet not in rpc.call('listwallets'):
        raise TransferError('Select a loaded Bitcoin Core wallet.')
    result=BitcoinRPC(url,Path(cookie),wallet).call('gettransaction',txid)
    conf=int(result.get('confirmations',0))
    return {'txid':txid, 'confirmations':conf, 'status':'CONFIRMED' if conf>0 else ('CONFLICTED' if conf<0 else 'UNCONFIRMED'),
            'amount':str(result.get('amount','')), 'fee':str(result.get('fee',''))}

def wallet_unlock_temporarily(url: str, cookie: str, wallet: str, password: str, seconds: int = 60):
    if not isinstance(password,str) or not password:
        return False
    if not (5<=seconds<=120):
        raise TransferError('Unsafe Bitcoin Core unlock timeout.')
    rpc,_ = checked_node(url,cookie)
    if wallet not in rpc.call('listwallets'):
        raise TransferError('Bitcoin Core wallet not loaded.')
    BitcoinRPC(url,Path(cookie),wallet).call('walletpassphrase',password,seconds)
    return True

def wallet_lock(url: str, cookie: str, wallet: str) -> None:
    BitcoinRPC(url,Path(cookie),wallet).call('walletlock')
