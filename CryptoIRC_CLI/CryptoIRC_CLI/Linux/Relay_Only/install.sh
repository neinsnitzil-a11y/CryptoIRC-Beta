#!/usr/bin/env bash
# VaultForge Linux installer — no root, always CPython 3.12.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
ROOT="$PWD"
umask 077

if (( EUID == 0 )); then
  echo '[ERROR] Do not run this installer with sudo or as root.' >&2
  echo '[ACTION] Run ./install.sh as your normal Linux user.' >&2
  echo '[ACTION] If old attempts left root-owned .runtime/.venv files, repair ownership of only those directories first.' >&2
  exit 2
fi
if [[ ! -w "$ROOT" ]]; then
  echo "[ERROR] No write access to $ROOT; check ownership of the extracted program folder." >&2
  exit 2
fi

echo "[DATA] Preparing private $HOME/VaultForge storage..."
bash "$ROOT/PREPARE_DATA_DIRS.sh" relay

# Prefer a working Python 3.12 already on PATH. This needs no uv, no download.
for candidate in python3.12; do
  if command -v "$candidate" >/dev/null 2>&1; then
    resolved="$(command -v "$candidate")"
    if "$resolved" -c 'import sys; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3,12)' >/dev/null 2>&1; then
      # On Ubuntu/Debian, python3.12 may exist without python3.12-venv/ensurepip.
      # Test a temporary venv first so we can fall back to uv rather than fail late.
      CHECK_VENV="$(mktemp -d "${TMPDIR:-/tmp}/vf-venv-check.XXXXXXXX")"
      if "$resolved" -m venv "$CHECK_VENV/env" >/dev/null 2>&1 &&
         "$CHECK_VENV/env/bin/python" -m pip --version >/dev/null 2>&1; then
        rm -rf -- "$CHECK_VENV"
        printf '[SETUP] Using installed CPython 3.12: %s (no uv download needed)\n' "$resolved"
        export VAULTFORGE_PYTHON="$resolved"
        unset VAULTFORGE_UV || true
        exec "$resolved" install_runtime.py
      else
        echo '[INFO] System Python 3.12 lacks a usable pip/venv; switching to isolated managed Python 3.12.'
        rm -rf -- "$CHECK_VENV"
      fi
    fi
  fi
done

# Use a private managed runtime. Do not alter system Python or global PATH.
export UV_NO_CONFIG=1
export UV_PYTHON_INSTALL_DIR="$ROOT/.runtime/python"
export UV_PYTHON_BIN_DIR="$ROOT/.runtime/bin"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-45}"
UV_LOCAL="$ROOT/.runtime/uv/uv"

if [[ -x "$UV_LOCAL" ]]; then
  UV="$UV_LOCAL"
elif command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
elif [[ -x "$HOME/.local/bin/uv" ]]; then
  UV="$HOME/.local/bin/uv"
else
  # Avoid piping a network installer into sh: its binary download has no wall-time limit.
  # Pin both the release and the artifact hash (official Astral release 0.13.6).
  UV_VERSION='0.13.6'
  case "$(uname -m)" in
    x86_64|amd64)
      PLATFORM='x86_64-unknown-linux-gnu'
      EXPECTED_SHA256='f29c3e94ffabd7e6f3ba521dba169a9b7ec12100bf3257087f0f24f6123f3645'
      ;;
    aarch64|arm64)
      PLATFORM='aarch64-unknown-linux-gnu'
      EXPECTED_SHA256='229e194255c7958d86d56e8790d969a6f74736592133f0dfd0076f754c642c1d'
      ;;
    *)
      echo "[ERROR] No prebuilt pinned uv binary for $(uname -m). Install python3.12 or uv via your OS." >&2
      exit 1
      ;;
  esac
  ARCHIVE_NAME="uv-${PLATFORM}.tar.gz"
  if ! command -v sha256sum >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1; then
    echo '[ERROR] sha256sum and tar are required to verify and unpack uv.' >&2
    exit 1
  fi
  TEMP="$(mktemp -d "${TMPDIR:-/tmp}/vaultforge-uv.XXXXXXXX")"
  trap 'rm -rf -- "$TEMP"' EXIT
  URL_MIRROR="https://releases.astral.sh/github/uv/releases/download/${UV_VERSION}/${ARCHIVE_NAME}"
  URL_GITHUB="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${ARCHIVE_NAME}"
  echo "[SETUP] Downloading verified uv ${UV_VERSION} binary for ${PLATFORM} (timeout per source: 120 seconds)..."
  fetched=0
  for url in "$URL_MIRROR" "$URL_GITHUB"; do
    echo "[DOWNLOAD] ${url}"
    rm -f -- "$TEMP/$ARCHIVE_NAME"
    if command -v curl >/dev/null 2>&1; then
      if curl --proto '=https' --tlsv1.2 --fail --location --show-error --progress-bar \
           --connect-timeout 12 --max-time 120 --retry 1 --retry-max-time 120 \
           --output "$TEMP/$ARCHIVE_NAME" "$url"; then
        fetched=1
        break
      fi
    elif command -v wget >/dev/null 2>&1; then
      if command -v timeout >/dev/null 2>&1; then
        if timeout 120 wget --https-only --timeout=12 --tries=2 --show-progress \
           -O "$TEMP/$ARCHIVE_NAME" "$url"; then
          fetched=1
          break
        fi
      else
        echo '[ERROR] curl or timeout is needed to guarantee a bounded download.' >&2
        break
      fi
    else
      echo '[ERROR] Install curl or wget to download uv.' >&2
      break
    fi
    echo '[WARN] Download failed; attempting the alternate official release location.' >&2
  done
  if (( fetched == 0 )); then
    echo '[ERROR] Could not download uv. Check DNS, HTTPS access, VPN/proxy/firewall and disk space.' >&2
    echo '[ACTION] Alternatively install python3.12 with your OS package manager, then rerun ./install_linux.sh.' >&2
    exit 1
  fi
  echo "${EXPECTED_SHA256}  ${TEMP}/${ARCHIVE_NAME}" | sha256sum --check --status || {
    echo '[ERROR] Downloaded uv binary checksum mismatch. File not executed.' >&2
    exit 1
  }
  echo '[OK] Official uv SHA-256 checksum verified.'
  mkdir -p -- "$TEMP/extract" "$ROOT/.runtime/uv"
  tar -xzf "$TEMP/$ARCHIVE_NAME" -C "$TEMP/extract"
  UV_SOURCE="$TEMP/extract/uv-${PLATFORM}/uv"
  if [[ ! -f "$UV_SOURCE" ]]; then
    echo '[ERROR] Unexpected uv archive layout (no executable found).' >&2
    exit 1
  fi
  install -m 700 "$UV_SOURCE" "$UV_LOCAL"
  UV="$UV_LOCAL"
  trap - EXIT
  rm -rf -- "$TEMP"
fi

if ! "$UV" --version >/dev/null 2>&1; then
  echo '[ERROR] uv is not executable or cannot run on this system.' >&2
  exit 1
fi
printf '[SETUP] Installing/reusing private CPython 3.12 using %s\n' "$UV"
# Managed Python download may also stall when outbound network access is blocked.
if command -v timeout >/dev/null 2>&1; then
  if ! timeout 360 "$UV" python install 3.12; then
    echo '[ERROR] Python 3.12 download failed or exceeded 6 minutes.' >&2
    echo '[ACTION] Check HTTPS access; then rerun installer. Partial runtime downloads are reusable.' >&2
    exit 1
  fi
else
  "$UV" python install 3.12
fi
PYTHON312="$("$UV" python find 3.12 --managed-python)"
if [[ -z "$PYTHON312" || ! -x "$PYTHON312" ]] || \
   ! "$PYTHON312" -c 'import sys; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3,12)' >/dev/null 2>&1; then
  echo '[ERROR] uv could not provide a verified CPython 3.12 interpreter.' >&2
  exit 1
fi
export VAULTFORGE_UV="$UV"
export VAULTFORGE_PYTHON="$PYTHON312"
exec "$PYTHON312" install_runtime.py
