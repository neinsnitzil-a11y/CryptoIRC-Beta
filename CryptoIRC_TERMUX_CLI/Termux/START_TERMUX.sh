#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$BASE/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo '[ERROR] Full Termux Python runtime missing. Run bash Termux/INSTALL_TERMUX.sh' >&2; exit 1
fi
"$PY" -I "$BASE/termux_preflight.py" --full || { echo '[ERROR] Full wallet not available. Use INSTALL_PROOT_UBUNTU.sh as an alternative.' >&2; exit 1; }
case "${1:-}" in
  node-setup) shift; exec "$PY" -I "$BASE/app/node_manager.py" setup "$@" ;;
  node-start) shift; exec "$PY" -I "$BASE/app/node_manager.py" start "$@" ;;
  node-stop) shift; exec "$PY" -I "$BASE/app/node_manager.py" stop "$@" ;;
  node-status) shift; exec "$PY" -I "$BASE/app/node_manager.py" status "$@" ;;
esac
exec "$PY" -I "$BASE/app/vaultforge.py" "$@"
