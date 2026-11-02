#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# This starts background process via node manager. Android may kill it.
exec bash "$BASE/START_TERMUX.sh" node-start
