"""
Integration-style tests: verify that each phase node sets current_node
correctly when should_transition triggers.

These tests mock the LLM and compress_messages to focus purely on
routing logic, not on LLM output quality.

Tech track:  greeting → resume_dive → jd_tech → coding_test → wrap_up
HR track:    greeting → hr_self_intro → hr_behavioral → hr_career → wrap_up
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage

from app.agents.nodes.base import PHASE_MIN_TURNS
from tests.conftest import make_state, make_hr_state, fake_ai_response


def _mock_node_llm(node_module_path: str, content: str = "面试官回复"):
    """
    Patch the module-level _llm (or make_llm) in a given node module.
    Returns (patch_ctx, mock_instance).
    """
    ai_msg = fake_ai_response(content)
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=ai_msg)
    # Also mock with_config if needed
    mock.with_config = MagicMock(return_value=mock)
    return patch(f"{node_module_path}._llm", mock), mock


COMPRESS_PATH = "app.agents.nodes.base.compress_messages"


async def _run_node_until_transition(node_fn, state: dict, node_module: str):
    """
    Run a node function repeatedly until should_transition becomes True.
    Returns the final result dict.
    """
    cm, _ = _mock_node_llm(node_module)
    with cm:
        with patch(COMPRESS_PATH, new_callable=AsyncMock, return_value="压缩摘要"):
            result = None
            for _ in range(PHASE_MIN_TURNS.get(state["current_node"], 2) + 2):
                result = await node_fn(state)
                state = {**state, **result}
                # merge messages properly
                if result.get("should_transition"):
                    break
    return result


# ── Tech track transitions ────────────────────────────────────────────────────

class TestTechTrackTransitions:
    @pytest.mark.asyncio
    async def test_greeting_transitions_to_resume_dive(self):
        from app.agents.nodes.greeting import greeting_node
        state = make_state(
            current_node="greeting",
            phase_turn_count=PHASE_MIN_TURNS["greeting"] - 1,
            messages=[HumanMessage(content="我叫张三。")],
        )
        result = await _run_node_until_transition(
            greeting_node, state, "app.agents.nodes.greeting"
        )
        assert result["current_node"] == "resume_dive"
        assert result["should_transition"] is True

    @pytest.mark.asyncio
    async def test_resume_dive_transitions_to_jd_tech(self):
        """
        resume_dive uses a tool-based transition: the LLM must call
        advance_to_jd_tech AND phase_turn >= MIN_TURNS (3).
        We mock _llm_with_tool directly to emit a tool_call on first invoke.
        """
        from app.agents.nodes.resume_dive import resume_dive_node
        from langchain_core.messages import AIMessage

        # Build AIMessage that carries advance_to_jd_tech tool call
        ai_tool_msg = AIMessage(content="好，简历环节先到这里。")
        ai_tool_msg.tool_calls = [{"name": "advance_to_jd_tech", "args": {}, "id": "call_1"}]

        mock_llm_with_tool = MagicMock()
        mock_llm_with_tool.ainvoke = AsyncMock(return_value=ai_tool_msg)

        state = make_state(
            current_node="resume_dive",
            # Start at MIN_TURNS so phase_turn >= MIN_TURNS after first increment
            phase_turn_count=2,  # MIN_TURNS=3, incremented to 3 inside node
            messages=[HumanMessage(content="我在项目中使用了Redis。")],
        )
        with patch("app.agents.nodes.resume_dive._llm_with_tool", mock_llm_with_tool):
            with patch(COMPRESS_PATH, new_callable=AsyncMock, return_value="摘要"):
                result = await resume_dive_node(state)
        assert result["current_node"] == "jd_tech"
        assert result["should_transition"] is True

    @pytest.mark.asyncio
    async def test_phase_turn_count_resets_on_transition(self):
        """phase_turn_count must reset to 0 when any phase transitions."""
        from app.agents.nodes.greeting import greeting_node
        state = make_state(
            current_node="greeting",
            phase_turn_count=PHASE_MIN_TURNS["greeting"] - 1,
            messages=[HumanMessage(content="我叫李四。")],
        )
        result = await _run_node_until_transition(
            greeting_node, state, "app.agents.nodes.greeting"
        )
        assert result["phase_turn_count"] == 0

    @pytest.mark.asyncio
    async def test_jd_tech_forces_next_topic_after_max_turns_without_tool_call(self):
        """
        jd_tech should not depend solely on the LLM calling advance_to_next_topic.
        If the current topic has already been probed enough, code should advance
        to the next interview topic even when the model only returns a question.
        """
        from app.agents.nodes.jd_tech import jd_tech_node

        state = make_state(
            current_node="jd_tech",
            phase_turn_count=2,
            messages=[
                HumanMessage(content="我会从可控性、评估和失败兜底来设计这个 Agent。")
            ],
            node_scores={
                "jd_tech": {
                    "turn_count": 2,
                    "chain": [
                        {"node_id": "agent", "label": "LLM Agent", "is_root": True},
                        {"node_id": "react", "label": "ReAct", "is_root": False},
                        {"node_id": "rag", "label": "RAG", "is_root": True},
                        {"node_id": "vector", "label": "向量检索", "is_root": False},
                        {"node_id": "framework", "label": "Agent开发框架", "is_root": True},
                    ],
                    "interview_nodes": [
                        {"node_id": "agent", "label": "LLM Agent", "is_root": True},
                        {"node_id": "rag", "label": "RAG", "is_root": True},
                        {"node_id": "framework", "label": "Agent开发框架", "is_root": True},
                    ],
                    "node_idx": 0,
                    "turns_on_node": 2,
                    "covered_labels": ["LLM Agent"],
                    "qa_records": [],
                }
            },
        )

        with patch(
            "app.agents.nodes.jd_tech.llm_tool_loop",
            new_callable=AsyncMock,
            return_value=([fake_ai_response("请继续说明你的工具调用兜底策略。")], None),
        ):
            result = await jd_tech_node(state)

        jd_data = result["node_scores"]["jd_tech"]
        assert result["current_node"] == "jd_tech"
        assert result["should_transition"] is False
        assert jd_data["node_idx"] == 1
        assert jd_data["turns_on_node"] == 0


# ── HR track transitions ──────────────────────────────────────────────────────

class TestHRTrackTransitions:
    @pytest.mark.asyncio
    async def test_greeting_transitions_to_hr_self_intro(self):
        from app.agents.nodes.greeting import greeting_node
        state = make_hr_state(
            current_node="greeting",
            phase_turn_count=PHASE_MIN_TURNS["greeting"] - 1,
            messages=[HumanMessage(content="大家好，我叫王五。")],
        )
        result = await _run_node_until_transition(
            greeting_node, state, "app.agents.nodes.greeting"
        )
        assert result["current_node"] == "hr_self_intro"

    @pytest.mark.asyncio
    async def test_hr_self_intro_transitions_to_hr_behavioral(self):
        from app.agents.nodes.hr_self_intro import hr_self_intro_node
        state = make_hr_state(
            current_node="hr_self_intro",
            phase_turn_count=PHASE_MIN_TURNS["hr_self_intro"] - 1,
            messages=[HumanMessage(content="我对贵公司很感兴趣。")],
        )
        result = await _run_node_until_transition(
            hr_self_intro_node, state, "app.agents.nodes.hr_self_intro"
        )
        assert result["current_node"] == "hr_behavioral"

    @pytest.mark.asyncio
    async def test_hr_behavioral_transitions_to_hr_career(self):
        """
        hr_behavioral uses llm_tool_loop with _llm.bind_tools().
        We must mock _llm so that bind_tools() returns an object with AsyncMock ainvoke.
        """
        from app.agents.nodes.hr_behavioral import hr_behavioral_node

        ai_msg = fake_ai_response("请描述一次你主导的项目经历。")

        # _llm_with_tools is created inside the node via _llm.bind_tools(HR_TOOLS)
        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=ai_msg)

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm_with_tools)

        state = make_hr_state(
            current_node="hr_behavioral",
            phase_turn_count=PHASE_MIN_TURNS["hr_behavioral"] - 1,
            messages=[HumanMessage(content="我曾主导过一个团队协作项目。")],
        )
        with patch("app.agents.nodes.hr_behavioral._llm", mock_llm):
            with patch(COMPRESS_PATH, new_callable=AsyncMock, return_value="摘要"):
                result = None
                for _ in range(PHASE_MIN_TURNS["hr_behavioral"] + 2):
                    result = await hr_behavioral_node(state)
                    state = {**state, **result}
                    if result.get("should_transition"):
                        break
        assert result["current_node"] == "hr_career"


# ── Invariants across all phases ──────────────────────────────────────────────

class TestPhaseInvariants:
    @pytest.mark.asyncio
    async def test_node_scores_updated_each_turn(self):
        """node_scores[phase] should be set after any node runs."""
        from app.agents.nodes.greeting import greeting_node
        state = make_state(current_node="greeting", phase_turn_count=0, messages=[])
        cm, _ = _mock_node_llm("app.agents.nodes.greeting")
        with cm:
            with patch(COMPRESS_PATH, new_callable=AsyncMock, return_value=""):
                result = await greeting_node(state)
        assert "greeting" in result["node_scores"]

    @pytest.mark.asyncio
    async def test_messages_list_grows_each_turn(self):
        """Each node turn appends at least one message."""
        from app.agents.nodes.greeting import greeting_node
        state = make_state(current_node="greeting", phase_turn_count=0, messages=[])
        cm, _ = _mock_node_llm("app.agents.nodes.greeting")
        with cm:
            with patch(COMPRESS_PATH, new_callable=AsyncMock, return_value=""):
                result = await greeting_node(state)
        assert len(result["messages"]) >= 1
