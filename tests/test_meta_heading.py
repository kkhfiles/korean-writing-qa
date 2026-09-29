"""문서를 어떻게 읽을지 안내하는 제목 — 「읽는 법」 · 「문서 구성」.

**왜 있나** — 사용자가 기술 조사 보고서의 절 제목 「읽는 법」을 두고 「쓸데없는 말이다.
읽기 쉽게 써주면 되는건데」라고 했다(2026-09-23). 사례집 시료는 목록 한 줄로만 들어가서
제목 규칙을 못 고정하므로 여기서 제목으로 넣어 본다.

**놓을 쪽이 중요하다** — 「로그 읽는 법」·「시스템 구성」처럼 대상이 붙은 제목은 그 절에
내용이 있다는 뜻이라 걸리면 안 된다.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

KIND = "스캔 가치 없는 라벨"
MD_HEAD = "# 검증 동향\n\n**진입점** — 한 장 조망\n\n"


def load():
    spec = importlib.util.spec_from_file_location("doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MetaHeadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load()

    def warnings(self, suffix: str, text: str, form: str = "structured") -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / f"doc{suffix}"
            path.write_text(text, encoding="utf-8")
            scan = self.checker.scan_md if suffix == ".md" else self.checker.scan_html
            _, warn, _ = scan(str(path), False, form)
        return [w[-1] for w in warn if w[-2] == KIND]

    def md(self, heading: str, form: str = "structured") -> list[str]:
        return self.warnings(".md", MD_HEAD + f"## {heading}\n\n본문 한 줄입니다.\n", form)

    # ── 잡을 것 ──────────────────────────────────────────────────────────────

    def test_reading_guide_heading_is_caught(self) -> None:
        self.assertTrue(self.md("읽는 법"))

    def test_numbered_document_structure_heading_is_caught(self) -> None:
        self.assertTrue(self.md("3. 문서 구성"))

    def test_this_document_prefix_is_caught(self) -> None:
        self.assertTrue(self.md("이 자료 읽는 법"))

    def test_prose_form_still_catches_it(self) -> None:
        """산문 형식에서도 돈다 — 제목 형태 검사와 달리 낱말 선택이라서."""
        self.assertTrue(self.md("읽는 법", form="prose"))

    def test_the_html_path_catches_it_too(self) -> None:
        html = ("<h1>검증 동향</h1><p class=\"lede\"><b>진입점</b> · 한 장 조망</p>"
                "<h2>읽는 법</h2><p>본문</p>")
        self.assertTrue(self.warnings(".html", html))

    # ── 놓을 것 ──────────────────────────────────────────────────────────────

    def test_a_heading_with_its_subject_is_left_alone(self) -> None:
        self.assertFalse(self.md("로그 읽는 법"))
        self.assertFalse(self.md("시스템 구성"))


if __name__ == "__main__":
    unittest.main()
