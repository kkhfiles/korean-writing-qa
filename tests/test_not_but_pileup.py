"""「~가 아니라」 대구가 한 문서에 몰렸는지 — 건수와 밀도를 함께 본다.

**한 번은 정상이다.** 사람 업무 문서에도 「함수를 비교하는 것이 아니라 결과를 비교」가
나온다. 신호는 한 문서에 몰리는 것이다(300자 넘는 문서 중 두 번 이상 쓴 비율 · 사람
0.4% 대 AI 7.1%, 2026-10-23 실측). 긴 문서에 두 번 나온 것은 사람 수준이라 밀도로 거른다.

**왜 사례집(`C-2xx`)으로 다 못 지키나.** 그 시험틀은 한 줄을 넣는다. 밀도 문턱과 지시 파일
제외, HTML 겹친 태그 중복은 문서를 지어 봐야 갈린다.
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
TWO = "이번 도입은 비용 절감이 아니라 품질 확보가 목적입니다. 바뀌는 것은 도구가 아니라 일하는 순서입니다."
FILLER = "시험 장비는 다음 달 첫 주에 들어오고 담당 팀이 설치와 점검을 함께 맡습니다. "
KIND = "「~가 아니라」 반복"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NotButPileupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not repo_paths.CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {repo_paths.CHECKER}")
        cls.checker = load_checker()

    def warns(self, body, name="doc.md", sub=""):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / sub if sub else Path(directory)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / name
            path.write_text(body, encoding="utf-8")
            scan = self.checker.scan_html if name.endswith(".html") else self.checker.scan_md
            err, warn, _ = scan(str(path))
            err, warn = self.checker.apply_instruction_file(err, warn, str(path))
        return [i[1] if len(i) == 3 else i[0] for i in warn]

    def test_two_in_a_short_document_is_flagged(self) -> None:
        self.assertIn(KIND, self.warns(HEAD + TWO + "\n"))

    def test_one_is_normal(self) -> None:
        self.assertNotIn(KIND, self.warns(HEAD + "이번 도입은 비용 절감이 아니라 품질 확보가 목적입니다.\n"))

    def test_two_in_a_long_document_stay_below_the_density_line(self) -> None:
        """한글 1만 자당 3 아래면 사람 수준이다 — 긴 보고서의 두 번은 조용해야 한다."""
        self.assertNotIn(KIND, self.warns(HEAD + TWO + "\n\n" + FILLER * 300 + "\n"))

    def test_quoted_examples_are_not_counted(self) -> None:
        body = HEAD + "「비용 절감이 아니라 품질」과 「도구가 아니라 순서」는 인용입니다.\n"
        self.assertNotIn(KIND, self.warns(body))

    def test_instruction_files_are_spared(self) -> None:
        """지시 파일은 구분을 세우는 글이라 밀도가 원래 높다 — 반말처럼 뺀다."""
        self.assertNotIn(KIND, self.warns(HEAD + TWO + "\n", name="SKILL.md"))

    def test_html_counts_nested_tags_once(self) -> None:
        """`<li><p>…</p></li>` 는 같은 글이 두 번 들어온다 — 한 번 쓴 것을 두 번으로 세면 안 된다."""
        page = ('<!doctype html><html><head><meta name="form" content="prose"><title>검토</title>'
                '</head><body><h1>도입 검토</h1><ul><li><p>이번 도입은 비용 절감이 아니라 '
                '품질 확보가 목적입니다.</p></li></ul></body></html>')
        self.assertNotIn(KIND, self.warns(page, name="doc.html"))

    def test_html_two_are_flagged(self) -> None:
        page = ('<!doctype html><html><head><meta name="form" content="prose"><title>검토</title>'
                f'</head><body><h1>도입 검토</h1><p>{TWO}</p></body></html>')
        self.assertIn(KIND, self.warns(page, name="doc.html"))


if __name__ == "__main__":
    unittest.main()
