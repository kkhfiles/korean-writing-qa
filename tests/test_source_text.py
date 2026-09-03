from __future__ import annotations

import unittest
from pathlib import Path

from scripts import skill_bridge

# 배포본을 시험한다 — 저장소 사본을 시험하면 스킬이 망가져도 초록으로 남는다.
extract_source_text = skill_bridge.load("source_text").extract_source_text


class SourceTextExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parent / "fixtures" / "formats"

    def texts(self, filename: str) -> list[str]:
        return [
            str(unit["text"])
            for unit in extract_source_text(self.root / filename)
        ]

    def test_markdown_excludes_frontmatter_and_code_fences(self) -> None:
        texts = self.texts("sample.md")

        self.assertIn("# 제목", texts)
        self.assertIn("본문의 한국어 문장입니다.", texts)
        self.assertFalse(any("model:" in text for text in texts))
        self.assertFalse(any("print" in text for text in texts))

    def test_markdown_masks_inline_code_and_preserves_source_columns(self) -> None:
        units = extract_source_text(self.root / "inline-code.md")
        texts = [str(item["text"]) for item in units]

        self.assertFalse(any("제품화 경로" in text for text in texts))
        self.assertIn("  실제 문장은 제품화 단계입니다.", texts)

    def test_html_extracts_visible_blocks_and_joins_inline_text(self) -> None:
        texts = self.texts("sample.html")

        self.assertIn("검사 보고서", texts)
        self.assertIn("제품화 단계를 검토합니다.", texts)
        self.assertFalse(any("display:none" in text for text in texts))
        self.assertFalse(any("숨긴 문장" in text for text in texts))

    def test_html_joins_div_inline_text_and_skips_code_examples(self) -> None:
        texts = self.texts("inline-blocks.html")

        self.assertIn("제품화 경로를 검토합니다.", texts)
        self.assertFalse(any("코드 안 제품화 경로" in text for text in texts))
        self.assertFalse(any("CT를 다시 세우는 부분" in text for text in texts))

    def test_json_extracts_string_values_with_logical_paths(self) -> None:
        units = extract_source_text(self.root / "sample.json")
        by_text = {str(item["text"]): item for item in units}

        self.assertEqual(by_text["검사 결과"]["logical_path"], "/title")
        self.assertEqual(
            by_text["테스트를 설계합니다."]["logical_path"],
            "/items/0/message",
        )
        self.assertNotIn("2", by_text)

    def test_jsonl_preserves_record_lines_and_invalid_input(self) -> None:
        units = extract_source_text(self.root / "sample.jsonl")
        by_text = {str(item["text"]): item for item in units}

        self.assertEqual(by_text["첫 질문입니다."]["line_number"], 1)
        self.assertEqual(by_text["not-json"]["kind"], "invalid_jsonl")
        self.assertEqual(by_text["둘째 답변입니다."]["line_number"], 3)

    def test_yaml_extracts_string_values_but_not_numbers(self) -> None:
        texts = self.texts("sample.yaml")

        self.assertIn("검사 계획", texts)
        self.assertIn("테스트를 수행합니다.", texts)
        self.assertNotIn("2", texts)

    def test_properties_extracts_values_and_decodes_unicode(self) -> None:
        texts = self.texts("sample.properties")

        self.assertIn("검사 결과", texts)
        self.assertIn("테스트가 완료되었습니다.", texts)
        self.assertIn("검사 완료", texts)
        self.assertFalse(any("dialog.title" in text for text in texts))

    def test_text_removes_terminal_control_sequences(self) -> None:
        self.assertEqual(self.texts("sample.txt"), ["일반 텍스트 문장입니다."])


if __name__ == "__main__":
    unittest.main()
