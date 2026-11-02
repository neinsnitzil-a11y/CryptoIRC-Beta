# Publish CryptoIRC_TERMUX_CLI to GitHub

1. Extract the ZIP into a clean folder. Do not extract on top of existing local wallet data.
2. Inspect files, embedded demonstration addresses, sources and licenses. A `LICENSE` has deliberately not been asserted; the rights holder must select one with appropriate rights and third-party compliance.
3. Run syntax/test steps from the platform guides; do not treat offline tests as an independent security audit.
4. In the extracted `CryptoIRC_TERMUX_CLI` root:

```bash
git init
git branch -M main
git add .
git status --short
git diff --cached --name-only
git commit -m "Publish CryptoIRC_TERMUX_CLI source"
git remote add origin https://github.com/YOUR_ACCOUNT/CryptoIRC_TERMUX_CLI.git
git push -u origin main
```

Stop if `git status` includes `.vault`, node keys, accounts, wallet data, chat logs or private API credentials. `.gitignore` is a defense-in-depth measure, not a guarantee.

This independent distribution includes the full Windows/Linux CLI source and a self-contained Termux mesh chat/relay engine. It does not include the CRYPTO NOCTURNE GUI, market server, or the systemd-based AWS server manager.
