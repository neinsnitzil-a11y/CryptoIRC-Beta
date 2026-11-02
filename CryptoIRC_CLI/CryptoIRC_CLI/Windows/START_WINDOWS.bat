@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title VaultForge Unified CLI
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run INSTALL_WINDOWS.bat once before launching.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -I "vaultforge.py" %*
if errorlevel 1 (
  echo [INFO] VaultForge exited with an error. Check the text above.
)
pause
