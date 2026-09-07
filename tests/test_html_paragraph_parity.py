"""HTML 경로의 문단 검사가 마크다운과 같은 판정을 내는지 못 박는다.

**무엇이 틀려 있었나.** 2026-09-04 이전 HTML 경로는 `len(t) > 90` 만 봤다. 이름은
「서술형 문단」인데 **서술형인지를 안 봤다.** 두 방향으로 틀렸다.

| 방향 | 무엇 | 실측 |
|---|---|---|
| 미탐 | 짧은 서술 문단을 통째로 놓침 | 같은 내용 · 마크다운 오류 2 · HTML **오류 0** |
| 오탐 | 「굵은 결론 — 근거 문장」이 길다는 이유로 걸림 | 251건 · 다른 주의를 덮음 |

**고친 뒤 실측**(HTML 전수) — 주의 319 → 68 · 오류 29 → 195. 새 오류 166건은 파일
넷에 몰렸고 127건이 발표 대본이다(산문이라 `form: prose` 소관).

**이 시험이 막는 것.** 두 형식에 같은 내용을 넣고 판정이 갈리는 것. 형식이 판정을
바꾸면 사람은 통과한 쪽만 보고 발행한다 — 제목 검사가 HTML 경로에만 빠져 있던
2026-09-02 건과 같은 실패 모양이다.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

CHECKER = repo_paths.CHECKER
KIND = "서술형 문단"
MD_KIND = "서술형 종결"

MD_HEAD = "---\nform: structured\n---\n\n# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
HTML_HEAD = ('<h1>검토 결과</h1><p class="lede">하반기 검토 범위 — 한 장 조망</p>'
             '<dl><dt>기한</dt><dd>9월 4일</dd></dl>')

# 두 형식에 같은 내용을 넣는다. 왼쪽이 문단 본문, 오른쪽이 걸려야 하는지.
CASES = [
    ("맨 서술 문단", "이 문서는 설계 전용이다.", True),
    ("긴 서술 문단", "표는 그 자체가 값 슬롯이라 근거 문장이 올 곳이 아니며 값 칸에는 이 예외가 없다.", True),
    ("개조식 문단", "기한 9월 4일 · 담당 검사팀 · 다음 단계 시범 적용 대상 선정 · 되돌리는 방법 규칙 파일 삭제", False),
    ("짧은 명사 문단", "검토 완료", False),
]


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParagraphParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()
        cls.source = CHECKER.read_text(encoding="utf-8")

    def scan(self, name: str, text: str, form=None):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / name
            target.write_text(text, encoding="utf-8")
            scan = self.checker.scan_md if name.endswith(".md") else self.checker.scan_html
            errors, warnings, _ = scan(str(target), False, form)
        kind = lambda item: item[1] if len(item) == 3 else item[0]  # noqa: E731
        return ([kind(i) for i in errors], [kind(i) for i in warnings])

    def html(self, para: str, form=None):
        return self.scan("doc.html", HTML_HEAD + f"<p>{para}</p>", form)

    def md(self, para: str):
        return self.scan("doc.md", MD_HEAD + para + "\n")

    def test_html_catches_narrative_paragraphs(self) -> None:
        for name, para, should in CASES:
            with self.subTest(case=name):
                errors, _ = self.html(para)
                self.assertEqual(should, KIND in errors,
                                 f"HTML 판정이 기대와 다릅니다: {errors}")

    def test_markdown_agrees(self) -> None:
        """같은 내용을 두 형식에 넣었을 때 판정이 갈리면 안 된다."""
        for name, para, should in CASES:
            with self.subTest(case=name):
                md_err, _ = self.md(para)
                self.assertEqual(should, MD_KIND in md_err,
                                 f"마크다운 판정이 기대와 다릅니다: {md_err}")

    def test_bold_head_with_evidence_is_exempt(self) -> None:
        """「굵은 결론 — 근거 문장」은 결론만 본다 — 근거는 문장이어도 된다."""
        errors, _ = self.html(
            "<b>적용 범위 — 설계 전용</b> 코드 실행은 사용자 재컨펌 후 별도로 진행한다.")
        self.assertNotIn(KIND, errors)

    def test_bold_head_itself_is_still_checked(self) -> None:
        """결론 머리가 서술형이면 그것이 걸린다 — 굵게가 면제권이 아니다."""
        errors, _ = self.html(
            "<b>한 번에 0이 안 됐다</b> 첫 수정본이 오류 3으로 남았다.")
        self.assertIn(KIND, errors)

    def test_lead_mark_before_the_bold_head_keeps_the_exemption(self) -> None:
        """줄머리 기호가 앞에 붙어도 「굵은 결론 — 근거 문장」은 그대로 예외다.

        2026-09-08 이전에는 `<b>` 로 **시작할 때만** 예외를 줬다. 마크다운 경로는
        진작 `LEAD_MARK` 로 기호를 뗐는데 HTML 경로만 안 떼서, 같은 문장을 두 형식에
        넣으면 마크다운 0 · HTML 1 로 갈렸다. 규칙 파일이 기호로 강조를 다는 형태라
        정작 그 규칙을 설명하는 문서가 자기 규칙에 걸렸다.
        """
        body = "적용 범위 — 설계 전용</b> 코드 실행은 사용자 재컨펌 후 별도로 진행한다."
        for mark in ("⚠️", "★", "📌", "⛔"):
            with self.subTest(mark=mark):
                errors, _ = self.html(f"{mark} <b>{body}")
                self.assertNotIn(KIND, errors,
                                 f"줄머리 기호 「{mark}」 때문에 예외를 못 받았습니다")

    def test_lead_mark_does_not_excuse_a_narrative_head(self) -> None:
        """기호를 떼는 것은 굵은 머리를 찾으려는 것뿐 — 서술형 결론은 그대로 걸린다."""
        errors, _ = self.html(
            "⚠️ <b>한 번에 0이 안 됐다</b> 첫 수정본이 오류 3으로 남았다.")
        self.assertIn(KIND, errors)

    def test_markdown_agrees_on_the_lead_mark_cases(self) -> None:
        """두 형식이 같은 판정을 내는지가 이 시험 파일의 본론이다."""
        cases = [
            ("면제되는 것", "적용 범위 — 설계 전용", "코드 실행은 사용자 재컨펌 후 별도로 진행한다.", False),
            ("걸려야 하는 것", "한 번에 0이 안 됐다", "첫 수정본이 오류 3으로 남았다.", True),
        ]
        for name, head, tail, should in cases:
            with self.subTest(case=name):
                md_err, _ = self.md(f"⚠️ **{head}** {tail}")
                html_err, _ = self.html(f"⚠️ <b>{head}</b> {tail}")
                self.assertEqual(should, MD_KIND in md_err, f"마크다운: {md_err}")
                self.assertEqual(should, KIND in html_err, f"HTML: {html_err}")

    def test_list_items_take_the_lead_mark_too(self) -> None:
        """목록 항목 경로에도 같은 규칙이 걸린다 — 한쪽만 고치면 그쪽이 낡는다."""
        html = (HTML_HEAD + "<ul><li>⚠️ <b>적용 범위 — 설계 전용</b> "
                "코드 실행은 사용자 재컨펌 후 별도로 진행한다.</li></ul>")
        errors, _ = self.scan("doc.html", html)
        self.assertNotIn("서술형 종결", errors)

    def test_prose_form_turns_it_off(self) -> None:
        """발표 대본처럼 흐르는 문장이 뼈대인 문서는 형식 선언으로 끈다."""
        errors, warnings = self.html("이 문서는 설계 전용이다.", form="prose")
        self.assertNotIn(KIND, errors + warnings)

    def test_length_alone_no_longer_warns(self) -> None:
        """길이만으로는 지적하지 않는다 — 규칙 어디에도 「90자 넘으면 나쁘다」가 없다."""
        long_value = " · ".join(f"항목 {n} 처리 완료" for n in range(1, 12))
        self.assertGreater(len(long_value), 90)
        errors, warnings = self.html(long_value)
        self.assertNotIn(KIND, errors + warnings)

    def test_contrast_examples_are_exempt(self) -> None:
        """대조 예시 줄은 나쁜 쪽을 보여 주는 것이라 지적 대상이 아니다."""
        errors, _ = self.html("❌ 이 문서는 설계 전용이다. → ✅ 적용 범위 — 설계 전용")
        self.assertNotIn(KIND, errors)

    def test_the_length_only_rule_is_gone_from_source(self) -> None:
        """되살아나면 오탐 251건이 그대로 돌아온다."""
        self.assertNotIn("if len(t) > 90:", self.source,
                         "길이만 보는 문단 검사가 되살아났습니다")


if __name__ == "__main__":
    unittest.main()
