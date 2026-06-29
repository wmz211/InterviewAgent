import unittest

from app.core.session_metadata import (
    build_session_create_values,
    build_session_update_values,
)


class SessionMetadataTests(unittest.TestCase):
    def test_create_values_capture_session_identity_and_flow(self):
        state = {
            "session_id": "s1",
            "user_id": 42,
            "candidate_name": "Alice",
            "interview_mode": "tech",
            "practice_mode": True,
            "selected_phase": "jd_tech",
            "current_node": "jd_tech",
        }

        values = build_session_create_values(state)

        self.assertEqual(values["session_id"], "s1")
        self.assertEqual(values["user_id"], 42)
        self.assertEqual(values["candidate_name"], "Alice")
        self.assertEqual(values["interview_mode"], "tech")
        self.assertEqual(values["flow_mode"], "phase_practice")
        self.assertTrue(values["practice_mode"])
        self.assertEqual(values["selected_phase"], "jd_tech")
        self.assertEqual(values["current_node"], "jd_tech")
        self.assertEqual(values["status"], "created")

    def test_update_values_mark_completed_sessions(self):
        state = {
            "current_node": "wrap_up",
            "interview_complete": True,
        }

        values = build_session_update_values(state)

        self.assertEqual(values["current_node"], "wrap_up")
        self.assertEqual(values["status"], "completed")
        self.assertIn("completed_at", values)

    def test_update_values_keep_active_sessions_active(self):
        state = {
            "current_node": "resume_dive",
            "interview_complete": False,
        }

        values = build_session_update_values(state)

        self.assertEqual(values["current_node"], "resume_dive")
        self.assertEqual(values["status"], "active")
        self.assertNotIn("completed_at", values)


if __name__ == "__main__":
    unittest.main()
