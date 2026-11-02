# Run your own mesh node on a laptop/desktop

Every full CLI installation can host a node and also connect outbound as a client. A hosted node is not the same thing as a chat user account. Keep each installation's identity private and independent.

## Windows LAN host

```powershell
cd CLI/Windows
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1
.\.venv\Scripts\python.exe -I node_manager.py setup --mode lan --name LaptopRelay --listen 0.0.0.0:7777
.\.venv\Scripts\python.exe -I node_manager.py start
.\.venv\Scripts\python.exe -I node_manager.py status
```

On another laptop or phone on the **same Wi-Fi**, connect to your Windows laptop's LAN IP on TCP 7777. Limit Windows Defender Firewall access to the private network. Ensure the machine will not sleep; check process status after logout/reboot. To stop: `.\.venv\Scripts\python.exe -I node_manager.py stop`.

## Linux laptop LAN host

```bash
cd CLI/Linux
bash ./install_linux.sh
./SETUP_NODE_LINUX.sh --mode lan --name LaptopRelay --listen 0.0.0.0:7777
./HOST_RELAY_LINUX.sh
./NODE_STATUS_LINUX.sh
# Stop with ./STOP_NODE_LINUX.sh
```

## Hosting publicly from home

Use `--mode wan --listen 0.0.0.0:6667` and your real public endpoint for a freshly configured node, then open TCP 6667 only as needed on the host firewall and router (forward to a stable LAN address). Ordinary consumer ISP CGNAT may make inbound TCP impossible. A VPS is generally more reliable for a public mesh relay. Protect public chat nodes with basic host security, backups and monitoring.

**Do not rerun `node_manager.py setup` to replace an existing identity.** Peer trust pins must be verified before changes; never connect a relay outbound to its own advertised endpoint. 

For hosting a *dedicated AWS/VPS systemd relay*, use the other `CryptoIRC_CLI` package, which includes the Server/ service installer.
