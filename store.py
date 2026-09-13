"""
The in-memory key space, with per-key expiration and basic persistence.

Keys can hold one of: str, list[str], dict[str, str], set[str] -- mirroring
Redis's string / list / hash / set types closely enough for demo purposes.
"""
from __future__ import annotations

import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional


@dataclass
class Entry:
    value: Any
    expire_at: Optional[float] = None  # epoch seconds; None = no expiry

    def is_expired(self) -> bool:
        return self.expire_at is not None and time.time() >= self.expire_at


class Store:
    """Thread-safe key/value store with lazy + active expiration."""

    def __init__(self, snapshot_path: Optional[str] = None):
        self._data: Dict[str, Entry] = {}
        self._lock = RLock()
        self.snapshot_path = Path(snapshot_path) if snapshot_path else None
        if self.snapshot_path and self.snapshot_path.exists():
            self._load()

    # -- internal helpers ------------------------------------------------

    def _get_entry(self, key: str) -> Optional[Entry]:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._data[key]
            return None
        return entry

    # -- generic key operations ------------------------------------------

    def get_raw(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._get_entry(key)
            return entry.value if entry else None

    def set_raw(self, key: str, value: Any, ex: Optional[float] = None) -> None:
        with self._lock:
            expire_at = time.time() + ex if ex is not None else None
            self._data[key] = Entry(value=value, expire_at=expire_at)

    def delete(self, *keys: str) -> int:
        with self._lock:
            removed = 0
            for key in keys:
                if self._get_entry(key) is not None:
                    del self._data[key]
                    removed += 1
            return removed

    def exists(self, *keys: str) -> int:
        with self._lock:
            return sum(1 for k in keys if self._get_entry(k) is not None)

    def expire(self, key: str, seconds: float) -> bool:
        with self._lock:
            entry = self._get_entry(key)
            if entry is None:
                return False
            entry.expire_at = time.time() + seconds
            return True

    def persist(self, key: str) -> bool:
        with self._lock:
            entry = self._get_entry(key)
            if entry is None or entry.expire_at is None:
                return False
            entry.expire_at = None
            return True

    def ttl(self, key: str) -> int:
        """Seconds until expiry, -1 if no expiry, -2 if key doesn't exist."""
        with self._lock:
            entry = self._get_entry(key)
            if entry is None:
                return -2
            if entry.expire_at is None:
                return -1
            remaining = entry.expire_at - time.time()
            return max(0, int(remaining))

    def type_of(self, key: str) -> str:
        with self._lock:
            entry = self._get_entry(key)
            if entry is None:
                return "none"
            return {
                str: "string",
                list: "list",
                dict: "hash",
                set: "set",
            }.get(type(entry.value), "unknown")

    def keys(self, pattern: str = "*") -> list:
        import fnmatch

        with self._lock:
            self._sweep_expired()
            return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

    def dbsize(self) -> int:
        with self._lock:
            self._sweep_expired()
            return len(self._data)

    def flush_all(self) -> None:
        with self._lock:
            self._data.clear()

    def _sweep_expired(self) -> None:
        expired = [k for k, e in self._data.items() if e.is_expired()]
        for k in expired:
            del self._data[k]

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        if not self.snapshot_path:
            return
        with self._lock:
            self._sweep_expired()
            with open(self.snapshot_path, "wb") as f:
                pickle.dump(self._data, f)

    def _load(self) -> None:
        try:
            with open(self.snapshot_path, "rb") as f:
                self._data = pickle.load(f)
        except (EOFError, pickle.PickleError, OSError):
            self._data = {}
