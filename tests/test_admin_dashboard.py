import json
import unittest
from pathlib import Path

from app.api.endpoints.admin import (
    admin_email_allowlist,
    interview_phases,
    parse_admin_emails,
    summarize_knowledge_graph,
    summarize_question_banks,
)


STATIC_ADMIN = Path(__file__).resolve().parents[1] / "static" / "admin.html"


class AdminDashboardTests(unittest.TestCase):
    def test_parse_admin_emails_normalizes_csv(self):
        self.assertEqual(
            parse_admin_emails(" Admin@Example.com, ops@example.com ,, "),
            {"admin@example.com", "ops@example.com"},
        )

    def test_admin_allowlist_includes_env_file_value(self):
        self.assertIn("2231688769@qq.com", admin_email_allowlist())

    def test_knowledge_graph_summary_counts_domains_and_samples(self):
        path = Path(self.id().replace(".", "_") + ".json")
        payload = {
            "nodes": [
                {"id": "domain_ai", "label": "AI", "type": "Domain"},
                {"id": "llm", "label": "LLM", "type": "Tech", "domain": "domain_ai"},
                {"id": "rag", "label": "RAG", "type": "Tech"},
            ],
            "edges": [
                {"source": "rag", "target": "domain_ai", "relation": "BELONGS_TO"},
            ],
        }
        try:
            path.write_text(json.dumps(payload), encoding="utf-8")

            domains, node_types, node_count, edge_count = summarize_knowledge_graph(path)

            self.assertEqual(node_count, 3)
            self.assertEqual(edge_count, 1)
            self.assertEqual(node_types["Domain"], 1)
            self.assertEqual(node_types["Tech"], 2)
            self.assertEqual(domains[0].label, "AI")
            self.assertEqual(domains[0].node_count, 2)
            self.assertIn("LLM", domains[0].sample_topics)
            self.assertIn("RAG", domains[0].sample_topics)
        finally:
            if path.exists():
                path.unlink()

    def test_question_bank_summary_reads_topics_and_difficulty(self):
        directory = Path(self.id().replace(".", "_"))
        directory.mkdir(exist_ok=True)
        try:
            (directory / "sample.json").write_text(
                json.dumps(
                    [
                        {"topic": "RAG", "difficulty": "medium"},
                        {"topic": "RAG", "difficulty": "hard"},
                        {"topic": "Agent", "difficulty": "hard"},
                    ]
                ),
                encoding="utf-8",
            )

            banks = summarize_question_banks(directory)

            self.assertEqual(len(banks), 1)
            self.assertEqual(banks[0].name, "sample")
            self.assertEqual(banks[0].question_count, 3)
            self.assertEqual(banks[0].topics[:2], ["RAG", "Agent"])
            self.assertEqual(banks[0].difficulties, {"medium": 1, "hard": 2})
        finally:
            for child in directory.glob("*"):
                child.unlink()
            directory.rmdir()

    def test_interview_phases_include_tech_and_hr_tracks(self):
        phases = interview_phases()
        keys = {phase.key for phase in phases}

        self.assertIn("jd_tech", keys)
        self.assertIn("hr_behavioral", keys)
        self.assertIn("wrap_up", keys)

    def test_admin_html_calls_overview_endpoint(self):
        html = STATIC_ADMIN.read_text(encoding="utf-8")

        self.assertIn("/api/v1/admin/overview", html)
        self.assertIn("ia_admin_token", html)
        self.assertIn("系统覆盖与运行概览", html)


if __name__ == "__main__":
    unittest.main()
