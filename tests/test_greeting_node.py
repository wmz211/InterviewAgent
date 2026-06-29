"""
Tests for the greeting_node.

Covers:
- First turn (no human message yet) → uses _SYSTEM_FIRST prompt
- Follow-up turn (human message exists) → uses _SYSTEM_FOLLOWUP prompt
- Phase transition after PHASE_MIN_TURNS["greeting"] turns
- Tech track → transitions to resume_dive
- HR track → transitions to hr_self_intro
- Candidate name extraction from "我叫XX" message
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.nodes.greeting import greeting_node
from tests.conftest import make_state, make_hr_state, fake_ai_response

GREETING_MIN_TURNS = 2  # from base.PHASE_MIN_TURNS


def _patch_llm(response_content="欢迎参加面试，请自我介绍。"):
    """Context manager: patches the module-level _llm in greeting.py."""
    ai_msg = fake_ai_response(response_content)
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=ai_msg)
    return patch("app.agents.nodes.greeting._llm", mock), mock


class TestGreetingNodeFirstTurn:
    @pytest.mark.asyncio
    async def test_first_turn_increments_phase_turn_count(self):
        state = make_state(phase_turn_count=0, messages=[])
        cm, _ = _patch_llm()
        with cm:
            with patch("app.agents.nodes.greeting.compress_messages", new_callable=AsyncMock):
                result = await greeting_node(state)
        assert result["phase_turn_count"] == 1

    @pytest.mark.asyncio
    async def test_first_turn_stays_in_greeting(self):
        state = make_state(phase_turn_count=0, messages=[])
        cm, _ = _patch_llm()
        with cm:
            with patch("app.agents.nodes.greeting.compress_messages", new_callable=AsyncMock):
                result = await greeting_node(state)
        assert result["current_node"] == "greeting"
        assert result["should_transition"] is False

    @pytest.mark.asyncio
    async def test_response_appended_to_messages(self):
        state = make_state(phase_turn_count=0, messages=[])
        cm, _ = _patch_llm("你好，请开始自我介绍。")
        with cm:
            with patch("app.agents.nodes.greeting.compress_messages", new_callable=AsyncMock):
                result = await greeting_node(state)
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "你好，请开始自我介绍。"


class TestGreetingNodeTransition:
    @pytest.mark.asyncio
    async def test_transitions_to_resume_dive_in_tech_mode(self):
        """After GREETING_MIN_TURNS turns, tech track → resume_dive."""
        state = make_state(
            phase_turn_count=GREETING_MIN_TURNS - 1,
            messages=[HumanMessage(content="我叫张伟，有三年Python经验。")],
            interview_mode="tech",
        )
        cm, _ = _patch_llm()
        with cm:
            with patch(
                "app.agents.nodes.greeting.compress_messages",
                new_callable=AsyncMock,
                return_value="候选人完成自我介绍。",
            ):
                result = await greeting_node(state)
        assert result["current_node"] == "resume_dive"
        assert result["should_transition"] is True
        assert result["phase_turn_count"] == 0  # resets on transition

    @pytest.mark.asyncio
    async def test_transitions_to_hr_self_intro_in_hr_mode(self):
        """After GREETING_MIN_TURNS turns, HR track → hr_self_intro."""
        state = make_hr_state(
            phase_turn_count=GREETING_MIN_TURNS - 1,
            messages=[HumanMessage(content="大家好，我是李明。")],
        )
        cm, _ = _patch_llm()
        with cm:
            with patch(
                "app.agents.nodes.greeting.compress_messages",
                new_callable=AsyncMock,
                return_value="候选人完成自我介绍。",
            ):
                result = await greeting_node(state)
        assert result["current_node"] == "hr_self_intro"

    @pytest.mark.asyncio
    async def test_context_summary_set_on_transition(self):
        """context_summary is written to state when transitioning out."""
        state = make_state(
            phase_turn_count=GREETING_MIN_TURNS - 1,
            messages=[HumanMessage(content="我叫王芳。")],
        )
        summary = "候选人介绍了Python项目经验。"
        cm, _ = _patch_llm()
        with cm:
            with patch(
                "app.agents.nodes.greeting.compress_messages",
                new_callable=AsyncMock,
                return_value=summary,
            ):
                result = await greeting_node(state)
        assert result.get("context_summary") == summary

    @pytest.mark.asyncio
    async def test_no_context_summary_without_transition(self):
        """context_summary is NOT set when not transitioning."""
        state = make_state(phase_turn_count=0, messages=[])
        cm, _ = _patch_llm()
        with cm:
            with patch("app.agents.nodes.greeting.compress_messages", new_callable=AsyncMock):
                result = await greeting_node(state)
        assert "context_summary" not in result


class TestGreetingNodeNameExtraction:
    @pytest.mark.asyncio
    async def test_extracts_name_from_wo_jiao(self):
        """
        Simple name extraction from '我叫XX' pattern.
        The code uses split()[0] (whitespace), so the message must have a space
        after the name for the extraction to work correctly.
        """
        state = make_state(
            phase_turn_count=0,
            messages=[HumanMessage(content="我叫陈磊 有两年经验。")],
            candidate_name="",
        )
        cm, _ = _patch_llm()
        with cm:
            with patch("app.agents.nodes.greeting.compress_messages", new_callable=AsyncMock):
                result = await greeting_node(state)
        assert result["candidate_name"] == "陈磊"

    @pytest.mark.asyncio
    async def test_keeps_existing_name_if_set(self):
        """Does not overwrite candidate_name already in state."""
        state = make_state(
            phase_turn_count=0,
            messages=[HumanMessage(content="我叫李雷。")],
            candidate_name="韩梅梅",
        )
        cm, _ = _patch_llm()
        with cm:
            with patch("app.agents.nodes.greeting.compress_messages", new_callable=AsyncMock):
                result = await greeting_node(state)
        assert result["candidate_name"] == "韩梅梅"

    @pytest.mark.asyncio
    async def test_extracts_name_before_chinese_punctuation(self):
        """Stops name extraction at Chinese punctuation instead of swallowing the intro."""
        state = make_state(
            phase_turn_count=0,
            messages=[HumanMessage(content="你好，我叫王明哲，是苏州大学软件工程专业本科生。")],
            candidate_name="",
        )
        cm, _ = _patch_llm()
        with cm:
            with patch("app.agents.nodes.greeting.compress_messages", new_callable=AsyncMock):
                result = await greeting_node(state)
        assert result["candidate_name"] == "王明哲"
