"""
Interview session management endpoints.

POST /api/v1/interview/start
  Body: {session_id}
  → Runs the first LangGraph turn (greeting) and returns the interviewer's
    opening text + TTS audio (base64 encoded).

GET  /api/v1/interview/{session_id}/state
  → Returns current interview state snapshot.

GET  /api/v1/interview/{session_id}/report
  → Returns final evaluation report (after interview_complete=True).

POST /api/v1/interview/{session_id}/turn  (text-only fallback, no audio)
  Body: {user_text}
  → One text turn: appends HumanMessage, invokes LangGraph, returns AI reply.
"""
import base64
import json as _json
import os
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from loguru import logger

from app.audio.tts import tts_bytes
from app.core.interview_graph import get_interview_graph
from app.core.session_store import get_session_store
from app.audio.handler import _extract_last_ai_text
from langchain_core.messages import HumanMessage

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────

class StartRequest(BaseModel):
    session_id: str
    tts_enabled: bool = True   # set False to skip TTS on start


class StartResponse(BaseModel):
    session_id: str
    current_node: str
    greeting_text: str
    tts_audio_b64: str = ""    # base64-encoded PCM if tts_enabled


class TurnRequest(BaseModel):
    user_text: str
    tts_enabled: bool = False


class TurnResponse(BaseModel):
    ai_text: str
    current_node: str
    phase_turn_count: int
    should_transition: bool
    interview_complete: bool
    tts_audio_b64: str = ""


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("/start", response_model=StartResponse)
async def start_interview(body: StartRequest):
    """
    Run the first greeting turn and return the interviewer's opening text.
    The session must already exist (created by POST /upload/).
    """
    store = get_session_store()
    state = await store.get(body.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found. Call /upload first.")

    graph = get_interview_graph()
    result = await graph.ainvoke(dict(state))
    state = dict(state)
    state.update(result)
    await store.set(body.session_id, state)

    greeting_text = _extract_last_ai_text(result.get("messages", []))
    tts_b64 = ""
    if body.tts_enabled and greeting_text:
        try:
            audio = await tts_bytes(greeting_text)
            tts_b64 = base64.b64encode(audio).decode()
        except Exception as e:
            logger.warning(f"TTS failed on start: {e}")

    logger.info(f"Interview started: session={body.session_id}")
    return StartResponse(
        session_id=body.session_id,
        current_node=state.get("current_node", "greeting"),
        greeting_text=greeting_text,
        tts_audio_b64=tts_b64,
    )


@router.get("/{session_id}/state")
async def get_state(session_id: str):
    """Return a lightweight snapshot of the current interview state."""
    store = get_session_store()
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id":        session_id,
        "current_node":      state.get("current_node"),
        "phase_turn_count":  state.get("phase_turn_count"),
        "should_transition": state.get("should_transition"),
        "interview_complete": state.get("interview_complete"),
        "candidate_name":    state.get("candidate_name"),
        "node_scores":       state.get("node_scores"),
        "message_count":     len(state.get("messages", [])),
    }


@router.post("/{session_id}/turn", response_model=TurnResponse)
async def text_turn(session_id: str, body: TurnRequest):
    """
    Text-only fallback endpoint (no audio pipeline required).
    Useful for testing and non-audio clients.
    """
    store = get_session_store()
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    state = dict(state)
    state["messages"] = list(state.get("messages", [])) + [
        HumanMessage(content=body.user_text)
    ]

    graph = get_interview_graph()
    result = await graph.ainvoke(state)
    state.update(result)
    await store.set(session_id, state)

    ai_text = _extract_last_ai_text(result.get("messages", []))
    tts_b64 = ""
    if body.tts_enabled and ai_text:
        try:
            audio = await tts_bytes(ai_text)
            tts_b64 = base64.b64encode(audio).decode()
        except Exception as e:
            logger.warning(f"TTS failed: {e}")

    return TurnResponse(
        ai_text=ai_text,
        current_node=result.get("current_node", ""),
        phase_turn_count=result.get("phase_turn_count", 0),
        should_transition=result.get("should_transition", False),
        interview_complete=result.get("interview_complete", False),
        tts_audio_b64=tts_b64,
    )


@router.post("/{session_id}/turn/stream")
async def stream_turn(session_id: str, body: TurnRequest):
    """
    Streaming version of the text turn endpoint using SSE.
    Tokens are pushed to the client as they are generated by the LLM.

    SSE event format:
      data: {"type": "token",  "text": "..."}      — one or more LLM tokens
      data: {"type": "done",   "current_node": ..., "phase_turn_count": ...,
                               "should_transition": ..., "interview_complete": ...}
      data: {"type": "error",  "detail": "..."}
    """
    store = get_session_store()
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    state = dict(state)
    state["messages"] = list(state.get("messages", [])) + [
        HumanMessage(content=body.user_text)
    ]

    graph = get_interview_graph()

    async def generate():
        final_out: dict = {}
        try:
            async for event in graph.astream_events(state, version="v2"):
                ev = event["event"]

                if ev == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    # Skip tool-call chunks (content is empty during function calling)
                    if getattr(chunk, "tool_call_chunks", None):
                        continue
                    content = chunk.content
                    if isinstance(content, str) and content:
                        yield f"data: {_json.dumps({'type': 'token', 'text': content}, ensure_ascii=False)}\n\n"
                    elif isinstance(content, list):
                        # Some model variants return list of dicts
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text = part.get("text", "")
                                if text:
                                    yield f"data: {_json.dumps({'type': 'token', 'text': text}, ensure_ascii=False)}\n\n"

                elif ev == "on_chain_end":
                    out = event["data"].get("output", {})
                    if isinstance(out, dict) and "current_node" in out:
                        final_out.update(out)

        except Exception as e:
            logger.exception(f"Streaming error: {e}")
            yield f"data: {_json.dumps({'type': 'error', 'detail': str(e)}, ensure_ascii=False)}\n\n"
            return

        # Persist updated state
        state.update(final_out)
        await store.set(session_id, state)
        logger.info(f"Stream turn done: session={session_id} node={final_out.get('current_node')}")

        yield f"data: {_json.dumps({'type': 'done', 'current_node': final_out.get('current_node', ''), 'phase_turn_count': final_out.get('phase_turn_count', 0), 'should_transition': final_out.get('should_transition', False), 'interview_complete': final_out.get('interview_complete', False)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


VALID_PHASES = {"greeting", "resume_dive", "jd_tech", "coding_test", "wrap_up"}


@router.post("/{session_id}/set_phase")
async def set_phase(session_id: str, body: dict):
    """Force-jump to any interview phase (for debugging / custom flow)."""
    store = get_session_store()
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    phase = body.get("phase", "")
    if phase not in VALID_PHASES:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")

    state = dict(state)
    state["current_node"] = phase
    state["phase_turn_count"] = 0
    state["should_transition"] = False
    await store.set(session_id, state)
    logger.info(f"Phase jump: session={session_id} → {phase}")
    return {"current_node": phase}


@router.get("/{session_id}/report")
async def get_report(session_id: str):
    """
    Return the full evaluation report after interview_complete=True.

    Response includes:
      - overall_score, recommendation, summary
      - dimension_scores (technical_depth, cs_fundamentals, coding_ability, communication, jd_match)
      - phase_scores (per-phase average)
      - weak_items: questions the candidate answered poorly, with correct answers and study suggestions
      - strengths, improvement_areas
    """
    store = get_session_store()
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not state.get("interview_complete"):
        raise HTTPException(status_code=409, detail="Interview not yet complete")

    node_scores = state.get("node_scores", {})
    evaluation = node_scores.get("evaluation", {})

    # Build per-phase QA summary (questions + scores, without full tool_material)
    phase_details: dict = {}
    for phase in ("resume_dive", "jd_tech", "coding_test"):
        phase_data = node_scores.get(phase, {})
        qa_records = phase_data.get("qa_records", [])
        phase_details[phase] = {
            "turn_count": phase_data.get("turn_count", 0),
            "avg_score": evaluation.get("phase_scores", {}).get(phase),
            "questions": [
                {
                    "turn":             r["turn"],
                    "question":         r.get("question") or r.get("new_question", ""),
                    "answer":           r.get("answer", ""),
                    "score":            r.get("score"),
                    "is_weak":          r.get("is_weak", False),
                    "feedback":         r.get("feedback", ""),
                    "correct_answer":   r.get("correct_answer", ""),
                    "study_suggestions": r.get("study_suggestions", []),
                }
                for r in qa_records
            ],
        }

    return {
        "session_id":      session_id,
        "candidate_name":  state.get("candidate_name"),
        "overall_score":   evaluation.get("overall_score"),
        "recommendation":  evaluation.get("recommendation"),
        "summary":         evaluation.get("summary"),
        "dimension_scores": evaluation.get("dimension_scores", {}),
        "strengths":       evaluation.get("strengths", []),
        "improvement_areas": evaluation.get("improvement_areas", []),
        "weak_items":      evaluation.get("weak_items", []),
        "phase_details":   phase_details,
        "total_messages":  len(state.get("messages", [])),
        "interview_mode":  state.get("interview_mode", "tech"),
    }


@router.get("/{session_id}/messages")
async def get_messages(session_id: str):
    """Return the full conversation transcript for a completed session."""
    store = get_session_store()
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    raw = state.get("messages", [])
    result = []
    for m in raw:
        # In-memory: LangChain message objects; on-disk restore: plain dicts
        if isinstance(m, dict):
            mtype = m.get("type", "")
            content = m.get("content", "")
        else:
            mtype = type(m).__name__
            content = getattr(m, "content", "")
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
        if mtype in ("AIMessage", "HumanMessage") and str(content).strip():
            result.append({"role": "ai" if mtype == "AIMessage" else "human",
                           "content": str(content)})
    return result


@router.get("/sessions")
async def list_sessions():
    """
    返回所有已完成面试的摘要列表，从 ./data/sessions/ 目录读取。
    按完成时间倒序排列（最新的在前）。
    """
    sessions_dir = Path("./data/sessions")
    if not sessions_dir.exists():
        return []

    sessions = []
    for p in sessions_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = _json.load(f)
            evaluation = data.get("node_scores", {}).get("evaluation", {})
            mtime = p.stat().st_mtime
            sessions.append({
                "session_id":     p.stem,
                "candidate_name": data.get("candidate_name", "未知"),
                "interview_mode": data.get("interview_mode", "tech"),
                "overall_score":  evaluation.get("overall_score"),
                "recommendation": evaluation.get("recommendation", ""),
                "completed_at":   datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                "total_questions": evaluation.get("total_questions", 0),
                "weak_count":     evaluation.get("weak_count", 0),
            })
        except Exception as e:
            logger.warning(f"Failed to read session {p.name}: {e}")

    sessions.sort(key=lambda x: x["completed_at"], reverse=True)
    return sessions
