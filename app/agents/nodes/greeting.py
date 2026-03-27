"""
Greeting node — 开场破冰，收集自我介绍，提取候选人姓名。
无工具调用，纯对话。
"""
from langchain_core.messages import SystemMessage

from app.agents.nodes.base import make_llm, check_transition, ANTI_SIMULATION_RULE
from app.core.state import InterviewState

_SYSTEM_FIRST = """\
你是一位专业、严谨的技术面试官，正在进行一场真实的技术面试。

【当前阶段】开场与自我介绍 — 第一轮（候选人尚未发言）

【本轮任务】
- 热情但简洁地欢迎候选人，做一句话自我介绍
- 邀请候选人做3-5分钟自我介绍，重点介绍技术背景和项目经验
- 说完之后立即停止，等待候选人回应

【严格禁止】
- 不要模拟候选人的回答
- 不要生成"（等待候选人...）""---"之类的占位文字
- 不要在候选人发言前就给出"感谢你的介绍"类的回应
- 只输出面试官这一侧的话，一轮结束即停

候选人简历摘要：
{resume_summary}
"""

_SYSTEM_FOLLOWUP = """\
你是一位专业、严谨的技术面试官，正在进行一场真实的技术面试。

【当前阶段】开场与自我介绍 — 候选人已完成自我介绍

【本轮任务】
- 用2-3句简短正面回应候选人的自我介绍
- 从中提炼1-2个你感兴趣的项目点或经历，点名道姓地提及
- 用一句话自然衔接，表示接下来将针对这些方向深入了解
- 语气专业，略带审视感，让候选人感受到真实面试的紧张氛围

【严格禁止】
- 不要模拟候选人的回答或生成占位文字
- 只输出面试官这一侧的话，一轮结束即停
- 不要直接跳到技术细节问题

候选人简历摘要：
{resume_summary}
"""

_llm = make_llm(temperature=0.7)


async def greeting_node(state: InterviewState) -> dict:
    # Pick system prompt based on whether the candidate has already spoken
    has_human_msg = any(
        type(m).__name__ == "HumanMessage" for m in state.get("messages", [])
    )
    template = _SYSTEM_FOLLOWUP if has_human_msg else _SYSTEM_FIRST
    system = template.format(
        resume_summary=state.get("resume_summary", "（简历待解析）"),
    ) + ANTI_SIMULATION_RULE

    response = await _llm.ainvoke(
        [SystemMessage(content=system)] + state["messages"]
    )

    phase_turn = state.get("phase_turn_count", 0) + 1
    should_transition = check_transition(
        {**state, "phase_turn_count": phase_turn}, "greeting"
    )

    # Try to extract candidate name from messages
    candidate_name = state.get("candidate_name", "")
    if not candidate_name and len(state["messages"]) > 0:
        for msg in state["messages"]:
            if hasattr(msg, "content") and "我叫" in msg.content:
                # Very simple extraction — LLM will handle better in practice
                candidate_name = msg.content.split("我叫")[-1].split()[0][:10]
                break

    scores = state.get("node_scores", {})
    scores["greeting"] = {"turn_count": phase_turn}

    # On transition: route to first phase of the selected interview track
    mode = state.get("interview_mode", "tech")
    next_phase = "resume_dive" if mode == "tech" else "hr_self_intro"
    going_to = next_phase if should_transition else "greeting"

    return {
        "messages": [response],
        "current_node": going_to,
        "phase_turn_count": 0 if should_transition else phase_turn,
        "should_transition": should_transition,
        "candidate_name": candidate_name or state.get("candidate_name", ""),
        "node_scores": scores,
    }
