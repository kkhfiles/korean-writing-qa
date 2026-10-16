"""처리 기록(`--dismiss`)의 근거 대조와 표현 고르기가 세션을 헛걸음시키지 않는지 본다 — 모델은 안 부른다.

(2026-10-14 lab-docs 보고) ① 근거를 「<경로> 「인용」 — 원문 965행 6.2 절 안」으로 적었더니 965행을 이 문서(363행)의
줄로 읽고 거절했다. ② 링크 주소까지 든 긴 표현의 일부만 `--phrase` 로 주면 「그 지적이 없습니다」로 거절해,
세션이 표현을 통째로 옮기는 스크립트를 따로 짰다.

**지키는 것**

- 경로 뒤에 나온 「N행」은 그 파일의 줄로 대조한다(바로 뒤가 아니어도) · 「문서 N행」은 이 문서의 줄로 대조한다
- 경로가 없으면 이 문서의 줄로 대조한다 · 어느 쪽이든 없는 줄이면 거절한다(대조를 풀지 않는다)
- `--phrase` 는 정확히 같은 표현이 먼저 · 없으면 일부가 맞는 지적이 하나일 때만 고른다
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_rejudge_context import Scripted  # noqa: E402


class LineRefTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.src = self.dir / "source.txt"
        self.src.write_text("\n".join(f"원문 {i}번째 줄" for i in range(1, 1001)) + "\n", encoding="utf-8")
        self.doc = self.dir / "d.md"
        self.lines = ["# 문서"] + [f"본문 {i}" for i in range(1, 50)]
        self.doc.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        self.path = self.src.as_posix()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def problems(self, note: str) -> list[str]:
        return judge.evidence_problems(self.doc, note, self.lines)

    def test_a_line_after_the_path_belongs_to_that_file(self) -> None:
        self.assertEqual([], self.problems(f"{self.path} 「원문 965번째 줄」 — 이 문장은 원문 965행 안(991행)"))

    def test_a_line_beyond_the_file_is_still_refused(self) -> None:
        got = self.problems(f"{self.path} 「원문 9번째 줄」 — 원문 1200행")
        self.assertTrue(any("source.txt" in p for p in got), "그 파일에 없는 줄을 받았습니다")

    def test_document_lines_are_checked_against_the_document(self) -> None:
        self.assertEqual([], self.problems(f"{self.path} 「원문 9번째 줄」 · 이 문서 12행에서 충족"))
        self.assertTrue(self.problems(f"{self.path} 「원문 9번째 줄」 · 이 문서 120행에서 충족"))

    def test_without_a_path_lines_are_the_documents(self) -> None:
        self.assertEqual([], self.problems("12행에 정의가 있음"))
        self.assertTrue(self.problems("965행에 정의가 있음"))


class PhraseTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG
        judge.LOG = self.dir / "calls.jsonl"
        self.doc = self.dir / "d.md"
        self.doc.write_text("# 출처\n\n출처는 [RTCA FTP1055](https://example.com/very/long/link.pdf) · FTP1055 주제 문서입니다.\n",
                            encoding="utf-8")
        two = [{"line": 3, "phrase": "[RTCA FTP1055](https://example.com/very/long/link.pdf)", "category": "시험",
                "fix": "고친 말", "why": "시험", "decide": "fix"},
               {"line": 3, "phrase": "FTP1055 주제 문서", "category": "시험", "fix": "FTP1055 주제 문서(Topic Paper)",
                "why": "시험", "decide": "fix"}]
        judge.judge(self.doc, "opus", 10, Scripted([two]).pair())

    def tearDown(self) -> None:
        judge.LOG = self.saved
        self.tmp.cleanup()

    def test_a_unique_part_picks_the_finding(self) -> None:
        _, fx = judge._pick_fix(self.doc, 3, "RTCA")
        self.assertTrue(str(fx["phrase"]).startswith("[RTCA FTP1055]"))

    def test_an_ambiguous_part_is_refused_with_the_choices(self) -> None:
        with self.assertRaises(ValueError) as e:
            judge._pick_fix(self.doc, 3, "FTP1055")
        self.assertIn("일부가 맞는 지적이 여럿", str(e.exception))
        self.assertIn("FTP1055 주제 문서", str(e.exception))

    def test_an_exact_phrase_wins(self) -> None:
        _, fx = judge._pick_fix(self.doc, 3, "FTP1055 주제 문서")
        self.assertEqual("FTP1055 주제 문서", fx["phrase"])


if __name__ == "__main__":
    unittest.main()
