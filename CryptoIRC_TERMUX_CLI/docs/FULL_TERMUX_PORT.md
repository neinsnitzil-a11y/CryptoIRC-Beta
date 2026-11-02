# Android full CLI parity and installation guide

## Application scope

`Termux/app/` is an Android deployment of `CLI/Linux/` **with the complete original application source**. The 21-menu UI and all wallet transfer, encryption, mesh and diagnostics modules remain. Termux package installation and node-manager autostart are Android-adapted; feature execution depends on native crypto dependencies and external nodes. The old relay-only Termux build has been replaced.

| Full Linux CLI feature | Included on Android | Requirements / limitation |
|---|---|---|
| 30 wallet address formats | Yes, same source | `bip-utils` native dependencies must install; no live-money certification |
| Encrypted `.vault` create/restore/unlock/backup/password rotation | Yes, same source | `argon2-cffi` + native cryptography; protect device/backups |
| Native EVM balances & transfers, ERC-20, receipts | Yes, same source | Web3 dependency tree and RPC provider; live chain tests not run |
| BTC vault receive and send | Same source | Full synced Bitcoin Core loopback RPC, not included by installer |
| Monero send | Same source | `monero-wallet-rpc` on loopback, not included by installer |
| Tor privacy center | Same source | Separate `pkg install tor`; configure SOCKS 9050 and test fail-closed policies |
| Peer discovery, public node scan, online roster | Same source | Live peer and signed identity required |
| Channel creation, encrypted DM, encrypted file/folder offer | Same source | Two live peers / recipient acceptance; max 4 MiB attachment |
| WAN/LAN phone node hosting | Same source | Android network / CGNAT / battery dependent |
| Node autostart | Android-specific implementation | Termux:Boot script; no systemd |
| CLI help/tests/diagnostics | Yes | Native import checks, Linux tests running offline |

## Native Python dependencies

Use `Termux/INSTALL_TERMUX.sh`: Termux's `pkg` supplies native cryptography/PyNaCl rather than incompatible desktop glibc wheels. A venv with system packages installs the remaining Web3/bip-utils dependencies from source or compatible wheels; compilation is **not guaranteed**. The installer halts if `termux_preflight.py --full` does not pass. In particular, `coincurve`, `ckzg`, `py-sr25519-bindings`, and `ed25519-blake2b` may need architecture-specific build fixes. Never bypass preflight. To inspect import status: `Termux/.venv/bin/python -I Termux/termux_preflight.py --full`.

If native compilation fails use `Termux/INSTALL_PROOT_UBUNTU.sh` for Ubuntu userspace; this retains the full Linux program and Python 3.12 installer, but performance and service hosting differ. PRoot is not a VM and has no systemd.

## Example private-phone storage

```text
/data/data/com.termux/files/home/VaultForge/
    wallets/             # encrypted vault files
    mesh_chat/           # distinct phone chat accounts, peer pins, node identity
        downloads/
```

Always keep the source in Termux private HOME and do not use `sudo`/root. Never publish `$HOME/VaultForge`, `.venv`, node secret files, wallets, recovery phrases or SQLite databases to GitHub.

## External services and operations

Stock trading GUI is in the separate CRYPTO NOCTURNE EXE builder repository, not the CLI. Wallet sending must not start when dependencies are missing. BTC and Monero functions are retained but are **not self-hosted blockchain nodes on Android**. On-device Tor is optional and changes transport routing, not wallet anonymization. Tested local unit suites are not a substitute for actual device testing and real-node signet/testnet tests.
