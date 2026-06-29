from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from langchain_core.messages import HumanMessage
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.core.interview_graph import get_interview_graph, make_initial_state
from app.rag.graph_rag.knowledge_base import get_knowledge_graph


RESUME = """
姓名：王明哲
背景：苏州大学软件工程，大模型应用、Agent、NLP 方向。
自我介绍中主动提到的项目：
1. 新闻文本幻觉检测与事件事实性识别研究：ICL、CoT、双路径检索、动态权重融合、F1 评估。
2. InterviewAgent AI 模拟面试系统：LangGraph 多阶段工作流、Neo4j GraphRAG、FastAPI、JWT、Redis/SQLite、ChromaDB 题库。
3. CodingAgent 复刻：学习 Claude Code 源码思路，复刻一个命令行 Coding Agent。

简历中还有但自我介绍没有主动展开的项目：
项目：基于全局上下文的知识图谱逻辑查询推理
- DFS/BFS 双路序列化、BERT 指令-上下文融合。
"""

JD = """
岗位：大模型应用 / Agent 工程实习生。
要求：熟悉 Python、FastAPI、LangGraph/LangChain、RAG、Neo4j、ChromaDB、Redis、工具调用、流式输出、Agent 评估和工程化部署。
"""


ANSWERS = {
    "greeting": [
        "面试官你好，我叫王明哲，目前就读于苏州大学软件工程。我的核心方向是大模型应用和 Agent 工程化。我主要做过新闻文本幻觉检测、基于 LangGraph 的 AI 模拟面试系统，以及一个 CodingAgent 复刻项目。",
    ],
    "resume_dive": [
        "新闻幻觉检测项目里，我负责整体流程。忠实性幻觉用全局输入和局部分解句子，让模型找出原文中互相矛盾的句子；事实性幻觉走双路径，一路是搜索证据和 embedding 相似度，另一路是 Qwen 联网判断，最后动态加权融合。",
        "ICL 示例主要由人工语言专家书写，我负责把任务拆成可执行的 Prompt 结构。CoT 不是要求模型暴露隐藏推理，而是让它按可观察步骤输出：抽取关键事实、检索证据、对齐证据、给出标签和置信度。",
        "动态权重是通过开发集调出来的。Qwen 路径越确定，权重越高；两路最终融合成一个真实性分数，再和阈值比较。评估主要看 F1，同时记录每一步检索证据和模型判断日志来定位问题。",
        "InterviewAgent 项目是我独立设计的。核心是用 LangGraph 把面试拆成 greeting、resume_dive、jd_tech、coding_test、wrap_up 等阶段，每个阶段只返回局部 state update，便于控制状态流转。",
        "GraphRAG 这块我用 Neo4j 存技术节点和 LEADS_TO、HAS_COMPONENT、HAS_PITFALL 等关系。JD 阶段先抽实体，再做 BM25 和向量检索，用 RRF 融合，最后沿图谱关系生成追问链。",
    ],
    "jd_tech": [
        "ReAct 可以理解为规划、行动、观察的循环。Thought 用来规划下一步，Action 调工具，Observation 接收工具结果。工程上我不会让它无限循环，会设置最大工具迭代次数和失败兜底。",
        "LLM 通过工具名、描述、参数 schema、使用场景和禁止使用场景来选择工具。schema 里应该写清楚参数类型、含义、边界条件，以及什么时候应该调用这个工具。",
        "短期记忆是当前对话窗口和当前阶段状态，长期记忆可以是用户偏好、反复提到的信息和历史项目资料。我的做法是结构化保存必要状态，长上下文时做摘要压缩。",
        "RAG 里纯向量检索的问题是容易召回语义相似但关键实体不精确的内容。BM25 适合精确术语，向量适合语义召回，RRF 可以融合排名而不用比较不同分数尺度。",
        "GraphRAG 的价值是让追问有层次。比如命中 RAG 后，可以沿图谱继续问向量检索、混合检索、重排、幻觉风险和评估指标，而不是只问一个孤立概念。",
        "如果工具调用失败，我会做超时、有限重试、改写 query、fallback 和日志记录。多次结果一致或达到 max_turns 就停止，避免 Agent 无限重试。",
        "生产化上我会监控 phase、node_idx、turns_on_node、LLM latency、retrieval latency、token cost、tool failure rate 和 report JSON parse success rate。",
        "Redis 应该做热缓存而不是唯一存储。session 元数据、transcript 和 report 应该进 SQL，Redis 用 TTL 管理活跃状态，进程重启后还能从数据库恢复。",
        "FastAPI 高并发下要注意异步 I/O、请求超时、限流、上传大小限制和外部服务熔断。涉及同一个 session 的修改还要考虑串行化或版本检查。",
    ],
    "coding_test": [
        "这题我会用滑动窗口。维护 left 指针和一个 char_idx 字典，记录字符最近出现的位置。right 向右扩张，如果当前字符上次出现位置在窗口内，就把 left 移到上次位置加一。",
        "每一步更新 char_idx[c] = right，并用 right - left + 1 更新最大长度。时间复杂度 O(n)，空间复杂度 O(min(n, 字符集大小))。",
        "空字符串返回 0，单字符返回 1。遇到重复字符时，left 只能向右移动，不能回退，所以要判断 char_idx[c] >= left 再更新 left。",
    ],
    "wrap_up": [
        "我没有更多问题了，谢谢面试官。",
    ],
}

FALLBACK = "这个问题我会从目标、实现、失败情况和评估指标四个方面回答。"


def text_of(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content or "")


def last_ai(messages: list) -> str:
    for msg in reversed(messages):
        if type(msg).__name__ == "AIMessage" and not getattr(msg, "tool_calls", None):
            return text_of(msg).strip()
    return ""


def tool_names(messages: list) -> list[str]:
    names: list[str] = []
    for msg in messages:
        for tool_call in getattr(msg, "tool_calls", None) or []:
            names.append(tool_call.get("name", ""))
    return names


async def main() -> None:
    settings = get_settings()
    print(f"ENV graph_backend={settings.graph_backend} uri={settings.neo4j_uri} db={settings.neo4j_database}")

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    driver.verify_connectivity()
    records, _, _ = driver.execute_query("MATCH (n) RETURN count(n) AS c", database_=settings.neo4j_database)
    print(f"NEO4J nodes={records[0]['c']}")
    driver.close()
    print(f"KG_CLASS {type(get_knowledge_graph()).__name__}")

    graph = get_interview_graph()
    state = make_initial_state(str(uuid.uuid4()), RESUME, JD, interview_mode="tech")
    used = {phase: 0 for phase in ANSWERS}
    rows: list[dict] = []

    result = await graph.ainvoke(state)
    state.update(result)
    rows.append({
        "turn": 0,
        "phase_in": "start",
        "candidate": "",
        "interviewer": last_ai(result.get("messages", [])),
        "state": dict(state),
        "tools": tool_names(result.get("messages", [])),
    })

    for turn in range(1, 26):
        phase = state.get("current_node", "greeting")
        phase_answers = ANSWERS.get(phase, [])
        idx = used.get(phase, 0)
        candidate = phase_answers[idx] if idx < len(phase_answers) else FALLBACK
        used[phase] = idx + 1

        state["messages"] = list(state.get("messages", [])) + [HumanMessage(content=candidate)]
        result = await graph.ainvoke(state)
        state.update(result)

        rows.append({
            "turn": turn,
            "phase_in": phase,
            "candidate": candidate,
            "interviewer": last_ai(result.get("messages", [])),
            "state": dict(state),
            "tools": tool_names(result.get("messages", [])),
        })
        if state.get("interview_complete"):
            break

    print("\n=== DIALOGUE ===")
    for row in rows:
        st = row["state"]
        jd = st.get("node_scores", {}).get("jd_tech", {})
        print(
            f"\nTURN {row['turn']:02d} | phase_in={row['phase_in']} | "
            f"node={st.get('current_node')} | phase_turn={st.get('phase_turn_count')} | "
            f"transition={st.get('should_transition')} | complete={st.get('interview_complete')} | "
            f"tools={row['tools']} | jd_idx={jd.get('node_idx')} | "
            f"turns_on_node={jd.get('turns_on_node')} | reason={jd.get('last_advance_reason')}"
        )
        if row["candidate"]:
            print(f"CANDIDATE: {row['candidate']}")
        print(f"INTERVIEWER: {row['interviewer']}")

    print("\n=== SUMMARY ===")
    print(
        f"current_node={state.get('current_node')} phase_turn={state.get('phase_turn_count')} "
        f"should_transition={state.get('should_transition')} complete={state.get('interview_complete')}"
    )
    for phase, data in state.get("node_scores", {}).items():
        if isinstance(data, dict):
            print(
                f"{phase}: turn_count={data.get('turn_count')} "
                f"qa_records={len(data.get('qa_records', []))} "
                f"node_idx={data.get('node_idx')} turns_on_node={data.get('turns_on_node')} "
                f"reason={data.get('last_advance_reason')}"
            )
    evaluation = state.get("node_scores", {}).get("evaluation", {})
    if evaluation:
        print(
            f"evaluation overall={evaluation.get('overall_score')} "
            f"recommendation={evaluation.get('recommendation')} weak_count={evaluation.get('weak_count')}"
        )


if __name__ == "__main__":
    asyncio.run(main())
