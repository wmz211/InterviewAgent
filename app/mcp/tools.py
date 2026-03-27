"""
MCP tool implementations — thin wrappers over existing RAG and graph functions.
All heavy imports and connections are initialized at module load time so that
tool calls return quickly without cold-start delays.
"""
from __future__ import annotations

import json
from typing import Any

# ── Pre-load heavy dependencies at startup ────────────────────────────────────

from app.config import get_settings
from app.rag.vector_store.retriever import _query_collection
from app.rag.graph_rag.knowledge_base import get_knowledge_graph

_settings = get_settings()
_kg = get_knowledge_graph()   # opens Neo4j / NetworkX connection once


# ── 1. Search interview questions (ChromaDB) ─────────────────────────────────

def search_interview_questions(
    query: str,
    topic: str = "",
    difficulty: str = "",
    n_results: int = 5,
) -> list[dict[str, Any]]:
    where: dict | None = None
    filters: list[dict] = []
    if topic:
        filters.append({"topic": {"$eq": topic}})
    if difficulty:
        filters.append({"difficulty": {"$eq": difficulty}})
    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    return _query_collection(
        collection_name=_settings.chroma_collection_questions,
        query=query,
        n_results=n_results,
        where=where,
    )


# ── 2. Search algorithm problems (ChromaDB) ───────────────────────────────────

def search_algorithm_problems(
    query: str,
    difficulty: str = "",
    n_results: int = 3,
) -> list[dict[str, Any]]:
    where = {"difficulty": {"$eq": difficulty}} if difficulty else None
    return _query_collection(
        collection_name=_settings.chroma_collection_algorithms,
        query=query,
        n_results=n_results,
        where=where,
    )


# ── 3. Lookup a tech concept in the knowledge graph ───────────────────────────

def lookup_tech_concept(tech_name: str) -> dict[str, Any]:
    node_id = _kg.lookup_by_alias(tech_name)
    if node_id is None:
        hits = _kg.fulltext_search(tech_name, top_k=1)
        node_id = hits[0]["id"] if hits else None

    if node_id is None:
        return {"found": False, "query": tech_name}

    node = _kg.get_node(node_id)
    if node is None:
        return {"found": False, "query": tech_name}

    components = [
        {"id": c.id, "label": c.label, "type": c.type}
        for c in _kg.get_components(node_id)
    ]
    pitfalls = [
        {"id": p.id, "label": p.label, "description": p.description}
        for p in _kg.get_pitfalls(node_id, recursive=False)
    ]

    return {
        "found": True,
        "id": node.id,
        "label": node.label,
        "type": node.type,
        "domain": node.domain,
        "description": node.description,
        "aliases": node.aliases,
        "components": components,
        "pitfalls": pitfalls,
    }


# ── 4. Get interview question hints for a tech concept ───────────────────────

def get_question_hints(tech_name: str, depth: int = 3) -> dict[str, Any]:
    node_id = _kg.lookup_by_alias(tech_name)
    if node_id is None:
        hits = _kg.fulltext_search(tech_name, top_k=1)
        node_id = hits[0]["id"] if hits else None

    if node_id is None:
        return {"found": False, "query": tech_name}

    chain = _kg.get_leads_to_chain(node_id, max_depth=depth)
    pitfalls = [
        {"label": p.label, "description": p.description}
        for p in _kg.get_pitfalls(node_id, recursive=True)
    ]

    return {
        "found": True,
        "start_node": node_id,
        "question_chain": chain,
        "pitfalls": pitfalls,
    }


# ── 5. Get interview phases info ─────────────────────────────────────────────

def get_interview_phases() -> list[dict[str, Any]]:
    return [
        {
            "phase": "greeting",
            "label": "开场介绍",
            "description": "自我介绍，建立面试氛围",
            "focus": ["候选人背景", "岗位意向", "整体印象"],
        },
        {
            "phase": "resume_dive",
            "label": "简历深挖",
            "description": "针对简历中的项目和技术栈深入追问",
            "focus": ["项目细节", "技术选型", "难点挑战", "个人贡献"],
        },
        {
            "phase": "cs_fundamentals",
            "label": "基础知识考察",
            "description": "考察计算机科学基础知识",
            "focus": ["数据结构", "操作系统", "计算机网络", "数据库", "设计模式"],
        },
        {
            "phase": "coding_test",
            "label": "编程能力测试",
            "description": "算法题或代码设计题",
            "focus": ["算法思路", "时间空间复杂度", "代码质量", "边界条件"],
        },
        {
            "phase": "wrap_up",
            "label": "总结收尾",
            "description": "面试官总结反馈，候选人提问",
            "focus": ["综合评价", "优势亮点", "改进建议", "反向提问"],
        },
    ]
