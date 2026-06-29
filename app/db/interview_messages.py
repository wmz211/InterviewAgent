"""Persistence helpers for interview messages."""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.message_metadata import build_message_records
from app.db.models import InterviewMessage


async def replace_interview_messages(
    db: AsyncSession,
    session_id: str,
    state: Mapping[str, Any],
) -> int:
    records = build_message_records(session_id, state)
    await db.execute(
        delete(InterviewMessage).where(InterviewMessage.session_id == session_id)
    )
    if records:
        db.add_all(InterviewMessage(**record) for record in records)
    await db.commit()
    return len(records)
