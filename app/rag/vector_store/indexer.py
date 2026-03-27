"""
Indexer: load question bank JSON → ChromaDB.

Run once via:  python scripts/init_vector_db.py
"""
from __future__ import annotations

import json
from pathlib import Path

import chromadb
from loguru import logger

from app.config import get_settings
from app.rag.vector_store.client import get_chroma_client

settings = get_settings()

QUESTION_BANK_DIR = Path(__file__).parents[3] / "data" / "question_bank"


def _get_or_create_collection(
    client: chromadb.PersistentClient,
    name: str,
) -> chromadb.Collection:
    """Get collection if it exists, create if not."""
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},   # cosine similarity for semantic search
    )


def index_question_bank(json_filename: str, collection_name: str) -> int:
    """
    Load a question bank JSON file and upsert all entries into ChromaDB.

    Each document = "question\\n\\nanswer" text for embedding.
    Returns count of indexed documents.
    """
    json_path = QUESTION_BANK_DIR / json_filename
    if not json_path.exists():
        logger.error(f"Question bank file not found: {json_path}")
        return 0

    with open(json_path, encoding="utf-8") as f:
        questions = json.load(f)

    client = get_chroma_client()
    collection = _get_or_create_collection(client, collection_name)

    ids, documents, metadatas = [], [], []

    for i, q in enumerate(questions):
        doc_id = f"{json_filename}_{i}"
        # Embedding target: question + answer together for richer semantic coverage
        document = f"{q['question']}\n\n{q['answer']}"

        metadata = {
            "question":      q["question"],
            "topic":         q.get("topic", ""),
            "difficulty":    q.get("difficulty", "medium"),
            "question_type": q.get("question_type", "conceptual"),
        }

        ids.append(doc_id)
        documents.append(document)
        metadatas.append(metadata)

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    logger.info(f"Indexed {len(ids)} questions into collection '{collection_name}'")
    return len(ids)


HR_SEED_QUESTIONS = [
    {"id": "hr_001", "question": "请用 STAR 法则描述一次你主动承担超出职责范围的任务的经历。", "category": "initiative"},
    {"id": "hr_002", "question": "讲一个你与团队成员发生分歧、最终达成共识的具体案例。", "category": "collaboration"},
    {"id": "hr_003", "question": "描述一次你在压力下（时间紧、资源有限）完成重要任务的经历。", "category": "pressure"},
    {"id": "hr_004", "question": "给我一个你犯了错误、然后如何处理和复盘的例子。", "category": "resilience"},
    {"id": "hr_005", "question": "讲一个你需要快速学习一项新技能来完成工作的案例。", "category": "learning"},
    {"id": "hr_006", "question": "描述你如何推动一个没有明确负责人的问题得到解决。", "category": "ownership"},
    {"id": "hr_007", "question": "讲一个你需要说服他人接受你的方案的经历，你是怎么做的？", "category": "influence"},
    {"id": "hr_008", "question": "给我一个你的决策结果不如预期、你如何调整的例子。", "category": "adaptability"},
    {"id": "hr_009", "question": "描述一次你帮助团队成员成长或解决问题的经历。", "category": "mentoring"},
    {"id": "hr_010", "question": "讲一个你需要在多个高优先级任务之间做取舍的案例，你的判断依据是什么？", "category": "prioritization"},
]


def index_hr_questions() -> int:
    """Upsert HR behavioral questions into ChromaDB."""
    client = get_chroma_client()
    collection = _get_or_create_collection(client, settings.chroma_collection_hr)
    ids, documents, metadatas = [], [], []
    for q in HR_SEED_QUESTIONS:
        ids.append(q["id"])
        documents.append(q["question"])
        metadatas.append({
            "question": q["question"],
            "topic": q["id"],           # re-use topic field as id for retrieval
            "difficulty": "medium",
            "question_type": q["category"],
        })
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    logger.info(f"Indexed {len(ids)} HR questions into '{settings.chroma_collection_hr}'")
    return len(ids)


def index_all() -> dict[str, int]:
    """Index all question banks into ChromaDB."""
    results = {}
    mapping = {
        "llm_questions.json": settings.chroma_collection_questions,
        "algorithm_problems.json": settings.chroma_collection_algorithms,
    }
    for filename, collection in mapping.items():
        if (QUESTION_BANK_DIR / filename).exists():
            results[collection] = index_question_bank(filename, collection)
        else:
            logger.warning(f"Skipping missing file: {filename}")
    results[settings.chroma_collection_hr] = index_hr_questions()
    return results
