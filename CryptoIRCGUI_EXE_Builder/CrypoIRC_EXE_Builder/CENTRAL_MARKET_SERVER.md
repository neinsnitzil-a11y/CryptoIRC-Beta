# CRYPTO NOCTURNE — Central Market Service for All Desktop Users

The admin sets up a **separate AWS read-only market server** once. Then the admin includes a public HTTPS market URL in the Windows build. **End users do not need their own Alpaca key for charts.**

**This does not enable real trades.** Users' on-device `PaperLedger` continues to simulate orders, and every real brokerage account would require user-specific authorization through a proper broker OAuth flow.

## Steps
1. Get lawful **data display/redistribution permissions** for the feed. Basic provider API access may be personal-use only; do not assume stock exchange rights.
2. Upload `CRYPTO_NOCTURNE_AWS_Market_Server.zip` separately to EC2. It installs as `nocturne-market.service` on localhost TCP 8787; it does **not** alter your IRC relay on TCP 6667.
3. Set a DNS A record for e.g. `markets.yourdomain.com` to your AWS public IP, and configure HTTPS with Caddy on port 443.
4. Run `python CONFIGURE_MARKET_SERVICE.py https://markets.yourdomain.com` in the *source package root*, not inside `src`.
5. Rebuild with `BUILD_WINDOWS.bat` and distribute this revised build. The URL is non-secret and is bundled at `src/data/market_server.json`.
6. Users select **Trading Terminal**. They see **NOCTURNE SERVER** by default. It polls the read-only server every 20 seconds. No provider key is required on users' PCs.

## What the server returns
`GET /health` — no secrets, server status. `GET /api/v1/bars?symbol=AAPL&market=stock&timeframe=1Min&limit=120` — licensed or clearly labeled simulated bars. `GET /api/v1/latest?symbol=BTC%2FUSD&market=crypto` — latest available bar, with source/mode.

## Security and limitations
- End-user devices **never receive the provider's API key or secret**.
- Only HTTPS with a valid certificate is accepted by the desktop. No plain HTTP fallback.
- The current server is read-only: **no brokerage login, payments, wallets, or order endpoints**.
- Polling isn't full exchange-tick streaming. IEX stock feed is not the full US consolidated market.
- Keys belong solely on AWS in the private `.market.env` environment file, not in an installer or the AWS mesh relay.
- Public market-data redistribution needs provider/exchange contractual permission. The AWS server starts in **synthetic demo** mode unless explicitly authorized and configured.
- Live trading should be a separate future integration using per-user approved broker OAuth and verified order processing.
