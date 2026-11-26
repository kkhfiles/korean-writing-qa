"""「덜어낸 것과 남긴 것」처럼 관형형 「것」 둘을 대구로 이은 명사구 — 제목은 오류, 그 밖의 값은 주의.

(2026-11-26 사용자 지적 · 대장 F-331) 발표 덱 장 제목 「재설계 범위 — 덜어낸 것과 남긴 것」을 「전형적인 AI 가
만든 티가 나는 문구」로 짚었다. 실측(`runs/paired-geot-heading-20261126`)에서 이 꼴은 사람 업무 문서 5,174편의
제목 4,835개와 라벨 24,698개에 0건, AI 와 작성한 기획 문서 748편의 제목에 24건(21편)이었다. 제목 아닌 값에서는
「오승인 · 오거부」 정의처럼 설명으로 쓴 나열이 섞여 주의로 둔다.

**지키는 것**

- 잡음 — 대시 부제 뒤의 대구, 과·와·빗금·가운뎃점으로 이은 대구, 끝에 이모지가 붙은 제목, HTML 제목(오류),
  목록 값(주의), 제목에는 주의를 겹쳐 내지 않음
- 안 잡음 — 명령형 「하지 말 것」, 비교 「~과 같은 것」, 조사가 이어지는 본문 문장, 쉼표로 셋을 늘어놓은 문장,
  사이에 「것」 아닌 항목이 낀 나열, 대명사 「그것과 이것」, 「」 인용
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
    spec = importlib.util.spec_from_file_location("chk_paired_geot", repo_paths.CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = load_checker()
HEAD = "---\nform: {form}\n---\n\n# 재설계 계획\n\n**재설계 범위와 일정** — 한 장 정리\n\n"
TITLE = "대구 「것」 제목"


def scan(body: str, form: str = "prose", suffix: str = ".md"):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"doc{suffix}"
        if suffix == ".md":
            path.write_text(HEAD.format(form=form) + body, encoding="utf-8")
            errors, warnings, _ = C.scan_md(str(path))
        else:
            path.write_text(body, encoding="utf-8")
            errors, warnings, _ = C.scan_html(str(path))
    return errors, warnings


def kinds(found):
    return [k for k, *_ in ((x[1], x[2]) if len(x) == 3 else x for x in found)]


def paired_warnings(warnings):
    return [x for x in warnings if C.PAIR_GEOT_NAME in str(x)]


class PairedGeotHeadingTests(unittest.TestCase):

    def test_paired_headings_are_errors_in_every_shape(self) -> None:
        for heading in ("## 재설계 범위 — 덜어낸 것과 남긴 것", "## 얻는 것과 잃는 것",
                        "## 할 수 있는 것과 없는 것", "## 실장 판단 — 해결된 것과 남은 것 🆕",
                        "## 각 안이 잘 잡은 것 / 두 안이 다르게 답한 것", "## 가진 것·비어 있는 것",
                        "## 5년 안에 바뀌는 것 vs 10년 가는 것"):
            for form in ("prose", "structured"):
                with self.subTest(heading=heading, form=form):
                    errors, warnings = scan(heading + "\n", form)
                    self.assertIn(TITLE, kinds(errors))
                    self.assertEqual(paired_warnings(warnings), [],
                                     "제목에 주의를 겹쳐 내면 같은 줄이 두 번 나옵니다")

    def test_html_heading_is_an_error_without_a_duplicate_warning(self) -> None:
        html = ('<html><head><meta name="form" content="prose"></head><body>'
                '<h1>재설계 계획</h1><p>재설계 범위와 일정을 정리했습니다.</p>'
                '<h2>재설계 범위 — 덜어낸 것과 남긴 것</h2><p>본문입니다.</p></body></html>')
        errors, warnings = scan(html, suffix=".html")
        self.assertIn(TITLE, kinds(errors))
        self.assertEqual(paired_warnings(warnings), [])

    def test_paired_value_is_a_warning(self) -> None:
        errors, warnings = scan("- **범위** — 바뀐 것과 바뀌지 않은 것\n- 확인한 것과 확인하지 못한 것\n",
                                "structured")
        self.assertNotIn(TITLE, kinds(errors))
        self.assertEqual(len(paired_warnings(warnings)), 2)
        html = ('<html><head><meta name="form" content="prose"></head><body>'
                '<h1>재설계 계획</h1><p>재설계 범위와 일정을 정리했습니다.</p>'
                '<ul><li>확인한 것과 확인하지 못한 것</li></ul></body></html>')
        _, warnings = scan(html, suffix=".html")
        self.assertEqual(len(paired_warnings(warnings)), 1)

    def test_lookalikes_pass(self) -> None:
        body = ("## 하지 말 것\n\n## 할 것과 하지 말 것\n\n## 측정한 것과 같은 값\n\n## 「덜어낸 것과 남긴 것」\n\n"
                "- 처음에만 할 것, 이후 빌드에서는 절대 하지 말 것\n"
                "- 고객이 요청한 것과 같은 것\n"
                "- 막힌 것 · 늦어질 이유 · 다른 묶음에 기대는 것\n"
                "- 기대한 것과 실제 나온 것이 다릅니다.\n"
                "- `얻는 것과 잃는 것`은 코드입니다.\n\n"
                "일을 하는 것과 일을 적는 것은 다릅니다. 고친 것, 결정이 필요한 것, 그대로 둔 것으로 나눴습니다.\n")
        errors, warnings = scan(body)
        self.assertNotIn(TITLE, kinds(errors))
        self.assertEqual(paired_warnings(warnings), [])

    def test_pattern_needs_an_adnominal_before_each_geot(self) -> None:
        self.assertIsNone(C.PAIR_GEOT.search("그것과 이것"))
        self.assertIsNone(C.PAIR_GEOT.search("이 문서의 목적과 범위"))
        # 「것」 앞이 받침 ㄴ·ㄹ 음절이 아니면 관형형이 아님(띄어 쓴 지시 관형사)
        self.assertIsNone(C.PAIR_GEOT.search("이 것과 저 것"))
        self.assertIsNotNone(C.PAIR_GEOT.search("버린 것과 지킨 것"))
        self.assertIsNotNone(C.PAIR_GEOT.search("남길 것과 버릴 것"))


if __name__ == "__main__":
    unittest.main()
