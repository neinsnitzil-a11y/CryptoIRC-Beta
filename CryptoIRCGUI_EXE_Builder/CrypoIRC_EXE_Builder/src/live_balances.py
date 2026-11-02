"""Read-only, chain-authoritative balance snapshots; never infer funds from local vaults.

Do not use these values to authorize sends: sending modules must do their own
fresh verification. An RPC failure is an unavailable balance, not zero.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
import re

@dataclass(frozen=True)
class BalanceSnapshot:
    source: str
    currency: str
    available: str
    total: str
    secondary: str
    secondary_label: str
    height: str
    timestamp_utc: str
    pending_note: str


def _positive_amount(value) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError('Unusable blockchain balance')
    return amount


def snapshot_btc(url: str, cookie: str, wallet: str) -> BalanceSnapshot:
    from live_crypto import checked_node
    from core.transfer import BitcoinRPC, TransferError
    rpc, chain = checked_node(url, cookie)
    if not wallet or wallet not in rpc.call('listwallets'):
        raise TransferError('No selected, loaded Bitcoin Core wallet')
    mine = BitcoinRPC(url, Path(cookie), wallet).call('getbalances').get('mine')
    if not isinstance(mine, dict):
        raise TransferError('Bitcoin Core balance not available')
    trusted = _positive_amount(mine.get('trusted'))
    pending = _positive_amount(mine.get('untrusted_pending', '0'))
    immature = _positive_amount(mine.get('immature', '0'))
    return BalanceSnapshot('Bitcoin Core','BTC',format(trusted, 'f'),format(trusted+pending+immature,'f'),
        format(pending,'f'), 'Untrusted pending',str(chain['blocks']),
        datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'Core trusted balance can include trusted unconfirmed change; pending funds may not be spendable. '
        + f'Immature: {immature:f} BTC.')


def snapshot_xmr(url: str, username: str, password: str) -> BalanceSnapshot:
    from backend import xmr_rpc
    rpc, info=xmr_rpc(url,username,password)
    bal=rpc.call('get_balance',{'account_index':0})
    total=_positive_amount(bal.get('balance'))/Decimal(10**12)
    unlocked=_positive_amount(bal.get('unlocked_balance'))/Decimal(10**12)
    if unlocked>total: raise ValueError('Invalid Monero unlocked balance')
    return BalanceSnapshot('Monero wallet RPC','XMR',format(unlocked,'f'),format(total,'f'),
        format(total-unlocked,'f'),'Locked or pending',str(info.get('wallet_block_height','—')),
        datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'XMR unlocked amount is the wallet-reported spendable amount; locked includes incoming and other reserves.')


def snapshot_evm(code: str, url: str, address: str, token_contract: str = '') -> BalanceSnapshot:
    from backend import evm_w3
    from core.transfer import COIN_NETWORKS, ERC20_ABI
    from web3 import Web3
    if not Web3.is_address(address): raise ValueError('Valid public EVM address required')
    w3=evm_w3(code,url)   # enforces chain ID; HTTPS-only remote endpoint
    addr=Web3.to_checksum_address(address)
    height=int(w3.eth.block_number)
    if not token_contract:
        val=_positive_amount(int(w3.eth.get_balance(addr, 'latest')))/Decimal(10**18)
        symbol=COIN_NETWORKS[code][2]
        note='Latest-block RPC balance. Broadcast transactions may remain pending until mined; network gas is deducted on confirmation.'
    else:
        if not Web3.is_address(token_contract): raise ValueError('Invalid token contract address')
        contract_addr=Web3.to_checksum_address(token_contract)
        if not w3.eth.get_code(contract_addr): raise ValueError('No contract deployed at that address')
        contract=w3.eth.contract(address=contract_addr,abi=ERC20_ABI)
        decimals=int(contract.functions.decimals().call())
        if decimals<0 or decimals>36: raise ValueError('Token decimals outside supported range')
        symbol=str(contract.functions.symbol().call())
        if not re.fullmatch(r'[A-Za-z0-9_.+\-]{1,24}',symbol): raise ValueError('Invalid token symbol')
        val=_positive_amount(int(contract.functions.balanceOf(addr).call()))/Decimal(10)**decimals
        note='Token symbol/contract are UNVERIFIED identity data. Independently check the contract address and chain. Native gas coin is separate.'
    return BalanceSnapshot(f'{code} RPC','{}'.format(symbol),format(val,'f'),format(val,'f'),
        '—','Pending: check transaction status',str(height),datetime.now(timezone.utc).isoformat(timespec='seconds'),note)


def transaction_state(source: str, txid: str, *, btc_url='', btc_cookie='', btc_wallet='',
                      xmr_url='', xmr_user='', xmr_password='', evm_code='', evm_url='') -> str:
    """Pending, confirmed, failed or unknown. Never claim submission equals confirmation."""
    if source == 'Bitcoin Core BTC':
        from live_crypto import wallet_transaction_status
        row = wallet_transaction_status(btc_url,btc_cookie,btc_wallet,txid)
        return f"{row['status']} • {row['confirmations']} confirmations"
    if source == 'Monero wallet RPC XMR':
        from backend import xmr_rpc
        rpc,_=xmr_rpc(xmr_url,xmr_user,xmr_password)
        r=rpc.call('get_transfer_by_txid',{'txid':txid})
        item=r.get('transfer') if isinstance(r,dict) else None
        if not item: return 'NOT YET FOUND IN MONERO WALLET'
        if item.get('double_spend_seen'):return 'CONFLICT / DOUBLE SPEND REPORTED'
        return f"{item.get('type','unknown').upper()} • {item.get('confirmations',0)} confirmations"
    from backend import evm_w3
    from web3.exceptions import TransactionNotFound
    if not re.fullmatch(r'(0x)?[0-9a-fA-F]{64}',txid):raise ValueError('Invalid transaction hash')
    w3=evm_w3(evm_code,evm_url)
    try:r=w3.eth.get_transaction_receipt(txid)
    except TransactionNotFound:return 'PENDING / NOT INCLUDED IN BLOCK'
    confirmations=max(0,int(w3.eth.block_number)-int(r['blockNumber'])+1)
    return f"{'CONFIRMED' if int(r['status'])==1 else 'REVERTED'} • {confirmations} block confirmations"
