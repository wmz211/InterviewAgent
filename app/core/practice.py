"""Interview flow and phase-practice helpers."""
from __future__ import annotations

from typing import Literal, TypedDict


FULL_INTERVIEW = "full_interview"
PHASE_PRACTICE = "phase_practice"
FlowMode = Literal["full_interview", "phase_practice"]

TECH_PHASES = ("greeting", "resume_dive", "jd_tech", "coding_test", "wrap_up")
HR_PHASES = ("greeting", "hr_self_intro", "hr_behavioral", "hr_career", "wrap_up")
ALL_PHASES = tuple(dict.fromkeys((*TECH_PHASES, *HR_PHASES)))


class PracticeMetadata(TypedDict):
    practice_mode: bool
    selected_phase: str
    initial_phase: str


def phases_for_mode(interview_mode: str) -> tuple[str, ...]:
    return HR_PHASES if interview_mode == "hr" else TECH_PHASES


def is_valid_phase_for_mode(interview_mode: str, phase: str) -> bool:
    return phase in phases_for_mode(interview_mode)


def normalize_flow_mode(flow_mode: str) -> FlowMode:
    return PHASE_PRACTICE if flow_mode == PHASE_PRACTICE else FULL_INTERVIEW


def build_practice_metadata(
    interview_mode: str,
    flow_mode: str = FULL_INTERVIEW,
    selected_phase: str = "",
) -> PracticeMetadata:
    normalized_flow = normalize_flow_mode(flow_mode)
    if normalized_flow != PHASE_PRACTICE:
        return {
            "practice_mode": False,
            "selected_phase": "",
            "initial_phase": "greeting",
        }

    if not is_valid_phase_for_mode(interview_mode, selected_phase):
        return {
            "practice_mode": True,
            "selected_phase": "",
            "initial_phase": "greeting",
        }

    return {
        "practice_mode": True,
        "selected_phase": selected_phase,
        "initial_phase": selected_phase,
    }
