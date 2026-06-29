import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage

from tests.conftest import fake_ai_response, make_state


@pytest.mark.asyncio
async def test_resume_dive_forces_transition_at_max_turns_without_tool_call():
    from app.agents.nodes.resume_dive import MAX_TURNS, resume_dive_node

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=fake_ai_response("最后确认一个项目复盘问题。"))

    state = make_state(
        current_node="resume_dive",
        phase_turn_count=MAX_TURNS - 1,
        messages=[
            HumanMessage(content="我介绍了新闻幻觉检测、中医知识图谱和肿瘤编码微调三个项目。"),
            HumanMessage(content="我主要负责RAG链路。"),
        ],
    )

    with patch("app.agents.nodes.resume_dive._llm_with_tool", mock_llm):
        with patch(
            "app.agents.nodes.resume_dive.compress_messages",
            new_callable=AsyncMock,
            return_value="简历深挖已完成。",
        ):
            result = await resume_dive_node(state)

    assert result["current_node"] == "jd_tech"
    assert result["should_transition"] is True
    assert result["phase_turn_count"] == 0


@pytest.mark.asyncio
async def test_resume_dive_prompt_includes_turn_budget_and_intro_projects():
    from app.agents.nodes.resume_dive import resume_dive_node

    captured = {}

    async def capture_messages(messages):
        captured["system"] = messages[0].content
        return fake_ai_response("你在新闻幻觉检测项目里个人负责哪部分？")

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=capture_messages)

    state = make_state(
        current_node="resume_dive",
        phase_turn_count=1,
        resume_summary=(
            "项目：新闻幻觉检测与事件事实性识别\n"
            "项目：中医古典文献知识图谱构建系统\n"
            "项目：肿瘤编码识别与病理规范化\n"
        ),
        jd_text="要求具备RAG、Agent、Prompt Engineering项目经验。",
        messages=[
            HumanMessage(
                content=(
                    "我做过新闻幻觉检测、中医知识图谱和肿瘤编码微调三个项目，"
                    "其中新闻幻觉检测用到了RAG。"
                )
            )
        ],
    )

    with patch("app.agents.nodes.resume_dive._llm_with_tool", mock_llm):
        await resume_dive_node(state)

    system = captured["system"]
    assert "当前是简历深挖第 2 轮" in system
    assert "剩余 6 轮" in system
    assert "最大 8 轮" in system
    assert "新闻幻觉检测与事件事实性识别" in system
    assert "中医古典文献知识图谱构建系统" in system
    assert "肿瘤编码识别与病理规范化" in system
    assert "优先围绕候选人自我介绍中主动提到的项目" in system
