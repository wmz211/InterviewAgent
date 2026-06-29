import tempfile
import unittest
from pathlib import Path

from scripts.verify_fast import find_forbidden_text


class VerifyFastTests(unittest.TestCase):
    def test_find_forbidden_text_reports_secret_like_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / ".env.example"
            sample.write_text("DASHSCOPE_API_KEY=sk-test-value\n", encoding="utf-8")

            matches = find_forbidden_text(root, [sample], ["sk-"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].path.name, ".env.example")
        self.assertEqual(matches[0].pattern, "sk-")
        self.assertEqual(matches[0].line_number, 1)

    def test_find_forbidden_text_ignores_clean_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / ".env.example"
            sample.write_text("DASHSCOPE_API_KEY=your_key\n", encoding="utf-8")

            matches = find_forbidden_text(root, [sample], ["sk-"])

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
