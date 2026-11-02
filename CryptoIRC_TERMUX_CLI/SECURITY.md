# Security policy for CryptoIRC_TERMUX_CLI

Development / experimental source only. This custom encrypted mesh chat, cryptocurrency wallet and any trading-related module are not independently security audited or production certified. Do not rely on it for significant funds, custody or sensitive communications.

## Never commit private data

Keep chat identities (`node.json`, `node.secret`, `accounts.json`, `known_peers.json`), wallet vaults, mnemonic/seed phrases, private keys, API keys, databases, histories, tokens, `.env` files and passwords OUTSIDE the repository.

## Remote peer trust

Verify the server fingerprint using an independent channel before pinning. If a server is reinitialized, fingerprints change; clients reject this until the change is independently verified. Never bypass identity verification globally. Never use a relay's public IP as its own upstream peer.

## Server exposure

Do not expose wallet directories or management endpoints. Use dedicated low-privilege users and restrictive `0700` directories. Back up your server identity files privately and as a matched set. For a public relay apply firewall rules, rate limits and host monitoring.

## Disclosing vulnerabilities

Do not publish working exploits or sensitive dumps; contact the repository owner privately. This source bundle includes no warranty, external certification, or a claim of live trading readiness.
