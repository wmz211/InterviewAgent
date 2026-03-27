"""
Global application settings loaded from environment variables.
Uses pydantic-settings for type-safe config management.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM ---
    dashscope_api_key: str = ""
    llm_model_name: str = "qwen-max"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # --- Embedding ---
    embedding_model_name: str = "text-embedding-v3"

    # --- TTS ---
    tts_model_name: str = "qwen3-tts-instruct-flash-realtime"
    tts_voice: str = "Ethan"
    tts_speech_rate: float = 1.3   # 0.5-2.0, default 1.0
    tts_instructions: str = ""     # instruct model only

    # --- ASR ---
    asr_model_name: str = "sensevoice-v1"

    # --- ChromaDB ---
    chroma_persist_dir: str = "./data/chroma_db"
    chroma_collection_questions: str = "interview_questions"
    chroma_collection_algorithms: str = "algorithm_problems"
    chroma_collection_hr: str = "hr_questions"

    # --- Neo4j / Graph ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "interviewagent"
    graph_backend: Literal["neo4j", "networkx"] = "networkx"

    # --- App ---
    app_env: Literal["development", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "DEBUG"

    # --- Session ---
    session_timeout_seconds: int = 3600
    max_interview_duration_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
