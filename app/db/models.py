"""
SQLAlchemy ORM models.
"""
from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    email:        Mapped[str]      = mapped_column(String, unique=True, index=True, nullable=False)
    username:     Mapped[str]      = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str]     = mapped_column(String, nullable=False)
    is_active:    Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    candidate_name: Mapped[str] = mapped_column(String, default="")
    interview_mode: Mapped[str] = mapped_column(String, default="tech")
    flow_mode: Mapped[str] = mapped_column(String, default="full_interview")
    practice_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_phase: Mapped[str] = mapped_column(String, default="")
    current_node: Mapped[str] = mapped_column(String, default="greeting")
    status: Mapped[str] = mapped_column(String, default="created", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class InterviewMessage(Base):
    __tablename__ = "interview_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.session_id"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
