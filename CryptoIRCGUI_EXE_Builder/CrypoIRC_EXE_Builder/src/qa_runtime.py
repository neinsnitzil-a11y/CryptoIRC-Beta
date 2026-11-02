"""Phase 17: conservative, repeatable transaction QA evidence and release blockers.

No transaction signing, key access, external provider calls or live-money operations
occur in this module. Local tests are *not* mainnet certification. The report's
SHA-256 detects accidental edits only; it is not authenticated evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

VERSION = '4.5.1'
SCHEMA = 1

# External gates are intentionally never cleared by code presence, locally
# generated files, or a claimed approval string. Independent verification is
# outside the authority of this application.
REQUIREMENTS = (
    ('SRC_PREFLIGHT', 'Local source and secret-file preflight', 'local',
     'Required source files exist and release source excludes wallet/credential files.'),
    ('REGRESSION', 'Full local regression suite', 'local',
     'All discovered source regression tests exit successfully in an isolated workspace.'),
    ('FAULT_MATRIX', 'Transaction-failure regression matrix', 'local',
     'Specialized tests reject duplicates, preserve unknown status and recover journal states.'),
    ('BTC_REGTEST', 'Bitcoin Core regtest integration', 'optional',
     'Run the existing isolated real bitcoind send, confirmation and backup-restore test.'),
    ('BTC_MAINNET', 'Controlled BTC mainnet send/receive', 'external',
     'Independent authorized real-node trial, finality, reorg and recovery evidence.'),
    ('EVM_TESTNET', 'EVM public-testnet send and restore', 'external',
     'Live nonce, fee, broadcast, reorg and token-event checks against supported RPC.'),
    ('XMR_STAGENET', 'Monero stagenet send and recovery', 'external',
     'Actual wallet-RPC relay, scan, subaddress and independent restore evidence.'),
    ('MULTICHAIN_SPEND', 'Remaining coin and token spending', 'external',
     'Each advertised supported asset independently passes signed send and recovery matrix.'),
    ('WALLET_RECOVERY', 'Independent wallet recovery drill', 'external',
     'Restore all enabled wallet families in independent software/hardware and verify access.'),
    ('SETTLEMENT', 'Live fiat/provider settlement and reconciliation', 'external',
     'Approved provider, verified events, refund/chargeback controls and on-chain delivery.'),
    ('CRYPTO_AUDIT', 'External cryptography and key-management audit', 'external',
     'Independent findings remediated and re-tested; coverage includes wallet and signing.'),
    ('APP_PENTEST', 'External security and P2P/Tor penetration testing', 'external',
     'Independent desktop, backend, mesh, remote-node and key-isolation test report.'),
    ('WINDOWS_RUNTIME', 'Windows frozen EXE / installer end-to-end', 'external',
     'Target-machine compiled app runs send/recovery/upgrade smoke tests.'),
    ('SIGNED_DISTRIBUTION', 'Authenticode, update authenticity and SBOM', 'external',
     'Externally verified installer signature, secure updates and dependency security review.'),
    ('DISASTER_RECOVERY', 'Real service disaster-recovery exercise', 'external',
     'Verified restore, operational monitoring, incident response and target SLOs.'),
    ('REGULATORY', 'Provider approvals and applicable legal compliance', 'external',
     'Independent provider/legal sign-off for actual custody, payments and jurisdictions.'),
)

class QAError(ValueError):
    pass


def _gate(gate_id, name, kind, requirement, *, status='BLOCKED_EXTERNAL', note=''):
    return {'id':gate_id,'name':name,'kind':kind,'status':status,
            'requirement':requirement,'note':note or requirement}


def _suite(source: Path, *, pattern: str, timeout: int):
    """Run source tests in disposable CWD; never save or return test output.

    Fail closed on timeout, crashes, or a missing 'Ran N tests / OK' marker.
    Tests are not permitted to write persistent state inside the source tree.
    """
    with tempfile.TemporaryDirectory(prefix='nocturne-qa-') as scratch:
        env=os.environ.copy()
        env['PYTHONPATH']=str(source)+os.pathsep+env.get('PYTHONPATH','')
        env['CRYPTO_RELAY_DATABASE']=str(Path(scratch)/'isolated_relay.sqlite3')
        cmd=[sys.executable,'-m','unittest','discover','-s',str(source/'tests'),
             '-p',pattern,'-q']
        try:
            proc=subprocess.run(cmd,cwd=scratch,env=env,text=True,
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                timeout=timeout,check=False)
        except (subprocess.TimeoutExpired, OSError):
            return {'passed':False,'total':0,'skipped':0,'note':'Test execution unavailable or timed out.'}
    combined=proc.stdout+'\n'+proc.stderr
    found=re.search(r'Ran (\d+) tests? in ',combined)
    total=int(found.group(1)) if found else 0
    skipped=re.search(r'OK \(skipped=(\d+)\)',combined)
    skipped_count=int(skipped.group(1)) if skipped else 0
    success=proc.returncode==0 and total>0 and bool(re.search(r'(?m)^OK(?: \(skipped=\d+\))?\s*$',combined))
    return {'passed':success,'total':total,'skipped':skipped_count,
            'note':'Source tests passed locally.' if success else 'Source tests failed; inspect your local test output.'}


def _source_preflight(source:Path):
    try:
        # No secret values or absolute paths from the scan are returned to a report.
        import build_release
        required=build_release.REQUIRED
        missing=sum(not (source/name).is_file() for name in required)
        suspects=build_release.scan_sources_for_secrets(source)
        if missing or suspects:
            return {'passed':False,'note':'Source audit failed: missing required components or unexpected wallet/credential files.'}
        return {'passed':True,'note':'Required modules present; no wallet or credential files found in source.'}
    except (OSError,ImportError,RuntimeError):
        return {'passed':False,'note':'Source audit unavailable.'}


def _regtest(source:Path, *, timeout=180):
    # The controlled harness starts its own temporary -regtest bitcoind; no
    # mainnet connection and no real-value bitcoin are involved.
    script=source/'tests'/'bitcoin_core_regtest_e2e.py'
    if not script.is_file():return 'FAIL_LOCAL','Regtest test harness is missing.'
    with tempfile.TemporaryDirectory(prefix='nocturne-regtest-check-') as scratch:
        try:
            proc=subprocess.run([sys.executable,str(script)],cwd=scratch,
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                text=True,timeout=timeout,check=False)
        except (OSError,subprocess.TimeoutExpired):
            return 'FAIL_LOCAL','Regtest test could not finish.'
    if proc.returncode==0 and '[PASS] REGTEST:' in proc.stdout:
        return 'PASS_TESTNET','Isolated bitcoind regtest completed. Not mainnet proof.'
    if proc.returncode==2:return 'NOT_RUN','Verified bitcoind executable not available; regtest not run.'
    return 'FAIL_LOCAL','Real bitcoind regtest did not pass; inspect local developer output.'


def assess(*, source:Path|str, run_tests:bool=False, run_btc_regtest:bool=False):
    """Build an *untrusted local* QA snapshot, never a certificate of safety."""
    source=Path(source).resolve()
    # Source-only suite not available in a PyInstaller frozen distribution.
    in_source=bool((source/'tests').is_dir() and (source/'build_release.py').is_file())
    scan=_source_preflight(source) if in_source else {'passed':False,'note':'Source tree unavailable (frozen executable).'}
    local={
        'SRC_PREFLIGHT':('PASS_LOCAL' if scan['passed'] else 'FAIL_LOCAL',scan['note']),
        'REGRESSION':('NOT_RUN','Full source test suite has not been run.'),
        'FAULT_MATRIX':('NOT_RUN','Specialized transaction-failure matrix has not been run.'),
        'BTC_REGTEST':('NOT_RUN','Optional isolated bitcoind regtest has not been run.'),
    }
    stats={'regression':{'total':0,'skipped':0},'fault_matrix':{'total':0,'skipped':0}}
    if run_tests:
        if not in_source:
            local['REGRESSION']=('NOT_RUN','Source tests unavailable in frozen application.')
            local['FAULT_MATRIX']=('NOT_RUN','Source tests unavailable in frozen application.')
        elif not scan['passed']:
            local['REGRESSION']=('NOT_RUN','Source preflight failed; tests blocked.')
            local['FAULT_MATRIX']=('NOT_RUN','Source preflight failed; tests blocked.')
        else:
            full=_suite(source,pattern='test_*.py',timeout=240)
            focused=_suite(source,pattern='test_transaction_fault_matrix_v44.py',timeout=90)
            for ident,result in [('REGRESSION',full),('FAULT_MATRIX',focused)]:
                local[ident]=('PASS_LOCAL' if result['passed'] else 'FAIL_LOCAL',result['note'])
            stats={'regression':{'total':full['total'],'skipped':full['skipped']},
                   'fault_matrix':{'total':focused['total'],'skipped':focused['skipped']}}
    if run_btc_regtest:
        local['BTC_REGTEST']=_regtest(source) if in_source and scan['passed'] else ('NOT_RUN','Source or preflight unavailable.')
    gates=[]
    for ident,name,kind,requirement in REQUIREMENTS:
        status,note=local.get(ident,('BLOCKED_EXTERNAL','Requires verifiable external evidence and independent approval.'))
        gates.append(_gate(ident,name,kind,requirement,status=status,note=note))
    status_counts={s:sum(g['status']==s for g in gates)
                   for s in ('PASS_LOCAL','PASS_TESTNET','NOT_RUN','FAIL_LOCAL','BLOCKED_EXTERNAL')}
    result={
        'schema':SCHEMA,'application':'CRYPTO NOCTURNE','version':VERSION,
        'generated_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'release_status':'BLOCKED', 'production_ready':False,
        'real_money_approved':False, 'independently_certified_assets':0,
        'summary':status_counts,'tests':stats,'gates':gates,
        'warning':'Local source tests, hashes and simulated RPCs are not audits or proof of live transactions. '
                  'Independent external gates cannot be cleared by this software.'
    }
    digest=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result['sha256_untrusted']=digest
    return result


def validate_report(report):
    """Validate structure/hash for accidental corruption; never attest authenticity."""
    if not isinstance(report,dict) or report.get('schema')!=SCHEMA or report.get('version')!=VERSION:
        raise QAError('Unexpected QA report schema or version.')
    if report.get('production_ready') is not False or report.get('real_money_approved') is not False or report.get('release_status')!='BLOCKED':
        raise QAError('QA report cannot authorize production.')
    prior=report.get('sha256_untrusted')
    if not isinstance(prior,str) or not re.fullmatch(r'[0-9a-f]{64}',prior):raise QAError('Missing report hash.')
    payload={k:v for k,v in report.items() if k!='sha256_untrusted'}
    if hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=prior:
        raise QAError('QA report modified or corrupt. This is not a signature verification.')
    if [g.get('id') for g in report.get('gates',[])] != [row[0] for row in REQUIREMENTS]:
        raise QAError('Incomplete QA release gates.')
    for row in report['gates']:
        if row['kind']=='external' and row['status']!='BLOCKED_EXTERNAL':
            raise QAError('External QA gate cannot be approved locally.')
    return True


def export_report(report, destination):
    validate_report(report)
    target=Path(destination).expanduser()
    if not target.is_absolute():raise QAError('Choose an absolute export path.')
    if target.is_symlink():raise QAError('Refusing to write to a symbolic link.')
    # A QA export is generated operational data, not release source. Never save
    # it under the packaged project directory (even via a symlinked parent).
    try:
        if target.resolve(strict=False).is_relative_to(Path(__file__).resolve().parent.parent):
            raise QAError('Export outside the application project folder.')
    except (OSError,RuntimeError) as exc:
        raise QAError('Cannot validate QA report destination.') from exc
    payload=(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=True)+'\n').encode('utf-8')
    flags=os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
    try:
        fd=os.open(target,flags,0o600)
        try:
            with os.fdopen(fd,'wb',closefd=True) as stream:
                stream.write(payload)
                stream.flush();os.fsync(stream.fileno())
        except Exception:
            try:target.unlink(missing_ok=True)
            except OSError:pass
            raise
    except (OSError,ValueError) as exc:
        raise QAError('QA export failed or target already exists.') from exc
    return target
