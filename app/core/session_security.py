"""Session ownership helpers."""
from __future__ import annotations

from typing import Any, Mapping


def session_belongs_to_user(state: Mapping[str, Any], user_id: int) -> bool:
    """Return True only when the stored session owner matches the user."""
    owner_id = state.get("user_id")
    if owner_id is None:
        return False
    try:
        return int(owner_id) == int(user_id)
    except (TypeError, ValueError):
        return False
