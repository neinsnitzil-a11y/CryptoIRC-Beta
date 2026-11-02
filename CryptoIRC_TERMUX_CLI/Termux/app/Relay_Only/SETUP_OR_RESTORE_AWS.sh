#!/usr/bin/env bash
# VaultForge AWS guided installation/recovery. Existing node identity is never regenerated.
set -Eeuo pipefail
umask 077
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP_SOURCE="$SCRIPT_DIR/RELAY_SOURCE"
[[ -d "$APP_SOURCE" ]] || APP_SOURCE="$SCRIPT_DIR"
DATA="${VAULTFORGE_DATA_ROOT:-$HOME/VaultForge}/mesh_chat"
APP="${VAULTFORGE_RELAY_ROOT:-$HOME/IRC/Relay_Only}"
UNIT='vaultforge-mesh.service'
ENDPOINT="${VAULTFORGE_AWS_ENDPOINT:-18.188.145.207:6667}"
MODE="${1:-install}"
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 2; }
[[ "${EUID}" -ne 0 ]] || fail 'Run as normal ubuntu user, NOT with sudo. sudo is used only for systemd.'
[[ -n "$HOME" && "$HOME" == /* ]] || fail 'HOME is not an absolute path.'
[[ -f "$APP_SOURCE/node_manager.py" && -f "$APP_SOURCE/install.sh" ]] || fail "Missing relay source in $APP_SOURCE. Extract complete bundle."
[[ "$DATA" == /* && "$APP" == /* && "$DATA" != / && "$APP" != / ]] || fail 'Invalid installation path.'
for path in "${DATA%/mesh_chat}" "$DATA" "$APP" "$APP_SOURCE"; do
  [[ ! -L "$path" ]] || fail "Symlinked root rejected: $path"
done
if [[ -d "$DATA" && ! -O "$DATA" ]]; then fail "Node storage is not owned by $USER: $DATA"; fi
if [[ -d "$APP" && ! -O "$APP" ]]; then fail "Relay program directory is not owned by $USER: $APP"; fi
# Do not infer that the lack of node.json proves there was never an old identity.
identity_state() {
 local json="$DATA/node.json" secret="$DATA/node.secret" accounts="$DATA/accounts.json"
 if [[ -f "$json" && -f "$secret" && -f "$accounts" ]]; then echo existing; return; fi
 if [[ -e "$json" || -e "$secret" || -e "$accounts" || -e "$DATA/known_peers.json" ]]; then echo partial; return; fi
 echo empty
}
state="$(identity_state)"
printf '[DATA] %s\n[RELAY PROGRAM] %s\n[IDENTITY] %s\n' "$DATA" "$APP" "$state"
if [[ "$MODE" == '--diagnose' ]]; then
 for file in node.json node.secret accounts.json; do
  if [[ -f "$DATA/$file" ]]; then echo "[FOUND] $file"; else echo "[MISSING] $file"; fi
 done
 if [[ -x "$APP/.venv/bin/python" ]]; then echo '[RUNTIME] Available'; else echo '[RUNTIME] Missing'; fi
 if command -v systemctl >/dev/null 2>&1 && systemctl cat "$UNIT" >/dev/null 2>&1; then echo '[SERVICE] Installed'; else echo '[SERVICE] Missing'; fi
 exit 0
fi
if [[ "$state" == partial ]]; then
 fail "Incomplete old identity in $DATA. Recovery required; DO NOT create a replacement. Look for backups of node.json, node.secret, accounts.json."
fi
# Preserve old identity. Never silently generate new private keys, even when all identity files are absent.
if [[ "$state" == empty && "$MODE" != '--prepare-only' ]]; then
 echo '[NEW NODE REQUIRED] The VaultForge directories are not the node identity.'
 echo '[WARNING] Your previous AWSVaultRelay fingerprint cannot be recovered by making empty folders.'
 echo '[WARNING] If you have an existing relay identity/backups elsewhere, STOP and restore them instead.'
 echo '[WARNING] A NEW relay identity requires connected clients to verify and update pinned trust.'
 read -r -p 'Type CREATE NEW RELAY to authorize a NEW identity, or press Enter to cancel: ' confirmation || fail 'Confirmation unavailable.'
 [[ "$confirmation" == 'CREATE NEW RELAY' ]] || fail 'No identity created. Locate backups or rerun to authorize new identity.'
fi
# Folder initialization is deliberately distinct from identity initialization.
if [[ -f "$SCRIPT_DIR/PREPARE_DATA_DIRS.sh" ]]; then
 bash "$SCRIPT_DIR/PREPARE_DATA_DIRS.sh" relay
elif [[ -f "$APP_SOURCE/PREPARE_DATA_DIRS.sh" ]]; then
 bash "$APP_SOURCE/PREPARE_DATA_DIRS.sh" relay
else
 fail 'Data-folder initializer missing.'
fi
if [[ "$MODE" == '--prepare-only' ]]; then
 printf '[PREPARED] Root: %s\n' "${DATA%/mesh_chat}"
 printf '[NEXT] Run ./SETUP_OR_RESTORE_AWS.sh to configure the server, not just its directories.\n'
 exit 0
fi
# Restore ONLY absent program files. Existing source and node data are never overwritten.
mkdir -p -- "$APP"
for source in "$APP_SOURCE"/*; do
 [[ -f "$source" ]] || continue
 name="${source##*/}"
 dest="$APP/$name"
 [[ ! -L "$dest" ]] || fail "Refusing symlinked file: $dest"
 if [[ ! -e "$dest" ]]; then install -m 600 -- "$source" "$dest"; fi
done
chmod +x "$APP"/*.sh
if [[ -e "$APP/.venv" && -L "$APP/.venv" ]]; then fail 'Symbolic-link virtual environment refused.'; fi
if [[ ! -x "$APP/.venv/bin/python" ]] || ! "$APP/.venv/bin/python" -c 'import sys, cryptography, argon2, socks; assert sys.version_info[:2]==(3,12)' >/dev/null 2>&1; then
 echo '[INSTALL] Restoring isolated Python 3.12 and relay dependencies...'
 ( cd "$APP" && bash ./install.sh ) || fail 'Python dependency setup failed. No systemd changes were made.'
fi
PY="$APP/.venv/bin/python"
[[ -x "$PY" ]] || fail "Python executable missing after install: $PY"
if [[ "$state" == empty ]]; then
 echo '[INITIALIZE] Creating a new AWS relay identity (explicitly approved above)...'
 ( cd "$APP" && "$PY" -I node_manager.py setup --mode wan --name AWSVaultRelay --listen 0.0.0.0:6667 --advertise "$ENDPOINT" --yes ) || fail 'New node identity initialization failed. Inspect partial files; never overwrite a partial identity.'
else
 echo '[RECOVER] Preserving existing node identity and public advertisement.'
fi
( cd "$APP" && "$PY" -I node_manager.py status ) || fail 'Cannot validate node config; relay not started.'
# Don't start two listeners on one port.
if command -v ss >/dev/null 2>&1 && ss -ltnH '( sport = :6667 )' | grep -q .; then
 if ! systemctl is-active --quiet "$UNIT"; then fail 'Another process already occupies TCP port 6667. Stop it before setup.'; fi
fi
# Generate a unit against the actual installed program path. Protect existing service with a backup.
tmp="$(mktemp "${TMPDIR:-/tmp}/vf-unit.XXXXXXXX")"
trap 'rm -f -- "$tmp"' EXIT
( cd "$APP" && "$PY" -I node_manager.py service-file > "$tmp" ) || fail 'Could not generate service config.'
[[ -s "$tmp" ]] || fail 'Generated service is empty.'
if command -v systemd-analyze >/dev/null 2>&1; then
  echo '[VERIFY] Checking generated systemd unit before changing the installed service...'
  systemd-analyze verify "$tmp" || fail 'Generated systemd unit failed validation; old service was not replaced.'
fi
if [[ -f /etc/systemd/system/vaultforge-mesh.service ]]; then
 backup="$HOME/VaultForge/.vaultforge-mesh.service.before-repair"
 if [[ ! -e "$backup" ]]; then
   sudo cat /etc/systemd/system/vaultforge-mesh.service > "$backup"
   chmod 600 "$backup"
   echo "[BACKUP] Prior systemd unit at $backup"
 fi
fi
sudo install -m 644 "$tmp" /etc/systemd/system/vaultforge-mesh.service
sudo systemctl daemon-reload
sudo systemctl stop "$UNIT" || true
sudo systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
sudo systemctl start "$UNIT"
sleep 3
if ! systemctl is-active --quiet "$UNIT"; then
 sudo journalctl -u "$UNIT" -n 20 --no-pager || true
 fail 'Relay failed after start. Identity preserved. See logs above.'
fi
if command -v ss >/dev/null 2>&1 && ! ss -ltnH '( sport = :6667 )' | grep -q .; then
 sudo journalctl -u "$UNIT" -n 20 --no-pager || true
 fail 'Service exists but TCP 6667 is not listening.'
fi
if [[ -f "$APP/node_health.py" ]]; then
 ( cd "$APP" && "$PY" -I node_health.py --port 6667 ) || fail 'Relay is listening but encrypted handshake failed.'
fi
printf '[SUCCESS] Relay program: %s\n' "$APP"
printf '[SUCCESS] VaultForge storage: %s\n' "${DATA%/mesh_chat}"
printf '[SUCCESS] Encrypted mesh relay is listening on TCP 6667.\n'
printf '[STATUS] Boot autostart was not changed. Enable explicitly: sudo systemctl enable vaultforge-mesh\n'
printf '[NETWORK] Clients may connect to %s if EC2 IP/firewall allow it.\n' "$ENDPOINT"
