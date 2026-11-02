#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then ./install_linux.sh; fi
exec .venv/bin/python -I node_manager.py start "$@"
