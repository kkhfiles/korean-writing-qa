"""덩어리 태그가 지워지면서 두 칸의 글자가 붙지 않는지 못 박는다.

**무엇이 틀려 있었나.** `strip()` 이 모든 태그를 빈 문자열로 지워
`<dt>쓰는 곳</dt><dd>사내 메신저</dd>` 가 **「쓰는 곳사내 메신저」**로 붙었다.
화면에서는 두 줄인데 검사기에는 한 낱말로 보인다.

**무엇이 문제인가 — 발췌다.** 지적의 발췌는 사람이 **그 글자를 찾아가는 길**이다.
붙은 발췌를 받으면 문서에 없는 낱말을 찾게 된다. 2026-09-18 에 첫 화면 소개
페이지를 검사하다 「쓰는 곳사내 메신저」를 보고 알았다.

**판정은 안 바뀐다** — HTML 84개 전수로 재서 새로 나는 지적 0 · 가려졌던 지적 0
(2026-09-18). 고친 값은 발췌 하나다. 그래서 이 시험은 **지적 수가 아니라 발췌
글자**를 본다.

⚠️ **남는 한계 — 규칙 쪽은 아직 줄을 안 가른다.** 규칙 쉰 곳이 `\\s*` 로 띄어쓰기를
받는데 그것이 줄바꿈도 받는다. 그래서 `<li>닿는</li><li>값을 적음</li>` 은 지금도
「지어낸 명사구」 오류가 난다. 실문서 84개에서 0건이라 **고치지 않고 적어 둔다** —
규칙 쉰 곳을 줄바꿈만 막게 고치는 쪽이 이득보다 위험이 크다. 실제로 나면 그때
그 규칙만 고친다.
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

HEAD = '<meta name="form" content="prose">\n<title>칸 경계</title>\n'

#: 붙으면 안 되는 짝 — (마크업, 붙은 꼴, 갈라진 꼴)
PAIRS = [
    ("라벨과 값",
     "<dl><div><dt>쓰는 곳</dt><dd>사내 메신저</dd></div></dl>",
     "곳사내", "곳 사내"),
    ("표의 두 칸",
     "<table><tr><td>확인</td><td>할 지점</td></tr></table>",
     "확인할", "확인 할"),
    ("목록의 두 줄",
     "<ul><li>먼저 봄</li><li>사람이 정함</li></ul>",
     "봄사람", "봄 사람"),
]

#: 인라인은 화면에서도 붙어 보이므로 **붙는 것이 맞다.**
INLINE = [
    ("굵게", "<p>닿는 <b>값</b>을 적음</p>", "닿는 값"),
    ("링크", '<p>여기 <a href="/x">문서</a>를 봄</p>', "여기 문서를 봄"),
]


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BlockBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def stripped(self, markup: str) -> str:
        return self.checker.strip(markup)

    def test_block_tags_leave_a_break(self) -> None:
        """덩어리 태그 자리에 줄이 남아야 두 칸의 글자가 안 붙는다."""
        for name, markup, joined, apart in PAIRS:
            with self.subTest(case=name):
                text = " ".join(self.stripped(markup).split())
                self.assertNotIn(joined, text,
                                 f"칸이 붙었습니다: {text}")
                self.assertIn(apart, text, f"갈라진 꼴을 못 찾았습니다: {text}")

    def test_inline_tags_stay_joined(self) -> None:
        """인라인 태그는 화면에서 붙어 보이므로 갈라 놓으면 안 된다.

        갈라 놓으면 `닿는 <b>값</b>` 처럼 강조를 낀 표현이 규칙을 빠져나간다.
        """
        for name, markup, want in INLINE:
            with self.subTest(case=name):
                text = " ".join(self.stripped(markup).split())
                self.assertIn(want, text, f"인라인이 갈라졌습니다: {text}")

    def test_the_report_quotes_the_document(self) -> None:
        """지적의 발췌가 문서에 실제로 있는 글자여야 한다.

        이 시험이 증상을 그대로 잰다 — 붙은 발췌가 나가면 읽는 사람이
        **문서에 없는 낱말**을 찾는다.
        """
        body = HEAD + "<dl><div><dt>쓰는 곳</dt><dd>사내 메신저</dd></div></dl>"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.html"
            target.write_text(body, encoding="utf-8")
            errors, warnings, _ = self.checker.scan_html(str(target))
        found = [text for _kind, text in list(errors) + list(warnings)]
        self.assertTrue(found, "지적이 하나도 없어 발췌를 못 봅니다 — "
                               "규칙이 바뀌었으면 이 예문도 같이 고칩니다")
        for text in found:
            self.assertNotIn("곳사내", text, f"발췌가 붙어 있습니다: {text}")


if __name__ == "__main__":
    unittest.main()
