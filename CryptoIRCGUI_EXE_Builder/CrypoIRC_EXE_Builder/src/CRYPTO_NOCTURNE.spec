# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir distribution of the financial desktop client ONLY.

The source includes an optional WAN relay under server/. It must NOT be
bundled into the desktop EXE. This spec includes only curated static data.
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

source_root = Path.cwd().resolve()
icon_file = str(source_root / 'brand_assets' / 'CRYPTO_NOCTURNE.ico')
static_files = [
    (str(source_root / 'brand_assets'), 'brand_assets'),
    (str(source_root / 'data'), 'data'),
    # Chat worker uses an isolated subprocess and imports matching wire-protocol
    # modules from data/vaultmesh at runtime; no server credentials included.
    (str(source_root / 'vaultmesh'), 'vaultmesh'),
]
# Only runtime resources belong in a customer-facing desktop distribution.
# collect_all() without filters pulls in qrcode.tests, Web3 test contract fixtures,
# and other development modules. Those caused the 2.3.2 package-audit failure.
_TEST_SEGMENTS = {'test', 'tests', 'testing', '__pycache__'}
def _production_submodule(name):
    return not any(segment.lower() in _TEST_SEGMENTS for segment in name.split('.'))

def _production_data(item):
    # (source, destination) pairs collected by PyInstaller.
    source, destination = item[:2]
    parts = Path(str(source)).parts + Path(str(destination)).parts
    return not any(part.lower() in _TEST_SEGMENTS for part in parts)

# Native and dynamically loaded dependencies of bip-utils are not reliably
# discovered from import statements alone. Include their Python modules and
# compiled binary extensions, but never bundled test directories. The frozen
# wallet self-test below remains mandatory, because collection is not proof.
from importlib.util import find_spec
hidden = ['socks', 'websockets', 'websockets.sync.client']
extra_binaries = []
_CRYPTO_RUNTIME_PACKAGES = (
    'bip_utils', 'coincurve', 'cbor2', 'ecdsa', 'ed25519_blake2b',
    'sr25519', 'x25519', 'nacl', 'argon2', 'Crypto', 'Cryptodome',
    'pytoniq_core', 'py_ecc', 'eth_utils', 'web3', 'eth_account', 'qrcode',
)
for package_name in _CRYPTO_RUNTIME_PACKAGES:
    # Different bip-utils releases expose some extensions under different
    # import names. Missing optional packages are not synthesized or faked.
    module_spec = find_spec(package_name)
    if module_spec is None:
        continue
    if module_spec.submodule_search_locations is None:
        # Native extension modules such as sr25519 are not Python packages:
        # tell PyInstaller to include the extension directly instead of
        # calling collect_all() on a module with no package directory.
        hidden.append(package_name)
        continue
    pkg_data, pkg_binaries, pkg_hidden = collect_all(
        package_name,
        include_py_files=False,
        filter_submodules=_production_submodule,
        exclude_datas=['**/tests/**', '**/test/**', '**/testing/**', '**/__pycache__/**'],
    )
    static_files.extend(item for item in pkg_data if _production_data(item))
    extra_binaries.extend(item for item in pkg_binaries if _production_data(item))
    hidden.extend(module for module in pkg_hidden if _production_submodule(module))
# Do not accidentally turn a compatibility exclusion into a silent wallet
# fallback. The bundled runtime self-test must still derive and restore funds-
# free test wallets before the builder will run Inno Setup.
hidden = sorted(set(hidden))

analysis = Analysis(
    [str(source_root / 'crypto.py')],
    pathex=[str(source_root)],
    binaries=extra_binaries,
    datas=static_files,
    hiddenimports=hidden,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'IPython', 'jupyter', 'notebook', 'financial_backend', 'server',
              'tests', 'build_release', 'builder_gui', 'qa_runner', 'release_ops_cli',
              'qrcode.tests', 'web3._utils.module_testing'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True,
    name='CRYPTO_NOCTURNE',
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    disable_windowed_traceback=False,
    icon=icon_file,
)
coll = COLLECT(
    exe, analysis.binaries, analysis.zipfiles, analysis.datas,
    strip=False, upx=False,
    name='CRYPTO_NOCTURNE',
)
