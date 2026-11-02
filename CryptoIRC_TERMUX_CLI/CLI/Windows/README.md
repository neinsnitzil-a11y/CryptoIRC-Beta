# VaultForge Windows CLI

The full wallet/mesh CLI is retained in this folder. It is a **separate console app** from the CRYPTO NOCTURNE desktop application.

Open PowerShell here:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_cli.ps1
```

Python 3.12 is installed/reused in a local virtual environment by the installer. Keep it in the Windows source folder; do not run as Administrator.

To host a LAN node (after installation):

```powershell
.\.venv\Scripts\python.exe -I .\node_manager.py setup --mode lan --name MyLaptop --listen 0.0.0.0:7777
.\.venv\Scripts\python.exe -I .\node_manager.py start
.\.venv\Scripts\python.exe -I .\node_manager.py status
```

**WAN hosting:** Use the app's Mesh Chat hosting menu and configure your firewall/router or use the standalone [Server guide](../../docs/VPS_AWS_SERVER.md). Do not recreate an established identity or disable identity pinning.

[Installation guide](../../docs/WINDOWS_FROM_SCRATCH.md) · [Chat commands](../../docs/MESH_CHAT_COMMANDS.md)
