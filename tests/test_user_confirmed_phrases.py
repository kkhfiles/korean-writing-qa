from __future__ import annotations

import json
import unittest
from pathlib import Path


class UserConfirmedPhraseTests(unittest.TestCase):
    def test_confirmed_phrase_pairs_are_stable(self) -> None:
        project_root = Path(__file__).parents[1]
        source = (
            project_root / "data" / "annotations" / "user-confirmed-phrases.jsonl"
        )
        rows = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
        ]
        pairs = {row["original"]: row["revised"] for row in rows}

        self.assertEqual(pairs["제품화 경로"], "제품화 단계")
        self.assertEqual(
            pairs["CT를 다시 세우는 부분"], "CT 재개발이 필요한 항목"
        )
        self.assertEqual(len(pairs), len(rows))


if __name__ == "__main__":
    unittest.main()
