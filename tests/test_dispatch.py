"""
Tests for the dispatch node and _dispatch_route router.

dispatch() detects exit intent and overrides current_node → "wrap_up".
_dispatch_route() maps current_node to the correct graph branch.
"""
import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import HumanMessage

from app.core.interview_graph import _dispatch_route, dispatch, ALL_PHASES
from tests.conftest import make_state


# ── _dispatch_route ───────────────────────────────────────────────────────────

class TestDispatchRoute:
    def test_routes_to_greeting_by_default(self):
        state = make_state(current_node="greeting")
        assert _dispatch_route(state) == "greeting"

    def test_routes_to_each_known_phase(self):
        for phase in ALL_PHASES:
            state = make_state(current_node=phase)
            assert _dispatch_route(state) == phase

    def test_unknown_phase_falls_back_to_greeting(self):
        state = make_state(current_node="nonexistent_phase")
        assert _dispatch_route(state) == "greeting"

    def test_missing_current_node_falls_back_to_greeting(self):
        state = make_state()
        state.pop("current_node", None)
        assert _dispatch_route(state) == "greeting"


# ── dispatch() exit-intent detection ─────────────────────────────────────────

class TestDispatchNode:
    @pytest.mark.asyncio
    async def test_no_exit_intent_returns_empty(self):
        """Normal turn: dispatch returns {} so current_node is unchanged."""
        state = make_state(
            current_node="resume_dive",
            messages=[HumanMessage(content="我在项目中使用了Redis做缓存。")],
        )
        with patch(
            "app.core.interview_graph.detect_exit_intent",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await dispatch(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_exit_intent_routes_to_wrap_up(self):
        """User expresses exit → dispatch overrides current_node to wrap_up."""
        state = make_state(
            current_node="jd_tech",
            messages=[HumanMessage(content="我想结束面试。")],
        )
        with patch(
            "app.core.interview_graph.detect_exit_intent",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await dispatch(state)
        assert result["current_node"] == "wrap_up"
        assert result["phase_turn_count"] == 0

    @pytest.mark.asyncio
    async def test_exit_intent_from_greeting_not_triggered(self):
        """
        detect_exit_intent itself skips greeting/wrap_up phases.
        dispatch should return {} because detect_exit_intent returns False.
        """
        state = make_state(
            current_node="greeting",
            messages=[HumanMessage(content="结束面试")],
        )
        with patch(
            "app.core.interview_graph.detect_exit_intent",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await dispatch(state)
        assert result == {}
