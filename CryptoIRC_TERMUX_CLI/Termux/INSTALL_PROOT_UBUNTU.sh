#!/data/data/com.termux/files/usr/bin/bash
# Full Linux CLI fallback under Ubuntu PRoot if Android-native cryptography can't build.
# This does not install systemd and does not require root on the Android device.
set -Eeuo pipefail
umask 077
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
APP="$BASE/app"
if [[ "${PREFIX:-}" != */com.termux/files/usr || "$(id -u)" == 0 ]]; then
  echo '[ERROR] Use native, non-root Termux.' >&2; exit 2
fi
if [[ "$BASE" == /sdcard/* || "$BASE" == /storage/* ]]; then
  echo '[ERROR] Extract into Termux private HOME.' >&2; exit 2
fi
printf '%s\n' '[INFO] This installs an Ubuntu Linux userspace inside Termux (not Android root).'
printf '%s\n' '[INFO] It may use substantial storage and data; do not store real funds until verified.'
read -r -p 'Type INSTALL UBUNTU to proceed: ' answer
[[ "$answer" == 'INSTALL UBUNTU' ]] || { echo 'Cancelled'; exit 1; }
pkg install -y proot-distro
if ! proot-distro list --installed 2>/dev/null | grep -Eq '(^|[[:space:]])ubuntu([[:space:]]|$)'; then
  proot-distro install ubuntu
fi
# A dedicated unprivileged guest; keep guest identity in its own persistent HOME.
proot-distro login ubuntu -- /bin/bash -lc '
  set -e
  if ! id cryptoirc >/dev/null 2>&1; then useradd -m -s /bin/bash cryptoirc; fi
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl tar git bash coreutils build-essential
'
# Copy *source* into guest home, never copy wallet databases, secrets or Android .venv.
proot-distro login ubuntu --bind "$APP:/opt/cryptoirc-install-source" -- /bin/bash -lc '
  set -e
  mkdir -p /home/cryptoirc/CryptoIRC
  find /opt/cryptoirc-install-source -maxdepth 1 -type f \( -name "*.py" -o -name "*.sh" -o -name "requirements.txt" \) -exec cp -f {} /home/cryptoirc/CryptoIRC/ \;
  if [ -d /opt/cryptoirc-install-source/tests ]; then
    mkdir -p /home/cryptoirc/CryptoIRC/tests
    cp -a /opt/cryptoirc-install-source/tests/. /home/cryptoirc/CryptoIRC/tests/
  fi
  chmod +x /home/cryptoirc/CryptoIRC/*.sh
  chown -R cryptoirc:cryptoirc /home/cryptoirc/CryptoIRC
'
echo '[SETUP] Installing Linux CPython 3.12 and complete wallet dependencies inside PRoot.'
proot-distro login ubuntu --user cryptoirc -- /bin/bash -lc 'cd "$HOME/CryptoIRC" && bash ./install_linux.sh'
echo '[READY] Full Linux CLI installed inside Termux Ubuntu compatibility runtime.'
echo '[NEXT] bash Termux/START_PROOT_UBUNTU.sh'
