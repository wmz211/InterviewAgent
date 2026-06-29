from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.nodes.base import get_context_window
from tests.conftest import fake_ai_response, make_state


def test_new_phase_uses_summary_without_previous_phase_messages():
    state = make_state(
        messages=[
            AIMessage(content="resume dive question about project"),
            HumanMessage(content="resume dive answer about project"),
        ],
        context_summary="previous resume dive summary",
    )

    window = get_context_window(state, "jd tech system", is_new_phase=True)

    assert len(window) == 1
    assert isinstance(window[0], SystemMessage)
    assert "jd tech system" in window[0].content
    assert "previous resume dive summary" in window[0].content
    assert "resume dive answer about project" not in window[0].content


@pytest.mark.asyncio
async def test_jd_tech_new_phase_does_not_inject_resume_context_summary():
    from app.agents.nodes.jd_tech import jd_tech_node

    captured = {}

    async def capture_loop(_llm, messages, _tools):
        captured["system"] = messages[0].content
        return [fake_ai_response("Tell me about RAG retrieval tradeoffs.")], None

    state = make_state(
        current_node="jd_tech",
        phase_turn_count=0,
        context_summary="resume-only project: global context KG logic query",
        messages=[HumanMessage(content="I finished resume deep dive.")],
        node_scores={
            "jd_tech": {
                "turn_count": 0,
                "chain": [
                    {"node_id": "rag", "label": "RAG", "is_root": True},
                    {"node_id": "vector", "label": "Vector Search", "is_root": False},
                ],
                "interview_nodes": [
                    {"node_id": "rag", "label": "RAG", "is_root": True},
                ],
                "node_idx": 0,
                "turns_on_node": 0,
                "covered_labels": [],
                "qa_records": [],
            }
        },
    )

    with patch("app.agents.nodes.jd_tech.llm_tool_loop", new=AsyncMock(side_effect=capture_loop)):
        await jd_tech_node(state)

    assert "RAG" in captured["system"]
    assert "resume-only project" not in captured["system"]
    assert "global context KG logic query" not in captured["system"]
