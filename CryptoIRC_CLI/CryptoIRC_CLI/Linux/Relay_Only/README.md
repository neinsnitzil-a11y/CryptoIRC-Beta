> **Current AWS bootstrap fix:** Read `INSTALL_AND_NODE_SETUP_FIX.md` in the full CLI root or `README_SETUP_FIX.md` in the AWS Launcher. A created `~/VaultForge` folder is **not** an initialized server identity. Use guided first-run setup.

# VaultForge Relay-Only v2.7.1 — AWS / Linux Server Manual

This folder is the **chat relay only**: it does not install the wallet generator, Bitcoin Core, Monero or cryptocurrency keys. It uses the same encrypted VaultForge mesh protocol as the Windows/Linux v2.7.1 CLI.

For the **complete CLI and server manual**, see `../../README.md` from the root of the full package, especially sections 6–18, 27–31. This README remains usable if the `Relay_Only/` folder is uploaded to AWS by itself.

## New Ubuntu EC2 installation

1. Create an Ubuntu EC2 server, keep port **22/SSH** restricted to trusted administration IPs and configure inbound **TCP 6667** for approved chat clients. Configure public access only after appropriate hardening. Record the instance's **Public IPv4**; private `172.31.x.x` is not a public peer address.
2. Upload **only this folder** or the matching small standalone relay ZIP to the instance. Do not upload wallet vaults, mnemonics, EC2 SSH private keys, or Bitcoin RPC credentials.
3. From the extracted relay folder, as user `ubuntu` (not root):

```bash
chmod +x *.sh
./install.sh
./AWS_QUICK_SETUP.sh YOUR_PUBLIC_IP:6667
```

The installer uses isolated Python 3.12 and the chat dependencies. The setup creates a private relay chat identity (if one is not already present), stores an owner-only node password, publishes an opt-in signed endpoint and installs the systemd service with elevated permissions only where necessary. The AWS security group is managed **separately** in AWS Console.

## Existing AWS node: preserve identity and service

If `vaultforge-mesh.service` already runs, **do not create a new identity or run fresh-node setup**. To install the matching v2.7.1 roster/history/room-file update, use the separately distributed `VaultForge_AWS_Relay_v2.7.1_Roster_Fix.zip` in the **current service source directory**, then run `./APPLY_AWS_MESH_271.sh`. The updater checks the service's path, backs up protocol modules, restarts and attempts rollback if necessary. Keep `~/VaultForge/mesh_chat/node.json`, `node.secret`, `accounts.json`, identity keys and history.

Find the active source location first:

```bash
sudo systemctl cat vaultforge-mesh
sudo systemctl status vaultforge-mesh --no-pager
```

## Service commands

```bash
sudo systemd-analyze verify /etc/systemd/system/vaultforge-mesh.service
sudo systemctl enable --now vaultforge-mesh
sudo systemctl status vaultforge-mesh --no-pager
sudo ss -lntp | grep ':6667'
sudo journalctl -u vaultforge-mesh -n 60 --no-pager
sudo systemctl restart vaultforge-mesh
sudo systemctl stop vaultforge-mesh
sudo systemctl start vaultforge-mesh
```

If systemd reports **bad unit file setting**, inspect the generated unit and use the previously supplied v2.6.1 **systemd service hotfix** as appropriate. Do not delete the chat identity to repair a unit syntax error. Only one process can bind `0.0.0.0:6667`; stop old manually launched relays before enabling the service. Systemd `enable` starts after an EC2 reboot but cannot prevent AWS instance suspension or credit expiration.

## Test an external client

Windows PowerShell:

```powershell
Test-NetConnection YOUR_PUBLIC_IP -Port 6667
```

Inside a Windows/Linux v2.7.1 VaultForge chat: use **21 → 1**, enter `YOUR_PUBLIC_IP:6667`, make a **local chat account**, then run `/peers`, `/users`, `/join #general` and send a test message. Validate a second distinct client and a DM/file transfer before considering the deployment healthy. `TcpTestSucceeded : True` proves TCP reachability only, not an authenticated mesh handshake.

## Public discovery

Publishing `PUBLIC_IP:6667` opts into signed public-node announcements but **does not** auto-scan the internet or establish that a host is trustworthy/reachable. For discovery through the AWS bootstrap, another host should establish a peer path to this node and explicitly advertise itself. When no bootstrap exists, exchange a reachable peer address directly. The default endpoint from this project has been `18.188.145.207:6667` but may change if the EC2 public IP changes.

## History, files and privacy

The history-capable relay caches a **limited** set of public channel messages (up to 40 per room, up to 7 days; up to 25 replayed per query). Public-channel history is plaintext on the relay and visible to the operator. DMs and attachments are recipient-encrypted in the experimental custom protocol; files are accepted on the receiving client, not a server-hosted cloud drive. There is no offline queue or independent cryptographic audit. A server operator can see sensitive room traffic and metadata. Do not post wallet secrets or personal data to channels.

## Troubleshooting

- **Connection refused:** is the service active and listening? `sudo ss -lntp | grep 6667`.
- **Connection timeout:** verify current public IP, attached security group, TCP 6667 inbound rule and remote client's public IP, subnet routing, network ACLs, host firewall, ISP restrictions.
- **Local works, remote fails:** capture `sudo timeout 40 tcpdump -ni ens5 'tcp port 6667'` while the remote client tries.
- **Password issue:** CLI chat accounts are **local to each device**. Connecting to AWS does not log into the AWS node's own chat account.
- **Roster empty:** use `/peers` and check version compatibility; users must be simultaneously reachable through a connected mesh.
- **New-node setup says identity exists:** this is protective; **reuse** the original node and use the update workflow instead of deleting accounts.

**Security warning:** This is an experimental, unaudited public network protocol. Harden and monitor the service before exposing TCP 6667 to `0.0.0.0/0`. Never open Bitcoin RPC or other wallet administrative ports publicly. Restrict SSH TCP 22 to authorized administration IP addresses.


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
