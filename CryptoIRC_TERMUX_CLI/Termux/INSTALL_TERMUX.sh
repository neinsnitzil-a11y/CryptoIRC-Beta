#!/data/data/com.termux/files/usr/bin/bash
# Full native port installer. Native Android extension wheels may be unavailable.
# Never claim full-wallet setup succeeded until all imports and smoke checks succeed.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP="$ROOT/app"
if [[ "${PREFIX:-}" != */com.termux/files/usr || ! -d "$PREFIX" ]]; then
  echo '[ERROR] Run in the native Termux app, not desktop Linux, Kali or PRoot.' >&2
  exit 2
fi
if [[ "$(id -u)" == 0 ]]; then
  echo '[ERROR] Never run the installer as root.' >&2; exit 2
fi
case "$ROOT" in /sdcard/*|/storage/*) echo '[ERROR] Extract source into Termux private HOME, not Android shared storage.' >&2; exit 2;; esac
if [[ -L "$HOME/VaultForge" || -L "$HOME/VaultForge/mesh_chat" || -L "$HOME/VaultForge/wallets" ]]; then
  echo '[ERROR] Refusing symlinked wallet/mesh data folder.' >&2; exit 2
fi
mkdir -p "$HOME/VaultForge/wallets" "$HOME/VaultForge/mesh_chat/downloads"
chmod 700 "$HOME/VaultForge" "$HOME/VaultForge/wallets" "$HOME/VaultForge/mesh_chat" "$HOME/VaultForge/mesh_chat/downloads"

echo '[SETUP] Termux native Python + compiled cryptography libraries.'
pkg update
pkg install -y python python-pip python-cryptography python-pycryptodomex python-pynacl \
  clang make rust openssl libffi pkg-config libsodium git coreutils
# Prefer Termux-managed native crypto; do not pip-upgrade Termux's global pip.
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  python -m venv --system-site-packages "$ROOT/.venv"
fi
VPY="$ROOT/.venv/bin/python"
if ! "$VPY" -c 'import sys; assert sys.prefix != sys.base_prefix' >/dev/null; then
  echo '[ERROR] The private Termux Python venv is unusable.' >&2; exit 1
fi
# Windows/Linux pinned requirements include glibc wheels. Use Termux-oriented
# dependency resolution instead; verify exact API imports below.
echo '[SETUP] Installing FULL wallet + networking dependency tree (may require ARM source compilation).'
if ! "$VPY" -m pip install --prefer-binary -r "$ROOT/requirements-termux.txt"; then
  echo '[BLOCKED] Native Android full-wallet dependencies could not compile/install.' >&2
  echo '[ACTION] Full-wallet startup is blocked; run bash Termux/INSTALL_PROOT_UBUNTU.sh for the Linux compatibility runtime.' >&2
  exit 1
fi
if ! "$VPY" -I "$ROOT/termux_preflight.py" --full; then
  echo '[BLOCKED] Native wallet dependency self-test failed. Do NOT use for funds.' >&2
  echo '[ACTION] Try the supported Linux-userspace fallback: bash Termux/INSTALL_PROOT_UBUNTU.sh' >&2
  exit 1
fi
echo '[READY] Full Linux CLI source running under Termux native Python.'
echo '[NEXT] bash Termux/START_TERMUX.sh'
