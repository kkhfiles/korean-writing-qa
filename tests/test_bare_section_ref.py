"""§ 없이 번호로 절을 가리킨 곳 — 「(4-5)」 · 「5-1절」 · 「(1절)」.

**왜 있나** — 사용자 규칙은 「(§3) 와 같은 형태의 참조를 문서에서 만들지 말 것」이다.
검사기가 § 만 보던 동안 같은 참조가 lab-docs 빌드 대상에 40곳 남아 있었다(2026-09-23).

**가르는 기준은 같은 문서의 번호 붙은 제목** — 제목 대조가 없으면 날짜 · 코드 줄
범위 · 남의 문서 절과 못 가른다. 그래서 놓을 쪽 시료가 잡을 쪽만큼 중요하다.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

KIND = "절 번호로 가리킴"
MD_HEAD = "# 채널 등재\n\n등재 준비 · 한 장 조망\n\n## 1. 등재처\n\n- **곳** — 공식 목록\n\n"
MD_TAIL = "\n## 4-5. 등재 이후 — 연락·구매로 이어지는 길\n\n- **길** — 문의 창구\n"


def load():
    spec = importlib.util.spec_from_file_location("doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BareSectionRefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load()

    def findings(self, suffix: str, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / f"doc{suffix}"
            path.write_text(text, encoding="utf-8")
            scan = self.checker.scan_md if suffix == ".md" else self.checker.scan_html
            err, _, _ = scan(str(path), False, "structured")
        return [e[1] if len(e) == 2 else e[2] for e in err
                if (e[0] if len(e) == 2 else e[1]) == KIND]

    def md(self, line: str) -> list[str]:
        return self.findings(".md", MD_HEAD + line + "\n" + MD_TAIL)

    # ── 잡을 것 ──────────────────────────────────────────────────────────────

    def test_a_dashed_number_in_parentheses_is_caught_and_the_title_named(self) -> None:
        found = self.md("- **순서** — 안내 창구부터 확보(4-5)")
        self.assertEqual(1, len(found), found)
        self.assertIn("등재 이후", found[0], "가리키는 절 제목을 알려 줘야 고치기 쉽다")

    def test_a_single_number_with_jeol_is_caught(self) -> None:
        self.assertTrue(self.md("- **결과** — 실행 결과는 1절 표"))

    def test_the_html_path_catches_it_too(self) -> None:
        html = ("<h1>채널 등재</h1><p>등재 준비 · 한 장 조망</p>"
                "<h2>4-5. 등재 이후</h2><dl><dt>순서</dt><dd>안내 창구부터 확보(4-5)</dd></dl>")
        found = self.findings(".html", html)
        self.assertEqual(1, len(found), found)
        self.assertIn("등재 이후", found[0])

    # ── 놓을 것 — 제목과 안 맞으면 절 참조가 아니다 ─────────────────────────

    def test_no_matching_heading_means_no_finding(self) -> None:
        self.assertEqual([], self.md("- **범위** — 표본 줄(7-9)만 봄"))

    def test_an_enumeration_is_not_a_section(self) -> None:
        """「(1)」은 열거나 개수다 — 제목 「1.」이 있어도 한 마디 번호는 「절」이 붙어야 한다."""
        self.assertEqual([], self.md("- **렌즈** — (1) 기능 성격 · (2) 목적"))

    def test_a_decimal_is_not_a_section_even_with_a_dashed_heading(self) -> None:
        """가름표를 하나로 맞추면 「(4.5)」가 제목 「4-5.」과 맞는다 — 소수는 절이 아니다."""
        self.assertEqual([], self.md("- **평균** — 만족도(4.5)"))

    def test_a_date_is_not_a_section(self) -> None:
        self.assertEqual([], self.md("- **발표** — 전임연구원(05-14)"))

    def test_another_documents_section_is_left_alone(self) -> None:
        self.assertEqual([], self.md("- **자료** — 제안서 본문 6절과 부록"))

    def test_quotes_and_code_are_examples(self) -> None:
        self.assertEqual([], self.md("- **보기** — 「(4-5)」 꼴 · `(4-5)` 꼴"))


if __name__ == "__main__":
    unittest.main()
