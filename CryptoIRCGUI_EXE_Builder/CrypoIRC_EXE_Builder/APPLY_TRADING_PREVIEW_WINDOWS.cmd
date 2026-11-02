@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
if not exist "%ROOT%src\crypto.py" (
  echo [ERROR] Extract this patch beside the source folder containing src\crypto.py
  pause
  exit /b 1
)
if not exist "%ROOT%src\mesh_gui.py" (
  echo [ERROR] This update requires CRYPTO NOCTURNE v4.5.1 Mesh GUI source.
  pause
  exit /b 1
)
if not exist "%ROOT%UPDATE_TRADING_FILES\src\crypto.py" (
  echo [ERROR] Missing UPDATE_TRADING_FILES directory.
  pause
  exit /b 1
)
set "BACKUP=%ROOT%TRADING_UPDATE_BACKUP"
if not exist "%BACKUP%" mkdir "%BACKUP%"
for %%F in (crypto.py build_release.py requirements.txt CRYPTO_NOCTURNE.spec) do (
  if exist "%ROOT%src\%%F" if not exist "%BACKUP%\%%F" copy /Y "%ROOT%src\%%F" "%BACKUP%\%%F" >nul
)
if exist "%ROOT%START_WINDOWS.bat" if not exist "%BACKUP%\START_WINDOWS.bat" copy /Y "%ROOT%START_WINDOWS.bat" "%BACKUP%\START_WINDOWS.bat" >nul
for %%F in (crypto.py build_release.py requirements.txt CRYPTO_NOCTURNE.spec market_terminal.py trading_terminal_ui.py) do (
  copy /Y "%ROOT%UPDATE_TRADING_FILES\src\%%F" "%ROOT%src\%%F" >nul
  if errorlevel 1 (echo [ERROR] Could not update %%F & pause & exit /b 1)
)
copy /Y "%ROOT%UPDATE_TRADING_FILES\src\tests\test_trading_terminal_v46.py" "%ROOT%src\tests\test_trading_terminal_v46.py" >nul
if errorlevel 1 (echo [ERROR] Could not update regression test & pause & exit /b 1)
copy /Y "%ROOT%UPDATE_TRADING_FILES\START_WINDOWS.bat" "%ROOT%START_WINDOWS.bat" >nul
copy /Y "%ROOT%UPDATE_TRADING_FILES\TRADING_TERMINAL.md" "%ROOT%TRADING_TERMINAL.md" >nul
echo.
echo [OK] Trading Terminal source installed. Backups are in TRADING_UPDATE_BACKUP.
echo Run START_WINDOWS.bat to launch or BUILD_WINDOWS.bat to compile an EXE.
echo SIMULATED DEMO is the default. THIS DOES NOT PLACE REAL TRADES.
pause
