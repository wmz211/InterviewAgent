"""
LangGraph interview state machine.

단일 그래프에 tech/HR 두 트랙의 모든 노드를 등록.
dispatch 는 current_node 를 읽어 라우팅하고,
각 노드는 전환 시 current_node 를 다음 단계 이름으로 설정.

Tech track:  greeting → resume_dive → jd_tech → wrap_up
HR track:    greeting → hr_self_intro → hr_behavioral → hr_career → wrap_up
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from app.core.state import InterviewState
from app.agents.nodes.base          import detect_exit_intent
from app.agents.nodes.greeting      import greeting_node
from app.agents.nodes.resume_dive   import resume_dive_node
from app.agents.nodes.jd_tech       import jd_tech_node
from app.agents.nodes.coding_test   import coding_test_node
from app.agents.nodes.hr_self_intro import hr_self_intro_node
from app.agents.nodes.hr_behavioral import hr_behavioral_node
from app.agents.nodes.hr_career     import hr_career_node
from app.agents.nodes.wrap_up       import wrap_up_node

ALL_PHASES = [
    "greeting",
    # tech track
    "resume_dive", "jd_tech", "coding_test",
    # hr track
    "hr_self_intro", "hr_behavioral", "hr_career",
    # shared
    "wrap_up",
]


async def dispatch(state: InterviewState) -> dict:
    """意图检测：用户若表达退出意图则直接路由到 wrap_up。"""
    if await detect_exit_intent(state):
        from loguru import logger
        logger.info(f"Exit intent detected — jumping to wrap_up "
                    f"(was: {state.get('current_node')})")
        return {"current_node": "wrap_up", "phase_turn_count": 0}
    return {}


def _dispatch_route(state: InterviewState) -> str:
    node = state.get("current_node", "greeting")
    return node if node in ALL_PHASES else "greeting"


def build_interview_graph() -> StateGraph:
    graph = StateGraph(InterviewState)

    graph.add_node("dispatch", dispatch)
    graph.add_edge(START, "dispatch")
    graph.add_conditional_edges(
        "dispatch",
        _dispatch_route,
        {phase: phase for phase in ALL_PHASES},
    )

    graph.add_node("greeting",       greeting_node)
    graph.add_node("resume_dive",    resume_dive_node)
    graph.add_node("jd_tech",        jd_tech_node)
    graph.add_node("coding_test",    coding_test_node)
    graph.add_node("hr_self_intro",  hr_self_intro_node)
    graph.add_node("hr_behavioral",  hr_behavioral_node)
    graph.add_node("hr_career",      hr_career_node)
    graph.add_node("wrap_up",        wrap_up_node)

    for phase in ALL_PHASES:
        graph.add_edge(phase, END)

    return graph


_compiled_graph = None


def get_interview_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_interview_graph().compile()
    return _compiled_graph


def make_initial_state(
    session_id: str,
    resume_summary: str,
    jd_text: str,
    interview_mode: str = "tech",
) -> dict:
    return {
        "session_id":         session_id,
        "candidate_name":     "",
        "resume_summary":     resume_summary,
        "jd_text":            jd_text,
        "messages":           [],
        "current_node":       "greeting",
        "current_topic":      "",
        "context_summary":    "",
        "node_scores":        {},
        "asked_question_ids": [],
        "phase_turn_count":   0,
        "should_transition":  False,
        "interview_complete": False,
        "interview_mode":     interview_mode,
    }
