"""
面试评估引擎 — 对各阶段 QA 记录进行 LLM 打分，生成结构化评估报告。

评估维度：
  - resume_dive:     技术深度（对自己项目的掌握程度）
  - cs_fundamentals: 基础知识（答题准确性与完整性）
  - coding_test:     算法能力（思路、复杂度、边界）
  - 综合：           表达能力、JD 匹配度、综合评级
"""
from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI
from loguru import logger

from app.agents.nodes.base import make_llm
from app.core.state import InterviewState

# ── Scoring thresholds ─────────────────────────────────────────────────
WEAK_THRESHOLD = 6      # score < 6 → is_weak = True
PASS_THRESHOLD = 6.5    # overall ≥ 6.5 → 建议录用

# ── Phase weight for overall score ────────────────────────────────────
PHASE_WEIGHTS = {
    "resume_dive":     0.35,
    "cs_fundamentals": 0.35,
    "coding_test":     0.30,
}

# ── LLM prompt ────────────────────────────────────────────────────────
_EVAL_SYSTEM = """\
你是一位资深技术面试评估专家。请对以下面试问答记录进行打分和点评。

评分规则（0-10分）：
- 9-10：回答准确、完整、有深度，甚至超出预期
- 7-8 ：主要知识点正确，有一定深度，但存在小的遗漏或不够精确的地方
- 5-6 ：知识点部分正确，有明显遗漏或错误，但方向对
- 3-4 ：回答方向基本正确但内容空洞，或有关键错误
- 0-2 ：回答严重错误、答非所问或完全不会

对于得分 < {weak_threshold} 的题目，必须给出：
1. correct_answer：标准答案（清晰、完整、可以直接学习使用）
2. study_suggestions：具体的补充学习建议（学什么、看什么资料）

【面试阶段】{phase}
【参考资料（含标准答案片段）】
{tool_materials}

【问答记录】
{qa_text}

请严格按照以下 JSON 格式输出，不要有任何解释文字：
[
  {{
    "turn": <题目编号>,
    "score": <0-10的整数或一位小数>,
    "is_weak": <true/false>,
    "feedback": "<对候选人回答的简短点评（1-3句）>",
    "correct_answer": "<标准答案，如果 is_weak=true；否则留空字符串>",
    "study_suggestions": ["<建议1>", "<建议2>"]
  }}
]
"""

_SUMMARY_SYSTEM = """\
你是一位资深技术面试评估专家。根据以下面试数据，生成一份完整的面试评估报告。

【候选人】{candidate_name}
【应聘岗位】{jd_summary}

【各阶段得分】
{phase_scores}

【薄弱题目汇总】
{weak_items}

请输出以下 JSON 格式的评估报告（不要有解释文字）：
{{
  "dimension_scores": {{
    "technical_depth": <项目技术深度，0-10>,
    "cs_fundamentals": <基础知识，0-10>,
    "coding_ability":  <算法能力，0-10>,
    "communication":   <表达清晰度，0-10>,
    "jd_match":        <与岗位匹配度，0-10>
  }},
  "overall_score": <加权综合得分，0-10，保留一位小数>,
  "recommendation": "强烈推荐录用 | 建议录用 | 待定，需进一步考察 | 不建议录用",
  "summary": "<3-5句话的候选人综合评价>",
  "strengths": ["<优势1>", "<优势2>", "<优势3>"],
  "improvement_areas": ["<待提升方向1>", "<待提升方向2>"]
}}
"""


async def evaluate_interview(state: InterviewState) -> dict:
    """
    Main entry point. Branches on interview_mode: 'tech' or 'hr'.
    """
    mode = state.get("interview_mode", "tech")
    if mode == "hr":
        return await _evaluate_hr(state)
    return await _evaluate_tech(state)


async def _evaluate_tech(state: InterviewState) -> dict:
    """Tech track evaluation (resume_dive + jd_tech)."""
    llm = make_llm(temperature=0)
    node_scores: dict[str, Any] = state.get("node_scores", {})

    phase_avg_scores: dict[str, float] = {}
    all_weak_items: list[dict] = []

    # ── Step 1: Score each phase ───────────────────────────────────────
    for phase in ("resume_dive", "jd_tech", "coding_test"):
        phase_data = node_scores.get(phase, {})
        qa_records: list[dict] = phase_data.get("qa_records", [])

        if not qa_records:
            logger.warning(f"No QA records for phase {phase}, skipping evaluation")
            continue

        scored = await _score_phase(llm, phase, qa_records)

        # Write scores back into phase_data
        for record in qa_records:
            turn = record["turn"]
            scored_item = next((s for s in scored if s.get("turn") == turn), None)
            if scored_item:
                record["score"] = scored_item.get("score", 5)
                record["is_weak"] = scored_item.get("is_weak", False)
                record["feedback"] = scored_item.get("feedback", "")
                record["correct_answer"] = scored_item.get("correct_answer", "")
                record["study_suggestions"] = scored_item.get("study_suggestions", [])
                if record["is_weak"]:
                    all_weak_items.append({
                        "phase": phase,
                        "question": record["question"] or record["new_question"],
                        "answer": record["answer"],
                        "score": record["score"],
                        "feedback": record["feedback"],
                        "correct_answer": record["correct_answer"],
                        "study_suggestions": record["study_suggestions"],
                    })

        # Phase average (only records that have a real score and some content)
        valid_scores = [
            r["score"] for r in qa_records
            if r.get("score") is not None and (r.get("question") or r.get("answer"))
        ]
        phase_avg = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 5.0
        phase_avg_scores[phase] = phase_avg

    # ── Step 2: Overall summary ────────────────────────────────────────
    evaluation = await _generate_summary(
        llm=llm,
        candidate_name=state.get("candidate_name", "候选人"),
        jd_text=state.get("jd_text", ""),
        phase_avg_scores=phase_avg_scores,
        all_weak_items=all_weak_items,
    )
    evaluation["phase_scores"] = phase_avg_scores
    evaluation["weak_items"] = all_weak_items
    evaluation["total_questions"] = sum(
        len(node_scores.get(p, {}).get("qa_records", []))
        for p in ("resume_dive", "jd_tech", "coding_test")
    )
    evaluation["weak_count"] = len(all_weak_items)

    logger.info(
        f"Evaluation complete: overall={evaluation.get('overall_score')} "
        f"weak={len(all_weak_items)}/{evaluation['total_questions']}"
    )
    return evaluation


async def _score_phase(llm: ChatOpenAI, phase: str, qa_records: list[dict]) -> list[dict]:
    """Call LLM to score all QA records in one phase."""
    # Build readable Q&A text
    qa_lines = []
    for r in qa_records:
        q = r.get("question") or "(承接上一阶段)"
        a = r.get("answer") or "(无回答)"
        qa_lines.append(f"【题目{r['turn']}】问：{q}\n回答：{a}")

    qa_text = "\n\n".join(qa_lines)

    # Collect all tool_material as reference
    tool_materials = "\n---\n".join(
        r["tool_material"] for r in qa_records if r.get("tool_material")
    )[:3000]  # cap to avoid token overflow

    prompt = _EVAL_SYSTEM.format(
        weak_threshold=WEAK_THRESHOLD,
        phase=_phase_cn(phase),
        tool_materials=tool_materials or "（无参考资料）",
        qa_text=qa_text,
    )

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        if content.startswith("```"):
            content = "\n".join(content.splitlines()[1:])
        if content.endswith("```"):
            content = content[: content.rfind("```")]
        return json.loads(content)
    except Exception as e:
        logger.error(f"Phase {phase} scoring failed: {e}")
        # Return default scores on failure
        return [{"turn": r["turn"], "score": 5, "is_weak": False,
                 "feedback": "评估失败", "correct_answer": "", "study_suggestions": []}
                for r in qa_records]


async def _generate_summary(
    llm: ChatOpenAI,
    candidate_name: str,
    jd_text: str,
    phase_avg_scores: dict[str, float],
    all_weak_items: list[dict],
) -> dict:
    """Call LLM to generate the overall evaluation summary."""
    phase_scores_text = "\n".join(
        f"- {_phase_cn(p)}: {s}/10" for p, s in phase_avg_scores.items()
    )

    weak_text = ""
    if all_weak_items:
        for item in all_weak_items[:8]:  # cap at 8 weak items in prompt
            weak_text += (
                f"\n[{_phase_cn(item['phase'])}] 问：{item['question'][:80]}\n"
                f"  答：{item['answer'][:80]}\n"
                f"  得分：{item['score']}  点评：{item['feedback']}\n"
            )
    else:
        weak_text = "（无明显薄弱题目）"

    jd_summary = jd_text[:300] if jd_text else "未提供岗位描述"

    prompt = _SUMMARY_SYSTEM.format(
        candidate_name=candidate_name,
        jd_summary=jd_summary,
        phase_scores=phase_scores_text,
        weak_items=weak_text,
    )

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        if content.startswith("```"):
            content = "\n".join(content.splitlines()[1:])
        if content.endswith("```"):
            content = content[: content.rfind("```")]
        return json.loads(content)
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        avg = sum(phase_avg_scores.values()) / len(phase_avg_scores) if phase_avg_scores else 5.0
        return {
            "dimension_scores": {},
            "overall_score": round(avg, 1),
            "recommendation": "待定，需进一步考察",
            "summary": "评估报告生成失败，请人工复核。",
            "strengths": [],
            "improvement_areas": [],
        }


def _phase_cn(phase: str) -> str:
    return {
        "resume_dive":   "简历经历深挖",
        "jd_tech":       "JD 技术考察",
        "hr_self_intro": "自我介绍",
        "hr_behavioral": "行为面试",
        "hr_career":     "职业规划",
    }.get(phase, phase)


# ── HR 评估 ────────────────────────────────────────────────────────────

_HR_EVAL_SYSTEM = """\
你是一位资深 HR 面试评估专家。请对以下 HR 行为面试问答记录进行打分和点评。

评分规则（0-10分）：
- 9-10：STAR 四要素完整，结果量化，表达流畅有逻辑
- 7-8 ：三要素完整，result 缺少量化，但方向清晰
- 5-6 ：两要素，描述较空洞，缺少具体行动或结果
- 3-4 ：只有背景，无行动细节，空话套话为主
- 0-2 ：完全跑题或拒绝回答

【面试阶段】{phase}
【问答记录】
{qa_text}

请严格按以下 JSON 格式输出，不要有任何解释文字：
[
  {{
    "turn": <题目编号>,
    "score": <0-10的整数或一位小数>,
    "is_weak": <true/false，score < 6 时为 true>,
    "feedback": "<对候选人回答的简短点评（1-2句）>",
    "correct_answer": "",
    "study_suggestions": []
  }}
]
"""

_HR_SUMMARY_SYSTEM = """\
你是一位资深 HR 面试评估专家。根据以下面试数据，生成完整的 HR 面试评估报告。

【候选人】{candidate_name}
【应聘岗位】{jd_summary}

【各阶段得分】
{phase_scores}

【薄弱项汇总】
{weak_items}

请输出以下 JSON 格式（不要有解释文字）：
{{
  "dimension_scores": {{
    "communication":      <表达清晰度，0-10>,
    "star_quality":       <STAR 完整性，0-10>,
    "self_awareness":     <自我认知，0-10>,
    "motivation":         <求职动机，0-10>,
    "overall_impression": <整体印象，0-10>
  }},
  "overall_score": <加权综合得分，0-10，保留一位小数>,
  "recommendation": "强烈推荐录用 | 建议录用 | 待定，需进一步考察 | 不建议录用",
  "summary": "<3-5句话的候选人综合评价>",
  "strengths": ["<优势1>", "<优势2>"],
  "improvement_areas": ["<待提升方向1>", "<待提升方向2>"]
}}
"""


async def _evaluate_hr(state: InterviewState) -> dict:
    """HR track evaluation."""
    llm = make_llm(temperature=0)
    node_scores: dict[str, Any] = state.get("node_scores", {})

    phase_avg_scores: dict[str, float] = {}
    all_weak_items: list[dict] = []

    for phase in ("hr_self_intro", "hr_behavioral", "hr_career"):
        phase_data = node_scores.get(phase, {})
        qa_records: list[dict] = phase_data.get("qa_records", [])
        if not qa_records:
            continue

        qa_lines = []
        for r in qa_records:
            q = r.get("question") or "(承接上一阶段)"
            a = r.get("answer") or "(无回答)"
            qa_lines.append(f"【题目{r['turn']}】问：{q}\n回答：{a}")

        prompt = _HR_EVAL_SYSTEM.format(
            phase=_phase_cn(phase),
            qa_text="\n\n".join(qa_lines),
        )
        try:
            resp = await llm.ainvoke(prompt)
            content = resp.content.strip()
            if content.startswith("```"):
                content = "\n".join(content.splitlines()[1:])
            if content.endswith("```"):
                content = content[:content.rfind("```")]
            scored = json.loads(content)
        except Exception as e:
            logger.error(f"HR phase {phase} scoring failed: {e}")
            scored = [{"turn": r["turn"], "score": 5, "is_weak": False,
                       "feedback": "评估失败", "correct_answer": "", "study_suggestions": []}
                      for r in qa_records]

        for record in qa_records:
            si = next((s for s in scored if s.get("turn") == record["turn"]), None)
            if si:
                record["score"] = si.get("score", 5)
                record["is_weak"] = si.get("is_weak", False)
                record["feedback"] = si.get("feedback", "")
                record["correct_answer"] = ""
                record["study_suggestions"] = []
                if record["is_weak"]:
                    all_weak_items.append({
                        "phase": phase,
                        "question": record.get("question") or record.get("new_question", ""),
                        "answer": record.get("answer", ""),
                        "score": record["score"],
                        "feedback": record["feedback"],
                        "correct_answer": "",
                        "study_suggestions": [],
                    })

        valid = [r["score"] for r in qa_records if r.get("score") is not None]
        phase_avg_scores[phase] = round(sum(valid) / len(valid), 1) if valid else 5.0

    # Summary
    phase_scores_text = "\n".join(f"- {_phase_cn(p)}: {s}/10" for p, s in phase_avg_scores.items())
    weak_text = ""
    for item in all_weak_items[:6]:
        weak_text += f"\n[{_phase_cn(item['phase'])}] 问：{item['question'][:80]}\n  答：{item['answer'][:80]}\n  得分：{item['score']}\n"
    if not weak_text:
        weak_text = "（无明显薄弱项）"

    prompt = _HR_SUMMARY_SYSTEM.format(
        candidate_name=state.get("candidate_name", "候选人"),
        jd_summary=state.get("jd_text", "")[:300] or "未提供",
        phase_scores=phase_scores_text,
        weak_items=weak_text,
    )
    try:
        resp = await llm.ainvoke(prompt)
        content = resp.content.strip()
        if content.startswith("```"):
            content = "\n".join(content.splitlines()[1:])
        if content.endswith("```"):
            content = content[:content.rfind("```")]
        evaluation = json.loads(content)
    except Exception as e:
        logger.error(f"HR summary failed: {e}")
        avg = sum(phase_avg_scores.values()) / len(phase_avg_scores) if phase_avg_scores else 5.0
        evaluation = {
            "dimension_scores": {},
            "overall_score": round(avg, 1),
            "recommendation": "待定，需进一步考察",
            "summary": "HR 评估报告生成失败。",
            "strengths": [],
            "improvement_areas": [],
        }

    evaluation["phase_scores"] = phase_avg_scores
    evaluation["weak_items"] = all_weak_items
    evaluation["total_questions"] = sum(
        len(node_scores.get(p, {}).get("qa_records", []))
        for p in ("hr_self_intro", "hr_behavioral", "hr_career")
    )
    evaluation["weak_count"] = len(all_weak_items)
    return evaluation
