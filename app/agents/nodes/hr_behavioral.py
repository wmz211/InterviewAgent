"""
HR Behavioral node — 行为面试，STAR 法则追问。
使用 VectorDB 检索 HR 行为题，确保不重复。
每道题追问 STAR 四个维度的完整性。
max 轮次：4
"""
from langchain_core.messages import SystemMessage

from app.agents.nodes.base import make_llm, check_transition, llm_tool_loop, build_qa_record, compress_messages, get_context_window, ANTI_SIMULATION_RULE
from app.core.state import InterviewState

_SYSTEM = """\
你是一位专业的 HR 面试官，正在用 STAR 法则进行行为面试。

【候选人简历】
{resume_summary}

【本轮任务】
1. 调用 vector_search_hr_questions 工具，检索一道还没问过的行为面试题
   - asked_ids 参数传入 {asked_ids}
2. 以自然口语化的方式抛出这道行为题
3. 候选人回答后，评估 STAR 要素的完整性：
   - Situation（背景）、Task（任务）、Action（行动）、Result（结果）
   - 缺失哪个维度就追问哪个："那最终结果怎么样？" / "你具体采取了哪些行动？"
4. 每轮只问一个问题，等候选人回答后再追问

【候选人说"不知道"时】直接说"好的，我换一个问题"，不解释。
{anti_simulation}"""

_llm = make_llm(temperature=0.6)


async def hr_behavioral_node(state: InterviewState) -> dict:
    from app.agents.tools.hr_search_tool import HR_TOOLS
    _llm_with_tools = _llm.bind_tools(HR_TOOLS)

    phase_turn = state.get("phase_turn_count", 0)
    scores = state.get("node_scores", {})
    phase_data = scores.get("hr_behavioral", {
        "turn_count": 0,
        "asked_ids": [],
        "qa_records": [],
    })
    asked_ids = phase_data.get("asked_ids", [])

    system = _SYSTEM.format(
        resume_summary=state.get("resume_summary", "（未提供）"),
        asked_ids=asked_ids if asked_ids else "[]（第一题，无限制）",
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    messages = get_context_window(state, system)
    new_messages, _ = await llm_tool_loop(_llm_with_tools, messages, HR_TOOLS)

    # 从 ToolMessage 中提取已问的题目 ID
    for msg in new_messages:
        if type(msg).__name__ == "ToolMessage":
            import json
            try:
                result = json.loads(msg.content)
                if isinstance(result, dict) and result.get("id"):
                    qid = result["id"]
                    if qid not in asked_ids:
                        asked_ids = list(asked_ids) + [qid]
            except Exception:
                pass

    phase_turn += 1
    should_transition = check_transition(
        {**state, "phase_turn_count": phase_turn}, "hr_behavioral"
    )

    qa = build_qa_record(
        state_messages=state["messages"],
        new_messages=new_messages,
        phase="hr_behavioral",
        turn=phase_turn,
    )
    phase_data.setdefault("qa_records", []).append(qa)
    phase_data["turn_count"] = phase_turn
    phase_data["asked_ids"] = asked_ids
    scores["hr_behavioral"] = phase_data

    going_to = "hr_career" if should_transition else "hr_behavioral"

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
