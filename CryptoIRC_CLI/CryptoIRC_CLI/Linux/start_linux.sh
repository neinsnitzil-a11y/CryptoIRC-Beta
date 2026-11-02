#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# A brand-new extraction must work without manual Python installation.
# Existing incompatible environments are preserved by install_runtime.py.
if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import sys; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3,12)' >/dev/null 2>&1; then
  echo '[SETUP] A supported Python 3.12 environment is missing; starting the installer.'
  ./install_linux.sh
fi
if [[ "${1:-}" == "node-setup" ]]; then shift; exec .venv/bin/python -I node_manager.py setup "$@"; fi
if [[ "${1:-}" == "node-start" ]]; then shift; exec .venv/bin/python -I node_manager.py start "$@"; fi
if [[ "${1:-}" == "node-stop" ]]; then shift; exec .venv/bin/python -I node_manager.py stop "$@"; fi
if [[ "${1:-}" == "node-status" ]]; then shift; exec .venv/bin/python -I node_manager.py status "$@"; fi
exec .venv/bin/python -I vaultforge.py "$@"
