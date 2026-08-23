from __future__ import annotations

import unittest

from scripts.run_existing_tools import parse_doc_style


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


if __name__ == "__main__":
    unittest.main()
