"""
ChromaDB singleton client.
"""
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.config import get_settings

settings = get_settings()
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def resolve_chroma_persist_dir(raw_path: str) -> Path:
    """Resolve Chroma paths from the project root, not the process cwd."""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    persist_dir = resolve_chroma_persist_dir(settings.chroma_persist_dir)
    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    logger.info(f"ChromaDB client initialized at '{persist_dir}'")
    return client
