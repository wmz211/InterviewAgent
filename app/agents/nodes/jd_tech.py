"""
JD technical interview node.

The expensive JD -> graph topic chain can be prepared before this phase starts.
When cached phase data is present, this node reuses it and only asks the next
question.
"""
import re as _re

from langchain_core.tools import tool
from loguru import logger

from app.agents.nodes.base import (
    ANTI_SIMULATION_RULE,
    build_qa_record,
    compress_messages,
    get_context_window,
    llm_tool_loop,
    make_llm,
)
from app.agents.tools.graph_search_tool import GRAPH_RAG_TOOLS
from app.core.state import InterviewState

_GLINER_LABELS = [
    "技术框架",
    "工具",
    "概念",
    "方法论",
    "技术技能",
    "AI模型",
    "系统组件",
    "技术术语",
    "开发工具",
    "算法",
]

MIN_TURNS_PER_NODE = 2
MAX_TURNS_PER_NODE = 3
MAX_INTERVIEW_NODES = 3


def _extract_entities(jd_text: str) -> list[str]:
    """Extract technical entity terms from JD text."""
    try:
        from app.rag.graph_rag.knowledge_base import _get_gliner

        model = _get_gliner()
        if model:
            entities = model.predict_entities(jd_text, labels=_GLINER_LABELS)
            terms = list(
                dict.fromkeys(e["text"] for e in entities if 1 < len(e["text"]) < 20)
            )
            if terms:
                logger.debug(f"GLiNER extracted {len(terms)} entities: {terms[:10]}")
                return terms
    except Exception as e:
        logger.warning(f"GLiNER extraction failed: {e}")

    terms = _re.findall(r"[A-Za-z][A-Za-z0-9.+#_-]{2,}", jd_text)
    return list(dict.fromkeys(terms))[:20]


def _node_has_content(node_id: str) -> bool:
    """Return whether a graph node has follow-up material."""
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
    Call this when the current JD technical topic has been covered enough and
    the interview should move to the next topic or next phase.
    """
    return "ok"


_ALL_TOOLS = GRAPH_RAG_TOOLS + [advance_to_next_topic]
_llm = make_llm(temperature=0.5)
_llm_with_tools = _llm.bind_tools(_ALL_TOOLS)


def _build_jd_chain(jd_text: str) -> list[dict]:
    """
    Build a JD-driven graph chain:
    GLiNER terms -> BM25/vector retrieval -> RRF -> LEADS_TO expansion.
    """
    from app.rag.graph_rag.knowledge_base import get_knowledge_graph, rrf_merge

    kg = get_knowledge_graph()
    terms = _extract_entities(jd_text)
    logger.info(f"JD entity terms: {terms}")

    bm25_rankings = kg.bm25_search(terms, top_k=5) if terms else []
    vector_rankings = kg.vector_search(terms, top_k=5) if terms else []

    if not bm25_rankings and not vector_rankings:
        logger.warning("BM25 and vector both empty; fallback to Lucene fulltext")
        seen: set[str] = set()
        fallback: dict[str, int] = {}
        for term in terms[:20]:
            for candidate in kg.fulltext_search(term, top_k=2):
                node_id = candidate["node_id"]
                if node_id not in seen:
                    fallback[node_id] = fallback.get(node_id, 0) + 1
                    seen.add(node_id)
        bm25_rankings = [sorted(fallback, key=lambda x: -fallback[x])]

    active_rankings = [ranking for ranking in bm25_rankings + vector_rankings if ranking]
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
            step_id = step["node_id"]
            if step_id not in seen_ids:
                chain.append(
                    {"node_id": step_id, "label": step["label"], "is_root": False}
                )
                seen_ids.add(step_id)

    logger.info(f"JD chain built: {[item['label'] for item in chain]}")
    return chain


def _get_sub_topics(chain: list[dict], root_node_id: str) -> list[str]:
    sub_topics: list[str] = []
    found = False
    for item in chain:
        if item["node_id"] == root_node_id:
            found = True
            continue
        if found:
            if item.get("is_root", True):
                break
            sub_topics.append(item["label"])
    return sub_topics


def prepare_jd_tech_phase_data(jd_text: str, phase_data: dict | None = None) -> dict:
    """Prepare and cache JD technical phase data."""
    data = dict(phase_data or {})
    data.setdefault("turn_count", 0)
    data.setdefault("chain", [])
    data.setdefault("interview_nodes", [])
    data.setdefault("node_idx", 0)
    data.setdefault("turns_on_node", 0)
    data.setdefault("covered_labels", [])
    data.setdefault("qa_records", [])

    chain: list[dict] = data.get("chain", [])
    if not chain and jd_text:
        chain = _build_jd_chain(jd_text)
        data["chain"] = chain

    interview_nodes: list[dict] = data.get("interview_nodes", [])
    if not interview_nodes and chain:
        for item in chain:
            if item.get("is_root", True) and _node_has_content(item["node_id"]):
                interview_nodes.append(item)
                if len(interview_nodes) >= MAX_INTERVIEW_NODES:
                    break
        if not interview_nodes:
            interview_nodes = [{"node_id": "", "label": "LLM应用工程", "is_root": True}]
        data["interview_nodes"] = interview_nodes

    return data


_SYSTEM = """\
LOW_VALUE_FOLLOWUP_GUARD:
- Do not ask for full prompt text, exact prompt templates, long input/output examples, or implementation trivia unless it is essential to judge ownership.
- Do not ask the candidate to reveal chain-of-thought. Ask for observable structure instead: task framing, input fields, output schema, validation rules, and fallback behavior.
- If an answer is abstract but already identifies the method, move to design tradeoffs, evaluation, failure cases, or engineering details.

你是一位技术面试官，正在按照岗位要求考察候选人的技术深度。

【岗位要求摘要】
{jd_summary}

【当前考察主题】{current_label}（第 {node_index}/{total_nodes} 个主题）
【相关子话题】{sub_topics}
【本主题已追问轮次】{turns_on_node}（满 {min_turns} 轮后可调用 advance_to_next_topic）

【操作步骤】
1. 调用 lookup_tech_node(tech_name="{current_label}") 获取节点 ID。
2. 调用 graph_rag_tool 获取追问路径与提示。
3. 结合候选人简历背景，提出一个口语化、有针对性的问题。
4. 当本主题考察充分时，调用 advance_to_next_topic 自然过渡。

【追问原则】
- 不要重复已经问过的问题或已经讨论过的话题。
- 候选人说不知道或没用过：只说“好的，换个问题”，不解释答案。
- 每次只问一个问题。
- 已覆盖的技术点：{covered_labels}
{anti_simulation}"""


async def jd_tech_node(state: InterviewState) -> dict:
    phase_turn = state.get("phase_turn_count", 0)
    jd_text = state.get("jd_text", "")
    jd_summary = jd_text[:400] if jd_text else "（未提供）"

    scores = state.get("node_scores", {})
    phase_data = prepare_jd_tech_phase_data(jd_text, scores.get("jd_tech", {}))
    chain: list[dict] = phase_data.get("chain", [])
    interview_nodes: list[dict] = phase_data.get("interview_nodes", [])

    node_idx: int = phase_data.get("node_idx", 0)
    turns_on_node: int = phase_data.get("turns_on_node", 0)
    covered_labels: list[str] = phase_data.get("covered_labels", [])
    if phase_data.get("message_start_index") is None:
        phase_data["message_start_index"] = len(state.get("messages", []))

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

    phase_messages = state.get("messages", [])[phase_data["message_start_index"] :]
    isolated_state = {**state, "messages": phase_messages, "context_summary": ""}
    messages = get_context_window(isolated_state, system, is_new_phase=(phase_turn == 0))
    new_messages, _ = await llm_tool_loop(_llm_with_tools, messages, _ALL_TOOLS)

    wants_advance = any(
        tool_call.get("name") == "advance_to_next_topic"
        for msg in new_messages
        if hasattr(msg, "tool_calls") and msg.tool_calls
        for tool_call in msg.tool_calls
    )

    turns_on_node += 1
    phase_turn += 1
    should_transition = False
    force_advance = turns_on_node >= MAX_TURNS_PER_NODE
    advance_reason = ""

    if (wants_advance and turns_on_node >= MIN_TURNS_PER_NODE) or force_advance:
        advance_reason = "llm_tool" if wants_advance else "max_turns_fallback"
        if node_idx + 1 < len(interview_nodes):
            node_idx += 1
            turns_on_node = 0
            logger.info(
                f"jd_tech: advance to node {node_idx} "
                f"({interview_nodes[node_idx]['label']}), reason={advance_reason}"
            )
        else:
            should_transition = True
            logger.info(
                "jd_tech: all nodes covered, transitioning to coding_test, "
                f"reason={advance_reason}"
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
    phase_data["interview_nodes"] = interview_nodes
    phase_data["node_idx"] = node_idx
    phase_data["turns_on_node"] = turns_on_node
    phase_data["covered_labels"] = covered_labels
    phase_data["last_advance_reason"] = advance_reason
    scores["jd_tech"] = phase_data

    going_to = "coding_test" if should_transition else "jd_tech"
    result = {
        "messages": new_messages,
        "current_node": going_to,
        "phase_turn_count": 0 if should_transition else phase_turn,
        "should_transition": should_transition,
        "node_scores": scores,
    }
    if should_transition:
        result["context_summary"] = await compress_messages(state)
    return result
