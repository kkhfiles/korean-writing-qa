"""문서가 적어 둔 형식(`form:`)을 검사기가 제대로 읽는지 본다.

**왜 있나.** (2026-10-13) 형식을 읽을 때 HTML 용 표시(`<meta name="form" content="prose">`)를 파일 앞
4,096자에서 **먼저** 찾았다. 사용 안내 본문에 그 표시를 설명하는 예시가 코드로 들어 있어, 머리말에
`form: structured` 라고 적었는데도 산문으로 판정되고 개조식 검사가 꺼진 채 통과해 왔다(감춰진 오류 12건).
위쪽에 글이 늘어 예시가 4,096자 밖으로 밀리자 드러났다. `docs/architecture.md` 도 같은 결함에 걸려 있었다.

**지키는 것** — 머리말이 있으면 머리말만 본다. HTML 표시는 머리말이 없을 때만, 코드 밖의 것만 본다.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "assets" / "doc-style-check.py"
EXAMPLE = '| HTML | `<meta name="form" content="prose">` |\n'


def load():
    spec = importlib.util.spec_from_file_location("doc_style_check_form", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeclaredFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load()

    def test_front_matter_wins_over_an_html_example_in_the_body(self) -> None:
        raw = "---\nform: structured\n---\n\n# 안내\n\n" + EXAMPLE
        self.assertEqual("structured", self.m.declared_form(raw))

    def test_front_matter_without_form_is_not_filled_by_the_example(self) -> None:
        raw = "---\nname: 스킬\n---\n\n# 안내\n\n" + EXAMPLE
        self.assertIsNone(self.m.declared_form(raw), "머리말에 형식이 없는데 본문 예시로 정했습니다")

    def test_an_example_in_backticks_is_not_a_declaration(self) -> None:
        raw = "# 안내\n\n형식을 적는 법 — " + EXAMPLE
        self.assertIsNone(self.m.declared_form(raw))

    def test_a_real_html_meta_is_read(self) -> None:
        raw = '<!doctype html><html><head><meta name="form" content="prose"></head><body><p>글</p></body></html>'
        self.assertEqual("prose", self.m.declared_form(raw))

    def test_front_matter_prose_is_read(self) -> None:
        self.assertEqual("prose", self.m.declared_form("---\nform: prose\n---\n\n# 소개\n"))


if __name__ == "__main__":
    unittest.main()
