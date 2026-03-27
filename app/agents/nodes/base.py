"""
Shared utilities for all interview phase nodes.
"""
from __future__ import annotations

from langchain_core.messages import SystemMessage, ToolMessage
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
"""


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


async def llm_tool_loop(llm, messages: list, tools: list) -> tuple[list, object]:
    """
    Run the LLM in a loop until it returns a response with no tool_calls.

    Returns:
        (new_messages, final_response)
        new_messages — all intermediate + final messages to append to state
        final_response — the last AIMessage (no tool_calls)
    """
    response = await llm.ainvoke(messages)
    new_messages = [response]

    while getattr(response, "tool_calls", None):
        tool_results = await execute_tools(response.tool_calls, tools)
        new_messages.extend(tool_results)
        response = await llm.ainvoke(messages + new_messages)
        new_messages.append(response)

    return new_messages, response


def build_entity_summary(anchored_entities: list[dict]) -> str:
    if not anchored_entities:
        return "（暂无锚定技术点）"
    lines = []
    for e in anchored_entities:
        lines.append(f"- {e['kg_node_label']}（简历原文：{e['resume_text']}）")
    return "\n".join(lines)
