# CryptoIRC on Android — FULL Linux CLI port

`Termux/app/` contains **all** CLI Linux application source modules (not just chat): encrypted 30-address wallet generation, vault operations, Bitcoin via Bitcoin Core, EVM transactions, Monero wallet RPC orchestration, diagnostics, security center, full mesh chat, local account creation, room/DM/file sharing, and node manager. It uses the same menu as `CLI/Linux/vaultforge.py`.

**Install options:** native Termux installer tries the full Python/crypto dependency set and **fails closed** if required modules cannot be built for Android; alternatively `INSTALL_PROOT_UBUNTU.sh` installs a Linux userspace (the same full CLI) under Termux. Both are source-level ports. Neither has been validated on a physical Android phone here.

## Native full CLI (recommended first)

Install Termux from official F-Droid or GitHub and move the repository into Termux private `$HOME` (not `/sdcard`). Open Termux:

```sh
pkg update && pkg install -y git unzip
cd ~/CryptoIRC_TERMUX_CLI
bash Termux/INSTALL_TERMUX.sh
bash Termux/START_TERMUX.sh
```

The native installer handles Android Termux packages, creates `~/VaultForge/wallets` and `~/VaultForge/mesh_chat`, installs the full-wallet Python dependencies into a private venv, and **requires an import/preflight pass**. Compiled packages such as `coincurve`, `bip-utils` and Web3 transitive dependencies can fail to build on some ARM/Python versions; success is not asserted until the checks pass. Do not use significant funds even if they pass.

Useful commands:

```sh
bash Termux/START_TERMUX.sh --diagnostics
bash Termux/START_TERMUX.sh --list-networks
bash Termux/START_TERMUX.sh --self-test
bash Termux/CONNECT_TERMUX.sh 18.188.145.207:6667
bash Termux/SETUP_PHONE_RELAY.sh PhoneRelay lan
bash Termux/RUN_PHONE_RELAY.sh
bash Termux/STATUS_PHONE_RELAY.sh
bash Termux/STOP_PHONE_RELAY.sh
bash Termux/START_TERMUX.sh node-status
```

**Chat account setup:** Launch the full menu → `21` Mesh Communications → `1` Connect to existing peer; create a local account or log in, confirm independently verified relay fingerprint, `/refresh`, `/online`. Phone local chat accounts are separate from the AWS server's chat identity. If relay fingerprint rotates, verify new key out-of-band and update trusted pins consciously.

**Host your own phone node:** `SETUP_PHONE_RELAY` creates a distinct node account only once (refuses to overwrite existing identity). Choose `lan` on Wi-Fi; then `RUN_PHONE_RELAY`. Other devices use `PHONE_LAN_IP:7777`. Router client isolation, Android network rules, CGNAT and battery restrictions can stop connectivity/uptime. For optional boot scripts use full mesh menu → 14, plus the separately installed Termux:Boot app. It does not make hosting continuous or secure against Android kills.

**Wallet limits:** Menu is preserved, but not every coin supports spending. BTC vault spending and confirmed balances require a **separately managed, fully synced Bitcoin Core RPC on loopback**; that service is not supplied by this Termux installer. Monero sends require separately managed `monero-wallet-rpc` on loopback. Mobile cannot transparently replace these with a remote public node. EVM native/ERC-20 signing needs operational RPC networks and independent verification. All 30 wallet formats derive addresses only when `bip_utils` and its native dependencies work. The custom crypto/network code is experimental and unaudited.

## Full Linux userspace fallback (Ubuntu PRoot on Android)

If native dependencies fail, use:

```sh
bash Termux/INSTALL_PROOT_UBUNTU.sh
bash Termux/START_PROOT_UBUNTU.sh
```

This requires more storage. It creates a **separate, unprivileged Linux user** for the full CLI, installed via the original Linux CPython 3.12 installer; its wallet files and mesh identities stay inside the Ubuntu guest and **are not shared with native Termux**. PRoot has no init/systemd; use foreground node options or a user-started node manager. Android background restrictions still apply. This path also needs real-device verification.

## Security

No Android root, no wallet secrets in the GitHub source, no silent account reset, no automatic trust pin deletion, no global pip upgrade, and no code execution from `/sdcard`. Keep backups of offline recovery phrases separate from the phone. Software wallets on compromised Android devices are unsafe. Read `docs/FULL_TERMUX_PORT.md`.
