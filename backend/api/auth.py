from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time


SESSION_TTL_SECONDS = 8 * 60 * 60


class APIAccessControl:
    def __init__(self, api_token: str | None) -> None:
        self._api_token = api_token
        self._sessions: dict[str, float] = {}
        self._lock = threading.Lock()

    def validate_configuration(self) -> None:
        if self._api_token is None or len(self._api_token.encode("utf-8")) < 32:
            raise RuntimeError(
                "INTENTFLOW_API_TOKEN must contain at least 32 bytes of "
                "high-entropy secret material."
            )

    def accepts_api_token(self, candidate: str | None) -> bool:
        if not self._api_token or candidate is None:
            return False
        return hmac.compare_digest(
            self._api_token.encode("utf-8"),
            candidate.encode("utf-8"),
        )

    def create_session(self) -> str:
        session_id = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._remove_expired_sessions(now)
            self._sessions[self._session_key(session_id)] = (
                now + SESSION_TTL_SECONDS
            )
        return session_id

    def accepts_session(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        key = self._session_key(session_id)
        now = time.monotonic()
        with self._lock:
            expires_at = self._sessions.get(key)
            if expires_at is None:
                return False
            if expires_at <= now:
                del self._sessions[key]
                return False
            return True

    def revoke_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(self._session_key(session_id), None)

    @staticmethod
    def _session_key(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    def _remove_expired_sessions(self, now: float) -> None:
        expired = [
            session_id
            for session_id, expires_at in self._sessions.items()
            if expires_at <= now
        ]
        for session_id in expired:
            del self._sessions[session_id]
