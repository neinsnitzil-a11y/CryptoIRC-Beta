@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0INSTALL_WINDOWS.bat"
  if errorlevel 1 exit /b 1
)
set "ENDPOINT=%~1"
if "%ENDPOINT%"=="" set "ENDPOINT=18.188.145.207:6667"
".venv\Scripts\python.exe" -I connection_diagnostics.py "%ENDPOINT%" --connect
if errorlevel 1 (
  echo [HELP] Check AWS security group inbound TCP 6667, relay systemd status, IP/port, and remote fingerprint.
)
pause
