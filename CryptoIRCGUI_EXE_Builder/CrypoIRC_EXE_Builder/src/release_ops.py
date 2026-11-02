"""Phase 18 offline release operations and support evidence.

No network calls, no wallet access, no automatic upgrades and no release approvals.
Only a separately pinned Ed25519 key can authenticate a candidate installer.
Checking a signature never grants permission to process real money.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote

VERSION = '4.5.1'
SCHEMA = 1
APP = 'CRYPTO_NOCTURNE'
MAX_UPDATE_BYTES = 2 * 1024 * 1024 * 1024
HASH_RE = re.compile(r'[0-9a-f]{64}\Z')
VERSION_RE = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')

class ReleaseOpsError(ValueError):
    pass


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _version(value):
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise ReleaseOpsError('Release version must be a three-part numeric version.')
    return tuple(int(x) for x in value.split('.'))


def check_installer_policy(path):
    """Static checks only, NOT a real installation/upgrade test."""
    try:
        value = Path(path).read_text(encoding='utf-8')
    except OSError:
        return False, 'Installer source not available.'
    expectations = (
        (r'(?mi)^\s*AppId\s*=\s*\{\{DC6E2F6D-11DA-4E4E-AE51-3DBEC5B40CE2\}\s*$', 'stable application identity'),
        (r'(?mi)^\s*#define AppVersion "4\.5\.1"\s*$', 'current version'),
        (r'(?mi)^\s*PrivilegesRequired\s*=\s*lowest\s*$', 'unprivileged installation'),
        (r'(?mi)^\s*UsePreviousAppDir\s*=\s*yes\s*$', 'stable upgrade destination'),
        (r'(?mi)^\s*Source:\s*"\.\.\\dist\\CRYPTO_NOCTURNE\\\*";', 'binary-only installer'),
    )
    if any(not re.search(pattern, value) for pattern, _ in expectations):
        return False, 'Installer policy source checks did not pass.'
    if re.search(r'(?mi)^\s*\[(?:UninstallDelete|InstallDelete|Code)\]\s*$', value):
        return False, 'Installer contains an unreviewed destructive or scripted section.'
    # An installer may not package user vaults or raw project source.
    if re.search(r'(?mi)^\s*Source:\s*[^\r\n]*(?:\.vault|\.sqlite|wallet\.db|\.py\b)', value):
        return False, 'Installer source pattern may include private or source data.'
    return True, 'Static installer upgrade policy passed; Windows install/upgrade remains unverified.'


def _source_check(source):
    if not (source/'build_release.py').is_file():
        return False, 'Source code not available in this distribution.'
    try:
        import build_release
        missing = [x for x in build_release.REQUIRED if not (source/x).is_file()]
        secrets = build_release.scan_sources_for_secrets(source)
        return not (missing or secrets), ('Source/layout and credential-file scan passed.' if not (missing or secrets)
                                       else 'Source/layout or credential-file scan failed.')
    except (ImportError, OSError, RuntimeError):
        return False, 'Source scan could not complete.'


def assess_release(source=None):
    """Never elevate a local diagnostic to independent production approval."""
    source = Path(source or Path(__file__).resolve().parent).resolve()
    exists = (source/'build_release.py').is_file()
    checks = []
    def add(name, ok, note):
        checks.append({'id': name, 'status': 'PASS_LOCAL' if ok else 'NOT_RUN' if not exists else 'FAIL_LOCAL', 'note':note})
    ok, note = _source_check(source)
    add('SOURCE_SANITIZATION', ok, note)
    ok, note = check_installer_policy(source/'installer.iss')
    add('UPGRADE_POLICY_SOURCE', ok, note)
    has_cli = (source/'release_ops_cli.py').is_file() and (source/'tests'/'test_release_ops_v45.py').is_file()
    add('RELEASE_TOOLING_PRESENT', has_cli, 'Local release CLI and negative-test suite present.' if has_cli else 'Release source tooling unavailable.')
    signed = [
        {'id':'WINDOWS_SIGNED_INSTALLER', 'status':'BLOCKED_EXTERNAL', 'note':'Windows installer must be compiled, signed, timestamped, and validated on target machines.'},
        {'id':'UPGRADE_ROLLBACK_DRILL', 'status':'BLOCKED_EXTERNAL', 'note':'Independent install/upgrade/rollback trial using disposable wallets is required.'},
        {'id':'SIGNED_UPDATE_TRUST', 'status':'BLOCKED_EXTERNAL', 'note':'Publisher signing key must be established and fingerprint distributed securely outside the update channel.'},
        {'id':'INCIDENT_RESPONSE_DRILL', 'status':'BLOCKED_EXTERNAL', 'note':'Operational drill, custody controls, responder ownership, service telemetry, and recovery objectives need review.'},
    ]
    return {'schema':SCHEMA, 'version':VERSION, 'application':'CRYPTO NOCTURNE',
            'production_ready':False, 'real_money_approved':False, 'release_status':'BLOCKED',
            'generated_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'checks':checks, 'external_requirements':signed,
            'warnings':['Local preflight is not deployment certification.',
                        'No user wallet data, node credentials, arbitrary logs, addresses or secrets were inspected.',
                        'Automatic internet updates are intentionally disabled pending a trusted distribution channel.']}


def make_sbom(requirements_file):
    """CycloneDX direct-dependency inventory; NOT full resolved SBOM/vulnerability audit."""
    path = Path(requirements_file)
    components = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        matched = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[A-Za-z0-9_,.-]+\])?==([A-Za-z0-9_.+-]+)', line)
        if not matched:
            raise ReleaseOpsError('All direct dependencies must be pinned with == and no environment-dependent expressions.')
        name = matched.group(1).lower().replace('_','-')
        version = matched.group(2)
        components.append({'type':'library', 'name':name, 'version':version,
                           'purl':f'pkg:pypi/{quote(name)}@{quote(version)}',
                           'scope':'required'})
    if not components:raise ReleaseOpsError('Empty dependency inventory.')
    return {'bomFormat':'CycloneDX','specVersion':'1.5','version':1,
            'metadata':{'component':{'type':'application','name':APP,'version':VERSION}},
            'components':sorted(components,key=lambda item:item['name']),
            'properties':[{'name':'nocturne:scope','value':'direct requirements only; transitive frozen components not enumerated'},
                          {'name':'nocturne:approval','value':'experimental; not audited or approved'}]}


def _public_key(path, expected_sha256):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(expected_sha256,str) or not HASH_RE.fullmatch(expected_sha256):
        raise ReleaseOpsError('Expected trusted public-key SHA-256 fingerprint is mandatory.')
    try:
        key = serialization.load_pem_public_key(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise ReleaseOpsError('Trusted public-key file invalid.') from exc
    if not isinstance(key,Ed25519PublicKey):
        raise ReleaseOpsError('Only Ed25519 public keys are supported.')
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest()!=expected_sha256:
        raise ReleaseOpsError('Trusted public-key fingerprint mismatch. Update rejected.')
    return key


def verify_signed_update(manifest, artifact, trusted_public_key, expected_key_sha256, *, current_version=VERSION):
    """Verify a locally staged installer offline. Does NOT execute or install it.

    Trust is anchored by a *separately* confirmed public-key SHA-256 fingerprint,
    never by the downloaded manifest itself or a key inside the update package.
    """
    from cryptography.exceptions import InvalidSignature
    manifest, artifact = Path(manifest), Path(artifact)
    if manifest.is_symlink() or artifact.is_symlink() or not artifact.is_file():
        raise ReleaseOpsError('Update files are missing or symbolic links.')
    try:
        if manifest.stat().st_size > 64*1024:
            raise ReleaseOpsError('Update metadata is unexpectedly large.')
    except OSError as exc:
        raise ReleaseOpsError('Update metadata is unavailable.') from exc
    try:
        envelope = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ReleaseOpsError('Invalid update envelope.') from exc
    if not isinstance(envelope,dict) or set(envelope)!={'payload','signature_base64'}:
        raise ReleaseOpsError('Unexpected update envelope shape.')
    payload, signature = envelope['payload'],envelope['signature_base64']
    required = {'schema','application','channel','platform','version','artifact','bytes','sha256','minimum_from'}
    if not isinstance(payload,dict) or set(payload)!=required:
        raise ReleaseOpsError('Unrecognized signed metadata fields.')
    if payload['schema']!=SCHEMA or payload['application']!=APP or payload['channel']!='stable' or payload['platform']!='windows-x86_64':
        raise ReleaseOpsError('Update targets an unsupported application, channel or platform.')
    new = _version(payload['version'])
    current = _version(current_version)
    minimum = _version(payload['minimum_from'])
    if new <= current or current < minimum:
        raise ReleaseOpsError('Update is a downgrade, duplicate or skips its minimum-supported version.')
    expected_filename = f'CRYPTO_NOCTURNE_Setup_v{payload["version"]}.exe'
    if payload['artifact']!=expected_filename or artifact.name!=expected_filename:
        raise ReleaseOpsError('Installer filename/version mismatch.')
    if type(payload['bytes']) is not int or not 0 < payload['bytes'] <= MAX_UPDATE_BYTES or not isinstance(payload['sha256'],str) or not HASH_RE.fullmatch(payload['sha256']):
        raise ReleaseOpsError('Update size or checksum field is invalid.')
    if not isinstance(signature,str):raise ReleaseOpsError('Signature must be text.')
    try:
        raw_signature=base64.b64decode(signature,validate=True)
    except (ValueError,base64.binascii.Error) as exc:
        raise ReleaseOpsError('Invalid signature encoding.') from exc
    if len(raw_signature)!=64:raise ReleaseOpsError('Invalid Ed25519 signature length.')
    key = _public_key(trusted_public_key,expected_key_sha256)
    try:
        key.verify(raw_signature,_canonical(payload))
    except InvalidSignature as exc:
        raise ReleaseOpsError('Signature verification failed. Update rejected.') from exc
    if artifact.stat().st_size!=payload['bytes'] or sha256_file(artifact)!=payload['sha256']:
        raise ReleaseOpsError('Installer bytes differ from signed manifest.')
    # Windows also requires Microsoft platform code-signing validation before
    # the staged artifact can be considered fully verified for this host.
    authenticode = False
    if os.name=='nt':
        try:
            from release_security import verify_windows_signature
            verify_windows_signature(artifact)
            authenticode = True
        except (ImportError,OSError,RuntimeError) as exc:
            raise ReleaseOpsError('Windows installer Authenticode validation failed.') from exc
    return {'verified':True,'version':payload['version'],'artifact_sha256':payload['sha256'],
            'result':'Pinned publisher-key and bytes verified offline; no update was installed.',
            'authenticode_checked':authenticode,'installed':False,'production_ready':False}


def write_exclusive_json(report,destination,*,project_root=None):
    """Create a sanitized diagnostics report without replacing existing files."""
    target=Path(destination).expanduser()
    if not target.is_absolute() or target.is_symlink():
        raise ReleaseOpsError('Choose a new absolute destination outside the source tree.')
    root=Path(project_root or Path(__file__).resolve().parent.parent).resolve()
    if target.resolve(strict=False).is_relative_to(root):
        raise ReleaseOpsError('Reports must not be stored inside the source/release tree.')
    # Never accept arbitrary supporting data; only this exact assessment schema.
    if not isinstance(report,dict) or report.get('application')!='CRYPTO NOCTURNE' or report.get('version')!=VERSION or report.get('production_ready') is not False:
        raise ReleaseOpsError('Invalid release diagnostics schema.')
    allowed={'schema','version','application','production_ready','real_money_approved','release_status',
             'generated_utc','checks','external_requirements','warnings'}
    date=report.get('generated_utc')
    if not isinstance(date,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00',date):
        raise ReleaseOpsError('Diagnostic time format rejected.')
    if set(report)!=allowed or report.get('schema')!=SCHEMA or report.get('release_status')!='BLOCKED' or report.get('real_money_approved') is not False or not isinstance(report.get('checks'),list):
        raise ReleaseOpsError('Diagnostics schema rejected.')
    # Further allowlist and fixed notes prevent caller from injecting secrets.
    expected=assess_release()
    identifiers={x['id'] for x in expected['checks']}
    if len(report['checks'])!=len(expected['checks']) or {x.get('id') for x in report['checks']}!=identifiers or report['external_requirements']!=expected['external_requirements'] or report['warnings']!=expected['warnings']:
        raise ReleaseOpsError('Diagnostics content is not from the supported release checker.')
    for item in report['checks']:
        baseline=next(x for x in expected['checks'] if x['id']==item.get('id'))
        if item.get('status')!=baseline['status'] or item.get('note')!=baseline['note']:
            raise ReleaseOpsError('Diagnostic check no longer matches current local result.')
        if item.get('status') not in ('PASS_LOCAL','FAIL_LOCAL','NOT_RUN') or item.get('note') not in (
            'Source/layout and credential-file scan passed.', 'Source/layout or credential-file scan failed.',
            'Source scan could not complete.', 'Source code not available in this distribution.',
            'Installer source not available.', 'Installer policy source checks did not pass.',
            'Installer contains an unreviewed destructive or scripted section.',
            'Installer source pattern may include private or source data.',
            'Static installer upgrade policy passed; Windows install/upgrade remains unverified.',
            'Local release CLI and negative-test suite present.', 'Release source tooling unavailable.'):
            raise ReleaseOpsError('Unapproved free-form diagnostic content.')
    data = (_canonical(report)+b'\n')
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ReleaseOpsError('Report export failed; target must not exist.') from exc
    return target


INCIDENT_PLAYBOOK = (
    ('01 ISOLATE','Disconnect affected app instance and revoke compromised service credentials. Never submit seeds or keys to support.'),
    ('02 PRESERVE','Record UTC occurrence time, affected version and error category without user addresses, passwords, private keys or raw wallet logs.'),
    ('03 CONTAIN','Stop unverified auto-updates, freeze provider payouts, quarantine malicious packages. Do not automatically rebroadcast unknown transactions.'),
    ('04 RECOVER','Use an independently verified offline backup; rehearse restore with test-only wallets and separate machines. Verify state before return to service.'),
    ('05 REVIEW','Assign incident owner, publish a redacted notice, capture remediation evidence, require independent sign-off before reopening.'),
)
