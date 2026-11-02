"""재판정이 사실 주장의 근거를 받는지 본다 — 세션이 적은 근거(`--evidence`)와 창 밖의 닮은 줄. 모델은 안 부른다.

(2026-11-02) 사람 확인으로 올라온 2건이 모두 근거가 있는 줄이었다. 하나는 근거가 같은 문서 38줄 아래에 있었는데
재판정이 대상 앞뒤 20줄만 받아 「문서만으로 확인할 수 없음」을 냈다. 사용자가 두 길을 골랐다 — 고칠 때 근거를 함께
적어 재판정이 받게 하는 것, 창 밖에서 대상 줄과 닮은 줄을 함께 보내는 것.

**지키는 것**

- 근거는 경로와 그 파일 원문 인용, 또는 이 문서의 「N행」이어야 받고, 없는 파일과 파일에 없는 인용은 거절한다
- 기록한 줄의 재판정 프롬프트에 근거와 근거가 가리키는 문서 줄이 실린다 · 기록이 없으면 안 실린다
- 프롬프트는 근거 밖의 새 주장을 그대로 짚으라고 적는다
- 재판정 입력 저장과 재생에도 근거가 따라간다
- 창 밖의 닮은 줄은 글에 붙고 「판정기가 본 줄」에는 들지 않는다
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
import replay_rejudge as replay  # noqa: E402
from test_rejudge_context import Scripted  # noqa: E402

BASE = ["# 결과", "", "새 검사기의 회수율은 이전 판과 같은 수준입니다.", "", "Numbers are below."]
EDITED = list(BASE)
EDITED[2] = "새 검사기의 회수율은 이전 판보다 낮습니다."
DATA = '{"recall_diff": -0.13, "ci": [-0.19, -0.08]}'


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = (judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, coverage.INSTRUCTIONS,
                      coverage.EVIDENCE)
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, coverage.INSTRUCTIONS, coverage.EVIDENCE = (
            self.dir / f for f in ("a", "d", "x", "i", "e"))
        self.doc = self.dir / "d.md"
        self.doc.write_text("\n".join(EDITED) + "\n", encoding="utf-8")
        self.data = self.dir / "result.json"
        self.data.write_text(DATA, encoding="utf-8")
        self.note = f"{self.data.as_posix()} 「\"recall_diff\": -0.13」 — 신뢰구간이 0을 포함하지 않음"

    def tearDown(self) -> None:
        (judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, coverage.INSTRUCTIONS,
         coverage.EVIDENCE) = self.saved
        self.tmp.cleanup()

    def rejudge(self) -> Scripted:
        fake = Scripted([[]])
        judge.judge(self.doc, "opus", 10, fake.pair(), [3], BASE)
        return fake


class RecordTests(_Base):

    def test_a_note_without_a_source_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge.record_evidence(self.doc, 3, "결과 파일에서 확인했습니다")

    def test_a_quote_missing_from_the_file_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge.record_evidence(self.doc, 3, f"{self.data.as_posix()} 「\"recall_diff\": -0.50」")

    def test_a_missing_file_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge.record_evidence(self.doc, 3, f"{(self.dir / 'none.json').as_posix()} 「\"recall_diff\": -0.13」")

    def test_a_line_without_korean_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge.record_evidence(self.doc, 5, self.note)

    def test_the_cli_records_and_refuses(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, judge.main([str(self.doc), "--evidence", "3", "--note", self.note]))
            self.assertEqual(2, judge.main([str(self.doc), "--evidence", "3", "--note", "근거 없이 적은 메모입니다"]))
        self.assertEqual(1, len(coverage.EVIDENCE.read_text(encoding="utf-8").splitlines()))


class PromptTests(_Base):

    def test_the_evidence_reaches_the_rejudge(self) -> None:
        judge.record_evidence(self.doc, 3, self.note)
        user = self.rejudge().calls[0]["user"]
        self.assertIn("3행 근거: " + self.note, user)
        self.assertIn("근거가 말하지 않는 새 주장", user, "근거 밖 주장을 그대로 짚으라는 말이 없습니다")

    def test_a_document_line_reference_brings_that_line(self) -> None:
        judge.record_evidence(self.doc, 3, "문서 1행의 절 제목 아래 수치로 확인함")
        self.assertIn("(문서 1행: # 결과)", self.rejudge().calls[0]["user"])

    def test_no_record_no_evidence(self) -> None:
        self.assertNotIn("근거:", self.rejudge().calls[0]["user"])

    def test_replay_carries_the_evidence(self) -> None:
        judge.record_evidence(self.doc, 3, self.note)
        live = self.rejudge()
        case = replay.load_cases(self.dir / "korean-replay")[0]
        fake = Scripted([[]])
        replay.replay(case, case["context"], fake.pair(), "opus")
        self.assertEqual(live.calls[0]["user"], fake.calls[0]["user"])


def far_doc() -> list[str]:
    lines = ["# 측정", "", "요약: 엄격 기준 회수율은 새 판정기가 낮음.", ""]
    lines += [f"- 항목 {i}: 일정 회의록 정리와 배포 준비를 했습니다." for i in range(60)]
    lines += ["", "- 엄격 기준 회수율: 새 판정기 0.74, 단순 요청 0.87, 차이 −0.13(신뢰구간 −0.19~−0.08)"]
    return lines


class SupportTests(unittest.TestCase):

    def test_a_far_line_with_the_same_words_is_sent_but_not_seen(self) -> None:
        lines = far_doc()
        piece = judge.parts_for(lines, {3}, "fixed", Path("d.md"))[0]
        far = len(lines)
        self.assertIn(f"{far:>3} | {lines[far - 1]}", piece["document"])
        self.assertNotIn(lines[far - 1], piece["seen"], "창 밖 근거 줄이 판정기가 본 줄로 잡혔습니다")

    def test_a_short_document_has_nothing_outside_the_window(self) -> None:
        lines = far_doc()[:10]
        self.assertNotIn(judge.SUPPORT_NOTE.strip()[:20], judge.parts_for(lines, {3}, "fixed", Path("d.md"))[0]["document"])

    def test_unrelated_lines_are_not_sent(self) -> None:
        lines = far_doc()[:-1] + ["", "- Release notes are kept in English."]
        self.assertEqual([], judge.support_lines(lines, [3], set(range(1, 24))))


if __name__ == "__main__":
    unittest.main()
