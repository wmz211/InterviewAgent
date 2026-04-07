"""
HR Self-Intro node — 自我介绍与开放性追问。
纯 LLM，无工具。将简历全文注入，请候选人做自我介绍，然后追问 1 个开放问题。
max 轮次：2
"""
from langchain_core.messages import SystemMessage

from app.agents.nodes.base import make_llm, check_transition, build_qa_record, compress_messages, get_context_window, ANTI_SIMULATION_RULE
from app.core.state import InterviewState

_SYSTEM_FIRST = """\
你是一位专业的 HR 面试官，正在进行一场真实的 HR 面试。

【候选人简历】
{resume_summary}

【本轮任务】
- 热情但简洁地欢迎候选人，做一句话自我介绍
- 邀请候选人用 3-5 分钟做自我介绍，重点介绍求职动机和个人亮点
- 说完立即停止，等待候选人回应

【禁止】不要模拟候选人的回答，不要提前评价，只输出面试官这一侧的话。
{anti_simulation}"""

_SYSTEM_FOLLOWUP = """\
你是一位专业的 HR 面试官，候选人刚刚完成了自我介绍。

【候选人简历】
{resume_summary}

【本轮任务】
- 用 1-2 句正面回应候选人的自我介绍，提及其中 1 个具体亮点
- 提出 1 个开放性问题，例如："你提到了 XX 项目，让你印象最深的是什么？"
- 问完立即停止

【禁止】不要模拟候选人的回答，只输出面试官这一侧的话。
{anti_simulation}"""

_llm = make_llm(temperature=0.7)


async def hr_self_intro_node(state: InterviewState) -> dict:
    has_human = any(type(m).__name__ == "HumanMessage" for m in state.get("messages", []))
    template = _SYSTEM_FOLLOWUP if has_human else _SYSTEM_FIRST
    system = template.format(
        resume_summary=state.get("resume_summary", "（未提供）"),
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    response = await _llm.ainvoke(get_context_window(state, system))
    new_messages = [response]

    phase_turn = state.get("phase_turn_count", 0) + 1
    should_transition = check_transition(
        {**state, "phase_turn_count": phase_turn}, "hr_self_intro"
    )

    scores = state.get("node_scores", {})
    phase_data = scores.get("hr_self_intro", {"turn_count": 0, "qa_records": []})
    qa = build_qa_record(
        state_messages=state["messages"],
        new_messages=new_messages,
        phase="hr_self_intro",
        turn=phase_turn,
    )
    phase_data.setdefault("qa_records", []).append(qa)
    phase_data["turn_count"] = phase_turn
    scores["hr_self_intro"] = phase_data

    going_to = "hr_behavioral" if should_transition else "hr_self_intro"

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
