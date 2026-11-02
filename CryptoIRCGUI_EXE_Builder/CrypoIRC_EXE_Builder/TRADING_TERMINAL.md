# CRYPTO NOCTURNE — Trading Terminal (Preview)

This module extends the existing CRYPTO NOCTURNE v4.5.1 desktop source with a native trading workspace. It is **paper trading only**. It **does not** place stock/crypto orders with a broker, exchange, or wallet. It does not move money, nor does it change fiat balances or encrypted wallet vaults. Existing wallet verification/recovery and payment release gates remain blocked as previously documented.

## 1. Install and launch

Extract the complete source release. From the application root on Windows, run `START_WINDOWS.bat`; it creates/reuses the isolated Windows Python runtime and installs `websockets` when missing. No global `pip` or `--break-system-packages` is needed. Select **Trading Terminal** in the WORKSPACE navigation. To compile the EXE, use `BUILD_WINDOWS.bat` with Python 3.12 and Inno Setup as the existing builder requires. A successful source test does not prove a compiled Windows installer works.

## 2. Market data modes

**SIMULATED DEMO** is the default, explicitly marked in green/purple. It creates artificial candles and animates them every five seconds. They are never real market quotes or forecasts. Buy/Sell here is simulated.

**ALPACA REAL DATA** reads historic bars over TLS and subscribes to Alpaca's authenticated WebSocket trade/bar feed. Before starting the app from PowerShell, configure YOUR OWN read-access Alpaca API keys for that PowerShell session:

```powershell
$env:ALPACA_API_KEY = "YOUR_MARKET_DATA_KEY"
$env:ALPACA_API_SECRET = "YOUR_MARKET_DATA_SECRET"
.\START_WINDOWS.bat
```

Do **not** paste credentials into chat logs, screenshots, source code or a publicly distributed EXE. The terminal reads them from the process environment; it does not store them in the watchlist or paper database. The feed uses TLS and doesn't intentionally send credentials to an inherited HTTP proxy. The trade interface is **not** linked to your Alpaca brokerage/paper account.

Real-time and historical market coverage are governed by your provider's license/subscription. The stock adapter uses the **IEX** feed (not all US exchanges). Crypto support is limited to symbols offered by Alpaca's crypto endpoint, e.g. `BTC/USD`, `ETH/USD`, `SOL/USD`; it does not claim to cover all 30 wallet networks or every token. Historical loading is bounded to one page of available bars; missing or older data remains labeled, not synthesized. WebSocket connection errors are surfaced as unavailable and retried with backoff. No direct connection or credential is sent to the VaultForge P2P relay.

This market data connection does not inherit Tor settings from the VaultForge mesh. Do not assume Tor anonymity or Tor fail-closed networking for stock/crypto market data.

## 3. Interface

The workspace has a symbol/category selector (stock or crypto), intervals (1Min, 5Min, 15Min, 1Hour, 1Day), OHLC candles (green up/red down), EMA-12/EMA-26, volume bars, RSI-14, an editable watchlist, and a separate paper portfolio and order history. Use the mouse wheel over the chart to zoom the visible candle window. Hover a bar for OHLC values.

The chart updates from a live feed when available; for higher timeframes, the websocket receives 1-minute events and updates the displayed reference price, while the timeframe's historical chart does not automatically reaggregate every streamed tick. Market feed timestamps and age matter: a 1-minute IEX feed may contain no fresh trades after exchange hours.

The watchlist stores symbols and asset types, not streaming quotes for every watchlist row. Double-click a symbol to open its chart; use Add or Remove to edit. It defaults to a few example stocks/crypto pairs. There is no options-chain, Level II orderbook or full screener in this preview.

## 4. Buy and sell (paper only)

Set a quantity and click **PAPER BUY** or **PAPER SELL**. Review and approve the simulated order. Paper fills are executed locally at the latest fresh reference price (must be no older than 120 seconds), with cash and positions updated in the paper database. There are **no commissions, market impact, spreads, slippage, latency, margin, short-selling or live brokerage fills** in the simulator, so simulated results can be substantially different from real-world execution.

Default starting balance is **$100,000 of simulated cash**. It is not your real money or wallet balance. You cannot deposit, withdraw or cash out paper dollars.

Paper records are stored under:

- Windows: `%LOCALAPPDATA%\CRYPTO_NOCTURNE\paper_trading\paper.db`
- Linux/macOS dev: `$XDG_DATA_HOME/CRYPTO_NOCTURNE/paper_trading/paper.db` or `~/.local/share/CRYPTO_NOCTURNE/paper_trading/paper.db`

Watchlist: `watchlist.json` in the same folder. These files contain simulated orders, not wallet private keys. Back them up for training history. Never mix paper balances with the application's fiat ledger or verified wallet balances.

## 5. Security and troubleshooting

- **No chart data:** Choose SIMULATED DEMO or supply valid Alpaca market-data credentials; click LOAD CHART. A data feed that excludes your selected symbol may return no bars.
- **Market stream unavailable:** Check credentials, provider entitlement, internet/TLS, rate limits, and market hours. Check network restrictions rather than disabling TLS verification.
- **Order rejected: stale quote:** Wait for a fresh trade/candle; never assume an old price can execute now. Demo mode animates synthetic quotes every five seconds.
- **Insufficient paper holdings or cash:** No short selling and no negative cash in the simulator.
- **Watchlist errors:** Invalid symbols are rejected. The watchlist is local to this computer; it is not synchronized over your AWS mesh.
- **No real-money trading:** This module intentionally does not contain live broker order placement. Separate broker authorization, account connectivity, order-state reconciliation, independent tests, credential controls, and regulatory checks are necessary before real orders can be considered.

## 6. What is still missing for the complete platform

Cross-venue market aggregation, paid all-exchange consolidated equity feeds, price-alert engine, more indicators/drawings, synced watchlists, scanners, advanced order tickets, paper order types beyond market, slippage/fees modelling, broker paper-account integration, options analytics, true live execution and reconciliation, failover/rate-limit dashboards, external audit, signed Windows builds, and legal/broker permissions.

### Source boundaries

- `src/market_terminal.py`: data parsing, technical indicators, read-only market feed, synthetic demo and isolated SQLite paper ledger.
- `src/trading_terminal_ui.py`: Tk chart, watchlist and paper-order UI. No wallet keys or broker order code.
- `src/tests/test_trading_terminal_v46.py`: offline unit tests for symbols, candles, indicators, market response shape, paper funds and storage.

## 7. Official API references

- https://docs.alpaca.markets/us/docs/about-market-data-api
- https://docs.alpaca.markets/us/docs/streaming-market-data
- https://docs.alpaca.markets/us/docs/real-time-crypto-pricing-data
- https://docs.alpaca.markets/us/reference/stockbars
- https://docs.alpaca.markets/us/reference/cryptobars-1
