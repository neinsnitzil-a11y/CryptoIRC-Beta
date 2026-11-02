> **Current AWS bootstrap fix:** Read `INSTALL_AND_NODE_SETUP_FIX.md` in the full CLI root or `README_SETUP_FIX.md` in the AWS Launcher. A created `~/VaultForge` folder is **not** an initialized server identity. Use guided first-run setup.

# VaultForge Unified CLI v2.7.2 — Complete User, Network & Server Manual

**Release:** `2.7.2-mesh-auto-connect-roster-preview`  
**Platforms:** Windows and Linux; independent application directories  
**Included components:** encrypted 30-format wallet creator, selected cryptocurrency transfer paths, Security Center, authenticated P2P mesh chat, LAN discovery, opt-in public-node directory, encrypted direct messages, file/folder sharing, and optional relay-only deployments  
**Status:** **EXPERIMENTAL / UNAUDITED. NOT PRODUCTION-READY FOR REAL FUNDS OR OPEN PUBLIC CHAT.**

This README documents the **v2.7.2 CLI source included in this ZIP**, based on the v2.7.1 wallet and relay implementation. It is not a description of a hypothetical future release. Whenever the source does **not** implement a capability, the limitation is explained here. The Windows and Linux copies of this README contain the same material, so you can refer to it after extracting either platform folder.

> **Quick distinction:** A *wallet* creates/holds cryptocurrency keys; a *mesh chat account* has its own password and identity keys; a *relay node* connects chat participants. **Never deploy cryptocurrency vaults, seed phrases or Bitcoin Core authentication material to an internet-facing chat relay.**

---

## Contents

1. [Start here: choose your task](#1-start-here-choose-your-task)
2. [What VaultForge is and is not](#2-what-vaultforge-is-and-is-not)
3. [Release folders and important files](#3-release-folders-and-important-files)
4. [Windows installation and start](#4-windows-installation-and-start)
5. [Linux installation and start](#5-linux-installation-and-start)
6. [First-time chat account registration](#6-first-time-chat-account-registration)
7. [Connect to the existing AWS relay](#7-connect-to-the-existing-aws-relay)
8. [AWS EC2: deploy a new relay-only server](#8-aws-ec2-deploy-a-new-relay-only-server)
9. [AWS EC2: update an existing node safely](#9-aws-ec2-update-an-existing-node-safely)
10. [Keep an AWS node running in the background](#10-keep-an-aws-node-running-in-the-background)
11. [Host a public relay from your own computer](#11-host-a-public-relay-from-your-own-computer)
12. [Offline LAN chat and peer scanning](#12-offline-lan-chat-and-peer-scanning)
13. [Public-node discovery and connecting to advertised nodes](#13-public-node-discovery-and-connecting-to-advertised-nodes)
14. [Room creation, messaging and online-user lists](#14-room-creation-messaging-and-online-user-lists)
15. [Private direct messages and trust](#15-private-direct-messages-and-trust)
16. [Share images, files and folders](#16-share-images-files-and-folders)
17. [Chat history and retention](#17-chat-history-and-retention)
18. [Tor privacy and onion services](#18-tor-privacy-and-onion-services)
19. [CLI menu reference: all 21 selections](#19-cli-menu-reference-all-21-selections)
20. [Mesh menu reference: all 17 selections](#20-mesh-menu-reference-all-17-selections)
21. [Chat command reference](#21-chat-command-reference)
22. [Command-line flags and direct launcher commands](#22-command-line-flags-and-direct-launcher-commands)
23. [Wallet creation, storage and recovery](#23-wallet-creation-storage-and-recovery)
24. [Bitcoin receive, balance, spend and confirmation](#24-bitcoin-receive-balance-spend-and-confirmation)
25. [EVM, ERC-20, Monero and supported coins](#25-evm-erc-20-monero-and-supported-coins)
26. [Security Center, passwords and new seed phrases](#26-security-center-passwords-and-new-seed-phrases)
27. [Firewall and port reference](#27-firewall-and-port-reference)
28. [Troubleshooting: installation, AWS, presence and transfers](#28-troubleshooting-installation-aws-presence-and-transfers)
29. [Maintenance, backup, upgrades and removal](#29-maintenance-backup-upgrades-and-removal)
30. [Architecture, security boundaries and limitations](#30-architecture-security-boundaries-and-limitations)
31. [Validation checklist](#31-validation-checklist)

---

## 1. Start here: choose your task

| You want to… | Go to… |
|---|---|
| Install and launch on Windows | [Windows setup](#4-windows-installation-and-start) |
| Install and launch on Ubuntu/Debian/Kali | [Linux setup](#5-linux-installation-and-start) |
| Make a chat account | [Registration](#6-first-time-chat-account-registration) |
| Join the AWS chat | [Connect to AWS](#7-connect-to-the-existing-aws-relay) |
| Host the **small chat server** on AWS | [New AWS relay](#8-aws-ec2-deploy-a-new-relay-only-server) |
| Upgrade AWS without losing the existing identity | [AWS update](#9-aws-ec2-update-an-existing-node-safely) |
| Run a node after closing the terminal | [Background services](#10-keep-an-aws-node-running-in-the-background) |
| Host from a laptop with router forwarding | [Self-hosting](#11-host-a-public-relay-from-your-own-computer) |
| Chat with no internet (on the same LAN) | [Offline LAN](#12-offline-lan-chat-and-peer-scanning) |
| Find other publicly advertised nodes | [Public discovery](#13-public-node-discovery-and-connecting-to-advertised-nodes) |
| Create a room, DM, see online users | [Rooms](#14-room-creation-messaging-and-online-user-lists), [DMs](#15-private-direct-messages-and-trust) |
| Send pictures, files or folders | [Attachments](#16-share-images-files-and-folders) |
| Recover earlier public room messages | [History](#17-chat-history-and-retention) |
| Use Tor for outbound chat connections | [Tor](#18-tor-privacy-and-onion-services) |
| Make a BTC wallet or send BTC | [Wallets](#23-wallet-creation-storage-and-recovery), [Bitcoin](#24-bitcoin-receive-balance-spend-and-confirmation) |
| Fix a failure | [Troubleshooting](#28-troubleshooting-installation-aws-presence-and-transfers) |

### Five-minute chat setup

**On Windows:** extract the package, open `Windows/`, run `INSTALL_WINDOWS.bat`, then `START_WINDOWS.bat`. At the main menu choose **21 → 1**. Accept the default `18.188.145.207:6667` *only if that address is still your working relay*, create a **local** chat user (option **1** at the account screen), and use `/users`, `/join #general`, and regular text to chat.

**On Linux:** extract, `cd Linux`, run `chmod +x *.sh`, `./install_linux.sh`, `./start_linux.sh`; use the same **21 → 1** chat menu. Do **not** run the installer with `sudo`.

**On AWS:** use **only the chat-only relay** (`Linux/Relay_Only/` or the matching standalone AWS relay package). Wallet libraries and crypto vaults are unnecessary on the server. The production-style background process in this package is named `vaultforge-mesh.service`; a healthy service listens on `0.0.0.0:6667` and survives SSH disconnects.

---

## 2. What VaultForge is and is not

VaultForge bundles two largely independent sets of functionality:

- **Self-custody wallet CLI:** 30 advertised address/derivation formats, encrypted `.vault` files, BIP39 and Monero recovery information, selected EVM send paths, and Bitcoin Core-backed index-0 Bitcoin operations.
- **Chat/mesh CLI:** local encrypted identities, authenticated encrypted peer links, relayed channel messages, signed user presence, opt-in signed public node advertisements, LAN discovery, Tor-routed outbound peer links, private messages, small encrypted transfers, and saved public-channel history.

**It is not** an RFC-compliant IRC server, a generic scanner for all IRC servers worldwide, a decentralized account registry, an audited anonymity system, a complete 30-coin sending wallet, or a guarantee that cryptocurrency transactions succeed. HexChat, WeeChat and other standard IRC clients cannot join this custom wire protocol as-is.

The AWS relay is an **optional always-reachable peer/bootstrap**, not the owner of client chat passwords or wallet seeds. Without AWS, users can connect through another reachable self-hosted node or a same-LAN mesh. A WAN connection still requires actual network reachability or separately configured networking such as port forwarding, a VPN, or an onion service. This release does **not** implement automatic NAT traversal or a fully decentralized DHT.

---

## 3. Release folders and important files

The top-level archive contains:

```text
VaultForge_Unified_v2.7.2/
├── README.md                       <- This complete manual
├── QUICKSTART_NETWORK.md           <- Older condensed network notes
├── MESH_UPDATE_2.7.1.md            <- Release change notes
├── Windows/                         <- Independently installable Windows CLI
│   ├── README.md
│   ├── INSTALL_WINDOWS.bat
│   ├── START_WINDOWS.bat
│   ├── CONNECT_AWS_WINDOWS.bat
│   ├── HOST_RELAY_WINDOWS.bat
│   ├── SETUP_NODE_WINDOWS.bat
│   ├── STOP_NODE_WINDOWS.bat
│   ├── NODE_STATUS_WINDOWS.bat
│   ├── ENABLE_NODE_AUTOSTART_WINDOWS.bat
│   ├── SCAN_LAN_WINDOWS.bat
│   ├── SCAN_PUBLIC_WINDOWS.bat
│   ├── vaultforge.py, mesh_chat.py, node_manager.py, ...
│   ├── requirements.txt
│   ├── docs/SECURITY_AND_RECOVERY.md
│   ├── tests/
│   └── Relay_Only/               <- Windows chat-only node
└── Linux/                           <- Independently installable Linux CLI
    ├── README.md
    ├── install_linux.sh
    ├── start_linux.sh
    ├── INSTALL_REQUIREMENTS_LINUX.sh
    ├── HOST_RELAY_LINUX.sh
    ├── SETUP_NODE_LINUX.sh
    ├── STOP_NODE_LINUX.sh
    ├── NODE_STATUS_LINUX.sh
    ├── SCAN_LAN_LINUX.sh
    ├── SCAN_PUBLIC_LINUX.sh
    ├── vaultforge.py, mesh_chat.py, node_manager.py, ...
    ├── requirements.txt
    ├── docs/SECURITY_AND_RECOVERY.md
    ├── tests/
    └── Relay_Only/              <- Linux/AWS chat-only node
```

The `Windows/` and `Linux/` app folders carry their own source, dependencies, launchers and tests. Do not mix their installation scripts. The `Relay_Only/` subfolders deliberately omit the cryptocurrency wallet engine and need only chat-related dependencies.

**Generated, local-only directories (not part of the release):** `.venv/`, `.runtime/`, Python caches, logs, temporary files and user-specific application data. Do not add these to a public distribution. User data is normally **outside** the application directory under your home folder.

---

## 4. Windows installation and start

1. Download and extract the ZIP to a user-writable directory, for example `C:\VaultForge\VaultForge_Unified_v2.7.2\`.
2. Open its `Windows` folder. Do not run from inside the ZIP archive.
3. Double-click **`INSTALL_WINDOWS.bat`** and let it finish. It targets CPython **3.12** and creates an isolated `.venv` in this folder; if necessary it uses a private `uv`-managed Python installation.
4. Double-click **`START_WINDOWS.bat`**, choose the function you want, and avoid putting passwords or recovery phrases on a command line.

PowerShell from the extracted **Windows** folder:

```powershell
.\INSTALL_WINDOWS.bat
.\START_WINDOWS.bat
```

Optional convenience scripts:

```powershell
.\CONNECT_AWS_WINDOWS.bat
.\SCAN_LAN_WINDOWS.bat
.\SCAN_PUBLIC_WINDOWS.bat
.\SETUP_NODE_WINDOWS.bat
.\HOST_RELAY_WINDOWS.bat
.\NODE_STATUS_WINDOWS.bat
```

To test the default public relay independently of VaultForge:

```powershell
Test-NetConnection 18.188.145.207 -Port 6667
```

`TcpTestSucceeded : True` proves **TCP reachability only**, not the cryptographic handshake. The script `CONNECT_AWS_WINDOWS.bat` adds connection diagnostics and launches the compatible client on successful checks.

The Windows installer does **not** require administrator privileges. If antivirus, download policy, or Windows execution settings block a step, inspect its specific error; do not disable system security protections blindly. Windows user logon autostart is different from an always-on Windows Service: the provided startup entry runs when the user logs in.

---

## 5. Linux installation and start

Extract the ZIP and open the **Linux** subfolder:

```bash
cd /path/to/VaultForge_Unified_v2.7.2/Linux
chmod +x *.sh
./install_linux.sh
./start_linux.sh
```

The installer **refuses root** and prefers an existing working **CPython 3.12**. Otherwise it downloads a checksum-verified `uv` bootstrap and installs private Python 3.12 under `.runtime/`, then creates `.venv/` and installs dependencies. It does not change the system default Python. Internet access is needed the first time when runtime/packages are missing.

Minimal Ubuntu/Debian prerequisites (if `curl`, `tar`, or `unzip` are missing):

```bash
sudo apt update
sudo apt install -y ca-certificates curl tar unzip
```

Use `sudo` only for apt or later systemd administration, **not** `sudo bash install_linux.sh` or `sudo ./install_linux.sh`.

**Install/reinstall requirements in the isolated environment:**

```bash
./INSTALL_REQUIREMENTS_LINUX.sh
```

Do **not** add `pip --break-system-packages`: that flag is for bypassing protections on externally managed Python installations and is neither needed nor appropriate for this project's `.venv`. Use the provided installer or `.venv/bin/python -m pip` where pip exists.

Direct launch examples from `Linux/`:

```bash
./start_linux.sh
./start_linux.sh --diagnostics
./start_linux.sh --self-test
./start_linux.sh --list-networks
./start_linux.sh spend-btc
./start_linux.sh receive-btc
./start_linux.sh btc-balance
./start_linux.sh btc-status
./start_linux.sh chat --scan
./start_linux.sh chat --scan-public
```

If previous `sudo` runs accidentally made only the application runtime directories root-owned, inspect them first:

```bash
ls -ld . .venv .runtime 2>/dev/null
```

When you have confirmed those directories belong to **this extracted copy**, repair only them:

```bash
for d in .venv .runtime; do
  if [ -d "$d" ]; then sudo chown -R "$(id -u):$(id -g)" -- "$d"; fi
done
```

Do not recursively change permissions under system directories or unrelated wallet backup folders.

---

## 6. First-time chat account registration

Open main menu **21 — MESH CHAT** and choose your connection mode. The child chat process presents:

```text
VAULTFORGE MESH — LOCAL CHAT ACCOUNT
1) Create a new user
2) Log in
3) Change chat password
0) Back
```

- Select **1** to create an identity **on this machine**. Usernames are 3–24 letters, digits, hyphens or underscores; passwords must be at least 14 characters. The app creates separate, encrypted chat identity keys and prints `nickname@short-id`.
- Select **2** to unlock an account **already stored on the same machine**. A username created on AWS is not automatically registered on Windows.
- Select **3** to change a chat account password. This does **not** change a `.vault` password or cryptocurrency seed.
- Verify a peer's full public identity fingerprint out of band before trusting it. First-connection pinning is TOFU (*trust on first use*), not proof of the peer's real-world identity.

Standard chat data location:

```text
Linux:   ~/VaultForge/mesh_chat/
Windows: C:\Users\<your-user>\VaultForge\mesh_chat\
```

The folder can contain `accounts.json`, `known_peers.json`, history, node configuration, downloads and other application state. Back up the identity store securely if you need the *same* identity on another device; copying public nicknames alone does not transfer encrypted identity keys. Cross-device account synchronization is **not** implemented.

---

## 7. Connect to the existing AWS relay

The default sample/live-at-last-check endpoint in this package is **`18.188.145.207:6667`**. It came from the existing EC2 deployment; **its availability and public IP can change**. For a permanent endpoint use a DNS name and a reserved/Elastic IP where appropriate.

**Windows:** `START_WINDOWS.bat` → **21** → **1 CONNECT TO AWS** → press Enter at the suggested endpoint (or type the new `HOST:PORT`). Create or log into **your local** user account. **Linux:** the same numbered menu with `./start_linux.sh`.

Or connect in an existing chat session:

```text
/connect 18.188.145.207:6667
/peers
/users
/join #general
```

**Successful connection evidence** is a `[CONNECTED] peer ..., encrypted` line and the presence of the remote relay in `/peers`. `[CONNECTING]` by itself is not proof of success. The relay's online roster may take a moment to propagate after authentication.

From Windows, check TCP before login:

```powershell
Test-NetConnection 18.188.145.207 -Port 6667
```

From the **same EC2 instance as the relay**, first try `127.0.0.1:6667` rather than the public IP. Never enter EC2's private `172.31.x.x` address from an unrelated home computer.

After connecting, use `/users` for currently reachable participants, `/rooms` for visible rooms, `/join #general` and type a normal message. Public room text is sent by just typing; do **not** use `/msg` unless sending a private message to a different person.

---

## 8. AWS EC2: deploy a new relay-only server

**Recommended:** a small Ubuntu EC2 instance, using the **chat-only** `Relay_Only/` package. You do not need the wallet-generating application or any seed data. AWS hosting is optional: other publicly reachable nodes can replace it.

### 8.1 Create and secure the EC2 instance

1. Create an Ubuntu EC2 instance in your preferred AWS region and choose a suitable instance size for your expected traffic.
2. Store the SSH key securely. Prefer a non-root `ubuntu` account.
3. Ensure it has a **public IPv4 address** or reachable DNS hostname, and a subnet route through an internet gateway.
4. In the security group, allow **TCP 22 only from trusted administrative IP addresses**, and allow **TCP 6667** only from authorized client IPs for private testing. A public service may require `0.0.0.0/0` for 6667, but that exposes an unaudited custom protocol to the internet and should not be done before hardening, monitoring and abuse protections.
5. Consider AWS Budgets alerts. When credits expire, AWS can stop service depending on the account's plan and billing state. A plain auto-assigned public IP can change after instance stop/start; use an Elastic IP or updatable DNS if this is intended to be permanent.
6. **Never put real wallet vaults, seeds, API keys or private signing keys on this host.**

### 8.2 Transfer only chat code

On your own computer, upload the small **relay-only** ZIP (or the `Linux/Relay_Only/` folder). Example if your archive is named `VaultForge_AWS_Relay_v2.7.1.zip`:

```bash
scp -i your-ec2-key.pem VaultForge_AWS_Relay_v2.7.1.zip ubuntu@YOUR_EC2_PUBLIC_IP:~/
```

That name is illustrative; use the **actual** relay ZIP filename you downloaded, not the entire GUI/wallet package. If you already uploaded the full package, you can run only its `Linux/Relay_Only/` directory instead; this doesn't turn the wallet into a service.

### 8.3 Initial relay setup

With a **fresh** relay-only folder on Ubuntu (not replacing an existing identity):

```bash
cd ~/YOUR_RELAY_DIRECTORY
chmod +x *.sh
./install.sh
./AWS_QUICK_SETUP.sh YOUR_EC2_PUBLIC_IP:6667
```

For example, on the previously configured instance:

```bash
./AWS_QUICK_SETUP.sh 18.188.145.207:6667
```

The script installs Python 3.12 chat dependencies, creates the separate `AWSVaultRelay` chat identity if none exists, opts into public advertisement, generates a systemd unit, enables the background service, and checks a local encrypted handshake. **Run it without `sudo`;** it invokes `sudo` only for systemd work. The AWS security-group rule must be set separately in the console.

**Before restarting any service**, verify the generated unit is valid:

```bash
sudo systemd-analyze verify /etc/systemd/system/vaultforge-mesh.service
```

If verification reports a **bad unit file setting**, fix or upgrade the service generator using the previously provided v2.6.1 systemd hotfix rather than repeatedly launching the broken unit. Do not delete the node's account data to fix systemd.

> **IMPORTANT:** If this host already has a working relay, **do not run new-node setup again**. Use the update procedure in [section 9](#9-aws-ec2-update-an-existing-node-safely). A node reinstall or re-registration can change the identity fingerprint that clients have trusted.

### 8.4 Verify the relay

```bash
sudo systemctl status vaultforge-mesh --no-pager
sudo ss -lntp | grep ':6667'
sudo journalctl -u vaultforge-mesh -n 60 --no-pager
```

Expected: `active (running)` and a Python listener bound to `0.0.0.0:6667`. To check locally:

```bash
python3 -c "import socket; socket.create_connection(('127.0.0.1',6667),5).close(); print('LOCAL TCP OK')"
```

On Windows, also test **public reachability** using `Test-NetConnection`. Neither local TCP nor external TCP proves authentication; the final test is an encrypted VaultForge handshake followed by an actual message exchanged between **two distinct client identities**.

---

## 9. AWS EC2: update an existing node safely

The existing node is controlled by `vaultforge-mesh.service`. **Keep its identity, `accounts.json`, `node.secret`, `node.json`, existing history and application storage.** Never point a freshly created standalone service at the same port while the old service is running.

### 9.1 Back up and inspect

On the existing EC2 Ubuntu instance:

```bash
sudo systemctl status vaultforge-mesh --no-pager
sudo systemctl cat vaultforge-mesh
sudo ss -lntp | grep ':6667'
```

Use `systemctl cat` to identify the exact active source directory; it may be `~/IRC/Relay_Only/`, not a differently named downloaded package. Back up important node files **outside** the publicly distributed source tree with owner-only permissions; do not publish these backups or paste their contents into chat.

### 9.2 Apply the matching v2.7.1 relay patch

Use the **separate** `VaultForge_AWS_Relay_v2.7.1_Roster_Fix.zip` package from this project release. Upload it to the existing `Relay_Only` directory. From that directory:

```bash
cd ~/IRC/Relay_Only
unzip -o VaultForge_AWS_Relay_v2.7.1_Roster_Fix.zip
chmod +x APPLY_AWS_MESH_271.sh
./APPLY_AWS_MESH_271.sh
```

The patch expects to find the existing `mesh_chat.py`, `.venv/bin/python`, and a systemd unit pointing at **this same folder**. It backs up the previous protocol files under `.updates/`, compiles the replacements, restarts the existing service, and attempts rollback if startup fails. **It does not intentionally replace your node identity or crypto vaults.** This is a targeted v2.7.1 roster/room/files patch, not a whole-app installer.

If the script says the service points to another folder, **do not force it**: inspect `sudo systemctl cat vaultforge-mesh` and use the directory shown there. Do not change symlink targets or copy secret files just to satisfy an update.

### 9.3 Post-upgrade validation

```bash
sudo systemctl is-active vaultforge-mesh
sudo systemctl status vaultforge-mesh --no-pager
sudo ss -lntp | grep ':6667'
sudo journalctl -u vaultforge-mesh -n 60 --no-pager
```

Then connect updated v2.7.1 Windows and Linux clients, check `/peers`, `/users`, `/rooms`, send a test room message and a DM, and request `/history` after reconnecting. Old messages from before history storage was enabled cannot be recovered retroactively.

---

## 10. Keep an AWS node running in the background

A **foreground** relay launched by `mesh_chat.py --relay` ends when you stop it or its terminal session ends. A **systemd** service is the preferred way to host a continuously running Ubuntu EC2 node.

```bash
sudo systemctl enable --now vaultforge-mesh   # persist across instance reboot
sudo systemctl status vaultforge-mesh --no-pager
sudo journalctl -u vaultforge-mesh -f         # live server logs
sudo systemctl restart vaultforge-mesh        # after a deliberate update
sudo systemctl stop vaultforge-mesh           # deliberately take it offline
sudo systemctl start vaultforge-mesh          # bring it back
```

`enable` means start after future EC2 **boots**; it does **not** keep AWS running after credits expire or an EC2 instance has been stopped. The node does not become a guaranteed 24/7 service until hosting, billing, IP stability, monitoring and operating-system updates are all handled.

Inspect `sudo ss -lntp | grep ':6667'` before launching another foreground relay. **Only one process can bind this address/port.** For a separate laptop test use a different local port or stop the existing node first.

On Linux desktops, the CLI's **21 → 14** creates a **user** systemd service. A user service may require `loginctl enable-linger USER` to start without the user logging in; that is distinct from the AWS **system** service above. On Windows, option 14 installs a **user-login** startup shortcut, not a Windows service.

---

## 11. Host a public relay from your own computer

A laptop or desktop can be a relay if others can reach it. **Listen address and connect address are different:** `0.0.0.0:6667` means “accept connections on all interfaces of *this computer*”; clients must enter the host's **public IPv4/DNS address and forwarded TCP port**, never `0.0.0.0`.

### 11.1 Host interactively (foreground)

Start the application, choose **21 → 6 HOST PUBLIC/REMOTE MESH RELAY**, choose TCP port 6667 (or another permitted port), create/log in to a chat-only account, and type `PUBLIC LISTEN` when prompted. Closing the app will end this foreground host.

### 11.2 Host in the background (Linux)

From `Linux/`:

```bash
./start_linux.sh node-setup --mode wan --name LaptopRelay --listen 0.0.0.0:6667
./start_linux.sh node-start
./start_linux.sh node-status
./start_linux.sh node-stop
```

`node-setup` refuses to overwrite an existing node identity. The WAN setup requires an explicit exposure confirmation; do not run it unattended by piping random confirmation text. The standalone manager supports `--yes` for deliberate scripted acknowledgement, but keep that out of unreviewed scripts.

To opt into listing this host publicly and connect its relay to the known AWS bootstrap, **when setting up a new node**:

```bash
./start_linux.sh node-setup --mode wan --name LaptopRelay \
  --listen 0.0.0.0:6667 \
  --advertise YOUR_PUBLIC_IP:6667 \
  --peer 18.188.145.207:6667
```

If the identity is already configured, do **not** rerun setup. Instead update only its advertisement:

```bash
./.venv/bin/python -I node_manager.py publish YOUR_PUBLIC_IP:6667
./start_linux.sh node-stop
./start_linux.sh node-start
```

### 11.3 Windows laptop/desktop

Run `INSTALL_WINDOWS.bat` first. Start the CLI → **21 → 10** to create a node identity, **11** to start it in the background, **12** to stop, **13** for status, and **14** for user-login autostart. Equivalent `.bat` launchers are included for setup, hosting, status, stop and autostart.

### 11.4 Router and carrier-grade NAT

A computer at `192.168.x.x`, `10.x.x.x` or `172.16–31.x.x` is on a private network. To accept inbound public connections, configure your router to forward **external TCP 6667 to your host's LAN IP/TCP 6667**, and open the appropriate *host OS* firewall rule. Give the host a stable local DHCP reservation. If your ISP uses **carrier-grade NAT (CGNAT)**, ordinary port forwarding may not work: request a public IP, use a reachable trusted relay or VPN, or configure a Tor onion service separately. There is no automatic hole punching or UPnP setup in this release.

A host must also connect to at least one bootstrap/mesh peer if it wants its signed public advertisement to reach that peer network. Merely opening a port or advertising an IP **does not** cause a global directory to discover it.

---

## 12. Offline LAN chat and peer scanning

**Offline** means no internet is needed but clients still require a functioning reachable **local network**: same router, Wi-Fi access point, Ethernet LAN, or an intentionally routed local segment. “Offline” does **not** mean chatting between two computers with no network link at all.

On Linux host A, choose **21 → 7 HOST OFFLINE LAN MESH** (defaults to TCP 7777) and approve `LAN LISTEN`. On laptop B, choose **21 → 8 SCAN LAN & CONNECT** or **9 SCAN LAN ONLY**. LAN discovery uses **UDP port 48877** and opt-in signed responses; the host's TCP listener must also be reachable. Windows has `SCAN_LAN_WINDOWS.bat`; Linux has `./SCAN_LAN_LINUX.sh`.

After scanning from an interactive chat:

```text
/scan
/connect 1
/users
/join #general
```

`/connect 1` means connect to the **first result of your last LAN scan**, not a global server ID. If discovery fails on a network that blocks broadcasts or isolates wireless clients, use a known local address explicitly:

```text
/connect 192.168.1.50:7777
```

**Offline enforcement:** `--offline` refuses public IPs, hostnames and automatic WAN reconnect. Direct WAN, public discovery and Tor-only mode are intentionally incompatible with offline-only mode. Use menu **21 → 3** for single-device loopback-only local chat (no remote peers), or **21 → 7/8** for multi-device offline LAN.

---

## 13. Public-node discovery and connecting to advertised nodes

Choose **21 → 16 SCAN PUBLIC NODES**. The client connects to a **known bootstrap** such as `18.188.145.207:6667` and requests signed advertisements from nodes that **opted in**. The UI lists nickname, identity and endpoint, but a signed listing is **not** proof that the service is currently reachable, trustworthy or actually operated by the displayed name.

From a Linux shell:

```bash
./SCAN_PUBLIC_LINUX.sh
./SCAN_PUBLIC_LINUX.sh 18.188.145.207:6667
./start_linux.sh chat --scan-public --bootstrap 18.188.145.207:6667
```

From an interactive chat:

```text
/public
/connectpublic 1
```

`/connectpublic 1` connects to the first result of `/public`, after a review and explicit confirmation. The menu's public scanner also offers selecting a numbered result and typing `CONNECT`.

**For a node to show up:** the operator must (1) run an authenticated VaultForge relay, (2) make it reachable by a public `HOST:PORT` or equivalent, (3) explicitly publish `--advertise PUBLIC_IP:PORT` in WAN mode, and (4) connect the node to a bootstrap/peer path where announcements can propagate. An arbitrary internet host exposing TCP 6667 is **not** automatically listed. This package does **not** scan internet address ranges or standard IRC servers.

If AWS is offline, you may use another known/bootstrap peer or connect to a host directly, but the client cannot obtain a complete worldwide directory without a reachable discovery path. The currently known AWS endpoint is a default, **not** a promise of permanent availability.

---

## 14. Room creation, messaging and online-user lists

Every chat session has an active room, usually `#general`. Type ordinary text to send a **room message**, not a DM. Rooms are mesh-visible channel labels; they are not centrally reserved, access-controlled groups. The client supports up to **12 joined channels**.

```text
/join #general               # join or create the room and make it active
/create #music               # same as join/create
/rooms                       # rooms visible from connected peers
/leave #music                # leave a room (at least one must remain)
/users                       # all recently authenticated, reachable online users
/peers                       # directly connected peers only
```

Example:

```text
/join #music
Hello everyone in #music!
```

**Online means known via the currently connected mesh.** It is not a worldwide list of all people who installed VaultForge. A user whose device is offline, not connected to your reachable component, not recently announced, or blocked will not appear. Updated v2.7.1 peers replay recently signed presence after connection, but there is no central global registration database. Two peers sharing the same AWS relay should become visible when the encrypted links and presence messages are healthy.

Use `/users` to obtain the exact `nickname@short-id` for private messaging. A nickname can be duplicated across independent identities; prefer the exact ID to avoid ambiguous recipients. Relay nodes may appear in online lists as users because they have their own chat identities.

---

## 15. Private direct messages and trust

Use `/users`, then send to a **different online user's** identity:

```text
/msg Mr_Robot@7c030891e74ce8d5 Hello, this is a private message.
```

The address above is only an **example**; copy the actual `nickname@ID` from your live `/users` output. Attempting to DM your own ID, an offline identity, or an ambiguous nickname produces a recipient error. Public room text is typed **without** a `/msg` command.

DM content is encrypted to the recipient's advertised X25519 key and signed/relayed through authenticated connections. **The custom cryptographic design is unaudited.** Relays can observe metadata and timing even if they cannot decrypt a correctly addressed DM. Both participants must be currently reachable through the mesh; offline mailboxes are not implemented.

Peer trust and privacy commands:

```text
/whoami                     # your chat identity and fingerprint
/trust                      # saved first-contact identity pins
/unpin HOST:PORT            # remove a pin after typing explicit confirmation
/block USER_ID              # local block
/peers                      # inspect direct connections
```

A changed fingerprint after reinstalling an AWS node is a security-sensitive event. Do **not** automatically remove a pin; verify the server's identity by an independent channel first.

---

## 16. Share images, files and folders

VaultForge v2.7.1 supports **opt-in encrypted offers**, not unlimited online storage or permanent uploads. The receiver must be **online and reachable**, the offer must finish arriving, and the receiver must explicitly `/accept` it before it is written to downloads.

### 16.1 Send a file or image to a person

```text
/users
/upload Bobby@ACTUAL_ID /home/user/Pictures/photo.png
```

Windows example (type in the VaultForge chat terminal, not in PowerShell):

```text
/upload Bobby@ACTUAL_ID C:\Users\YourUser\Pictures\photo.png
```

Other accepted commands: `/sendfile USER@ID PATH` and `/share USER@ID PATH`.

### 16.2 Send a folder to one person

```text
/sendfolder Bobby@ACTUAL_ID /home/user/Documents/Samples
```

Or simply `/upload USER@ID DIRECTORY`; the client detects a directory and makes a **ZIP snapshot**. It refuses symbolic links and selected wallet/credential filenames; receivers do **not** automatically extract a ZIP.

### 16.3 Send to everyone currently online in one room

```text
/join #music
/uploadroom #music /home/user/Pictures/photo.png
/uploadroom #music /home/user/Documents/Samples
```

The sender creates **individually encrypted offers** to each currently reachable member of that room. Maximum **8 recipients** per room transfer; it is not a broadcast to offline users or a cloud-hosted room attachment. `/sendroom` is an alias.

### 16.4 Receive an attachment

```text
/files                   # list offers and transfer IDs
/accept TRANSFER_ID      # write a finished transfer to private downloads
/downloads               # show saved download directory
/reject TRANSFER_ID      # discard an unwanted offer
```

Downloads are saved under the current user's `~/VaultForge/mesh_chat/downloads` (or Windows equivalent). Do not execute untrusted binaries or automatically extract downloaded archives. Inspect the file and its source before opening it.

### 16.5 Actual transfer limits

| Constraint | v2.7.1 behavior |
|---|---|
| File payload | 1 byte to **4 MiB** per transfer |
| Folder input | At most **8 MiB uncompressed** and **100 files** |
| Compressed folder ZIP | Must fit in the **4 MiB** encrypted transfer cap |
| Room fan-out | At most **8 currently online** other room members |
| Receiving | Requires completed transfer and explicit `/accept ID` |
| Offline recipients | **Not supported**: no persistent delivery queue |
| File safety | SHA-256 integrity check and authenticated encryption in the source implementation; externally unaudited |
| Server file storage | No full-file cloud upload/archive service |

Sending an offer is not proof that the remote user accepted or saved it. On failure use `/files` on the intended recipient and inspect logs; avoid assuming that the file was delivered.

---

## 17. Chat history and retention

Type `/history` for the currently active room or `/history #music` after joining that room. When you `/join`, the client shows locally saved messages and requests recent signed history from compatible connected peers. Reconnecting can recover messages that a **history-capable relay** recorded while you were away.

The v2.7 history implementation is limited to **up to 40 public room messages per room for up to 7 days on an updated relay**, and **up to 25 recent messages** in a sync response. The original v2.6 relay had no persistent history; messages **before** enabling history cannot be recovered. History synchronization only works with peers/relays that have the corresponding update installed.

**Privacy:** Channel messages are per-link encrypted in transit but are **not end-to-end encrypted** across relays. Public-room history is stored **in plaintext on the relay**, accessible to its operator. Private DMs and encrypted file contents are **not** supposed to be inserted into public room history. Treat every room as public to its connected operators/members; do not post sensitive wallet or personal secrets.

---

## 18. Tor privacy and onion services

VaultForge has **two separate Tor-related controls**:

1. **Security Center (main menu 20)** can require selected EVM RPC calls to use a local SOCKS5h proxy; it also checks Bitcoin Core's onion configuration before certain BTC RPC-backed actions. Monero external wallet-RPC sends are blocked in Tor-required mode because their complete external routing cannot be verified by this app.
2. **Mesh chat (menu 21 → 15 / `--tor`)** routes outbound WAN chat-peer connections through a **locally running SOCKS5 Tor proxy**, refusing fallback to direct WAN. It does not install, maintain or validate Tor circuits or hidden services automatically.

Typical Linux Tor package setup (service name may vary by distribution):

```bash
sudo apt update
sudo apt install -y tor
sudo systemctl status tor --no-pager
```

The application expects SOCKS5 on local port **9050** by default; Tor Browser commonly uses **9150**, with application-specific configuration required. `--tor` alone does **not** create a Tor onion service or hide the IP of a WAN listener bound to `0.0.0.0`.

To **host an inbound onion-only relay**, configure a Tor hidden service separately, with its virtual port forwarded to a VaultForge listener on **`127.0.0.1:7777`**; choose node mode `tor`. Do not expose that loopback-only listener on the public interface, and test the Tor configuration independently. An `.onion` address must be a real configured Tor destination, not a guessed one. Tor and `--offline` are not compatible modes.

**Privacy limitations:** Onion routing does not make public blockchain transfers anonymous; relays may still observe message metadata; endpoint compromise defeats local privacy; and the code's SOCKS5 probe only proves a local proxy responded, not that a trustworthy Tor network route was used. This custom implementation has not had an external privacy/security audit.

---

## 19. CLI menu reference: all 21 selections

Start with `START_WINDOWS.bat` or `./start_linux.sh`:

| # | Action | Notes |
|---|---|---|
| 1 | Create or restore encrypted 30-coin wallet set | Creates a `.vault`; supports 12/24-word BIP39 and separate XMR native seed |
| 2 | List saved encrypted vaults | Lists locally discovered `.vault` files |
| 3 | Unlock and show public receiving addresses | Requires the **selected file's vault password** |
| 4 | Reveal recovery phrases | Requires private display confirmation `REVEAL` |
| 5 | Verify paper backup | Samples words; not independent restoration proof |
| 6 | Change vault encryption password | Preserves seeds and addresses |
| 7 | Check saved EVM native balance | Read-only; **not** BTC, SOL or token balances |
| 8 | Send EVM native currency from vault | Limited set of supported source networks |
| 9 | Send ERC-20 from vault | Supported chain, verified contract details and fee controls required |
| 10 | Check EVM transaction receipt | RPC observation is not guaranteed finality |
| 11 | Show BTC receiving address | Offline BIP84 **mainnet** address from vault |
| 12 | Check confirmed BTC balance | Requires synced local Bitcoin Core; index-0 UTXOs only |
| 13 | SPEND BTC from same encrypted vault | Local Bitcoin Core signing RPC; experimental, explicit authorization |
| 14 | Check BTC transaction confirmations | Uses Bitcoin Core; missing status ≠ failure |
| 15 | Send XMR using local `monero-wallet-rpc` | Uses a separately managed Monero RPC wallet |
| 16 | EVM send from separate V3 keystore | Legacy path |
| 17 | ERC-20 send from separate V3 keystore | Legacy path |
| 18 | Legacy BTC send from separate Bitcoin Core wallet | Different from menu 13 |
| 19 | Diagnostics and supported networks | Dependency and crypto transfer support; distinguishes advertised vs spendable |
| 20 | Security Center | Tor/direct, fresh seeds, permissions, password changes, backup verification |
| 21 | Mesh Chat | Accounts, AWS, host, scan, rooms, DMs, files, history |
| 0 | Exit | Leaves local wallets and identities on disk |

**Do not conflate menu 1's address-generation coverage with sending support for 30 coins.** Unsupported spend operations remain unsupported even if an address can be generated.

---

## 20. Mesh menu reference: all 17 selections

Select **21** in the main menu, then:

| # | Mode | What it actually does |
|---|---|---|
| 1 | Connect to AWS / existing server | Default `18.188.145.207:6667`, outbound to server, localhost ephemeral listener |
| 2 | Reconnect to saved trusted peers | Uses locally stored peer identity pins |
| 3 | Local private chat | Loopback only; **not** another laptop |
| 4 | Advanced connection | Set custom local `HOST:PORT` and optional remote peer |
| 5 | Connect to user-hosted P2P relay | Enter their reachable public/LAN endpoint |
| 6 | Host public/remote mesh relay | Foreground `0.0.0.0:PORT`, requires explicit warning acknowledgement |
| 7 | Host offline LAN mesh | Foreground, offline-only, LAN TCP plus UDP discovery |
| 8 | Scan LAN and connect | Interactive offline LAN listener; `/scan`, then `/connect N` |
| 9 | Scan LAN only | No chat login required |
| 10 | Set up background node | Creates separate `wan`, `lan` or `tor` node identity |
| 11 | Start background node | Starts a detached process; **not** automatically reboot-persistent |
| 12 | Stop background node | Stops an owned background process |
| 13 | Node status | Process, mode, log path |
| 14 | Enable node autostart | User-login startup on Windows, user systemd on Linux |
| 15 | Connect to peer through Tor | Requires external Tor SOCKS5 service |
| 16 | Scan public nodes | Queries signed advertised listings via bootstrap |
| 17 | Diagnose AWS/remote TCP | Network-reachability check, not a crypto handshake |
| 0 | Return | Back to main application menu |

Node setup from the menu only prompts for mode/name; for specific listener, upstream peer and advertised endpoint, use the direct `node_manager.py setup` command shown earlier.

---

## 21. Chat command reference

Run these **inside** the `#general>` / `#room>` chat prompt (not PowerShell or Bash):

| Command | Function |
|---|---|
| `/help` or `/?` | List commands |
| `/users` or `/who` | Show currently known reachable online accounts |
| `/peers` | List authenticated directly connected peer links |
| `/whoami` | Show your own nickname, ID and full identity fingerprint |
| `/trust` | List pinned endpoint public identities |
| `/unpin HOST:PORT` | Remove a pin with an explicit confirmation; verify identity afterward |
| `/block ID` | Block a particular identity locally |
| `/connect HOST:PORT` | Connect to a peer or relay |
| `/scan` | Scan discoverable LAN peers using UDP 48877 |
| `/connect N` | Connect to numbered result from last `/scan` |
| `/public` or `/scanpublic` | Show advertised nodes already learned from connected mesh |
| `/connectpublic N` | Review and confirm connection to advertised result |
| `/join #ROOM` | Join/create and select a channel |
| `/create #ROOM` or `/createroom #ROOM` | Join/create alias |
| `/leave #ROOM` | Leave channel; cannot leave final room |
| `/rooms` | List locally joined and reachable visible rooms |
| `/history` or `/history #ROOM` | Show stored history and request peer replay |
| `/msg USER@ID TEXT` | Send an end-to-end encrypted DM to a currently reachable user |
| `/sendfile USER@ID PATH` | Offer a single file/image privately |
| `/upload USER@ID PATH` | Offer a file **or folder**; folder becomes ZIP |
| `/share USER@ID PATH` | Alias for `/upload` |
| `/sendfolder USER@ID DIR` | ZIP and offer a folder privately |
| `/uploadroom #ROOM PATH` | Encrypted per-recipient offers to online members |
| `/sendroom #ROOM PATH` | Alias for `/uploadroom` |
| `/files` | Show pending received file offers |
| `/accept TRANSFER_ID` | Save finished attachment to downloads directory |
| `/reject TRANSFER_ID` | Discard an offer |
| `/downloads` | Display download destination path |
| `/quit` or `/exit` | Leave the chat session |

**Plain text** (no leading slash) is sent to your **active room**, not to whoever you last saw in `/users`. The CLI has **no GUI recipient selector**: always write the explicit target for `/msg` and `/upload`.

---

## 22. Command-line flags and direct launcher commands

### 22.1 Main wallet CLI

Linux usage from its folder:

```bash
./start_linux.sh --help
./start_linux.sh --diagnostics
./start_linux.sh --self-test
./start_linux.sh --list-networks
./start_linux.sh spend-btc
./start_linux.sh receive-btc
./start_linux.sh btc-balance
./start_linux.sh btc-status
```

For Windows, `START_WINDOWS.bat` accepts comparable arguments after the `.bat` filename. These direct BTC commands open interactive prompts; they do not take secrets as command-line arguments.

### 22.2 Chat CLI

Linux examples:

```bash
./start_linux.sh chat --listen 127.0.0.1:0 --peer 18.188.145.207:6667
./start_linux.sh chat --listen 0.0.0.0:6667 --relay
./start_linux.sh chat --listen 0.0.0.0:7777 --offline --lan
./start_linux.sh chat --scan
./start_linux.sh chat --scan-public --bootstrap 18.188.145.207:6667
./start_linux.sh chat --listen 127.0.0.1:0 --tor --peer YOUR_ONION_HOST:6667
```

| Flag | Effect |
|---|---|
| `--listen HOST:PORT` | Local TCP listener; `127.0.0.1:0` asks OS to assign a free localhost port |
| `--peer HOST:PORT` | Initiate outbound connection; may be repeated |
| `--relay` | Headless authenticated forwarding node |
| `--advertise PUBLIC_IP:PORT` | Opt-in signed WAN endpoint (relay only; requires reachability) |
| `--bootstrap HOST:PORT` | Public listing query source; may be repeated |
| `--scan-public` | Query signed public directory without logging in to a persistent account |
| `--lan` | Listen for/respond to signed local LAN discovery |
| `--offline` | LAN-only enforcement; rejects public IPs/hostnames and WAN reconnect |
| `--scan` | One-time LAN scan (no chat account) |
| `--no-auto-connect` | Skip reconnecting pinned peers on startup |
| `--tor` | Require local SOCKS5 proxy for outbound WAN peer connections, no fallback |

Avoid `--relay` in a normal client session unless deliberately hosting. A public listener on `0.0.0.0` is a security decision. Flags that specify addresses must use `HOST:PORT`, **not** `https://`, `username@host`, or the literal `0.0.0.0` as a remote destination.

### 22.3 Background node manager

```bash
./start_linux.sh node-setup --mode lan --name LaptopRelay
./start_linux.sh node-start
./start_linux.sh node-status
./start_linux.sh node-stop
./.venv/bin/python -I node_manager.py publish YOUR_PUBLIC_IP:6667
```

The direct Python manager also supports `run`, `autostart` and `service-file` actions. Keep an existing node's `node.json`, `node.secret` and encrypted identity unchanged during upgrades.

---

## 23. Wallet creation, storage and recovery

### 23.1 The 30 address formats in the creator

| # | Code | Network / address format description |
|---|---|---|
| 1 | BTC | Bitcoin native SegWit BIP84 |
| 2 | LTC | Litecoin native SegWit BIP84 |
| 3 | DOGE | Dogecoin |
| 4 | BCH | Bitcoin Cash CashAddr |
| 5 | DASH | Dash |
| 6 | DGB | DigiByte |
| 7 | ZEC | Zcash transparent address only |
| 8 | ETH | Ethereum |
| 9 | ETC | Ethereum Classic |
| 10 | BSC | BNB Smart Chain |
| 11 | POLYGON | Polygon PoS |
| 12 | AVAXC | Avalanche C-Chain |
| 13 | ARB | Arbitrum One |
| 14 | OP | Optimism |
| 15 | FTM | Fantom Opera |
| 16 | TRX | TRON |
| 17 | XRP | XRP Ledger |
| 18 | XLM | Stellar |
| 19 | SOL | Solana |
| 20 | ATOM | Cosmos Hub |
| 21 | OSMO | Osmosis |
| 22 | NEAR | NEAR Protocol |
| 23 | FIL | Filecoin |
| 24 | XTZ | Tezos |
| 25 | VET | VeChain |
| 26 | ZIL | Zilliqa |
| 27 | EGLD | MultiversX |
| 28 | SUI | Sui |
| 29 | APT | Aptos |
| 30 | XMR | Monero, native legacy 25-word seed |

**These are derivation/address-generation entries, not 30 independently verified signing/spending integrations.** Verify each address against a trusted independent wallet implementation before depositing any value.

### 23.2 Create a wallet (menu 1)

1. Choose storage: user profile, mounted USB or custom absolute directory.
2. Let the installer perform its writable-folder test; it should print `[STORAGE OK]`.
3. Choose coins by number, code, range (`1-5`) or `ALL`.
4. Choose **1–20 independent wallet sets**. A new set generates independent randomness.
5. Choose **12 or 24 words** for BIP39; optionally enable an additional BIP39 passphrase (not the same as the vault encryption password).
6. Choose a strong **vault password** (minimum 14 characters).
7. Decide whether to import **your own** existing recovery phrase or create a new one; do not import another person's phrase.
8. Wait for `[SAVED] ... .vault`, record your receiving addresses, and reveal recovery phrases **privately** only if needed.
9. Write down and **independently verify** every recovery phrase/passphrase offline before accepting funds.

The creator shares one BIP39 mnemonic among selected BIP39 coins **within a set** and creates a separate native Monero mnemonic for XMR. The extra BIP39 passphrase changes the derived wallet. **Losing that passphrase can make an otherwise correct seed backup unusable.**

Default wallet location:

```text
Linux:   ~/VaultForge/wallets/*.vault
Windows: C:\Users\<your-user>\VaultForge\wallets\*.vault
```

### 23.3 Unlock, reveal, verify and change passwords

- **Menu 3:** select the **correct vault filename** and enter *that vault's own encryption password*. Different vaults can have different passwords.
- **Menu 4:** enter the vault password, then type exactly **`REVEAL`**, not `yes`, before recovery phrases appear. Only do this on a private/offline computer.
- **Menu 5:** verify selected written seed words and the optional passphrase. This is **not** a complete independent restoration test.
- **Menu 6 / Security Center 20 → 4:** re-encrypt with a **new vault password** without changing wallet keys or addresses.

### 23.4 Restore from paper

Use menu 1 to select the same original coin family, phrase and optional BIP39 passphrase. The same compatible **derivation account/index settings** are required to recover the same addresses. Recovery across all 30 families has **not** been independently proved; never rely solely on this application as the only recovery method. Existing `.vault` files are encrypted containers; they are not a substitute for an independently verified offline backup.

---

## 24. Bitcoin receive, balance, spend and confirmation

**Bitcoin receive (menu 11)** displays the BTC mainnet native SegWit `bc1...` address derived from the encrypted vault using **BIP84 path `m/84'/0'/0'/0/0`**. This is an **offline display**, not evidence that a payment arrived.

**Bitcoin balance (menu 12)** needs your own **running, sufficiently synchronized local Bitcoin Core node** and valid loopback RPC credentials. It scans currently unspent confirmed output(s) for **the single external index-0 address**. It does not show a complete wallet balance across arbitrary change/account indices, pending mempool transactions or every historical transaction.

**Spend BTC (menu 13; `spend-btc`)** unlocks the selected vault, derives and checks the Bitcoin identity, checks your local node/network, builds a transaction, validates recipient/fees/outputs, uses Bitcoin Core to **temporarily handle the private signing key via local RPC**, and broadcasts only after explicit authorization. This is **not hardware-wallet signing**. Keep Core RPC on loopback and the cookie secret; do not enable remote RPC or sensitive parameter logging.

For signet/testnet testing, the Bitcoin network choice must match a correctly configured local node. The code supports mainnet, signet and selected test-network RPC choices; the **saved mainnet receiving address is not your signet address**. Mainnet sends require the exact `MAINNET` confirmation. Do not test this feature with valuable funds until independent recovery and real-node transactions are fully verified.

**Status (menu 14)** checks the transaction ID using Bitcoin Core; “not found” is **not** proof of failed broadcast. Avoid retries that could duplicate sends when status is unknown.

**Legacy BTC menu 18** operates on a separately managed Bitcoin Core wallet and is different from the direct vault-backed menu 13. The source does not implement a general multi-address BIP84 wallet scanner, robust bump-fee/replacement support, or complete independent disaster-recovery verification.

---

## 25. EVM, ERC-20, Monero and supported coins

- **Read-only native EVM balance (menu 7):** queries a selected supported EVM account via a properly configured HTTPS RPC endpoint. A returned native balance is not a token balance, and no missing RPC balance should be treated as zero.
- **Direct encrypted-vault EVM send (menu 8) and ERC-20 (menu 9):** the code's direct supported source set is **ETH, ETC, BNB, POL and AVAX** (corresponding to Ethereum, Ethereum Classic, BNB Chain, Polygon PoS and Avalanche C-Chain). The creator's display codes (e.g. `BSC`, `POLYGON`, `AVAXC`) are internally mapped; not every listed network is directly spendable.
- **Transaction receipt (menu 10):** requires RPC data and displays observed confirmation depth. Execution success is not guaranteed finality.
- **Separate V3 keystore modes (16/17):** legacy EVM/ ERC-20 paths with a separate encrypted key store and their own network configuration. Do not confuse with vault-backed modes.
- **Monero (15):** delegates to an independently configured local `monero-wallet-rpc` wallet and its daemon. It does not directly spend XMR from the creator's encrypted VaultForge `.vault` file.
- **Additional addresses:** LTC, DOGE, BCH, XRP, SOL and the other displayed formats do not have comprehensive, independently verified sending, recovery and confirmation engines in this release.

For ERC-20, independently verify **chain ID, contract address, token decimals/symbol, recipient, amount and fees**; a display symbol alone is not a reliable contract identity. Optimism, Base, Arbitrum and other L2 fee accounting remains incomplete in the direct vault-send path; unsupported paths fail closed rather than guessing costs. All transaction paths are experimental and require actual chain/RPC validation before real use.

---

## 26. Security Center, passwords and new seed phrases

Choose **main menu 20 — Security Center**:

| Submenu | Action | Critical distinction |
|---|---|---|
| 1 | Tor-required vs direct network privacy | Routing policy, not guaranteed anonymity |
| 2 | Generate a new encrypted wallet with fresh seeds | **New addresses; funds are NOT moved** |
| 3 | Audit encrypted-vault permissions | On Linux can harden owner-only file/dir modes; on Windows inspect ACLs separately |
| 4 | Change existing vault encryption password | **Same seeds/addresses**, no funds moved |
| 5 | Verify paper recovery backup | Sample check, not an independent restore |
| 0 | Back | Return to main menu |

**Seed rotation does not “refresh” an existing address.** New recovery phrases control a new wallet. Old funds remain spendable only via the **old** wallet until deliberately moved. Preserve the old vault and paper backup during migration, including for pending payments. Vault password rotation and chat password rotation affect **different** encrypted objects.

Never store a recovery phrase in chat, cloud backups, screenshots, email or logs. Use full-disk encryption, restricted local permissions, trusted software and offline independently tested recovery. VaultForge's cryptography and transaction flows have **not** undergone an independent security audit.

---

## 27. Firewall and port reference

| Protocol/port | Where | Use | Exposure guidance |
|---|---|---|---|
| TCP **22** | AWS EC2 | SSH administrative login | Restrict to trusted administrator IPs |
| TCP **6667** | Public relay | Default WAN VaultForge mesh peer listener | Initially restrict test clients; public opening needs hardening |
| TCP **7777** | LAN/local node | Typical local mesh listener | LAN only unless deliberately hosting WAN |
| TCP **7778** | LAN scanner mode | Local scan-and-connect listener | LAN only |
| UDP **48877** | LAN peers | Opt-in signed LAN discovery | Same local network; do not expose to public internet |
| TCP **9050** | Local machine | Typical Tor SOCKS5 proxy | Loopback only |
| TCP **9150** | Local machine | Common Tor Browser SOCKS port | Loopback only |
| Local Bitcoin Core RPC | Local machine | Bitcoin Core wallet/full-node interaction | **Loopback only**, do not open to WAN |

**Example AWS security-group rules:** SSH TCP 22 from trusted administrator IP `/32`; relay TCP 6667 from trusted test client `/32` (or `0.0.0.0/0` **only after** deliberate public exposure/hardening). Firewall rules are separate from process listeners: opening a port in AWS doesn't start the relay, and a local `ss` listener doesn't prove it is accessible from outside AWS.

Public service test from Windows:

```powershell
Invoke-RestMethod https://checkip.amazonaws.com
Test-NetConnection 18.188.145.207 -Port 6667
```

A Windows `SourceAddress` like `10.x.x.x` is **private** and is not necessarily the public address AWS sees. If firewall rules restrict `/32`, they must match the **current** public client IP. When the relay is configured for all clients, `0.0.0.0/0` means all IPv4 sources, not all IPv6 addresses. Remember that an unrestricted public IRC-style listener attracts unsolicited traffic.

---

## 28. Troubleshooting: installation, AWS, presence and transfers

### 28.1 Linux `Python 3.14`, `coincurve`, `cffi` or `Expected exactly one LICENSE file`

You are probably running an old creator installer or unsupported interpreter. Use the **v2.7.2 `Linux/install_linux.sh`**, which selects **Python 3.12** and installs `coincurve==20.0.0` in an isolated environment. Do not manually run the old `crypto/creator/VaultForge_30_Coin_Wallet` installer or install with system Python 3.14.

### 28.2 Installer shows `unittest: Start directory is not importable: 'tests'`

You extracted or invoked the wrong/incomplete package or the `tests/` folder is missing/inaccessible. Verify you're in `Linux/` or `Windows/`, not the root of an old `crypto/` folder. The full client release includes a platform-local `tests/` directory. The **Relay_Only** package intentionally omits wallet test folders and uses its own installer.

### 28.3 `uv` download hangs or `--break-system-packages` requested

Use the new bounded installer without sudo. Check outbound HTTPS, DNS, VPN/proxy, storage and certificates; use an already installed working Python 3.12 if appropriate. **Never add `--break-system-packages` as a workaround for a broken isolated virtual environment.**

### 28.4 `Permission denied` when saving `.vault`

Select a writable personal or external directory. VaultForge tests destination writability before creating recovery material. On Linux check user ownership of the chosen folder; on Windows check folder ACLs/Controlled Folder Access. Do not disable security protections or run the wallet as administrator to hide the cause.

### 28.5 `Unable to unlock`, incorrect password, or no recovery phrase shown

Choose the correct **vault filename**, not a different older `.vault`. Enter the **vault encryption password**, not the BIP39 extra passphrase. Reveal requires exactly `REVEAL`; a `yes` response skips display. The app cannot defeat AES encryption if the password is genuinely wrong or the vault is damaged. Do not delete old vaults before verifying a restore.

### 28.6 AWS `Unit has a bad unit file setting`

Validate the systemd unit:

```bash
sudo systemd-analyze verify /etc/systemd/system/vaultforge-mesh.service
sudo systemctl status vaultforge-mesh --no-pager
sudo journalctl -u vaultforge-mesh -n 50 --no-pager
```

A prior service-generator version incorrectly quoted `WorkingDirectory`; use the **v2.6.1 systemd service hotfix** or a corrected unit rather than discarding node credentials. Before enabling or restarting, verify the unit and read errors. **Never delete `~/VaultForge/mesh_chat` to troubleshoot systemd.**

### 28.7 `Address already in use`, port conflict, or `[Errno 111] Connect call failed`

A service and an interactive relay may be attempting to listen on **the same port**. On AWS:

```bash
sudo systemctl status vaultforge-mesh --no-pager
sudo ss -lntp | grep ':6667'
```

Check the **actual active** service source via `sudo systemctl cat vaultforge-mesh`. `Connection refused` usually indicates no reachable listener at the target address/port or explicit rejection; it does **not** mean bad chat credentials. Start/repair the service before reinstalling the client.

### 28.8 Windows `TcpTestSucceeded: False` but relay works locally

Check: EC2 public IP still current; **correct attached security group**; inbound TCP 6667; correct client public `/32` if restricted; EC2 subnet internet-gateway route; network ACL return traffic; host firewall and local network/ISP filters. A failed ICMP ping is not itself proof of a broken TCP relay. On AWS, capture the attempted connection:

```bash
sudo timeout 40 tcpdump -ni ens5 'tcp port 6667'
```

Run `Test-NetConnection PUBLIC_IP -Port 6667` from Windows **while capturing**. Zero packets means the attempt was blocked/misrouted before reaching that interface. If TCP 22 works but 6667 fails, narrow the security group, network ACL and port-filtering hypotheses. Do **not** jump straight to exposing SSH publicly or changing the application protocol.

### 28.9 TCP works but `/peers` remains empty

TCP reachability is only the first layer. Confirm the chat's **authenticated encrypted handshake** completes and the peer's pinned fingerprint is expected. Distinguish `[CONNECTING]` from `[CONNECTED]`. A moved/reinstalled relay may have a different identity; independently verify a new fingerprint before unpinning.

### 28.10 Login error `Unknown local chat account or incorrect password`

Each device maintains **its own local account store**. Register with account menu **1** on a new device, or use an existing **local** user/password on that device. Signing into AWS's chat identity does not register the same login on Windows. A chat password and `.vault` password are unrelated.

### 28.11 Only yourself appears online

Confirm the remote relay is actually in `/peers`, then ask a second client to connect to the **same reachable mesh** and type `/users`. Identity announcements are exchanged after connections and expire when peers become stale. Users worldwide who have not connected into the same mesh are **not** listed. If the relay is older, install the v2.7.1 roster fix. A server-only process is not a global account directory.

### 28.12 `Recipient not found or nickname ambiguous`

Check `/users`, use the **full current `nickname@ID`**, do not DM yourself, and make sure the recipient is online and reachable. For a public channel, **type plain text** after `/join #room`; do not put your own identity into `/msg` or `/upload`. Use `/uploadroom #room PATH` for eligible room members.

### 28.13 `/scan` finds nobody on LAN

Enable host `--lan` or menu 21 → 7; both machines must have an actual reachable LAN. Permit UDP 48877 and the chosen TCP listener in their host firewalls. Broadcast discovery can be blocked by Wi-Fi guest isolation, subnet boundaries or VPNs. Try manually `/connect LAN_IP:PORT` instead; nothing in this release scans arbitrary external IPs.

### 28.14 `/public` or public scan returns zero nodes

The bootstrap must be online and authenticate, and hosts must **explicitly publish** their endpoints with `--advertise` while connected to the directory mesh. Neither a port forward nor `0.0.0.0:6667` automatically registers a node. Advertised nodes can be stale or unreachable; review fingerprints before connecting.

### 28.15 Missing room messages/history after join

Use `/join #room`, then `/history #room`. The relay must be v2.7-history-capable and connected, the message must fall within the stored retention window, and the message must be a **public-room** message. Historical messages from before the history feature was installed cannot be reconstructed.

### 28.16 Attachment offer fails or file won't save

Verify recipient is online with `/users`; use `nickname@ID`; ensure file is 1 byte–4 MiB, or a folder with up to 100 files/8 MiB input that compresses under 4 MiB. For room sharing limit to eight online recipients. Receiver must wait for complete arrival and run `/files` then `/accept TRANSFER_ID`. Received ZIPs require manual safe inspection/extraction. There is no offline delivery guarantee.

### 28.17 Tor required, but proxy unavailable

Start/configure Tor separately and verify the appropriate local SOCKS5 port. The client **fails closed** if Tor mode is required and the proxy cannot be used; it should not silently route WAN traffic directly. `--tor` and `--offline` cannot be combined. No Tor configuration or application setting alone proves anonymity.

### 28.18 Recover chat when AWS credits end

The AWS instance may stop when credits expire. Peers can still connect to another trusted public bootstrap or a self-hosted relay (if it is reachable) or use offline LAN mode. Save alternative endpoints **before** losing AWS, because there is no guaranteed global DHT and a new client cannot discover the global network from nothing.

---

## 29. Maintenance, backup, upgrades and removal

### What to back up (privately)

| Data | Why it matters | Where it normally lives |
|---|---|---|
| `.vault` files | Encrypted wallet data | `~/VaultForge/wallets/` |
| Recovery phrase **and** optional BIP39 passphrase | Independent wallet recovery | Offline paper/metal, **not** a network service |
| Chat identity `accounts.json` | Existing chat identity keys (encrypted) | `~/VaultForge/mesh_chat/` |
| Trusted pins / node config | Stable peer verification and node configuration | `~/VaultForge/mesh_chat/` |
| `node.secret` | Background node login secret | Same chat directory, owner-only, **never published** |
| Public channel history | Optional service data | Mesh chat data; privacy-sensitive/plaintext on relay |

Back up data while software is stopped as appropriate, use encrypted storage, and ensure permissions/backup access are restricted. Test that you can independently restore a wallet on a separate safe machine before any real funds. Never commit chat credentials, node secret, wallet files, transaction private material or SSH keys to GitHub or package ZIPs.

### Safe update sequence for an established public relay

1. Note current fingerprint, service source directory and public endpoint.
2. Make a secure local backup of identity/config/history.
3. Update **only the relay code** with its matching patch (no fresh setup).
4. Restart `vaultforge-mesh.service`; verify active status, listener and local handshake.
5. Test from an external updated client, including `/users`, `/history` and actual room messages.
6. Then update Windows/Linux clients. Old clients may continue basic chat but not newer features.

### Safely remove the application

Stop any background node or systemd service first. Removing extracted application code or `.venv` generally does **not** delete wallet/chat files under your home directory. Treat those as sensitive data requiring deliberate separate backup/removal, not routine cleanup. If removing an AWS node, disable its service before deleting source files; otherwise systemd may repeatedly attempt to restart missing code.

### Monitoring and abuse protection

Public nodes should have resource limits, rate limits, authentication monitoring, log rotation, patch management, firewall restrictions, budget alarms and incident response procedures. This release has some basic protocol limits and authentication, but **does not** ship a complete public-service abuse or DDoS protection system. Logs can contain chat metadata: restrict access and use a privacy-conscious retention policy.

---

## 30. Architecture, security boundaries and limitations

```text
Windows CLI / Linux CLI
        │
        ├── Wallet process: encrypted .vault, local signing flows
        │   └── LOCAL Bitcoin Core / Monero wallet-RPC / selected EVM RPC
        │
        └── Separate mesh-chat child process
              ├── Local encrypted chat identity
              ├── Authenticated encrypted peer links
              ├── Per-recipient encrypted DMs and file offers
              ├── Per-link-encrypted public rooms + limited shared history
              ├── LAN scan (UDP 48877) / offline LAN
              └── Optional reachable AWS/laptop/other peer relay (TCP 6667)
                        └── Opt-in signed public-node announcement exchange
```

**Cryptographic trust:** The protocol uses local cryptographic identities, signatures, encrypted transports and recipient-encrypted direct content. These have been exercised in local test environments but **not independently audited**. The relay operator can read public-room content and stored room history; E2EE DMs/files do not hide every sender/recipient/traffic metadata field. TOFU pins require independent verification. Direct connections reveal network endpoints unless separately anonymized.

**Peer discovery:** there is no universal global scanner, DHT, automatic NAT traversal, centralized synchronized login directory, guaranteed presence accuracy or offline message queue. A WAN mesh can consist of multiple servers/users without one mandatory host **only when reachable peer paths already exist**. Public signing/advertising is voluntary and does not constitute a reputation or identity system.

**Wallet production readiness:** 30 address formats do not equal 30 supported sending networks. Bitcoin mainnet send/receive, testnet recovery, EVM/Monero transfers and provider settlements still require real-node end-to-end evidence and independent verification. This project has not completed its required external security audit, penetration test, verified release-signing/update gates, cross-platform installer testing, disaster recovery drills, or all applicable legal/provider signoffs. **Do not use it to custody significant cryptocurrency.**

**Installer reliability:** Python 3.12 bootstrap and packaging have automated checks, but each host platform may still have unverified environmental problems (downloads, proxy, permission, antivirus, service unit, network ports). Test the *actual* Windows and Ubuntu deployments before declaring them production-ready.

---

## 31. Validation checklist

Use this checklist after installing or upgrading a client and relay:

- [ ] Full archive extracted, using the correct Windows or Linux folder.
- [ ] Python **3.12** selected and dependencies installed **inside** `.venv`.
- [ ] `--diagnostics` runs; wallet self-test is attempted with installed crypto libraries.
- [ ] Wallet files remain **off the AWS/public relay**; recovery phrase backed up offline.
- [ ] Relay's original cryptographic fingerprint and node secret preserved during upgrade.
- [ ] On AWS: `systemctl is-active vaultforge-mesh` reports `active`.
- [ ] On AWS: `ss` shows intended TCP listener `0.0.0.0:6667`.
- [ ] From Windows: `Test-NetConnection PUBLIC_IP -Port 6667` succeeds.
- [ ] Chat reports `[CONNECTED]`, not merely `[CONNECTING]`.
- [ ] `/peers` includes the expected verified relay fingerprint.
- [ ] `/users` shows at least **two distinct connected test users**.
- [ ] `/join #general` followed by a test message works across two clients.
- [ ] `/msg OTHER_NICK@ID ...` reaches only the intended user.
- [ ] `/upload OTHER_NICK@ID small.txt`, `/files`, `/accept ID` succeeds.
- [ ] `/uploadroom #general PATH` offers separately to eligible room members.
- [ ] `/history #general` reloads a recently stored message after reconnect (updated relay only).
- [ ] LAN scan tested separately on a LAN with no internet; offline mode rejects public peers.
- [ ] Public-node scan tested only against a reachable bootstrap; each advertised identity reviewed.
- [ ] Tor-required mode tested for **fail-closed** behavior when SOCKS5 is absent.
- [ ] Security group keeps TCP 22 restricted to administration; public port exposure is deliberate.
- [ ] Node survives SSH disconnect and restarts after a controlled EC2 reboot (systemd service).
- [ ] No real funds used before independent seed recovery, chain-level tests and outside audits.

### Help and bug-report template

Provide the **exact application version**, operating system, whether you run Windows CLI/Linux CLI/Relay_Only, which menu item/command failed, and redacted output of the relevant diagnostics. On AWS include:

```bash
sudo systemctl status vaultforge-mesh --no-pager
sudo ss -lntp | grep ':6667'
sudo journalctl -u vaultforge-mesh -n 40 --no-pager
```

On Windows include the result of:

```powershell
Test-NetConnection YOUR_RELAY_PUBLIC_IP -Port YOUR_RELAY_PORT
```

**Never share:** recovery phrases, BIP39 passphrases, `.vault` contents, chat passwords, `accounts.json`, `node.secret`, Bitcoin Core cookie/WIF/RPC password, EC2 SSH private key or unredacted authentication logs. A public peer IP can also be sensitive; redact endpoints when sharing troubleshooting reports publicly.

---

**Version notes:** This manual is for the **v2.7.1 CLI snapshot** supplied here. It replaces the stale v2.6.0/v2.7.0 README descriptions; it does not alter the application, encryption format, wallet data or wire protocol. The default AWS endpoint `18.188.145.207:6667` is **configuration guidance, not a guarantee that the server is currently online**.


---

## Appendix A — New CLI mesh controls in v2.7.2

The v2.7.2 CLI includes all wallet functions, encrypted chat, node hosting, file/folder
transfers, public room history, LAN discovery, Tor settings and complete platform
installers from v2.7.1. It adds **client-side usability and presence controls**:

| Location | Command / option | Function |
| --- | --- | --- |
| Main menu > 21 | `1` | Enter your AWS host and sign in; connection starts immediately after local login |
| Main menu > 21 | `18` | Sign in and auto-connect to the AWS endpoint you have previously approved |
| Main menu > 21 | `19` | Save/change your auto-connect preference and peer endpoint (opt-in) |
| Chat console | `/users` | Show your own account separately from other authenticated online users |
| Chat console | `/online` or `/remote` | Only remote authenticated identities with fresh presence |
| Chat console | `/refresh` | Request refreshed signed roster through already-connected peers |
| Chat console | `/status` | Display encrypted links, retry state, and count of remote users |
| Chat console | `/reconnect` | Immediately try reconnecting to manually approved endpoints |
| Chat console | `/connect HOST:PORT` | Join a peer and remember the explicit endpoint for bounded reconnects |

### AWS autoconnect, first use

1. Open the correct `Windows` or `Linux` folder and run its installer and launcher.
2. Select **21 — Mesh Chat**, then **19 — Configure saved AWS auto-connect**.
3. Use `18.188.145.207:6667` or your own reachable trusted node. Confirm **y**.
4. Select **18 — Chat login + auto-connect**, and register/log in to your **local** chat identity.
5. On a successful authenticated connection, type `/status`, `/online`, and `/refresh`.
6. On future sessions, choose menu 18 to use the saved endpoint without retyping it.

The preference file is `~/VaultForge/mesh_chat/client_preferences.json` on Linux
or the corresponding `VaultForge\mesh_chat\client_preferences.json` directory under the
Windows user profile. **It stores only the approved node endpoint and on/off flag**,
not chat passwords or cryptocurrency secrets. It is not a global user database.

### Compatibility and security

- The roster-refresh operation uses the existing v2.7.1 *authenticated introduction*
  and *signed presence* frames; there are no new unrecognized wire-frame types.
  The unchanged AWS v2.7.1 relay is compatible with this CLI; no server update is
  necessary solely to use these CLI options.
- Refreshed entries are only identities with valid, recent signed announcements
  within the reachable mesh. A user disconnected from every reachable peer is not
  displayed. A cached user database is **not** a live online roster.
- Refresh is limited to once every five seconds; duplicate signed gossip messages
  remain rejected. Old signatures cannot be replayed to manufacture online users.
- Peer reconnections retry approved endpoints using a bounded, increasing delay
  (up to five minutes). `/reconnect` can trigger a new attempt immediately.
- `--offline` and `--no-auto-connect` disable automatic network reconnect; Tor
  settings remain fail-closed as implemented in the existing transport layer.
- This software and its encryption protocol remain experimental and unaudited.
  A localhost test does not verify your live AWS, ISP, or Windows firewall setup.

### If you still only see your own account

Run `/status`. If it shows **0 direct encrypted links**, the application is not
connected to AWS, regardless of successful local login. Check the actual EC2 public
IPv4, saved inbound TCP 6667 security-group rule, systemd service, and `ss -lntp`
listener, then `/reconnect`. When linked, run `/refresh` and `/online`. The relay
may be alone, or other users may be offline; an empty remote list is possible.

**Keep the chat process separate from wallet keys.** Never copy encrypted wallet
vaults, recovery phrases, or secrets to AWS to enable chat.


## Data directory creation — v2.7.3 fix

Both Linux installers now create private folders **before installing Python**. Run as your normal Linux account, never with `sudo bash`:

```bash
./install_linux.sh       # complete Linux wallet + mesh CLI
# or, from Linux/Relay_Only/
./install.sh             # relay-only, no wallet dependencies
./AWS_QUICK_SETUP.sh YOUR_PUBLIC_IP:6667   # fresh AWS relay setup
```

The full Linux CLI creates `~/VaultForge/`, `~/VaultForge/mesh_chat/`, `~/VaultForge/mesh_chat/downloads/` and `~/VaultForge/wallets/`. The relay-only installer creates the same mesh folders **without** a wallets folder. All directories are owner-private (0700). Data is under the Unix account running the installer; `sudo bash start_linux.sh` erroneously creates root-owned `/root/VaultForge` data and is unsupported.

**Directories are not identities.** Merely creating folders does not create `node.json`, `node.secret` or `accounts.json`. A genuinely fresh relay setup explicitly creates identity files via `node_manager.py setup`; if old accounts/keys exist but `node.json` is missing, setup stops rather than silently replacing cryptographic identity. Recover the old identity first. The previously missing AWS `~/IRC/Relay_Only` source/venv requires a separate runtime restore; making these data folders alone will not start a damaged systemd service.

You can manually prepare the directories without installing anything:

```bash
./PREPARE_DATA_DIRS.sh client     # from Linux/
./PREPARE_DATA_DIRS.sh relay      # from Linux/Relay_Only/
```


## Automatic detection of changed relay fingerprints

See [FINGERPRINT_ROTATION.md](../FINGERPRINT_ROTATION.md) for safe verification and one-endpoint trust update. A changed fingerprint is detected automatically but NEVER automatically trusted.
