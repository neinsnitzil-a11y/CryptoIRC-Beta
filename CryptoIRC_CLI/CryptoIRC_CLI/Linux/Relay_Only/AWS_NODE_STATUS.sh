#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
sudo systemctl --no-pager status vaultforge-mesh.service || true
sudo ss -ltnp | grep ':6667' || true
if [[ -x .venv/bin/python ]]; then .venv/bin/python -I node_health.py --port 6667; fi
