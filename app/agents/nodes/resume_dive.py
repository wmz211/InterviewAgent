"""
Resume Deep Dive node — 简历经历深挖。

LLM 主导推进：当 LLM 判断简历经历已充分覆盖时，主动调用 advance_to_jd_tech 工具
触发阶段转移。保底最少 MIN_TURNS 轮，防止过早结束。
"""
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
import re

from app.agents.nodes.base import make_llm, build_qa_record, compress_messages, get_context_window, ANTI_SIMULATION_RULE
from app.agents.nodes.followup_policy import build_resume_followup_memory
from app.core.state import InterviewState

# 最少轮次保底——即使 LLM 调工具也不会提前跳走
MIN_TURNS = 3
MAX_TURNS = 8
MAX_PROJECTS_IN_PLAN = 3
MIN_CHINESE_PROJECT_MATCH = 4


def _message_text(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content or "")


def _first_human_text(state: InterviewState) -> str:
    for msg in state.get("messages", []):
        if type(msg).__name__ == "HumanMessage":
            return _message_text(msg)
    return ""


def _extract_resume_projects(resume_summary: str) -> list[str]:
    projects: list[str] = []
    for line in resume_summary.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"(?:项目|经历)\s*[:：]\s*(.+)", stripped)
        if match:
            projects.append(match.group(1).strip())
            continue
        bracket = re.search(r"【([^】]+)】", stripped)
        if bracket:
            projects.append(bracket.group(1).strip())

    seen: set[str] = set()
    unique: list[str] = []
    for project in projects:
        project = re.sub(r"\s+", " ", project).strip(" -：:")
        if project and project not in seen:
            seen.add(project)
            unique.append(project)
    return unique


def _project_intro_score(project: str, intro: str) -> int:
    if not intro:
        return 0
    normalized_project = re.sub(r"[^\w\u4e00-\u9fff]", "", project)
    normalized_intro = re.sub(r"[^\w\u4e00-\u9fff]", "", intro)
    if not normalized_project or not normalized_intro:
        return 0
    if normalized_project in normalized_intro:
        return len(normalized_project) + 10
    intro_lower = intro.lower()
    generic_words = {
        "project", "system", "platform", "app", "application", "service",
        "tool", "demo", "pipeline",
    }
    ascii_tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", project)
        if token.lower() not in generic_words and len(token) >= 2
    ]
    if ascii_tokens:
        return sum(len(token) for token in ascii_tokens if token in intro_lower)
    return _longest_common_chinese_substring_score(normalized_project, normalized_intro)


def _longest_common_chinese_substring_score(project: str, intro: str) -> int:
    longest = 0
    project_len = len(project)
    for start in range(project_len):
        for end in range(start + MIN_CHINESE_PROJECT_MATCH, project_len + 1):
            candidate = project[start:end]
            if candidate in intro:
                longest = max(longest, len(candidate))
    return longest if longest >= MIN_CHINESE_PROJECT_MATCH else 0


def _build_project_plan(state: InterviewState, phase_turn: int) -> dict:
    intro = _first_human_text(state)
    resume_projects = _extract_resume_projects(state.get("resume_summary", ""))

    scored = [
        (project, _project_intro_score(project, intro))
        for project in resume_projects
    ]
    intro_projects = [
        project
        for project, score in sorted(scored, key=lambda item: item[1], reverse=True)
        if score >= 2
    ]
    projects = intro_projects[:MAX_PROJECTS_IN_PLAN]

    if not projects and intro:
        projects = ["候选人自我介绍中提到的核心项目"]

    if len(projects) <= 1:
        planned_turns = 4
        turns_per_project = 3
    elif len(projects) == 2:
        planned_turns = 6
        turns_per_project = 3
    else:
        planned_turns = MAX_TURNS
        turns_per_project = 2

    planned_turns = min(MAX_TURNS, max(MIN_TURNS, planned_turns))
    current_turn = phase_turn + 1
    remaining_turns = max(0, MAX_TURNS - current_turn)
    current_project = ""
    if projects:
        project_idx = min(len(projects) - 1, max(0, (current_turn - 1) // turns_per_project))
        current_project = projects[project_idx]

    return {
        "intro": intro,
        "projects": projects,
        "current_project": current_project,
        "current_turn": current_turn,
        "remaining_turns": remaining_turns,
        "planned_turns": planned_turns,
        "turns_per_project": turns_per_project,
    }

_SYSTEM = """\
LOW_VALUE_FOLLOWUP_GUARD:
- Do not ask for full prompt text, exact prompt templates, long input/output examples, or implementation trivia unless it is essential to judge ownership.
- Do not ask the candidate to reveal chain-of-thought. If prompt strategy matters, ask for observable structure instead: task framing, input fields, output schema, validation rules, and fallback behavior.
- At most one clarification question about prompt strategy is allowed for the same project detail. If the candidate has already said they used ICL, CoT, structured output, or examples, do not keep asking for a concrete prompt example.
- If an answer is abstract but already identifies the method, move to design tradeoffs, evaluation, failure cases, or engineering details.
- Prefer high-signal follow-ups in this order: personal contribution, design tradeoff, measurement/evaluation, failure analysis, production constraints, then low-level implementation detail.
- If two consecutive turns stay on a low-level detail such as prompt wording, field names, or examples without adding new signal, change direction immediately.

REPEAT_AVOIDANCE_GUARD:
- Treat RESUME_DIVE_MEMORY as authoritative. Do not repeat questions, project details, threshold/metric variants, or prompt-example requests already shown there.
- When RESUME_DIVE_MEMORY marks status=CLOSED_LOW_SIGNAL, the candidate has already said they have no useful information on that line. Acknowledge briefly and switch to another project, contribution, tradeoff, failure case, or evaluation dimension.
- Do not return to an earlier project just because it is still in the recent chat window. Only return if the candidate adds new concrete information about it.

你正在对一名候选人进行技术面试，考察其简历经历的真实深度。

【候选人简历】
{resume_summary}

【岗位要求】
{jd_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【轮次规划】
当前是简历深挖第 {current_turn} 轮，最大 {max_turns} 轮，剩余 {remaining_turns} 轮。
本阶段应该围绕候选人自我介绍中主动提到的项目展开；如果候选人只提到 1 个项目，最多深挖 3-4 轮；
如果提到 2 个项目，每个项目问 2-3 个技术性问题；如果提到 3 个及以上项目，优先选择与 JD 最匹配的 2-3 个项目，每个项目约 2 轮。
不要为了问满轮次而硬问；当核心项目已经覆盖充分，或达到第 {planned_turns} 轮附近，应自然收束并推进到 JD 技术考察。

【候选人自我介绍中的项目优先级】
{intro_projects}

【当前建议聚焦项目】
{current_project}

【每个项目的追问节奏】
1. 先问候选人个人具体贡献与负责边界。
2. 再问一个核心技术选择、架构取舍、实现细节或替代方案。
3. 如轮次允许，再问评估指标、失败案例、工程兜底、复盘改进。
同一个项目连续追问达到规划轮次后，必须切换到下一个项目或收束，不要一直问一个项目。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【任务】
逐一深挖简历中与JD相匹配的项目/实习经历。

【追问优先级】
优先围绕候选人自我介绍中主动提到的项目，其次才根据简历和 JD 补问其他匹配项目/实习经历。
优先深挖与JD要求匹配度最高的经历和技术点，与JD无关的不问。
当某个方向连续两次得到浅显或无实质内容的回答时，立刻转移话题。
不要为了"追问完整"而在低价值方向继续消耗时间。
如果候选人回答和问题不匹配，最多追问一次澄清；仍然低信号时换项目或进入下一阶段。

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
- 严禁重复上一轮问题的同义改写；如果 RESUME_DIVE_MEMORY 显示同一细节已经问过，必须换维度、换项目或收束

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

RESUME_DIVE_MEMORY:
{followup_memory}

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
    project_plan = _build_project_plan(state, phase_turn)
    scores = state.get("node_scores", {})
    phase_data = scores.get("resume_dive", {
        "turn_count": 0,
        "covered": [],
        "qa_records": [],
        "followup_memory": "",
    })
    covered = phase_data.get("covered", [])
    followup_memory = build_resume_followup_memory(phase_data.get("qa_records", []))

    jd_text = state.get("jd_text", "")
    jd_summary = jd_text[:300] if jd_text else "（未提供，请根据简历内容追问）"

    system = _SYSTEM.format(
        resume_summary=state.get("resume_summary", "（简历未解析）"),
        jd_summary=jd_summary,
        current_turn=project_plan["current_turn"],
        max_turns=MAX_TURNS,
        remaining_turns=project_plan["remaining_turns"],
        planned_turns=project_plan["planned_turns"],
        intro_projects=(
            "\n".join(f"- {p}" for p in project_plan["projects"])
            if project_plan["projects"] else "（自我介绍中未识别出明确项目，围绕候选人刚才主动提到的核心经历追问）"
        ),
        current_project=project_plan["current_project"] or "（根据候选人回答动态选择）",
        covered="\n".join(f"- {c}" for c in covered) if covered else "无（这是第一轮）",
        followup_memory=followup_memory,
        anti_simulation=ANTI_SIMULATION_RULE,
    )

    messages = get_context_window(state, system)
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
    should_transition = should_transition or phase_turn >= MAX_TURNS
    should_transition = should_transition or (
        phase_turn >= project_plan["planned_turns"]
        and phase_turn >= MIN_TURNS
        and len(project_plan["projects"]) > 0
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
    phase_data["followup_memory"] = build_resume_followup_memory(phase_data["qa_records"])
    phase_data["project_plan"] = {
        "projects": project_plan["projects"],
        "planned_turns": project_plan["planned_turns"],
        "turns_per_project": project_plan["turns_per_project"],
    }
    scores["resume_dive"] = phase_data

    going_to = "jd_tech" if should_transition else "resume_dive"

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
