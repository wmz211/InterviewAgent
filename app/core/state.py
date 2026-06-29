"""
LangGraph interview state — single source of truth for all node I/O.
"""
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class InterviewState(TypedDict):
    # ── Session identity ──────────────────────────────────────────
    session_id: str
    candidate_name: str

    # ── Document context ───────
    # ───────────────────────────────────
    resume_summary: str           # Parsed resume text (for LLM context)
    jd_text: str                  # Raw JD text (for CS_Fundamentals topic selection)

    # ── Conversation ─────────────────────────────────────────────
    messages: Annotated[list, add_messages]
    current_node: str             # Active phase name

    # ── Per-turn context ─────────────────────────────────────────
    current_topic: str            # e.g. "RAG向量检索"
    context_summary: str          # Compressed history injected into system prompt on phase change

    # ── Long-term performance tracking ───────────────────────────
    node_scores: dict[str, Any]   # {phase: {turn_count, topics, notes}}
    asked_question_ids: list[str] # Prevent repeating questions

    # ── Flow control ─────────────────────────────────────────────
    phase_turn_count: int         # Turns within current phase (resets on transition)
    should_transition: bool
    interview_complete: bool
    interview_mode: str           # "tech" | "hr"
    practice_mode: bool
    selected_phase: str
