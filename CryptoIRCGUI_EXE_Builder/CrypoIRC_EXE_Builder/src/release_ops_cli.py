"""Offline release checks; no automatic downloads or user wallet access."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from release_ops import assess_release,make_sbom,verify_signed_update,write_exclusive_json,ReleaseOpsError


def main(argv=None):
    p=argparse.ArgumentParser(description='CRYPTO NOCTURNE Phase 18 (offline, experimental)')
    commands=p.add_subparsers(dest='command',required=True)
    c=commands.add_parser('check',help='Local non-spending release checks')
    c.add_argument('--export',type=Path,help='New absolute file path outside project')
    s=commands.add_parser('sbom',help='Direct pinned dependency inventory, no vulnerability claims')
    s.add_argument('--export',required=True,type=Path)
    v=commands.add_parser('verify-update',help='Offline verification; NEVER installs the update')
    for name in ('manifest','artifact','trusted-key','trusted-key-sha256'):
        v.add_argument('--'+name,required=True)
    v.add_argument('--current-version',default='4.5.1')
    a=p.parse_args(argv)
    try:
        if a.command=='check':
            result=assess_release()
            for item in result['checks']+result['external_requirements']:
                print('['+item['status']+'] '+item['id'])
            print('PRODUCTION: BLOCKED; zero external approvals asserted')
            if a.export:
                write_exclusive_json(result,a.export)
                print('Local sanitized diagnostic report created (unsigned).')
            return 1 if any(c['status']=='FAIL_LOCAL' for c in result['checks']) else 0
        if a.command=='sbom':
            result=make_sbom(Path(__file__).resolve().parent/'requirements.txt')
            target=Path(a.export)
            if not target.is_absolute() or target.is_symlink() or target.exists() or target.resolve(strict=False).is_relative_to(Path(__file__).resolve().parent.parent):
                raise ReleaseOpsError('Choose a new absolute SBOM filename outside source tree.')
            # Refuse replace; report makes no claim about transitive/frozen libraries.
            with target.open('x',encoding='utf-8') as out:
                json.dump(result,out,indent=2)
            print('Direct-dependency CycloneDX inventory created (not a vulnerability audit).')
            return 0
        result=verify_signed_update(a.manifest,a.artifact,a.trusted_key,a.trusted_key_sha256,current_version=a.current_version)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ReleaseOpsError,OSError,ImportError,ValueError) as exc:
        # Intentionally no raw input/exception values; file paths may contain secrets.
        print('RELEASE BLOCKED: Offline verification or export failed. No updates installed.')
        return 2

if __name__=='__main__':raise SystemExit(main())
