"""
Resume parser: PDF / DOCX → structured ResumeData.

Pipeline:
  raw file bytes
    → extract plain text (pdfplumber / python-docx)
    → LLM structured extraction → ResumeData
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import pdfplumber
from docx import Document
from langchain_openai import ChatOpenAI
from loguru import logger

from app.config import get_settings

settings = get_settings()

_llm = ChatOpenAI(
    model=settings.llm_model_name,
    api_key=settings.dashscope_api_key,
    base_url=settings.llm_base_url,
    temperature=0,
)

_EXTRACT_PROMPT = """\
你是一个简历解析专家。请从以下简历原文中提取结构化信息，严格按照 JSON 格式输出，不要任何解释。

输出格式：
{{
  "name": "姓名",
  "education": [
    {{"school": "学校", "degree": "学位", "major": "专业", "period": "时间段"}}
  ],
  "work_experience": [
    {{"company": "公司", "role": "职位", "period": "时间段", "highlights": ["亮点1", "亮点2"]}}
  ],
  "projects": [
    {{
      "name": "项目名",
      "role": "职责",
      "period": "时间段",
      "tech_stack": ["技术1", "技术2"],
      "description": "项目描述（保留原文关键细节）",
      "highlights": ["量化成果或技术亮点"]
    }}
  ],
  "skills": ["技能1", "技能2"],
  "summary": "50字以内的候选人技术背景总结"
}}

简历原文：
{resume_text}"""


@dataclass
class ProjectExperience:
    name: str
    role: str
    period: str
    tech_stack: list[str]
    description: str
    highlights: list[str]


@dataclass
class ResumeData:
    name: str
    education: list[dict]
    work_experience: list[dict]
    projects: list[ProjectExperience]
    skills: list[str]
    summary: str
    raw_text: str                        # 保留原文供图谱实体抽取使用


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


def _extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_raw_text(file_bytes: bytes, filename: str) -> str:
    """Dispatch to correct extractor based on file extension."""
    fname = filename.lower()
    if fname.endswith(".pdf"):
        return _extract_text_from_pdf(file_bytes)
    elif fname.endswith(".docx") or fname.endswith(".doc"):
        return _extract_text_from_docx(file_bytes)
    else:
        # Assume plain text
        return file_bytes.decode("utf-8", errors="ignore")


async def parse_resume(file_bytes: bytes, filename: str) -> ResumeData:
    """
    Full pipeline: file bytes → ResumeData.
    Called by the /upload endpoint after receiving the file.
    """
    import json

    raw_text = extract_raw_text(file_bytes, filename)
    logger.info(f"Extracted {len(raw_text)} chars from resume '{filename}'")

    prompt = _EXTRACT_PROMPT.format(resume_text=raw_text[:6000])  # 截断防超限
    response = await _llm.ainvoke(prompt)

    content = response.content.strip()
    # Strip markdown code block if LLM wraps it
    if content.startswith("```"):
        content = "\n".join(content.splitlines()[1:])
    if content.endswith("```"):
        content = content[: content.rfind("```")]

    data = json.loads(content)

    projects = [
        ProjectExperience(
            name=p.get("name", ""),
            role=p.get("role", ""),
            period=p.get("period", ""),
            tech_stack=p.get("tech_stack", []),
            description=p.get("description", ""),
            highlights=p.get("highlights", []),
        )
        for p in data.get("projects", [])
    ]

    resume = ResumeData(
        name=data.get("name", "候选人"),
        education=data.get("education", []),
        work_experience=data.get("work_experience", []),
        projects=projects,
        skills=data.get("skills", []),
        summary=data.get("summary", ""),
        raw_text=raw_text,
    )
    logger.info(
        f"Resume parsed: {resume.name}, "
        f"{len(projects)} projects, "
        f"{len(resume.skills)} skills"
    )
    return resume
