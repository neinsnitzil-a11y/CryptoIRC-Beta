# Multi-Relay Directory & Live Peer Status — Network Update 2.8.0

**Network default:** `18.227.91.173:6667` (user's new AWS EC2 public IP, 2 TB server).  
**Previously used relay:** `18.188.145.207:6667` (kept in host list).  
**Do not use as a WAN address:** `172.31.35.252` (private EC2 VPC IP).  
**Applies to:** CRYPTO NOCTURNE GUI, VaultForge Windows/Linux CLI, CryptoIRC Termux CLI, packaged Relay_Only sources.

## What changed

- Added **persistent `relay_hosts.json`** in the existing per-user chat storage root. First migration imports previously trusted custom hosts from `known_peers.json` without modifying fingerprints. New AWS and old AWS appear as separate entries.
- New sessions **auto-select the saved active relay**; initially `18.227.91.173:6667`. Connect multiple manually if desired. The active relay is a UI preference, not a cryptographic trust authority.
- Each saved relay shows **CONNECTED / DISCONNECTED**, display label, active selection, and whether it has a stored fingerprint. Only a completed authenticated encrypted handshake counts as connected.
- **GUI:** Mesh Network → Saved Relays / Live Hosts tab; **Save Host**, **Use as Active**, **Connect Selected**, **Remove Host**. The **Live Connections** tab displays direct authenticated links. Online Users refreshes from signed presence every two seconds.
- **CLI/Termux:** `/servers`, `/servers add HOST:PORT Optional Display Name`, `/servers select N`, `/servers connect N`, `/servers remove N`. `/status`, `/peers`, `/users`, `/online`, `/public` remain available.
- Manually entered `--peer HOST:PORT` endpoints are kept in the directory. Custom relays can be re-selected after restart. Removing a host entry **never erases saved identity pins, accounts, wallet data, downloads, or chat history**.
- **First-contact trust:** A new endpoint automatically pins its cryptographically authenticated identity on first successful handshake (TOFU); no manual fingerprint typing is required. A fingerprint **change at the same HOST:PORT** still blocks connection until separately verified with that server operator. After verification, users may approve a **pre-filled** changed fingerprint using a YES prompt (CLI) or confirmation dialog (GUI), instead of manually retyping the characters. This is **not** automatic acceptance of changed identities.

## Quick start

**CLI Windows/Linux**: use your existing installer/launcher, then start Chat without an explicit `--peer` to use the saved active server, or run `python mesh_chat.py --listen 127.0.0.1:0` inside its installed runtime. Log in with your existing chat identity, then run:

```text
/servers
/servers add chat.example.net:6667 Friend's relay
/servers select 1
/servers connect 2
/status
/peers
/users
/public
```

**Termux:** install as before, then run `bash Termux/CONNECT_TERMUX.sh` to use the default or saved active server; provide `HOST:PORT` to connect to a specific server. The ordinary Termux CLI can use the same `/servers` commands.

**GUI:** start using your existing Windows launcher (`START_WINDOWS.bat`) / build script (`BUILD_WINDOWS.bat`). Log in to your existing chat account. Open Mesh Network → Saved Relays / Live Hosts. The client selects your saved active relay at login. The Live Connections and Online Users tabs display live, not merely previously saved, links.

## Changing AWS machines

1. Install **the relay server software** on the new EC2 instance and configure the same peer protocol, not a stock IRC daemon. Listen on `0.0.0.0:6667`. **TCP 6667 inbound** must be permitted in EC2 security group, instance firewall, and routing. Restrict exposure to authorized users where possible.
2. For new server identities and a **new endpoint**, clients use first-contact TOFU; there is no old endpoint pin to rotate. Don't copy another user's private chat identity or wallet seeds into the relay.
3. For **the same endpoint** serving a different identity, clients stop with identity-change protection. Verify the fingerprint on the machine via a trusted admin session before clicking confirmation.
4. To preserve a relay's identity across a rebuild, securely restore the **relay's own protected chat account/identity** (not users' wallet data). With the same key, the authenticated peer identity stays stable. Back up before migration.
5. An EC2 instance with a **2 TB EBS volume** does not automatically make that volume the chat file store. Separately mount the volume, configure the relay's intended storage location, permissions, backup and capacity policies, and verify server-side persistence. The current file-transfer protocol does **not** become centralized persistent attachment hosting merely because clients point at a larger relay.
6. The public node directory lists only participants who deliberately publish signed advertisements; it is not a worldwide server search or a proof that an advertised address is safe.

## Security and compatibility

This is a custom **IRC-style encrypted mesh**, **not** compatible with conventional IRC servers. The protocol and wallet project are experimental and not independently audited. On first contact, TOFU can be attacked if an adversary intercepts the *first ever* connection. Compare the pinned fingerprint using an independent source if strong authentication is needed. Changed fingerprints are never accepted silently. Multiple connected relays may bridge message traffic in rooms that share the same identity/mesh; only connect trusted communities if you intend that interaction.

No cloud connectivity or 2 TB attachment persistence was verified from the local build environment. No precompiled Windows EXE, Linux binary, or Android APK is supplied. Windows GUI compilation and physical Android execution require a real device/build environment.
