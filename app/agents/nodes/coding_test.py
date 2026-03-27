"""
Coding Test node — 手撕算法题。
调用 VectorDB 算法题库，引导候选人描述思路。
"""
from langchain_core.messages import SystemMessage

from app.agents.nodes.base import make_llm, check_transition, execute_tools, llm_tool_loop, build_qa_record, ANTI_SIMULATION_RULE
from app.agents.tools.vector_search_tool import VECTOR_TOOLS
from app.core.state import InterviewState

_SYSTEM = """\
你是一位大厂算法面试官，正在考察候选人的编程与算法能力。

【当前阶段】手撕算法题
【候选人背景】
{resume_summary}

【你的任务】
1. 调用 vector_search_algorithms 工具选一道合适的算法题
   - query 参数：根据候选人背景选择相关方向，如 "动态规划" "二叉树" "字符串处理"
   - difficulty 参数：medium 起步，可根据表现调整
2. 清晰描述题目，给候选人 5-10 分钟思考
3. 引导候选人先说思路，再写代码（伪代码或Python均可）
4. 候选人给出解法后，追问时间/空间复杂度，或给出边界条件提示

【提问模板】
- "我给你出一道题，你先说说你的思路，不用急着写代码"
- "这个方案的时间复杂度是多少？有没有优化空间？"
- "如果输入是空数组或者超大数据量，你的方案还成立吗？"
{anti_simulation}"""

_llm = make_llm(temperature=0.3)
_llm_with_tools = _llm.bind_tools(VECTOR_TOOLS)


async def coding_test_node(state: InterviewState) -> dict:
    system = _SYSTEM.format(
        resume_summary=state.get("resume_summary", ""),
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    messages = [SystemMessage(content=system)] + state["messages"]
    new_messages, _ = await llm_tool_loop(_llm_with_tools, messages, VECTOR_TOOLS)

    phase_turn = state.get("phase_turn_count", 0) + 1
    should_transition = check_transition(
        {**state, "phase_turn_count": phase_turn}, "coding_test"
    )

    scores = state.get("node_scores", {})
    phase_data = scores.get("coding_test", {"turn_count": 0, "qa_records": []})

    qa = build_qa_record(
        state_messages=state["messages"],
        new_messages=new_messages,
        phase="coding_test",
        turn=phase_turn,
    )
    phase_data.setdefault("qa_records", []).append(qa)
    phase_data["turn_count"] = phase_turn
    scores["coding_test"] = phase_data

    going_to = "wrap_up" if should_transition else "coding_test"

    return {
        "messages": new_messages,
        "current_node": going_to,
        "phase_turn_count": 0 if should_transition else phase_turn,
        "should_transition": should_transition,
        "node_scores": scores,
    }
