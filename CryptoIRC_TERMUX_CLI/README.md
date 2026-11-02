> **NETWORK UPDATE 2.8.0 (November 2026):** The new default relay is `18.227.91.173:6667`. The previous `18.188.145.207:6667` and user-hosted relays remain selectable. See [MULTI_RELAY_UPGRADE_2_8_0.md](MULTI_RELAY_UPGRADE_2_8_0.md) for saved hosts, live peer indicators, new trust workflow, and limits. This package is updated source, not a verified deployment.

# CryptoIRC_TERMUX_CLI — Full VaultForge CLI for Android/Termux

This is an independent source package containing the complete VaultForge CLI for Windows, Linux, and **a full source-level Android Termux port**. The Termux app has the same 21-menu wallet + encrypted mesh CLI as Linux. It is not restricted to chat.

The Android native installer attempts the full wallet dependency tree and fails closed if native packages cannot be compiled/imported. An **Ubuntu PRoot compatibility installer** is included to run the same full Linux CLI when Android-native Python builds fail. Neither mode is claimed as live-tested on physical Android here; verify carefully, especially before funds are involved.

- `CLI/Windows`: original full Windows CLI.
- `CLI/Linux`: original full Linux CLI.
- `Termux/app`: entire Linux wallet + mesh Python source (Termux-specific node autostart).
- `Termux/INSTALL_TERMUX.sh`, `START_TERMUX.sh`, `CONNECT_TERMUX.sh`: native full-port install, launch, peer connect.
- `Termux/INSTALL_PROOT_UBUNTU.sh`, `START_PROOT_UBUNTU.sh`: full Linux environment fallback.
- `Termux/*PHONE_RELAY.sh`: phone node hosting controls.
- `Termux/termux_preflight.py`: required full dependency import gate.
- `docs/FULL_TERMUX_PORT.md`: detailed parity, dependencies and risks.

## Quick start

```sh
pkg update && pkg install -y git unzip
cd ~/CryptoIRC_TERMUX_CLI
bash Termux/INSTALL_TERMUX.sh
bash Termux/START_TERMUX.sh
```

If Android-native dependencies fail:

```sh
bash Termux/INSTALL_PROOT_UBUNTU.sh
bash Termux/START_PROOT_UBUNTU.sh
```

See [Termux/README.md](Termux/README.md), [docs/FULL_TERMUX_PORT.md](docs/FULL_TERMUX_PORT.md) and [SECURITY.md](SECURITY.md). The full wallet is experimental and unaudited; don't use substantial funds. The Android package does not ship Bitcoin Core or Monero wallet RPC.


## Automatic detection of changed relay fingerprints

See [FINGERPRINT_ROTATION.md](FINGERPRINT_ROTATION.md) for safe verification and one-endpoint trust update. A changed fingerprint is detected automatically but NEVER automatically trusted.
