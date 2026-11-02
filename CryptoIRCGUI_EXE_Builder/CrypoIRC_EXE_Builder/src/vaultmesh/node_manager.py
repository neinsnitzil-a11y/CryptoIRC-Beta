#!/usr/bin/env python3
"""User-owned persistent VaultForge mesh node: setup/start/stop/status/autostart.

Node identity is separate from wallet identity. Experimental custom protocol.
"""
from __future__ import annotations
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # -I mode removes the script directory
PY = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def storage():
    from mesh_chat import secure_root
    return secure_root()


def private_write(path: Path, content: str) -> None:
    if path.is_symlink():
        raise ValueError('Refusing symlinked node configuration')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name('.node-' + secrets.token_hex(8))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if os.name != 'nt':
            os.chmod(path, 0o600)
    finally:
        tmp.unlink(missing_ok=True)


def load_config():
    path = storage() / 'node.json'
    if not path.is_file() or path.is_symlink():
        raise ValueError('Node not configured. Run node_manager.py setup first.')
    obj = json.loads(path.read_text())
    from mesh_chat import parse_endpoint, NAME, is_lan_host, public_endpoint
    if not isinstance(obj, dict) or obj.get('mode') not in ('wan', 'lan', 'tor') or not NAME.fullmatch(obj.get('account', '')):
        raise ValueError('Invalid node configuration')
    host, port = parse_endpoint(obj.get('listen', ''))
    if obj['mode'] == 'tor' and host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Tor node must listen on localhost (expose through an onion service)')
    if obj['mode'] == 'lan' and not is_lan_host('127.0.0.1'):
        raise ValueError('Bad LAN settings')
    if not isinstance(obj.get('peers'), list) or len(obj['peers']) > 12:
        raise ValueError('Invalid upstream peers')
    for target in obj['peers']:
        peer_host, _ = parse_endpoint(target)
        if obj['mode'] == 'lan' and not is_lan_host(peer_host):
            raise ValueError('LAN mode cannot add public peers')
    advertised = obj.get('advertise', '')
    if advertised:
        if obj['mode'] != 'wan':
            raise ValueError('Only WAN nodes may publish a public endpoint')
        public_endpoint(advertised)
    secret = storage() / 'node.secret'
    if not secret.is_file() or secret.is_symlink():
        raise ValueError('Node password file missing')
    if os.name != 'nt' and (secret.stat().st_mode & 0o077):
        raise ValueError('Node secret must be owner-readable only (chmod 600)')
    return obj


def launch_args(obj):
    args = ([sys.executable, '--mesh-cli'] if getattr(sys, 'frozen', False) else
            [str(PY if PY.is_file() else sys.executable), '-I', str(ROOT / 'mesh_chat.py')]) + [
            '--root', str(storage()), '--node-account', obj['account'],
            '--password-file', str(storage() / 'node.secret'),
            '--listen', obj['listen'], '--relay', '--assume-listen']
    if obj['mode'] == 'lan':
        args += ['--offline', '--lan', '--no-auto-connect']
    if obj['mode'] == 'tor':
        args += ['--tor']
    for peer in obj['peers']:
        args += ['--peer', peer]
    if obj.get('advertise'):
        args += ['--advertise', obj['advertise']]
    return args


def configure(opts):
    from mesh_chat import NAME, parse_endpoint, is_lan_host, create_account
    folder = storage()
    cfg_path = folder / 'node.json'
    if cfg_path.exists() or (folder / 'node.secret').exists():
        raise ValueError('Existing node configuration detected; refusing to overwrite node identity. Use start/status.')
    mode = opts.mode
    account = opts.name
    advertise = getattr(opts, 'advertise', '') or ''
    if advertise:
        if mode != 'wan':
            raise ValueError('Public advertisements require WAN mode')
        from mesh_chat import public_endpoint
        advertise = public_endpoint(advertise)
    if not NAME.fullmatch(account):
        raise ValueError('Node account must be 3-24 letters/digits/hyphens/underscores')
    listen = opts.listen or {'wan': '0.0.0.0:6667', 'lan': '0.0.0.0:7777', 'tor': '127.0.0.1:7777'}[mode]
    host, _ = parse_endpoint(listen)
    if mode == 'tor' and host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Tor-only listener must bind to localhost')
    if mode == 'wan' and not opts.yes:
        if input('This exposes an unaudited network service. Type EXPOSE RELAY: ').strip() != 'EXPOSE RELAY':
            print('Canceled')
            return
    peers = opts.peer or []
    for endpoint in peers:
        peer_host, _ = parse_endpoint(endpoint)
        if mode == 'lan' and not is_lan_host(peer_host):
            raise ValueError('LAN node cannot connect to public or DNS endpoints')
    password = secrets.token_urlsafe(36)
    create_account(folder, account, password)
    private_write(folder / 'node.secret', password + '\n')
    private_write(cfg_path, json.dumps({'mode': mode, 'listen': listen,
                                        'account': account, 'peers': peers,
                                        'advertise': advertise}, indent=2) + '\n')
    print(f'[SETUP] Node {account} configured in {mode.upper()} mode on {listen}.')
    print('[SECURITY] Separate randomly generated chat password stored in node.secret (local 0600).')
    print('[SECURITY] Server compromise compromises this node identity; NEVER upload wallet vaults.')
    if advertise:
        print(f'[DISCOVERABLE] Public node advertising {advertise}. Confirm inbound firewall and public IP.')
    if mode == 'tor':
        print('[TOR] Configure a Tor onion service mapping port 7777 to 127.0.0.1:7777; requires a Tor SOCKS5 listener on port 9050/9150 for outbound peers.')


def set_advertise(endpoint: str) -> None:
    """Update only public-node directory announcement while preserving identity."""
    from mesh_chat import public_endpoint
    cfg = load_config()
    if cfg['mode'] != 'wan':
        raise ValueError('Only a WAN node can be listed in the public mesh directory')
    cfg['advertise'] = public_endpoint(endpoint)
    private_write(storage() / 'node.json', json.dumps(cfg, indent=2) + '\n')
    print(f'[DIRECTORY] Public endpoint set to {cfg["advertise"]}; restart the node service.')


def read_pid():
    path = storage() / 'node.pid'
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def is_running(pid):
    if not pid or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    if os.name != 'nt':
        try:
            cmdline = Path(f'/proc/{pid}/cmdline').read_bytes()
            return (b'mesh_chat.py' in cmdline or b'--mesh-cli' in cmdline) and (str(ROOT).encode() in cmdline or b'--root' in cmdline)
        except OSError:
            return False
    return True


def start():
    obj = load_config()
    if is_running(read_pid()):
        print(f'[ALREADY RUNNING] Node PID {read_pid()}')
        return
    log = storage() / 'node.log'
    fd = os.open(log, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    if os.name != 'nt':os.chmod(log,0o600)
    with os.fdopen(fd,'ab') as out:
        opts = {'stdin': subprocess.DEVNULL, 'stdout': out, 'stderr': subprocess.STDOUT, 'cwd': ROOT}
        if os.name == 'nt':
            opts['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            opts['start_new_session'] = True
        child = subprocess.Popen(launch_args(obj), **opts)
    time.sleep(1.2)
    if child.poll() is not None:
        raise RuntimeError(f'Node exited immediately (code {child.returncode}); read {log}')
    private_write(storage() / 'node.pid', str(child.pid))
    print(f'[STARTED] Background node PID {child.pid}, {obj["mode"].upper()} {obj["listen"]}. Log: {log}')
    print('Use node_manager.py status / stop. A background process alone does not auto-start after reboot.')


def stop():
    pid = read_pid()
    if not is_running(pid):
        print('[STOPPED] No owned background node running')
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], check=True)
    else:
        os.kill(pid, signal.SIGTERM)
    (storage() / 'node.pid').unlink(missing_ok=True)
    print(f'[STOPPED] Node PID {pid}')


def status():
    obj = load_config()
    pid = read_pid()
    print(f'[NODE] {obj["account"]}  mode={obj["mode"]}  listen={obj["listen"]}')
    print(f'[PROCESS] {"RUNNING" if is_running(pid) else "NOT RUNNING (or service-managed)"}  pid={pid or "none"}')
    print(f'[LOG] {storage() / "node.log"}')
    print('[NOTE] For systemd service status: systemctl status vaultforge-mesh; for user service: systemctl --user status vaultforge-mesh')


def run():
    obj = load_config()
    cmd = launch_args(obj)
    if os.name == 'nt':
        raise RuntimeError('Run Windows background nodes with start or autostart')
    os.execv(cmd[0], cmd)


def systemd_unit():
    if os.name == 'nt':
        raise ValueError('systemd unavailable on Windows')
    import shlex
    obj = load_config()
    def sd(s):
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    command = (sd(sys.executable) + ' --mesh-node run') if getattr(sys,'frozen',False) else (sd(PY if PY.is_file() else sys.executable) + ' -I ' + sd(ROOT / 'node_manager.py') + ' run')
    return f'''[Unit]
Description=VaultForge Encrypted Mesh Relay ({obj['mode']})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={getpass.getuser()}
ExecStart={command}
Restart=always
RestartSec=5
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
'''


def autostart():
    load_config()
    if os.name == 'nt':
        folder = Path(os.environ.get('APPDATA', str(Path.home()))) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / 'VaultForgeMeshNode.bat'
        # Startup entry only for the signed-in user (not reboot service without login).
        command = f'"{sys.executable}" --mesh-node start' if getattr(sys,"frozen",False) else f'"{PY if PY.is_file() else sys.executable}" -I "{ROOT / "node_manager.py"}" start'
        private_write(file, f'@echo off\r\n{command}\r\n')
        print(f'[AUTOSTART] Windows login startup entry: {file}')
    else:
        unit_dir = Path.home() / '.config' / 'systemd' / 'user'
        unit_dir.mkdir(parents=True, exist_ok=True)
        path = unit_dir / 'vaultforge-mesh.service'
        content = systemd_unit().replace('User=' + getpass.getuser() + '\n', '').replace('WantedBy=multi-user.target', 'WantedBy=default.target')
        private_write(path, content)
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', '--now', 'vaultforge-mesh.service'], check=True)
        print('[AUTOSTART] Enabled systemd USER service. To survive reboot without login, ask an admin to enable lingering:')
        print(f'  sudo loginctl enable-linger {getpass.getuser()}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='VaultForge setup node, background hosting, autostart and status')
    actions = parser.add_subparsers(dest='action', required=True)
    setup = actions.add_parser('setup', help='create separate non-wallet mesh node account')
    setup.add_argument('--mode', choices=['wan', 'lan', 'tor'], default='lan')
    setup.add_argument('--name', default='VaultRelay')
    setup.add_argument('--listen', default='')
    setup.add_argument('--peer', action='append', default=[])
    setup.add_argument('--advertise', default='', help='explicit opt-in public node listing PUBLIC_IP:PORT')
    setup.add_argument('--yes', action='store_true', help='acknowledge public listener exposure')
    publish = actions.add_parser('publish', help='opt in an already configured WAN node to public discovery')
    publish.add_argument('endpoint', help='globally routable IP:PORT')
    for a in ('start', 'stop', 'status', 'run', 'autostart', 'service-file'):
        actions.add_parser(a)
    opt = parser.parse_args(argv)
    try:
        if opt.action == 'setup': configure(opt)
        elif opt.action == 'publish': set_advertise(opt.endpoint)
        elif opt.action == 'start': start()
        elif opt.action == 'stop': stop()
        elif opt.action == 'status': status()
        elif opt.action == 'run': run()
        elif opt.action == 'autostart': autostart()
        elif opt.action == 'service-file': sys.stdout.write(systemd_unit())
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'[NODE ERROR] {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
