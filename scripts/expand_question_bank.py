"""
LLM-assisted question bank expansion script.

Usage:
    # 预览，不写入文件
    python scripts/expand_question_bank.py --topic "Fine-tuning" --count 5 --difficulty hard --dry-run

    # 生成并追加到 llm_questions.json，然后导入 ChromaDB
    python scripts/expand_question_bank.py --topic "Transformer" --count 8 --difficulty medium

    # 生成算法题
    python scripts/expand_question_bank.py --type algorithm --topic "动态规划" --count 3 --difficulty hard
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from openai import OpenAI
from app.config import get_settings

settings = get_settings()

QUESTION_BANK_DIR = Path("data/question_bank")
LLM_QUESTIONS_FILE   = QUESTION_BANK_DIR / "llm_questions.json"
ALGO_QUESTIONS_FILE  = QUESTION_BANK_DIR / "algorithm_problems.json"

# ── Prompts ────────────────────────────────────────────────────────────

_LLM_QUESTION_PROMPT = """\
你是一位资深大厂技术面试官，擅长考察 AI/LLM 方向的深度理解。

请为技术主题「{topic}」生成 {count} 道面试题，难度为「{difficulty}」。
严格按照以下 JSON 数组格式输出，不要任何解释或 markdown 代码块。

要求：
- question: 面试官提问（简洁，口语化，15-50字）
- answer: 详细参考答案（包含原理、关键点、可能的延伸，200-400字）
- topic: 固定填写 "{topic}"
- difficulty: 固定填写 "{difficulty}"
- question_type: conceptual(原理概念) / practical(实践经验) / pitfall(常见坑点) 三选一

输出格式（纯 JSON 数组）：
[
  {{
    "question": "...",
    "answer": "...",
    "topic": "{topic}",
    "difficulty": "{difficulty}",
    "question_type": "conceptual"
  }}
]"""

_ALGO_QUESTION_PROMPT = """\
你是一位大厂算法面试官。请为「{topic}」方向生成 {count} 道算法编程题，难度为「{difficulty}」。
严格按照以下 JSON 数组格式输出，不要任何解释或 markdown 代码块。

要求：
- question: 题目描述（包含输入输出格式和示例）
- answer: 解题思路 + 关键代码（Python），200-400字
- topic: 固定填写 "{topic}"
- difficulty: "{difficulty}"
- question_type: 固定填写 "algorithm"
- time_complexity: 时间复杂度，如 "O(n log n)"
- space_complexity: 空间复杂度，如 "O(n)"

输出格式（纯 JSON 数组）：
[
  {{
    "question": "...",
    "answer": "...",
    "topic": "{topic}",
    "difficulty": "{difficulty}",
    "question_type": "algorithm",
    "time_complexity": "...",
    "space_complexity": "..."
  }}
]"""


# ── Core functions ─────────────────────────────────────────────────────

def generate_questions(
    topic: str,
    count: int,
    difficulty: str,
    question_type: str,  # "llm" or "algorithm"
) -> list[dict]:
    client = OpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.llm_base_url,
    )

    prompt = (_ALGO_QUESTION_PROMPT if question_type == "algorithm" else _LLM_QUESTION_PROMPT).format(
        topic=topic, count=count, difficulty=difficulty,
    )

    response = client.chat.completions.create(
        model=settings.llm_model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    raw = response.choices[0].message.content.strip()

    # Strip markdown code block if present
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]

    return json.loads(raw.strip())


def append_to_file(questions: list[dict], target_file: Path) -> int:
    """Append new questions to JSON file, skip duplicates by question text."""
    existing = []
    if target_file.exists():
        with open(target_file, encoding="utf-8") as f:
            existing = json.load(f)

    existing_questions = {q["question"] for q in existing}
    new_questions = [q for q in questions if q["question"] not in existing_questions]

    if new_questions:
        existing.extend(new_questions)
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    return len(new_questions)


def reimport_to_chromadb(target_file: Path, collection_name: str) -> None:
    """Re-index the updated file into ChromaDB."""
    from app.rag.vector_store.indexer import index_question_bank
    count = index_question_bank(target_file.name, collection_name)
    print(f"ChromaDB: upserted {count} documents into '{collection_name}'")


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Expand question bank via LLM")
    parser.add_argument("--topic",      required=True, help="技术主题，如 'RAG' / '动态规划'")
    parser.add_argument("--count",      type=int, default=5, help="生成题目数量（默认5）")
    parser.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    parser.add_argument("--type",       default="llm", choices=["llm", "algorithm"],
                        help="题库类型：llm=八股题，algorithm=算法题（默认llm）")
    parser.add_argument("--dry-run",    action="store_true", help="只预览，不写入文件")
    args = parser.parse_args()

    target_file = ALGO_QUESTIONS_FILE if args.type == "algorithm" else LLM_QUESTIONS_FILE
    collection  = "algorithm_problems" if args.type == "algorithm" else "interview_questions"

    print(f"Generating {args.count} [{args.difficulty}] {args.type} questions for '{args.topic}'...")
    questions = generate_questions(args.topic, args.count, args.difficulty, args.type)

    print(f"\n── Generated {len(questions)} questions ──────────────────────")
    for i, q in enumerate(questions, 1):
        print(f"\nQ{i} [{q.get('difficulty')}] [{q.get('question_type')}]")
        print(f"  问题: {q['question']}")
        print(f"  答案: {q['answer'][:100]}...")
    print("─────────────────────────────────────────────────────────\n")

    if args.dry_run:
        print("[dry-run] 未写入文件。去掉 --dry-run 参数即可写入。")
        return

    confirm = input("写入文件并导入 ChromaDB？[y/N] ").strip().lower()
    if confirm != "y":
        print("已取消。")
        return

    added = append_to_file(questions, target_file)
    print(f"文件更新：新增 {added} 题（跳过重复）→ {target_file}")

    reimport_to_chromadb(target_file, collection)
    print("完成！")


if __name__ == "__main__":
    main()
