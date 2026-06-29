from app.agents.nodes.followup_policy import (
    build_resume_followup_memory,
    is_low_signal_answer,
)


def test_low_signal_answer_detects_no_or_unknown():
    assert is_low_signal_answer("\u6ca1\u6709\u3002")
    assert is_low_signal_answer("\u4e0d\u77e5\u9053")
    assert not is_low_signal_answer(
        "\u6211\u5f53\u65f6\u628a\u6bcf\u4e2a\u9636\u6bb5\u7684\u8f6e\u6b21\u548c\u7528\u65f6\u90fd\u8bb0\u5230\u65e5\u5fd7\u91cc\u505a\u4e86\u5bf9\u6bd4\u3002"
    )


def test_resume_followup_memory_marks_low_signal_turn_closed():
    memory = build_resume_followup_memory([
        {
            "turn": 6,
            "question": "\u4f60\u4eec\u5173\u6ce8\u4e86\u54ea\u4e9b\u6307\u6807\uff1f",
            "answer": "\u6ca1\u6709\u3002",
            "new_question": "\u597d\u7684\uff0c\u6211\u4eec\u6362\u4e00\u4e2a\u3002",
        }
    ])

    assert "CLOSED_LOW_SIGNAL" in memory
    assert "Do not repeat" in memory
    assert "candidate_answer" in memory
