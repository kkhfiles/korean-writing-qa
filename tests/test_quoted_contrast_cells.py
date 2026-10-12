"""목록 항목 안에 틀린 예 · 고친 예 칸이 인용뿐이면 절단형으로 걸지 않는지 못 박는다.

**무엇이 틀려 있었나.** `all_quoted` 가 「값 전체가 인용인가」를 볼 때 인용을 지우고 남은
공백 · 가운뎃점은 지웠지만 줄바꿈은 안 지웠다. 목록 항목 하나에 칸 둘(`<div>`)이 있으면
칸 사이에 줄바꿈이 남아 「인용뿐」으로 안 보였고, 끝 인용 「…결과에서」가 조사 종결로
「절단형 종결」(오류)에 걸렸다. 2026-10-07 사례집에서 고친 예 칸 끝의 「로 바꿈」을
지우자 발행이 막혔다.

**고쳐도 잃는 것이 없다** — 실문서 1,325개를 고치기 전 · 뒤로 나란히 재서 「절단형 종결」
140 → 140, 사라진 지적 0건(2026-10-12). 그래서 이 시험은 **인용 칸은 풀리고, 인용이
아닌 값은 그대로 걸리는지** 둘 다 본다.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

CHECKER = repo_paths.CHECKER
HEAD = '<h1>사례 모음</h1>\n<p class="lede">대조 예시 확인 · 시험용</p>\n'


def pair(bad: str, good: str) -> str:
    return (f'<ul><li><div class="ba bad"><p>{bad}</p></div>'
            f'<div class="ba good"><p>{good}</p></div></li></ul>')


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuotedContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def cut_errors(self, body: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.html"
            target.write_text(HEAD + body, encoding="utf-8")
            errors, _warnings, _ = self.checker.scan_html(str(target))
        return [text for kind, text in errors if kind == "절단형 종결"]

    def test_quote_only_cells_are_not_cut(self) -> None:
        # 2026-10-07 사례집 그대로 — 고친 예 칸이 인용 둘뿐
        got = self.cut_errors(pair("「앞 판에서」", "「앞 실험에서」 · 「먼저 측정한 결과에서」"))
        self.assertEqual([], got, "인용뿐인 칸을 절단형으로 걸었습니다")

    def test_a_plain_cut_value_is_still_caught(self) -> None:
        # 인용이 아닌 글이 조사로 끝나면 칸이 둘이어도 그대로 걸려야 한다
        got = self.cut_errors(pair("「앞 판에서」", "새 자료는 해당 폴더에"))
        self.assertTrue(got, "인용 아닌 절단형 값이 빠졌습니다 — 인용 판정이 넓어졌습니다")

    def test_a_cut_value_beside_a_quote_is_still_caught(self) -> None:
        got = self.cut_errors(pair("「앞 판에서」", "「앞 실험에서」 · 고친 결과를"))
        self.assertTrue(got, "인용 옆의 절단형 글이 빠졌습니다")


if __name__ == "__main__":
    unittest.main()
