from __future__ import annotations

import json
import unittest
from pathlib import Path


class FeedbackCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.schema = json.loads(
            (cls.root / "data" / "feedback" / "candidate-schema.json").read_text(
                encoding="utf-8"
            )
        )

    def test_schema_keeps_decision_source_verdict_and_context_separate(self) -> None:
        required = set(self.schema["required"])
        self.assertTrue(
            {
                "context_level",
                "decision_source",
                "user_verdict",
                "status",
            }.issubset(required)
        )
        properties = self.schema["properties"]
        self.assertEqual(
            set(properties["context_level"]["enum"]),
            {"sentence", "window", "block", "document"},
        )
        self.assertIn("model_candidate", properties["decision_source"]["enum"])
        self.assertIn("false_positive", properties["user_verdict"]["enum"])
        self.assertIn("technical-report", properties["profile"]["enum"])
        self.assertIn("short-message", properties["profile"]["enum"])

    def test_candidate_queue_matches_schema_when_present(self) -> None:
        queue = self.root / "data" / "feedback" / "candidates.jsonl"
        if not queue.exists():
            self.skipTest("candidate queue is created on first capture")
        required = set(self.schema["required"])
        properties = self.schema["properties"]
        seen_ids: set[str] = set()
        for line_number, line in enumerate(
            queue.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            record = json.loads(line)
            with self.subTest(line=line_number):
                self.assertFalse(required - set(record))
                self.assertNotIn(record["candidate_id"], seen_ids)
                seen_ids.add(record["candidate_id"])
                for field in (
                    "context_level",
                    "decision_source",
                    "user_verdict",
                    "status",
                ):
                    self.assertIn(record[field], properties[field]["enum"])


if __name__ == "__main__":
    unittest.main()
