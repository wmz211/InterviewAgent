"""
Resume Deep Dive node — 简历经历深挖。

LLM 主导推进：当 LLM 判断简历经历已充分覆盖时，主动调用 advance_to_jd_tech 工具
触发阶段转移。保底最少 MIN_TURNS 轮，防止过早结束。
"""
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

from app.agents.nodes.base import make_llm, build_qa_record, ANTI_SIMULATION_RULE
from app.core.state import InterviewState

# 最少轮次保底——即使 LLM 调工具也不会提前跳走
MIN_TURNS = 3

_SYSTEM = """\
你正在对一名候选人进行技术面试，考察其简历经历的真实深度。

【候选人简历】
{resume_summary}

【岗位要求】
{jd_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【任务】
逐一深挖简历中与JD相匹配的项目/实习经历。

【追问优先级】
优先深挖与JD要求匹配度最高的经历和技术点，与JD无关的不问。
当某个方向连续两次得到浅显或无实质内容的回答时，立刻转移话题。
不要为了"追问完整"而在低价值方向继续消耗时间。

【追问框架】
不要线性走固定流程。根据候选人的回答实时判断下一个问题：

当回答中出现以下信号时，优先处理：
- 出现"我们"/"参与了"/"负责过"等模糊表述 → 立刻追问：你个人具体做了什么？
- 出现技术选型（"用了X"） → 追问：为什么不用Y？当时有没有对比过？
- 出现结果/数据（"提升了X%"） → 追问：baseline是什么？怎么测量的？
- 回答流畅完整，无明显漏洞 → 推进到下一层：这个方案有什么局限性？你现在回头看会怎么改？
- 回答表面正确但缺乏细节 → 追问：能更具体吗？比如你当时怎么做的？

【开场规则】
第一个问题：让候选人做简短自我介绍。
第二个问题起：立刻聚焦到简历中技术含量最高或描述最模糊的那个经历，不要按简历顺序线性推进。

【硬性规则】
- 只追问简历里写的内容，不考察通用知识点
- 每次只问一个问题
- 候选人说"不知道"或明显答不上来：直接说"好，我们换一个"，不解释，不给答案
- 不用"感谢你的回答""你说得很好"等客套话
- 不要说"作为面试官"或解释自己的行为，直接提问

【语气】
简洁、直接。过渡用短句，如"好的""明白了""这里我想深入一下"。
适当表达疑问，如"这个我有点疑问""这里想确认一下"。
不友好也不敌对，保持专业的审视感。

【推进规则】
当你认为已经充分评估了候选人的简历经历深度（至少覆盖了简历中最重要的 1-2 个经历，
每个经历追问了不止一层，候选人的真实参与深度已基本判断清楚），
调用 advance_to_jd_tech 工具推进到下一阶段。
宁可多问一轮，不要急着推进。


【已覆盖的经历】
{covered}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
你就是面试官，现在开始面试。不要介绍自己的规则，直接开口。
{anti_simulation}"""


@tool
def advance_to_jd_tech() -> str:
    """
    调用此工具表示简历深挖阶段已完成，推进到 JD 技术考察阶段。

    调用时机：
    - 已覆盖简历中最重要的 1-2 个经历
    - 每个经历至少追问了 2-3 层（参与内容 → 技术决策 → 挑战/反思）
    - 候选人的真实参与深度已基本评估完毕

    调用时，在同一条消息里自然地说一句过渡语（如"好，简历这部分我们先聊到这里，接下来..."），
    不要暴露"工具"或"阶段"等词。
    """
    return "ok"


_RESUME_DIVE_TOOLS = [advance_to_jd_tech]
_llm = make_llm(temperature=0.7)
_llm_with_tool = _llm.bind_tools(_RESUME_DIVE_TOOLS)


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
    response = await _llm_with_tool.ainvoke(messages)
    new_messages = [response]

    # 记录本轮新问题（用于 covered 追踪）
    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    new_question = str(content).strip()[:120]
    if new_question:
        covered = list(covered) + [f"第{phase_turn + 1}轮：{new_question}"]

    phase_turn += 1

    # LLM 主动决定推进：检测 advance_to_jd_tech tool call
    tool_calls = getattr(response, "tool_calls", None) or []
    llm_wants_transition = any(
        tc.get("name") == "advance_to_jd_tech" for tc in tool_calls
    )
    # 最少轮次保底，防止 LLM 过早跳走
    should_transition = llm_wants_transition and phase_turn >= MIN_TURNS

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
