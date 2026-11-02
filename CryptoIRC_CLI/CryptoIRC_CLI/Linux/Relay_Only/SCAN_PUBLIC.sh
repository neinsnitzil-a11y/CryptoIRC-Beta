#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ -x .venv/bin/python ]] || ./install.sh
exec .venv/bin/python -I mesh_chat.py --scan-public --bootstrap "${1:-18.188.145.207:6667}"
