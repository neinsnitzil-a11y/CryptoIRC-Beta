# CRYPTO NOCTURNE v4.5.1 — VaultForge Mesh desktop integration

This update adds the **VaultForge v2.7-compatible encrypted mesh** to the existing Tkinter application. It does not replace or alter existing `.vault` files, wallet private keys, fiat ledger files, BTC Core integration, Monero RPC, or existing payment implementations.

## Starting on Windows

1. Extract the ZIP to a fresh directory; run `START_WINDOWS.bat` (Python **3.12 64-bit** required; it sets up an isolated runtime on first launch).
2. Open **Mesh Network** in the left navigation (the legacy **Internet Chat** menu entry also opens this screen).
3. Enter a chat username, choose **Register** or **Log In**, and enter a separate **chat password** (14+ characters). Existing *VaultForge CLI chat accounts on the same Windows user profile* are discoverable, as both applications use `~/VaultForge/mesh_chat/accounts.json`.
4. Under `WAN / AWS`, the default bootstrap is **18.188.145.207:6667**. Click **Connect** to try its encrypted handshake. The relay must still be online and reachable. A successful TCP test alone is not enough.
5. Use **Scan Public Nodes** for signed opt-in community node listings. Select a node to copy its endpoint and expected identity, then **Connect**. The app rejects fingerprint mismatches, but **signed listings do not prove a node is safe, reachable or owned by the claimed person**. Verify first-contact fingerprints independently.
6. **Live Rooms** shows rooms reported by peers in the currently connected mesh; select and **Join** or enter a channel name such as `#general`. Type in the chat box and press Enter/Send. The input remains visible while messages arrive.
7. **Online Users** lists reachable peers, not everyone globally registered. Select a person and choose **Message Selected** for a private DM; clear the recipient field to send a public channel message.
8. Public history is displayed on login and requested from the relay after connection and when joining. The relay must be a history-capable v2.7 node for historical replay. Older servers cannot recover messages they never stored.
9. **Upload File / Image**, **Share Folder (ZIP)** and **Incoming Files → Accept & Save** exchange recipient-encrypted files or bounded ZIP archives. The recipient must consent; folders are never automatically extracted. The transport limit remains **4 MiB per transfer**. Both sender and recipient need to be online.

## Network modes, node hosting, and privacy

- **WAN / AWS:** publicly reachable relay or a peer-hosted node; for hosted WAN nodes, open TCP port on router and host firewall. `0.0.0.0` is the *listen binding*, never an address that other clients should enter. To publish to the community, opt into advertising your real reachable `PUBLIC_IP:PORT`, and connect your relay to a bootstrap peer.
- **Offline LAN:** devices on the same reachable LAN can connect without internet; LAN scan is opt-in and uses UDP discovery port **48877**. Offline mode rejects public IPs/hostnames and does not silently fall back to WAN.
- **Tor required:** install and start a trusted local Tor SOCKS5 service on **9050** (or configure the existing VaultForge network privacy settings for **9150**). Select this mode *before logging in*. WAN connections use SOCKS5h with remote DNS and no direct fallback. An inbound onion service requires separate Tor configuration. Tor routing is not itself an end-to-end encryption substitute, nor does it hide cryptocurrency activity on public blockchains.
- **Background Node:** select mode, name, listener and (for public WAN) optional advertised endpoint, then **Configure Node**, **Start in Background**, **Status**, and **Autostart**. The node uses a separate chat identity and a protected local `node.secret`; there is no wallet key involved. Windows autostart runs when the user logs in; Linux user systemd may need lingering for restart without login. Do not start a second node on a port already bound by another service.

## Build and verification

Use `BUILD_WINDOWS.bat` on a real Windows PC to compile the **actual Windows executable/installer**. This download contains source and the Windows builder, **not a precompiled EXE**. The build requires the project runtime/dependencies and Inno Setup (as configured in the existing builder). `python src/build_release.py test` runs source regressions. Test *compiled* execution and actual AWS encrypted handshakes on Windows separately.

This is a custom IRC-style protocol, **not RFC IRC**. Internet-wide discovery uses signed, voluntary announcements routed by reachable bootstraps; it does not automatically find arbitrary servers on the internet. File content and private DMs are encrypted for recipients, while public channels and their saved history are readable by participating relays. This networking code has **not been independently audited**. Keep wallet and payment production release gates blocked pending the separate cryptographic audit, penetration testing, mainnet/testnet evidence, real installer/upgrade tests, signed updates, recovery drills, and legal/provider approvals.
