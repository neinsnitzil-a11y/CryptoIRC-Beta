"""Isolated JSON-line IPC worker for the VaultForge wire-compatible P2P mesh.

No imports from wallet, fiat, or transaction packages. No password, identity seed,
or private message crosses a process command line. Text JSON goes via local pipes.
The GUI owns *only* transport metadata and visible chat messages.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
from pathlib import Path
import sys
import traceback

HERE = Path(__file__).resolve().parent
MESH_SRC = HERE / 'vaultmesh'
if str(MESH_SRC) not in sys.path:
    sys.path.insert(0, str(MESH_SRC))
import mesh_chat as mesh
from file_transfer import list_saved_downloads

# Windowed PyInstaller builds set sys.stdout to None even when launched with a
# redirected stdout pipe. Recover the inherited pipe descriptor explicitly.
WIRE = sys.stdout if sys.stdout is not None else os.fdopen(os.dup(1), 'w', buffering=1, encoding='utf-8')
if sys.stdin is None:
    sys.stdin = os.fdopen(os.dup(0), 'r', encoding='utf-8')
sys.stdout = sys.stderr if sys.stderr is not None else open(os.devnull, 'w')  # library print() stays off IPC stdout


def emit(kind, **fields):
    try:
        WIRE.write(json.dumps({'kind': kind, **fields}, ensure_ascii=True, separators=(',', ':')) + '\n')
        WIRE.flush()
    except (OSError, ValueError):
        pass


class Session:
    def __init__(self, root: Path | None = None):
        self.root = mesh.secure_root(root)
        self.node = None
        self.identity = None
        self._active = True

    def log(self, text):
        emit('log', text=str(text)[:1800])

    async def _stop(self):
        if self.node is not None:
            await self.node.stop()
            self.node = None
        self.identity = None
        emit('state', **self.snapshot())

    def snapshot(self):
        if not self.node:
            return {'identity': '', 'connected': False, 'users': [], 'peers': [],
                    'rooms': [], 'room': '#general', 'files': [], 'saved': [], 'nodes': [],
                    'relays': [dict(x, state='DISCONNECTED', active=x['endpoint'] == mesh.load_relay_hosts(self.root)['active'])
                               for x in mesh.load_relay_hosts(self.root)['hosts']],
                    'active_relay': mesh.load_relay_hosts(self.root)['active']}
        node = self.node
        return {
            'identity': f'{node.ident.nick}@{node.ident.keyid}',
            'connected': bool(node.links),
            'relays': node.relay_rows(), 'active_relay': node.relay_hosts['active'],
            'users': [{'nick': n, 'id': k, 'rooms': r} for n,k,r in node.online()],
            'peers': [{'name': link.nick, 'id': link.keyid, 'endpoint': link.endpoint} for link in node.links],
            'rooms': sorted(node.rooms), 'room': node.active_room,
            'files': [{**row, 'status': 'READY' if row['ready'] else 'Receiving'}
                      for row in node.files.offer_rows()],
            'saved': list_saved_downloads(node.root),
            'nodes': [{'nick': n, 'id': k, 'endpoint': a} for n,k,a in node.listed_public()],
            'room_counts': node.visible_rooms(),
        }

    async def execute(self, cmd: dict):
        action = cmd.get('action')
        if action == 'accounts':
            accounts = mesh.secure_load(self.root / 'accounts.json')
            emit('accounts', names=sorted(accounts))
            return
        if action == 'change_password':
            mesh.change_account_password(self.root, str(cmd.get('nick','')),
                                         str(cmd.get('old','')), str(cmd.get('new','')))
            emit('log', text='Chat account password changed; wallet passwords unchanged.')
            return
        if action in ('login', 'register'):
            if self.node is not None:
                raise ValueError('Disconnect before changing chat identities')
            nick, pw = str(cmd.get('nick','')), str(cmd.get('password',''))
            ident = (mesh.create_account if action == 'register' else mesh.login)(self.root, nick, pw)
            host, port = mesh.parse_endpoint(str(cmd.get('listen','127.0.0.1:0')), allow_zero=True)
            offline = bool(cmd.get('offline', False))
            tor = bool(cmd.get('tor', False))
            lan = bool(cmd.get('lan', False))
            node = mesh.MeshNode(ident, self.root, notify=self.log,
                                 offline_only=offline, lan_discovery=lan, tor_mode=tor)
            try:
                await node.start(host, port)
            except BaseException:
                await node.stop()
                raise
            self.identity, self.node = ident, node
            emit('identity', nick=ident.nick, id=ident.keyid, port=node.current_port)
            emit('state', **self.snapshot())
            for entry in node.history.entries(node.active_room,25):
                self.log('[HISTORY] ' + node.history.format(entry))
            # Avoid silently connecting over WAN when the user chose offline mode.
            return
        if action == 'disconnect':
            await self._stop()
            return
        if action == 'scan_public':
            source = str(cmd.get('bootstrap',mesh.DEFAULT_BOOTSTRAP)).strip()
            mesh.parse_endpoint(source)
            results, errors = await mesh.scan_public([source], tor_mode=bool(cmd.get('tor',False)))
            emit('scan_public', rows=[{'nick': a,'id': b,'endpoint': c} for a,b,c in results], errors=errors)
            return
        if action == 'scan_lan':
            peers = await mesh.scan_lan()
            emit('scan_lan', rows=[{'nick': n,'id': k,'endpoint': a} for n,k,a in peers])
            return
        if self.node is None:
            raise ValueError('Register or log in before using the chat network')
        n = self.node
        if action in ('relay_add', 'relay_select', 'relay_remove'):
            endpoint = str(cmd.get('endpoint', '')).strip()
            if action == 'relay_add':
                n.relay_add(endpoint, str(cmd.get('label', '')).strip())
            elif action == 'relay_select':
                n.relay_select(endpoint)
            else:
                n.relay_remove(endpoint)
            emit('state', **self.snapshot())
            return
        if action == 'peer_trust_status':
            endpoint = str(cmd.get('endpoint','')).strip()
            mesh.parse_endpoint(endpoint)
            emit('trust_status', endpoint=endpoint, pinned=str(n.pins.get(endpoint, '')))
            return
        if action == 'replace_peer_trust':
            # Explicit, user-verified key rotation. Never accept a changed identity
            # automatically from an untrusted server error or peer directory.
            endpoint = str(cmd.get('endpoint','')).strip()
            mesh.parse_endpoint(endpoint)
            previous = str(cmd.get('previous_id','')).strip().lower()
            verified = str(cmd.get('verified_id','')).strip().lower()
            current = n.pins.get(endpoint)
            if not re.fullmatch(r'[0-9a-f]{16}',verified):
                raise ValueError('Expected a 16-character hex identity fingerprint verified separately')
            if not current:
                raise ValueError('Endpoint has no existing pin to rotate; use Connect and independently verify first contact')
            if current != previous:
                raise ValueError('Saved trust changed while confirmation was open; review it again')
            if current == verified:
                raise ValueError('New fingerprint is identical to the existing trusted fingerprint')
            if any(link.endpoint == endpoint for link in n.links):
                raise ValueError('Disconnect the current peer link before changing its fingerprint')
            # Keep a separately named, user-owned copy of the original pin registry
            # so this explicit rotation is reversible if the server key was mistaken.
            import secrets
            backup = n.root / ('known_peers.pre-rotation-' + secrets.token_hex(5) + '.json')
            mesh.secure_save(backup, dict(n.pins))
            n.pins[endpoint] = verified
            try:
                mesh.secure_save(n.pins_path, n.pins)
            except BaseException:
                n.pins[endpoint] = current
                raise
            # Stop retrying a changed identity until the user explicitly
            # reconnects.  Keep the saved relay and its separate trust pin.
            n.retry_targets = [p for p in n.retry_targets if p != endpoint]
            n.auto_reconnect = bool(n.retry_targets) and not n.offline_only
            emit('trust_updated', endpoint=endpoint, old_id=current, new_id=verified)
            return
        if action == 'connect':
            endpoint = str(cmd.get('endpoint','')).strip()
            mesh.parse_endpoint(endpoint)
            before_pin=n.pins.get(endpoint)
            n.relay_add(endpoint)
            await n.connect(endpoint)
            expected=str(cmd.get('expected_id','')).strip()
            new_link=next((l for l in n.links if l.endpoint==endpoint),None)
            if expected and (new_link is None or new_link.keyid!=expected):
                if new_link is not None:new_link.close()
                if before_pin is None and new_link is not None and n.pins.get(endpoint)==new_link.keyid:
                    n.pins.pop(endpoint,None)
                    mesh.secure_save(n.pins_path,n.pins)
                raise ValueError('Node fingerprint does not match signed directory listing; connection rejected')
            if not n.offline_only:
                n.remember_retry(endpoint)
            self.log('[CONNECTED] ' + endpoint)
        elif action == 'chat':
            await n.send_chat(str(cmd.get('text','')))
        elif action == 'dm':
            await n.send_dm(str(cmd.get('recipient','')), str(cmd.get('text','')))
        elif action == 'join':
            room = str(cmd.get('room','')).lower()
            if not mesh.ROOM.fullmatch(room) or len(n.rooms) >= 12 and room not in n.rooms:
                raise ValueError('Invalid room or room limit exceeded')
            n.rooms.add(room)
            n.active_room = room
            self.log('[ROOM] Created/joined '+room+'; other users can join with /join '+room)
            await n.announce()
            for entry in n.history.entries(room):
                self.log('[HISTORY] ' + n.history.format(entry))
            await n.request_history(room)
        elif action == 'leave':
            room = str(cmd.get('room','')).lower()
            if room not in n.rooms or len(n.rooms) == 1:
                raise ValueError('Cannot leave the last channel or an unknown channel')
            n.rooms.remove(room)
            if n.active_room == room:
                n.active_room = sorted(n.rooms)[0]
            await n.announce()
        elif action == 'history':
            room = str(cmd.get('room',n.active_room)).lower()
            if room not in n.rooms: raise ValueError('Join this channel first')
            emit('history', room=room, lines=[n.history.format(x) for x in n.history.entries(room,25)])
            await n.request_history(room)
        elif action == 'upload_room':
            room = str(cmd.get('room',n.active_room)).lower()
            src = Path(str(cmd.get('path',''))).expanduser()
            if not src.exists(): raise ValueError('Selected file or folder does not exist')
            n.background_file_send(n.files.send_room(room,str(src)))
        elif action == 'upload':
            recipient = str(cmd.get('recipient',''))
            src = Path(str(cmd.get('path',''))).expanduser()
            if not src.exists(): raise ValueError('Selected file or folder does not exist')
            # FileTransfers validates size, forbidden credential files, safe ZIP and E2E encryption.
            coroutine = n.files.send_folder(recipient,str(src)) if src.is_dir() else n.files.send(recipient,str(src))
            n.background_file_send(coroutine)
        elif action == 'refresh_files':
            n.files.prune()
            emit('state', **self.snapshot())
        elif action == 'accept':
            output = n.files.accept(str(cmd.get('id','')))
            emit('download', path=str(output))
        elif action == 'reject':
            if n.files.pending.pop(str(cmd.get('id','')),None) is None:
                raise ValueError('No such pending offer')
        elif action == 'block':
            n.block(str(cmd.get('id','')))
        elif action == 'refresh_roster':
            if not n.links:
                self.log('[ROSTER] No connected peers; connect to AWS or another host first.')
            else:
                # Reuse the existing, authenticated 'intro' frame rather than
                # adding a new wire type that would disconnect older AWS nodes.
                # Each receiving peer will replay only recently signed presence,
                # never an unverified global user registry.
                await n.announce()
                count = 0
                for link in tuple(n.links):
                    try:
                        await link.send({'type': 'intro', 'nick': n.ident.nick,
                                         'rooms': sorted(n.rooms),
                                         'features': ['public-directory-v1', 'channel-history-v1']})
                        count += 1
                    except (ConnectionError, OSError, asyncio.TimeoutError):
                        link.close()
                self.log(f'[ROSTER] Refresh requested from {count} connected peer(s); '
                         'only reachable, authenticated, recently online users are displayed.')
        elif action == 'status':
            pass
        else:
            raise ValueError('Unknown chat command')
        emit('state', **self.snapshot())

    async def run(self):
        emit('ready', protocol=mesh.PROTOCOL, root=str(self.root))
        async def snapshots():
            while self._active:
                await asyncio.sleep(2)
                if self.node:
                    emit('state', **self.snapshot())
        task = asyncio.create_task(snapshots())
        try:
            while True:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break
                if len(line) > 12000:
                    emit('error', text='Command exceeds maximum size'); continue
                try:
                    cmd = json.loads(line)
                    if not isinstance(cmd, dict): raise ValueError('Invalid command')
                    if cmd.get('action') == 'shutdown': break
                    await self.execute(cmd)
                except mesh.PeerIdentityChanged as exc:
                    emit('peer_identity_changed', endpoint=exc.endpoint, pinned=exc.pinned,
                         presented=exc.presented)
                except (ValueError, TypeError, KeyError, OSError, RuntimeError, ConnectionError,
                        asyncio.TimeoutError) as exc:
                    emit('error', text=f'{type(exc).__name__}: {str(exc)[:350]}')
                except Exception as exc:
                    emit('error', text=f'Internal chat error: {type(exc).__name__}')
        finally:
            self._active = False
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await self._stop()


def main():
    try:
        asyncio.run(Session().run())
    except BaseException as exc:
        emit('error', text=f'Mesh worker stopped: {type(exc).__name__}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
