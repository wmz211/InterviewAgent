"""
GraphRAG Tools — two LangChain tools for the LangGraph agent.

lookup_tech_node(tech_name)
  → queries Neo4j (exact alias + full-text search) → returns node_id candidates

graph_rag_tool(node_id, resume_context, depth)
  → Cypher multi-hop LEADS_TO traversal + HAS_PITFALL collection
  → returns structured context string injected into LLM prompt

The LLM never reads JSON or Cypher — it only sees the formatted output string.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool
from loguru import logger

from app.rag.graph_rag.knowledge_base import get_knowledge_graph


# ══════════════════════════════════════════════════════════════════════
# Tool 1: Node lookup  (Agent calls this first)
# ══════════════════════════════════════════════════════════════════════

@tool
def lookup_tech_node(tech_name: str) -> str:
    """
    在知识图谱中查找与给定技术名称匹配的节点。

    Agent 在决定深度追问某个技术点前，先调用此工具确认 node_id，
    再将 node_id 传给 graph_rag_tool 执行追问链遍历。

    Args:
        tech_name: 候选人简历或对话中出现的技术名称，
                   如 "Transformer"、"RAG"、"LoRA"、"注意力机制"

    Returns:
        JSON 字符串，包含匹配节点列表 [{node_id, label, type, description}]。
    """
    kg = get_knowledge_graph()

    # 1. Exact alias match
    node_id = kg.lookup_by_alias(tech_name)
    if node_id:
        node = kg.get_node(node_id)
        if node:
            result = [{
                "node_id": node_id, "label": node.label,
                "type": node.type, "description": node.description,
                "match_type": "exact", "confidence": 1.0,
            }]
            logger.debug(f"lookup_tech_node: exact '{tech_name}' → '{node_id}'")
            return json.dumps(result, ensure_ascii=False, indent=2)

    # 2. Full-text / fuzzy search
    candidates = kg.fulltext_search(tech_name, top_k=3)
    if not candidates:
        return json.dumps(
            {"message": f"未找到与 '{tech_name}' 匹配的知识图谱节点"},
            ensure_ascii=False,
        )

    result = []
    for c in candidates:
        node = kg.get_node(c["node_id"])
        if node:
            result.append({
                "node_id": node.id, "label": node.label,
                "type": node.type, "description": node.description,
                "match_type": "fuzzy", "confidence": c.get("score", 0.8),
            })

    logger.debug(f"lookup_tech_node: fuzzy '{tech_name}' → {[r['node_id'] for r in result]}")
    return json.dumps(result, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════
# Tool 2: Graph traversal  (Agent calls this second)
# ══════════════════════════════════════════════════════════════════════

@tool
def graph_rag_tool(
    node_id: str,
    resume_context: str,
    depth: int = 3,
) -> str:
    """
    遍历知识图谱的追问链，返回结构化面试上下文注入 LLM prompt。

    Cypher 执行路径（Neo4j backend）：
      MATCH path = (start {id: node_id})-[:LEADS_TO*1..depth]->(node)
      → 按深度排序，收集每跳的 question_hint
      → 同时收集 HAS_PITFALL 坑点节点

    Args:
        node_id:        知识图谱节点 ID（由 lookup_tech_node 返回），如 "transformer"
        resume_context: 候选人简历中与该技术相关的原文片段
        depth:          追问链深度，默认 3（L1→L2→L3）

    Returns:
        结构化追问上下文字符串，LLM 据此生成口语化追问。
    """
    kg = get_knowledge_graph()
    node = kg.get_node(node_id)
    if not node:
        return (
            f"[GraphRAG ERROR] node_id='{node_id}' 不存在于知识图谱中。\n"
            "请先调用 lookup_tech_node 确认正确的 node_id。"
        )

    depth_chain = kg.get_leads_to_chain(node_id, max_depth=depth)
    pitfalls    = kg.get_pitfalls(node_id, recursive=True)

    logger.debug(
        f"graph_rag_tool '{node_id}': chain={len(depth_chain)} hops, "
        f"pitfalls={len(pitfalls)}"
    )

    # ── Format for LLM injection ──────────────────────────────────
    lines = [
        f"## 知识图谱追问上下文：{node.label}",
        f"**技术说明**：{node.description}",
        f"**候选人简历原文**：「{resume_context}」",
        "",
        "### 追问路径（请按 L1 → L2 → L3 顺序逐步深入）",
    ]

    if depth_chain:
        for i, step in enumerate(depth_chain, 1):
            lines.append(f"\nL{i}. **{step['label']}** [{step['type']}]")
            lines.append(f"    说明：{step['description']}")
            if step.get("question_hint"):
                lines.append(f"    追问提示：{step['question_hint']}")
    else:
        lines.append(f"（无预设追问链，请围绕「{node.description}」自由发问）")

    if pitfalls:
        lines += ["", "### 高频坑点（追问链结束后抛出）"]
        for p in pitfalls:
            lines.append(f"- **{p.label}**：{p.description}")

    lines += [
        "",
        "---",
        "### 面试官行动指令",
        "1. 本轮使用 L1 追问提示，结合候选人简历原文，生成口语化追问（≤50字）。",
        "2. 候选人答完后：回答充分 → 进入 L2；回答模糊 → 在 L1 继续追问细节。",
        "3. 所有层次结束后：从坑点中选 1 个最相关的抛出。",
        "4. 全程不要暴露'追问链'概念，保持自然对话感。",
    ]

    return "\n".join(lines)


# ── Session-aware Cypher: get all deep-dive paths for a candidate ──────

def get_session_interview_paths(session_id: str) -> list[dict]:
    """
    Non-tool utility — called by LangGraph during interview initialization.

    Cypher:
      MATCH (rp:ResumeProject {session_id: $sid})
            -[:MENTIONS]->(tech)
            -[:LEADS_TO*1..3]->(concept)
      RETURN tech.id, tech.label, collect(concept.label) as chain

    Returns a list of {tech_node_id, tech_label, chain_labels}
    that the agent uses to plan its Resume_Deep_Dive questions.
    """
    from app.rag.graph_rag.knowledge_base import Neo4jKnowledgeGraph

    kg = get_knowledge_graph()
    if not isinstance(kg, Neo4jKnowledgeGraph):
        logger.warning("get_session_interview_paths requires Neo4j backend")
        return []

    with kg._session() as s:
        rows = s.run(
            """
            MATCH (rp:ResumeProject {session_id: $sid})-[:MENTIONS]->(tech)
            OPTIONAL MATCH (tech)-[:LEADS_TO*1..3]->(concept)
            RETURN tech.id       AS tech_id,
                   tech.label    AS tech_label,
                   collect(DISTINCT concept.label) AS chain_labels
            ORDER BY tech_label
            """,
            sid=session_id,
        ).data()

    logger.info(f"Session {session_id}: {len(rows)} tech nodes with interview paths")
    return rows


# ── Exported tool list (bound to LangGraph agent) ─────────────────────
GRAPH_RAG_TOOLS = [lookup_tech_node, graph_rag_tool]
