"""
Small prompt-memory helpers for interviewer follow-up control.

These helpers are intentionally dependency-free so they can be unit tested
without initializing LangChain or provider clients.
"""
from __future__ import annotations


LOW_SIGNAL_ANSWER_PATTERNS = (
    "\u6ca1\u6709",  # 没有
    "\u6682\u65f6\u6ca1\u6709",  # 暂时没有
    "\u4e0d\u77e5\u9053",  # 不知道
    "\u4e0d\u6e05\u695a",  # 不清楚
    "\u4e0d\u4e86\u89e3",  # 不了解
    "\u6ca1\u60f3\u8fc7",  # 没想过
    "\u6ca1\u9047\u5230",  # 没遇到
    "\u6ca1\u53c2\u4e0e",  # 没参与
    "\u53ea\u662f\u4e86\u89e3",  # 只是了解
    "\u53ea\u662f\u8bba\u6587",  # 只是论文
    "\u6ca1\u6709\u6d89\u53ca",  # 没有涉及
    "no",
    "not sure",
    "unknown",
)


def _clip(text: object, limit: int = 120) -> str:
    value = str(text or "").strip()
    return " ".join(value.split())[:limit]


def is_low_signal_answer(answer: str) -> bool:
    """Return True when the answer clearly gives no more useful interview signal."""
    normalized = _clip(answer, 160).lower()
    if not normalized:
        return False
    return any(pattern in normalized for pattern in LOW_SIGNAL_ANSWER_PATTERNS)


def build_resume_followup_memory(qa_records: list[dict], max_items: int = 8) -> str:
    """
    Build compact memory that tells the next interviewer turn what is closed.

    The wording is English on purpose: it avoids source-encoding drift while
    still being understood by the LLM alongside the Chinese system prompt.
    """
    if not qa_records:
        return (
            "No previous resume deep-dive turns. Ask the first high-signal "
            "resume question."
        )

    lines = [
        "Use this as authoritative memory. Do not repeat these questions.",
        (
            "If status=CLOSED_LOW_SIGNAL, briefly move to another project, "
            "topic, or evaluation dimension."
        ),
    ]
    for record in qa_records[-max_items:]:
        question = _clip(record.get("question"), 100)
        answer = _clip(record.get("answer"), 100)
        new_question = _clip(record.get("new_question"), 100)
        status = "CLOSED_LOW_SIGNAL" if is_low_signal_answer(answer) else "OPEN"
        turn = record.get("turn", "?")
        lines.append(
            f"- turn={turn} status={status} answered_q={question!r} "
            f"candidate_answer={answer!r} next_q={new_question!r}"
        )
    return "\n".join(lines)
