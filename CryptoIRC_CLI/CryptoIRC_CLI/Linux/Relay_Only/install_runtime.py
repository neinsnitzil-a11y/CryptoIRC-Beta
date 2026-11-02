#!/usr/bin/env python3
"""Small chat-only dependency installer. No wallet source or credentials."""
from pathlib import Path
import os
import subprocess
import sys
ROOT=Path(__file__).resolve().parent

def run(args):
    print('[RUN] '+ ' '.join(map(str,args)),flush=True)
    subprocess.run(args,cwd=ROOT,check=True)

def main():
    if sys.version_info[:2] != (3,12):
        raise RuntimeError('Chat relay requires CPython 3.12, not system Python 3.14')
    env=ROOT/'.venv'
    py=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if py.is_file():
        current=subprocess.run([str(py),'-c','import sys; print(sys.version_info[:2])'],capture_output=True,text=True)
        if current.returncode or '(3, 12)' not in current.stdout:
            for i in range(1,100):
                backup=ROOT/f'.venv.incompatible-backup-{i}'
                if not backup.exists():
                    env.rename(backup)
                    break
            else:
                raise RuntimeError('Too many old virtual environments')
    if not py.is_file():
        uv=os.environ.get('VAULTFORGE_UV')
        if uv:run([uv,'venv','--python',sys.executable,str(env)])
        else:run([sys.executable,'-m','venv',str(env)])
    uv=os.environ.get('VAULTFORGE_UV')
    if uv:run([uv,'pip','install','--python',str(py),'-r',str(ROOT/'requirements.txt')])
    else:
        run([str(py),'-m','pip','install','--require-virtualenv','--upgrade','pip'])
        run([str(py),'-m','pip','install','--require-virtualenv','-r',str(ROOT/'requirements.txt')])
    run([str(py),'-I',str(ROOT/'mesh_chat.py'),'--help'])
    print('[OK] Chat-only installed; no wallet dependencies or vault data loaded.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'[ERROR] Relay-only installation failed: {exc}',file=sys.stderr)
        sys.exit(1)
