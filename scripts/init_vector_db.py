"""
One-time script to initialize ChromaDB with the question bank.

Run from project root:
    python scripts/init_vector_db.py

ChromaDB uses its built-in embedding function by default (all-MiniLM-L6-v2).
To switch to DashScope text-embedding-v3, set EMBEDDING_MODEL_NAME in .env
and update client.py to pass the embedding_function argument.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.rag.vector_store.indexer import index_all
from app.rag.vector_store.client import get_chroma_client

if __name__ == "__main__":
    print("Initializing ChromaDB...")
    client = get_chroma_client()

    # List existing collections
    existing = [c.name for c in client.list_collections()]
    if existing:
        print(f"Existing collections: {existing}")

    results = index_all()
    print("\nIndexing complete:")
    for collection, count in results.items():
        print(f"  {collection}: {count} documents")
