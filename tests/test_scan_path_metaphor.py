from __future__ import annotations

import unittest

from scripts.scan_path_metaphor import classify


class PathMetaphorTests(unittest.TestCase):
    def classify_term(self, text: str) -> str:
        start = text.index("경로")
        return classify(text, start, start + len("경로"))[0]

    def test_abstract_productization_path(self) -> None:
        self.assertEqual(self.classify_term("제품화 경로를 구체화한다."), "abstract_candidate")

    def test_abstract_solution_path(self) -> None:
        self.assertEqual(self.classify_term("해결 경로 두 가지를 비교한다."), "abstract_candidate")

    def test_literal_file_path(self) -> None:
        self.assertEqual(self.classify_term("파일 경로를 입력한다."), "literal_candidate")

    def test_unknown_compound_requires_review(self) -> None:
        self.assertEqual(self.classify_term("호출 경로를 확인한다."), "review")


if __name__ == "__main__":
    unittest.main()
