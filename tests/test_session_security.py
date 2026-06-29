import unittest

from app.core.session_security import session_belongs_to_user


class SessionSecurityTests(unittest.TestCase):
    def test_session_belongs_to_matching_user_id(self):
        state = {"session_id": "s1", "user_id": 42}

        self.assertTrue(session_belongs_to_user(state, 42))

    def test_session_rejects_different_user_id(self):
        state = {"session_id": "s1", "user_id": 42}

        self.assertFalse(session_belongs_to_user(state, 7))

    def test_session_without_owner_is_not_authorized(self):
        state = {"session_id": "legacy-session"}

        self.assertFalse(session_belongs_to_user(state, 42))

    def test_session_owner_compares_numeric_strings(self):
        state = {"session_id": "s1", "user_id": "42"}

        self.assertTrue(session_belongs_to_user(state, 42))


if __name__ == "__main__":
    unittest.main()
