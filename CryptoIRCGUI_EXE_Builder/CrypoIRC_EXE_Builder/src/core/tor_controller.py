"""Application-managed Tor Expert Bundle daemon (not Tor Browser or VPN).

The Tor executable must come from an independently verified Tor Project
installation. No silent downloads of unverified binaries. Tor mode applies to
P2P .onion connections only, not blockchain RPC or the rest of the OS.
"""
from __future__ import annotations
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path


class TorController:
    def __init__(self, folder=None, callback=None):
        self.folder=Path(folder or (Path.home()/'.crypto_creating_wallets'/'tor')).expanduser().resolve()
        self.callback=callback or (lambda *a,**kw:None)
        self.process=None
        self._reader=None
        self.bootstrapped=False
        self.socks_port=9157
        self.peer_port=None
        self.last_error=''
        self.executable=None

    def find_binary(self, selected=None):
        options = [selected,os.environ.get('CRYPTO_TOR_EXECUTABLE'),
                   str(self.folder/'tor.exe'),str(self.folder/'tor'),
                   shutil.which('tor.exe'),shutil.which('tor')]
        for candidate in options:
            if candidate and Path(candidate).is_file():return Path(candidate).resolve()
        return None

    def set_binary(self, path):
        candidate=self.find_binary(path)
        if not candidate or candidate!=Path(path).resolve():
            raise FileNotFoundError('Choose an existing tor executable from the verified Tor Expert Bundle')
        if candidate.name.lower() not in ('tor','tor.exe'):
            raise ValueError('Selected binary must be named tor or tor.exe')
        self.executable=candidate
        # A matching filename is NOT proof of authenticity; verify Tor's
        # official download signature out-of-band before choosing this path.

    def _notify(self, status, detail=''):
        self.callback({'event':'tor_status','status':status,'detail':detail})

    def start(self, peer_port=None, executable=None, socks_port=9157):
        if self.process and self.process.poll() is None:raise RuntimeError('Tor is already running')
        if executable and not Path(executable).is_file():
            raise FileNotFoundError('Requested Tor daemon path does not exist')
        binary=self.find_binary(executable or self.executable)
        if binary is None:raise FileNotFoundError('Tor daemon not installed: select verified Tor Expert Bundle executable')
        if binary.name.lower() not in ('tor','tor.exe'):
            raise ValueError('Refusing a file that is not named tor or tor.exe')
        if not binary.is_file():raise FileNotFoundError('Tor executable is unavailable')
        socks_port=int(socks_port)
        if socks_port==0:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as candidate:
                candidate.bind(('127.0.0.1',0))
                socks_port=candidate.getsockname()[1]
        if not 1024<=socks_port<=65535:raise ValueError('Invalid SOCKS port')
        if peer_port is not None and not 1024<=int(peer_port)<=65535:raise ValueError('Invalid local peer listener port')
        self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        if os.name!='nt':self.folder.chmod(0o700)
        data=self.folder/'state';data.mkdir(exist_ok=True,mode=0o700)
        if os.name!='nt':data.chmod(0o700)
        hs=self.folder/'onion_service'
        # Torrc is line oriented: a malicious folder name cannot inject options.
        for path in (self.folder,data,hs):
            if any(c in str(path) for c in '\r\n"'):
                raise ValueError('Unsafe characters in Tor configuration directory')
        config=['SocksPort 127.0.0.1:'+str(socks_port)+' IsolateSOCKSAuth','DataDirectory "'+data.as_posix()+'"',
                'Log notice stdout','CookieAuthentication 1', 'ClientOnly 0']
        if peer_port is not None:
            hs.mkdir(exist_ok=True,mode=0o700)
            if os.name!='nt':hs.chmod(0o700)
            config.extend(['HiddenServiceDir "'+hs.as_posix()+'"',
                           'HiddenServicePort '+str(int(peer_port))+' 127.0.0.1:'+str(int(peer_port))])
        torrc=self.folder/'torrc'
        # Avoid following an attacker-created torrc symlink and keep it private.
        flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC
        if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
        if torrc.is_symlink():raise ValueError('Tor configuration must not be a symlink')
        fd=os.open(str(torrc), flags, 0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            output.write('\n'.join(config)+'\n')
            output.flush();os.fsync(output.fileno())
        if os.name!='nt':torrc.chmod(0o600)
        self.bootstrapped=False;self.last_error=''
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        try:
            self.process=subprocess.Popen([str(binary),'-f',str(torrc)],
                           stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
                           bufsize=1,creationflags=flags)
        except OSError as exc:
            raise RuntimeError('Unable to start Tor daemon (check binary and DLLs)') from exc
        self.socks_port=socks_port;self.peer_port=peer_port
        self._reader=threading.Thread(target=self._read_output,args=(self.process,),daemon=True)
        self._reader.start()
        self._notify('STARTING','Tor daemon launching')

    def _read_output(self, process):
        try:
            for line in process.stdout:
                # Never emit raw Tor lines: they may contain local paths or configurations.
                m=re.search(r'Bootstrapped (\d+)%',line)
                if m and self.process is process and process.poll() is None:
                    pct=int(m.group(1))
                    self.bootstrapped=pct==100
                    self._notify('READY' if pct==100 else 'BOOTSTRAPPING',str(pct)+'%')
                if self.process is process and '[err]' in line.lower():
                    self.last_error='Tor daemon reported a startup error'
                    self._notify('ERROR',self.last_error)
        except (OSError,ValueError):pass
        finally:
            if self.process is process:
                self.bootstrapped=False
                self._notify('STOPPED','Tor daemon exited')

    def onion_address(self):
        if self.status()!='READY' or self.peer_port is None:return ''
        path=self.folder/'onion_service'/'hostname'
        try:
            value=path.read_text(encoding='ascii').strip()
            return value if re.fullmatch('[a-z2-7]{56}\\.onion',value) else ''
        except (OSError,UnicodeError):return ''

    def status(self):
        # Snapshot the handle to avoid a concurrent stop() replacing it with None.
        process=self.process
        if process is None:return 'OFF'
        if process.poll() is not None:
            if self.process is process:self.bootstrapped=False
            return 'STOPPED'
        return 'READY' if self.process is process and self.bootstrapped else 'STARTING'

    def stop(self):
        proc=self.process
        self.process=None
        self.bootstrapped=False
        if proc and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait(timeout=3)
        self._notify('OFF','Tor stopped')
