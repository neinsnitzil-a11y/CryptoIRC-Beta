@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -I node_manager.py status
pause
