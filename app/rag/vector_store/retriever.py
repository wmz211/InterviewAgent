"""
VectorDB retrieval tool — exposed to LangGraph agent via Tool Calling.

Two retrieval modes:
  1. Semantic only:    query text → top-k similar questions
  2. Semantic + filter: query + topic/difficulty filter → targeted questions

Used by:
  CS_Fundamentals node → query by JD topic keywords
  Coding_Test node     → query algorithm_problems collection
"""
from __future__ import annotations

from langchain_core.tools import tool
from loguru import logger

from app.config import get_settings
from app.rag.vector_store.client import get_chroma_client

settings = get_settings()


def _query_collection(
    collection_name: str,
    query: str,
    n_results: int = 3,
    where: dict | None = None,
) -> list[dict]:
    """
    Core retrieval function. Returns list of question dicts with metadata.
    `where` is a ChromaDB metadata filter, e.g. {"difficulty": "hard"} or
    {"$and": [{"topic": "RAG"}, {"difficulty": "hard"}]}.
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(collection_name)
    except Exception:
        logger.warning(f"Collection '{collection_name}' not found. Run init_vector_db.py first.")
        return []

    kwargs = dict(query_texts=[query], n_results=n_results, include=["documents", "metadatas", "distances"])
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({
            "question":      meta.get("question", ""),
            "answer":        doc.split("\n\n", 1)[-1] if "\n\n" in doc else doc,
            "topic":         meta.get("topic", ""),
            "difficulty":    meta.get("difficulty", ""),
            "question_type": meta.get("question_type", ""),
            "relevance":     round(1 - dist, 3),   # cosine: distance→similarity
        })

    logger.debug(f"VectorDB query '{query[:30]}...' → {len(output)} results from '{collection_name}'")
    return output


def _format_results(results: list[dict], context_label: str) -> str:
    if not results:
        return f"[VectorDB] 未检索到相关题目，请尝试调整 topic 或 difficulty 参数。"

    lines = [f"## 向量检索结果：{context_label}", ""]
    for i, r in enumerate(results, 1):
        lines += [
            f"### Q{i} [{r['difficulty']}] {r['topic']} — {r['question_type']}",
            f"**问题**：{r['question']}",
            f"**参考答案**：{r['answer']}",
            f"*相关度: {r['relevance']}*",
            "",
        ]
    lines += [
        "---",
        "### 面试官指令",
        "请从以上题目中选择最适合当前对话节奏的一题，",
        "用口语化、自然的方式向候选人提问。不要直接读题，要自然引入。",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Tool 1: 通用知识题库检索（CS_Fundamentals 节点使用）
# ══════════════════════════════════════════════════════════════════════

@tool
def vector_search_questions(
    query: str,
    topic: str = "",
    difficulty: str = "",
    n_results: int = 3,
) -> str:
    """
    从八股/专业知识题库中检索与当前面试话题最相关的题目。

    在 CS_Fundamentals 节点使用：根据 JD 关键词或当前对话话题，
    召回标准面试题供面试官参考出题。

    Args:
        query:      检索关键词，如 "Transformer attention mechanism" 或 "RAG召回优化"
        topic:      可选，按话题过滤，如 "Transformer" / "RAG" / "Fine-tuning"
        difficulty: 可选，按难度过滤，easy / medium / hard
        n_results:  返回题目数量，默认 3

    Returns:
        结构化的题目列表字符串，包含问题、参考答案、难度信息，供 LLM 出题参考。
    """
    where = None
    filters = []
    if topic:
        filters.append({"topic": topic})
    if difficulty:
        filters.append({"difficulty": difficulty})

    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    results = _query_collection(
        collection_name=settings.chroma_collection_questions,
        query=query,
        n_results=n_results,
        where=where,
    )
    return _format_results(results, context_label=query)


# ══════════════════════════════════════════════════════════════════════
# Tool 2: 算法题检索（Coding_Test 节点使用）
# ══════════════════════════════════════════════════════════════════════

@tool
def vector_search_algorithms(
    query: str,
    difficulty: str = "",
    n_results: int = 2,
) -> str:
    """
    从算法题库中检索适合当前面试的编程题。

    在 Coding_Test 节点使用：根据候选人技术背景和 JD 要求，
    召回匹配的算法题。

    Args:
        query:      检索关键词，如 "动态规划背包" 或 "二叉树层序遍历" 或 "字符串滑动窗口"
        difficulty: 可选，按难度过滤，easy / medium / hard
        n_results:  返回题目数量，默认 2

    Returns:
        算法题描述和约束条件，供面试官向候选人出题。
    """
    where = {"difficulty": difficulty} if difficulty else None

    results = _query_collection(
        collection_name=settings.chroma_collection_algorithms,
        query=query,
        n_results=n_results,
        where=where,
    )
    return _format_results(results, context_label=f"算法题：{query}")


# ── 对外暴露工具列表 ──────────────────────────────────────────────────
VECTOR_TOOLS = [vector_search_questions, vector_search_algorithms]
