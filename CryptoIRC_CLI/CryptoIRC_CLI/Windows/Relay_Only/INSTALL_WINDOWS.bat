@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"
if errorlevel 1 (echo [ERROR] Install failed.&pause&exit /b 1)
echo [OK] Chat-only relay ready.
pause
