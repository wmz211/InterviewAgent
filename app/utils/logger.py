"""
Centralized logger accessor.
Import this instead of calling loguru directly so format stays consistent.
"""
from loguru import logger

__all__ = ["logger"]
