import unittest
from types import SimpleNamespace

from app.core.runtime_safety import validate_runtime_settings


class RuntimeSafetyTests(unittest.TestCase):
    def test_development_allows_local_defaults(self):
        settings = SimpleNamespace(
            app_env="development",
            secret_key="change-me-in-production",
            redis_url="",
            cors_allowed_origins="*",
        )

        self.assertEqual(validate_runtime_settings(settings), [])

    def test_production_rejects_placeholder_secret(self):
        settings = SimpleNamespace(
            app_env="production",
            secret_key="replace_with_a_long_random_secret",
            redis_url="redis://localhost:6379/0",
            cors_allowed_origins="https://example.com",
        )

        issues = validate_runtime_settings(settings)

        self.assertIn("SECRET_KEY must be set to a non-placeholder value in production", issues)

    def test_production_rejects_in_memory_sessions(self):
        settings = SimpleNamespace(
            app_env="production",
            secret_key="a-realistic-long-random-secret",
            redis_url="",
            cors_allowed_origins="https://example.com",
        )

        issues = validate_runtime_settings(settings)

        self.assertIn("REDIS_URL must be set in production", issues)

    def test_production_rejects_wildcard_cors(self):
        settings = SimpleNamespace(
            app_env="production",
            secret_key="a-realistic-long-random-secret",
            redis_url="redis://localhost:6379/0",
            cors_allowed_origins="*",
        )

        issues = validate_runtime_settings(settings)

        self.assertIn("CORS origins must not be '*' in production", issues)


if __name__ == "__main__":
    unittest.main()
