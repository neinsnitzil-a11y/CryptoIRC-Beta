#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ -x .venv/bin/python ]] || ./install_linux.sh
if [[ $# -gt 0 ]]; then
  exec .venv/bin/python -I mesh_chat.py --scan-public --bootstrap "$1"
fi
exec .venv/bin/python -I mesh_chat.py --scan-public
