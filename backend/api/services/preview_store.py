from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
from uuid import UUID, uuid4

from backend.models.canonical_intent import CanonicalIntent


class PreviewNotFoundError(KeyError):
    pass


class PreviewStore:
    def __init__(self, ttl: timedelta = timedelta(minutes=10), capacity: int = 1000):
        self._ttl = ttl
        self._capacity = capacity
        self._lock = threading.Lock()
        self._items: dict[UUID, tuple[datetime, CanonicalIntent, bool]] = {}

    def save(self, intent: CanonicalIntent, eligible: bool) -> UUID:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._remove_expired(now)
            if len(self._items) >= self._capacity:
                oldest_id = min(self._items, key=lambda preview_id: self._items[preview_id][0])
                del self._items[oldest_id]
            preview_id = uuid4()
            self._items[preview_id] = (now + self._ttl, intent, eligible)
            return preview_id

    def consume(self, preview_id: UUID) -> tuple[CanonicalIntent, bool]:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._remove_expired(now)
            value = self._items.pop(preview_id, None)
            if value is None:
                raise PreviewNotFoundError(preview_id)
            return value[1], value[2]

    def get(self, preview_id: UUID) -> tuple[CanonicalIntent, bool]:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._remove_expired(now)
            value = self._items.get(preview_id)
            if value is None:
                raise PreviewNotFoundError(preview_id)
            return value[1], value[2]

    def _remove_expired(self, now: datetime) -> None:
        expired = [
            preview_id
            for preview_id, (expires_at, _, _) in self._items.items()
            if expires_at <= now
        ]
        for preview_id in expired:
            del self._items[preview_id]
