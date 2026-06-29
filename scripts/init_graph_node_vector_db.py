"""Index knowledge-graph nodes into Chroma using a BGE embedding model.

Run from project root:
    python scripts/init_graph_node_vector_db.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import chromadb
from chromadb.utils import embedding_functions

from app.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = PROJECT_ROOT / "data" / "tech_knowledge_graph.json"


def node_document(node: dict) -> str:
    aliases = " ".join(str(alias) for alias in node.get("aliases", []))
    return " ".join(
        str(value)
        for value in (
            node.get("id", ""),
            node.get("label", ""),
            aliases,
            node.get("description", ""),
        )
        if value
    )


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    settings = get_settings()
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = [node for node in graph["nodes"] if node.get("type") != "Domain"]

    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.local_embedding_model_name,
        local_files_only=True,
        normalize_embeddings=True,
    )
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    collection = client.get_or_create_collection(
        name=settings.chroma_collection_graph_nodes,
        embedding_function=embedding_function,
        metadata={
            "description": "Knowledge graph nodes embedded with BGE for RAG evaluation",
            "embedding_model": settings.local_embedding_model_name,
        },
    )

    ids = [str(node["id"]) for node in nodes]
    documents = [node_document(node) for node in nodes]
    metadatas = [
        {
            "node_id": str(node["id"]),
            "label": str(node.get("label", "")),
            "type": str(node.get("type", "")),
            "domain": str(node.get("domain", "")),
        }
        for node in nodes
    ]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    print(
        f"Indexed {len(ids)} graph nodes into Chroma collection "
        f"'{settings.chroma_collection_graph_nodes}' with {settings.local_embedding_model_name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
