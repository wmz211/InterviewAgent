"""
Resume Deep Dive node — 简历经历深挖。
纯 LLM，无工具调用。将简历全文注入 system prompt，专注追问候选人的亲身经历。

追问框架（三层递进）：
  L1 — 你具体做了什么？（描述工作内容）
  L2 — 你为什么这样做？有没有对比过其他方案？（考察判断力）
  L3 — 遇到了什么问题？怎么解决的？有什么遗憾？（考察深度与反思）

注意：此阶段只追问候选人的项目/实习/经历，不考察通用技术理论。
"""
from langchain_core.messages import SystemMessage

from app.agents.nodes.base import make_llm, check_transition, build_qa_record, ANTI_SIMULATION_RULE
from app.core.state import InterviewState

_SYSTEM = """\
你是一位经验丰富的技术面试官，正在对候选人进行简历经历深挖。

【候选人简历】
{resume_summary}

【岗位要求（JD 摘要）】
{jd_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【你的核心任务】
逐一针对简历中的项目/实习经历进行追问，考察候选人的实际参与深度。
每个经历按三层递进追问（仅作为你内部的提问框架，不要在问题中出现"L1/L2/L3"或"第X次"等标签）：
  第一层：你在这个项目里具体负责了什么？做了哪些工作？
  第二层：你为什么选择这个技术方案？有没有考虑过其他方案？
  第三层：过程中遇到了什么挑战或问题？你是怎么解决的？

【重要原则】
- 只追问候选人简历里真实写的内容，不考察通用知识点
- 候选人说"不知道"时，直接说"好的，我们换个话题"，绝不解释答案
- 候选人回答浅显时，追问"能更具体吗？比如..."
- 不要一次问多个问题
- 第一轮先问一个宏观问题暖场，然后聚焦到具体经历

【当前已覆盖的经历】
{covered}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{anti_simulation}"""

_llm = make_llm(temperature=0.7)


async def resume_dive_node(state: InterviewState) -> dict:
    phase_turn = state.get("phase_turn_count", 0)
    scores = state.get("node_scores", {})
    phase_data = scores.get("resume_dive", {
        "turn_count": 0,
        "covered": [],
        "qa_records": [],
    })
    covered = phase_data.get("covered", [])

    jd_text = state.get("jd_text", "")
    jd_summary = jd_text[:300] if jd_text else "（未提供，请根据简历内容追问）"

    system = _SYSTEM.format(
        resume_summary=state.get("resume_summary", "（简历未解析）"),
        jd_summary=jd_summary,
        covered="\n".join(f"- {c}" for c in covered) if covered else "无（这是第一轮）",
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    messages = [SystemMessage(content=system)] + state["messages"]
    response = await _llm.ainvoke(messages)
    new_messages = [response]

    # 记录本轮新问题（用于 covered 追踪）
    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    new_question = str(content).strip()[:120]

    if new_question:
        covered = list(covered) + [f"第{phase_turn + 1}轮：{new_question}"]

    phase_turn += 1
    should_transition = check_transition(
        {**state, "phase_turn_count": phase_turn}, "resume_dive"
    )

    qa = build_qa_record(
        state_messages=state["messages"],
        new_messages=new_messages,
        phase="resume_dive",
        turn=phase_turn,
    )
    phase_data.setdefault("qa_records", []).append(qa)
    phase_data["turn_count"] = phase_turn
    phase_data["covered"] = covered
    scores["resume_dive"] = phase_data

    going_to = "jd_tech" if should_transition else "resume_dive"

    return {
        "messages": new_messages,
        "current_node": going_to,
        "phase_turn_count": 0 if should_transition else phase_turn,
        "should_transition": should_transition,
        "node_scores": scores,
    }
