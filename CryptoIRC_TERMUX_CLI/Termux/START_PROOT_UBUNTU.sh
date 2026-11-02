#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
if ! command -v proot-distro >/dev/null 2>&1; then
  echo '[ERROR] Ubuntu compatibility runtime not installed.' >&2; exit 1
fi
# Dedicated PRoot home, distinct from native Termux vault/identity data.
exec proot-distro login ubuntu --user cryptoirc -- /bin/bash -lc 'cd "$HOME/CryptoIRC" && exec ./start_linux.sh'
