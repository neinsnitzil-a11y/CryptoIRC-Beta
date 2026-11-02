"""Reproducibility / client-asset checks. Signing requires external trusted tools.
Do not present this as an audit or a substitute for vulnerability scanning.
"""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
import importlib.metadata as metadata

BASE=Path(__file__).resolve().parent
APP='CRYPTO_NOCTURNE'

class ReleaseBlocked(RuntimeError):pass

def _bundled_private_component(path):
    """Only application-owned privileged components are prohibited.

    PyInstaller's third-party packages can contain harmless `tests` and
    `server` subfolders. A generic `'/tests/' in path` rule caused false
    failures. It cannot distinguish unrelated package data from OUR backend.
    """
    parts=Path(path).as_posix().lower().split('/')
    if parts and parts[0] == '_internal':
        parts=parts[1:]
    return bool(parts and parts[0] in ('financial_backend','server','tests'))


def distribution_audit(location):
    root=Path(location)
    if not root.is_dir():raise ReleaseBlocked('Compiled distribution does not exist')
    from build_release import scan_distribution_for_secrets
    bad=scan_distribution_for_secrets(root)
    if bad:raise ReleaseBlocked('Personal files found in build: '+', '.join(bad))
    files=[x.relative_to(root).as_posix() for x in root.rglob('*') if x.is_file()]
    blocked=[item for item in files if _bundled_private_component(item)]
    if blocked:
        raise ReleaseBlocked('Private application backend, relay, or application tests in desktop bundle: '
                             +', '.join(blocked[:20]))
    # Runtime modules are also excluded at PyInstaller Analysis level in the spec.
    # The compiled PYZ module archive is not independently audited here.
    if not (root/(APP+'.exe')).is_file():raise ReleaseBlocked('Desktop executable missing')
    return len(files)

def sign_executable(exe,thumbprint):
    if os.name!='nt':raise ReleaseBlocked('Authenticode signing must run on Windows')
    if not thumbprint or not all(c in '0123456789abcdefABCDEF' for c in thumbprint) or len(thumbprint)!=40:
        raise ReleaseBlocked('Set CRYPTO_SIGN_CERT_SHA1 to the verified certificate thumbprint')
    import shutil
    signtool=shutil.which('signtool.exe') or os.environ.get('CRYPTO_SIGNTOOL_PATH','')
    if not signtool:raise ReleaseBlocked('Windows SDK signtool.exe not installed or configured')
    # No private key is ever included in the app. Certificate stays in Windows cert store / HSM.
    cmd=[signtool,'sign','/sha1',thumbprint,'/fd','SHA256','/tr','http://timestamp.digicert.com','/td','SHA256',str(exe)]
    subprocess.run(cmd,check=True,timeout=120)
    subprocess.run([signtool,'verify','/pa','/v',str(exe)],check=True,timeout=60)

def verify_windows_signature(executable):
    """Require an existing valid Windows Authenticode signature.

    A valid signing chain is NOT an external security audit or authorization to
    activate financial services. Certificate ownership/revocation remain review items.
    """
    if os.name!='nt':raise ReleaseBlocked('Authenticode verification requires a Windows host')
    import shutil
    signtool=shutil.which('signtool.exe') or os.environ.get('CRYPTO_SIGNTOOL_PATH','')
    if not signtool:raise ReleaseBlocked('Windows SDK signtool.exe not available')
    if not Path(executable).is_file():raise ReleaseBlocked('Signing target missing')
    try:
        subprocess.run([signtool,'verify','/pa','/v',str(executable)],check=True,timeout=60,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired,OSError) as exc:
        raise ReleaseBlocked('Windows Authenticode signature could not be verified') from exc
    return True

def dependencies():
    # Inventory NOT a vulnerability scan. Save as machine-readable artifact.
    return sorted(({'name':d.metadata.get('Name','unknown'),'version':d.version}
                  for d in metadata.distributions()),key=lambda x:x['name'].lower())

def package_manifest(location,output):
    root=Path(location);out=Path(output)
    files=[]
    for candidate in sorted(root.rglob('*')):
        if candidate.is_file() and candidate.resolve()!=out.resolve():
            digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
            files.append({'path':candidate.relative_to(root).as_posix(),'sha256':digest,'bytes':candidate.stat().st_size})
    result={'schema':1,'release':'development-unverified','source_dir':root.name,
            'created_utc':datetime.now(timezone.utc).isoformat(),'files':files,
            'note':'Checksum list is NOT a digital signature.'}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('operation',choices=['audit','inventory','sign','manifest'])
    ap.add_argument('--path',default='')
    ap.add_argument('--output',default='')
    a=ap.parse_args(argv)
    if a.operation=='inventory':
        f=Path(a.output or BASE.parent/'release'/'dependency_inventory.json');f.parent.mkdir(parents=True,exist_ok=True)
        f.write_text(json.dumps({'packages':dependencies(),'warning':'Inventory only; run pip-audit on build machine.'},indent=2),encoding='utf-8')
        print('Inventory:',f)
    elif a.operation=='audit':print('Audited files:',distribution_audit(a.path or BASE.parent/'dist'/APP))
    elif a.operation=='manifest':
        root=Path(a.path or BASE.parent/'dist'/APP);package_manifest(root,a.output or BASE.parent/'release'/'dist_manifest.json')
        print('SHA-256 manifest written. NOT SIGNED.')
    else:
        path=Path(a.path or BASE.parent/'release'/'CRYPTO_NOCTURNE_Setup_v4.5.1.exe')
        if not path.is_file():raise ReleaseBlocked('Installer missing')
        sign_executable(path,os.environ.get('CRYPTO_SIGN_CERT_SHA1',''))
        print('Installer signed and verified')
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ReleaseBlocked,subprocess.CalledProcessError) as exc:
        print('RELEASE BLOCKED:',exc,file=sys.stderr)
        raise SystemExit(1)
