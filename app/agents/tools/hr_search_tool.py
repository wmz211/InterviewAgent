"""HR 行为面试题检索工具。"""
from langchain_core.tools import tool
from app.rag.vector_store.retriever import _query_collection, _format_results
from app.config import get_settings
import json

settings = get_settings()


@tool
def vector_search_hr_questions(
    asked_ids: list[str] | None = None,
    k: int = 1,
) -> str:
    """
    从 HR 行为面试题库中检索一道还没问过的题目。

    Args:
        asked_ids: 已问过的题目 ID 列表，避免重复。如 ["hr_001", "hr_003"]
        k:         返回题目数量，默认 1

    Returns:
        JSON 字符串，包含 {id, text, category}
    """
    asked = set(asked_ids or [])
    results = _query_collection(
        collection_name=settings.chroma_collection_hr,
        query="行为面试 STAR 经历",
        n_results=10,
    )
    for r in results:
        qid = r.get("topic", "")  # We store id in topic field
        if qid not in asked:
            return json.dumps(
                {"id": qid, "text": r["question"], "category": r.get("question_type", "")},
                ensure_ascii=False,
            )
    # 全部问完，循环重用第一题
    if results:
        r = results[0]
        return json.dumps(
            {"id": r.get("topic", ""), "text": r["question"], "category": r.get("question_type", "")},
            ensure_ascii=False,
        )
    return json.dumps({"id": "", "text": "请描述一次你在压力下完成重要任务的经历。", "category": "pressure"}, ensure_ascii=False)


HR_TOOLS = [vector_search_hr_questions]
