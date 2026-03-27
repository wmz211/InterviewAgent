"""
ChromaDB singleton client.
"""
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    client = chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    logger.info(f"ChromaDB client initialized at '{settings.chroma_persist_dir}'")
    return client
