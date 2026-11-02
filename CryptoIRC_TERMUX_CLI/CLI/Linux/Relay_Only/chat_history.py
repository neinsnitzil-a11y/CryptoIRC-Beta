"""Bounded, signed public-channel history for VaultForge mesh.

No DMs, attachments, recovery secrets or passwords are persisted here.
History is available to any authenticated mesh peer who requests the public room.
Relay administrators can read these public room messages at rest. Not E2EE.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import time

MAX_ROOMS = 12
MAX_PER_ROOM = 40
REPLAY_LIMIT = 25
RETENTION_SECONDS = 7 * 24 * 3600

def _valid_record(item, validate):
    if not isinstance(item, dict) or item.get('kind') != 'chat':
        return False
    try:
        _, kind = validate(item, allow_expired=True)
        data = item['data']
        if kind != 'chat' or not isinstance(data.get('room'), str) or not isinstance(data.get('text'), str):
            return False
        from mesh_chat import ROOM, MAX_MESSAGE
        if not ROOM.fullmatch(data['room']) or not 1 <= len(data['text']) <= MAX_MESSAGE:
            return False
        if not 0 <= time.time() - item['time'] <= RETENTION_SECONDS:
            return False
        return True
    except Exception:
        return False

class ChannelHistory:
    def __init__(self, root: Path, validate, load, save, *, all_rooms=False):
        self.root = root
        self.path = root / 'public_channel_history.json'
        self.validate = validate
        self.save = save
        self.all_rooms = all_rooms
        self.rooms = {}
        try:
            state = load(self.path, max_size=550000)
            stored = state.get('rooms', {})
            if isinstance(stored, dict):
                for room, records in list(stored.items())[:MAX_ROOMS]:
                    if not isinstance(room,str) or not isinstance(records,list):
                        continue
                    valid = [r for r in records[-MAX_PER_ROOM:] if _valid_record(r, validate) and r['data']['room'] == room]
                    if valid:
                        self.rooms[room] = valid[-MAX_PER_ROOM:]
        except (ValueError, OSError):
            # Invalid history should not stop wallet/chat startup, but must not be used.
            self.rooms = {}

    def prune(self):
        changed = False
        for room in list(self.rooms):
            values = [r for r in self.rooms[room] if _valid_record(r, self.validate)]
            if len(values) != len(self.rooms[room]):
                changed = True
            if values:
                self.rooms[room] = values
            else:
                self.rooms.pop(room, None)
                changed = True
        if changed:
            self.save(self.path, {'format': 1, 'rooms': self.rooms})

    def entries(self, room, limit=REPLAY_LIMIT):
        return [r for r in self.rooms.get(room, []) if _valid_record(r, self.validate)][-min(REPLAY_LIMIT, max(0, limit)):]

    def append(self, record, *, persist=True):
        if not _valid_record(record, self.validate):
            raise ValueError('Invalid signed public-channel message')
        room = record['data']['room']
        if room not in self.rooms and len(self.rooms) >= MAX_ROOMS:
            # Remove the oldest existing room, not the current message.
            oldest = min(self.rooms, key=lambda name: self.rooms[name][-1]['time'] if self.rooms[name] else 0)
            self.rooms.pop(oldest, None)
        rows = self.rooms.setdefault(room, [])
        ident = (record['origin'], record['id'])
        if any((v['origin'],v['id']) == ident for v in rows):
            return False
        rows.append(record)
        self.rooms[room] = [r for r in rows[-MAX_PER_ROOM:] if _valid_record(r, self.validate)]
        if persist:
            # Ensure stored JSON remains within the secure_load cap even if 12 rooms
            # each contain large signed public messages. Discard oldest first.
            while len(json.dumps({'format': 1, 'rooms': self.rooms})) > 450000:
                candidates = [name for name, values in self.rooms.items() if values]
                if not candidates:
                    break
                first = min(candidates, key=lambda name: self.rooms[name][0]['time'])
                self.rooms[first].pop(0)
                if not self.rooms[first]:
                    self.rooms.pop(first)
            self.save(self.path, {'format': 1, 'rooms': self.rooms})
        return True

    @staticmethod
    def format(record):
        when = datetime.fromtimestamp(record['time'],timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        return f'[{when}] [{record["data"]["room"]}] {record["nick"]}: {record["data"]["text"]}'
