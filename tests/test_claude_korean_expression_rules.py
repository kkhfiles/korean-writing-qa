from __future__ import annotations

import json
import unittest
from pathlib import Path


class ClaudeKoreanExpressionRuleDataTests(unittest.TestCase):
    def test_rule_ids_and_statuses_are_valid(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "annotations"
            / "claude-korean-expression-rules.jsonl"
        )
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertGreaterEqual(len(records), 37)
        self.assertEqual(len({record["rule_id"] for record in records}), len(records))
        self.assertEqual(
            {record["status"] for record in records},
            {"confirmed", "scoped", "false_positive", "candidate_unvalidated"},
        )
        for record in records:
            self.assertTrue(record["guidance"])
            self.assertTrue(record["source_refs"])
            for source in record["source_refs"]:
                self.assertIn("path", source)
                self.assertRegex(source["lines"], r"^\d+-\d+$")


if __name__ == "__main__":
    unittest.main()
