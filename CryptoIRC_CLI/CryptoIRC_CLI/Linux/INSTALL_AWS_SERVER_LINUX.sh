#!/usr/bin/env bash
# Install and start a standalone AWS relay from the full CLI package.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/Relay_Only"
exec ./SETUP_OR_RESTORE_AWS.sh "$@"
