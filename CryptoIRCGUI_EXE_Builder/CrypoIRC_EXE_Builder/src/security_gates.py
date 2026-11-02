"""Conservative, read-only release gate reporting for the desktop client.
Never infer success from the presence of code, an environment variable, or a GUI.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,json

GATES=[
 ('Private-key generation & recovery','BLOCKED','Independent audit plus cross-wallet recovery vectors required'),
 ('Real blockchain deposits and withdrawals','BLOCKED','Testnet end-to-end and live risk-reviewed trials required'),
 ('Payment secrets on isolated server','BLOCKED','Backend separation designed; real deployment, KMS and access review required'),
 ('Provider settlement and reconciliation','SANDBOX','Durable outbox, test Stripe event parser and dual review; no live provider settlement'),
 ('Resilience, monitoring and backups','SANDBOX','Synthetic-data queue, health checks and restore-to-new-db; no production SLO verification'),
 ('MFA and session security','SANDBOX','Auth reference prototype, not integrated user identity system'),
 ('WAN chat security review','BLOCKED','Unaudited custom transport; no production assurance'),
 ('Signed installer, updates and SBOM','PARTIAL','Build hooks are present; actual signing certificate and external scans required'),
 ('Regulatory, legal and partner approvals','BLOCKED','Local notice journal and signed-policy assessment exist; actual licenses, KYC/AML and provider authorization remain unverified'),
]

def release_status():return {'release':'BLOCKED','production_payments_enabled':False,'financial_balances_authoritative':False,'gates':GATES}

def check_manifest(root):
    root=Path(root)
    manifest=root/'MANIFEST_SHA256.txt'
    if not manifest.is_file():return False,'No release manifest available'
    # Legacy manifest format might differ; don't claim authenticity without a signature.
    return False,'Hash manifest is not a digital release signature; verify vendor signature externally'
