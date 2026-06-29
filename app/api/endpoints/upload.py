"""
File upload endpoint: resume (PDF/DOCX) + JD (plain text in request body).

POST /api/v1/upload/
  Form fields:
    resume : UploadFile  (PDF or DOCX), optional when reusing a resume
    jd_text: str         (job description text, pasted or reused)

Returns:
    session_id, resume summary
"""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.agents.nodes.jd_tech import prepare_jd_tech_phase_data
from app.core.interview_graph import make_initial_state
from app.core.reusable_materials import (
    get_reuse_options,
    get_reusable_jd,
    get_reusable_resume,
    save_reusable_materials,
)
from app.core.session_store import get_session_store
from app.db.database import get_db
from app.db.interview_sessions import create_interview_session
from app.db.models import User
from app.rag.parser.resume_parser import parse_resume

router = APIRouter()


class UploadResponse(BaseModel):
    session_id: str
    candidate_name: str
    resume_summary: str
    practice_mode: bool = False
    selected_phase: str = ""


class ReusableResumeOption(BaseModel):
    session_id: str
    candidate_name: str = ""
    resume_summary: str
    created_at: str = ""


class ReusableJdOption(BaseModel):
    session_id: str
    jd_text: str
    jd_preview: str = ""
    created_at: str = ""


class ReuseOptionsResponse(BaseModel):
    resumes: list[ReusableResumeOption]
    jds: list[ReusableJdOption]


@router.get("/reuse-options", response_model=ReuseOptionsResponse)
async def list_reuse_options(current_user: User = Depends(get_current_user)):
    """Return resumes and JDs previously submitted by the current user."""
    options = get_reuse_options(current_user.id)
    return ReuseOptionsResponse(**options)


@router.post("/", response_model=UploadResponse)
async def upload_documents(
    resume: UploadFile | None = File(None, description="Candidate resume (PDF or DOCX)"),
    jd_text: str = Form("", description="Job description (plain text)"),
    reuse_resume_session_id: str = Form("", description="Previous session id whose parsed resume should be reused"),
    reuse_jd_session_id: str = Form("", description="Previous session id whose JD text should be reused"),
    interview_mode: str = Form("tech", description="Interview track: 'tech' or 'hr'"),
    flow_mode: str = Form("full_interview", description="Interview flow: 'full_interview' or 'phase_practice'"),
    selected_phase: str = Form("", description="Initial phase for phase practice mode"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create an interview session from either newly uploaded materials or
    previously saved resume/JD materials owned by the current user.
    """
    session_id = str(uuid.uuid4())
    candidate_name = ""

    if resume and resume.filename:
        filename = (resume.filename or "").lower()
        if not (filename.endswith(".pdf") or filename.endswith(".docx")):
            raise HTTPException(status_code=400, detail="Resume must be a PDF or DOCX file")
        logger.info(f"New upload: session={session_id}, file={resume.filename}")
        try:
            raw_bytes = await resume.read()
            resume_data = await parse_resume(raw_bytes, filename)
            logger.info(f"Parsed resume: {resume_data.name}, {len(resume_data.projects)} projects")
        except Exception as e:
            logger.exception("Resume parsing failed")
            raise HTTPException(status_code=422, detail=f"Resume parsing failed: {e}")
        resume_summary = _format_resume_summary(resume_data)
        candidate_name = resume_data.name
    elif reuse_resume_session_id.strip():
        reusable_resume = get_reusable_resume(current_user.id, reuse_resume_session_id.strip())
        if not reusable_resume:
            raise HTTPException(status_code=404, detail="Reusable resume not found")
        resume_summary = reusable_resume["resume_summary"]
        candidate_name = reusable_resume.get("candidate_name", "")
        logger.info(f"Reused resume: session={session_id}, source={reuse_resume_session_id}")
    else:
        raise HTTPException(status_code=400, detail="Resume is required unless reusing a previous resume")

    resolved_jd_text = jd_text.strip()
    if not resolved_jd_text and reuse_jd_session_id.strip():
        reusable_jd = get_reusable_jd(current_user.id, reuse_jd_session_id.strip())
        if not reusable_jd:
            raise HTTPException(status_code=404, detail="Reusable JD not found")
        resolved_jd_text = reusable_jd["jd_text"]

    mode = interview_mode if interview_mode in ("tech", "hr") else "tech"
    state = make_initial_state(
        session_id=session_id,
        resume_summary=resume_summary,
        jd_text=resolved_jd_text or "General technical position",
        interview_mode=mode,
        flow_mode=flow_mode,
        selected_phase=selected_phase,
    )
    state["candidate_name"] = candidate_name
    state["user_id"] = current_user.id
    if mode == "tech":
        try:
            state["node_scores"]["jd_tech"] = prepare_jd_tech_phase_data(
                state["jd_text"],
                state["node_scores"].get("jd_tech", {}),
            )
        except Exception as e:
            logger.warning(f"JD tech prewarm failed during upload: {e}")

    store = get_session_store()
    await store.set(session_id, state)
    await create_interview_session(db, state)
    save_reusable_materials(
        current_user.id,
        session_id,
        candidate_name,
        resume_summary,
        state["jd_text"],
    )

    logger.info(f"Session {session_id} ready: name={candidate_name}")
    return UploadResponse(
        session_id=session_id,
        candidate_name=candidate_name,
        resume_summary=resume_summary,
        practice_mode=state.get("practice_mode", False),
        selected_phase=state.get("selected_phase", ""),
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
