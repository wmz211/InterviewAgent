"""
Tests for shared utilities in app/agents/nodes/base.py.

Covers:
- check_transition(): turn threshold logic
- next_phase(): phase order traversal
- detect_exit_intent(): keyword pre-filter + LLM semantic check
- get_context_window(): system prompt injection, context_summary, window size
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.nodes.base import (
    check_transition,
    next_phase,
    detect_exit_intent,
    get_context_window,
    PHASE_MIN_TURNS,
    CONTEXT_WINDOW_SIZE,
)
from tests.conftest import make_state, fake_ai_response


# ── check_transition ──────────────────────────────────────────────────────────

class TestCheckTransition:
    def test_below_threshold_returns_false(self):
        for phase, min_turns in PHASE_MIN_TURNS.items():
            state = make_state(phase_turn_count=min_turns - 1)
            assert check_transition(state, phase) is False, f"Failed for phase={phase}"

    def test_at_threshold_returns_true(self):
        for phase, min_turns in PHASE_MIN_TURNS.items():
            state = make_state(phase_turn_count=min_turns)
            assert check_transition(state, phase) is True, f"Failed for phase={phase}"

    def test_above_threshold_returns_true(self):
        state = make_state(phase_turn_count=999)
        assert check_transition(state, "greeting") is True


# ── next_phase ────────────────────────────────────────────────────────────────

class TestNextPhase:
    def test_greeting_to_resume_dive(self):
        assert next_phase("greeting") == "resume_dive"

    def test_resume_dive_to_jd_tech(self):
        assert next_phase("resume_dive") == "jd_tech"

    def test_jd_tech_to_coding_test(self):
        assert next_phase("jd_tech") == "coding_test"

    def test_coding_test_to_wrap_up(self):
        assert next_phase("coding_test") == "wrap_up"

    def test_last_phase_returns_wrap_up(self):
        assert next_phase("wrap_up") == "wrap_up"


# ── detect_exit_intent ────────────────────────────────────────────────────────

class TestDetectExitIntent:
    @pytest.mark.asyncio
    async def test_no_messages_returns_false(self):
        state = make_state(current_node="resume_dive", messages=[])
        result = await detect_exit_intent(state)
        assert result is False

    @pytest.mark.asyncio
    async def test_greeting_phase_always_returns_false(self):
        """Exit detection is disabled in greeting phase."""
        state = make_state(
            current_node="greeting",
            messages=[HumanMessage(content="我想结束面试")],
        )
        result = await detect_exit_intent(state)
        assert result is False

    @pytest.mark.asyncio
    async def test_wrap_up_phase_always_returns_false(self):
        state = make_state(
            current_node="wrap_up",
            messages=[HumanMessage(content="结束面试")],
        )
        result = await detect_exit_intent(state)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_exit_keyword_skips_llm(self):
        """Message with no exit keywords → False without calling LLM."""
        state = make_state(
            current_node="resume_dive",
            messages=[HumanMessage(content="我在项目中使用了Redis。")],
        )
        with patch("app.agents.nodes.base.make_llm") as mock_make_llm:
            result = await detect_exit_intent(state)
        mock_make_llm.assert_not_called()
        assert result is False

    @pytest.mark.asyncio
    async def test_exit_keyword_and_llm_confirms_yes(self):
        """Keyword hit + LLM says 'yes' → True."""
        state = make_state(
            current_node="jd_tech",
            messages=[HumanMessage(content="我想结束面试，不想继续了。")],
        )
        ai_yes = fake_ai_response("yes")
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=ai_yes)
        with patch("app.agents.nodes.base.make_llm", return_value=mock_llm):
            result = await detect_exit_intent(state)
        assert result is True

    @pytest.mark.asyncio
    async def test_exit_keyword_but_llm_says_no(self):
        """Keyword hit but LLM says 'no' (e.g. 'skip this question') → False."""
        state = make_state(
            current_node="jd_tech",
            messages=[HumanMessage(content="结束这个话题换下一题吧。")],
        )
        ai_no = fake_ai_response("no")
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=ai_no)
        with patch("app.agents.nodes.base.make_llm", return_value=mock_llm):
            result = await detect_exit_intent(state)
        assert result is False


# ── get_context_window ────────────────────────────────────────────────────────

class TestGetContextWindow:
    def test_system_message_is_first(self):
        state = make_state(messages=[])
        window = get_context_window(state, "你是面试官。")
        assert isinstance(window[0], SystemMessage)

    def test_context_summary_injected_into_system(self):
        state = make_state(
            messages=[],
            context_summary="候选人已介绍了Redis经验。",
        )
        window = get_context_window(state, "你是面试官。")
        assert "候选人已介绍了Redis经验。" in window[0].content

    def test_no_context_summary_when_empty(self):
        state = make_state(messages=[], context_summary="")
        window = get_context_window(state, "你是面试官。")
        # summary block should not appear
        assert "私有备忘" not in window[0].content

    def test_limits_to_context_window_size(self):
        messages = [HumanMessage(content=f"消息{i}") for i in range(CONTEXT_WINDOW_SIZE + 5)]
        state = make_state(messages=messages)
        window = get_context_window(state, "系统提示")
        # 1 SystemMessage + CONTEXT_WINDOW_SIZE messages
        assert len(window) == CONTEXT_WINDOW_SIZE + 1

    def test_new_phase_flag_isolates_previous_phase_messages(self):
        state = make_state(messages=[HumanMessage(content="上一阶段的消息")])
        window = get_context_window(state, "你是面试官。", is_new_phase=True)
        assert len(window) == 1
        assert window[0].content == "你是面试官。"

    def test_new_phase_false_no_reminder(self):
        state = make_state(messages=[HumanMessage(content="消息")])
        window = get_context_window(state, "你是面试官。", is_new_phase=False)
        assert "上一阶段" not in window[0].content
