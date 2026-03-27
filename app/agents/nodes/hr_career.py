"""
HR Career node — 职业规划与求职动机考察。
纯 LLM，无工具。
max 轮次：2
"""
from langchain_core.messages import SystemMessage

from app.agents.nodes.base import make_llm, check_transition, build_qa_record, ANTI_SIMULATION_RULE
from app.core.state import InterviewState

_SYSTEM = """\
你是一位专业的 HR 面试官，正在考察候选人的职业规划和求职动机。

【候选人简历】
{resume_summary}

【岗位要求（JD 摘要）】
{jd_summary}

【本轮考察维度】
1. 求职动机：为什么选择这个岗位？为什么选择我们公司？
2. 职业规划：3-5 年后你希望自己处于什么阶段？
3. 对公司/岗位的了解：你对我们的业务了解多少？

【追问策略】
- 每次只问一个问题
- 追问要具体，不接受空洞回答，如"你说'希望成长'，能不能说得更具体，比如在哪个方向？"
- 考察候选人对岗位的了解程度和真实的求职动机

【候选人说"不知道"时】说"好的，那我们换一个话题"，不解释。
{anti_simulation}"""

_llm = make_llm(temperature=0.7)


async def hr_career_node(state: InterviewState) -> dict:
    jd_text = state.get("jd_text", "")
    system = _SYSTEM.format(
        resume_summary=state.get("resume_summary", "（未提供）"),
        jd_summary=jd_text[:300] if jd_text else "（未提供）",
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    response = await _llm.ainvoke([SystemMessage(content=system)] + state["messages"])
    new_messages = [response]

    phase_turn = state.get("phase_turn_count", 0) + 1
    should_transition = check_transition(
        {**state, "phase_turn_count": phase_turn}, "hr_career"
    )

    scores = state.get("node_scores", {})
    phase_data = scores.get("hr_career", {"turn_count": 0, "qa_records": []})
    qa = build_qa_record(
        state_messages=state["messages"],
        new_messages=new_messages,
        phase="hr_career",
        turn=phase_turn,
    )
    phase_data.setdefault("qa_records", []).append(qa)
    phase_data["turn_count"] = phase_turn
    scores["hr_career"] = phase_data

    going_to = "wrap_up" if should_transition else "hr_career"

    return {
        "messages": new_messages,
        "current_node": going_to,
        "phase_turn_count": 0 if should_transition else phase_turn,
        "should_transition": should_transition,
        "node_scores": scores,
    }
