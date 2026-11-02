# VaultForge Unified — Recovery and Security

**Recovery phrases control funds.** The password for a `.vault` file is *not* a replacement for a separate, offline recovery-phrase backup. Write down every word in its exact order, including any BIP39 extra passphrase. Do not screenshot, sync, email or message phrases. Do not keep your only backup on a USB drive.

## Recovering an original vault

Use menu `3` to select a legacy `.vault` by absolute path or directory, enter its original password, and display the same addresses and original derivation paths. Use menu `5` to compare sampled backup words. Use menu `4` to explicitly display the encrypted phrase for offline recovery if necessary. Use menu `6` to rotate the encryption password after copying your encrypted backup to a separate safe location.

To restore from paper instead, use menu `1`, choose the original coins, enter the original 12/24-word BIP39 or native 25-word XMR recovery phrase and any original extra BIP39 passphrase. **You must restore with compatible derivation settings and coin index to get the same addresses.** This workflow has not been independently verified across all 30 coin families.

## Transfer limitations

The native vault-backed EVM signer validates that (a) an account belongs to the selected vault, (b) its original BIP44 coin derivation path matches the current package configuration, and (c) the regenerated public address equals the stored address. It rejects mismatches rather than guessing. Only five source networks are enabled for this mode. Transfers require RPC access and an exact manually typed confirmation. Extra L1/data fee accounting for OP Stack and Arbitrum remains incomplete, so their EVM send paths are disabled.

Bitcoin **menu 13** now derives the BTC index-0 signing key from the same unlocked encrypted vault, verifies it matches the saved mainnet address, scans a separately running **local Bitcoin Core full node**, and builds, locally signs via Core RPC, verifies, and optionally broadcasts transactions. **Menu 18** remains the legacy *separate Core-wallet* signer; the two methods must not be confused. Bitcoin Core will receive a WIF private key transiently in memory over localhost RPC for the new method. Restrict RPC access to loopback, disable parameter logging, and use only your own trusted node. Unlike an offline hardware wallet, this design exposes the private key to the local node process. It does not scan BIP84 change/account indices beyond external `0/0`; change returns to the same original address. Live transactions, independent recovery and reorg/fee-bump handling remain unverified. Monero still uses a separately loaded wallet-RPC wallet. The 30-address catalog is not a 30-coin spend wallet.

## Operational rules

Use an offline, trusted device for initial creation and paper backups where possible. Verify your installation and dependencies before funding. Use a trusted HTTPS RPC endpoint or loopback. Recheck chain ID, recipient, contract, amount, fee and sending address. Do not broadcast with real funds until testnet trials and independent restoration are performed. A broadcast error may be ambiguous: inspect the displayed transaction hash *before* attempting to send again. For large balances, prefer audited, independently verified hardware-wallet solutions.

## Security Center v2.2.0

Use the unified CLI's option 20 for Tor-required EVM RPC routing, point-in-time Bitcoin Core onion configuration checks, encrypted-vault password changes and generation of an independent new wallet with freshly generated recovery seeds. The new wallet initially holds **zero** funds; original funds remain at their original addresses until you deliberately transfer them. Never delete the original vault merely because a new one was generated. Tor cannot hide on-chain transaction history, and no in-app Tor SOCKS probe can prove anonymity. See README.md for the limitations and Bitcoin Core `bitcoin.conf` example.

## Mesh chat v2.3.0

Chat identity keys are stored in `~/VaultForge/mesh_chat/accounts.json`, encrypted with a **separate local account password**; they never derive from, or replace, cryptocurrency wallet seeds, vault passwords or BIP39 passphrases. The peer pin/blocked lists are stored separately in the same directory. No wallet mnemonic is required for the chat. Do not post wallet seeds/private keys, wallet passwords, or bitcoin-core RPC cookies to any channel or private message. The locally designed authenticated transport has not undergone professional cryptographic auditing. Room traffic is encrypted per-peer link, NOT end-to-end across relay nodes. Direct messages are end-to-end encrypted to signed X25519 keys announced by participants, but recipient/sender metadata remains visible to relays. Direct P2P leaks your peer IP address. Tor hidden-service operation requires separately configured Tor service and peer fingerprint verification.
