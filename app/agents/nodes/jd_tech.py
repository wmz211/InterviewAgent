"""
JD Tech node — 按 JD 要求考察候选人的技术深度。
使用 GraphRAG：从 JD 文本中匹配 KG 技术节点，沿 LEADS_TO 链路逐步追问。

流程：
  1. 首轮：从 JD 关键词匹配 KG Tech/Concept 节点，构建追问链
  2. 每轮：对当前链节点调用 graph_rag_tool 获取追问提示
  3. 每个节点问 MAX_TURNS_PER_NODE 轮后，推进到链中的下一个节点
  4. 达到 PHASE_MIN_TURNS["jd_tech"] 后，过渡到 wrap_up
"""
import re as _re

from langchain_core.messages import SystemMessage
from loguru import logger

from app.agents.nodes.base import (
    make_llm, check_transition, llm_tool_loop, build_qa_record, ANTI_SIMULATION_RULE,
)
from app.agents.tools.graph_search_tool import GRAPH_RAG_TOOLS
from app.core.state import InterviewState

_GLINER_LABELS = [
    "技术框架", "工具", "概念", "方法论",
    "技术技能", "AI模型", "系统组件",
    "技术术语", "开发工具", "算法"
]


def _extract_entities(jd_text: str) -> list[str]:
    """用 GLiNER 从 JD 抽取技术实体，不可用时退回正则。"""
    try:
        from app.rag.graph_rag.knowledge_base import _get_gliner
        model = _get_gliner()
        if model:
            entities = model.predict_entities(jd_text, labels=_GLINER_LABELS)
            terms = list(dict.fromkeys(
                e["text"] for e in entities if 1 < len(e["text"]) < 20
            ))
            if terms:
                logger.debug(f"GLiNER extracted {len(terms)} entities: {terms[:10]}")
                return terms
    except Exception as e:
        logger.warning(f"GLiNER extraction failed: {e}")
    # 正则兜底：抽英文技术词
    terms = _re.findall(r'[A-Za-z][A-Za-z0-9.+#_-]{2,}', jd_text)
    return list(dict.fromkeys(terms))[:20]

MAX_TURNS_PER_NODE = 2   # 每个技术节点最多追问几轮后推进

_SYSTEM = """\
你是一位技术面试官，正在按照岗位要求考察候选人的技术深度。

【岗位要求（JD 摘要）】
{jd_summary}

【候选人技术背景（简历锚定实体）】
{entity_background}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【本轮考察的技术点】{current_label}
【本轮是第 {turns_on_node} 次在此技术点提问（共最多 {max_turns} 次）】
{node_remaining_hint}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【操作步骤】
1. 调用 lookup_tech_node(tech_name="{current_label}") 获取节点 ID
2. 调用 graph_rag_tool 获取追问路径与提示
3. 结合候选人简历背景，提出一个口语化、有针对性的问题

【追问原则】
- 仔细阅读上方的完整对话历史，绝对不要重复已经问过的问题或已经讨论过的话题（包括候选人已明确表示没用过的技术）
- 候选人说"不知道"或"没用过"：只说"好的，换个问题"，绝不解释答案，也不要在后续轮次再问同一技术
- 每次只问一个问题
- 问题要与候选人简历或 JD 结合，不要照搬教科书定义
- 已覆盖的技术点：{covered_labels}
{anti_simulation}"""

_llm = make_llm(temperature=0.5)
_llm_with_tools = _llm.bind_tools(GRAPH_RAG_TOOLS)


def _build_jd_chain(jd_text: str) -> list[dict]:
    """
    混合检索架构：GLiNER 实体抽取 → BM25 + 向量双路召回 → RRF 融合 → LEADS_TO 展开。
    任一环节不可用时自动降级，保证链路不中断。
    """
    from app.rag.graph_rag.knowledge_base import get_knowledge_graph, rrf_merge
    kg = get_knowledge_graph()

    # ── 1. 实体抽取 ──────────────────────────────────────────────────
    terms = _extract_entities(jd_text)
    logger.info(f"JD entity terms: {terms}")

    # ── 2. 双路召回 ──────────────────────────────────────────────────
    bm25_scores   = kg.bm25_search(terms)   if terms else {}
    vector_scores = kg.vector_search(terms) if terms else {}

    bm25_ranking   = sorted(bm25_scores,   key=lambda x: -bm25_scores[x])
    vector_ranking = sorted(vector_scores, key=lambda x: -vector_scores[x])

    # ── 降级：两路都空时用 Lucene fulltext ──────────────────────────
    if not bm25_ranking and not vector_ranking:
        logger.warning("BM25 and vector both empty; fallback to Lucene fulltext")
        seen: set[str] = set()
        fallback: dict[str, int] = {}
        for term in terms[:20]:
            for c in kg.fulltext_search(term, top_k=2):
                nid = c["node_id"]
                if nid not in seen:
                    fallback[nid] = fallback.get(nid, 0) + 1
                    seen.add(nid)
        bm25_ranking = sorted(fallback, key=lambda x: -fallback[x])

    # ── 3. RRF 融合，取 top5 ─────────────────────────────────────────
    active_rankings = [r for r in [bm25_ranking, vector_ranking] if r]
    final_scores = rrf_merge(active_rankings)
    top_ids = sorted(final_scores, key=lambda x: -final_scores[x])[:5]
    logger.info(f"JD top nodes after RRF: {top_ids}")

    # ── 4. 沿 LEADS_TO 展开成链（原有逻辑不变）──────────────────────
    chain: list[dict] = []
    seen_ids: set[str] = set()
    for node_id in top_ids:
        node = kg.get_node(node_id)
        if not node or node_id in seen_ids:
            continue
        chain.append({"node_id": node_id, "label": node.label})
        seen_ids.add(node_id)
        for step in kg.get_leads_to_chain(node_id, max_depth=2):
            sid = step["node_id"]
            if sid not in seen_ids:
                chain.append({"node_id": sid, "label": step["label"]})
                seen_ids.add(sid)

    logger.info(f"JD chain built: {[c['label'] for c in chain]}")
    return chain


async def jd_tech_node(state: InterviewState) -> dict:
    phase_turn = state.get("phase_turn_count", 0)
    jd_text = state.get("jd_text", "")
    jd_summary = jd_text[:400] if jd_text else "（未提供）"

    scores = state.get("node_scores", {})
    phase_data = scores.get("jd_tech", {
        "turn_count": 0,
        "chain": [],
        "chain_idx": 0,
        "turns_on_node": 0,
        "covered_labels": [],
        "qa_records": [],
    })

    # ── 首轮构建追问链 ────────────────────────────────────────────
    chain: list[dict] = phase_data.get("chain", [])
    if not chain and jd_text:
        chain = _build_jd_chain(jd_text)
        phase_data["chain"] = chain

    chain_idx: int = phase_data.get("chain_idx", 0)
    turns_on_node: int = phase_data.get("turns_on_node", 0)
    covered_labels: list[str] = phase_data.get("covered_labels", [])

    # ── 选当前节点 ────────────────────────────────────────────────
    if chain and chain_idx < len(chain):
        current = chain[chain_idx]
        current_label = current["label"]
    else:
        # 链用完或没有匹配到节点 → 直接用 JD 里提炼的关键词
        current_label = "LLM应用工程"
        current = {"node_id": "", "label": current_label}

    # 是否需要推进到下一个节点
    if turns_on_node >= MAX_TURNS_PER_NODE and chain_idx + 1 < len(chain):
        chain_idx += 1
        turns_on_node = 0
        current = chain[chain_idx]
        current_label = current["label"]
        if current_label not in covered_labels:
            covered_labels = list(covered_labels) + [current_label]

    if current_label not in covered_labels:
        covered_labels = list(covered_labels) + [current_label]

    node_remaining = MAX_TURNS_PER_NODE - turns_on_node
    node_remaining_hint = (
        f"（还有 {node_remaining} 次机会，请充分考察）"
        if node_remaining > 0
        else "（此节点考察完毕，下轮自动切换）"
    )

    # ── 候选人背景 ────────────────────────────────────────────────
    entities = state.get("anchored_entities", [])
    entity_background = (
        ", ".join(e["kg_node_label"] for e in entities) or "（未从简历锚定到具体技术点）"
    )

    system = _SYSTEM.format(
        jd_summary=jd_summary,
        entity_background=entity_background,
        current_label=current_label,
        turns_on_node=turns_on_node + 1,
        max_turns=MAX_TURNS_PER_NODE,
        node_remaining_hint=node_remaining_hint,
        covered_labels=", ".join(covered_labels) if covered_labels else "无",
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    messages = [SystemMessage(content=system)] + state["messages"]
    new_messages, _ = await llm_tool_loop(_llm_with_tools, messages, GRAPH_RAG_TOOLS)

    # ── 更新节点追踪 ──────────────────────────────────────────────
    turns_on_node += 1
    phase_turn += 1
    should_transition = check_transition(
        {**state, "phase_turn_count": phase_turn}, "jd_tech"
    )

    qa = build_qa_record(
        state_messages=state["messages"],
        new_messages=new_messages,
        phase="jd_tech",
        turn=phase_turn,
    )
    phase_data.setdefault("qa_records", []).append(qa)
    phase_data["turn_count"] = phase_turn
    phase_data["chain"] = chain
    phase_data["chain_idx"] = chain_idx
    phase_data["turns_on_node"] = turns_on_node
    phase_data["covered_labels"] = covered_labels
    scores["jd_tech"] = phase_data

    going_to = "coding_test" if should_transition else "jd_tech"

    return {
        "messages": new_messages,
        "current_node": going_to,
        "phase_turn_count": 0 if should_transition else phase_turn,
        "should_transition": should_transition,
        "node_scores": scores,
    }
