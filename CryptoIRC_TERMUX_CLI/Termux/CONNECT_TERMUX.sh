#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$BASE/.venv/bin/python"
[[ -x "$PY" ]] || { echo '[ERROR] Install full Termux runtime first.' >&2; exit 1; }
"$PY" -I "$BASE/termux_preflight.py" --full || exit 1
if [[ -n "${1:-}" ]]; then
  exec "$PY" -I "$BASE/app/vaultforge.py" chat --listen '127.0.0.1:0' --peer "$1"
fi
# No argument: connect to the locally saved active server (defaults to the new AWS relay).
exec "$PY" -I "$BASE/app/vaultforge.py" chat --listen '127.0.0.1:0' 
