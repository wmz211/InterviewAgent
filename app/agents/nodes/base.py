"""
Shared utilities for all interview phase nodes.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.core.state import InterviewState

settings = get_settings()

# ── Phase turn thresholds (min turns before transition is allowed) ─────
PHASE_MIN_TURNS = {
    # Tech track
    "greeting":         2,
    "resume_dive":      4,
    "jd_tech":          6,
    "coding_test":      3,
    "wrap_up":          1,
    # HR track
    "hr_self_intro":    2,
    "hr_behavioral":    4,
    "hr_career":        2,
}

PHASE_ORDER = ["greeting", "resume_dive", "jd_tech", "coding_test", "wrap_up"]


# Appended to every node's system prompt to prevent the LLM from
# simulating user responses or generating placeholder text.
ANTI_SIMULATION_RULE = """
【通用约束 — 所有阶段必须遵守】
- 你只扮演面试官，每次只输出面试官这一侧的一轮对话
- 严禁模拟或代替候选人回答，严禁生成"（等待...）""---""候选人："之类的占位或剧本格式
- 每次输出后立即停止，等待候选人的真实回应
- 每轮只问一个问题，不要一次堆砌多个问题
- 你的所有分析、判断、评估只在内部进行，绝对不能出现在回复里
- 回复只包含你要问的那一个问题，不附加任何总结、标签、评分或内部备注
- 不要输出任何 Markdown 格式（加粗、列表、标题等）
"""


# 关键词预筛：命中后才调 LLM，正常对话零开销
_EXIT_KEYWORDS = ["结束", "不想答", "不想继续", "跳过所有", "退出", "终止面试", "结束面试", "不想面了", "放弃"]

# 不触发退出检测的阶段（已经在收尾或刚开始）
_NO_EXIT_PHASES = {"greeting", "wrap_up"}


async def detect_exit_intent(state: InterviewState) -> bool:
    """
    判断用户最新消息是否表达了提前结束面试的意图。
    先做关键词预筛，命中后再用 LLM 做语义确认，避免每轮额外 LLM 开销。
    """
    current_node = state.get("current_node", "greeting")
    if current_node in _NO_EXIT_PHASES:
        return False

    messages = state.get("messages", [])
    if not messages:
        return False

    # 取最新一条 HumanMessage
    user_text = ""
    for msg in reversed(messages):
        if type(msg).__name__ == "HumanMessage":
            user_text = getattr(msg, "content", "")
            break
    if not user_text:
        return False

    # 关键词预筛：无命中直接返回，不调 LLM
    if not any(kw in user_text for kw in _EXIT_KEYWORDS):
        return False

    # LLM 语义确认，避免"结束这个话题换下一题"之类误触发
    llm = make_llm(temperature=0)
    resp = await llm.ainvoke([
        SystemMessage(content=(
            "判断候选人的输入是否表达了想要立即结束整个面试、退出所有剩余环节的意图。"
            "注意区分：'换个问题'/'跳过这题' 不算结束面试。"
            "只回答 yes 或 no，不要解释。"
        )),
        HumanMessage(content=user_text),
    ], config={"tags": ["internal"]})
    return resp.content.strip().lower().startswith("y")


def make_llm(temperature: float = 0.7) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model_name,
        api_key=settings.dashscope_api_key,
        base_url=settings.llm_base_url,
        temperature=temperature,
    )


def next_phase(current: str) -> str:
    idx = PHASE_ORDER.index(current)
    return PHASE_ORDER[idx + 1] if idx + 1 < len(PHASE_ORDER) else "wrap_up"


def has_tool_calls(state: InterviewState) -> bool:
    msgs = state.get("messages", [])
    if not msgs:
        return False
    last = msgs[-1]
    return bool(getattr(last, "tool_calls", None))


def check_transition(state: InterviewState, phase: str) -> bool:
    """Return True if this phase has run enough turns to transition."""
    return state.get("phase_turn_count", 0) >= PHASE_MIN_TURNS[phase]


async def execute_tools(tool_calls: list, tools: list) -> list[ToolMessage]:
    """Execute a list of tool calls and return ToolMessage results."""
    tool_map = {t.name: t for t in tools}
    results = []
    for tc in tool_calls:
        tool = tool_map.get(tc["name"])
        if tool:
            output = await tool.ainvoke(tc["args"])
        else:
            output = f"[Error] Tool '{tc['name']}' not found."
        results.append(ToolMessage(content=str(output), tool_call_id=tc["id"]))
    return results


def _get_text(msg) -> str:
    """Extract plain text from any message type."""
    c = getattr(msg, "content", "")
    if isinstance(c, list):
        return " ".join(item.get("text", "") for item in c if isinstance(item, dict))
    return str(c)


def build_qa_record(
    state_messages: list,
    new_messages: list,
    phase: str,
    turn: int,
    extra: dict | None = None,
) -> dict:
    """
    Build one QA record for a node turn.

    question      = last clean AIMessage in state_messages (what candidate just answered)
    answer        = last HumanMessage in state_messages (candidate's answer this turn)
    tool_material = all ToolMessage content from new_messages (reference / correct answers)
    new_question  = last clean AIMessage in new_messages (what we just asked)
    """
    # ── candidate's answer: last HumanMessage in state ────────────────
    answer = ""
    for msg in reversed(state_messages):
        if type(msg).__name__ == "HumanMessage":
            answer = _get_text(msg)
            break

    # ── question being answered: last clean AIMessage BEFORE that HumanMessage ──
    question = ""
    passed_human = False
    for msg in reversed(state_messages):
        mtype = type(msg).__name__
        if not passed_human:
            if mtype == "HumanMessage":
                passed_human = True
            continue
        if mtype == "AIMessage" and not getattr(msg, "tool_calls", None):
            question = _get_text(msg)
            break

    # ── reference material from tools called this turn ─────────────────
    tool_material = "\n---\n".join(
        _get_text(m) for m in new_messages if type(m).__name__ == "ToolMessage"
    ).strip()

    # ── new question just asked by interviewer ─────────────────────────
    new_question = ""
    for msg in reversed(new_messages):
        if type(msg).__name__ == "AIMessage" and not getattr(msg, "tool_calls", None):
            new_question = _get_text(msg)
            break

    record: dict = {
        "phase": phase,
        "turn": turn,
        "question": question,
        "answer": answer,
        "tool_material": tool_material[:1500],  # cap to avoid huge state
        "new_question": new_question,
        # filled by evaluator in wrap_up:
        "score": None,
        "is_weak": False,
        "feedback": "",
        "correct_answer": "",
        "study_suggestions": [],
    }
    if extra:
        record.update(extra)
    return record


MAX_TOOL_ITERATIONS = 8
CONTEXT_WINDOW_SIZE = 10  # recent messages passed to LLM per turn


def _inject_context_summary(system: str, context_summary: str, *, new_phase: bool) -> str:
    if not context_summary:
        return system
    if new_phase:
        return system + (
            "\n\n【跨阶段背景】以下摘要仅作为背景和去重依据，"
            "不得延续上一阶段的项目深挖或追问链；进入当前阶段后必须严格按照当前阶段任务提问："
            f"「{context_summary}」"
        )
    return system + (
        f"\n\n注意：以下是你之前面试阶段的私有备忘，只作为你提问时的参考背景，"
        f"绝对不能出现在你说的任何一句话里：「{context_summary}」"
    )


def get_context_window(state: InterviewState, system: str, is_new_phase: bool = False) -> list:
    """
    Build the message list to pass to LLM.
    - Injects context_summary at the TOP of system prompt as internal memory
    - Only sends the most recent CONTEXT_WINDOW_SIZE messages, not full history
    - is_new_phase=True includes only the new phase system prompt plus a
      constrained summary, never previous raw messages.
    """
    context_summary = state.get("context_summary", "")
    if is_new_phase:
        system = _inject_context_summary(system, context_summary, new_phase=True)
        return [SystemMessage(content=system)]

    messages = state.get("messages", [])
    system = _inject_context_summary(system, context_summary, new_phase=False)

    recent = messages[-CONTEXT_WINDOW_SIZE:] if len(messages) > CONTEXT_WINDOW_SIZE else messages
    return [SystemMessage(content=system)] + recent


async def compress_messages(state: InterviewState) -> str:
    """
    Compress state["messages"] into plain-text notes.
    Called at phase transitions so the next phase has a concise history.
    Merges with any existing context_summary.
    """
    messages = state.get("messages", [])
    prior_summary = state.get("context_summary", "")

    if not messages:
        return prior_summary

    text = "\n".join(
        f"[{'面试官' if type(m).__name__ == 'AIMessage' else '候选人'}] {_get_text(m)}"
        for m in messages
        if type(m).__name__ in ("AIMessage", "HumanMessage")
    )

    prompt = ""
    if prior_summary:
        prompt += f"已有记录：{prior_summary}\n\n"
    prompt += f"新增对话：\n{text}"

    llm = make_llm(temperature=0)
    resp = await llm.ainvoke([
        SystemMessage(content=(
            "将以下面试对话压缩成一段简短的流水记录（150字以内）。"
            "要求：只用自然连贯的句子，记录已聊过的话题和候选人的表现，"
            "不使用任何标题、分项、加粗、列表等格式，不做评价性语言。"
        )),
        HumanMessage(content=prompt),
    ], config={"tags": ["internal"]})
    return resp.content.strip()


async def llm_tool_loop(llm, messages: list, tools: list) -> tuple[list, object]:
    """
    Run the LLM in a loop until it returns a response with no tool_calls.
    Caps at MAX_TOOL_ITERATIONS to prevent runaway loops.

    Returns:
        (new_messages, final_response)
        new_messages — all intermediate + final messages to append to state
        final_response — the last AIMessage (no tool_calls)
    """
    response = await llm.ainvoke(messages)
    new_messages = [response]

    iterations = 0
    while getattr(response, "tool_calls", None) and iterations < MAX_TOOL_ITERATIONS:
        tool_results = await execute_tools(response.tool_calls, tools)
        new_messages.extend(tool_results)
        response = await llm.ainvoke(messages + new_messages)
        new_messages.append(response)
        iterations += 1

    return new_messages, response
