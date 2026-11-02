#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec bash "$BASE/START_TERMUX.sh" node-stop
