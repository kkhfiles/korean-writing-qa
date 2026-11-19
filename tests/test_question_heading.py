"""「~인가」, 「~는가」로 끝나는 제목과 라벨 — 의문사, 물음표, 대시 부제, 산문 여부와 상관없이 잡는다.

(2026-11-19 사용자 지적) 예전에는 「의문사가 있고, 부제가 없고, 구조형인」 꼴만 주의로 냈다. 실측
(`runs/question-heading-20261119`)에서 이 꼴의 제목은 사람 업무 문서 4,835개 중 4개(모두 회의 메모), AI 와
작성한 기획 문서 10,319개 중 44개였다. 물음표 없는 의문 라벨은 사람 2개 대 57개, 물음표 라벨은 사람 89개 대 26개라
물음표 라벨은 주의로 둔다(점검 질문 목록은 정상). 본문 의문문은 빈도가 같아 1층에서 보지 않고 2층이 맡는다.

**지키는 것**

- 잡음 — 대시 부제가 붙은 제목, 물음표로 끝난 제목, 의문사 없는 제목, 산문 문서의 제목, HTML 제목(오류),
  물음표 없는 의문 라벨(오류), 물음표 라벨(주의)
- 안 잡음 — 「단가」, 「전문가」, 「인가」 같은 명사, 자주 묻는 질문의 「~나요?」, 본문 문장의 의문문, 「」로 감싼 제목
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import repo_paths  # noqa: E402


def load_checker():
    spec = importlib.util.spec_from_file_location("chk_question", repo_paths.CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = load_checker()
HAS_MORPH = C.morph() is not None
HEAD = "---\nform: {form}\n---\n\n# 전환 계획\n\n**전환 범위와 일정** — 한 장 정리\n\n"


def scan(body: str, form: str = "prose", suffix: str = ".md"):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"doc{suffix}"
        if suffix == ".md":
            path.write_text(HEAD.format(form=form) + body, encoding="utf-8")
            errors, warnings, _ = C.scan_md(str(path))
        else:
            path.write_text(body, encoding="utf-8")
            errors, warnings, _ = C.scan_html(str(path))
    return [k for k, _ in errors], [k for k, _ in warnings]


@unittest.skipUnless(HAS_MORPH, "형태소 분석기가 있어야 끝맺음을 가른다")
class QuestionHeadingTests(unittest.TestCase):

    def test_question_headings_are_errors_in_every_shape(self) -> None:
        for heading in ("## 왜 전환인가 — 기존 방식의 한계와 대안", "## 어떻게 적용하는가",
                        "## 기존 방식으로 충분한가?", "## 전환이 돌파구인가"):
            for form in ("prose", "structured"):
                with self.subTest(heading=heading, form=form):
                    errors, _ = scan(heading + "\n", form)
                    self.assertIn("의문문 제목", errors)

    def test_html_heading_is_an_error(self) -> None:
        html = ('<html><head><meta name="form" content="prose"></head><body>'
                '<h1>전환 계획</h1><p>전환 범위와 일정을 정리했습니다.</p>'
                '<h2>왜 지금인가?</h2><p>본문입니다.</p></body></html>')
        errors, _ = scan(html, suffix=".html")
        self.assertIn("의문문 제목", errors)

    def test_question_label_is_an_error_and_asked_label_a_warning(self) -> None:
        errors, warnings = scan("- 점검 담당자를 지정했는가\n- 설치 경로는 어디인가?\n", "structured")
        self.assertIn("절단형 종결", errors)
        self.assertIn("절단형 의심", warnings)

    def test_nouns_faq_body_and_quoted_titles_pass(self) -> None:
        body = ("## 납품 단가와 전문가 인가 절차\n\n## 설치는 어떻게 하나요?\n\n## 「무엇이 문제인가」\n\n"
                "기존 방식으로 과연 충분한지 살펴봤습니다. 정말 충분한가? 측정 결과는 부족했습니다.\n")
        errors, warnings = scan(body)
        self.assertNotIn("의문문 제목", errors)
        self.assertEqual([k for k in errors + warnings if k in ("절단형 종결", "절단형 의심")], [])

    def test_question_end_reads_the_part_before_the_dash(self) -> None:
        self.assertEqual(C.question_end("왜 전환인가 — 기존 방식의 한계"), "q")
        self.assertEqual(C.question_end("기존 방식으로 충분한가?"), "q?")
        self.assertIsNone(C.question_end("전환 이유 — 기존 방식의 한계"))
        self.assertIsNone(C.question_end("사업 인가"))


if __name__ == "__main__":
    unittest.main()
