"""Run the offline RAG retrieval evaluation and write a JSON report."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evals.rag_eval import (
    build_default_retrievers,
    build_chroma_neo4j_retrievers,
    build_graph_index,
    build_sentence_transformer_retrievers,
    evaluate_ablation,
    load_json,
)
from app.config import get_settings


GRAPH_PATH = PROJECT_ROOT / "data" / "tech_knowledge_graph.json"
CASES_PATH = PROJECT_ROOT / "evals" / "rag_cases.json"
REPORT_PATH = PROJECT_ROOT / "output" / "rag_eval_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RAG retrieval ablation evaluation.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--dense-backend",
        choices=("hashing", "sentence-transformer", "chroma-bge"),
        default="chroma-bge",
        help="Use chroma-bge for real system eval, sentence-transformer for local embedding eval, or hashing for CI.",
    )
    parser.add_argument(
        "--embedding-model",
        default="paraphrase-multilingual-MiniLM-L12-v2",
        help="SentenceTransformer model name when --dense-backend=sentence-transformer.",
    )
    return parser.parse_args()


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    args = parse_args()
    settings = get_settings()
    graph = load_json(GRAPH_PATH)
    cases = load_json(CASES_PATH)
    index = build_graph_index(graph)
    if args.dense_backend == "sentence-transformer":
        retrievers = build_sentence_transformer_retrievers(index, args.embedding_model)
        dense_backend = f"sentence-transformer:{args.embedding_model}"
        backend_status = {"sentence_transformer": "ok"}
    elif args.dense_backend == "chroma-bge":
        retrievers, backend_status = build_chroma_neo4j_retrievers(
            index=index,
            chroma_collection_name=settings.chroma_collection_graph_nodes,
            chroma_persist_dir=settings.chroma_persist_dir,
            chroma_embedding_model_name=settings.local_embedding_model_name,
            neo4j_uri=settings.neo4j_uri,
            neo4j_username=settings.neo4j_username,
            neo4j_password=settings.neo4j_password,
            neo4j_database=settings.neo4j_database,
        )
        dense_backend = f"chroma:{settings.chroma_collection_graph_nodes}:{settings.local_embedding_model_name}"
    else:
        retrievers = build_default_retrievers(index)
        dense_backend = "hashing"
        backend_status = {"hashing": "ok"}

    report = evaluate_ablation(cases, retrievers, top_k=args.top_k)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["graph_path"] = str(GRAPH_PATH.relative_to(PROJECT_ROOT))
    report["cases_path"] = str(CASES_PATH.relative_to(PROJECT_ROOT))
    report["dense_backend"] = dense_backend
    report["backend_status"] = backend_status

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"RAG eval ablation: {report['case_count']} cases, "
        f"top_k={report['top_k']}, dense_backend={dense_backend}"
    )
    for backend, status in backend_status.items():
        print(f"  backend {backend}: {status}")
    for name, strategy in report["strategies"].items():
        print(
            f"  {name}: "
            f"Recall@{args.top_k}={strategy[f'recall_at_{args.top_k}']:.4f}, "
            f"MRR@{args.top_k}={strategy[f'mrr_at_{args.top_k}']:.4f}"
        )
    print(f"Report written to {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
