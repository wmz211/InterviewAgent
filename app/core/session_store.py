"""
In-memory session store — maps session_id → InterviewState.
Completed sessions (interview_complete=True) are persisted to disk under
./data/sessions/ so they survive server restarts.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from loguru import logger

from app.core.state import InterviewState

_SESSIONS_DIR = Path("./data/sessions")


def _session_path(session_id: str) -> Path:
    return _SESSIONS_DIR / f"{session_id}.json"


def _serialize(state: InterviewState) -> dict:
    """Convert state to a JSON-serializable dict (messages use their text content)."""
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


class SessionStore:
    def __init__(self):
        self._store: dict[str, InterviewState] = {}
        self._lock = asyncio.Lock()
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_completed_from_disk()

    def _load_completed_from_disk(self) -> None:
        """Restore completed sessions from disk into memory on startup."""
        loaded = 0
        for p in _SESSIONS_DIR.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Restore as plain dict (messages are serialized strings, not LangChain objects)
                # We only need this for the /report endpoint which reads node_scores, not messages
                self._store[p.stem] = data  # type: ignore[assignment]
                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load session {p.name}: {e}")
        if loaded:
            logger.info(f"Restored {loaded} completed session(s) from disk")

    async def set(self, session_id: str, state: InterviewState) -> None:
        async with self._lock:
            self._store[session_id] = state
        # Persist to disk when interview is complete
        if state.get("interview_complete"):
            await self._persist(session_id, state)

    async def get(self, session_id: str) -> Optional[InterviewState]:
        async with self._lock:
            return self._store.get(session_id)

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._store.pop(session_id, None)

    async def exists(self, session_id: str) -> bool:
        async with self._lock:
            return session_id in self._store

    async def _persist(self, session_id: str, state: InterviewState) -> None:
        path = _session_path(session_id)
        try:
            data = _serialize(state)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _write_json, path, data)
            logger.info(f"Session {session_id} persisted to {path}")
        except Exception as e:
            logger.warning(f"Failed to persist session {session_id}: {e}")

        # Clean up ResumeProject nodes from Neo4j — no longer needed after interview ends
        try:
            from app.rag.graph_rag.knowledge_base import get_knowledge_graph
            kg = get_knowledge_graph()
            kg.delete_session_nodes(session_id)
        except Exception as e:
            logger.warning(f"Failed to clean up Neo4j session nodes for {session_id}: {e}")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Module-level singleton
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
