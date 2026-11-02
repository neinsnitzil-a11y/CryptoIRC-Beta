> **NETWORK UPDATE 2.8.0 (November 2026):** The new default relay is `18.227.91.173:6667`. The previous `18.188.145.207:6667` and user-hosted relays remain selectable. See [MULTI_RELAY_UPGRADE_2_8_0.md](MULTI_RELAY_UPGRADE_2_8_0.md) for saved hosts, live peer indicators, new trust workflow, and limits. This package is updated source, not a verified deployment.

# CRYPTO NOCTURNE — Complete Desktop Application & Source Manual

> **Windows desktop GUI • Encrypted cryptocurrency vaults • Multi-chain account tools • Fiat and payment prototypes • Trading Terminal • VaultForge encrypted mesh • Release and security operations**
>
> **Documentation edition:** October 31, 2026  
> **Source examined:** `CRYPTO_NOCTURNE_v4.5.2_Mesh_2.7.3_Trust_Repair_FULL_SOURCE.zip` (original project layout preserved)  
> **Build identity:** `4.5.1` is still hard-coded in `src/build_release.py` and `src/installer.iss`. Some source folders and later mesh modules carry newer release labels. Do not interpret a folder name as a compiled or audited release version.  
> **Distribution:** Source only; no precompiled Windows binary is supplied by this source package.

**IMPORTANT — EXPERIMENTAL FINANCIAL AND NETWORKING SOFTWARE.** This repository contains real code and local tests, but it is **not independently audited, not a licensed brokerage or payment service, and not approved for production custody, settlement, or significant-value transactions**. The trading terminal supports **paper orders only**. Its custom mesh protocol is **not standard IRC**. Several blockchain features are read-only, depend on external nodes, or are prototypes. Do not confuse an available screen, a passed unit test, an address generated, or a compiled EXE with verified real-money functionality.

---

## Contents

1. [What CRYPTO NOCTURNE is](#1-what-crypto-nocturne-is)
2. [Read this before using funds](#2-read-this-before-using-funds)
3. [Feature status at a glance](#3-feature-status-at-a-glance)
4. [Source directory layout](#4-source-directory-layout)
5. [Hardware, software and prerequisites](#5-hardware-software-and-prerequisites)
6. [Windows: fresh source installation](#6-windows-fresh-source-installation)
7. [Windows: build the application EXE](#7-windows-build-the-application-exe)
8. [Windows: build the installer and portable package](#8-windows-build-the-installer-and-portable-package)
9. [Linux: development/source launch](#9-linux-developmentsource-launch)
10. [Navigation and workspace map](#10-navigation-and-workspace-map)
11. [Creating an encrypted wallet](#11-creating-an-encrypted-wallet)
12. [Opening, viewing and backing up vaults](#12-opening-viewing-and-backing-up-vaults)
13. [Supported address formats versus real transaction support](#13-supported-address-formats-versus-real-transaction-support)
14. [Unified wallets and signer backends](#14-unified-wallets-and-signer-backends)
15. [Bitcoin: receiving, balances, and spending](#15-bitcoin-receiving-balances-and-spending)
16. [EVM chains and ERC-20 transfers](#16-evm-chains-and-erc-20-transfers)
17. [Monero integration](#17-monero-integration)
18. [Other chains, tokens and chain expansion](#18-other-chains-tokens-and-chain-expansion)
19. [Portfolio, monitoring and accounting](#19-portfolio-monitoring-and-accounting)
20. [Money Hub, fiat and payment features](#20-money-hub-fiat-and-payment-features)
21. [Trading Terminal: charting and paper orders](#21-trading-terminal-charting-and-paper-orders)
22. [Alpaca market-data setup](#22-alpaca-market-data-setup)
23. [Optional centralized market-data server](#23-optional-centralized-market-data-server)
24. [VaultForge Mesh: concepts and security](#24-vaultforge-mesh-concepts-and-security)
25. [Mesh registration and connecting to a relay](#25-mesh-registration-and-connecting-to-a-relay)
26. [Rooms, online users, messages and transfers](#26-rooms-online-users-messages-and-transfers)
27. [Identity trust, changes and recovery](#27-identity-trust-changes-and-recovery)
28. [Hosting your own mesh node](#28-hosting-your-own-mesh-node)
29. [AWS, VPS and dedicated relay deployment](#29-aws-vps-and-dedicated-relay-deployment)
30. [Offline LAN and Tor-required networking](#30-offline-lan-and-tor-required-networking)
31. [Files, storage, secrets and backups](#31-files-storage-secrets-and-backups)
32. [Security, privacy and threat model](#32-security-privacy-and-threat-model)
33. [QA, compliance, operations and release centers](#33-qa-compliance-operations-and-release-centers)
34. [Test and verification commands](#34-test-and-verification-commands)
35. [Build signing and staged update verification](#35-build-signing-and-staged-update-verification)
36. [Common Windows and Linux errors](#36-common-windows-and-linux-errors)
37. [Mesh troubleshooting, including AWS failures](#37-mesh-troubleshooting-including-aws-failures)
38. [Trading and provider troubleshooting](#38-trading-and-provider-troubleshooting)
39. [Backups, restoration and incident handling](#39-backups-restoration-and-incident-handling)
40. [Developers: source modules and extension rules](#40-developers-source-modules-and-extension-rules)
41. [Publishing the source on GitHub](#41-publishing-the-source-on-github)
42. [Production-readiness gates and roadmap](#42-production-readiness-gates-and-roadmap)
43. [FAQ, glossary and reference guides](#43-faq-glossary-and-reference-guides)

---

## 1. What CRYPTO NOCTURNE is

CRYPTO NOCTURNE is a native Python/Tkinter desktop project combining local wallet management, supported-chain readers/signers, fiat/payment *development workflows*, a technical-analysis and paper-trading interface, and experimental encrypted P2P communications. It uses a distinctive black/purple/green UI and a scrollable sidebar that organizes screens by work area. Its long-term goal is a unified wallet, banking, market and networking workstation, but not every advertised system is completed or approved for live money.

There are **three different things** developers must not confuse:

- **CRYPTO NOCTURNE application:** the Windows-oriented desktop interface built from `src/crypto.py` and related modules; `BUILD_WINDOWS.bat` is the Windows compiler GUI entry point.
- **VaultForge mesh engine bundled with the GUI:** `src/vaultmesh/` plus the subprocess bridge and GUI; it creates independent chat identities, connects to other nodes, and can configure local background nodes. It is *not* a stock market feed and not a wallet seed-sharing mechanism.
- **Separate dedicated mesh/market servers:** a headless VaultForge IRC-style relay and an optional HTTPS market-data server can run elsewhere. Installing a desktop client does not automatically deploy or configure an AWS EC2 service.

The application is not MetaTrader, TradingView, a traditional IRC server, or a production cryptocurrency exchange. Similar visual concepts do not imply compatibility with those products.

## 2. Read this before using funds

**Do not fund a wallet or authorize a real mainnet transaction based only on this README.** Verify independently that you can restore the seed, derive the identical address, control the signing backend, construct and inspect a transaction, send on a safe test network, track confirmations, and recover from interruption or chain reorganization. Even if the interface exposes a mainnet option, its presence does not prove those tests passed.

Never publish or share: mnemonic seed phrases, private keys, `.vault` files, keystore JSON, account databases, RPC cookies, chat identity secrets, OAuth refresh tokens, payment credentials, signing certificates or private market-data API keys. Do not put them into screenshots, issue reports, public ZIPs, or a GitHub repository.

A locally generated public address is *not* proof that the corresponding wallet can spend. A balance check is *not* proof that funds are recoverable. Paper trading results are *not* real investments. A signed public-node directory entry is *not* proof that its advertised operator is trustworthy.

## 3. Feature status at a glance

| Area | In this source | Critical qualification |
|---|---|---|
| Native desktop GUI | Yes | Windows-oriented; Linux source launch is developmental |
| Encrypted vault creation, unlock and recovery UI | Yes | Independent backup/recovery evidence still required |
| Multiple cryptocurrency address formats | Yes | Address generation ≠ universal send/receive support |
| Unified Wallets account registry | Yes | Registry can include watch-only public data and external signers |
| Bitcoin Core integration | Yes | Own fully synchronized/owned Core wallet and RPC required |
| EVM/ERC-20 backend and workflow | Yes | RPC/network/gas/nonce and real-chain safety must be validated |
| Monero wallet RPC integration | Yes | External wallet RPC, node synchronization and stagenet tests needed |
| Chain Expansion/Token Center | Yes | Network-specific functionality differs; see screen warnings |
| Fiat ledger, funding and banking rails | Prototypes, adapters and UI | Do not represent as actual bank custody or settled payments |
| Stock and crypto charts | Yes | Simulated demo or entitled provider data; not all feeds/markets |
| EMA, RSI, volume, watchlist | Yes | Current preview does not include full pro screening/options tools |
| Paper Buy/Sell and order history | Yes | No actual broker or exchange order execution |
| Central market-data client | Yes | Separate HTTPS backend and lawful data rights are required |
| VaultForge Mesh rooms, DMs and files | Yes | Experimental, unaudited custom protocol; server must be reachable |
| LAN discovery, public directory, Tor-required mode | Yes | Different modes require the stated connectivity prerequisites |
| Background user-hosted mesh node | Yes | Service/port/firewall/identity setup remains host-specific |
| Release, QA, security and compliance screens | Yes | Local checks do not substitute for third-party signoffs |
| Windows PyInstaller EXE / Inno Setup | Build source included | Actual build must run on Windows; output is not supplied here |
| Signed updates | Offline verification/staging workflow | No automatically deployed trusted production update channel |

**Version note:** the original archive is identified as v4.5.2/Mesh 2.7.3 in distribution names, but the Windows builder and installer still use `4.5.1`. This README records that inconsistency instead of changing executable metadata or claiming a new binary release.

## 4. Source directory layout

The **original layout is retained**. Do not move `src`, `brand_assets`, `data`, the spec file or Inno script independently and expect packaging to work.

```text
CRYPTO_NOCTURNE_v4.5.2_Mesh_v2.7.2_Source/
├── README.md                         ← this complete guide
├── BUILD_WINDOWS.bat                 ← graphical EXE builder
├── START_WINDOWS.bat                 ← Windows source/runtime launcher
├── start_linux.sh                    ← Linux source launcher
├── CONFIGURE_MARKET_SERVICE.py       ← publisher HTTPS URL configuration
├── MESH_NETWORK_GUIDE.md
├── MESH_UPDATE_2.7.1.md
├── GUI_RELAY_TRUST_UPDATE.md
├── TRADING_TERMINAL.md
├── CENTRAL_MARKET_SERVER.md
└── src/
    ├── crypto.py                     ← native GUI and navigation
    ├── builder_gui.py                ← Windows compiler interface
    ├── build_release.py              ← preflight/tests/EXE/installer
    ├── CRYPTO_NOCTURNE.spec          ← PyInstaller configuration
    ├── installer.iss                 ← Inno Setup installer definition
    ├── requirements.txt
    ├── brand_assets/                 ← icons and UI artwork
    ├── data/                         ← BIP-39 words, fiat catalog, market URL
    ├── vaultmesh/                    ← VaultForge chat/node/network engine
    │   ├── mesh_chat.py
    │   ├── node_manager.py
    │   ├── chat_history.py
    │   ├── file_transfer.py
    │   └── security_center.py
    ├── mesh_bridge.py                ← GUI subprocess protocol
    ├── mesh_gui.py                   ← rooms, roster, DMs, transfer UI
    ├── market_terminal.py            ← feed, indicators, paper ledger
    ├── trading_terminal_ui.py        ← chart + trading interface
    ├── market_server_client.py       ← optional central HTTPS data client
    ├── unified_wallet.py / unified_wallet_ui.py
    ├── btc_phase1.py / btc_phase1_ui.py
    ├── evm_phase2.py / xmr_phase3.py
    ├── core/                         ← vaults, assets, transfer and protocols
    ├── financial_backend/            ← local/payment development backends
    ├── release_ops.py / release_ops_cli.py
    ├── qa_runner.py / qa_runtime.py
    └── tests/                        ← unit and offline integration tests
```

**Clarification:** Bitcoin GUI support is in `src/btc_phase1.py`, `src/core/transfer.py`, and related wallet modules. The standalone full VaultForge CLI is distributed separately and should not be inferred from this GUI directory alone.

## 5. Hardware, software and prerequisites

### Windows

- Windows 10/11, **64-bit**, with desktop GUI access.
- **Python 3.12 x64**, preferably from the official installer. Ensure the Python launcher `py -3.12` works; `BUILD_WINDOWS.bat` verifies version and architecture.
- Internet access for the *initial* `pip` installation of the pinned project requirements and PyInstaller.
- **Inno Setup 6** to create a Windows setup EXE; the portable/one-folder EXE build uses PyInstaller.
- Windows SDK **SignTool** plus a legitimate certificate *only if* you plan to sign builds; signing is not automatically configured.
- Optional: Bitcoin Core, Monero wallet RPC, Tor, an EVM RPC provider, or an entitled market-data account depending on the feature in use.

Python dependencies are pinned in `src/requirements.txt`, including `bip-utils`, `cryptography`, `argon2-cffi`, `web3`, `requests`, `qrcode[pil]`, `PySocks`, and `websockets`. PyInstaller is installed by the builder separately. Do not assume other Python installations or a system-wide package set are compatible.

### Linux

The project offers `start_linux.sh` as a *source-run* path. It expects `python3`, `python3-venv`, GUI Tkinter support and installation of dependencies from `src/requirements.txt`. This is not a certified Linux installer; Python version, wheels, display server, and native libraries may vary by distro.

### Separate server dependencies

A dedicated mesh server does **not** need the complete financial GUI or wallet modules. Use a relay-only source bundle and a separate restricted account; configure firewall and service manager for the chosen OS. A centralized market server is another independent process with its own provider credentials and HTTPS reverse proxy. Do not combine them merely because they can run on the same EC2 instance.

## 6. Windows: fresh source installation

1. Download the **full original source** ZIP or the source archive with this updated README. Extract it completely to a user-writable directory, such as `C:\Development\CRYPTO_NOCTURNE`. Avoid nesting partially extracted patches inside the wrong root.
2. Install **Python 3.12 x64**. In PowerShell, check:

   ```powershell
   py -3.12 --version
   py -3.12 -c "import struct; print(struct.calcsize('P')*8)"
   ```

   Expected: Python **3.12** and `64` bits.
3. Double-click **`START_WINDOWS.bat`** in the folder containing `src`. The script creates/reuses `%LOCALAPPDATA%\CRYPTO_NOCTURNE\runtime-v2.3` and installs pinned source dependencies. It does not require you to globally install every library.
4. The desktop should open. Use **Dashboard** first, then visit individual screens. Local workspace contents will vary by feature, and older data may remain in your existing profile.
5. Do not import real wallet keys until you have independently validated the build and recovery procedures.

A first-run dependency download may require an internet connection. If the batch window closes, run it inside Command Prompt so the error stays visible:

```bat
cd /d C:\Development\CRYPTO_NOCTURNE
START_WINDOWS.bat
```

**Do not run an untrusted source release as Administrator.** The installer is designed for per-user installation and user-owned files.

## 7. Windows: build the application EXE

From the same source root, double-click:

```bat
BUILD_WINDOWS.bat
```

This creates/reuses `%LOCALAPPDATA%\CRYPTO_NOCTURNE\builder-v2.3`, installs pinned application dependencies plus a supported PyInstaller 6 release, and opens the native graphical compiler. The available builder actions are:

| Button | Purpose |
|---|---|
| **01 PREFLIGHT** | Verify required source/asset files, dependencies and sensitive-file scan |
| **02 RUN TESTS** | Run source regression suite before release |
| **03 BUILD EXE** | Compile a Windows one-folder application; also invokes smoke/security checks |
| **04 BUILD INSTALLER** | Use an already-built EXE to create Inno Setup installer |
| **BUILD BOTH** | Build EXE, perform checks, then build installer |
| **PORTABLE EXE** | Run the portable-target build path; read its own output constraints |
| **RELEASE CHECKS** | Perform local Phase 18 release gate evaluation |

The compiler window also has **Open outputs**, **Save log**, and an optional **Launch Inno Setup installer after a successful build** checkbox.

Equivalent source commands, when invoked with the correct environment:

```powershell
py -3.12 src\build_release.py check
py -3.12 src\build_release.py test
py -3.12 src\build_release.py release-check
py -3.12 src\build_release.py exe
py -3.12 src\build_release.py full
```

These direct commands assume the interpreter already has the required packages; using `BUILD_WINDOWS.bat` is easier because it prepares the dedicated environment. **PyInstaller does not cross-compile a Windows EXE from Linux.**

The primary output is:

```text
dist/CRYPTO_NOCTURNE/CRYPTO_NOCTURNE.exe
```

The `_internal` folder and other bundled files must remain beside that executable; a one-folder PyInstaller application is **not** normally a standalone one-file EXE.

The build includes a frozen-wallet smoke check and scans build output for accidentally included private files. A passing smoke check is not an independent crypto audit.

## 8. Windows: build the installer and portable package

**Inno Setup:** Install Inno Setup 6 and run **BUILD BOTH**. `src/installer.iss` copies the *built onedir distribution*, not raw source files. The generated installer is expected at:

```text
release/CRYPTO_NOCTURNE_Setup_v4.5.1.exe
```

If Inno Setup is installed in a nonstandard location, configure `ISCC_PATH` to the absolute location of `ISCC.exe`, then rerun the builder. The source application version currently remains `4.5.1`; renaming a ZIP does not alter installer metadata.

The setup uses a per-user installation directory under `%LOCALAPPDATA%\Programs\CRYPTO NOCTURNE`, retains a stable application ID for upgrades, and intentionally does not remove user wallet data on uninstall. Actual upgrade, rollback, and uninstallation tests on disposable data remain necessary.

**Portable:** The builder has a separate `portable` action. Use the resulting package as described by its build output, and do not label it verified or signed merely because the file exists.

**Code signing:** If you hold a legitimate local certificate, the builder can use the SHA-1 certificate thumbprint from `CRYPTO_SIGN_CERT_SHA1` to sign and verify the EXE and installer. Without it, the release is explicitly **unsigned development**. No signing key or certificate should ever be shipped in the source ZIP.

## 9. Linux: development/source launch

On a desktop Linux installation with working Tk support, for example Ubuntu/Debian/Kali:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk
cd /path/to/CRYPTO_NOCTURNE_v4.5.2_Mesh_v2.7.2_Source
chmod +x start_linux.sh
./start_linux.sh
```

The script prepares a private runtime under `${XDG_DATA_HOME:-$HOME/.local/share}/crypto-nocturne/runtime-v2.3`, installs dependencies once and runs `src/crypto.py`. It **does not** build a Linux AppImage, Flatpak, distro package, or certified Linux desktop release.

If your distro ships incompatible Python packages or no matching wheels, use a supported isolated environment and record the exact error. Do **not** globally override Kali's externally managed Python (`--break-system-packages`) just to bypass installation problems. The desktop needs a graphical session; SSH without X forwarding or a display will not open Tk windows.

---

## 10. Navigation and workspace map

The GUI groups screens under the following **actual sidebar labels**. Availability of a page means that source/UI exists; it does *not* imply its external provider or blockchain connection works for a given user.

### Workspace

| Screen | Purpose and user flow |
|---|---|
| **Dashboard** | Landing page, general navigation, public overview and shortcuts |
| **Trading Terminal** | Stock/crypto candles, data mode, indicators, watchlist and **paper** Buy/Sell |
| **Money Hub** | Consolidated financial-experience entry; distinguish projected/demo values from verified accounts |
| **Portfolio** | Portfolio/account views and analytics using available records |
| **Unified Wallets** | Link public accounts and external signer backends; verify address, network and status |
| **Chain Expansion** | Supported additional-chain readers and account workflows |
| **Universal Transactions** | Transaction-related interfaces and validation workflows |
| **Token Center** | Token/network metadata and infrastructure UI |
| **Blockchain Health** | Read-only node/network health surfaces |
| **Asset Coverage** | Supported assets and limitations/status coverage |
| **BTC Phase 1** | Bitcoin Core and transaction-oriented development flow |
| **EVM Phase 2** | EVM native/ERC-20 development flow |
| **Monero Phase 3** | Wallet RPC-driven Monero development flow |
| **Live Crypto** | Price/data interfaces with source availability constraints |
| **Create Wallet** | Local encrypted vault creation and backup process |

### Accounts

| Screen | Purpose |
|---|---|
| **Fiat Accounts** | Local fiat/account prototype views, not a guaranteed real bank account |
| **Crypto Vault** | Navigate to encrypted crypto vault management |
| **Stablecoins** | Stablecoin-related data/views; chain and issuer support must be separately checked |
| **Wallets** | Select, unlock, inspect or manage existing vault files |
| **Fiat Ledger** | Local fiat-style ledger record operations |

### Money Movement

| Screen | Purpose |
|---|---|
| **Banking Rails** | Financial rails adapter, local gateway and authorization controls |
| **Phase 4 Funding** | Funding-order prototypes and integrations |
| **Wallet Funding** | Determine a funding target; require verified chain/address before transferring |
| **Receive** | Public receiving-address workflow |
| **Send** | Transaction preparation, checks and optional signing path, dependent on backend |
| **Transactions** | Transaction records/status and supported views |
| **Fiat Payments** | Fiat payment backend integration/workflow, not proof of settlement |
| **Currency Exchange** | Currency/rate or exchange interfaces; do not assume licensed execution |

### Network / P2P

| Screen | Purpose |
|---|---|
| **Mesh Network** | VaultForge-compatible encrypted network, AWS peers, signed roster, rooms, DMs, transfers |
| **Peer to Peer** | Separate P2P development interface |
| **IRC LAN Chat** | LAN-oriented chat interface |
| **Internet Chat** | Routes to the VaultForge-compatible Mesh Network in the current source |

### Protection and Operations

| Screen | Purpose |
|---|---|
| **Recovery** | Wallet recovery/backup validation tools |
| **Connections** | Provider/network connection surfaces |
| **Security** | Security tooling and controls |
| **Vault Security** | Local encryption, safeguards and vault management |
| **Compliance Center** | Compliance-oriented development checks; not legal approval |
| **QA Center** | Local quality and fault-injection tooling |
| **Release Center** | Build/readiness checks, safe support export and incident guidance |
| **Financial Controls** | Controls, guardrails and authorization requirements |
| **Operations Center** | Operations activity surfaces |
| **Performance Center** | Local performance and queue-related checks |
| **Reliability Center** | Read-only health/queue/recovery-oriented checks |

The top-bar **LOCK PUBLIC VIEW** clears current unlocked public displays and sensitive input fields. The application also contains an idle-lock mechanism; do not treat it as protection against malware on an unlocked computer.

## 11. Creating an encrypted wallet

1. Open **Create Wallet**. Select an appropriate user-controlled destination, ideally on a secure local disk rather than inside this GitHub/source directory.
2. Choose the wallet/asset workflow offered by that screen and a strong, unique encryption password. Password reuse with the mesh account or other services is discouraged.
3. Read every confirmation on network, phrase length, derivation and recovery. **Never copy a seed phrase into online tickets, screenshots, or cloud notes.**
4. Generate/store the encrypted vault. Confirm its final file path; do not assume the default folder is your USB drive.
5. Make an offline backup of the appropriate recovery material. Restore on a separate clean environment and compare the derived public address before trusting funds to it.
6. Return to **Wallets** or **Unified Wallets** to inspect its public records. A visible address alone is not sufficient evidence of signing capability.

The code uses local encrypted vault functions, including Argon2id-derived keys and AES-256-GCM in its VaultForge implementation. Cipher selection and source-level tests do not replace a cryptographic security assessment.

**Never put any genuine wallet vault in `src/`, `dist/`, `release/`, or a public GitHub repo.** The builder actively rejects suspicious secrets and wallet file extensions in the source tree.

## 12. Opening, viewing and backing up vaults

Use **Wallets** to choose the correct existing `.vault` file, unlock it with its own password, and inspect public receiving addresses. The UI may retain unlocked *public* information for the current session; changing pages, idle-locking, or closing can clear sensitive UI state.

Check the exact asset and chain (e.g. Ethereum vs an EVM L2). A public EVM-style address may look identical on multiple networks, but sending funds on the wrong chain still causes loss or inaccessibility.

Back up the encrypted vault and required independent recovery phrase separately. Your recovery plan must specify file locations, encryption password management, network derivation settings, any external signer and a tested restoration sequence. Do not assume that copying only the app install folder preserves your vaults.

For a meaningful recovery drill: use a new temporary environment, restore from the independent backup, compare known addresses, verify a harmless test signature or testnet transaction, and document the result without recording seeds in the test report.

## 13. Supported address formats versus real transaction support

The VaultForge asset generator in `src/core/vaultforge.py` includes broad address-derivation definitions for approximately thirty currencies/networks. Examples visible in the source include BTC, LTC, DOGE, BCH, DASH, DGB, transparent ZEC, ETH/ETC, BNB Smart Chain, Polygon, Avalanche C-Chain, Arbitrum, Optimism, Fantom, TRON, XRP, Stellar, Solana, Cosmos, Osmosis, NEAR, Filecoin, Tezos, VeChain and Zilliqa, alongside additional entries in the actual source catalog.

**Do not read this list as a promise of full send/receive/sign/broadcast/restore for each asset.** The desktop supports several specific transaction paths, while other entries may be address-generation, metadata, watch-only or read-only network coverage. Zcash in the cited generator uses **transparent addresses**, not a claim of shielded Zcash support. Coin/token/network support can also change across upstream dependencies and chains.

For every advertised asset, independently verify: derivation, address format, secret export/recovery, balance source, unsigned transaction construction, signer, fee policy, broadcast, finality, reorg behavior, failed-send recovery, and version-upgrade compatibility. The production readiness table later in this document treats unverified assets as blocked.

## 14. Unified wallets and signer backends

Open **Unified Wallets**. Its first panel allows linking **Bitcoin Core**, an **EVM keystore**, **Monero wallet RPC**, or an unlocked `.vault`. The account list displays public identity and status; a second panel provides actions such as **VERIFY CONNECTION & BALANCE**, **COPY ADDRESS**, **ADD MONEY → ACCOUNT**, **OPEN SEND WORKFLOW**, **CHAIN BALANCE / READ ONLY**, **REMOVE SAVED LINK** and **REFRESH LIST**.

Important boundaries:

- The registry stores public metadata and local paths; it is not a secure substitute for a signing key backup.
- A displayed address or remembered keystore header does **not** prove you know the password.
- A Bitcoin Core watch-only wallet does not prove spend ownership.
- A Monero RPC public address does not prove the external wallet can spend or is fully synchronized.
- Unlocking a `.vault` does not automatically convert it into a Bitcoin Core, Monero, or EVM keystore signer.
- The chain reader may intentionally support only specific assets (the source calls out LTC, DOGE, BCH, SOL, TRX and XRP in one read-only workflow).

Always use the correct network and independently verify signer control before funding. If you don't have a supported signer, treat the account as watch-only regardless of a reassuring visual status.

## 15. Bitcoin: receiving, balances, and spending

The Bitcoin screens depend on **your own Bitcoin Core RPC service** for several balance and spend workflows. The source includes regtest and mainnet selections and local cookie-authenticated RPC; the common ports are 18443 (regtest) and 8332 (mainnet), but your actual `bitcoin.conf` determines the service address and permissions.

**Recommended order:**

1. Start Bitcoin Core in an isolated **regtest** environment first. Use a disposable wallet, not valuable holdings.
2. Configure the correct local RPC endpoint and select its cookie file using the GUI. Never publish the `.cookie` or put RPC credentials in this README or source ZIP.
3. Link Core under **Unified Wallets → BITCOIN CORE**, or use the **BTC Phase 1** panel for its intended workflow.
4. Obtain and verify a public receiving address. Confirm network prefix and ownership using Core.
5. Inspect balance, UTXO confirmation state, fee estimate, total cost, recipient address and transaction outputs.
6. If an authorized test spend is supported, sign/broadcast on regtest, confirm receipt, and repeat after a simulated restart.
7. Only consider mainnet after independent recovery, UTXO ownership and reorg/fee/error testing. The code's mainnet confirmation prompts are protective controls, not authorization to use real funds.

Potential failures include absent RPC cookie, wrong network, unsynchronized Core, incorrect Core wallet, immature coinbase outputs, dust/fee problems, mempool rejection, unconfirmed or already-spent UTXOs, and interrupted broadcasts. A timeout after signing must **never** cause an automatic blind resend; check the transaction ID and chain/mempool state first.

The GUI/source is not a full Bitcoin node and cannot substitute for an actual fully synced node or independent transaction verification.

## 16. EVM chains and ERC-20 transfers

The EVM-related modules (`src/evm_phase2.py`, source transfer modules, unified wallet code) cover Ethereum-style account workflows and selected EVM networks. Transfers depend on appropriate RPC endpoints, chain IDs, signing credentials, gas parameters, nonce handling, and token contract addresses.

When configuring an EVM transfer:

1. Verify the **exact chain ID**, RPC URL and recipient address independently.
2. Verify the asset: native gas coin versus ERC-20 contract; network-specific bridged tokens may use different contracts.
3. Check balance and **native gas reserve**, even when sending a token.
4. Review current nonce, max/priority fees, amount in the correct token decimals, contract and recipient before any signature.
5. Use disposable testnet funds first; record the transaction hash and check receipt/finality.
6. If an RPC request times out, query nonce, mempool and receipt before attempting any replacement or retry.

A token symbol matching across networks is not proof of contract identity. No one should assume cross-chain transfers are reversible. The existence of an `OPEN SEND WORKFLOW` button does not mean every EVM account in the unified list is actually signable.

## 17. Monero integration

The **Monero Phase 3** and **Unified Wallets → MONERO RPC** workflows rely on an external `monero-wallet-rpc` backend; this desktop package does not ship a verified live Monero node/wallet setup. Correct wallet selection, synchronization, daemon connectivity and spending authority are external prerequisites.

Use Monero **stagenet** (or an otherwise nonvaluable test environment) for an actual transfer-and-recovery drill. Review subaddresses, balance/unlocked balance, ring and fee behavior, transfer metadata, relays, rescans and wallet restore height. Do not treat a public address alone as spend authorization.

The GUI contains a safeguard against leaving the Monero transfer-preparation page while unrelayed transaction metadata is in memory. Complete or explicitly cancel a prepared operation before changing screens. Never expose a Monero spend key or mnemonic in a support log.

## 18. Other chains, tokens and chain expansion

**Chain Expansion**, **Token Center**, **Asset Coverage** and **Universal Transactions** provide additional interfaces and infrastructure for assets beyond the Bitcoin/EVM/Monero paths. Some features are read-only readers, prototype adapters or catalog entries, not independent complete spenders.

For chain-specific troubleshooting, inspect the module's supported-network list and its current UI warnings. If a chain only exposes balances or addresses, do not infer private-key import, multisig, stake/unstake, token approvals, NFTs, or transaction broadcasting. Fees and address memo/tag requirements differ between networks; XRP, Stellar and other networks may use destination tags/memos in some recipient contexts.

A robust release should eventually publish a **per-asset capability matrix** and test report distinguishing `ADDRESS`, `BALANCE`, `SIGN`, `BROADCAST`, `CONFIRM`, `RECOVER`, `REORG`, and `LIVE VERIFIED` for every network. Until that exists, use the individual source routes and tests as limited implementation evidence only.

## 19. Portfolio, monitoring and accounting

**Portfolio** and **Money Hub** can aggregate local public records and available account observations; they must not be mistaken for proof of ownership, exchange balances or confirmed funds without a verified source and timestamp. Verify whether values are from live RPC, a public price API, cached data, simulated fixtures or manually entered ledgers.

**Live Crypto** and **Blockchain Health** show other market/network indicators, subject to their source and provider restrictions. Protect against stale quotes and chain outages: an old price or cached balance should never silently be represented as current.

Use **Transactions** for available records and audit trails, but reconcile them with network explorers, wallet RPCs, processor reports or broker statements as appropriate. An application ledger entry is not a blockchain confirmation or bank settlement.

## 20. Money Hub, fiat and payment features

The project contains `financial_backend/` modules and screens for **Fiat Accounts**, **Fiat Ledger**, **Banking Rails**, **Phase 4 Funding**, **Wallet Funding**, **Fiat Payments**, **Currency Exchange**, **Money Hub** and **Financial Controls**.

Their exact capabilities depend on the configured local and external adapters. The source includes provider reference interfaces, local ledger operations, tests and development integrations; it does **not** independently establish that a real payment provider approved the app, that a bank account belongs to a user, that settled funds can be withdrawn, or that statutory obligations are met.

Before accepting real money, a production deployment would need a custody model, account ownership verification, provider authentication, KYC/AML where applicable, authorization and least privilege, reconciliation, settlement and reversals, funding/withdrawal controls, privacy/legal terms, and external operational audits. Never collect or store plaintext card credentials to “enable” an incomplete processor flow.

**Local receipts and sandbox transactions are not deposits.** Never imply that paper trading cash or a local fiat ledger can be transferred into a real bank account.

## 21. Trading Terminal: charting and paper orders

Open **WORKSPACE → Trading Terminal**. The current native interface includes:

- A stock/crypto symbol selector; supported examples include `AAPL`, `MSFT` and `BTC/USD`, depending on chosen data source.
- Timeframes: `1Min`, `5Min`, `15Min`, `1Hour` and `1Day`.
- Green/red candlesticks and OHLC inspection, EMA-12/EMA-26 overlays, volume and RSI-14.
- A local editable watchlist; double-click a symbol to display its chart.
- Synthetic **SIMULATED DEMO**, optional authenticated **ALPACA REAL DATA**, and optional read-only **NOCTURNE SERVER** feed.
- A completely separate **paper** cash/positions/order ledger and confirmation before simulated orders.

The default simulated opening balance is **$100,000 paper cash**. It is not fiat held by CRYPTO NOCTURNE, an exchange, a broker or a bank. Paper orders use the most recent acceptable price in the preview (subject to freshness checks); they do **not** model real spreads, slippage, queue priority, commissions, market impact, financing, margin or short selling.

Example training workflow:

1. Select **SIMULATED DEMO** to learn the interface without relying on network data.
2. Choose an asset and timeframe, click **LOAD CHART**, then inspect EMA and RSI.
3. Add the symbol to the watchlist and select a paper order quantity.
4. Click **PAPER BUY** or **PAPER SELL**; read and approve the order confirmation.
5. Review your updated paper positions, cash and order history; repeat with other symbols.
6. Switch to an entitled market-data feed only after understanding its source, coverage and timestamp.

**No live stock or crypto exchange orders are sent from this trading preview.** The terminal's price feed does not inherit VaultForge/Tor privacy settings and does not send wallet seeds to the mesh.

The watchlist is **not** a live quote stream for every row. The preview does not implement full options chains, Level II order books, professional screeners or all technical drawing tools shown in third-party screenshots.

## 22. Alpaca market-data setup

This is an optional **per-user read-only market-data configuration** for developers with their own credentials and permitted feed access. Start the application from a PowerShell session containing the temporary variables:

```powershell
$env:ALPACA_API_KEY = 'YOUR_MARKET_DATA_KEY'
$env:ALPACA_API_SECRET = 'YOUR_MARKET_DATA_SECRET'
.\START_WINDOWS.bat
```

Then open Trading Terminal and select **ALPACA REAL DATA**. Credentials are obtained from the process environment. Do not hard-code them in GitHub, `.spec`, `.json`, `.bat`, `.iss`, readme screenshots, or the EXE you redistribute.

**Coverage matters:** the current stock adapter uses an IEX feed, not an all-US-exchange consolidated feed; crypto assets are limited to what the configured Alpaca endpoint supports. Quotes may be delayed, incomplete or absent outside market hours. The implementation uses HTTPS for historical data and authenticated streaming where available; the real market feed needs entitlement, connectivity and error handling. Streaming one-minute updates do not magically reaggregate all higher-timeframe historical candles.

Reference provider documentation is linked at the end of this README. No API account, live data contract or entitlement is included in the source.

## 23. Optional centralized market-data server

If you operate the application for many desktop users, you can run a **separate read-only HTTPS server** with the feed provider's credentials stored *only on the server*. This allows users to receive authorized chart data without typing a provider key on every PC.

The desktop client code lives in `src/market_server_client.py`; its public service origin is stored in `src/data/market_server.json`. To configure the release at the source root:

```powershell
py -3.12 CONFIGURE_MARKET_SERVICE.py https://markets.example.com
```

Then rebuild and distribute the updated EXE. This configuration accepts a valid HTTPS origin on port 443, **not HTTP, embedded credentials, arbitrary paths or query strings**. When configured, the UI's **NOCTURNE SERVER** source polls the backend approximately every 20 seconds, using `/api/v1/bars` and `/api/v1/latest`. The backend also has a `/health` endpoint.

**Server deployment is separate from this GUI source archive:** use the matching standalone market server package, an appropriately configured environment file, a real DNS name, HTTPS reverse proxy, access/rate controls, and provider permission. It typically runs internally on localhost port **8787** behind a port-443 reverse proxy. Your VaultForge chat relay is unrelated and commonly listens on **TCP 6667**. Do not send market credentials over mesh chat or copy them into client source.

Crucially, **market-data redistribution may require contractual and exchange licensing** beyond an individual API subscription. The separate server defaults to clearly labeled synthetic demo data until lawfully configured. It exposes no order-placement or broker authorization endpoint. It does not enable real trading by itself.

---

## 24. VaultForge Mesh: concepts and security

The desktop's **Mesh Network** uses a bundled, separate VaultForge v2.7-compatible network implementation. Each participant holds a **local chat identity** with an independently generated key fingerprint and a separate password. Local account records reside outside the wallet vault. Each node can listen locally, connect outward to an AWS/VPS relay or another peer, or (when configured) host its own background node.

**Important design truths:**

- **Not standard IRC:** ordinary IRC clients and servers cannot automatically connect to this custom signed/encrypted transport.
- **Not a global login directory:** registering on one device does not create a central account accessible on every other device. User `joker` on one Linux installation and user `Joker` on another can be different cryptographic identities.
- **Reachable roster, not every account ever created:** remote online users appear only when authenticated presence propagates through connected peers.
- **Private DMs and files are recipient-encrypted** under the implementation; the relay should not receive the plaintext payload.
- **Public-room text and history are not end-to-end private from the relay.** Assume a relay operator and anyone with access to its stored room history may read them.
- **Identity pins matter:** when a relay's key changes, clients deliberately refuse it until the operator's new fingerprint is independently verified.
- **Signed public listings are not trust endorsements.** They do not guarantee that a node is reachable, safe or correctly attributed.
- **Experimentally designed custom cryptography/transport:** it has not received an independent protocol audit.

No chat password, node secret or peer key should be a wallet seed. Do not send wallet files, sensitive account databases, payment tokens or signing secrets through the experimental file-transfer feature.

## 25. Mesh registration and connecting to a relay

On Windows:

1. Open **NETWORK / P2P → Mesh Network**.
2. Enter your desired username and use **Register** for a new local chat identity, or **Log In** for an existing identity on **this same local user profile**. The chat password must be at least **14 characters**.
3. Choose **WAN / AWS**, **Offline LAN**, or **Tor required** *before* connecting.
4. For a public relay, enter its actual public **`HOST:PORT`**. Example only: `18.188.145.207:6667` was used by a project test EC2; it must still resolve to a running and authorized server. Private AWS `172.31.x.x` addresses are not normally reachable from the public internet.
5. Press **Connect**. Successful TCP connectivity is not sufficient: the encrypted handshake and expected identity must also succeed.
6. Look for **CONNECTED** and a nonzero authenticated link count. If you see **LOCAL ONLY**, other devices cannot reach you through the selected relay.
7. Click **Refresh Online** to request current signed presence from connected peers. Auto-connect on login is an optional UI checkbox.
8. Verify the remote identity out-of-band before relying on it. Do not auto-approve changes just because the hostname or IP is familiar.

The chat identity header shows your *own* nickname and fingerprint. **Online Users (remote peers)** deliberately excludes your own account.

Both the GUI and standalone VaultForge CLI can use compatible local chat identity storage in the same operating-system user home. Their wallet-related files and runtime setups remain separate.

## 26. Rooms, online users, messages and transfers

### Public rooms

Use **Live Rooms** to view announced rooms, select one and click **Join Selected Room**, or type a new room name such as `#general` into the Room field and click **Create / Join Room**. Click **Send to Room** before posting when you have previously selected a DM recipient. Public room messages are visible to connected room participants and may be stored by the relay.

The **Recent History** button asks the connected network for available room history. Existing history capability depends on the relay version and retention settings; a newly upgraded relay cannot reconstruct messages it never recorded. Seeing prior local history does not prove the client is currently connected.

### Remote users and private messages

Switch to **Online Users (remote peers)**, click **Refresh Online**, select a user and press **Message Selected**. The DM target should contain the intended **remote identity**. Do not enter your own fingerprint or an ambiguous nickname. After returning to a room, explicitly click **Send to Room** to avoid accidentally addressing a private recipient.

If the roster is empty, inspect the top status and log panel. `LOCAL ONLY` or `0 authenticated links` means you must establish a peer connection first; a refresh button cannot query nonconnected servers or all offline accounts worldwide.

### Files, images and ZIP folders

Use **Upload File / Image** to offer an attachment to the selected DM recipient or to eligible members of the active room, as permitted by the UI routing. Use **Share Folder (ZIP)** to package a directory into a bounded ZIP rather than transferring a raw arbitrary directory tree. On the receiving side, open **Incoming Files** and choose **Accept & Save** or **Reject**.

Current transport constraints include an approximate **4 MiB encrypted attachment cap**, with bounded recipient fan-out for room attachments. Both sides need current reachability and consent; file offers do not make an offline user magically receive a transfer. Do not auto-extract untrusted ZIPs or run received executables. A green network connection does not imply that a remote file is trustworthy.

### Presence and reconnects

The GUI refreshes its roster presentation periodically and supports signed presence refresh. Auto-connect/retry works only against a configured/reachable endpoint with accepted identity. The server's public address may change if an EC2 instance is restarted without a stable allocation; update the endpoint carefully and verify the peer key separately.

## 27. Identity trust, changes and recovery

The GUI contains a native **Verify / Update Relay Trust** button. This was added because the chat compose box is **not** a command console; typing CLI commands like `/unpin` or `/trust` into it does not update the trust registry.

Use the button **only after verifying a genuine key rotation independently**, for example by signing into your own relay via SSH and obtaining its public fingerprint locally. The dialog shows the currently pinned fingerprint, requires an explicitly entered replacement, and updates only that endpoint's record after confirmation. The old trust data is backed up before rotation.

Saved trust metadata is generally under:

```text
Windows: %USERPROFILE%\VaultForge\mesh_chat\known_peers.json
Linux:   ~/VaultForge/mesh_chat/known_peers.json
```

Do **not** blindly delete this file or turn off fingerprint verification to make a connection pass. That may allow an impostor relay to impersonate your trusted server. If the operator intentionally recreated the node, its key has truly changed; every previously pinned client needs an independently verified transition.

The example incident in this project's testing involved an old fingerprint `f704e415f7ffc6dd` and a *newly verified* replacement `9aca2e4a28878448`. **These are incident-specific examples, not universal credentials or a guarantee that the current host is still that server.** Never hard-code one user's test fingerprint into a public distribution.

If your chat account password or local identity key is lost, treat that as an account recovery issue; it is not fixed by changing the relay trust pin. The remote relay does not own your local chat password or identity private key.

## 28. Hosting your own mesh node

The GUI has an **OPTIONAL BACKGROUND NODE** area with **Node name**, **Listen**, optional **Public advertise**, and buttons: **Configure Node**, **Start in Background**, **Stop**, **Status**, **Autostart**. You do **not** need to host a node merely to join someone else's relay.

Behind that UI, the node manager provides these source commands:

```text
setup     configure separate mesh identity and listener
publish   set an opt-in public discovery endpoint
start     start saved node in background
stop      stop the node
status    inspect current saved node/process
run       foreground server process for service managers
autostart configure supported per-user startup
service-file  print a systemd service definition
```

For a **private LAN node**, a developer with installed Python dependencies can create a node via the source manager, without using real wallet data:

```bash
cd src
python vaultmesh/node_manager.py setup --mode lan --name LaptopRelay --listen 0.0.0.0:7777
python vaultmesh/node_manager.py start
python vaultmesh/node_manager.py status
```

Use `stop` when finished. The `setup` action is intentionally **non-idempotent** with respect to cryptographic identity: it refuses to overwrite an existing `node.json` or `node.secret`. If you want to reuse a node after upgrading, preserve those files and start the *existing* configuration. Host firewalls and LAN reachability must still be configured.

To expose a node outside your LAN you must deliberately choose WAN mode, open the appropriate TCP port, arrange router port-forwarding or VPS firewall rules, and verify actual reachability from another network. A host with only carrier-grade NAT generally cannot accept unsolicited public inbound connections without tunneling/relay help. Publishing `0.0.0.0:6667` as a public endpoint is wrong: `0.0.0.0` is a **bind address**, not a client's destination.

On Windows, autostart uses the Windows user's startup machinery; on Linux, the node manager has per-user `systemd` integration. Actual process survival depends on host sleep, account login/session and OS policies. For all-day public hosting, use a properly configured dedicated server rather than an intermittently sleeping laptop.

## 29. AWS, VPS and dedicated relay deployment

**The GUI source contains a node manager and relay engine; a production-style headless server deployment needs the separately maintained relay launcher/source, system service, and its own security review.** The AWS relay is not a piece of the wallet application installer.

A clean deployment plan:

1. Provision a supported Linux host under a dedicated non-root service account.
2. Keep the relay program files in an app installation directory and persistent chat data in a distinct private directory, commonly `~/VaultForge/mesh_chat`.
3. Install the relay's supported Python version and dependencies in a dedicated virtual environment. Confirm the service executable path exists before installing a unit.
4. Initialize **one** relay identity. Back up its identity/configuration securely. Do not regenerate it on every setup or upgrade.
5. Bind to a controlled host address, commonly `0.0.0.0:6667` for an intentionally public listener. Allow inbound TCP **6667** only as appropriate; restrict SSH to trusted management IPs. Add host firewall, rate limiting and monitoring.
6. Configure a valid **public IP/DNS plus port** for clients, e.g. `relay.example.com:6667`; use a stable allocation if possible.
7. Use `systemd` only after its `ExecStart` points to the real Python binary and its `WorkingDirectory` is valid. Validate with `systemd-analyze verify` and `systemctl status`.
8. From **a different computer**, verify that TCP 6667 is reachable, the encrypted handshake succeeds and the out-of-band fingerprint matches.
9. Enable autostart after the node has remained stable. Keep the service log private and monitor error/restart rates.

Example **management** commands for a service that is already installed as `vaultforge-mesh.service`:

```bash
sudo systemctl start vaultforge-mesh
sudo systemctl stop vaultforge-mesh
sudo systemctl restart vaultforge-mesh
sudo systemctl status vaultforge-mesh --no-pager
sudo ss -lntp | grep ':6667'
sudo journalctl -u vaultforge-mesh -f
sudo systemctl enable --now vaultforge-mesh
```

Those commands **do not install missing source, repair a virtual environment, or create an identity**. The `Active: active (running)` snapshot alone is insufficient if the process immediately exits; always check the stable listener and recent logs.

**Known past installer trap:** The project previously experienced systemd `203/EXEC` because an old unit referenced a removed virtual environment, and a separate `bad unit file setting` due to an incorrectly quoted `WorkingDirectory`. Verify the installed unit, repair/replace the unit using your actual path and run `sudo systemctl daemon-reload`; do not repeatedly rerun a broken service. A future installer should automatically validate the generated unit before enabling it.

**Self-connection trap:** A relay should not use its own public IP and listening port as an upstream bootstrap peer. That produces `Cannot connect to your own identity` errors and retry loops. Keep the public **advertisement** separate from the **outbound peer list**. Only set peers to *other* independent nodes.

**Identity loss:** If `node.json`, `node.secret` or account storage is missing, first search secure backups. Creating an empty `~/VaultForge` folder restores only a directory, not identity keys. A newly created node has a different fingerprint; clients must independently trust the new key after verifying a deliberate rotation. Never silently create a new identity during normal service restarts.

## 30. Offline LAN and Tor-required networking

### LAN mode

Select **Offline LAN** for devices sharing a reachable LAN. The implemented opt-in discovery uses UDP **48877**; encrypted peer connections use the selected TCP listener port. Devices on guest Wi-Fi, different VLANs or firewalled subnets may not see each other. The offline mode rejects public IPs/hostnames and must not silently fall back to the internet.

Use **Scan LAN**, select a discovered peer and verify its fingerprint. If automatic discovery fails, test explicit LAN IP/port connectivity from both machines. A scanner result is not an authenticated connection until the handshake completes.

### Tor-required mode

Select **Tor required** *before connecting*. The mesh engine uses an available local Tor SOCKS5h endpoint, commonly port **9050** (sometimes **9150** with a browser configuration), and avoids direct WAN fallback in this mode. The SOCKS proxy must actually be running and reachable; otherwise the correct behavior is to fail closed instead of leaking a direct connection.

If you want others to reach a hidden node, configure a Tor onion service separately. The node manager's Tor mode listens only on loopback and must not be exposed as a public `0.0.0.0` Tor listener. A Tor proxy is not the same as an onion service. Tor does not make public cryptocurrency transactions private and does not automatically anonymize the separate Trading Terminal market feed.

## 31. Files, storage, secrets and backups

The application deliberately uses **several** directories rather than a single master folder. Check actual source defaults and your selected locations before backing up:

| Data class | Typical location | Backup rule |
|---|---|---|
| User-selected encrypted vault files | Often `~/CryptoWallets` or the path chosen in the GUI | Back up file **and** independent recovery information securely |
| VaultForge wallet files (core component) | `~/VaultForge/wallets` | Private, never in source/GitHub |
| VaultForge chat account and keys | `~/VaultForge/mesh_chat` | Preserve securely when migrating the same chat identity |
| Mesh trusted peer pins | `~/VaultForge/mesh_chat/known_peers.json` | Back up; rotate explicitly, not blindly |
| Background node config/key | `~/VaultForge/mesh_chat/node.json`, `node.secret` | Highly sensitive; never publish or regenerate casually |
| Mesh downloaded attachments | `~/VaultForge/mesh_chat/downloads` | Treat received files as untrusted |
| Trading paper ledger and watchlist (Windows) | `%LOCALAPPDATA%\CRYPTO_NOCTURNE\paper_trading\` | Training records only, not real balances |
| Trading paper ledger and watchlist (Linux dev) | `$XDG_DATA_HOME/CRYPTO_NOCTURNE/paper_trading/` or `~/.local/share/CRYPTO_NOCTURNE/paper_trading/` | Local-only; not mesh-synced |
| GUI source runtime (Windows) | `%LOCALAPPDATA%\CRYPTO_NOCTURNE\runtime-v2.3` | Reinstallable dependencies; not a wallet backup |
| GUI builder runtime (Windows) | `%LOCALAPPDATA%\CRYPTO_NOCTURNE\builder-v2.3` | Reinstallable build tools |
| Core wallet/fiat development data | Depends on module and user folder | Examine each subsystem; no universal backup location |
| Market server credentials | Separate private server environment | Never include in desktop EXE or source |

Some legacy/financial components use `~/.crypto_creating_wallets`, `~/.crypto_nocturne`, or OS-local application data paths. A complete backup inventory must inspect the actual components you use; **backing up only `~/VaultForge` is not sufficient for every Nocturne feature**.

For backups: encrypt at rest, keep independently protected offline copies, test recovery, separate testnet and mainnet, preserve filenames/versions and protect OS access. For chat, restoring an account database without matching private identity material may not restore the original cryptographic identity.

## 32. Security, privacy and threat model

The key threats include compromised host devices, malicious dependencies, tampered installers, clipboard hijacking, unsafe RPC configuration, malware in transferred files, malicious relay operators, privacy leakage from public rooms and network traffic, inaccurate price feeds, and accidental real-money sends.

Protective measures implemented in source include input validation, limited file sizes, separation of wallet and mesh secrets, source/output scans for sensitive files, peer fingerprint pinning, fail-closed Tor-required connections, UI clear/idle-lock behavior, and local release checks. None of these controls alone establishes complete confidentiality, safety or legal compliance.

A public relay operator can see connection metadata and any readable public room/history data. Do not use room history for secrets. Do not interpret private-message encryption as an audited guarantee of metadata privacy, secure multi-device key rotation, forward secrecy or resistance to every active network attack.

For wallet safety, use verified upstream node software, independent address checks, transaction whitelists/limits where possible, strong backup protection and disconnected recovery drills. For build safety, pin/dependency-review packages, maintain reproducible provenance and sign artifacts with a separate protected publisher key.

**This is not security advice to ignore provider or regulatory requirements.** Payment processing, custody and exchange integration will require legal and operational approvals specific to the operating jurisdiction and business model.

## 33. QA, compliance, operations and release centers

The application includes **QA Center**, **Reliability Center**, **Operations Center**, **Financial Controls**, **Compliance Center**, **Performance Center**, and **Release Center** pages. They provide development checks, health surfaces, incident guidance, local evidence or control interfaces; they are **not independent auditors, licensed bank partners or deployment approvals**.

Release Center's local gate evaluation includes read-only checks and exports fixed, redacted support diagnostics. A support export is intended not to include node passwords, wallet phrases or raw financial records. Nevertheless, manually inspect every report before publishing it: paths, hostnames and incidental output can still reveal internal details if a component changes.

The release subsystem can create limited inventories and check signed update metadata against an independently verified key. These are *building blocks* for release governance, not a hosted update service, vulnerability scan or financial certification.

## 34. Test and verification commands

Run application source tests from the correct extracted root with a Python environment containing the pinned dependencies. For example, on Windows:

```powershell
py -3.12 src\build_release.py check
py -3.12 src\build_release.py test
py -3.12 src\build_release.py release-check
```

The tester uses a temporary working directory and redirects relay SQLite test storage so it does not contaminate the source tree. The batch builder enables UTF-8 when launching its tests; this avoids legacy Windows CP1252 encoding exceptions seen in earlier mesh test runs.

Additional tools:

```powershell
py -3.12 src\qa_runner.py
py -3.12 src\release_ops_cli.py check
py -3.12 src\release_ops_cli.py sbom --export C:\Reports\direct-deps.cdx.json
```

Use the QA runner's Bitcoin regtest option only when you intentionally have a proper disposable regtest setup. Never point an automated test toward a real wallet holding valuable funds.

**Test evidence for this source lineage:** the previous local release passed 494 discovered desktop tests with 2 skipped, including GUI mesh trust-rotation tests. This README does not rerun all tests on every user OS. A green Linux Python test run is not evidence that the compiled Windows EXE, installation, AWS relay, Termux, real blockchain transactions or payment integrations worked end-to-end.

Test separately: Python unit tests; multi-client local encrypted handshakes; signed roster; file acceptance; a clean Windows EXE; an Inno Setup install/upgrade/uninstall; actual AWS firewall/identity connection; Bitcoin regtest; EVM testnet; Monero stagenet; disaster recovery; and any external provider's sandbox reconciliation.

## 35. Build signing and staged update verification

Phase 18 includes `src/release_ops_cli.py verify-update`, which verifies staged metadata signatures, byte length, SHA-256 and supported version policy **without downloading, installing or running the update**. An approved public signing key must come through a separate trusted channel, not from the same unverified update manifest.

High-level example (illustrative paths, not a shipped key):

```powershell
py -3.12 src\release_ops_cli.py verify-update `
  --manifest C:\Staging\update.json `
  --artifact C:\Staging\CRYPTO_NOCTURNE_Setup_v4.5.1.exe `
  --trusted-key C:\Trusted\publisher_public.pem `
  --trusted-key-sha256 YOUR_INDEPENDENTLY_VERIFIED_FINGERPRINT
```

The manifest is a strict signed envelope, with canonical payload fields for application, channel, platform, version, upgrade floor, artifact name, byte length and checksum. A passing signature does not guarantee the installer is free of vulnerabilities. Windows Authenticode validation still requires a legitimate signature and Windows-supported verification tools.

When preparing a public release, produce reproducible artifact hashes, source commit ID, dependency inventory, signature evidence and independent test reports. Never label an unsigned `development_release_receipt` as a trusted supply-chain attestation.

---

## 36. Common Windows and Linux errors

| Symptom | Likely cause | Safe response |
|---|---|---|
| `Python 3.12 64-bit required` | Wrong version/architecture | Install Python 3.12 x64; verify `py -3.12` and 64-bit pointer size |
| `py` not recognized | Python launcher absent | Install official Python launcher or configure a valid 3.12 executable |
| `No module named ...` | Runtime missing/incomplete dependency | Re-run the matching source launcher/builder; avoid mixing unrelated venvs |
| `UnicodeEncodeError: charmap` | Windows legacy console encoding | Current builder sets UTF-8 for tests; use updated source, capture clean logs |
| `UnicodeDecodeError` reading source/tests | CP1252 default reading UTF-8 file | Use corrected source/test explicit UTF-8 handling |
| `Inno Setup ISCC.exe not found` | Installer compiler missing | Install Inno Setup 6 or configure `ISCC_PATH` |
| PyInstaller EXE missing despite no obvious failure | Build unsuccessful/incomplete | Save full compiler log; check final command exit code and `dist` |
| Frozen-wallet smoke test failed | Packaged module/data mismatch | Do not ship EXE; fix actual spec/dependency and retest |
| Build blocks `*.vault`, `*.db`, `.pem` etc. | Secrets/private data in source tree | Move real runtime data out of source before building; don't disable scan |
| `No display name and no $DISPLAY` | Linux without graphical session | Use desktop session or correctly configured X/Wayland forwarding |
| `externally-managed-environment` | Global pip attempted on Kali/Debian | Use provided isolated venv; don't bypass OS guardrails |
| Tkinter import error on Linux | `python3-tk` absent/mismatched | Install matching distro Tk package; check `python3 -m tkinter` |
| Installer succeeds but app appears old | Running previous executable/install directory | Check actual EXE path and internal version; rebuild/reinstall deliberately |

Builder log files can be saved with **Save log** and attached to a bug report after checking that no sensitive information was printed. Do not send seed phrases, full wallet JSONs or credentials.

## 37. Mesh troubleshooting, including AWS failures

| Symptom | Meaning / checks |
|---|---|
| `LOCAL ONLY — no remote peer` | No successful authenticated connection; click Connect and verify relay state |
| `Connection refused` / WinError 1225 / Errno 111 | No listener or traffic being rejected at target: check service, IP, host firewall, AWS security group and actual TCP port |
| Relay shows `203/EXEC` | systemd ExecStart executable path is missing/inaccessible; recreate the runtime or correct the service unit |
| `Unit has a bad unit file setting` | Inspect unit with `systemd-analyze verify`; review `WorkingDirectory` syntax and referenced paths |
| `Cannot connect to your own identity` | Node has its own endpoint configured as an outbound peer; remove from upstream list, not from public advertisement |
| `Peer identity changed` | Pinned peer fingerprint differs; independent rotation verification required; **do not blindly bypass** |
| `REMOTE ONLINE: 0` with `CONNECTED` | No other authenticated clients currently reachable, roster delay, version mismatch or stale presence |
| `REMOTE ONLINE: 0` with `NOT CONNECTED` | Connection problem first; refresh cannot fix the missing link |
| `/trust` typed in GUI appears as message | GUI compose field is not CLI shell; use **Verify / Update Relay Trust** |
| Local registration succeeds but AWS login fails | Accounts are local per installation; connection/authentication and local account registration are separate |
| DM `recipient not found or nickname ambiguous` | Choose remote user by verified ID and ensure connection/room mode is correct |
| Room messages stay local | Current chat isn't connected; historical display alone doesn't indicate WAN reachability |
| File offer absent | Sender/recipient disconnected, wrong room/ID, size/fan-out limit, or recipient hasn't accepted |
| No public nodes discovered | No reachable bootstrap or opt-in listings; directory is not internet-wide port scanning |
| LAN peers missing | Different subnet, firewall/UDP 48877 blocked, LAN discovery disabled or isolation settings |
| Tor connection fails | SOCKS5 proxy missing/misconfigured; no unsafe direct fallback should occur |

### Minimum AWS validation sequence

On your server:

```bash
sudo systemctl status vaultforge-mesh --no-pager
sudo systemctl cat vaultforge-mesh
sudo ss -lntp | grep ':6667'
sudo journalctl -u vaultforge-mesh -n 80 --no-pager
```

On **a different client PC**:

```powershell
Test-NetConnection YOUR_PUBLIC_IP -Port 6667
```

A TCP success only establishes reachability; you still need to register/log in locally, finish the signed/encrypted peer handshake and verify the server identity. Make sure `YOUR_PUBLIC_IP` is the real current server endpoint, not `0.0.0.0` or an EC2 private `172.31.x.x` IP.

If an AWS server identity was unintentionally regenerated during reinstall, recover the original node keys from a trusted backup if possible. Otherwise record and independently distribute the new fingerprint and update pins explicitly on each client. Never resolve this by disabling identity checks for everyone.

## 38. Trading and provider troubleshooting

**No bars:** confirm source mode, symbol syntax (`BTC/USD` differs from `BTCUSD`), timeframe, network and data entitlement. Choose **SIMULATED DEMO** to verify that the chart UI works independently of provider credentials.

**No streaming prices:** check the source's latest timestamp, market hours, API subscription, allowed symbols, WebSocket errors and firewall/proxy configuration. Do not mislabel stale IEX data as a consolidated exchange feed.

**Paper Buy/Sell rejected:** ensure a recent enough reference price, sufficient paper cash/holdings, supported symbol and positive quantity. The local paper ledger must not transfer real funds or modify a genuine fiat account.

**No central server prices:** verify that `src/data/market_server.json` contains the intended HTTPS origin and the packaged EXE includes it. Test the public `/health` and read-only `/api/v1/bars` endpoints, TLS certificate, server permissions and backend provider rights. A source edit does not change an EXE already compiled on a user machine; rebuild it.

**Broker account not connected:** this preview has **no live brokerage authorization/order system**. Do not paste a broker password or API trading key into market-data fields or invent a direct “Buy” integration to move funds.

## 39. Backups, restoration and incident handling

Build a disaster recovery plan before experimenting with account credentials or real blockchain data. At minimum:

1. Inventory encrypted vaults, mnemonic backup procedures, external keystores, Bitcoin Core/Monero data, chat identities, trusted peer pins, paper ledgers, and financial integration credentials separately.
2. Back up **secrets privately**, never alongside a public repo or shared installer. Protect against ransomware, unauthorized reads and cloud synchronization leaks.
3. Test restore in a fresh disposable environment. Verify the same public addresses and actual *testnet* signing capability, not just successful file decryption.
4. Rebuild the application from source with pinned dependencies and a verified commit; audit the resulting artifacts before distribution.
5. Test relay recovery by restoring its original identity. Check client fingerprint pins and confirm that any key rotation is intentional.
6. For interrupted financial transactions, determine the authoritative state from the blockchain/provider and audit log *before* attempting any retry.
7. For suspected compromise: isolate the affected host/service, revoke/rotate exposed credentials, preserve a limited redacted incident timeline, assess affected wallets/providers, and communicate verified facts to users.
8. Never ask users to send seeds or unencrypted vaults to “support.”

**Backups are not successful until a tested restore works.** A new relay initialized with the same display name has a *new* identity unless the original private key material is restored.

## 40. Developers: source modules and extension rules

### Broad module map

| Area | Source paths |
|---|---|
| UI shell, navigation, idle-lock | `src/crypto.py`, `src/brand_theme.py`, `src/brand_assets/` |
| Wallet/vault generation | `src/backend.py`, `src/core/vaultforge.py`, `src/professional_ui.py` |
| Unified account registry | `src/unified_wallet.py`, `src/unified_wallet_ui.py` |
| Bitcoin | `src/btc_phase1.py`, `src/btc_phase1_ui.py`, `src/core/transfer.py` |
| EVM/Monero | `src/evm_phase2.py`, `src/xmr_phase3.py`, `src/phase23_ui.py` |
| Chain coverage/tokens | `src/chain_expansion*`, `src/token_infrastructure.py`, `src/token_center_ui.py`, `src/universal_transactions*` |
| Money Hub and fiat | `src/financial_backend/`, `src/financial_experience*`, `src/core/fiat_*`, `src/banking_rails*` |
| Trading core and UI | `src/market_terminal.py`, `src/trading_terminal_ui.py`, `src/market_server_client.py` |
| Mesh GUI/worker | `src/mesh_gui.py`, `src/mesh_bridge.py`, `src/vaultmesh/` |
| Legacy LAN/WAN/P2P UI | `src/lan_chat_ui.py`, `src/wan_chat_ui.py`, `src/peer_ui.py`, `src/core/{lan_chat,wan_chat,peer_network}.py` |
| Privacy and controls | `src/vault_security*`, `src/security_gates.py`, `src/compliance_*`, `src/reliability_*` |
| Release/build | `src/build_release.py`, `src/builder_gui.py`, `src/installer.iss`, `src/CRYPTO_NOCTURNE.spec`, `src/release_ops*` |
| Tests | `src/tests/test_*.py` and specialized test scripts |

### Coding practices

- Keep wallet private keys and chat node keys **completely separate** in memory and persistent storage.
- Never perform network calls, disk scans, or signing on Tkinter's main UI thread; use the existing background worker patterns and bounded event queues.
- Preserve user-created vault/fiat data on upgrades. New database migrations need rollback plans, version checks and backup tests.
- Prefer fail-closed parsing and explicit network/asset selection over silent defaults for financial operations.
- Do not log raw RPC cookies, passwords, secret keystores, seeds, payment credentials or encrypted chat payloads.
- Avoid retriable transaction broadcasts without checking idempotence, nonce/UTXO state and finality.
- Test code and source package separately from runtime databases so integrity checks don't flag or ship generated SQLite files.
- Add unit and integration tests for security-relevant error paths and external-provider faults before expanding the feature matrix.

### Source compatibility

The GUI contains local helper modules, historical prototypes and integration code from multiple development phases. Do not delete an apparently “unused” module merely because a screen looks incomplete; check `crypto.py` imports, the PyInstaller spec and regression tests first. Keep filenames/relative asset paths compatible with the builder.

## 41. Publishing the source on GitHub

This README is written for the **original source archive**, not a reorganized monorepo. To publish:

1. Extract the original source into a new private working directory.
2. Replace the original top-level `README.md` with this document.
3. Add a restrictive `.gitignore` and **independently inspect** the entire tree before committing. At a minimum exclude `.venv/`, `.runtime/`, `__pycache__/`, `build/`, `build_temp/`, `dist/`, `release/`, `.env*`, `*.vault`, `*.fiat`, private `*.db`/`*.sqlite*`, `node.secret`, `accounts.json`, raw keystores, RPC cookies, API tokens, `.pem` keys, `.p12` and `.pfx`.
4. Review embedded endpoint URLs, test fixtures, logs and data files; *test-looking values* are not automatically safe to publish.
5. Verify you own or may redistribute any artwork, source dependencies and branded assets. Add a deliberate LICENSE only after reviewing those rights.
6. Run source checks, commit a pinned dependency set and record a manifest/checksum of the release.
7. Publish through a GitHub repository only after the secret scan and legal review; prefer tagged source releases over replacing existing release files silently.

Example Git commands **after** safety checks:

```bash
git init
git branch -M main
git add .
git status --short
git diff --cached --name-only
git commit -m "Document CRYPTO NOCTURNE source and setup"
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPO.git
git push -u origin main
```

A `.gitignore` does not remove secrets from earlier commits. If one was ever pushed, treat it as exposed; revoke and rotate as appropriate, review history and use a proper history-cleaning process. Never post an entire source ZIP that contains live user balances, chat databases or wallet files.

## 42. Production-readiness gates and roadmap

**The 18 historical development phases are not 18 completed certifications.** UI modules and local test harnesses are milestones, not operational signoff. This project's expanded launch-readiness checklist still requires concrete external evidence for at least these twelve gates:

| Gate | Required evidence before claiming readiness |
|---|---|
| 1. Bitcoin mainnet | Real synced-node end-to-end funding/spend, fees, confirmations, reorgs, safe retries and independently controlled recovery |
| 2. EVM/ERC-20 | Testnet send/receipt/finality, nonce/gas/replacement, recovery and network-selection controls |
| 3. Monero | Stagenet wallet-RPC transfers, subaddresses, scanning/relay/recovery and operational restart drills |
| 4. Other advertised assets | Actual send/receive/sign/broadcast/recovery for **each** supported asset, not address generation alone |
| 5. Independent recovery | Restore seeds, keystores, wallet databases and signer configuration independently from another trusted device |
| 6. Fiat/payment providers | Signed provider agreements, settlement/withdrawal/reversal/reconciliation tests, appropriate licensing/controls |
| 7. Cryptography audit | Qualified external review of wallet cryptography, key management, and custom encrypted mesh transport |
| 8. Security penetration test | External application, installer, backend and infrastructure pentest with remediation verification |
| 9. Windows deployment | Real EXE, installer, upgrade, rollback and uninstall tests on supported Windows systems |
| 10. Signed releases | Independent publisher signing and verified update provenance, key-management and rollback policy |
| 11. Disaster recovery | Tested incident response, backup restoration, corrupted-state recovery and interrupted-transaction drills |
| 12. Legal and custody approval | Jurisdiction-specific custody model, privacy obligations, broker/payment-provider authorization and signoffs |

A status report should label each item **Implemented**, **Locally tested**, **Externally verified**, or **Blocked**; do not use a single vague percentage to imply that all launch requirements are satisfied. At the time of this documentation, the evidence available does **not** close all production gates. The app should remain clearly marked experimental.

### Priorities for future versions

1. Stabilize the native Windows build and prove clean upgrades on multiple user machines.
2. Complete real cross-device mesh connection/roster/DM/file tests and obtain independent protocol review.
3. Verify wallet recovery and spendability on safely controlled regtest/testnets and published capability matrices.
4. Add provider-authorized market feeds, entitlement and freshness enforcement, rather than silently substituting demo prices.
5. Only then assess per-user broker authorization, real execution, reconciliation, custody and regulatory obligations.
6. Close every external audit, incident and signing gate with published evidence before calling the platform production-ready.

## 43. FAQ, glossary and reference guides

### FAQ

**Q: Is this a complete, compiled Windows EXE?**  
A: No. This is full source. Run `BUILD_WINDOWS.bat` on Windows and verify the resulting `dist/CRYPTO_NOCTURNE` folder or optional Inno installer.

**Q: Why does the title bar still say 4.5.1?**  
A: The source builder and installer metadata have not yet been synchronized with later source/mesh package names.

**Q: Can I place stock orders from Trading Terminal?**  
A: No. The current buttons place simulated paper orders only. Market-data access does not authorize real trading.

**Q: Do all thirty cryptocurrency formats support real spending?**  
A: No such blanket claim is supported. Derivation/address visibility and complete signed spend/recovery must be checked separately for each asset.

**Q: Does installing the GUI start my AWS relay?**  
A: No. The relay is a separate host/service with its own identity and listener. The desktop can connect to it or configure a separate local node.

**Q: Can my friends share one central chat login?**  
A: Chat accounts are local cryptographic identities; each user creates their own local account and connects to a reachable mesh.

**Q: Why does a user appear offline after I click Refresh Online?**  
A: Refresh requests currently reachable signed presence. The client must be CONNECTED and that user must be online and reachable through the mesh; it does not search all historical accounts.

**Q: Why does my app reject the same relay IP after an AWS reinstall?**  
A: The relay key may have changed. Verify the new fingerprint independently, then use the GUI's **Verify / Update Relay Trust** button. Never disable identity checks just to connect.

**Q: Does Tor hide transactions or Alpaca traffic?**  
A: No. The mesh Tor-required mode protects the specified mesh outbound path; blockchain activity and market-data connections follow their own software/network configurations.

**Q: Why isn't my paper balance in my crypto vault?**  
A: Paper trading is a separate simulated SQLite ledger with fake starting funds. It cannot be cashed out or used as a real source of funds.

**Q: Is the Linux start script a complete Linux port?**  
A: It runs source in a Python virtual environment. A supported Linux package and device-specific test evidence have not been provided.

**Q: Does this package include an Android/Termux app?**  
A: Not as part of the original CRYPTO NOCTURNE GUI source. An experimental VaultForge CLI Termux port is separately distributed and must be evaluated independently.

**Q: What should I upload when reporting a bug?**  
A: The exact error message, OS/Python version, build log or sanitized service status, and reproduction steps. Never upload private keys, seeds, vaults, plaintext payment tokens or unredacted account databases.

### Glossary

- **Vault:** Encrypted local wallet container. A file's existence does not prove it was backed up successfully.
- **Signer:** The component holding or legitimately accessing keys that authorize a transaction; distinct from a watch-only address list.
- **RPC:** Application interface to an external node/wallet/provider such as Bitcoin Core or Monero wallet RPC.
- **Paper order:** Locally simulated trading action, not an exchange/broker order.
- **IEX feed:** A US equities market-data feed with coverage different from the full consolidated market.
- **Mesh peer:** A network participant connected using VaultForge's authenticated custom protocol.
- **Relay:** An online node forwarding authorized mesh traffic and potentially keeping public-room history.
- **Fingerprint/pin:** Locally remembered cryptographic identity for a trusted endpoint.
- **Bootstrap:** A known peer/node used to enter a mesh or discover opted-in public nodes.
- **LAN:** Local area network, generally private Wi-Fi or Ethernet subnets.
- **SOCKS5h:** Proxy scheme that asks the proxy to resolve hostnames rather than resolving directly on the client.
- **Regtest/stagenet:** Development/testing networks that must not be confused with live mainnets.
- **PyInstaller onedir:** Executable plus accompanying dependency folder, not just one `.exe` file.
- **Inno Setup:** Windows installer compiler used for the optional setup executable.
- **Release gate:** A specific verifiable condition required before claiming readiness to ship/support real-money users.

### Bundled specialist guides

- [`MESH_NETWORK_GUIDE.md`](MESH_NETWORK_GUIDE.md) — mesh desktop controls, connectivity, security and hosted nodes.
- [`MESH_UPDATE_2.7.1.md`](MESH_UPDATE_2.7.1.md) — room, roster and transfer corrections.
- [`GUI_RELAY_TRUST_UPDATE.md`](GUI_RELAY_TRUST_UPDATE.md) — GUI trust rotation procedure and safety.
- [`TRADING_TERMINAL.md`](TRADING_TERMINAL.md) — market modes, paper account and limits.
- [`CENTRAL_MARKET_SERVER.md`](CENTRAL_MARKET_SERVER.md) — optional HTTPS market backend integration.

### External project/provider documentation

- [Python](https://docs.python.org/3.12/) — Python 3.12 language/runtime.
- [PyInstaller](https://pyinstaller.org/) — Windows packaging (build on target OS).
- [Inno Setup](https://jrsoftware.org/isinfo.php) — Windows installer compiler.
- [Bitcoin Core](https://bitcoincore.org/en/doc/) — node and wallet RPC documentation.
- [Monero](https://www.getmonero.org/resources/developer-guides/) — developer and wallet RPC references.
- [Alpaca market data](https://docs.alpaca.markets/us/docs/about-market-data-api) — feed coverage and API documentation.
- [Alpaca streaming](https://docs.alpaca.markets/us/docs/streaming-market-data) — live subscription behavior.
- [Tor Project](https://support.torproject.org/) — Tor operation and onion-service concepts.
- [systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html) — Linux service definitions and management.

---

## Final release notice

**CRYPTO NOCTURNE is an ambitious source project, not a certified bank, exchange, broker, secure hardware wallet or audited communications suite.** Keep real private keys out of public repositories, use nonvaluable test environments for development, report exact failures, and close the external release gates before distributing a financial product to real users.

**The correct starting point for this source distribution is `START_WINDOWS.bat` to run the native desktop application and `BUILD_WINDOWS.bat` to compile it.** The dedicated AWS relay and market-data backend are distinct services; they are not installed by the desktop EXE builder.


## Automatic detection of changed relay fingerprints

See [FINGERPRINT_ROTATION.md](FINGERPRINT_ROTATION.md) for safe verification and one-endpoint trust update. A changed fingerprint is detected automatically but NEVER automatically trusted.
