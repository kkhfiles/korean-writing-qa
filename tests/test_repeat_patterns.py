"""「반복 문형」 — 한 번은 정상인데 문단이나 문서에 몰리면 짚는다(im-not-ai 2.3.2 밀집 조건).

**왜 사례집으로 다 못 지키나.** 문단 경계, 이어진 문장 수, 문단 끝 당위는 문서를 지어 봐야
갈린다. 정상 쪽 짝(한 번씩 쓴 것)을 같이 두어 문턱이 낮아지는 것을 막는다.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HEAD = "---\nform: prose\n---\n# 도입 검토\n\n"
KIND = "반복 문형"


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepeatPatternTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not repo_paths.CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {repo_paths.CHECKER}")
        cls.checker = load_checker()

    def notes(self, paragraphs, html=False):
        with tempfile.TemporaryDirectory() as directory:
            if html:
                path = Path(directory) / "doc.html"
                body = "".join(f"<p>{p}</p>" for p in paragraphs)
                path.write_text('<!doctype html><html><head><meta name="form" content="prose">'
                                f'<title>검토</title></head><body><h1>도입 검토</h1>{body}</body></html>',
                                encoding="utf-8")
                _err, warn, _ = self.checker.scan_html(str(path))
            else:
                path = Path(directory) / "doc.md"
                path.write_text(HEAD + "\n\n".join(paragraphs) + "\n", encoding="utf-8")
                _err, warn, _ = self.checker.scan_md(str(path))
        return [i[-1] for i in warn if (i[1] if len(i) == 3 else i[0]) == KIND]

    def test_three_about_in_one_paragraph(self) -> None:
        para = "보안 정책에 대해 검토하고, 접근 권한에 대해 정리하며, 로그 보관에 대해 결정합니다."
        for html in (False, True):
            self.assertTrue(any("「~에 대해」 밀집" in n for n in self.notes([para], html)), html)

    def test_about_spread_over_paragraphs_is_normal(self) -> None:
        paras = ["보안 정책에 대해 검토합니다.", "접근 권한에 대해 정리합니다.", "로그 보관에 대해 결정합니다."]
        self.assertFalse(any("「~에 대해」 밀집" in n for n in self.notes(paras)))

    def test_four_can_endings_in_a_row(self) -> None:
        para = ("시험을 실행할 수 있습니다. 결과를 비교할 수 있습니다. "
                "보고서를 만들 수 있습니다. 이력을 추적할 수 있습니다.")
        for html in (False, True):
            self.assertTrue(any("「~할 수 있다」 연속" in n for n in self.notes([para], html)), html)

    def test_can_endings_broken_by_another_sentence_are_normal(self) -> None:
        """문단 안 건수가 아니라 이어진 문장을 센다 — 기능 설명서 문단이 통째로 걸리지 않게."""
        para = ("시험을 실행할 수 있습니다. 결과를 비교할 수 있습니다. 결과는 표로 남습니다. "
                "보고서를 만들 수 있습니다. 이력을 추적할 수 있습니다.")
        self.assertFalse(any("「~할 수 있다」 연속" in n for n in self.notes([para])))

    def test_second_paragraph_ending_in_duty(self) -> None:
        paras = ["담당 팀은 보안 점검을 강화해야 합니다.", "운영 팀은 점검 주기를 줄여야 합니다."]
        for html in (False, True):
            self.assertTrue(any("당위로 끝나는 문단 반복" in n for n in self.notes(paras, html)), html)

    def test_one_duty_paragraph_is_normal(self) -> None:
        paras = ["담당 팀은 보안 점검을 강화해야 합니다.", "운영 팀은 다음 달에 점검 주기를 정합니다."]
        self.assertFalse(any("당위로" in n for n in self.notes(paras)))

    def test_same_english_gloss_twice(self) -> None:
        paras = ["인공지능(AI)은 문서를 검토합니다.", "검토 결과는 인공지능(AI)이 요약합니다."]
        self.assertTrue(any("영어 병기 반복" in n for n in self.notes(paras)))

    def test_gloss_once_is_normal(self) -> None:
        paras = ["인공지능(AI)은 문서를 검토합니다.", "검토 결과는 인공지능이 요약합니다."]
        self.assertFalse(any("영어 병기 반복" in n for n in self.notes(paras)))

    def test_jeok_chain_in_one_document(self) -> None:
        para = "전략적 함의와 실천적 기반, 구조적 변화를 차례로 다룹니다."
        self.assertTrue(any("「~적 N」 반복" in n for n in self.notes([para])))


if __name__ == "__main__":
    unittest.main()
