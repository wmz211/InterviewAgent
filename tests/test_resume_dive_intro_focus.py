import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import HumanMessage

from tests.conftest import fake_ai_response, make_state


@pytest.mark.asyncio
async def test_resume_dive_plan_uses_intro_projects_before_resume_fallback(monkeypatch):
    from app.agents.nodes import resume_dive

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=fake_ai_response("What did you own in Alpha Project?"))
    monkeypatch.setattr(resume_dive, "_llm_with_tool", mock_llm)

    state = make_state(
        current_node="resume_dive",
        phase_turn_count=0,
        resume_summary=(
            "项目：Alpha Project\n"
            "项目：Beta Project\n"
            "项目：Gamma Project\n"
        ),
        messages=[HumanMessage(content="I mainly introduced Alpha Project.")],
    )

    result = await resume_dive.resume_dive_node(state)

    plan = result["node_scores"]["resume_dive"]["project_plan"]
    assert plan["projects"] == ["Alpha Project"]
    assert plan["planned_turns"] == 4
    assert plan["turns_per_project"] == 3


@pytest.mark.asyncio
async def test_resume_dive_plan_does_not_fallback_to_unmentioned_resume_projects(monkeypatch):
    from app.agents.nodes import resume_dive

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=fake_ai_response("What did you own in your core project?"))
    monkeypatch.setattr(resume_dive, "_llm_with_tool", mock_llm)

    state = make_state(
        current_node="resume_dive",
        phase_turn_count=0,
        resume_summary=(
            "项目：Alpha Project\n"
            "项目：Beta Project\n"
            "项目：Gamma Project\n"
        ),
        messages=[HumanMessage(content="I mainly introduced an interview agent system.")],
    )

    result = await resume_dive.resume_dive_node(state)

    plan = result["node_scores"]["resume_dive"]["project_plan"]
    assert plan["projects"] == ["候选人自我介绍中提到的核心项目"]
    assert "Beta Project" not in plan["projects"]
    assert "Gamma Project" not in plan["projects"]


@pytest.mark.asyncio
async def test_resume_dive_plan_rejects_chinese_keyword_overlap_for_unmentioned_project(monkeypatch):
    from app.agents.nodes import resume_dive

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=fake_ai_response("What did you own in the hallucination project?"))
    monkeypatch.setattr(resume_dive, "_llm_with_tool", mock_llm)

    state = make_state(
        current_node="resume_dive",
        phase_turn_count=0,
        resume_summary=(
            "项目：新闻文本幻觉检测与事件事实性识别研究\n"
            "项目：基于 LangGraph 的 AI 模拟面试系统\n"
            "项目：基于全局上下文的知识图谱逻辑查询推理\n"
        ),
        messages=[
            HumanMessage(
                content=(
                    "我介绍了新闻文本幻觉检测项目，也介绍了基于 LangGraph 的 AI 模拟面试系统，"
                    "里面用了 GraphRAG 和 LLM 推理。"
                )
            )
        ],
    )

    result = await resume_dive.resume_dive_node(state)

    plan = result["node_scores"]["resume_dive"]["project_plan"]
    assert "基于全局上下文的知识图谱逻辑查询推理" not in plan["projects"]
