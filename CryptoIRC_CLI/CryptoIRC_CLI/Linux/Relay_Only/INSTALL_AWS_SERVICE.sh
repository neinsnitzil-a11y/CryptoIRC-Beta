#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ${EUID} -eq 0 ]]; then echo 'Run as normal ubuntu user, not sudo bash.' >&2; exit 2; fi
./PREPARE_DATA_DIRS.sh relay
if [[ ! -x .venv/bin/python ]]; then ./install.sh; fi
# The service executes as this user, never as root.
./.venv/bin/python -I node_manager.py service-file > .vaultforge-mesh.service
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify .vaultforge-mesh.service || { echo "[ERROR] Invalid service file; no installed unit changed." >&2; exit 1; }
fi
sudo install -m 0644 .vaultforge-mesh.service /etc/systemd/system/vaultforge-mesh.service
sudo systemctl daemon-reload
sudo systemctl enable --now vaultforge-mesh.service
sudo systemctl --no-pager status vaultforge-mesh.service
