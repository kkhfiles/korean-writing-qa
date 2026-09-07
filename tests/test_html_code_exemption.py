"""HTML 경로가 코드를 빼되 **맨 `<pre>` 는 빼지 않는지** 지킨다.

**무엇이 갈렸나.** 규칙 문서는 「검사에서 빠지는 구간」에 인라인 코드와 코드펜스를
적어 두었는데 마크다운 경로만 그것을 지켰다. 같은 코드 블록을 두 형식에 넣으면
마크다운 0건 · HTML 오류 2건이었다. 제목 검사(2026-09-02)·문단 검사(09-04)에 이어
**세 번째로 같은 모양의 결함**이다.

**넓게 잡았다가 좁혔다.** 처음에는 `<pre>` 를 통째로 뺐다. 실문서로 재니 업무 칸반
한 장에서 지적 44건이 사라졌는데, 그 파일의 `<pre>` 33개는 코드가 아니라 **공백을
살리려고 감싼 한국어 기록**이었다. 그대로 뒀으면 그 문장들이 검사에서 통째로 빠지고
아무도 다시 안 봤을 것이다 — 「예외를 넓게 잡으면 그 안의 미탐은 아무도 다시 안
본다」가 그대로 재현될 뻔했다.

**HTML 에서 코드 의미를 지는 것은 `<code>` 다.** `<pre>` 는 「미리 서식된 글」이지
코드가 아니다. 마크다운 코드펜스에 대응하는 것은 `<pre><code>` 다.

| 무엇 | 마크다운 | HTML | 검사하나 |
|---|---|---|---|
| 코드 블록 | 코드펜스 | `<pre><code>` | 안 함 |
| 인라인 코드 | 백틱 | `<code>` | 안 함 |
| 서식만 살린 글 | 해당 없음 | 맨 `<pre>` | **함** |

좁힌 뒤 실문서 35개 재측정 — 오류 109 그대로 · 주의 83 그대로 · 사라진 지적 0건.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

CODE = "결과를 파일로 저장한다\n값이 잘못 계산되어진다\n우리 제품이 아니다"
HEAD = ('<h1>실행 결과</h1><p class="lede">검사 대상 — 표본</p>'
        '<dl><dt>기한</dt><dd>9월 7일</dd></dl>')
MD_HEAD = "---\nform: structured\n---\n\n# 실행 결과\n\n**검사 대상** — 표본\n\n"


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CodeExemptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not repo_paths.CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {repo_paths.CHECKER}")
        cls.checker = load_checker()
        cls.source = repo_paths.CHECKER.read_text(encoding="utf-8")

    def scan(self, name: str, text: str):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / name
            target.write_text(text, encoding="utf-8")
            fn = self.checker.scan_md if name.endswith(".md") else self.checker.scan_html
            err, warn, slots = fn(str(target), False, None)

        def kind(item):
            return item[1] if len(item) == 3 else item[0]

        return sorted({kind(i) for i in err}), sorted({kind(i) for i in warn}), slots

    def test_markdown_code_fence_is_exempt(self) -> None:
        """기준선 — 마크다운 쪽이 이미 하던 것이다."""
        err, warn, _ = self.scan("doc.md", MD_HEAD + "```\n" + CODE + "\n```\n")
        self.assertEqual(([], []), (err, warn))

    def test_pre_code_matches_the_markdown_fence(self) -> None:
        """같은 내용이 형식에 따라 다르게 판정되면 안 된다."""
        err, warn, _ = self.scan("doc.html", HEAD + f"<pre><code>{CODE}</code></pre>")
        self.assertEqual(([], []), (err, warn))

    def test_inline_code_is_exempt(self) -> None:
        err, warn, _ = self.scan(
            "doc.html", HEAD + "<dl><dt>명령</dt><dd><code>결과를 파일로 저장한다</code></dd></dl>")
        self.assertEqual(([], []), (err, warn))

    def test_a_bare_pre_is_still_checked(self) -> None:
        """★ 맨 `<pre>` 는 코드가 아니다 — 서식만 살린 한국어 글이 여기 들어온다."""
        err, warn, _ = self.scan("doc.html", HEAD + f"<pre>{CODE}</pre>")
        self.assertIn("이중 피동", err)
        self.assertIn("모호한 지칭", err)

    def test_a_value_made_only_of_code_still_counts_as_a_slot(self) -> None:
        """슬롯이 0이 되면 「값 슬롯 미인식」으로 넘어간다 — 그건 못 본 것이 아니다."""
        _, _, slots = self.scan(
            "doc.html", '<h1>실행 결과</h1><p class="lede">검사 대상 — 표본</p>'
                        "<dl><dt>명령</dt><dd><code>결과를 저장한다</code></dd></dl>")
        self.assertGreaterEqual(slots, 1, "코드뿐인 값 칸이 슬롯에서 사라졌습니다")

    def test_the_wide_version_stays_out_of_the_source(self) -> None:
        """되살아나면 업무 기록 44건이 다시 조용히 빠진다."""
        self.assertNotIn("r'(<pre[^>]*>).*?(</pre>)'", self.source,
                         "맨 <pre> 를 통째로 빼는 판이 되살아났습니다")


if __name__ == "__main__":
    unittest.main()
