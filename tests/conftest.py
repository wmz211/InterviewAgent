"""
pytest fixtures — shared across all state machine tests.
All LLM calls are mocked so tests run offline without DashScope.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from app.core.interview_graph import make_initial_state


# ── Minimal state factories ───────────────────────────────────────────────────

def make_state(**overrides) -> dict:
    """Return a base tech-track state with sensible defaults."""
    state = make_initial_state(
        session_id="test-session",
        resume_summary="候选人具备3年后端开发经验，熟悉Python、Redis、MySQL。",
        jd_text="招聘后端工程师，要求熟悉分布式系统、缓存、消息队列。",
        interview_mode="tech",
    )
    state.update(overrides)
    return state


def make_hr_state(**overrides) -> dict:
    state = make_initial_state(
        session_id="hr-session",
        resume_summary="候选人具备3年后端开发经验。",
        jd_text="招聘后端工程师。",
        interview_mode="hr",
    )
    state.update(overrides)
    return state


def fake_ai_response(content: str = "这是面试官的回复。") -> AIMessage:
    msg = AIMessage(content=content)
    msg.tool_calls = []
    return msg


# ── LLM mock fixture ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_response():
    """
    Patches ChatOpenAI so every ainvoke() returns a clean AIMessage.
    Usage:
        async def test_foo(mock_llm_response):
            ...
    """
    ai_msg = fake_ai_response()
    with patch("app.agents.nodes.base.ChatOpenAI") as MockLLM:
        instance = MagicMock()
        instance.ainvoke = AsyncMock(return_value=ai_msg)
        MockLLM.return_value = instance
        yield instance


@pytest.fixture
def mock_compress():
    """Patches compress_messages to return a fixed summary string."""
    with patch(
        "app.agents.nodes.base.compress_messages",
        new_callable=AsyncMock,
        return_value="候选人完成了自我介绍，提及Python和Redis项目经验。",
    ) as m:
        yield m
