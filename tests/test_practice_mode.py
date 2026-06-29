import unittest

from app.core.practice import (
    FULL_INTERVIEW,
    PHASE_PRACTICE,
    build_practice_metadata,
    is_valid_phase_for_mode,
)


class PracticeModeTests(unittest.TestCase):
    def test_full_interview_starts_without_selected_phase(self):
        metadata = build_practice_metadata(
            interview_mode="tech",
            flow_mode=FULL_INTERVIEW,
            selected_phase="jd_tech",
        )

        self.assertFalse(metadata["practice_mode"])
        self.assertEqual(metadata["selected_phase"], "")
        self.assertEqual(metadata["initial_phase"], "greeting")

    def test_phase_practice_starts_at_selected_phase(self):
        metadata = build_practice_metadata(
            interview_mode="tech",
            flow_mode=PHASE_PRACTICE,
            selected_phase="coding_test",
        )

        self.assertTrue(metadata["practice_mode"])
        self.assertEqual(metadata["selected_phase"], "coding_test")
        self.assertEqual(metadata["initial_phase"], "coding_test")

    def test_invalid_practice_phase_falls_back_to_greeting(self):
        metadata = build_practice_metadata(
            interview_mode="hr",
            flow_mode=PHASE_PRACTICE,
            selected_phase="coding_test",
        )

        self.assertTrue(metadata["practice_mode"])
        self.assertEqual(metadata["selected_phase"], "")
        self.assertEqual(metadata["initial_phase"], "greeting")

    def test_valid_phase_respects_interview_mode(self):
        self.assertTrue(is_valid_phase_for_mode("tech", "jd_tech"))
        self.assertFalse(is_valid_phase_for_mode("tech", "hr_behavioral"))
        self.assertTrue(is_valid_phase_for_mode("hr", "hr_behavioral"))
        self.assertFalse(is_valid_phase_for_mode("hr", "coding_test"))


if __name__ == "__main__":
    unittest.main()
