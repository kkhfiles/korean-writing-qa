from __future__ import annotations

import unittest
from pathlib import Path

from scripts.scan_path_metaphor import classify, scan


class PathMetaphorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.formats = Path(__file__).parent / "fixtures" / "formats"

    def classify_term(self, text: str) -> str:
        start = text.index("경로")
        return classify(text, start, start + len("경로"))[0]

    def test_abstract_productization_path(self) -> None:
        self.assertEqual(self.classify_term("제품화 경로를 구체화한다."), "abstract_candidate")

    def test_abstract_solution_path(self) -> None:
        self.assertEqual(self.classify_term("해결 경로 두 가지를 비교한다."), "abstract_candidate")

    def test_literal_file_path(self) -> None:
        self.assertEqual(self.classify_term("파일 경로를 입력한다."), "literal_candidate")

    def test_literal_windows_path(self) -> None:
        self.assertEqual(self.classify_term("Windows 경로 처리 규칙"), "literal_candidate")

    def test_literal_import_path(self) -> None:
        self.assertEqual(
            self.classify_term("import 경로가 framer-motion/react로 바뀐다."),
            "literal_candidate",
        )

    def test_literal_saved_report_path(self) -> None:
        self.assertEqual(
            self.classify_term("보고서는 아래 경로에 저장되었습니다."),
            "literal_candidate",
        )

    def test_call_path_is_literal_in_it_context(self) -> None:
        self.assertEqual(
            self.classify_term("호출 경로를 확인한다."), "literal_candidate"
        )

    def test_metaphorical_deviation_is_an_abstract_candidate(self) -> None:
        self.assertEqual(
            self.classify_term("에이전트가 도중에 경로를 이탈했다."),
            "abstract_candidate",
        )

    def test_structured_values_use_the_common_extractor(self) -> None:
        findings = scan(self.formats)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["classification"], "abstract_candidate")
        self.assertEqual(findings[0]["logical_path"], "/message")
        self.assertEqual(findings[0]["source_format"], ".json")
        self.assertIsNone(findings[0]["line_number"])


if __name__ == "__main__":
    unittest.main()
