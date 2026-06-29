"""Helpers for mapping LangChain messages into durable message rows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


ROLE_BY_TYPE = {
    "HumanMessage": "human",
    "AIMessage": "ai",
    "ToolMessage": "tool",
    "SystemMessage": "system",
}


def _message_type(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("type", ""))
    return type(message).__name__


def _message_content(message: Any) -> str:
    content = message.get("content", "") if isinstance(message, Mapping) else getattr(message, "content", "")
    if isinstance(content, list):
        return " ".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, Mapping) and item.get("text")
        ).strip()
    return str(content).strip()


def build_message_records(session_id: str, state: Mapping[str, Any]) -> list[dict[str, Any]]:
    phase = str(state.get("current_node", ""))
    now = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    for turn_index, message in enumerate(state.get("messages", [])):
        role = ROLE_BY_TYPE.get(_message_type(message))
        content = _message_content(message)
        if not role or not content:
            continue
        records.append(
            {
                "session_id": session_id,
                "role": role,
                "phase": phase,
                "content": content,
                "turn_index": turn_index,
                "created_at": now,
            }
        )
    return records
