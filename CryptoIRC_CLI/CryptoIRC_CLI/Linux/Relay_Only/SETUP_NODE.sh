#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
./PREPARE_DATA_DIRS.sh relay
if [[ ! -x .venv/bin/python ]]; then ./install.sh; fi
exec .venv/bin/python -I node_manager.py setup "$@"
