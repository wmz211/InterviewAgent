"""
Wrap-up node — 反问环节与面试收尾，最后一轮触发评估报告生成。
"""
from langchain_core.messages import SystemMessage
from loguru import logger

from app.agents.nodes.base import make_llm, PHASE_MIN_TURNS
from app.core.state import InterviewState

_SYSTEM = """\
你是一位专业的技术面试官，面试即将结束。

【当前阶段】反问与收尾
【候选人表现记录】
{performance_summary}

【你的任务】
1. 告知候选人面试环节基本结束，询问是否有想了解的问题
2. 对候选人的反问给出真实、有价值的回答（可以谈团队技术栈、发展方向等）
3. 结束时给出积极、专业的道别语，告知后续流程（HR会跟进）

【注意】
- 不要在此阶段透露评分或明确的通过/拒绝信号
- 保持专业、友善的面试官形象直到最后
"""


def _build_performance_summary(node_scores: dict) -> str:
    if not node_scores:
        return "（暂无记录）"
    lines = []
    for phase, data in node_scores.items():
        if phase == "evaluation":
            continue
        turn = data.get("turn_count", 0)
        qa_count = len(data.get("qa_records", []))
        lines.append(f"- {phase}: {turn} 轮对话，记录 {qa_count} 道题")
    return "\n".join(lines)


_llm = make_llm(temperature=0.6)


async def wrap_up_node(state: InterviewState) -> dict:
    system = _SYSTEM.format(
        performance_summary=_build_performance_summary(state.get("node_scores", {}))
    )

    messages = [SystemMessage(content=system)] + state["messages"]
    response = await _llm.ainvoke(messages)

    phase_turn = state.get("phase_turn_count", 0) + 1
    interview_complete = phase_turn >= PHASE_MIN_TURNS["wrap_up"]

    scores = state.get("node_scores", {})
    scores["wrap_up"] = {"turn_count": phase_turn}

    # ── Trigger evaluation on the final wrap_up turn ───────────────────
    evaluation = None
    if interview_complete:
        try:
            from app.evaluation.evaluator import evaluate_interview
            logger.info("Running post-interview evaluation...")
            evaluation = await evaluate_interview({**state, "node_scores": scores})
            scores["evaluation"] = evaluation
            logger.info(
                f"Evaluation done: score={evaluation.get('overall_score')} "
                f"recommendation={evaluation.get('recommendation')}"
            )
        except Exception as e:
            logger.exception(f"Evaluation failed: {e}")
            scores["evaluation"] = {"error": str(e)}

    return {
        "messages": [response],
        "current_node": "wrap_up",
        "phase_turn_count": phase_turn,
        "should_transition": False,
        "interview_complete": interview_complete,
        "node_scores": scores,
    }
