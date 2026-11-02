@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title VaultForge Unified - Automatic Python 3.12 Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"
if errorlevel 1 goto fail
echo [OK] Installation complete. Run START_WINDOWS.bat.
pause
exit /b 0
:fail
echo [ERROR] Installation incomplete. See the details above.
pause
exit /b 1
