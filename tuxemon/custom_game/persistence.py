# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned local conversation snapshots, separate from campaign saves."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tuxemon.custom_game.composer import METHODS, ascii_bytes

SCHEMA = "tuxemon.custom-conversations"
VERSION = 1
MAX_BYTES = 2 * 1024 * 1024


def profile_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", value):
        raise ValueError(
            "Profile must be 1-32 lowercase letters, digits, - or _"
        )
    return value


@dataclass(frozen=True)
class NPCMemory:
    draft: str = ""
    method: int = 1
    history: tuple[tuple[str, str], ...] = ()


def decode(
    data: object, profile: str, npc_ids: tuple[str, ...]
) -> dict[str, NPCMemory]:
    if not isinstance(data, dict) or set(data) != {
        "schema",
        "version",
        "profile",
        "npcs",
    }:
        raise ValueError("Invalid conversation document")
    if data["schema"] != SCHEMA or data["profile"] != profile:
        raise ValueError("Conversation profile or scenario does not match")
    if type(data["version"]) is not int or data["version"] != VERSION:
        raise ValueError("Unsupported conversation version")
    records = data["npcs"]
    if not isinstance(records, dict) or set(records) != set(npc_ids):
        raise ValueError("Conversation NPC identities do not match")
    memories = {}
    for key, record in records.items():
        if not isinstance(record, dict) or set(record) != {
            "draft",
            "method",
            "history",
        }:
            raise ValueError("Invalid NPC memory")
        ascii_bytes(record["draft"], 96)
        method = record["method"]
        if type(method) is not int or method not in dict(METHODS):
            raise ValueError("Invalid input method")
        history = record["history"]
        if not isinstance(history, list) or len(history) > 20:
            raise ValueError("Invalid conversation history")
        turns = []
        for pair in history:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("Invalid conversation turn")
            ascii_bytes(pair[0], 96)
            ascii_bytes(pair[1], 8192)
            if not pair[0].strip() or not pair[1].strip():
                raise ValueError("Empty completed conversation turn")
            turns.append(tuple(pair))
        memories[key] = NPCMemory(record["draft"], method, tuple(turns))
    return memories


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate conversation field")
        result[key] = value
    return result


class ConversationStore:
    def __init__(
        self, directory: Path, profile: str, npc_ids: tuple[str, ...]
    ):
        self.profile = profile_name(profile)
        self.npc_ids = npc_ids
        self.path = directory / f"{self.profile}.json"
        self.notice = "Saved locally"
        self.writable = False
        self._lock = None
        self._last = None
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(
                self.path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600
            )
            self._lock = os.fdopen(descriptor, "a+b")
            if os.name == "nt":
                import msvcrt

                self._lock.seek(0)
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.writable = True
        except (OSError, ImportError):
            self.close()
            self.notice = (
                "Saving disabled: profile busy or storage unavailable"
            )

    def load(self) -> dict[str, NPCMemory]:
        empty = {key: NPCMemory() for key in self.npc_ids}
        if not self.writable:
            return empty
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Conversation file is too large")
            memories = decode(
                json.loads(raw, object_pairs_hook=unique_fields),
                self.profile,
                self.npc_ids,
            )
            self._last = raw
            return memories
        except FileNotFoundError:
            return empty
        except (OSError, ValueError, RecursionError):
            self.writable = False
            self.notice = (
                "Saving disabled: unreadable or unsupported save retained"
            )
            return empty

    def save(self, memories: dict[str, NPCMemory]) -> bool:
        if not self.writable:
            return False
        data = {
            "schema": SCHEMA,
            "version": VERSION,
            "profile": self.profile,
            "npcs": {
                key: {
                    "draft": value.draft,
                    "method": value.method,
                    "history": [list(turn) for turn in value.history],
                }
                for key, value in memories.items()
            },
        }
        decode(data, self.profile, self.npc_ids)
        raw = (
            json.dumps(data, ensure_ascii=True, sort_keys=True) + "\n"
        ).encode()
        if len(raw) > MAX_BYTES:
            raise ValueError("Conversation snapshot is too large")
        if raw == self._last:
            return True
        temporary = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=f".{self.profile}-", suffix=".tmp", dir=self.path.parent
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            self._last = raw
            return True
        except OSError:
            self.writable = False
            self.notice = "Saving disabled: storage write failed"
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def close(self):
        self.writable = False
        if self._lock is not None:
            self._lock.close()
            self._lock = None
