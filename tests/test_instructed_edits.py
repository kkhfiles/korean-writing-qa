"""사용자 지시로 뜻을 바꾼 줄을 기록하면(`--instructed`) 재판정이 그 지시를 함께 받는지 본다 — 모델은 안 부른다.

(2026-10-16) 사내 문서 1건에서 「고치다 뜻이 바뀐 곳」 닫기 46건 중 40건이 사용자 지시로 일부러 바꾼 것이었다.
판정기가 짚은 뒤 하나씩 「지시반영」으로 닫는 대신, 재판정 전에 지시를 알려 지시 안의 변경은 짚지 않게 한다.
지시 밖의 변경 · 확인이 필요한 새 주장 · 다른 규칙은 그대로 짚게 한다(외부 검토 — 지시는 편집 의도의 근거이지
사실의 근거가 아니다).

**지키는 것**

- 지시 원문을 「」로 옮겨야 받고, 한글이 없는 줄은 받지 않는다
- 기록한 줄(과 그 줄을 조금 더 고친 줄)의 재판정 프롬프트에 지시가 실린다 · 기록이 없으면 안 실린다
- 프롬프트는 지시 밖의 변경을 그대로 짚으라고 적는다
- 재판정 입력 저장 · 재생에도 지시가 따라간다
- 재현 도구는 지시 안 줄과 지시 밖 줄을 나눠 센다
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import bench_loop as bench  # noqa: E402
import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
import replay_rejudge as replay  # noqa: E402
from test_rejudge_context import Scripted  # noqa: E402

BASE = ["# 일정", "", "배포 일정은 다음 주 화요일로 정했습니다.", "", "Release notes are in English."]
EDITED = list(BASE)
EDITED[2] = "배포 일정은 이번 주 금요일로 정했습니다."
NOTE = "사용자 지시 「배포를 이번 주 금요일로 당긴다」(10/16 대화)"


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = (judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, coverage.INSTRUCTIONS)
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, coverage.INSTRUCTIONS = (
            self.dir / f for f in ("a", "d", "x", "i"))
        self.doc = self.dir / "d.md"
        self.doc.write_text("\n".join(EDITED) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, coverage.INSTRUCTIONS = self.saved
        self.tmp.cleanup()

    def rejudge(self) -> Scripted:
        fake = Scripted([[]])
        judge.judge(self.doc, "opus", 10, fake.pair(), [3], BASE)
        return fake


class InstructTests(_Base):

    def test_a_note_without_the_quoted_instruction_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge.instruct(self.doc, 3, "사용자가 금요일로 당기라고 했음")

    def test_a_line_without_korean_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge.instruct(self.doc, 5, NOTE)

    def test_the_cli_records_and_refuses(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, judge.main([str(self.doc), "--instructed", "3", "--note", NOTE]))
            self.assertEqual(2, judge.main([str(self.doc), "--instructed", "3", "--note", "인용 없는 지시 기록입니다"]))
        rows = coverage.INSTRUCTIONS.read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, len(rows))


class PromptTests(_Base):

    def test_the_instruction_reaches_the_rejudge(self) -> None:
        judge.instruct(self.doc, 3, NOTE)
        user = self.rejudge().calls[0]["user"]
        self.assertIn("3행 지시: " + NOTE, user)
        self.assertIn("지시가 말하지 않은 변경", user, "지시 밖 변경을 그대로 짚으라는 말이 없습니다")

    def test_no_record_no_instruction(self) -> None:
        self.assertNotIn("지시:", self.rejudge().calls[0]["user"])

    def test_the_instruction_follows_a_further_edit(self) -> None:
        judge.instruct(self.doc, 3, NOTE)
        again = list(EDITED)
        again[2] = "배포 일정은 이번 주 금요일 오전으로 정했습니다."
        self.doc.write_text("\n".join(again) + "\n", encoding="utf-8")
        self.assertIn("3행 지시:", self.rejudge().calls[0]["user"])

    def test_replay_carries_the_instruction(self) -> None:
        judge.instruct(self.doc, 3, NOTE)
        live = self.rejudge()
        case = replay.load_cases(self.dir / "korean-replay")[0]
        fake = Scripted([[]])
        replay.replay(case, "chunk", fake.pair(), "opus")
        self.assertEqual(live.calls[0]["user"], fake.calls[0]["user"])


class BenchTests(unittest.TestCase):

    def test_in_scope_and_out_of_scope_lines_are_counted_apart(self) -> None:
        edits = [{"edit_id": "I-1", "before": "배포 일정은 다음 주 화요일로 정했습니다.",
                  "after": "배포 일정은 이번 주 금요일로 정했습니다.", "instruction": "배포를 이번 주 금요일로 당긴다",
                  "scope": "in"},
                 {"edit_id": "I-7", "before": "보안 점검은 분기마다 외부 업체가 합니다.",
                  "after": "보안 점검은 매달 내부 팀이 합니다.", "instruction": "보안 점검 주기를 매달로 바꾼다",
                  "scope": "out"}]
        flagged = [{"flag_id": "F-1", "sentence": "보고서는 금요일에 올립니다.", "owner": "2층"}]
        lines, meta = bench.build_doc(flagged, [], edits)
        i1, i7 = [n for n, m in meta.items() if m["kind"] == "지시"]

        def moved(n, phrase, fix):
            return {"line": n, "phrase": phrase, "fix": fix, "decide": "fix", "category": "고치다 뜻이 바뀐 곳",
                    "why": "기준 판과 다름"}
        fake = Scripted([[], [moved(i1, "이번 주 금요일", "다음 주 화요일"), moved(i7, "내부 팀", "외부 업체")], []])
        real = coverage.INSTRUCTIONS
        before = real.read_bytes() if real.is_file() else None
        with tempfile.TemporaryDirectory() as d:
            got = bench.run_session(Path(d) / "run", flagged, [], edits, "batch", max_calls=10, backend=fake.pair(),
                                    instructions=True)
            self.assertTrue((Path(d) / "run" / "instructions.jsonl").is_file(), "지시 기록이 실행 폴더에 안 쌓였습니다")
        self.assertEqual(before, real.read_bytes() if real.is_file() else None,
                         "재현 도구가 실제 지시 기록에 썼습니다")
        t = got["total"]
        self.assertIn(f"{i1}행 지시:", fake.calls[1]["user"])
        self.assertEqual((t["지시 안 뜻 바뀜 짚은 줄"], t["지시 밖 짚은 줄"], t["지시 밖 시료"]), (1, 1, 1))
        self.assertEqual((t["지시반영 닫기"], t["지시 밖 짚음 처리"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
