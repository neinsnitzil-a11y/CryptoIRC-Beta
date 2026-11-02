#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "$0")/src" && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/crypto-nocturne"
ENV_DIR="$DATA_DIR/runtime-v2.3"
if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  echo '[SETUP] Preparing CRYPTO NOCTURNE; requires python3-venv and python3-tk.'
  python3 -m venv "$ENV_DIR"
  "$ENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$SOURCE_DIR/requirements.txt"
fi
cd "$SOURCE_DIR"
exec "$ENV_DIR/bin/python" crypto.py
