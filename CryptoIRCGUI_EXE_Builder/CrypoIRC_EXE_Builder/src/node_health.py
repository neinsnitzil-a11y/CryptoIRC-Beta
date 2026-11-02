"""Phase 9: fail-closed, read-only blockchain node health and synchronization.

No private keys or transaction payloads pass through this module. Endpoint
failover is ONLY for read-only observations. Sign/broadcast operations must
continue using their existing pinned chain-specific signing RPC and journals.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable

from chain_expansion import post_json, rpc_json, safe_rpc_endpoint
from core.transfer import BitcoinRPC, TransferError
from pathlib import Path

MAX_HEAD_AGE_SEC = 15 * 60


@dataclass(frozen=True)
class NodeHealth:
    family: str
    identity: str
    endpoint: str
    height: int
    observed_utc: int
    state: str  # READY / SYNCING / STALE / UNVERIFIED / ERROR
    detail: str

    @property
    def ready(self) -> bool:
        return self.state == 'READY'


def _height(value, label='height') -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**64:
        raise TransferError('Node returned invalid ' + label)
    return value


def _timestamp(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TransferError('Node returned invalid block timestamp')
    return value


def _freshness(block_time: int, now: int) -> bool:
    return -120 <= now - block_time <= MAX_HEAD_AGE_SEC


def probe_bitcoin(url: str, cookie_path: str, expected_chain='regtest', *, rpc_factory=BitcoinRPC, clock=time.time) -> NodeHealth:
    """Read-only Bitcoin Core chain status; regtest may have an old chain tip."""
    if expected_chain not in ('main', 'test', 'testnet4', 'signet', 'regtest'):
        raise TransferError('Unknown Bitcoin network')
    rpc = rpc_factory(url, Path(cookie_path))
    info = rpc.call('getblockchaininfo')
    if not isinstance(info, dict) or info.get('chain') != expected_chain:
        raise TransferError('Bitcoin network mismatch; node status refused')
    blocks = _height(info.get('blocks'))
    headers = _height(info.get('headers'))
    if headers < blocks:raise TransferError('Bitcoin node returned inconsistent heights')
    progress = info.get('verificationprogress', 0)
    if isinstance(progress, bool) or not isinstance(progress, (float, int)) or not math.isfinite(progress) or not 0 <= progress <= 1:
        raise TransferError('Invalid Bitcoin verification progress')
    now = int(clock())
    if info.get('initialblockdownload') is not False or headers > blocks:
        state = 'SYNCING'
    elif expected_chain == 'main':
        # A caught-up-but-stalled node cannot authoritatively report current funds.
        timestamp = _timestamp(info.get('time'))
        state = 'READY' if _freshness(timestamp, now) else 'STALE'
    else:
        state = 'READY'  # regtest/signet blocks can legitimately be old
    return NodeHealth('BTC', expected_chain, url, blocks, now, state,
        f'{blocks}/{headers} blocks/headers; verification {progress:.2%}; Core initial-download={info.get("initialblockdownload")}')


def probe_evm(url: str, expected_chain_id: int, *, transport=post_json, clock=time.time) -> NodeHealth:
    if isinstance(expected_chain_id, bool) or not isinstance(expected_chain_id, int) or expected_chain_id <= 0:
        raise TransferError('Invalid EVM chain identity')
    endpoint = safe_rpc_endpoint(url)
    raw_id = rpc_json(endpoint, 'eth_chainId', [], transport=transport).get('result')
    try: chain_id = int(raw_id, 16) if isinstance(raw_id, str) and raw_id.startswith('0x') else -1
    except ValueError: chain_id = -1
    if chain_id != expected_chain_id:
        raise TransferError('EVM node chain ID mismatch')
    syncing = rpc_json(endpoint, 'eth_syncing', [], transport=transport).get('result')
    if syncing is not False and not isinstance(syncing, dict):
        raise TransferError('Malformed EVM sync status')
    raw_height = rpc_json(endpoint, 'eth_blockNumber', [], transport=transport).get('result')
    try: height = int(raw_height, 16) if isinstance(raw_height, str) and raw_height.startswith('0x') else -1
    except ValueError: height = -1
    height = _height(height)
    head = rpc_json(endpoint, 'eth_getBlockByNumber', ['latest', False], transport=transport).get('result')
    if not isinstance(head, dict) or not isinstance(head.get('number'), str):
        raise TransferError('Missing EVM canonical head')
    try:
        head_height = int(head['number'], 16)
        timestamp = int(head['timestamp'], 16)
    except (KeyError, TypeError, ValueError):raise TransferError('Malformed EVM block timestamp')
    if _height(head_height) != height:
        raise TransferError('Inconsistent EVM node head height')
    state = 'SYNCING' if syncing is not False else ('READY' if _freshness(_timestamp(timestamp), int(clock())) else 'STALE')
    return NodeHealth('EVM', str(expected_chain_id), endpoint, height, int(clock()), state,
        'eth_syncing=' + ('false' if syncing is False else 'in progress') + '; latest block checked')


def probe_solana(url: str, expected_genesis: str, *, transport=post_json, clock=time.time) -> NodeHealth:
    from chain_expansion import b58decode
    endpoint = safe_rpc_endpoint(url)
    if not expected_genesis or len(b58decode(expected_genesis)) != 32:
        raise TransferError('Pin the independently verified Solana cluster genesis hash')
    genesis = rpc_json(endpoint, 'getGenesisHash', [], transport=transport).get('result')
    if genesis != expected_genesis:
        raise TransferError('Solana genesis mismatch')
    health = rpc_json(endpoint, 'getHealth', [], transport=transport)
    slot = rpc_json(endpoint, 'getSlot', [{'commitment': 'finalized'}], transport=transport).get('result')
    height = _height(slot, 'finalized slot')
    ready = health.get('result') == 'ok' and health.get('error') is None
    return NodeHealth('SOL', expected_genesis, endpoint, height, int(clock()),
        'READY' if ready else 'SYNCING', 'Solana getHealth and finalized-slot; pinned genesis match')


def probe_xrp(url: str, expected_network_id: int, *, transport=post_json, clock=time.time) -> NodeHealth:
    """Require server-reported network ID; otherwise NEVER advertise readiness."""
    if isinstance(expected_network_id, bool) or not isinstance(expected_network_id, int) or expected_network_id < 0:
        raise TransferError('Pin the expected XRPL network ID')
    endpoint = safe_rpc_endpoint(url)
    result = rpc_json(endpoint, 'server_info', [{}], transport=transport).get('result')
    info = result.get('info') if isinstance(result, dict) else None
    if not isinstance(info, dict):raise TransferError('Invalid XRP server_info response')
    actual = info.get('network_id')
    if actual is not None and (type(actual) is not int or actual != expected_network_id):
        raise TransferError('XRP Ledger network mismatch')
    ledger = info.get('validated_ledger')
    now = int(clock())
    if not isinstance(ledger, dict):
        return NodeHealth('XRP', str(expected_network_id), endpoint, 0, now, 'SYNCING', 'No validated XRP ledger')
    height = _height(ledger.get('seq'), 'validated ledger')
    age = ledger.get('age')
    if isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(age) or age < 0:
        raise TransferError('Invalid validated XRP ledger age')
    state = 'UNVERIFIED' if actual is None else ('READY' if age <= 120 else 'STALE')
    return NodeHealth('XRP', str(expected_network_id), endpoint, height, now, state,
        ('Network ID not reported by this server; cannot verify network. ' if actual is None else '') +
        f'Validated ledger age {age:g}s')


def select_read_endpoint(endpoints: tuple[str, ...], probe: Callable[[str], NodeHealth], *,
                         expected_identity: str, maximum_height_gap: int = 12) -> NodeHealth:
    """Only read-only failover. This function MUST NOT be used to send/sign/broadcast.

    All endpoints are explicitly configured by user; never take URLs from an
    untrusted node response. A backup is accepted only after independent
    same-network attestation and health checks. Block-height differences are
    bounded to prevent failover to an obviously stale fork.
    """
    if not endpoints or len(endpoints) > 4 or len(set(endpoints)) != len(endpoints):
        raise TransferError('Configure 1-4 distinct trusted read-only endpoints')
    if maximum_height_gap < 0 or maximum_height_gap > 1000:
        raise TransferError('Invalid failover height tolerance')
    snapshots: list[NodeHealth] = []
    for endpoint in endpoints:
        safe_rpc_endpoint(endpoint)
        try:
            s = probe(endpoint)
            if s.endpoint != endpoint or s.identity != expected_identity or not s.ready:
                continue
            snapshots.append(s)
        except (TransferError, OSError, ValueError):
            continue
    if not snapshots: raise TransferError('No healthy, correct-network read-only endpoint; balance unavailable')
    highest = max(s.height for s in snapshots)
    for endpoint in endpoints:
        for s in snapshots:
            if s.endpoint == endpoint and highest - s.height <= maximum_height_gap:
                return s
    raise TransferError('Healthy endpoint observations diverge; do not display a trusted live balance')


@dataclass(frozen=True)
class BalanceFreshness:
    received_at_monotonic: float
    network_identity: str
    endpoint: str
    ttl_seconds: int = 90

    def usable(self, *, now: float | None = None, identity: str, endpoint: str) -> bool:
        at = time.monotonic() if now is None else now
        return (identity == self.network_identity and endpoint == self.endpoint and
                0 <= at - self.received_at_monotonic <= self.ttl_seconds)
