#!/usr/bin/env bash
# Initialize VaultForge data storage safely; never create/overwrite node identity files.
set -Eeuo pipefail
umask 077
if (( EUID == 0 )); then
  echo '[ERROR] Do not create VaultForge user data as root. Run as the regular ubuntu/Linux user.' >&2
  exit 2
fi
mode="${1:-client}"
if [[ "$mode" != client && "$mode" != relay ]]; then
  echo 'Usage: ./PREPARE_DATA_DIRS.sh [client|relay]' >&2
  exit 2
fi
base="${VAULTFORGE_DATA_ROOT:-$HOME/VaultForge}"
# Avoid accidentally creating data in the wrong user's home or following symlinks.
if [[ ! "$base" = /* || "$base" == / || "$base" == "$HOME" ]]; then
  echo '[ERROR] VAULTFORGE_DATA_ROOT must be an absolute dedicated directory.' >&2
  exit 2
fi
if [[ -L "$base" || -L "$(dirname -- "$base")" ]]; then
  echo '[ERROR] Refusing symlinked VaultForge data location.' >&2
  exit 2
fi
folders=("$base" "$base/mesh_chat" "$base/mesh_chat/downloads")
if [[ "$mode" == client ]]; then
  folders+=("$base/wallets")
fi
for dir in "${folders[@]}"; do
  if [[ -L "$dir" ]]; then
    echo "[ERROR] Refusing symlink: $dir" >&2
    exit 2
  fi
  if [[ -e "$dir" && ! -d "$dir" ]]; then
    echo "[ERROR] Existing file blocks folder: $dir" >&2
    exit 2
  fi
  if [[ -d "$dir" && ! -O "$dir" ]]; then
    echo "[ERROR] Data directory is not owned by $USER: $dir" >&2
    echo '[ACTION] Do not run the installer with sudo. Inspect ownership and resolve it manually.' >&2
    exit 2
  fi
done
for dir in "${folders[@]}"; do
  if [[ ! -d "$dir" ]]; then
    mkdir -m 700 -- "$dir"
    echo "[CREATED] $dir"
  else
    echo "[EXISTS]  $dir"
  fi
  chmod 700 -- "$dir"
done
printf '[DATA READY] %s (mode=%s, private directories)\n' "$base" "$mode"
printf '[IDENTITY] No node.json, node.secret, or accounts.json created or modified.\n'
