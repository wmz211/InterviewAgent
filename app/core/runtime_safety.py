"""Runtime safety checks for production deployments."""
from __future__ import annotations

from typing import Any


PLACEHOLDER_SECRETS = {
    "",
    "change-me-in-production",
    "replace_with_a_long_random_secret",
}


def validate_runtime_settings(settings: Any) -> list[str]:
    """Return production safety issues for the provided settings object."""
    if getattr(settings, "app_env", "development") != "production":
        return []

    issues: list[str] = []
    secret_key = str(getattr(settings, "secret_key", ""))
    redis_url = str(getattr(settings, "redis_url", ""))
    cors_allowed_origins = str(getattr(settings, "cors_allowed_origins", ""))

    if secret_key in PLACEHOLDER_SECRETS:
        issues.append("SECRET_KEY must be set to a non-placeholder value in production")
    if not redis_url:
        issues.append("REDIS_URL must be set in production")
    if not cors_allowed_origins or cors_allowed_origins.strip() == "*":
        issues.append("CORS origins must not be '*' in production")

    return issues


def parse_cors_origins(raw: str, app_env: str) -> list[str]:
    """Parse comma-separated CORS origins, keeping permissive defaults for dev."""
    if raw.strip():
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    if app_env == "production":
        return []
    return ["*"]
