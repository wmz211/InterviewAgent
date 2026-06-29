import unittest

from app.core.message_metadata import build_message_records


class HumanMessage:
    def __init__(self, content):
        self.content = content


class AIMessage:
    def __init__(self, content):
        self.content = content


class ToolMessage:
    def __init__(self, content):
        self.content = content


class MessageMetadataTests(unittest.TestCase):
    def test_build_message_records_from_message_objects(self):
        state = {
            "current_node": "jd_tech",
            "messages": [
                HumanMessage("hello"),
                AIMessage("question"),
                ToolMessage("reference"),
            ],
        }

        records = build_message_records("s1", state)

        self.assertEqual(
            [(r["role"], r["content"], r["turn_index"], r["phase"]) for r in records],
            [
                ("human", "hello", 0, "jd_tech"),
                ("ai", "question", 1, "jd_tech"),
                ("tool", "reference", 2, "jd_tech"),
            ],
        )

    def test_build_message_records_from_serialized_dicts(self):
        state = {
            "current_node": "resume_dive",
            "messages": [
                {"type": "HumanMessage", "content": "answer"},
                {"type": "AIMessage", "content": "next question"},
            ],
        }

        records = build_message_records("s2", state)

        self.assertEqual(records[0]["role"], "human")
        self.assertEqual(records[1]["role"], "ai")
        self.assertEqual(records[0]["session_id"], "s2")

    def test_build_message_records_flattens_list_content(self):
        state = {
            "current_node": "greeting",
            "messages": [
                AIMessage([
                    {"type": "text", "text": "part one"},
                    {"type": "text", "text": "part two"},
                ]),
            ],
        }

        records = build_message_records("s3", state)

        self.assertEqual(records[0]["content"], "part one part two")

    def test_build_message_records_skips_empty_content(self):
        state = {
            "current_node": "greeting",
            "messages": [AIMessage("")],
        }

        records = build_message_records("s4", state)

        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
