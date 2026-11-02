"""Source-only offline QA command. No live network calls unless --btc-regtest."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from qa_runtime import assess,export_report,QAError

def main(argv=None):
    p=argparse.ArgumentParser(description='Local QA evidence, never a production release approval')
    p.add_argument('--check-only',action='store_true',help='Source scan only; skip local regression tests')
    p.add_argument('--btc-regtest',action='store_true',help='Opt in to temporary regtest bitcoind integration; never mainnet')
    p.add_argument('--report',type=Path,help='Create exclusive JSON report at an absolute path outside the project')
    args=p.parse_args(argv)
    source=Path(__file__).resolve().parent
    result=assess(source=source,run_tests=not args.check_only,run_btc_regtest=args.btc_regtest)
    print('CRYPTO NOCTURNE v4.5.1 QA — NOT A CERTIFICATE')
    for g in result['gates']:
        print(f"[{g['status']}] {g['id']}: {g['name']}")
    s=result['summary'];t=result['tests']
    print(f"Local tests: {t['regression']['total']} run; {t['regression']['skipped']} skipped")
    print(f"Local gate passes: {s['PASS_LOCAL']}; external blockers: {s['BLOCKED_EXTERNAL']}")
    print('PRODUCTION: BLOCKED. No mainnet or fiat status is inferred.')
    if args.report:
        try:export_report(result,args.report)
        except QAError as exc:
            print('Report not written:',str(exc),file=sys.stderr);return 2
        print('Local unsigned report written (not a certificate).')
    return 1 if s['FAIL_LOCAL'] or (not args.check_only and s['NOT_RUN']>=2) else 0

if __name__=='__main__':raise SystemExit(main())
