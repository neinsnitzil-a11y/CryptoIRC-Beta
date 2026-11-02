#!/usr/bin/env bash
# Execute ON the Ubuntu EC2 instance as normal 'ubuntu' user, not from Windows.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if (( EUID == 0 )); then echo '[ERROR] Run without sudo; privilege escalation is only used for systemd.' >&2; exit 2; fi
ADDRESS="${1:-18.188.145.207:6667}"
if [[ "$ADDRESS" != *:6667 ]]; then echo '[WARN] Custom public endpoint: '"$ADDRESS"; fi
echo '[DATA] Creating or validating ~/VaultForge/mesh_chat before first setup.'
./PREPARE_DATA_DIRS.sh relay
DATA="$HOME/VaultForge/mesh_chat"
# Partial identity on a damaged server is NOT permission to replace the original key.
if [[ -f "$DATA/node.json" && ! -f "$DATA/node.secret" ]] ||
   [[ -f "$DATA/node.secret" && ! -f "$DATA/node.json" ]]; then
  echo '[ERROR] Partial existing node identity detected. Recover your original node.json/node.secret before continuing.' >&2
  exit 3
fi
if [[ ! -f "$DATA/node.json" && ( -e "$DATA/accounts.json" || -e "$DATA/known_peers.json" ) ]]; then
  echo '[ERROR] Existing chat data but no node.json; this may be a lost identity. Fresh node setup is blocked.' >&2
  echo '[ACTION] Recover node.json/node.secret from backup, or explicitly plan a new identity in a clean data root.' >&2
  exit 3
fi
printf '[AWS] Installing isolated relay-only Python runtime...\n' 
./install.sh
PY=.venv/bin/python
# Never overwrite the original node's private keys or node secret.
if [[ -f "$HOME/VaultForge/mesh_chat/node.json" ]]; then
  echo '[AWS] Existing node detected; keeping identity and updating its public advertisement.'
  "$PY" -I node_manager.py publish "$ADDRESS"
else
  "$PY" -I node_manager.py setup --mode wan --name AWSVaultRelay --listen 0.0.0.0:6667 --advertise "$ADDRESS" --yes
fi
# Avoid colliding with a manually started relay on the same port.
if ! sudo systemctl is-active --quiet vaultforge-mesh.service; then
  if command -v ss >/dev/null 2>&1 && ss -ltnH '( sport = :6667 )' | grep -q .; then
    echo '[PORT BUSY] Stop the OLD terminal relay on TCP 6667 before enabling the new service.' >&2
    echo '[ACTION] Do not run a manual relay and systemd relay on the same port.' >&2
    exit 2
  fi
fi
./INSTALL_AWS_SERVICE.sh
sudo systemctl restart vaultforge-mesh.service
sleep 2
sudo systemctl --no-pager --full status vaultforge-mesh.service || true
"$PY" -I node_health.py --port 6667
printf '\n[AWS] Configured advertised endpoint: %s\n' "$ADDRESS"
printf '[AWS] TCP 6667 must also be allowed in this instance EC2 Security Group from approved client IPs.\n'
printf '[AWS] SSH port 22 should remain restricted. View logs: sudo journalctl -u vaultforge-mesh -n 60 --no-pager\n'
printf '[AWS] The IP may change when EC2 stops/starts; use an Elastic IP or update your bootstrap endpoint.\n'
