@echo off
setlocal
cd /d "%~dp0"
if not exist "src\crypto.py" (
  echo [ERROR] Put this patch in the existing CRYPTO NOCTURNE source folder, next to BUILD_WINDOWS.bat.
  pause
  exit /b 1
)
if not exist "src\trading_terminal_ui.py" (
  echo [ERROR] Trading Terminal source is missing. Apply the Trading Terminal release first.
  pause
  exit /b 1
)
echo [OK] Source files are present. Central market-service integration is available.
echo [ACTION] Set a public HTTPS market URL using:
echo          py -3.12 CONFIGURE_MARKET_SERVICE.py https://markets.YOUR_DOMAIN.com
echo [ACTION] Build with BUILD_WINDOWS.bat after configuring the URL.
echo [NOTE] Existing wallet and paper-trading data were not touched.
pause
