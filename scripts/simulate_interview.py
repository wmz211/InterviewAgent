"""
模拟面试自问自答脚本 — 展示完整 LangGraph 流程
============================================================
候选人：苏州大学软件工程本科生（RAG / LLM / NLP 方向）
目标：展示工具调用、节点转换、phase_turn_count 变化

用法：
    python -m scripts.simulate_interview
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import textwrap
import uuid

# ─── Force UTF-8 output on Windows ───────────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─── Add project root to path ────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage

from app.core.interview_graph import get_interview_graph, make_initial_state

# ══════════════════════════════════════════════════════════════════════
# 候选人简历摘要（真实简历精简版）
# ══════════════════════════════════════════════════════════════════════
RESUME_SUMMARY = """\
姓名：张伟（化名）
学校：苏州大学 软件工程 本科（2021-2025）GPA 3.8/4.0
技能：Python, PyTorch, LangChain/LangGraph, Neo4j, ChromaDB, HuggingFace, LLaMA-Factory

项目经历：
1. 【LLM幻觉检测系统】（IJCAI 2026 在投）
   - 构建 RAG 验证链路：检索增强 + 网络搜索，缓解 LLM 幻觉
   - 使用 ICL+CoT Prompt 策略进行多步推理与事实核验
   - 技术栈：all-MPNet-base-v2 Embedding, ChromaDB, Qwen2.5-7B

2. 【中医知识图谱问答系统】
   - 用 Neo4j 构建中医实体关系图谱（8000+ 节点）
   - LangChain 封装 LLM Agent 完成图谱问答
   - 技术栈：Cypher, BERT-BiLSTM-CRF 命名实体识别

3. 【肿瘤编码 SFT 微调】
   - 使用 LLaMA-Factory 对 Qwen2.5-7B 进行 SFT 监督微调
   - LoRA 低秩适配 + 混合精度训练（BF16）
   - 技术栈：LLaMA-Factory, PEFT, DeepSpeed
"""

JD_TEXT = """\
岗位：大模型算法工程师（实习）
要求：
- 熟悉 Transformer 架构，了解 Attention 机制原理
- 有 RAG / 知识库问答系统开发经验
- 熟悉 LLM 微调方法（SFT/LoRA/RLHF）
- 了解 LangChain/LangGraph Agent 框架
- 加分：有 AI 论文发表或竞赛经历
"""

# 锚定实体（由 build_session_graph 在真实流程中生成；这里手动预置）
ANCHORED_ENTITIES = [
    {"resume_text": "RAG验证链路",      "kg_node_id": "rag",               "kg_node_label": "RAG",               "confidence": 1.0},
    {"resume_text": "ICL+CoT Prompt",   "kg_node_id": "prompt_engineering", "kg_node_label": "Prompt Engineering", "confidence": 0.95},
    {"resume_text": "CoT多步推理",      "kg_node_id": "cot",               "kg_node_label": "Chain of Thought",   "confidence": 0.92},
    {"resume_text": "all-MPNet Embedding","kg_node_id": "embedding",        "kg_node_label": "Embedding",          "confidence": 1.0},
    {"resume_text": "LangChain Agent",  "kg_node_id": "llm_agent",         "kg_node_label": "LLM Agent",          "confidence": 1.0},
    {"resume_text": "LLaMA-Factory SFT","kg_node_id": "fine_tuning",       "kg_node_label": "Fine-tuning",        "confidence": 1.0},
]

# ══════════════════════════════════════════════════════════════════════
# 模拟候选人回答（按面试阶段预设）
# ══════════════════════════════════════════════════════════════════════
CANDIDATE_REPLIES = [
    # ── greeting 阶段（2轮触发转换）────────────────────────────────
    "你好！我叫张伟，是苏州大学软件工程大四学生。我主要做大模型相关方向，"
    "参与了一篇幻觉检测的论文投 IJCAI，同时做过中医知识图谱和肿瘤编码微调的项目，"
    "技术栈主要是 Python、LangChain、Neo4j、LLaMA-Factory 这些。",

    "对，我对 RAG 这块比较感兴趣，主要用它来做幻觉缓解。知识图谱那边我用 Neo4j 做过"
    "中医的实体关系构建，用 Cypher 写查询，感觉图谱和向量检索结合起来效果更好。",

    # ── resume_dive 阶段（6轮触发转换）─────────────────────────────
    "RAG 的核心思路是先用 Embedding 把问题转成向量，然后在向量数据库里检索相关文档片段，"
    "把检索结果拼进 Prompt 里给 LLM 生成答案，避免 LLM 直接靠参数记忆瞎说。",

    "向量检索用的是余弦相似度，存储用 ChromaDB，Embedding 模型用的 all-MPNet-base-v2。"
    "检索出来的片段我会做一个重排序，然后控制 top-k 数量防止上下文太长。",

    "幻觉缓解方面，我加了网络搜索作为第二通道验证。先 RAG 召回本地知识，"
    "再用 Tavily API 搜实时信息，两路结果对比，用 CoT 让模型自己判断哪个更可信。",

    "CoT 这边我用的是 few-shot ICL，给几个推理示例让模型学会'先检索—再推理—最后核验'的步骤。"
    "效果比 zero-shot 好挺多，尤其对事实性问题准确率提升了大概 15%。",

    # ── cs_fundamentals 阶段（4轮触发转换）─────────────────────────
    "Attention 机制本质是做加权求和，Query 和 Key 计算相似度得到权重，再对 Value 加权。"
    "Self-Attention 就是 Q/K/V 都来自同一序列，Multi-Head 是把向量切多份并行做 Attention，"
    "捕捉不同子空间的关系，最后拼接。时间复杂度是 O(n²d)，序列长了会很贵。",

    "LoRA 的思路是冻结原模型权重，在每个线性层旁边插一个低秩矩阵 A×B，"
    "A 和 B 的秩 r 远小于原始维度，参数量大幅减少。推理时可以把 ΔW=AB 合并进原权重，"
    "没有额外延迟。我们项目用 r=8，可训练参数大概只有全量微调的 0.1%。",

    "RAG 相比纯微调的优势是知识更新成本低，换文档库就行，不用重新训练。"
    "但 RAG 的问题是检索质量直接影响生成质量，如果召回噪声多，模型可能被带偏。"
    "微调的优势是模型能内化知识，推理更快，但更新知识代价大，而且容易灾难性遗忘。",

    # ── coding_test 阶段（3轮触发转换）─────────────────────────────
    "这道题我的思路是动态规划。定义 dp[i] 为以 nums[i] 结尾的最长上升子序列长度，"
    "转移：dp[i] = max(dp[j]+1) for j<i if nums[j]<nums[i]，初始值都是 1。"
    "时间复杂度 O(n²)，空间 O(n)。如果要优化到 O(n log n) 可以用二分+贪心维护一个 tails 数组。",

    "边界情况：空数组返回 0，单元素返回 1。如果有重复元素，等于号不能触发转移，"
    "要严格小于。O(n log n) 版本用 bisect_left 找插入位置，tails 数组不是真实的子序列，"
    "但长度代表最优答案。",
]

# ══════════════════════════════════════════════════════════════════════
# 打印辅助函数
# ══════════════════════════════════════════════════════════════════════
DIVIDER   = "═" * 70
THIN_LINE = "─" * 70

def print_section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)

def print_field(label: str, value: str, indent: int = 2):
    prefix = " " * indent
    wrapped = textwrap.fill(value, width=68, subsequent_indent=prefix + "  ")
    print(f"{prefix}【{label}】{wrapped}")

def _extract_text(msg) -> str:
    """Extract plain text from a message (handles str / list content)."""
    c = getattr(msg, "content", "")
    if isinstance(c, list):
        parts = []
        for item in c:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return " ".join(p for p in parts if p)
    return str(c)


def display_response(state: dict, turn: int, candidate_text: str, prev_msg_count: int = 0):
    """Pretty-print one turn of the interview."""
    all_msgs = state.get("messages", [])
    msgs = all_msgs[prev_msg_count:]  # only new messages from this turn
    current_node = state.get("current_node", "?")
    phase_turn   = state.get("phase_turn_count", 0)
    transitioning = state.get("should_transition", False)

    print(f"\n{'─'*70}")
    print(f"  Turn {turn:02d} │ node={current_node} │ phase_turn={phase_turn} │ transition={transitioning}")
    print(f"{'─'*70}")

    # Candidate input
    print_field("候选人", candidate_text)

    # Show all new messages (tool calls / tool results / final answer)
    for msg in msgs:
        mtype = type(msg).__name__

        if mtype == "AIMessage":
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    print(f"\n  TC [Tool Call] {tc['name']}")
                    for k, v in tc["args"].items():
                        v_str = str(v)[:120] + ("…" if len(str(v)) > 120 else "")
                        print(f"       {k}: {v_str}")
            else:
                text = _extract_text(msg)
                if text:
                    print(f"\n  >> [面试官]")
                    for line in textwrap.wrap(text, width=66):
                        print(f"     {line}")

        elif mtype == "ToolMessage":
            content = _extract_text(msg)[:300]
            print(f"\n  ** [Tool Result] (截断300字)")
            for line in content.splitlines()[:12]:
                print(f"     {line}")

    if transitioning:
        print(f"\n  [OK] 阶段结束 -> 即将进入下一阶段")


# ══════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════
async def main():
    session_id = str(uuid.uuid4())[:8]
    graph = get_interview_graph()

    print_section(f"InterviewAgent 模拟面试  [session={session_id}]")
    print(f"  候选人简历：苏州大学软件工程 · RAG/LLM/Neo4j 方向")
    print(f"  锚定实体数：{len(ANCHORED_ENTITIES)}")
    print(f"  图谱节点  ：{', '.join(e['kg_node_label'] for e in ANCHORED_ENTITIES)}")
    print(f"\n  面试阶段规划：")
    print(f"    greeting(2轮) → resume_dive(6轮) → cs_fundamentals(4轮)")
    print(f"                  → coding_test(3轮) → wrap_up")

    # Build initial state
    state = make_initial_state(
        session_id=session_id,
        resume_summary=RESUME_SUMMARY,
        jd_text=JD_TEXT,
        anchored_entities=ANCHORED_ENTITIES,
    )

    # ── Turn 0: 面试官开场白（无候选人输入）─────────────────────────
    print_section("TURN 00 │ 面试官开场 (greeting)")
    result = await graph.ainvoke(state)
    state.update(result)

    # Show opening message
    msgs = result.get("messages", [])
    for msg in msgs:
        text = _extract_text(msg)
        if text:
            print(f"\n  >> [面试官开场]")
            for line in textwrap.wrap(text, width=66):
                print(f"     {line}")
    print(f"\n  node={result.get('current_node')} │ phase_turn={result.get('phase_turn_count')}")

    # ── Turns 1-N: 候选人回答 + 面试官追问 ──────────────────────────
    for turn_idx, candidate_reply in enumerate(CANDIDATE_REPLIES, start=1):
        phase_before = state.get("current_node", "greeting")
        print_section(f"TURN {turn_idx:02d} │ 当前阶段: {phase_before.upper()}")

        # Append candidate reply and record message count BEFORE invocation
        state["messages"] = state.get("messages", []) + [
            HumanMessage(content=candidate_reply)
        ]
        prev_count = len(state["messages"])  # includes the candidate HumanMessage

        result = await graph.ainvoke(state)
        state.update(result)

        # prev_count already includes the HumanMessage; new msgs start after it
        display_response(result, turn_idx, candidate_reply, prev_msg_count=prev_count)

    # ── Final wrap-up ────────────────────────────────────────────────
    print_section("WRAP UP │ 面试结束")
    # Force state to wrap_up if not already
    if state.get("current_node") not in ("wrap_up",):
        state["current_node"] = "wrap_up"
        state["phase_turn_count"] = 0

    result = await graph.ainvoke(state)
    state.update(result)
    for msg in result.get("messages", []):
        text = _extract_text(msg)
        if text:
            print(f"\n  >> [面试官总结]")
            for line in textwrap.wrap(text, width=66):
                print(f"     {line}")

    print_section("模拟结束 — 状态汇总")
    scores = state.get("node_scores", {})
    for phase, info in scores.items():
        print(f"  {phase:20s}: {info}")
    print(f"\n  interview_complete = {state.get('interview_complete', False)}")
    print(f"  candidate_name     = {state.get('candidate_name', '(未提取)')}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
