"""
Admin endpoints for operational overview.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import InterviewMessage, InterviewSession, User

router = APIRouter()

_ROOT = Path(__file__).resolve().parents[3]
_GRAPH_PATH = _ROOT / "data" / "tech_knowledge_graph.json"
_QUESTION_BANK_DIR = _ROOT / "data" / "question_bank"


class AdminUserResponse(BaseModel):
    id: int
    email: str
    username: str


class MetricResponse(BaseModel):
    label: str
    value: int | str
    hint: str = ""


class DomainResponse(BaseModel):
    id: str
    label: str
    node_count: int
    sample_topics: list[str] = []


class QuestionBankResponse(BaseModel):
    name: str
    question_count: int
    topics: list[str] = []
    difficulties: dict[str, int] = {}


class PhaseResponse(BaseModel):
    key: str
    label: str
    track: str
    description: str


class AdminOverviewResponse(BaseModel):
    admin: AdminUserResponse
    metrics: list[MetricResponse]
    domains: list[DomainResponse]
    node_types: dict[str, int]
    question_banks: list[QuestionBankResponse]
    phases: list[PhaseResponse]
    session_status: dict[str, int]
    mode_distribution: dict[str, int]


def parse_admin_emails(raw: str) -> set[str]:
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def admin_email_allowlist() -> set[str]:
    emails = parse_admin_emails(get_settings().admin_emails)
    env_file_value = dotenv_values(_ROOT / ".env").get("ADMIN_EMAILS")
    if env_file_value:
        emails.update(parse_admin_emails(env_file_value))
    return emails


def _require_admin(user: User) -> None:
    allowed = admin_email_allowlist()
    if user.email.lower() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )


def _safe_load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def summarize_knowledge_graph(path: Path = _GRAPH_PATH) -> tuple[list[DomainResponse], dict[str, int], int, int]:
    data = _safe_load_json(path, {"nodes": [], "edges": []})
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    edges = data.get("edges", []) if isinstance(data, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []

    labels_by_id = {
        str(node.get("id", "")): str(node.get("label", ""))
        for node in nodes
        if isinstance(node, dict)
    }
    domains = {
        str(node.get("id", "")): str(node.get("label", ""))
        for node in nodes
        if isinstance(node, dict) and node.get("type") == "Domain"
    }
    domain_topics: dict[str, list[str]] = {domain_id: [] for domain_id in domains}
    node_types: Counter[str] = Counter()

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "Unknown")
        node_types[node_type] += 1
        domain_id = str(node.get("domain") or "")
        if domain_id in domain_topics and node_type != "Domain":
            domain_topics[domain_id].append(str(node.get("label") or node.get("id") or ""))

    for edge in edges:
        if not isinstance(edge, dict) or edge.get("relation") != "BELONGS_TO":
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if target in domain_topics and labels_by_id.get(source):
            domain_topics[target].append(labels_by_id[source])

    responses = [
        DomainResponse(
            id=domain_id,
            label=label,
            node_count=len(sorted(set(domain_topics[domain_id]))),
            sample_topics=sorted(set(domain_topics[domain_id]))[:6],
        )
        for domain_id, label in domains.items()
    ]
    responses.sort(key=lambda item: (-item.node_count, item.label))
    return responses, dict(sorted(node_types.items())), len(nodes), len(edges)


def summarize_question_banks(directory: Path = _QUESTION_BANK_DIR) -> list[QuestionBankResponse]:
    banks: list[QuestionBankResponse] = []
    if not directory.exists():
        return banks
    for path in sorted(directory.glob("*.json")):
        records = _safe_load_json(path, [])
        if not isinstance(records, list):
            records = []
        topics: Counter[str] = Counter()
        difficulties: Counter[str] = Counter()
        for record in records:
            if not isinstance(record, dict):
                continue
            if record.get("topic"):
                topics[str(record["topic"])] += 1
            if record.get("difficulty"):
                difficulties[str(record["difficulty"])] += 1
        banks.append(
            QuestionBankResponse(
                name=path.stem,
                question_count=len(records),
                topics=[topic for topic, _ in topics.most_common(8)],
                difficulties=dict(difficulties),
            )
        )
    return banks


def interview_phases() -> list[PhaseResponse]:
    return [
        PhaseResponse(key="greeting", label="开场确认", track="tech", description="候选人介绍与面试目标对齐"),
        PhaseResponse(key="resume_dive", label="简历深挖", track="tech", description="围绕项目经历、职责和结果追问"),
        PhaseResponse(key="jd_tech", label="JD 技术考察", track="tech", description="结合岗位要求进行技术链路追问"),
        PhaseResponse(key="coding_test", label="算法编程", track="tech", description="考察编码思路、复杂度与边界条件"),
        PhaseResponse(key="hr_self_intro", label="自我介绍", track="hr", description="HR 轨道开场与经历概览"),
        PhaseResponse(key="hr_behavioral", label="行为面试", track="hr", description="STAR 场景、协作和冲突处理"),
        PhaseResponse(key="hr_career", label="职业规划", track="hr", description="动机、稳定性和发展目标"),
        PhaseResponse(key="wrap_up", label="总结评估", track="both", description="输出结构化评分与建议"),
    ]


async def _count_rows(db: AsyncSession, model: Any) -> int:
    result = await db.execute(select(func.count()).select_from(model))
    return int(result.scalar_one() or 0)


async def _group_counts(db: AsyncSession, column: Any) -> dict[str, int]:
    result = await db.execute(select(column, func.count()).group_by(column))
    return {str(key or "unknown"): int(count) for key, count in result.all()}


@router.get("/overview", response_model=AdminOverviewResponse)
async def overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    domains, node_types, graph_nodes, graph_edges = summarize_knowledge_graph()
    question_banks = summarize_question_banks()
    users = await _count_rows(db, User)
    sessions = await _count_rows(db, InterviewSession)
    messages = await _count_rows(db, InterviewMessage)
    status_counts = await _group_counts(db, InterviewSession.status)
    mode_counts = await _group_counts(db, InterviewSession.interview_mode)
    question_total = sum(bank.question_count for bank in question_banks)

    return AdminOverviewResponse(
        admin=AdminUserResponse(
            id=current_user.id,
            email=current_user.email,
            username=current_user.username,
        ),
        metrics=[
            MetricResponse(label="用户数", value=users, hint="已注册账号"),
            MetricResponse(label="面试会话", value=sessions, hint="SQL 持久化会话"),
            MetricResponse(label="对话消息", value=messages, hint="已落库 transcript"),
            MetricResponse(label="覆盖领域", value=len(domains), hint="知识图谱 Domain"),
            MetricResponse(label="知识节点", value=graph_nodes, hint=f"{graph_edges} 条关系"),
            MetricResponse(label="题库题目", value=question_total, hint=f"{len(question_banks)} 个题库文件"),
        ],
        domains=domains,
        node_types=node_types,
        question_banks=question_banks,
        phases=interview_phases(),
        session_status=status_counts,
        mode_distribution=mode_counts,
    )
