#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
NAME="${1:-PhoneRelay}"
MODE="${2:-lan}"
case "$MODE" in lan) LISTEN='0.0.0.0:7777';; wan) LISTEN='0.0.0.0:6667';; *) echo 'Usage: ./SETUP_PHONE_RELAY.sh NAME [lan|wan]' >&2; exit 2;; esac
# Use FULL CLI runtime for the phone relay too, never separate chat identities.
exec bash "$BASE/START_TERMUX.sh" node-setup --mode "$MODE" --name "$NAME" --listen "$LISTEN"
