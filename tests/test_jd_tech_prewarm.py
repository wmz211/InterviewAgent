import pytest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from tests.conftest import fake_ai_response, make_state


def test_prepare_jd_tech_phase_data_builds_chain_and_interview_nodes():
    from app.agents.nodes import jd_tech

    chain = [
        {"node_id": "agent", "label": "LLM Agent", "is_root": True},
        {"node_id": "react", "label": "ReAct", "is_root": False},
        {"node_id": "rag", "label": "RAG", "is_root": True},
    ]

    phase_data = {}
    with patch("app.agents.nodes.jd_tech._build_jd_chain", return_value=chain) as build:
        with patch("app.agents.nodes.jd_tech._node_has_content", return_value=True):
            result = jd_tech.prepare_jd_tech_phase_data("Agent and RAG", phase_data)

    build.assert_called_once_with("Agent and RAG")
    assert result["chain"] == chain
    assert result["interview_nodes"] == [
        {"node_id": "agent", "label": "LLM Agent", "is_root": True},
        {"node_id": "rag", "label": "RAG", "is_root": True},
    ]


@pytest.mark.asyncio
async def test_jd_tech_node_uses_prewarmed_chain_without_rebuilding():
    from app.agents.nodes.jd_tech import jd_tech_node

    state = make_state(
        current_node="jd_tech",
        phase_turn_count=0,
        messages=[HumanMessage(content="I have used Agent systems.")],
        node_scores={
            "jd_tech": {
                "turn_count": 0,
                "chain": [
                    {"node_id": "agent", "label": "LLM Agent", "is_root": True},
                    {"node_id": "react", "label": "ReAct", "is_root": False},
                ],
                "interview_nodes": [
                    {"node_id": "agent", "label": "LLM Agent", "is_root": True},
                ],
                "node_idx": 0,
                "turns_on_node": 0,
                "covered_labels": [],
                "qa_records": [],
            }
        },
    )

    with patch("app.agents.nodes.jd_tech._build_jd_chain") as build:
        with patch(
            "app.agents.nodes.jd_tech.llm_tool_loop",
            new_callable=AsyncMock,
            return_value=([fake_ai_response("How would you prevent an Agent loop?")], None),
        ):
            result = await jd_tech_node(state)

    build.assert_not_called()
    assert result["node_scores"]["jd_tech"]["chain"][0]["label"] == "LLM Agent"
