@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run INSTALL_WINDOWS.bat first.&pause&exit /b 1)
".venv\Scripts\python.exe" -I mesh_chat.py --scan
pause
