"""Helpers for mapping InterviewState into durable session metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def flow_mode_from_state(state: Mapping[str, Any]) -> str:
    return "phase_practice" if state.get("practice_mode") else "full_interview"


def build_session_create_values(state: Mapping[str, Any]) -> dict[str, Any]:
    now = utc_now()
    return {
        "session_id": str(state.get("session_id", "")),
        "user_id": int(state.get("user_id", 0)),
        "candidate_name": str(state.get("candidate_name", "")),
        "interview_mode": str(state.get("interview_mode", "tech")),
        "flow_mode": flow_mode_from_state(state),
        "practice_mode": bool(state.get("practice_mode", False)),
        "selected_phase": str(state.get("selected_phase", "")),
        "current_node": str(state.get("current_node", "greeting")),
        "status": "created",
        "created_at": now,
        "updated_at": now,
    }


def build_session_update_values(state: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "candidate_name": str(state.get("candidate_name", "")),
        "interview_mode": str(state.get("interview_mode", "tech")),
        "flow_mode": flow_mode_from_state(state),
        "practice_mode": bool(state.get("practice_mode", False)),
        "selected_phase": str(state.get("selected_phase", "")),
        "current_node": str(state.get("current_node", "greeting")),
        "status": "completed" if state.get("interview_complete") else "active",
        "updated_at": utc_now(),
    }
    if state.get("interview_complete"):
        values["completed_at"] = values["updated_at"]
    return values
