@echo off
setlocal EnableExtensions
set "SRC=%~dp0src"
set "VENV=%LOCALAPPDATA%\CRYPTO_NOCTURNE\runtime-v2.3"
if not exist "%SRC%\crypto.py" (echo [ERROR] Missing application source. & pause & exit /b 1)
if not exist "%VENV%\Scripts\python.exe" (
  echo [SETUP] Configuring CRYPTO NOCTURNE for first run...
  where py >nul 2>&1
  if not errorlevel 1 (py -3.12 -m venv "%VENV%") else (python -m venv "%VENV%")
  if not exist "%VENV%\Scripts\python.exe" (echo [ERROR] Install Python 3.12 64-bit. & pause & exit /b 1)
  "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%SRC%\requirements.txt"
  if errorlevel 1 (echo [ERROR] Dependency install failed. & pause & exit /b 1)
)
rem Existing installations may have an older venv with no market stream support.
"%VENV%\Scripts\python.exe" -c "import websockets.sync.client" >nul 2>&1
if errorlevel 1 (
  echo [UPDATE] Installing verified market-stream dependency in the private runtime...
  "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%SRC%\requirements.txt"
  if errorlevel 1 (echo [ERROR] Market dependency install failed. & pause & exit /b 1)
)
cd /d "%SRC%"
"%VENV%\Scripts\python.exe" crypto.py
if errorlevel 1 (echo [ERROR] Application exited unexpectedly. & pause & exit /b 1)
