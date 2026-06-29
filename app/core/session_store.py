"""
Session store — maps session_id → InterviewState.

Backend selection (via REDIS_URL env var):
  REDIS_URL set   → RedisSessionStore  (production, multi-process safe)
  REDIS_URL empty → MemorySessionStore (local dev, single-process)

Completed sessions (interview_complete=True) are always persisted to
./data/sessions/ as JSON for the history/report endpoints.
"""
from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from loguru import logger

from app.core.state import InterviewState

_SESSIONS_DIR = Path("./data/sessions")


# ── Serialization ─────────────────────────────────────────────────────────────

def _serialize(state: InterviewState) -> dict:
    import copy
    data = copy.deepcopy(dict(state))
    msgs = []
    for m in data.get("messages", []):
        mtype = type(m).__name__
        content = getattr(m, "content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        msgs.append({"type": mtype, "content": str(content)})
    data["messages"] = msgs
    return data


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _session_path(session_id: str) -> Path:
    return _SESSIONS_DIR / f"{session_id}.json"


async def _persist_completed(session_id: str, state: InterviewState) -> None:
    """Persist completed interview to disk (for history/report endpoints)."""
    path = _session_path(session_id)
    try:
        data = _serialize(state)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write_json, path, data)
        logger.info(f"Session {session_id} persisted to {path}")
    except Exception as e:
        logger.warning(f"Failed to persist session {session_id}: {e}")


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseSessionStore(ABC):
    @abstractmethod
    async def set(self, session_id: str, state: InterviewState) -> None: ...
    @abstractmethod
    async def get(self, session_id: str) -> Optional[InterviewState]: ...
    @abstractmethod
    async def delete(self, session_id: str) -> None: ...
    @abstractmethod
    async def exists(self, session_id: str) -> bool: ...


# ── In-memory backend ─────────────────────────────────────────────────────────

class MemorySessionStore(BaseSessionStore):
    def __init__(self):
        self._store: dict[str, InterviewState] = {}
        self._lock = asyncio.Lock()
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_completed_from_disk()

    def _load_completed_from_disk(self) -> None:
        loaded = 0
        for p in _SESSIONS_DIR.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._store[p.stem] = data  # type: ignore[assignment]
                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load session {p.name}: {e}")
        if loaded:
            logger.info(f"Restored {loaded} completed session(s) from disk")

    async def set(self, session_id: str, state: InterviewState) -> None:
        async with self._lock:
            self._store[session_id] = state
        if state.get("interview_complete"):
            await _persist_completed(session_id, state)

    async def get(self, session_id: str) -> Optional[InterviewState]:
        async with self._lock:
            return self._store.get(session_id)

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._store.pop(session_id, None)

    async def exists(self, session_id: str) -> bool:
        async with self._lock:
            return session_id in self._store


# ── Redis backend ─────────────────────────────────────────────────────────────

class RedisSessionStore(BaseSessionStore):
    """
    Stores active interview states in Redis as JSON strings.
    TTL = session_ttl_seconds (default 2h) — expired sessions auto-cleaned.
    Completed sessions are also persisted to disk for the history endpoint.
    """

    def __init__(self, redis_url: str, ttl: int):
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"RedisSessionStore initialized: {redis_url}, TTL={ttl}s")

    def _key(self, session_id: str) -> str:
        return f"interview:session:{session_id}"

    def _encode(self, state: InterviewState) -> str:
        data = _serialize(state)
        return json.dumps(data, ensure_ascii=False)

    def _decode(self, raw: str) -> InterviewState:
        return json.loads(raw)  # type: ignore[return-value]

    async def set(self, session_id: str, state: InterviewState) -> None:
        await self._redis.setex(self._key(session_id), self._ttl, self._encode(state))
        if state.get("interview_complete"):
            await _persist_completed(session_id, state)

    async def get(self, session_id: str) -> Optional[InterviewState]:
        raw = await self._redis.get(self._key(session_id))
        return self._decode(raw) if raw else None

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def exists(self, session_id: str) -> bool:
        return bool(await self._redis.exists(self._key(session_id)))


# ── Factory ───────────────────────────────────────────────────────────────────

def _create_store() -> BaseSessionStore:
    from app.config import get_settings
    settings = get_settings()
    if settings.redis_url:
        logger.info("Session backend: Redis")
        return RedisSessionStore(settings.redis_url, settings.session_ttl_seconds)
    else:
        logger.info("Session backend: in-memory (set REDIS_URL to use Redis)")
        return MemorySessionStore()


_store: Optional[BaseSessionStore] = None


def get_session_store() -> BaseSessionStore:
    global _store
    if _store is None:
        _store = _create_store()
    return _store
