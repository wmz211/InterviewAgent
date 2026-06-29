"""Persistence helpers for interview session metadata."""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.session_metadata import (
    build_session_create_values,
    build_session_update_values,
    utc_now,
)
from app.db.models import InterviewSession


async def create_interview_session(
    db: AsyncSession,
    state: Mapping[str, Any],
) -> InterviewSession:
    values = build_session_create_values(state)
    record = InterviewSession(**values)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_interview_session_from_state(
    db: AsyncSession,
    session_id: str,
    state: Mapping[str, Any],
    *,
    mark_started: bool = False,
) -> InterviewSession:
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.session_id == session_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        record = InterviewSession(**build_session_create_values(state))
        db.add(record)

    values = build_session_update_values(state)
    if mark_started and record.started_at is None:
        values["started_at"] = utc_now()

    for key, value in values.items():
        setattr(record, key, value)

    await db.commit()
    await db.refresh(record)
    return record
