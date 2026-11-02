@echo off
setlocal EnableExtensions
rem Use UTF-8 in builder processes even when Windows uses legacy cp1252.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "SRC=%~dp0src"
set "VENV=%LOCALAPPDATA%\CRYPTO_NOCTURNE\builder-v2.3"
if not exist "%SRC%\build_release.py" (echo [ERROR] Missing build files. & pause & exit /b 1)
if not exist "%VENV%\Scripts\python.exe" (
  echo [SETUP] Preparing Windows EXE + Inno Setup compiler...
  where py >nul 2>&1
  if not errorlevel 1 (py -3.12 -m venv "%VENV%") else (python -m venv "%VENV%")
  if not exist "%VENV%\Scripts\python.exe" (echo [ERROR] Install Python 3.12 64-bit. & pause & exit /b 1)
)
"%VENV%\Scripts\python.exe" -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32, 'Python 3.12 64-bit required'"
if errorlevel 1 (echo [ERROR] Python 3.12 64-bit required. & pause & exit /b 1)
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%SRC%\requirements.txt" "pyinstaller>=6.10,<7"
if errorlevel 1 (echo [ERROR] Build dependency installation failed. & pause & exit /b 1)
cd /d "%SRC%"
"%VENV%\Scripts\python.exe" builder_gui.py
if errorlevel 1 (echo [ERROR] Compiler GUI failed. & pause & exit /b 1)
