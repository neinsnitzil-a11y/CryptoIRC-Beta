"""Bounded encrypted peer-to-peer attachments for VaultForge Mesh.

Per-recipient X25519 + HKDF + AES-GCM, with signed end-to-end chunks carried
through the mesh gossip layer. No central storage, no remote execution.
Not independently audited. Limited to 4 MiB and 4 inbound transfers per node.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAX_FILE_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 8192
MAX_TRANSFERS = 4
TRANSFER_TIMEOUT = 1800
ID_RE = re.compile(r'^[0-9a-f]{24}$')


def safe_filename(value: str) -> str:
    value = Path(value.replace('\\', '/')).name
    name = re.sub(r'[^A-Za-z0-9._-]', '_', value).lstrip('.')[:120]
    if not name or name in ('.', '..'):
        raise ValueError('Invalid attachment filename')
    return name


def decode(value: str, limit: int) -> bytes:
    if not isinstance(value, str) or len(value) > (limit + 32) * 4 // 3 + 12:
        raise ValueError('Invalid encoded attachment')
    raw = base64.b64decode(value, validate=True)
    if len(raw) > limit:
        raise ValueError('Oversized attachment part')
    return raw


def encoded(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def key_from_shared(shared: bytes, sender: bytes, eph: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=hashlib.sha256(sender + eph).digest(),
                info=b'vaultforge-file-v1').derive(shared)


def aad(sender: bytes, recipient: str, file_id: str, seq: int) -> bytes:
    return b'vf-file-v1|' + sender + recipient.encode('ascii') + file_id.encode('ascii') + seq.to_bytes(4, 'big')


def list_saved_downloads(root: Path, limit: int = 80) -> list[dict]:
    """List only regular files within the private downloads directory.

    Never follow links out of the user's downloads folder. Does not read contents.
    """
    directory = Path(root) / 'downloads'
    if directory.is_symlink() or not directory.is_dir():
        return []
    result = []
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        if path.parent != directory:
            continue
        try:
            stat = path.stat()
        except OSError:  # Files may be deleted while a live inbox is refreshing.
            continue
        result.append({'name': path.name, 'path': str(path),
                       'size': stat.st_size, 'modified': stat.st_mtime})
    return sorted(result, key=lambda row: (-row['modified'], row['name']))[:limit]


class FileTransfers:
    def __init__(self, node):
        self.node = node
        self.pending: dict[str, dict] = {}

    def prune(self):
        now = time.monotonic()
        for tid, transfer in list(self.pending.items()):
            if now - transfer['when'] > TRANSFER_TIMEOUT:
                del self.pending[tid]

    def offer_rows(self) -> list[dict]:
        """Snapshot of incoming offers, ordered for CLI numeric selection.

        No untrusted attachment bytes or session keys leave the receiving process.
        """
        self.prune()
        return [{'id': file_id, 'name': tx['name'], 'sender': tx['sender'],
                 'size': tx['size'], 'ready': 'content' in tx}
                for file_id, tx in sorted(self.pending.items(),
                                          key=lambda pair: (pair[1]['when'], pair[0]))]

    def resolve_offer(self, reference: str) -> str:
        """Use an exact transfer ID or its 1-based position in the current inbox."""
        self.prune()
        if reference in self.pending:
            return reference
        if isinstance(reference, str) and reference.isdecimal():
            rows = self.offer_rows()
            index = int(reference)
            if 1 <= index <= len(rows):
                return rows[index - 1]['id']
        raise ValueError('No matching incoming offer; run /files to refresh the list')

    def target_id(self, target: str) -> str:
        node = self.node
        matches = [key for key, nick in node.names.items()
                   if (key == target or f'{nick}@{key}' == target or nick.lower() == target.lower())
                   and key != node.ident.keyid and key in node.boxkeys and key not in node.blocked
                   and key in node.presence and node.presence[key]['online']
                   and time.monotonic() - node.presence[key]['last_seen'] < 40]
        if len(matches) != 1:
            raise ValueError('Recipient offline or ambiguous; use nickname@ID from /users')
        return matches[0]

    async def send(self, target: str, source: str):
        node = self.node
        path = Path(source).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError('Attachment must be an existing regular non-symlink file')
        size = path.stat().st_size
        if not 1 <= size <= MAX_FILE_BYTES:
            raise ValueError('Attachment must be 1 byte to 4 MiB; large files not supported yet')
        to_id = self.target_id(target)
        eph_priv = x25519.X25519PrivateKey.generate()
        from mesh_chat import raw_pub, sign_message
        eph = raw_pub(eph_priv.public_key())
        key = key_from_shared(eph_priv.exchange(x25519.X25519PublicKey.from_public_bytes(node.boxkeys[to_id])), node.ident.pub, eph)
        aes = AESGCM(key)
        file_id = secrets.token_hex(12)
        # Read/verify only a bounded file. Check for replacement between stat and read.
        content = path.read_bytes()
        if len(content) != size:
            raise ValueError('Attachment changed during preparation')
        total = math.ceil(size / CHUNK_BYTES)
        meta = {'name': safe_filename(path.name), 'size': size, 'sha256': hashlib.sha256(content).hexdigest(), 'total': total}
        ciphertext = aes.encrypt((0).to_bytes(12, 'big'), json.dumps(meta, separators=(',', ':')).encode(), aad(node.ident.pub, to_id, file_id, 0))
        await node._gossip(sign_message(node.ident, 'file_start', {
            'to': to_id, 'id': file_id, 'eph': encoded(eph), 'blob': encoded(ciphertext)}))
        for i in range(total):
            offset = i * CHUNK_BYTES
            cipher = aes.encrypt((i + 1).to_bytes(12, 'big'), content[offset:offset + CHUNK_BYTES],
                                 aad(node.ident.pub, to_id, file_id, i + 1))
            await node._gossip(sign_message(node.ident, 'file_chunk', {
                'to': to_id, 'id': file_id, 'seq': i + 1, 'blob': encoded(cipher)}))
            # Existing relay limit is 80 frames in 10 seconds; pace below it.
            await asyncio.sleep(0.17)
        node.notify(f'[SENT] {meta["name"]} ({size} bytes) offered to {target}; receiving user must /accept {file_id}. Delivery not acknowledged.')

    async def send_room(self, room: str, source: str):
        """Opt-in per-recipient E2E attachment offers, NOT a plaintext relay upload.

        Room names are not cryptographic identities: every online room member
        gets their own independently encrypted offer. Do not claim delivery to
        users who are offline, undiscovered, or joined after this snapshot.
        """
        recipients = self.node.online_room_recipients(room)
        if not recipients:
            raise ValueError('No other ONLINE reachable members of this channel. Connect first or choose a user.')
        if len(recipients) > 8:
            raise ValueError('Room transfer limited to 8 current recipients; choose specific peers for larger rooms')
        selected = Path(source).expanduser()
        # Preflight recipients and file validity before sending the first offer.
        for uid in recipients:
            self.target_id(uid)
        if selected.is_symlink() or not selected.exists():
            raise ValueError('Attachment must exist and must not be a symlink')
        if selected.is_file():
            if not 1 <= selected.stat().st_size <= MAX_FILE_BYTES:
                raise ValueError('File must be 1 byte to 4 MiB')
        elif not selected.is_dir():
            raise ValueError('Only files and folders can be shared')
        self.node.notify(f'[ROOM FILE] Offering encrypted attachment to {len(recipients)} currently online members of {room}; each must accept.')
        for uid in recipients:
            if selected.is_dir():
                await self.send_folder(uid, str(selected))
            else:
                await self.send(uid, str(selected))
        self.node.notify(f'[ROOM FILE] Finished offering to {len(recipients)} peer(s); delivery/acceptance not guaranteed.')

    def receive(self, item: dict, kind: str, user_id: str):
        self.prune()
        node = self.node
        data = item['data']
        if data.get('to') != node.ident.keyid:
            return
        file_id = data.get('id')
        if not isinstance(file_id, str) or not ID_RE.fullmatch(file_id):
            raise ValueError('Invalid file transfer ID')
        sender_pub = decode(item['origin'], 32)
        if len(sender_pub) != 32:
            raise ValueError('Invalid sender key')
        if kind == 'file_start':
            if file_id in self.pending or len(self.pending) >= MAX_TRANSFERS:
                return
            eph = decode(data.get('eph'), 32)
            if len(eph) != 32:
                raise ValueError('Invalid ephemeral file key')
            key = key_from_shared(node.ident.exchange.exchange(x25519.X25519PublicKey.from_public_bytes(eph)), sender_pub, eph)
            raw = AESGCM(key).decrypt((0).to_bytes(12, 'big'), decode(data.get('blob'), 4096),
                                      aad(sender_pub, node.ident.keyid, file_id, 0))
            metadata = json.loads(raw)
            name = metadata.get('name')
            size = metadata.get('size')
            total = metadata.get('total')
            digest = metadata.get('sha256')
            if not isinstance(name, str) or safe_filename(name) != name or \
               type(size) is not int or not 1 <= size <= MAX_FILE_BYTES or \
               type(total) is not int or total != math.ceil(size / CHUNK_BYTES) or \
               not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('Invalid attachment metadata')
            self.pending[file_id] = {'when': time.monotonic(), 'sender': user_id,
                                     'sender_pub': sender_pub, 'aes': AESGCM(key),
                                     'name': name, 'size': size, 'total': total,
                                     'sha256': digest, 'chunks': {}}
            node.notify(f'[FILE OFFER] {item["nick"]}@{user_id} sending encrypted {name} ({size} bytes), id {file_id}. Only save with /accept {file_id} after complete.')
            return
        transfer = self.pending.get(file_id)
        if not transfer or transfer['sender'] != user_id:
            return
        seq = data.get('seq')
        if type(seq) is not int or not 1 <= seq <= transfer['total']:
            raise ValueError('Bad attachment chunk number')
        if seq in transfer['chunks']:
            return
        part = transfer['aes'].decrypt(seq.to_bytes(12, 'big'), decode(data.get('blob'), CHUNK_BYTES + 32),
                                       aad(sender_pub, node.ident.keyid, file_id, seq))
        if not 1 <= len(part) <= CHUNK_BYTES:
            raise ValueError('Invalid attachment chunk')
        transfer['chunks'][seq] = part
        if len(transfer['chunks']) == transfer['total']:
            content = b''.join(transfer['chunks'][n] for n in range(1, transfer['total'] + 1))
            if len(content) != transfer['size'] or hashlib.sha256(content).hexdigest() != transfer['sha256']:
                del self.pending[file_id]
                raise ValueError('Attachment size or integrity failed')
            transfer['content'] = content
            transfer['chunks'].clear()
            node.notify(f'[FILE READY] {transfer["name"]} ({transfer["size"]} bytes), from {user_id}. /accept {file_id} or /reject {file_id}. Never open untrusted files.')


    async def send_folder(self, target: str, directory: str):
        """Send a bounded, safe ZIP snapshot of a directory. Receiver does not auto-extract."""
        import tempfile
        import zipfile
        folder = Path(directory).expanduser()
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Folder must be a real directory (not a symlink)')
        paths = []
        uncompressed = 0
        root = folder.resolve()
        for current, dirs, files in os.walk(folder, followlinks=False):
            here = Path(current)
            for d in dirs:
                if (here / d).is_symlink():
                    raise ValueError('Folder contains a symlink; refusing to package')
            for name in files:
                path = here / name
                if path.is_symlink() or not path.is_file():
                    raise ValueError('Folder contains symlink/special file; refusing to package')
                if name.lower() in ('.env', 'node.secret', 'accounts.json') or path.suffix.lower() in ('.vault', '.pem', '.key'):
                    raise ValueError(f'Folder includes sensitive credentials/wallet file: {name}')
                uncompressed += path.stat().st_size
                if uncompressed > 8 * 1024 * 1024 or len(paths) >= 100:
                    raise ValueError('Folder exceeds 8 MiB uncompressed or 100 files')
                paths.append(path)
        if not paths:
            raise ValueError('Folder has no regular files')
        with tempfile.TemporaryDirectory(prefix='vf_share_') as temp:
            dest = Path(temp) / (safe_filename(folder.name) + '.zip')
            with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                for file in sorted(paths):
                    arcname = str(Path(safe_filename(folder.name)) / file.relative_to(folder))
                    z.write(file, arcname=arcname)
            if dest.stat().st_size > MAX_FILE_BYTES:
                raise ValueError('Compressed folder exceeds 4 MiB encrypted transfer limit')
            await self.send(target, str(dest))
        self.node.notify('[FOLDER] ZIP offered for encrypted transfer. Recipient must /accept it; no automatic extraction.')

    def accept(self, file_id: str) -> Path:
        transfer = self.pending.get(file_id)
        if not transfer or 'content' not in transfer:
            raise ValueError('Unknown or incomplete transfer; check /files')
        folder = self.node.root / 'downloads'
        if folder.is_symlink():
            raise ValueError('Refusing symlinked downloads folder')
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != 'nt':
            os.chmod(folder, 0o700)
        for n in range(100):
            fname = transfer['name'] if n == 0 else f'{n}_{transfer["name"]}'
            dest = folder / fname
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(dest, flags, 0o600)
                break
            except FileExistsError:
                continue
        else:
            raise ValueError('Too many files with this name')
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(transfer['content'])
                out.flush()
                os.fsync(out.fileno())
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        del self.pending[file_id]
        return dest
