#!/usr/bin/env python3
"""VaultForge v2.7.2 installer coordinator; runs on CPython 3.12 only.

Launchers provision a local uv-managed Python 3.12, then invoke this script.
No wallet vaults are read, written, or migrated by this installer.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REQUIRED = (3, 12)
VERIFY_SCRIPT = 'vaultforge.py'
# Mandatory release files. A partial extraction is not a successful installation.
REQUIRED_BUNDLE_FILES = (
    'vaultforge.py', 'mesh_chat.py', 'node_manager.py', 'file_transfer.py', 'wallet_core.py', 'bitcoin_vault.py',
    'security_center.py', 'transfer_engine.py', 'vault_bridge.py',
    'requirements.txt', 'connection_diagnostics.py', 'tests/test_public_directory.py', 'tests/__init__.py',
    'tests/test_mesh_chat.py', 'tests/test_installer.py',
)


def validate_bundle() -> None:
    missing = [name for name in REQUIRED_BUNDLE_FILES
               if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError(
            'Incomplete VaultForge Mesh v2.7.2 extraction; missing: '
            + ', '.join(missing)
            + '. '
            + 'Extract the COMPLETE v2.7.2 ZIP in a fresh folder '
            + "(including tests/), then run that folder's ./install_linux.sh. "
            + 'Do not create an empty tests/ folder or skip validation.'
        )



def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print('[RUN] ' + ' '.join(map(str, command)), flush=True)
    return subprocess.run(command, cwd=ROOT, check=check)


def python_version(cmd: list[str]) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [*cmd, '-c', 'import sys; print("%d.%d" % sys.version_info[:2] if sys.implementation.name == "cpython" else "unsupported")'],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode:
            return None
        major, minor = map(int, result.stdout.strip().split('.'))
        return major, minor
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def choose_python() -> tuple[list[str], tuple[int, int]]:
    override = os.environ.get('VAULTFORGE_PYTHON', '').strip()
    if override:
        version = python_version([override])
        if version != REQUIRED:
            raise RuntimeError(f'VAULTFORGE_PYTHON must be CPython 3.12 (found {version}).')
        return [override], version

    candidates = ([['py', '-3.12']] if os.name == 'nt' else []) + [
        ['python3.12'], [sys.executable], ['python3'], ['python'],
    ]
    for cmd in candidates:
        if python_version(cmd) == REQUIRED:
            return cmd, REQUIRED
    raise RuntimeError(
        'Python 3.12 was not detected. Start with install_linux.sh or INSTALL_WINDOWS.bat '
        'to download a local Python 3.12 automatically. No global Python changes needed.'
    )


def venv_exe(venv: Path) -> Path:
    return venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def get_backup_path(venv: Path) -> Path:
    for i in range(1, 1000):
        candidate = venv.with_name(f'.venv.incompatible-backup-{i}')
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise RuntimeError('Too many old environment backups. Move them manually.')


def ensure_venv(selected: list[str]) -> Path:
    folder = ROOT / '.venv'
    executable = venv_exe(folder)
    if folder.exists() or folder.is_symlink():
        version = python_version([str(executable)]) if executable.is_file() else None
        if version != REQUIRED:
            destination = get_backup_path(folder)
            print(f'[INFO] Preserving incompatible .venv (Python {version}) at {destination.name}.', flush=True)
            folder.rename(destination)
        else:
            print('[INFO] Reusing Python 3.12 virtual environment.', flush=True)
            return executable

    uv = os.environ.get('VAULTFORGE_UV', '').strip()
    if uv:
        # Passing an explicit interpreter path prevents fallback to the system Python.
        run([uv, 'venv', '--python', selected[0], str(folder)])
    else:
        run([*selected, '-m', 'venv', str(folder)])
    if not executable.is_file() or python_version([str(executable)]) != REQUIRED:
        raise RuntimeError('Virtual environment creation failed to select Python 3.12.')
    return executable


def install_dependencies(py: Path) -> None:
    uv = os.environ.get('VAULTFORGE_UV', '').strip()
    try:
        if uv:
            # uv can install into its own managed 3.12 virtualenv even without pip.
            run([uv, 'pip', 'install', '--python', str(py), '--only-binary', 'coincurve',
                 '-r', str(ROOT / 'requirements.txt')])
        else:
            run([str(py), '-m', 'pip', 'install', '--require-virtualenv', '--upgrade', 'pip'])
            run([str(py), '-m', 'pip', 'install', '--require-virtualenv', '--only-binary=coincurve',
                 '-r', str(ROOT / 'requirements.txt')])
    except subprocess.CalledProcessError:
        raise RuntimeError(
            'Dependency installation failed. A compatible prebuilt wheel may be unavailable '
            'or the network may be blocked. coincurve source builds are forbidden; '
            'inspect the preceding output rather than bypassing this failure.'
        ) from None


def main() -> int:
    print('VaultForge Unified 2.7.2 — Mesh Chat / automatic Python 3.12 installer', flush=True)
    print('[INFO] Existing .vault files and system Python are untouched.', flush=True)
    try:
        validate_bundle()
        selected, version = choose_python()
        print(f'[OK] Selected Python {version[0]}.{version[1]}: {selected[0]}', flush=True)
        py = ensure_venv(selected)
        install_dependencies(py)
        # Python isolated mode removes the CWD from sys.path. Supplying both
        # absolute start and project top-level paths makes discovery reliable.
        tests_dir = ROOT / 'tests'
        if os.getenv('VAULTFORGE_RUN_TESTS', '1') == '1':
            run([str(py), '-I', '-m', 'unittest', 'discover',
                 '-s', str(tests_dir), '-t', str(ROOT), '-p', 'test_*.py', '-v'])
            run([str(py), '-I', VERIFY_SCRIPT, '--self-test'])
        else:
            print('[INFO] Installer tests explicitly skipped (VAULTFORGE_RUN_TESTS=0).')
        print('\n[OK] Python 3.12 environment, dependencies, and local tests completed.', flush=True)
        print('[WARN] Not audited or validated for real-value cryptocurrency transfers.', flush=True)
        return 0
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f'\n[ERROR] {exc}', file=sys.stderr, flush=True)
        print('[ERROR] Installation incomplete. Do not use this build with funds.', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
