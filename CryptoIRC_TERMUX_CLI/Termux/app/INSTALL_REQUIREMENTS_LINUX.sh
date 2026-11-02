#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then ./install_linux.sh; exit 0; fi
if .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m pip install --require-virtualenv -r requirements.txt
elif [[ -x .runtime/uv/uv ]]; then
  .runtime/uv/uv pip install --python .venv/bin/python -r requirements.txt
else
  echo '[ERROR] Virtual environment has no pip and no uv is available. Run the official installer.' >&2
  exit 1
fi
