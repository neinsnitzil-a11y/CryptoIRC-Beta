"""Crypto & Creating Wallets backend.

Safety boundary: .vault is an encrypted SOFTWARE wallet, not a hardware signer.
Send supports BTC Core, XMR wallet RPC and ten EVM chains using a validated
keystore or a VaultForge BIP39 vault for EVM only. All sends use an explicit
prepare/preview followed by single-use authorization; no automation or batching.
No seeds, private keys, RPC credentials, or passwords are persisted here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import json, os, re, threading, secrets
from core import vaultforge as vf, transfer as tx

HOME = Path.home() / '.crypto_creating_wallets'
REGISTRY = HOME / 'registry.json'
EVM_TO_VAULT = {
    'ETH':'ETH','ETC':'ETC','BNB':'BSC','POL':'POLYGON','AVAX':'AVAXC',
    'ARB':'ARB','OP':'OP', 'BASE':'ETH', 'GNO':'ETH', 'CELO':'ETH',
}
TOKEN_NETWORK_ASSETS = {
    'ETH':('USDT-ETH','USDC-ETH','DAI-ETH'),
    'BNB':('USDT-BSC',),'POL':('USDT-POL',),
    'AVAX':('USDT-AVAX',),'ARB':('USDT-ARB',),
    'OP':('USDT-OP',),'BASE':('USDC-BASE',),
}
SENDABLE = {'BTC':'Bitcoin Core local RPC','XMR':'Monero wallet RPC', **{k:'EVM keystore or compatible encrypted vault' for k in tx.COIN_NETWORKS}}


def save_registry(vaults: list[str], watch: list[dict]) -> None:
    HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Public paths and addresses only. Never store decrypted wallet payloads.
    safe_watch = []
    for r in watch:
        if all(isinstance(r.get(key), str) for key in ('label', 'coin', 'address')):
            safe_watch.append({key: r[key][:300] for key in ('label', 'coin', 'address')})
    blob = json.dumps({'version': 1, 'vault_paths': sorted(set(str(p) for p in vaults)),
                       'watch_only': safe_watch}, indent=2).encode()
    tmp = HOME / ('.registry_' + secrets.token_hex(6))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(blob); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, REGISTRY)
    finally:
        tmp.unlink(missing_ok=True)


def load_registry() -> tuple[list[str], list[dict]]:
    if not REGISTRY.exists(): return [], []
    if REGISTRY.stat().st_size > 2_000_000: raise ValueError('Registry file too large')
    d = json.loads(REGISTRY.read_text(encoding='utf-8'))
    if d.get('version') != 1: raise ValueError('Unknown registry version')
    return [v for v in d.get('vault_paths', []) if isinstance(v, str)], [v for v in d.get('watch_only', []) if isinstance(v, dict)]


def read_vault(path: str, password: str) -> dict:
    p = Path(path).expanduser()
    if p.is_symlink() or not p.is_file() or p.suffix.lower() != '.vault':
        raise ValueError('Not a regular .vault file')
    if p.stat().st_size > vf.MAX_VAULT_BYTES: raise ValueError('Vault too large')
    payload = vf.decrypt_payload(p.read_bytes(), password)
    if payload.get('format') != 'VaultForge-Unlocked-v1': raise ValueError('Incompatible vault')
    if not isinstance(payload.get('wallets'), list) or not isinstance(payload.get('groups'), list):
        raise ValueError('Missing required vault sections')
    return payload


def public_wallets(path: str, password: str) -> list[dict]:
    payload = read_vault(path, password)
    return [{'coin': e['coin'], 'address': e['address'], 'derivation':e.get('derivation',''), 'network':e.get('network',e['coin']), 'generation_method':e.get('generation_method',''), 'warning':e.get('warning',''), 'underlying_coin':e.get('underlying_coin',e['coin'])} for e in payload['wallets']]


def build_wallets(folder: str, coins: list[str], count: int, words: int, password: str,
                  bip39_passphrase: str = '', import_seed: str = '') -> list[str]:
    vf.load_crypto()
    if not 1 <= count <= 20: raise ValueError('Create between 1 and 20 wallet sets')
    if len(password) < 14: raise ValueError('Vault password must be 14+ characters')
    if words not in (12, 24): raise ValueError('BIP39 must use 12 or 24 words')
    coins = list(dict.fromkeys(coins))
    if not coins or any(c not in vf.COIN_BY_CODE for c in coins): raise ValueError('Invalid selected coins')
    if import_seed and count != 1: raise ValueError('Import creates exactly one wallet set')
    if import_seed and 'XMR' in coins and len(coins) > 1:
        raise ValueError('Import XMR separately from BIP39 coins')
    if import_seed:
        import_seed = vf.validate_phrase('monero' if coins == ['XMR'] else 'bip39', import_seed)
    folder_path = vf.secure_dir(Path(folder).expanduser().resolve())
    created = []
    for i in range(count):
        groups, entries = [], []
        bip_coins = [c for c in coins if c != 'XMR']
        if bip_coins:
            phrase = import_seed or vf.generate_bip39(words)
            groups.append({'scheme':'bip39','mnemonic':phrase,'passphrase':bip39_passphrase})
            for code in bip_coins:
                entry = vf.derive_coin(code, phrase, bip39_passphrase)
                entry['seed_group'] = 0
                entries.append(entry)
        if 'XMR' in coins:
            phrase = import_seed or vf.generate_monero()
            groups.append({'scheme':'monero','mnemonic':phrase,'passphrase':''})
            entry = vf.derive_coin('XMR', phrase, '')
            entry['seed_group'] = len(groups)-1
            entries.append(entry)
        payload = {'format':'VaultForge-Unlocked-v1', 'created_utc':datetime.now(timezone.utc).isoformat(),
                   'wallets': entries, 'groups': groups,
                   'warnings':['Software wallet, not a secure hardware signer',
                               'Verify recovery and receive address with trusted wallet software before funding']}
        created.append(str(vf.write_new_vault(folder_path, payload, password)))
    return created


def verify_public_address(code: str, addr: str) -> bool:
    if code in ('ETH','ETC','BSC','POLYGON','AVAXC','ARB','OP','FTM','BNB','POL','AVAX','BASE','GNO','CELO'):
        return bool(re.fullmatch('0x[0-9a-fA-F]{40}', addr))
    if code == 'BTC': return bool(re.fullmatch(r'(bc1[ac-hj-np-z02-9]{10,90}|[13][a-km-zA-HJ-NP-Z1-9]{25,40})', addr))
    if code == 'XMR': return bool(re.fullmatch(r'[48][1-9A-HJ-NP-Za-km-z]{94,105}', addr))
    # Other networks require validation in compatible wallet before funding.
    return bool(addr and len(addr) < 300 and all(ord(c) >= 33 for c in addr))


@dataclass
class SendPlan:
    kind: str
    coin: str
    network: str
    source: str
    destination: str
    amount: Decimal
    fee: Decimal
    fee_symbol: str
    detail: str
    context: dict = field(repr=False)
    used: bool = False

    @property
    def challenge(self):
        return f'SEND {self.amount:f} {self.coin} {self.destination[-8:]}'


# BTC: get wallet from trusted local node, always test mainnet, inspect PSBT outputs.
def btc_wallets(url: str, cookie: str) -> list[str]:
    rpc = tx.BitcoinRPC(url, Path(cookie))
    inf = rpc.call('getblockchaininfo')
    if inf.get('chain') != 'main' or inf.get('initialblockdownload'):
        raise tx.TransferError('Bitcoin Core must be mainnet and synced')
    return rpc.call('listwallets')


def btc_receive(url: str, cookie: str, wallet: str) -> tuple[str, str]:
    if wallet not in btc_wallets(url, cookie): raise tx.TransferError('Bitcoin wallet not loaded')
    rpc = tx.BitcoinRPC(url, Path(cookie), wallet)
    address = rpc.call('getnewaddress', 'Crypto Suite Receive', 'bech32')
    if not rpc.call('getaddressinfo', address).get('ismine'):
        raise tx.TransferError('New address not owned by wallet')
    return address, 'New Bitcoin Core receiving address (mainnet)'


def btc_balance_history(url: str, cookie: str, wallet: str) -> tuple[str, list[dict]]:
    if wallet not in btc_wallets(url, cookie): raise tx.TransferError('Bitcoin wallet not loaded')
    rpc = tx.BitcoinRPC(url, Path(cookie), wallet)
    bal = rpc.call('getbalances').get('mine',{})
    transactions = rpc.call('listtransactions', '*', 50, 0, True)
    rows = [{'type': v.get('category',''), 'amount':str(v.get('amount','')),
             'txid':v.get('txid',''), 'confirmations':str(v.get('confirmations',''))} for v in transactions]
    return f"Trusted: {bal.get('trusted',0)} BTC | Pending: {bal.get('untrusted_pending',0)} BTC", rows


def prepare_btc(url: str, cookie: str, wallet: str, dest: str, amount_str: str, cap_str: str) -> SendPlan:
    if wallet not in btc_wallets(url, cookie): raise tx.TransferError('BTC wallet must be loaded')
    rpc = tx.BitcoinRPC(url, Path(cookie), wallet)
    if not rpc.call('validateaddress', dest).get('isvalid'): raise tx.TransferError('Invalid BTC address')
    amount = tx.amount_decimal(amount_str, 8); cap = tx.amount_decimal(cap_str, 8, 'fee cap')
    funded = rpc.call('walletcreatefundedpsbt', [], [{dest:tx.float_exact(amount)}], 0, {'replaceable': True})
    fee = Decimal(str(funded['fee']))
    if fee <= 0 or fee > cap: raise tx.TransferError(f'Bitcoin fee {fee} outside cap')
    outputs = tx.verify_bitcoin_outputs(rpc, rpc.call('decodepsbt',funded['psbt'])['tx'], dest, amount)
    return SendPlan('btc','BTC','Bitcoin mainnet',wallet,dest,amount,fee,'BTC',
                    '\n'.join(f'{"Recipient" if a == dest else "Wallet change"}: {a}\n{v} BTC' for a,v in outputs),
                    {'url':url,'cookie':cookie,'wallet':wallet,'psbt':funded['psbt'],'outputs':outputs})


def commit_btc(plan: SendPlan, wallet_passphrase: str = '') -> str:
    c = plan.context; rpc = tx.BitcoinRPC(c['url'], Path(c['cookie']), c['wallet'])
    unlocked_here = False
    try:
        if wallet_passphrase:
            from live_crypto import wallet_unlock_temporarily
            unlocked_here = wallet_unlock_temporarily(c['url'], c['cookie'], c['wallet'], wallet_passphrase)
        signed = rpc.call('walletprocesspsbt',c['psbt'])
        finalized = rpc.call('finalizepsbt',signed['psbt'])
        if not finalized.get('complete') or not finalized.get('hex'):
            raise tx.TransferError('Signer could not fully sign this PSBT; not broadcast')
        raw = finalized['hex']; parsed = rpc.call('decoderawtransaction', raw)
        if tx.verify_bitcoin_outputs(rpc, parsed, plan.destination, plan.amount) != c['outputs']:
            raise tx.TransferError('Final transaction differs from preview')
        mempool = rpc.call('testmempoolaccept', [raw])
        if not mempool or not mempool[0].get('allowed'):
            raise tx.TransferError('Mempool did not accept final Bitcoin transaction; not broadcast')
        return rpc.call('sendrawtransaction', raw)
    finally:
        if unlocked_here:
            try: rpc.call('walletlock')
            except Exception: pass  # Unlock expires automatically at Core within 60 seconds.


def xmr_rpc(url: str, username: str, password: str):
    rpc = tx.MoneroRPC(url, username, password)
    info = rpc.call('get_wallet_info')
    if str(info.get('network_type','')).lower() != 'mainnet':
        raise tx.TransferError('Monero wallet RPC must be MAINNET')
    h, d = info.get('wallet_block_height'), info.get('daemon_block_height')
    if isinstance(h,int) and isinstance(d,int) and h+5 < d:
        raise tx.TransferError('Monero wallet is not synchronized')
    return rpc, info


def xmr_receive(url: str, username: str, password: str) -> tuple[str,str]:
    rpc, _ = xmr_rpc(url,username,password)
    result = rpc.call('create_address',{'account_index':0,'label':'Crypto Suite Receive'})
    if not result.get('address') or not isinstance(result.get('address_index'),int):
        raise tx.TransferError('Monero wallet did not return a new subaddress')
    return result['address'], f"Monero NEW subaddress #{result['address_index']} (mainnet)"


def xmr_balance_history(url: str, username: str, password: str) -> tuple[str, list[dict]]:
    rpc, _ = xmr_rpc(url,username,password)
    bal = rpc.call('get_balance',{'account_index':0})
    res = rpc.call('get_transfers',{'in':True,'out':True,'pending':True,'pool':True,'failed':True,'account_index':0})
    history = []
    for key in ('in','out','pending','pool','failed'):
        for v in res.get(key,[]):
            history.append({'type':key,'amount':str(Decimal(v.get('amount',0))/10**12),
                            'txid':v.get('txid',''),'confirmations':str(v.get('confirmations',''))})
    return f"Balance: {Decimal(bal.get('balance',0))/10**12} XMR | Unlocked: {Decimal(bal.get('unlocked_balance',0))/10**12} XMR",history[:100]


def prepare_xmr(url: str, username: str, password: str, dest: str, amount_str: str, cap_str: str) -> SendPlan:
    rpc, info = xmr_rpc(url, username, password)
    if str(info.get('wallet_type','')).lower() in ('watch only','background'):
        raise tx.TransferError('Watch-only wallet cannot sign')
    valid = rpc.call('validate_address',{'address':dest,'any_net_type':False,'allow_openalias':False})
    if not valid.get('valid') or valid.get('nettype') != 'mainnet':
        raise tx.TransferError('Monero mainnet address invalid')
    amount=tx.amount_decimal(amount_str,12); cap=tx.amount_decimal(cap_str,12,'fee cap')
    available=int(rpc.call('get_balance',{'account_index':0}).get('unlocked_balance',0))
    if tx.units(amount,12) >= available: raise tx.TransferError('Insufficient unlocked XMR')
    planned=rpc.call('transfer',{'destinations':[{'address':dest,'amount':tx.units(amount,12)}],
                                 'account_index':0,'priority':1,'do_not_relay':True,
                                 'get_tx_metadata':True,'unlock_time':0})
    fee_atomic=planned.get('fee'); meta=planned.get('tx_metadata')
    if not isinstance(fee_atomic,int) or fee_atomic<=0 or not isinstance(meta,str) or not meta:
        raise tx.TransferError('Monero wallet did not return fee/tx metadata')
    fee=Decimal(fee_atomic)/10**12
    if fee>cap or tx.units(amount,12)+fee_atomic>available:
        raise tx.TransferError('Fee cap or unlocked balance exceeded; prepared transaction NOT relayed')
    if int(planned.get('amount',-1))!=tx.units(amount,12):
        raise tx.TransferError('Prepared XMR sent amount mismatch')
    return SendPlan('xmr','XMR','Monero mainnet','Local Monero wallet RPC',dest,amount,fee,'XMR',
                    'Prepared offline from relay; cancellation does NOT relay.\nPrepared TX: '+str(planned.get('tx_hash','')),
                    {'url':url,'username':username,'password':password,'metadata':meta})


def commit_xmr(plan: SendPlan) -> str:
    c=plan.context
    rpc,_ = xmr_rpc(c['url'],c['username'],c['password'])
    sent=rpc.call('relay_tx',{'hex':c['metadata']})
    if not sent.get('tx_hash'): raise tx.TransferError('No Monero hash returned; check wallet history before retrying')
    return sent['tx_hash']


def evm_w3(code: str, url: str):
    if code not in tx.COIN_NETWORKS: raise tx.TransferError('Unsupported EVM network')
    from web3 import Web3
    url=tx.safe_evm_rpc_url(url)
    w3 = Web3(Web3.HTTPProvider(url,request_kwargs={'timeout':20}))
    if not w3.is_connected(): raise tx.TransferError('RPC connection failed')
    if int(w3.eth.chain_id) != tx.COIN_NETWORKS[code][1]:
        raise tx.TransferError('RPC chain ID mismatch. Refusing cross-chain send')
    return w3


def _evm_vault_entry(payload: dict, code: str, source_asset: str = 'Auto') -> dict:
    """Select one exact asset/derivation. Never silently sign with another seed."""
    allowed={EVM_TO_VAULT[code],*TOKEN_NETWORK_ASSETS.get(code,())}
    candidates=[e for e in payload['wallets'] if e.get('coin') in allowed]
    if source_asset and source_asset != 'Auto':
        candidates=[e for e in candidates if e.get('coin')==source_asset]
    if len(candidates)!=1:
        raise tx.TransferError(f'Expected ONE matching vault asset for {code}; found {len(candidates)}. '
                               'Select the exact source asset in Send, or use a separate encrypted keystore.')
    return candidates[0]


def evm_source(code: str, key_path: str, source_kind: str, password: str = '', source_asset: str = 'Auto') -> str:
    from web3 import Web3
    if source_kind=='keystore':
        data, address = tx.load_keystore_header(Path(key_path).expanduser())
        return Web3.to_checksum_address(address)
    if source_kind!='vault': raise tx.TransferError('Unsupported EVM signing source')
    wallet_code = EVM_TO_VAULT.get(code)
    if not wallet_code: raise tx.TransferError('No compatible vault mapping for this EVM network')
    payload=read_vault(key_path,password)
    entry=_evm_vault_entry(payload,code,source_asset)
    if not Web3.is_address(entry['address']): raise tx.TransferError('Invalid source address in vault')
    return Web3.to_checksum_address(entry['address'])


def evm_address_from_vault(code: str, path: str, password: str, source_asset: str = 'Auto'):
    """Derive exact selected key, compare against the stored address, and sign once."""
    from bip_utils import Bip39SeedGenerator,Bip44,Bip44Coins,Bip44Changes
    from eth_account import Account
    payload=read_vault(path,password)
    entry=_evm_vault_entry(payload,code,source_asset)
    group=payload['groups'][entry['seed_group']]
    if group['scheme']!='bip39': raise tx.TransferError('Invalid seed scheme for EVM')
    wallet_code=entry.get('underlying_coin',entry['coin'])
    if wallet_code not in vf.COIN_BY_CODE:
        raise tx.TransferError('Unrecognized underlying signing derivation')
    coin_info=vf.COIN_BY_CODE[wallet_code]
    seed=Bip39SeedGenerator(group['mnemonic']).Generate(group.get('passphrase',''))
    account_index=entry.get('account_index',0)
    if not isinstance(account_index,int) or not 0<=account_index<=100:
        raise tx.TransferError('Invalid vault derivation account')
    node=Bip44.FromSeed(seed,getattr(Bip44Coins,coin_info[3])).Purpose().Coin().Account(account_index).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    acct=Account.from_key(node.PrivateKey().Raw().ToBytes())
    if acct.address.lower()!=entry['address'].lower():
        raise tx.TransferError('Derived signing key does not match stored receiving address. NOT sending')
    return acct


def evm_receive_balance(code: str, url: str, address: str) -> str:
    from web3 import Web3
    w3=evm_w3(code,url)
    if not Web3.is_address(address): raise tx.TransferError('Invalid EVM address')
    sym=tx.COIN_NETWORKS[code][2]
    val=Decimal(int(w3.eth.get_balance(Web3.to_checksum_address(address))))/10**18
    return f'{val:f} {sym} (RPC-reported; native asset only)'


def prepare_evm(code: str, url: str, key_path: str, source_kind: str, source_password: str,
                dest: str, amount_str: str, cap_str: str, token_addr: str = '', source_asset: str = 'Auto') -> SendPlan:
    from web3 import Web3
    w3=evm_w3(code,url)
    name, chainid, native_symbol=tx.COIN_NETWORKS[code]
    source=evm_source(code,key_path,source_kind,source_password,source_asset)
    if not Web3.is_address(dest): raise tx.TransferError('Invalid recipient EVM 0x address')
    dest=Web3.to_checksum_address(dest)
    if dest.lower()==source.lower(): raise tx.TransferError('Sender equals recipient')
    token_mode=bool(token_addr.strip()); contract_addr=None; symbol=native_symbol; decimals=18
    balance_wei=int(w3.eth.get_balance(source))
    nonce=int(w3.eth.get_transaction_count(source,'pending'))
    if token_mode:
        if not Web3.is_address(token_addr): raise tx.TransferError('Invalid token contract')
        contract_addr=Web3.to_checksum_address(token_addr)
        if not w3.eth.get_code(contract_addr): raise tx.TransferError('No deployed token contract')
        contract=w3.eth.contract(address=contract_addr,abi=tx.ERC20_ABI)
        decimals=int(contract.functions.decimals().call())
        if not 0<=decimals<=36: raise tx.TransferError('Unexpected token decimals')
        symbol=str(contract.functions.symbol().call())
        if not re.fullmatch('[A-Za-z0-9_.+-]{1,24}', symbol): raise tx.TransferError('Unsafe token symbol')
        amount=tx.amount_decimal(amount_str,decimals); total_units=tx.units(amount,decimals)
        if total_units>int(contract.functions.balanceOf(source).call()): raise tx.TransferError('Insufficient token balance')
        data=contract.encode_abi('transfer',args=[dest,total_units])
        transaction={'from':source,'to':contract_addr,'value':0,'nonce':nonce,'chainId':chainid,'data':data}
        gas_est=int(w3.eth.estimate_gas({'from':source,'to':contract_addr,'value':0,'data':data}))
    else:
        if w3.eth.get_code(dest): raise tx.TransferError('Native transfer to a contract is blocked')
        amount=tx.amount_decimal(amount_str,18); total_units=tx.units(amount,18)
        transaction={'from':source,'to':dest,'value':total_units,'nonce':nonce,'chainId':chainid}
        gas_est=int(w3.eth.estimate_gas({'from':source,'to':dest,'value':total_units}))
    if not 21000<=gas_est<=500_000: raise tx.TransferError('Gas estimate is outside transfer safety limits')
    gas=min(500_000,(gas_est*12+9)//10)
    fee_fields,max_wei=tx.evm_fee_params(w3,gas); transaction.update(fee_fields); transaction['gas']=gas
    max_fee=Decimal(max_wei)/10**18; cap=tx.amount_decimal(cap_str,18,'fee cap')
    if max_fee>cap: raise tx.TransferError(f'Max fee {max_fee:f} {native_symbol} exceeds cap {cap:f}')
    if balance_wei<max_wei+(0 if token_mode else total_units):
        raise tx.TransferError('Insufficient native balance for max fee plus native amount')
    details=f'Chain ID: {chainid}\nAccount nonce: {nonce}\nGas estimate: {gas_est}; limit: {gas}'
    if token_mode:
        details+=f'\nTOKEN CONTRACT (independently verify): {contract_addr}\nToken decimals: {decimals}\nContract-reported symbol NOT an identity check.'
    return SendPlan('evm',symbol,name,source,dest,amount,max_fee,native_symbol,details,
                    {'code':code,'url':url,'transaction':transaction,'keystore':key_path,
                     'source_kind':source_kind,'token_addr':contract_addr,'source_asset':source_asset})


def commit_evm(plan: SendPlan, password: str) -> str:
    from eth_account import Account
    c=plan.context
    w3=evm_w3(c['code'],c['url'])
    if c['source_kind']=='vault':
        acct=evm_address_from_vault(c['code'], c['keystore'], password, c.get('source_asset','Auto'))
    else:
        data, addr=tx.load_keystore_header(Path(c['keystore']))
        try: key=Account.decrypt(data,password)
        except (ValueError,KeyError,TypeError) as exc:
            raise tx.TransferError('Keystore password failed') from exc
        acct=Account.from_key(key)
    if acct.address.lower()!=plan.source.lower():
        raise tx.TransferError('Signing wallet address changed; refusing')
    transaction=c['transaction']
    if int(transaction.get('chainId',-1))!=tx.COIN_NETWORKS[c['code']][1]:
        raise tx.TransferError('Transaction chain ID changed')
    signed=acct.sign_transaction({k:v for k,v in transaction.items() if k!='from'})
    recovered=Account.recover_transaction(signed.raw_transaction)
    if recovered.lower()!=plan.source.lower(): raise tx.TransferError('Signed sender mismatch')
    return w3.eth.send_raw_transaction(signed.raw_transaction).hex()


def execute_plan(plan: SendPlan, password: str = '') -> str:
    """One use only; mark before network call to prevent duplicate if RPC times out."""
    if plan.used: raise tx.TransferError('Plan already attempted. Check chain before retrying')
    plan.used=True
    if plan.kind=='btc': return commit_btc(plan,password)
    if plan.kind=='xmr': return commit_xmr(plan)
    if plan.kind=='evm': return commit_evm(plan,password)
    raise tx.TransferError('Unrecognized transaction type')
