from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_resume_dive_prompt_limits_low_value_prompt_chasing():
    src = _source("app/agents/nodes/resume_dive.py")

    assert "LOW_VALUE_FOLLOWUP_GUARD" in src
    assert "Do not ask for full prompt text" in src
    assert "Do not ask the candidate to reveal chain-of-thought" in src
    assert "move to design tradeoffs, evaluation, failure cases, or engineering details" in src
    assert "REPEAT_AVOIDANCE_GUARD" in src
    assert "RESUME_DIVE_MEMORY" in src
    assert "CLOSED_LOW_SIGNAL" in src


def test_jd_tech_prompt_limits_low_value_prompt_chasing():
    src = _source("app/agents/nodes/jd_tech.py")

    assert "LOW_VALUE_FOLLOWUP_GUARD" in src
    assert "Do not ask for full prompt text" in src
    assert "At most one clarification question about prompt strategy" in src
