# VaultForge Relay-Only v2.7.1 — Windows Node Guide

This folder hosts **only** the VaultForge mesh chat relay. It does not include or require the cryptocurrency wallet. For the complete user/operator manual, read the main package's `README.md` (also copied into `Windows/README.md`).

## Install and set up

Open this `Windows/Relay_Only` folder in Explorer and run:

1. `INSTALL_WINDOWS.bat` — install isolated Python 3.12 and chat-only dependencies.
2. `SETUP_NODE_WINDOWS.bat` — set up a dedicated chat-only relay identity. Choose WAN for a publicly reachable node, LAN for local-network-only hosting, or Tor for a separately configured onion service.
3. `START_NODE_WINDOWS.bat` — launch node in background; `STOP_NODE_WINDOWS.bat` stops it. `START_RELAY.bat` runs the interactive relay variant.
4. From the parent Windows folder, `NODE_STATUS_WINDOWS.bat` displays the main app node status; relay-only has its own configuration and code, so use the matching launcher for the node actually installed.

To host publicly, configure router TCP port forwarding, allow the chosen inbound TCP port in Windows Firewall, and provide other users with **your public IP/DNS:port**. `0.0.0.0` means bind all *local* interfaces; it is never a peer destination. Networks behind carrier-grade NAT may need a reachable alternate relay, VPN or configured onion service. Do not expose the unaudited protocol publicly without access controls and monitoring.

## Joining peers and discovering nodes

Regular users should launch the **full** VaultForge CLI, choose main menu **21 → 1** to connect to the default AWS node (`18.188.145.207:6667` at last configuration) or **21 → 5** for another user's node, then create/login to **their local chat account**. Public discovery is menu **21 → 16**; LAN scan is menu **21 → 8/9**. Hosts only appear in the public directory when they explicitly publish a reachable endpoint to a connected bootstrap/peer path. The full README documents commands for rooms, DMs, history, user lists, attachments, Tor and wallet security.

## Persistence and safety

Windows autostart is a **user-login startup** feature, not a Windows system service that runs before login. A laptop going to sleep stops hosting regardless of a startup shortcut. A Windows chat relay must keep its identity store and peer pins privately backed up; do **not** upload wallet vaults, recovery phrases or signing keys to public nodes. The custom protocol is experimental and not independently audited.
