from __future__ import annotations

import json
import unittest
from pathlib import Path


class UserConfirmedPhraseTests(unittest.TestCase):
    def load_rows(self) -> list[dict[str, object]]:
        project_root = Path(__file__).parents[1]
        source = (
            project_root / "data" / "annotations" / "user-confirmed-phrases.jsonl"
        )
        return [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
        ]

    def test_confirmed_phrase_pairs_are_stable(self) -> None:
        rows = self.load_rows()
        pairs = {row["original"]: row["revised"] for row in rows}

        self.assertEqual(pairs["제품화 경로"], "제품화 단계")
        self.assertEqual(
            pairs["CT를 다시 세우는 부분"], "CT 재개발이 필요한 항목"
        )
        self.assertEqual(len(pairs), len(rows))

    def test_presenter_examples_are_scoped_contextual_rewrites(self) -> None:
        rows = [
            row
            for row in self.load_rows()
            if row.get("feedback_group_id") == "presenter-register-2026-08-24"
        ]

        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["scope"] == "presenter_notes" for row in rows))
        self.assertTrue(
            all(row["replacement_mode"] == "contextual_rewrite" for row in rows)
        )
        fragments = {
            row["annotation_id"]
            for row in rows
            if row["standalone_status"] != "complete"
        }
        self.assertEqual(
            fragments,
            {"user-register-003", "user-register-005", "user-register-006"},
        )
        self.assertTrue(
            all(row["requires_context"] for row in rows if row["annotation_id"] in fragments)
        )

    def test_style_preferences_reference_existing_examples(self) -> None:
        project_root = Path(__file__).parents[1]
        preference_path = (
            project_root / "data" / "annotations" / "user-style-preferences.jsonl"
        )
        preferences = [
            json.loads(line)
            for line in preference_path.read_text(encoding="utf-8").splitlines()
        ]
        annotation_ids = {row["annotation_id"] for row in self.load_rows()}

        self.assertEqual(len(preferences), 4)
        self.assertEqual(
            {row["category"] for row in preferences if row["status"] == "user_stated"},
            {
                "expand_compressed_expression",
                "use_precise_work_terms",
                "mark_plan_or_progress",
            },
        )
        for preference in preferences:
            self.assertTrue(set(preference["evidence_ids"]).issubset(annotation_ids))


if __name__ == "__main__":
    unittest.main()
