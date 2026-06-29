"""Persist and list reusable resume/JD materials for interview setup."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

DEFAULT_STORE_PATH = Path("./data/reusable_materials.json")
DEFAULT_SESSIONS_DIR = Path("./data/sessions")
MAX_OPTIONS = 30

_LOCK = Lock()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join(str(text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "..."


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"users": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    data.setdefault("users", {})
    return data


def _write_store(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _user_bucket(data: dict[str, Any], user_id: int) -> dict[str, list[dict[str, Any]]]:
    users = data.setdefault("users", {})
    bucket = users.setdefault(str(user_id), {})
    bucket.setdefault("resumes", [])
    bucket.setdefault("jds", [])
    return bucket


def save_reusable_materials(
    user_id: int,
    session_id: str,
    candidate_name: str,
    resume_summary: str,
    jd_text: str,
    *,
    store_path: Path = DEFAULT_STORE_PATH,
) -> None:
    """Save materials from a successful setup so they can be reused later."""
    now = _utc_iso()
    with _LOCK:
        data = _load_store(store_path)
        bucket = _user_bucket(data, user_id)
        if resume_summary.strip():
            bucket["resumes"].append(
                {
                    "session_id": session_id,
                    "candidate_name": candidate_name,
                    "resume_summary": resume_summary,
                    "created_at": now,
                }
            )
        if jd_text.strip():
            bucket["jds"].append(
                {
                    "session_id": session_id,
                    "jd_text": jd_text,
                    "jd_preview": _preview(jd_text),
                    "created_at": now,
                }
            )
        _trim_bucket(bucket)
        _write_store(store_path, data)


def get_reuse_options(
    user_id: int,
    *,
    store_path: Path = DEFAULT_STORE_PATH,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
) -> dict[str, list[dict[str, Any]]]:
    """Return latest unique reusable resumes and JDs for one user."""
    data = _load_store(store_path)
    bucket = _user_bucket(data, user_id)
    resumes = list(bucket["resumes"])
    jds = list(bucket["jds"])

    for state in _iter_session_states(user_id, sessions_dir):
        session_id = str(state.get("session_id", ""))
        created_at = str(state.get("created_at") or state.get("completed_at") or "")
        resume_summary = str(state.get("resume_summary", ""))
        jd_text = str(state.get("jd_text", ""))
        if session_id and resume_summary.strip():
            resumes.append(
                {
                    "session_id": session_id,
                    "candidate_name": str(state.get("candidate_name", "")),
                    "resume_summary": resume_summary,
                    "created_at": created_at,
                }
            )
        if session_id and jd_text.strip():
            jds.append(
                {
                    "session_id": session_id,
                    "jd_text": jd_text,
                    "jd_preview": _preview(jd_text),
                    "created_at": created_at,
                }
            )

    return {
        "resumes": _dedupe_materials(resumes, "resume_summary"),
        "jds": _dedupe_materials(jds, "jd_text"),
    }


def get_reusable_resume(
    user_id: int,
    session_id: str,
    *,
    store_path: Path = DEFAULT_STORE_PATH,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
) -> dict[str, Any] | None:
    for item in get_reuse_options(user_id, store_path=store_path, sessions_dir=sessions_dir)["resumes"]:
        if item.get("session_id") == session_id:
            return item
    return None


def get_reusable_jd(
    user_id: int,
    session_id: str,
    *,
    store_path: Path = DEFAULT_STORE_PATH,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
) -> dict[str, Any] | None:
    for item in get_reuse_options(user_id, store_path=store_path, sessions_dir=sessions_dir)["jds"]:
        if item.get("session_id") == session_id:
            return item
    return None


def _dedupe_materials(items: list[dict[str, Any]], content_key: str) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda item: str(item.get("created_at", "")), reverse=True)
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in ordered:
        content = str(item.get(content_key, "")).strip()
        if not content or content in seen:
            continue
        seen.add(content)
        result.append(dict(item))
        if len(result) >= MAX_OPTIONS:
            break
    return result


def _trim_bucket(bucket: dict[str, list[dict[str, Any]]]) -> None:
    bucket["resumes"] = bucket["resumes"][-MAX_OPTIONS * 3 :]
    bucket["jds"] = bucket["jds"][-MAX_OPTIONS * 3 :]


def _iter_session_states(user_id: int, sessions_dir: Path) -> list[dict[str, Any]]:
    if not sessions_dir.exists():
        return []
    states: list[dict[str, Any]] = []
    for path in sessions_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if state.get("user_id") == user_id:
            state.setdefault("session_id", path.stem)
            states.append(state)
    return states
