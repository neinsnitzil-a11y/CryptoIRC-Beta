"""NOCTURNE Phase 15: public-account-first financial workflow policy.

No signing, broadcasting, custody, fiat settlement or credentials in this module.
No account is considered independently recovery-tested by software assertions.
"""
from __future__ import annotations
from dataclasses import dataclass

SUPPORTED_SEND = {"btc_core": "BTC Phase 1", "evm_keystore": "EVM Phase 2", "xmr_rpc": "Monero Phase 3"}
LIVE_KINDS = frozenset(("btc_core", "evm_keystore", "xmr_rpc", "vault", "watch_only"))
TEST_NETWORKS = frozenset(("regtest", "test", "testnet", "signet", "stagenet", "SEPOLIA"))

@dataclass(frozen=True)
class FinancialActions:
    receive: bool
    copy_address: bool
    balance_query: bool
    send_page: str | None
    buy_route: bool
    cashout_route: bool
    warning: str


def capabilities(account, *, fresh=False, observed=False) -> FinancialActions:
    """Show actions only when their explicit preconditions hold.

    A live RPC balance does NOT prove possession of signing credentials; an
    address can receive without the user being able to spend. A local account
    registry entry alone is never a confirmation or recovery guarantee.
    """
    if not getattr(account, 'address', '') or not getattr(account, 'asset', '') or not getattr(account, 'network', ''):
        return FinancialActions(False, False, False, None, False, False, 'Invalid public account reference.')
    kind=account.kind
    send=SUPPORTED_SEND.get(kind)
    is_test=account.network in TEST_NETWORKS
    # Provider eligibility must be verified separately. Only a compatible
    # mainnet signer account with a freshly checked wallet-bound RPC identity
    # may be routed to the provider review screen; still no claim of recovery.
    route=(fresh and observed and not is_test and
           ((kind=='btc_core' and account.asset=='BTC' and account.network=='main') or
            (kind=='xmr_rpc' and account.asset=='XMR' and account.network=='mainnet')))
    if kind in ('vault','watch_only'):
        warning='ADDRESS ONLY — independent ownership, recovery and spending are NOT verified.'
    elif kind=='evm_keystore':
        warning='Encrypted keystore reference; password, recovery and ability to sign have NOT been verified.'
    else:
        warning='Connected wallet required. An RPC balance does not independently prove recoverability.'
    if is_test: warning+=' TEST NETWORK — fiat purchase is unavailable.'
    return FinancialActions(True, True, kind in LIVE_KINDS, send, bool(route),
                            False, warning)


def observation_display(account, observation, *, now=None):
    """Only exact, fresh, account-bound network observations may be displayed."""
    from portfolio_engine import wallet_identity, amount
    if observation is None:
        return {'status':'UNAVAILABLE','total':'—','available':'—','pending':'—',
                'height':'—','provider':'No trusted RPC result'}
    if observation.identity != wallet_identity(account):
        raise ValueError('Balance belongs to a different wallet')
    if observation.network != account.network:
        raise ValueError('Balance belongs to another blockchain network')
    if not observation.fresh(now):
        return {'status':'STALE','total':'—','available':'—','pending':'—',
                'height':'—','provider':'Old observation discarded'}
    total=amount(observation.total)
    available=amount(observation.reported_available)
    if available>total:raise ValueError('Invalid balance from RPC')
    return {'status':'LIVE / RPC-REPORTED','total':format(total,'f'),
            'available':format(available,'f'),'pending':format(total-available,'f'),
            'height':observation.block_height,'provider':observation.provider}


def matching_history(entries, account, *, limit=12):
    """Match only the selected wallet's public transaction records.

    Local outgoing projections are not a complete on-chain activity scanner.
    """
    from portfolio_engine import public_activity
    if not 1<=limit<=50:raise ValueError('Invalid history limit')
    if account.kind not in SUPPORTED_SEND:
        return []
    return public_activity(entries, account, limit=limit)


def selected_funding_target(account):
    """Public checkout destination, no private key; eligibility checked by caller."""
    from wallet_funding import FundingTarget
    network={'BTC':'Bitcoin mainnet','XMR':'Monero mainnet'}.get(account.asset)
    if account.kind not in ('btc_core','xmr_rpc') or not network:
        raise ValueError('Only node-verified native BTC or XMR destinations can be routed')
    return FundingTarget(account.asset,account.address,network,
                         'Bitcoin Core verified' if account.kind=='btc_core' else 'Monero RPC',
                         account.label,True)
