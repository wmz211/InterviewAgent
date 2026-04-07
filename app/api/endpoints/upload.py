"""
File upload endpoint: resume (PDF/DOCX) + JD (plain text in request body).

POST /api/v1/upload/
  Form fields:
    resume : UploadFile  (PDF or DOCX)
    jd_text: str         (job description text, pasted by user)

Returns:
    session_id, resume summary
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from pydantic import BaseModel
from loguru import logger

from app.core.interview_graph import make_initial_state
from app.core.session_store import get_session_store
from app.rag.parser.resume_parser import parse_resume

_SESSIONS_DIR = Path("./data/sessions")

router = APIRouter()


class UploadResponse(BaseModel):
    session_id: str
    candidate_name: str
    resume_summary: str


@router.post("/", response_model=UploadResponse)
async def upload_documents(
    resume: UploadFile = File(..., description="Candidate resume (PDF or DOCX)"),
    jd_text: str = Form(..., description="Job description (plain text)"),
    interview_mode: str = Form("tech", description="Interview track: 'tech' or 'hr'"),
):
    """
    1. Parse resume bytes → ResumeData
    2. Create initial LangGraph state → store in session store
    3. Return session_id for subsequent WebSocket connection
    """
    # --- Validate file type ---
    filename = (resume.filename or "").lower()
    if not (filename.endswith(".pdf") or filename.endswith(".docx")):
        raise HTTPException(
            status_code=400,
            detail="Resume must be a PDF or DOCX file"
        )

    session_id = str(uuid.uuid4())
    logger.info(f"New upload: session={session_id}, file={resume.filename}")

    # --- Parse resume ---
    try:
        raw_bytes = await resume.read()
        resume_data = await parse_resume(raw_bytes, filename)
        logger.info(f"Parsed resume: {resume_data.name}, {len(resume_data.projects)} projects")
    except Exception as e:
        logger.exception("Resume parsing failed")
        raise HTTPException(status_code=422, detail=f"Resume parsing failed: {e}")

    # --- Build resume summary string ---
    resume_summary = _format_resume_summary(resume_data)

    # --- Initialize LangGraph state and store ---
    mode = interview_mode if interview_mode in ("tech", "hr") else "tech"
    state = make_initial_state(
        session_id=session_id,
        resume_summary=resume_summary,
        jd_text=jd_text,
        interview_mode=mode,
    )
    state["candidate_name"] = resume_data.name

    store = get_session_store()
    await store.set(session_id, state)

    logger.info(f"Session {session_id} ready: name={resume_data.name}")

    return UploadResponse(
        session_id=session_id,
        candidate_name=resume_data.name,
        resume_summary=resume_summary,
    )


@router.get("/resumes")
async def list_resumes():
    """
    List previously uploaded resumes available for reuse.
    Reads from completed sessions (data/sessions/*.json).
    Returns newest-first, deduplicates by candidate_name (keeps latest).
    """
    if not _SESSIONS_DIR.exists():
        return []

    seen: dict[str, dict] = {}
    for p in sorted(_SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            name = d.get("candidate_name", "").strip()
            if not name or not d.get("resume_summary"):
                continue
            if name not in seen:
                jd = d.get("jd_text", "")
                seen[name] = {
                    "session_id": d.get("session_id", p.stem),
                    "candidate_name": name,
                    "jd_snippet": jd[:60].replace("\n", " ") + ("..." if len(jd) > 60 else ""),
                    "jd_text": jd,
                    "interview_mode": d.get("interview_mode", "tech"),
                    "date": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d"),
                }
        except Exception as e:
            logger.warning(f"Failed to read session {p.name}: {e}")

    return list(seen.values())


class ReuseRequest(BaseModel):
    source_session_id: str
    jd_text: str = ""          # empty = keep original JD
    interview_mode: str = ""   # empty = keep original mode


@router.post("/reuse", response_model=UploadResponse)
async def reuse_resume(body: ReuseRequest):
    """
    Create a new interview session reusing a previous resume's parsed data.
    Skips resume parsing and KG anchoring — starts in ~100ms instead of ~10s.
    """
    # Load source session
    src_path = _SESSIONS_DIR / f"{body.source_session_id}.json"
    if not src_path.exists():
        raise HTTPException(status_code=404, detail="Source session not found")

    try:
        with open(src_path, encoding="utf-8") as f:
            src = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read source session: {e}")

    resume_summary = src.get("resume_summary", "")
    candidate_name = src.get("candidate_name", "")

    if not resume_summary:
        raise HTTPException(status_code=422, detail="Source session has no resume summary")

    jd_text = body.jd_text.strip() or src.get("jd_text", "")
    mode = body.interview_mode if body.interview_mode in ("tech", "hr") else src.get("interview_mode", "tech")
    session_id = str(uuid.uuid4())

    state = make_initial_state(
        session_id=session_id,
        resume_summary=resume_summary,
        jd_text=jd_text,
        interview_mode=mode,
    )
    state["candidate_name"] = candidate_name

    store = get_session_store()
    await store.set(session_id, state)

    logger.info(f"Reused session {body.source_session_id} → new session {session_id} ({candidate_name})")

    return UploadResponse(
        session_id=session_id,
        candidate_name=candidate_name,
        resume_summary=resume_summary,
    )


def _format_resume_summary(resume_data) -> str:
    """Build a concise resume summary string for the system prompt."""
    edu = resume_data.education
    if isinstance(edu, list) and edu:
        e = edu[0]
        edu_str = f"{e.get('school','')} {e.get('degree','')} {e.get('major','')}".strip()
    else:
        edu_str = str(edu)

    lines = [
        f"姓名：{resume_data.name}",
        f"学历：{edu_str}",
    ]
    if resume_data.skills:
        lines.append(f"技能：{', '.join(resume_data.skills[:12])}")
    for p in resume_data.projects[:3]:
        lines.append(f"\n项目：{p.name}")
        if p.description:
            lines.append(f"  描述：{p.description[:200]}")
        if p.tech_stack:
            lines.append(f"  技术栈：{', '.join(p.tech_stack)}")
    return "\n".join(lines)
