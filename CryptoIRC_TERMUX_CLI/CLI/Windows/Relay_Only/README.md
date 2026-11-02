# Windows chat-only relay source

Use Python 3.12 and PowerShell, **not removed BAT wrappers**. From this directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1
.\.venv\Scripts\python.exe -I .\node_manager.py --help
```

Check `node_manager.py --help` for the supported setup, start, stop and status commands. User identity and chat accounts are local. Do not copy or publish node secrets or wallets. See repository root README and `docs/`.
