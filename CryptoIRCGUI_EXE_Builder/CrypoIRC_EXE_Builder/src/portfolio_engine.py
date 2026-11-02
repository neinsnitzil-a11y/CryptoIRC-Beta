"""NOCTURNE Phase 10: read-only multi-account portfolio projection.

No pricing guesses, private keys, writes to signing journals or balance persistence.
A node-reported balance is not proof of ownership, available cash, or recovery.
Balances for different networks and assets must never be mixed. Account aliases
are de-duplicated before read-only aggregation.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Iterable
import time

MAX_AGE = 90

class PortfolioError(ValueError):
    pass


def amount(value) -> Decimal:
    if isinstance(value, (float, bool)):
        raise PortfolioError('Floating-point or boolean balance cannot be trusted')
    try:
        dec = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise PortfolioError('Invalid wallet balance') from None
    if not dec.is_finite() or dec < 0 or dec.adjusted() > 80:
        raise PortfolioError('Invalid wallet balance')
    return dec


def wallet_identity(account) -> tuple:
    """Core and XMR wallet balances are wallet-wide, not per receive address."""
    if account.kind == 'btc_core':
        return ('btc_core', account.network, account.source)
    if account.kind == 'xmr_rpc':
        return ('xmr_rpc', account.network, account.source)
    # Same EVM address in a vault, keystore, watch-only: one owned public account.
    return ('public_address', account.asset, account.network, account.address.lower())


def distinct_accounts(accounts: Iterable) -> list:
    preference = {'btc_core': 0, 'xmr_rpc': 0, 'evm_keystore': 1,
                  'vault': 2, 'watch_only': 3}
    result = {}
    for a in accounts:
        key = wallet_identity(a)
        if key not in result or preference.get(a.kind, 10) < preference.get(result[key].kind, 10):
            result[key] = a
    return list(result.values())


@dataclass(frozen=True)
class Observation:
    identity: tuple
    asset: str
    network: str
    total: Decimal
    reported_available: Decimal
    observed_monotonic: float
    block_height: str
    provider: str
    caveat: str

    @classmethod
    def from_snapshot(cls, account, snap, *, observed=None):
        total = amount(snap.total)
        available = amount(snap.available)
        if available > total:
            raise PortfolioError('Available balance exceeds reported total')
        if account.kind == 'btc_core' and snap.currency != 'BTC':
            raise PortfolioError('Bitcoin RPC currency mismatch')
        if account.kind == 'xmr_rpc' and snap.currency != 'XMR':
            raise PortfolioError('Monero RPC currency mismatch')
        if account.kind not in ('btc_core', 'xmr_rpc') and snap.currency != account.asset:
            # EVM chain identifiers may be ARB / OP while the actual gas currency
            # is ETH. Explicitly keep network and currency separate.
            from core.transfer import COIN_NETWORKS
            if COIN_NETWORKS.get(account.network, ('', 0, ''))[2] != snap.currency:
                raise PortfolioError('RPC balance currency does not match the selected chain')
        return cls(wallet_identity(account), snap.currency, account.network, total,
                   available, time.monotonic() if observed is None else observed,
                   str(snap.height), str(snap.source), str(snap.pending_note))

    def fresh(self, now=None):
        delta = (time.monotonic() if now is None else now) - self.observed_monotonic
        return 0 <= delta <= MAX_AGE


def summarize(accounts, observations: dict, *, now=None):
    """Only fresh authoritative observations contribute; missing rows are UNKNOWN.

    Never mix BTC regtest/mainnet or ETH on distinct networks. Never claim a
    portfolio-wide USD total. No spendability inference from watch-only balances.
    """
    unique = distinct_accounts(accounts)
    rows = []
    groups = {}
    for acc in unique:
        key = wallet_identity(acc)
        obs = observations.get(key)
        state = 'UNAVAILABLE' if obs is None else ('LIVE' if obs.fresh(now) else 'STALE')
        if obs is not None and obs.identity != key:
            raise PortfolioError('Account observation changed identities')
        displayed_total = obs.total if state == 'LIVE' else None
        displayed_available = obs.reported_available if state == 'LIVE' else None
        asset = obs.asset if state == 'LIVE' else acc.asset
        row = {'account': acc, 'identity': key, 'asset': asset,
               'network': acc.network, 'state': state, 'total': displayed_total,
               'reported_available': displayed_available,
               'height': obs.block_height if state == 'LIVE' else '—',
               'age': max(0, (time.monotonic() if now is None else now)-obs.observed_monotonic) if obs else None,
               'note': obs.caveat if state == 'LIVE' else 'Live network observation unavailable or expired'}
        rows.append(row)
        group = groups.setdefault((asset, acc.network), {'asset': asset, 'network': acc.network,
                        'reported_total': Decimal(0), 'reported_available': Decimal(0),
                        'live': 0, 'incomplete': 0})
        if state == 'LIVE':
            group['reported_total'] += displayed_total
            group['reported_available'] += displayed_available
            group['live'] += 1
        else:
            group['incomplete'] += 1
    # Only account groups where every account was queried can display an aggregate.
    for g in groups.values():
        if g['incomplete']:
            g['reported_total'] = None
            g['reported_available'] = None
    return {'rows': rows, 'groups': sorted(groups.values(), key=lambda g:(g['asset'],g['network'])),
            'live': sum(r['state']=='LIVE' for r in rows),
            'stale': sum(r['state']=='STALE' for r in rows),
            'unavailable': sum(r['state']=='UNAVAILABLE' for r in rows)}


def public_activity(transactions, account, limit=20):
    """Local projection only, not an independent live-chain transaction scan."""
    if not 1 <= limit <= 100: raise PortfolioError('Invalid activity limit')
    chain = 'BTC' if account.kind=='btc_core' else 'XMR' if account.kind=='xmr_rpc' else 'EVM'
    output=[]
    for tx in transactions:
        if tx.get('chain') != chain:continue
        if chain == 'BTC':
            if tx.get('network') != account.network or tx.get('source') != account.source:continue
        elif chain == 'XMR':
            if tx.get('network')!=account.network or tx.get('source')!=account.address:continue
        else:
            from core.transfer import COIN_NETWORKS
            if str(tx.get('network')) != str(COIN_NETWORKS.get(account.network,('',-1,''))[1]):continue
            if str(tx.get('source','')).lower()!=account.address.lower():continue
        output.append(tx)
        if len(output)>=limit:break
    return output


def query_account(account, config: dict, *, btc_factory=None, xmr_factory=None, evm_reader=None):
    """Strict single-account read-only RPC dispatch; never send, sign or unlock."""
    from live_balances import BalanceSnapshot
    if account.kind=='btc_core':
        from core.transfer import BitcoinRPC, TransferError
        from pathlib import Path
        from node_health import probe_bitcoin
        factory = btc_factory or (lambda url,cookie,wallet=None:BitcoinRPC(url,Path(cookie),wallet))
        url,cookie=config.get('btc_url',''),config.get('btc_cookie','')
        core=factory(url,cookie)
        status=probe_bitcoin(url,cookie,account.network,rpc_factory=lambda *args:core)
        if not status.ready:raise PortfolioError('Bitcoin Core node is not synchronized')
        if account.source not in core.call('listwallets'):
            raise PortfolioError('Bitcoin Core wallet is not loaded')
        rpc=factory(url,cookie,account.source)
        owned=rpc.call('getaddressinfo',account.address)
        if not isinstance(owned,dict) or not owned.get('ismine'):
            raise PortfolioError('Registered Bitcoin address is not owned by the selected Core wallet')
        mine=(rpc.call('getbalances') or {}).get('mine',{})
        trusted=amount(mine['trusted']);pending=amount(mine.get('untrusted_pending','0'))
        immature=amount(mine.get('immature','0'))
        return BalanceSnapshot('Bitcoin Core','BTC',str(trusted),str(trusted+pending+immature),
            str(pending),'Untrusted pending',str(status.height),datetime.now(timezone.utc).isoformat(),
            'Core trusted includes some unconfirmed change; not independently proven spendable.')
    if account.kind=='xmr_rpc':
        from core.transfer import MoneroRPC
                # Explicitly avoid instantiating a signing engine or opening a send journal.
        factory=xmr_factory or (lambda url,user,pw:MoneroRPC(url,user,pw))
        rpc=factory(config.get('xmr_url',''),config.get('xmr_user',''),config.get('xmr_password',''))
        info=rpc.call('get_wallet_info') or {}
        if info.get('network_type') != account.network:
            raise PortfolioError('Monero wallet RPC network mismatch')
        wallet_height=info.get('wallet_block_height')
        daemon_height=info.get('daemon_block_height')
        if (not isinstance(wallet_height,int) or not isinstance(daemon_height,int) or
                wallet_height < 1 or wallet_height+5 < daemon_height):
            raise PortfolioError('Monero wallet scan is not synchronized')
        height=(rpc.call('get_height') or {}).get('height')
        identity=(rpc.call('get_address',{'account_index':0}) or {}).get('address')
        valid=rpc.call('validate_address',{'address':identity,'any_net_type':False,'allow_openalias':False})
        if not isinstance(height,int) or height<1 or identity!=account.address or not valid.get('valid') or valid.get('nettype')!=account.network:
            raise PortfolioError('Monero wallet identity or network does not match')
        values=rpc.call('get_balance',{'account_index':0}) or {}
        total=amount(values['balance']);unlocked=amount(values['unlocked_balance'])
        if total!=total.to_integral_value() or unlocked!=unlocked.to_integral_value() or unlocked>total:
            raise PortfolioError('Invalid atomic Monero wallet balance')
        scale=Decimal(10)**12
        return BalanceSnapshot('Monero wallet RPC','XMR',str(unlocked/scale),str(total/scale),
            str((total-unlocked)/scale),'Locked',str(height),datetime.now(timezone.utc).isoformat(),
            'Wallet RPC unlocked amount; wallet scan completeness still requires independent verification.')
    if account.kind in ('evm_keystore','vault','watch_only'):
        from asset_capabilities import EVM_ALIASES
        from core.transfer import COIN_NETWORKS
        chain=account.network
        if chain not in COIN_NETWORKS or account.asset not in (chain, COIN_NETWORKS[chain][2]):
            # Token balances are handled in the separately pinned Token Center;
            # never incorrectly label a native gas balance as a stablecoin.
            raise PortfolioError('Use Token Center for token / unsupported asset balance')
        if config.get('evm_code')!=chain:
            raise PortfolioError('EVM endpoint must be configured for this exact chain')
        if not config.get('evm_url'):raise PortfolioError('Trusted EVM RPC endpoint required')
        from live_balances import snapshot_evm
        reader=evm_reader or snapshot_evm
        return reader(chain,config['evm_url'],account.address)
    raise PortfolioError('Read-only portfolio balance reader is not supported for this wallet type')
