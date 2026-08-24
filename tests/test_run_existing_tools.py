from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_existing_tools import parse_doc_style, verify_input_hash


class ExistingToolRunnerTests(unittest.TestCase):
    def test_parse_doc_style_summary(self) -> None:
        output = """
── sample.md  오류 2 · 주의 3  (값 슬롯 11)
합계 — 오류 2 · 주의 3 · 검사 불가 1
"""
        self.assertEqual(
            parse_doc_style(output),
            {"errors": 2, "warnings": 3, "blind": 1, "value_slots": 11},
        )

    def test_parse_doc_style_without_blind_files(self) -> None:
        output = "✅ sample.md  (값 슬롯 7)\n\n합계 — 오류 0 · 주의 0\n"
        self.assertEqual(
            parse_doc_style(output),
            {"errors": 0, "warnings": 0, "blind": 0, "value_slots": 7},
        )

    @patch("scripts.run_existing_tools.hash_file", return_value="actual")
    def test_manifest_hash_must_match_current_input(self, _hash_file) -> None:
        with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
            verify_input_hash(Path("sample.md"), "declared")

    @patch("scripts.run_existing_tools.hash_file", return_value="same")
    def test_verified_hash_is_returned(self, _hash_file) -> None:
        self.assertEqual(verify_input_hash(Path("sample.md"), "same"), "same")


if __name__ == "__main__":
    unittest.main()
