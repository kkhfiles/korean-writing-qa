"""닫은 지적과 사용자 답이 **짚은 표현이 든 문장**에 묶이는지 본다 — 모델은 안 부른다.

(2026-11-24 블로그 원고 인계) 닫음 기록과 답 기록이 줄 해시에만 묶여 있어, 한 줄에 문장이 여럿인 문단에서
다른 문장 하나만 고쳐도 같은 근거로 다시 닫아야 했고(세 번), 「그대로」라고 답한 표현을 다시 물었고, 표를 만든
뒤 무관한 문장을 고치면 답을 통째로 거절했다. 명령 끝 줄이 다른 지적의 근거 문장이라 성패도 못 갈랐다.

**지키는 것**

- 닫은 고칠 지적 — 같은 줄의 다른 문장만 고치면 닫힌 채로 남음 · 짚은 표현이 든 문장을 고치면 다시 열림
- 「그대로」 답한 사람 확인 — 다른 문장만 고쳐 다시 판정해도 다시 묻지 않음 · 그 문장을 고치면 다시 물음
- 표 답 — 표를 만든 뒤 다른 문장만 바뀌었으면 받음
- `--dismiss` 와 `--answer` 의 끝 줄은 처리 결과 · 이미 닫힌 줄의 `--answer` 는 오류가 아님
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402

FIRST = "출처는 주제 문서입니다."
SECOND = "자료는 매주 갱신합니다."
DOC = ["# 소개", "", f"{FIRST} {SECOND}", "", "마감이 가까운 업무를 맨 위에 둡니다."]
FIX = {"line": 3, "phrase": "주제 문서", "category": "원문 용어를 직역한 말",
       "fix": "주제 문서(Topic Paper)", "why": "시험", "decide": "fix"}
ASK = dict(FIX, decide="ask")
OTHER_SENTENCE = f"{FIRST} 자료는 매일 갱신합니다."
SAME_SENTENCE = f"출처는 주제 문서이고 원문 이름은 뒤에 적습니다. {SECOND}"


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS = self.dir / "answers.jsonl"
        coverage.DECISIONS = self.dir / "decisions.jsonl"
        coverage.DISMISSALS = self.dir / "dismissals.jsonl"
        self.doc = self.dir / "d.md"
        self.sheet = self.dir / "asks.md"
        self.write(DOC[2])

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = self.saved
        self.tmp.cleanup()

    def write(self, line3: str) -> None:
        lines = list(DOC)
        lines[2] = line3
        self.doc.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_main(self, argv, backend=None) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main(argv, backend=backend)
        return rc, out.getvalue()

    def judge_with(self, item: dict) -> None:
        rc, out = self.run_main([str(self.doc)], backend=FakeBackend([item]).pair())
        self.assertEqual(0, rc, out[-300:])

    def lines(self) -> list[str]:
        return coverage.read_doc(self.doc).splitlines()

    def open_fixes(self) -> list[int]:
        return sorted({n for n, _ in coverage.open_fixes(coverage.doc_key(self.doc), self.lines(), judge.LOG)})

    def open_asks(self) -> list[int]:
        return sorted({n for n, _ in coverage.open_asks(coverage.doc_key(self.doc), self.lines(), judge.LOG)})

    @staticmethod
    def last_line(out: str) -> str:
        return [l for l in out.splitlines() if l.strip()][-1]


class DismissedFixTests(_Base):

    def setUp(self) -> None:
        super().setUp()
        self.judge_with(FIX)
        judge.dismiss(self.doc, 3, "대상아님", "이 문서는 원문 용어를 그대로 쓰기로 정한 내부 용어 목록입니다")

    def test_editing_another_sentence_keeps_it_closed(self) -> None:
        self.write(OTHER_SENTENCE)
        self.assertEqual([], self.open_fixes(), "다른 문장만 고쳤는데 닫은 지적이 다시 열렸습니다")
        self.judge_with(FIX)
        self.assertEqual([], self.open_fixes(), "다시 판정한 같은 지적이 같은 문장에서 다시 열렸습니다")

    def test_editing_the_sentence_with_the_phrase_reopens_it(self) -> None:
        self.write(SAME_SENTENCE)
        self.assertEqual([3], self.open_fixes(), "짚은 표현이 든 문장을 고쳤는데 닫은 채로 남았습니다")


class KeptAskTests(_Base):

    def setUp(self) -> None:
        super().setUp()
        self.judge_with(ASK)
        rc, out = self.run_main([str(self.doc), "--sheet", str(self.sheet)])
        self.assertEqual(1, rc, out[-300:])

    def test_a_kept_phrase_is_not_asked_again_after_another_sentence_changes(self) -> None:
        self.run_main(["--answers-from", str(self.sheet), "--reply", "Q1 그대로"])
        self.write(OTHER_SENTENCE)
        self.judge_with(ASK)
        self.assertEqual([], self.open_asks(), "「그대로」 답한 표현을 다른 문장만 고친 뒤 다시 물었습니다")

    def test_a_kept_phrase_is_asked_again_when_its_sentence_changes(self) -> None:
        self.run_main(["--answers-from", str(self.sheet), "--reply", "Q1 그대로"])
        self.write(SAME_SENTENCE)
        self.judge_with(ASK)
        self.assertEqual([3], self.open_asks(), "답한 문장이 바뀌었는데 다시 묻지 않았습니다")

    def test_an_answer_is_taken_when_only_another_sentence_changed(self) -> None:
        self.write(OTHER_SENTENCE)
        rc, out = self.run_main(["--answers-from", str(self.sheet), "--reply", "Q1 그대로"])
        self.assertNotIn("바뀌었습니다", out, "무관한 문장이 바뀌었다고 답을 거절했습니다")
        self.assertIn("그대로 — 답 기록에 남김 1건", out)
        self.assertEqual([], self.open_asks())

    def test_an_answer_is_refused_when_the_sentence_changed(self) -> None:
        self.write(SAME_SENTENCE)
        rc, out = self.run_main(["--answers-from", str(self.sheet), "--reply", "Q1 그대로"])
        self.assertIn("그 줄이 바뀌었습니다", out, "사용자가 본 문장과 다른 문장에 답을 적었습니다")


class ResultLineTests(_Base):

    def test_dismiss_ends_with_its_result(self) -> None:
        self.judge_with(FIX)
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "대상아님",
                                 "--note", "이 문서는 원문 용어를 그대로 쓰기로 정한 내부 용어 목록입니다"])
        self.assertEqual(0, rc, out)
        self.assertTrue(self.last_line(out).startswith("결과 — 「주제 문서」 받지 않음(대상아님)"), out)

    def test_answering_a_closed_line_is_not_an_error(self) -> None:
        self.judge_with(ASK)
        argv = [str(self.doc), "--answer", "3", "--note", "사용자 답: 그대로"]
        rc, out = self.run_main(argv)
        self.assertEqual(0, rc, out)
        self.assertTrue(self.last_line(out).startswith("결과 — 답 기록함"), out)
        rc, out = self.run_main(argv)
        self.assertEqual(0, rc, out)
        self.assertIn("이미 닫혔습니다", out)
        self.assertTrue(self.last_line(out).startswith("결과 — 이미 닫혀"), out)


if __name__ == "__main__":
    unittest.main()
