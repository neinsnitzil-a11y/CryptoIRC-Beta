#!/usr/bin/env python3
"""CRYPTO NOCTURNE Windows release builder; no financial operations.

The builder intentionally never packages vault files, payment credentials,
server-side relay code, or mutable account state into the executable.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import tempfile

ROOT = Path(__file__).resolve().parent
APP_NAME = 'CRYPTO_NOCTURNE'
APP_VERSION = '4.5.1'
OUTPUT_ROOT = ROOT.parent
EXE = OUTPUT_ROOT / 'dist' / APP_NAME / f'{APP_NAME}.exe'
INSTALLER = OUTPUT_ROOT / 'release' / f'{APP_NAME}_Setup_v{APP_VERSION}.exe'

REQUIRED = ('crypto.py', 'btc_phase1.py', 'btc_phase1_ui.py', 'live_crypto.py', 'live_crypto_ui.py', 'live_balances.py', 'live_balance_ui.py', 'backend.py', 'professional_ui.py', 'brand_theme.py',
            'core/vaultforge.py', 'core/transfer.py', 'core/assets.py',
            'chain_expansion.py', 'chain_expansion_ui.py',
            'node_health.py', 'node_health_ui.py', 'portfolio_engine.py', 'portfolio_ui.py',
            'banking_rails.py', 'banking_rails_ui.py', 'vault_security.py', 'vault_security_ui.py', 'financial_backend/rails_gateway.py',
            'core/mesh_network.py', 'core/tor_controller.py', 'peer_ui.py',
            'data/2048_BIP_39_words.csv', 'data/iso4217_catalog.json',
            'brand_assets/CRYPTO_NOCTURNE.ico', 'brand_assets/tor_round.png',
            'brand_assets/skull_green.png', 'installer.iss',
            'CRYPTO_NOCTURNE.spec', 'security_gates.py', 'financial_controls_ui.py', 'operations_ui.py', 'release_security.py',
            'brand_assets/hazard_red.png', 'reliability_runtime.py', 'reliability_ui.py', 'financial_experience.py', 'financial_experience_ui.py', 'compliance_runtime.py', 'compliance_ui.py', 'qa_runtime.py', 'qa_ui.py', 'qa_runner.py',
            'release_ops.py', 'release_ops_ui.py', 'release_ops_cli.py',
            'mesh_gui.py', 'mesh_bridge.py', 'vaultmesh/mesh_chat.py', 'vaultmesh/node_manager.py',
            'vaultmesh/file_transfer.py', 'vaultmesh/chat_history.py', 'vaultmesh/security_center.py')
# Prevent accidental redistribution of live wallet/account data and credentials.
SENSITIVE_NAMES = {'.env', '.env.local', '.env.production', 'peer_identity.enc',
                   'credentials.json', 'token.json', 'wallet.dat', 'auth.json',
                   'secret.key', 'private.key', 'wallet.db'}
SENSITIVE_SUFFIXES = {'.vault', '.fiat', '.pem', '.p12', '.pfx', '.key', '.keystore', '.sqlite', '.sqlite3', '.db', '.wallet'}
EXCLUDED_SCAN_FOLDERS = {'.venv','.build-venv','.build_venv','venv','build','dist',
                         'dist_portable','release','build_logs','__pycache__','.git'}

def scan_sources_for_secrets(root=ROOT):
    """Find user/merchant secrets in source tree; exclude generated outputs."""
    suspects=[]
    for current, dirs, files in os.walk(root):
        dirs[:]=[d for d in dirs if d.lower() not in EXCLUDED_SCAN_FOLDERS]
        for name in files:
            path=Path(current)/name
            if name.lower() in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
                suspects.append(path.relative_to(root).as_posix())
    return sorted(suspects)


def _is_verified_certifi_bundle(root, relative_name):
    """Allow ONLY certifi's public CA collection inside a compiled distribution.

    Never exempt arbitrary *.pem files: they may contain signing keys.
    Requiring identical bytes to the installed certifi package also protects
    against a sensitive file renamed to `_internal/certifi/cacert.pem`.
    """
    import hashlib
    import hmac
    rel=Path(relative_name).as_posix().lower()
    if rel not in ('_internal/certifi/cacert.pem', 'certifi/cacert.pem'):
        return False
    try:
        import certifi
        bundled=(Path(root)/relative_name).read_bytes()
        trusted=Path(certifi.where()).read_bytes()
        # Avoid accidentally trusting an empty/missing/malformed bundle.
        if b'-----BEGIN CERTIFICATE-----' not in bundled or b'PRIVATE KEY' in bundled:
            return False
        return hmac.compare_digest(hashlib.sha256(bundled).digest(),
                                   hashlib.sha256(trusted).digest())
    except (OSError, ImportError, ValueError):
        return False


def scan_distribution_for_secrets(root):
    """Apply stricter output checks, except for the exact trusted CA bundle."""
    root=Path(root)
    return [item for item in scan_sources_for_secrets(root)
            if not _is_verified_certifi_bundle(root, item)]



def find_inno_setup():
    if os.name != 'nt': return None
    candidates=[]
    override=os.environ.get('ISCC_PATH') or os.environ.get('INNO_SETUP_ISCC')
    if override:
        p=Path(override.strip('"'))
        candidates.append(p/'ISCC.exe' if p.is_dir() else p)
    for name in ('ISCC.exe','iscc.exe'):
        v=shutil.which(name)
        if v:candidates.append(Path(v))
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'),
                 r'C:\Program Files (x86)',r'C:\Program Files'):
        if base:
            for ver in ('6','7'):
                candidates.append(Path(base)/f'Inno Setup {ver}'/'ISCC.exe')
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key in (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
                        r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'):
                try:
                    with winreg.OpenKey(hive,key) as h:
                        install_dir=winreg.QueryValueEx(h,'InstallLocation')[0]
                        candidates.append(Path(install_dir)/'ISCC.exe')
                except OSError: pass
    except ImportError: pass
    return next((p for p in candidates if p.is_file()), None)


def run(args, *, cwd=ROOT, env=None):
    print('>', ' '.join('"'+str(x)+'"' if ' ' in str(x) else str(x) for x in args), flush=True)
    # Do not use shell=True; command strings must never contain credentials.
    return subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)


def preflight(require_windows=False, require_dependencies=False):
    print(f'CRYPTO NOCTURNE Build Kit  |  Application v{APP_VERSION}')
    missing=[s for s in REQUIRED if not (ROOT/s).is_file()]
    if missing: raise RuntimeError('Missing application/asset files:\n  '+'\n  '.join(missing))
    suspects=scan_sources_for_secrets()
    if suspects:
        raise RuntimeError('Build blocked: possible secrets/wallet files in source directory:\n  '
                           +'\n  '.join(suspects)+'\nMove these outside the release source before building.')
    if require_windows and os.name != 'nt':
        raise RuntimeError('Windows EXE builds must be run on Windows; PyInstaller does not cross-compile.')
    if os.name=='nt' and require_windows:
        if sys.maxsize<=2**32:raise RuntimeError('Use 64-bit Python for a 64-bit Windows release.')
        if sys.version_info[:2] != (3,12):
            raise RuntimeError(f'Use Python 3.12 (detected {platform.python_version()}).')
    if require_dependencies:
        modules=('PyInstaller','bip_utils','cryptography','argon2','web3','eth_account','requests','PIL','qrcode','socks','websockets')
        not_found=[m for m in modules if importlib.util.find_spec(m) is None]
        if not_found: raise RuntimeError('Missing build/application dependencies: '+', '.join(not_found)
                                          +'\nRun BUILD_WINDOWS.bat to set up the compiler.')
    print('[OK] Required source and branding assets found.')
    print('[OK] No private wallet/credential files found in the source tree.')
    print('[INFO] User wallets are saved outside the application installation.')


def run_tests():
    print('[TEST] Running application unit tests...')
    # Existing relay imports can create relay_chat.sqlite3 at import time.
    # Isolate test working state so private/generated DBs never enter the source tree.
    with tempfile.TemporaryDirectory(prefix='nocturne-tests-') as scratch:
        env=os.environ.copy()
        # Windows cp1252 can crash mesh tests and misread UTF-8 source.
        # Force UTF-8 for the isolated test child, not for wallet runtime.
        env['PYTHONUTF8']='1'
        env['PYTHONIOENCODING']='utf-8'
        env['PYTHONPATH']=str(ROOT)+os.pathsep+env.get('PYTHONPATH','')
        env['CRYPTO_RELAY_DATABASE']=str(Path(scratch)/'test_relay.sqlite3')
        run([sys.executable,'-m','unittest','discover','-s',ROOT/'tests','-v'],cwd=Path(scratch),env=env)
    print('[PASS] Test process returned exit status 0 without writing into source tree.')


def build_exe():
    preflight(require_windows=True,require_dependencies=True)
    run_tests()
    print('[BUILD] Compiling Windows one-folder EXE and dependencies...')
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
         '--distpath',OUTPUT_ROOT/'dist','--workpath',OUTPUT_ROOT/'build_temp',
         ROOT/'CRYPTO_NOCTURNE.spec'])
    if not EXE.is_file():raise RuntimeError(f'PyInstaller completed without expected EXE: {EXE}')
    if not (OUTPUT_ROOT/'dist'/APP_NAME/'_internal'/'brand_assets'/'tor_round.png').is_file():
        # Older PyInstaller layouts may place data alongside EXE; accept only if present in either.
        alternative=OUTPUT_ROOT/'dist'/APP_NAME/'brand_assets'/'tor_round.png'
        if not alternative.is_file():raise RuntimeError('Compiled bundle missing Tor artwork.')
    from release_security import distribution_audit
    distribution_audit(OUTPUT_ROOT/'dist'/APP_NAME)
    verify_frozen_wallet_runtime()
    thumbprint=os.environ.get('CRYPTO_SIGN_CERT_SHA1','').strip()
    if thumbprint:
        from release_security import sign_executable,verify_windows_signature
        sign_executable(EXE,thumbprint)
        verify_windows_signature(EXE)
        print('[PASS] EXE Authenticode signing verified using configured local certificate.')
    else:
        print('[UNSIGNED DEVELOPMENT] No code-signing certificate configured. Do not ship to end users.')
    print(f'[SUCCESS] EXE: {EXE}')


def verify_frozen_wallet_runtime():
    # Critical: source tests cannot detect missing modules inside the frozen EXE.
    # Windowed PyInstaller apps may have no sys.stdout/stderr; obtain a strictly
    # sanitized status from a temporary file. No sensitive data is written.
    print('[TEST] Running frozen EXE wallet cryptography smoke test...')
    with tempfile.TemporaryDirectory(prefix='nocturne-frozen-wallet-check-') as scratch:
        report_path=Path(scratch)/'status.txt'
        try:
            frozen=subprocess.run([str(EXE), '--wallet-self-test',str(report_path)],
                                  cwd=EXE.parent, capture_output=True, text=True,
                                  timeout=150, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Frozen wallet runtime check timed out; installer blocked.') from exc
        report=report_path.read_text(encoding='utf-8') if report_path.is_file() else ''
        if frozen.returncode != 0 or not report.startswith('[PASS] Wallet runtime:'):
            # Never echo arbitrary stdout/stderr; these could carry secrets.
            safe=report if report.startswith('[FAILED] WLT-') else 'No safe diagnostic was returned.'
            raise RuntimeError('Frozen wallet runtime check failed; installer blocked.\n'+safe)
        print(report)


def build_installer():
    preflight(require_windows=True)
    if not EXE.is_file():raise RuntimeError('Application EXE not found. Run BUILD BOTH in BUILD_WINDOWS.bat.')
    from release_security import distribution_audit
    distribution_audit(OUTPUT_ROOT/'dist'/APP_NAME)
    verify_frozen_wallet_runtime()
    iscc=find_inno_setup()
    if not iscc: raise RuntimeError('Inno Setup ISCC.exe not found. Set ISCC_PATH to the full ISCC.exe path, '
                                    'or install Inno Setup 6.')
    (OUTPUT_ROOT/'release').mkdir(exist_ok=True)
    run([iscc,ROOT/'installer.iss'])
    if not INSTALLER.is_file():raise RuntimeError('Inno Setup returned without expected installer: '+str(INSTALLER))
    thumbprint=os.environ.get('CRYPTO_SIGN_CERT_SHA1','').strip()
    signed=False
    if thumbprint:
        from release_security import sign_executable,verify_windows_signature
        verify_windows_signature(EXE)
        sign_executable(INSTALLER,thumbprint)
        verify_windows_signature(INSTALLER)
        signed=True
        print('[PASS] Installer Authenticode signature verified locally.')
    else:
        print('[UNSIGNED DEVELOPMENT] Installer has no authenticated publisher signature.')
    from release_security import package_manifest
    from release_ops import make_sbom,sha256_file
    import json
    # Manifests and SBOM are generated outside app source. They do not certify safety.
    artifacts=OUTPUT_ROOT/'release'
    package_manifest(OUTPUT_ROOT/'dist'/APP_NAME,artifacts/f'bundle_manifest_v{APP_VERSION}.json')
    (artifacts/f'direct_deps_sbom_v{APP_VERSION}.json').write_text(
        json.dumps(make_sbom(ROOT/'requirements.txt'),indent=2)+'\n',encoding='utf-8')
    receipt={'schema':1,'version':APP_VERSION,'release_class':'UNVERIFIED DEVELOPMENT',
             'authenticode_verified_locally':signed,'production_ready':False,
             'installer':{'file':INSTALLER.name,'sha256':sha256_file(INSTALLER),
                          'bytes':INSTALLER.stat().st_size},
             'application':{'file':EXE.name,'sha256':sha256_file(EXE),
                            'bytes':EXE.stat().st_size},
             'warning':'This unsigned JSON inventory is not a digital signature or financial authorization.'}
    (artifacts/f'development_release_receipt_v{APP_VERSION}.json').write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(f'[SUCCESS] INSTALLER: {INSTALLER}')
    print('[WARN] Release is NOT production-ready. External approvals, recovery trials and signed-update trust remain open.')


def build_portable():
    preflight(require_windows=True,require_dependencies=True)
    run_tests()
    print('[BUILD] Creating optional portable one-file executable...')
    data_separator=os.pathsep
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole',
         '--name',APP_NAME+'_Portable','--icon',ROOT/'brand_assets'/'CRYPTO_NOCTURNE.ico',
         '--distpath',OUTPUT_ROOT/'dist_portable','--workpath',OUTPUT_ROOT/'build_portable',
         '--specpath',OUTPUT_ROOT/'build_portable',
         '--add-data',f'{ROOT/"brand_assets"}{data_separator}brand_assets',
         '--add-data',f'{ROOT/"data"}{data_separator}data',
         '--add-data',f'{ROOT/"vaultmesh"}{data_separator}vaultmesh',
         '--collect-all','bip_utils','--collect-all','web3','--collect-all','eth_account',
         '--collect-all','qrcode', '--hidden-import','socks',ROOT/'crypto.py']
    run(cmd)
    expected=OUTPUT_ROOT/'dist_portable'/(APP_NAME+'_Portable.exe')
    if not expected.is_file():raise RuntimeError('Portable EXE not found after build')
    print(f'[SUCCESS] PORTABLE EXE: {expected}')


def main(argv=None):
    parser=argparse.ArgumentParser(description='Build CRYPTO NOCTURNE Windows EXE and installer')
    parser.add_argument('action',choices=['check','test','release-check','exe','installer','full','portable'],nargs='?',default='check')
    options=parser.parse_args(argv)
    started=time.monotonic()
    try:
        if options.action=='check':preflight()
        elif options.action=='test':preflight();run_tests()
        elif options.action=='release-check':
            from release_ops import assess_release
            result=assess_release(ROOT)
            for gate in result['checks']+result['external_requirements']:
                print('['+gate['status']+'] '+gate['id'])
            if any(g['status']=='FAIL_LOCAL' for g in result['checks']):
                raise RuntimeError('Phase-18 local deployment checks failed')
            print('[INFO] Production remains BLOCKED; local checks are not independent approvals.')
        elif options.action=='exe':build_exe()
        elif options.action=='installer':build_installer()
        elif options.action=='full':
            build_exe()
            build_installer()
        elif options.action=='portable':build_portable()
        print(f'[DONE] {options.action} completed in {time.monotonic()-started:.1f}s')
        return 0
    except (OSError,RuntimeError,subprocess.CalledProcessError) as exc:
        print(f'[FAILED] {exc}',file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
