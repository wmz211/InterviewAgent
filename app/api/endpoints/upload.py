"""
File upload endpoint: resume (PDF/DOCX) + JD (plain text in request body).

POST /api/v1/upload/
  Form fields:
    resume : UploadFile  (PDF or DOCX)
    jd_text: str         (job description text, pasted by user)

Returns:
    session_id, resume summary, anchored KG entities
"""
import uuid

from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from pydantic import BaseModel
from loguru import logger

from app.core.interview_graph import make_initial_state
from app.core.session_store import get_session_store
from app.rag.graph_rag.builder import build_session_graph
import dataclasses

from app.rag.graph_rag.schema import AnchoredEntity
from app.rag.parser.resume_parser import parse_resume

router = APIRouter()


class UploadResponse(BaseModel):
    session_id: str
    candidate_name: str
    resume_summary: str
    anchored_entities: list[dict]
    entity_count: int


@router.post("/", response_model=UploadResponse)
async def upload_documents(
    resume: UploadFile = File(..., description="Candidate resume (PDF or DOCX)"),
    jd_text: str = Form(..., description="Job description (plain text)"),
    interview_mode: str = Form("tech", description="Interview track: 'tech' or 'hr'"),
):
    """
    1. Parse resume bytes → ResumeData
    2. Extract tech entities → anchor to knowledge graph
    3. Create initial LangGraph state → store in session store
    4. Return session_id for subsequent WebSocket connection
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

    # --- Build session KG + anchor entities ---
    try:
        anchored: list[AnchoredEntity] = await build_session_graph(resume_data, session_id)
    except Exception as e:
        logger.warning(f"KG anchoring failed (non-fatal): {e}")
        anchored = []

    anchored_dicts = [dataclasses.asdict(a) for a in anchored]

    # --- Build resume summary string ---
    resume_summary = _format_resume_summary(resume_data)

    # --- Initialize LangGraph state and store ---
    mode = interview_mode if interview_mode in ("tech", "hr") else "tech"
    state = make_initial_state(
        session_id=session_id,
        resume_summary=resume_summary,
        jd_text=jd_text,
        anchored_entities=anchored_dicts,
        interview_mode=mode,
    )
    state["candidate_name"] = resume_data.name

    store = get_session_store()
    await store.set(session_id, state)

    logger.info(
        f"Session {session_id} ready: "
        f"name={resume_data.name}, entities={len(anchored)}"
    )

    return UploadResponse(
        session_id=session_id,
        candidate_name=resume_data.name,
        resume_summary=resume_summary,
        anchored_entities=anchored_dicts,
        entity_count=len(anchored),
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
