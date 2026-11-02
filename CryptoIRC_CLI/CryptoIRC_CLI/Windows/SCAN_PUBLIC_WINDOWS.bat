@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call INSTALL_WINDOWS.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -I mesh_chat.py --scan-public %*
pause
