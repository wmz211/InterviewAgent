"""
JD Tech node — 按 JD 要求考察候选人的技术深度。
使用 GraphRAG：从 JD 文本中匹配 KG 技术节点，沿 LEADS_TO 链路逐步追问。

流程：
  1. 首轮：混合检索 + RRF 融合，构建追问链，取前 3 个根节点（RRF 直接命中）作为面试主题
  2. 每个根节点：调用 graph_rag_tool 获取追问提示，LLM 自主追问
  3. LLM 认为当前节点考察充分时，调用 advance_to_next_topic 切换；
     至少追问 MIN_TURNS_PER_NODE 轮后该工具才生效
  4. 第 3 个节点 advance 后过渡到 coding_test
"""
import re as _re

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from loguru import logger

from app.agents.nodes.base import (
    make_llm, llm_tool_loop, build_qa_record,
    compress_messages, get_context_window, ANTI_SIMULATION_RULE,
)
from app.agents.tools.graph_search_tool import GRAPH_RAG_TOOLS
from app.core.state import InterviewState

_GLINER_LABELS = [
    "技术框架", "工具", "概念", "方法论",
    "技术技能", "AI模型", "系统组件",
    "技术术语", "开发工具", "算法"
]

MIN_TURNS_PER_NODE = 2   # 每个根节点最少追问轮次，未满时 advance 工具不生效
MAX_INTERVIEW_NODES = 3  # 最多考察的根节点数


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
    terms = _re.findall(r'[A-Za-z][A-Za-z0-9.+#_-]{2,}', jd_text)
    return list(dict.fromkeys(terms))[:20]


def _node_has_content(node_id: str) -> bool:
    """节点是否有实质 RAG 内容（LEADS_TO 链或 pitfall）。"""
    if not node_id:
        return False
    try:
        from app.rag.graph_rag.knowledge_base import get_knowledge_graph
        kg = get_knowledge_graph()
        return bool(
            kg.get_leads_to_chain(node_id, max_depth=3)
            or kg.get_pitfalls(node_id, recursive=True)
        )
    except Exception:
        return False


@tool
def advance_to_next_topic() -> str:
    """
    当前技术点已充分考察，推进到下一个技术点（或结束本阶段）。

    调用时机：
    - 已对当前技术点追问至少 2 轮
    - 候选人的掌握深度已基本判断清楚，或候选人明显不熟悉该技术点

    调用时用自然过渡语（如"好，这部分先到这里，我们聊下一个话题..."），
    不要暴露"节点""阶段"等词。
    """
    return "ok"


_ALL_TOOLS = GRAPH_RAG_TOOLS + [advance_to_next_topic]
_llm = make_llm(temperature=0.5)
_llm_with_tools = _llm.bind_tools(_ALL_TOOLS)


def _build_jd_chain(jd_text: str) -> list[dict]:
    """
    混合检索架构：GLiNER 实体抽取 → BM25 + 向量双路召回 → RRF 融合 → LEADS_TO 展开。
    每个节点附带 is_root 标记：
      is_root=True  → RRF 直接命中的节点（面试主题候选）
      is_root=False → LEADS_TO 展开出的子节点（考察该主题时的深入方向）
    """
    from app.rag.graph_rag.knowledge_base import get_knowledge_graph, rrf_merge
    kg = get_knowledge_graph()

    terms = _extract_entities(jd_text)
    logger.info(f"JD entity terms: {terms}")

    bm25_rankings   = kg.bm25_search(terms, top_k=5)   if terms else []
    vector_rankings = kg.vector_search(terms, top_k=5) if terms else []

    if not bm25_rankings and not vector_rankings:
        logger.warning("BM25 and vector both empty; fallback to Lucene fulltext")
        seen: set[str] = set()
        fallback: dict[str, int] = {}
        for term in terms[:20]:
            for c in kg.fulltext_search(term, top_k=2):
                nid = c["node_id"]
                if nid not in seen:
                    fallback[nid] = fallback.get(nid, 0) + 1
                    seen.add(nid)
        bm25_rankings = [sorted(fallback, key=lambda x: -fallback[x])]

    active_rankings = [r for r in bm25_rankings + vector_rankings if r]
    final_scores = rrf_merge(active_rankings)
    top_ids = sorted(final_scores, key=lambda x: -final_scores[x])[:5]
    logger.info(f"JD top nodes after RRF: {top_ids}")

    chain: list[dict] = []
    seen_ids: set[str] = set()
    for node_id in top_ids:
        node = kg.get_node(node_id)
        if not node or node_id in seen_ids:
            continue
        chain.append({"node_id": node_id, "label": node.label, "is_root": True})
        seen_ids.add(node_id)
        for step in kg.get_leads_to_chain(node_id, max_depth=2):
            sid = step["node_id"]
            if sid not in seen_ids:
                chain.append({"node_id": sid, "label": step["label"], "is_root": False})
                seen_ids.add(sid)

    logger.info(f"JD chain built: {[c['label'] for c in chain]}")
    return chain


def _get_sub_topics(chain: list[dict], root_node_id: str) -> list[str]:
    """返回 chain 中紧跟在 root_node_id 之后、直到下一个根节点之前的子话题标签。"""
    sub: list[str] = []
    found = False
    for c in chain:
        if c["node_id"] == root_node_id:
            found = True
            continue
        if found:
            if c.get("is_root", True):
                break
            sub.append(c["label"])
    return sub


_SYSTEM = """\
你是一位技术面试官，正在按照岗位要求考察候选人的技术深度。

【岗位要求（JD 摘要）】
{jd_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【当前考察主题】{current_label}（第 {node_index}/{total_nodes} 个主题）
【本主题相关子话题】{sub_topics}
【本主题已追问轮次】{turns_on_node}（满 {min_turns} 轮后可调用 advance_to_next_topic）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【操作步骤】
1. 调用 lookup_tech_node(tech_name="{current_label}") 获取节点 ID
2. 调用 graph_rag_tool 获取追问路径与提示
3. 结合候选人简历背景，提出一个口语化、有针对性的问题
4. 当本主题考察充分时（已满 {min_turns} 轮），调用 advance_to_next_topic 自然过渡

【追问原则】
- 仔细阅读上方的完整对话历史，绝对不要重复已经问过的问题或已经讨论过的话题（包括候选人已明确表示没用过的技术）
- 候选人说"不知道"或"没用过"：只说"好的，换个问题"，不解释答案，不在后续轮次再问同一技术
- 每次只问一个问题
- 考察候选人对该技术的理解深度，不要问"你的项目中怎么用"，而是问"你觉得/你理解/你认为"这类知识性问题
- 不要照搬教科书定义，问有判断性的问题，如"为什么不用X""这样做有什么代价""你觉得它的局限是什么"
- 已覆盖的技术点：{covered_labels}
{anti_simulation}"""


async def jd_tech_node(state: InterviewState) -> dict:
    phase_turn = state.get("phase_turn_count", 0)
    jd_text = state.get("jd_text", "")
    jd_summary = jd_text[:400] if jd_text else "（未提供）"

    scores = state.get("node_scores", {})
    phase_data = scores.get("jd_tech", {
        "turn_count":      0,
        "chain":           [],
        "interview_nodes": [],  # 前 MAX_INTERVIEW_NODES 个根节点
        "node_idx":        0,   # 当前根节点下标
        "turns_on_node":   0,   # 当前根节点已追问轮次
        "covered_labels":  [],
        "qa_records":      [],
    })

    # ── 首轮：构建 chain & 确定 interview_nodes ───────────────────────
    chain: list[dict] = phase_data.get("chain", [])
    if not chain and jd_text:
        chain = _build_jd_chain(jd_text)
        phase_data["chain"] = chain

    interview_nodes: list[dict] = phase_data.get("interview_nodes", [])
    if not interview_nodes and chain:
        for c in chain:
            if c.get("is_root", True) and _node_has_content(c["node_id"]):
                interview_nodes.append(c)
                if len(interview_nodes) >= MAX_INTERVIEW_NODES:
                    break
        if not interview_nodes:
            interview_nodes = [{"node_id": "", "label": "LLM应用工程", "is_root": True}]
        phase_data["interview_nodes"] = interview_nodes

    node_idx: int       = phase_data.get("node_idx", 0)
    turns_on_node: int  = phase_data.get("turns_on_node", 0)
    covered_labels: list[str] = phase_data.get("covered_labels", [])

    current = interview_nodes[min(node_idx, len(interview_nodes) - 1)]
    current_label = current["label"]

    if current_label not in covered_labels:
        covered_labels = list(covered_labels) + [current_label]

    sub_topics = _get_sub_topics(chain, current["node_id"])
    sub_topics_str = "、".join(sub_topics) if sub_topics else "（无子话题，围绕主题自由追问）"

    system = _SYSTEM.format(
        jd_summary=jd_summary,
        current_label=current_label,
        node_index=node_idx + 1,
        total_nodes=len(interview_nodes),
        sub_topics=sub_topics_str,
        turns_on_node=turns_on_node,
        min_turns=MIN_TURNS_PER_NODE,
        covered_labels=", ".join(covered_labels) if covered_labels else "无",
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    messages = get_context_window(state, system, is_new_phase=(phase_turn == 0))
    new_messages, _ = await llm_tool_loop(_llm_with_tools, messages, _ALL_TOOLS)

    # ── 检测 advance_to_next_topic 工具调用 ──────────────────────────
    wants_advance = any(
        tc.get("name") == "advance_to_next_topic"
        for msg in new_messages
        if hasattr(msg, "tool_calls") and msg.tool_calls
        for tc in msg.tool_calls
    )

    turns_on_node += 1
    phase_turn    += 1
    should_transition = False

    if wants_advance and turns_on_node >= MIN_TURNS_PER_NODE:
        if node_idx + 1 < len(interview_nodes):
            node_idx      += 1
            turns_on_node  = 0
            logger.info(f"jd_tech: advance to node {node_idx} ({interview_nodes[node_idx]['label']})")
        else:
            should_transition = True
            logger.info("jd_tech: all nodes covered, transitioning to coding_test")

    qa = build_qa_record(
        state_messages=state["messages"],
        new_messages=new_messages,
        phase="jd_tech",
        turn=phase_turn,
    )
    phase_data.setdefault("qa_records", []).append(qa)
    phase_data["turn_count"]      = phase_turn
    phase_data["chain"]           = chain
    phase_data["interview_nodes"] = interview_nodes
    phase_data["node_idx"]        = node_idx
    phase_data["turns_on_node"]   = turns_on_node
    phase_data["covered_labels"]  = covered_labels
    scores["jd_tech"] = phase_data

    going_to = "coding_test" if should_transition else "jd_tech"

    result = {
        "messages":          new_messages,
        "current_node":      going_to,
        "phase_turn_count":  0 if should_transition else phase_turn,
        "should_transition": should_transition,
        "node_scores":       scores,
    }
    if should_transition:
        result["context_summary"] = await compress_messages(state)
    return result
