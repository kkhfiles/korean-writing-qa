"""재현 도구(`scripts/bench_loop.py`)가 고리를 제대로 세는지 본다 — 모델은 안 부른다.

**왜 있나.** 효과를 같은 일감으로 재려고 만든 도구라, 세는 법이 틀리면 개선도 악화도 거짓이 된다
(2026-10-13 하루 동안 다른 일감끼리 견주어 「줄어듦」을 적었다가 실제로는 늘어 있었다).

**지키는 것**

- 0회차는 전체 판정, 그 뒤는 `--since main` 으로 판정 안 한 줄만 보낸다
- 판정기가 바로 앞 회차에 제 수정안으로 쓴 말을 다시 짚으면 「판정기 글 재지적」, 예전 글로 돌아가면 「되돌림」
- 사람 확인은 적용하지 않고, known 정책은 정상 줄을 고치지 않는다
- 판정 · 답 · 결정 · 처리 기록은 실행 폴더에만 쌓이고, 끝나면 원래 경로로 돌아간다
- 호출이 실패하면 완주하지 않은 실행으로 남고, 비교에서 빠진다
- 비교는 미리 적은 규칙대로 — 실행 수 부족 · 겹침은 판정 불가, 정확도가 떨어지면 낭비가 줄어도 개선이 아님
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bench_loop as bench  # noqa: E402
import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402

FLAGGED = [{"flag_id": "F-1", "sentence": "보고서는 매주  금요일에 올립니다.", "owner": "2층"},
           {"flag_id": "F-2", "sentence": "회의록은 당일에 공유합니다.", "owner": "규칙"}]
CLEAN = [{"case_id": "C-1", "text": "배포 일정은 다음 주에 정합니다."}]
# build_doc 이 만드는 줄 번호
F1, F2, C1 = 7, 8, 12


def fix(n: int, phrase: str, to: str, decide: str = "fix") -> dict:
    return {"line": n, "phrase": phrase, "fix": to, "decide": decide,
            "category": "업무에서 쓰는 말로 쓰기", "why": "시험"}


ROUND0 = [fix(F1, "올립니다", "제출합니다"), fix(C1, "정합니다", "확정합니다"),
          # 사람 확인은 적용할 수 있는 모양이어도 적용하지 않는다
          fix(F2, "당일에", "당일 중에", decide="ask")]
# 1회차 — 앞 회차에 쓴 「제출합니다」를 다시 짚고 원래 말로 되돌리게 한다
ROUND1 = [fix(F1, "제출합니다", "올립니다")]


class Scripted:
    """호출마다 정해 둔 답을 차례로 낸다."""

    def __init__(self, replies, fail_at=None):
        self.replies, self.fail_at, self.calls = list(replies), fail_at, []

    def call(self, **kw):
        self.calls.append(kw)
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise TimeoutError("시험용 실패")
        reply = self.replies.pop(0) if self.replies else []
        return {"text": json.dumps(reply, ensure_ascii=False), "model": "fake",
                "usage": {"output_tokens": 100}, "cost_usd": None}

    def pair(self):
        return self.call, json.loads


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_loop(self, fake: Scripted, policy: str = "all") -> dict:
        return bench.run_once(self.dir / "run", FLAGGED, CLEAN, policy, rounds=6, backend=fake.pair())


class DocTests(unittest.TestCase):

    def test_each_sample_is_one_line_in_a_fixed_order(self) -> None:
        lines, meta = bench.build_doc(FLAGGED, CLEAN)
        self.assertEqual(lines[F1 - 1], "- 보고서는 매주 금요일에 올립니다.")   # 빈칸 둘은 하나로
        self.assertEqual([meta[n]["id"] for n in sorted(meta)], ["F-1", "F-2", "C-1"])
        self.assertEqual((meta[F1]["owner"], meta[C1]["kind"]), ("2층", "정상"))


class LoopTests(_Base):

    def test_the_loop_counts_reflags_and_reverts(self) -> None:
        fake = Scripted([ROUND0, ROUND1])
        got = self.run_loop(fake)
        t = got["total"]
        self.assertTrue(t["완주"])
        self.assertEqual(len(fake.calls), 2)
        # 되돌린 줄은 이미 본 줄이라 2회차에 판정할 새 줄이 없다 — 호출 없이 끝난다
        self.assertEqual([r["호출"] for r in got["rounds"]], [1, 1, 0])
        self.assertEqual((t["회차"], t["호출"], t["출력 토큰"]), (2, 2, 200))
        self.assertEqual((t["판정기 글 재지적"], t["되돌림"]), (1, 1))
        self.assertEqual((t["0회차 회수(짚음)"], t["0회차 회수(2층)"], t["0회차 정상 줄 지적"]), (2, 1, 1))
        self.assertEqual(got["rounds"][0]["사람 확인"], 1)
        self.assertIsInstance(t["1층 오류(끝)"], int)
        self.assertTrue((self.dir / "run" / "summary.json").is_file())

    def test_only_unjudged_lines_are_sent_after_the_first_round(self) -> None:
        fake = Scripted([ROUND0, ROUND1])
        self.run_loop(fake)
        self.assertNotIn("이번에는 아래 줄만 점검한다", fake.calls[0]["user"])
        self.assertIn(f"이번에는 아래 줄만 점검한다 — 나머지 줄은 문맥으로만 읽고 지적하지 않는다.\n{F1}, {C1}",
                      fake.calls[1]["user"])

    def test_asks_are_not_applied_and_known_leaves_clean_lines(self) -> None:
        self.run_loop(Scripted([ROUND0, []]), policy="known")
        doc = (self.dir / "run" / "bench.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(doc[F1 - 1], "- 보고서는 매주 금요일에 제출합니다.")
        self.assertEqual(doc[F2 - 1], "- 회의록은 당일에 공유합니다.")
        self.assertEqual(doc[C1 - 1], "- 배포 일정은 다음 주에 정합니다.")

    def test_logs_stay_in_the_run_folder(self) -> None:
        spots = [(judge, "LOG"), (coverage, "LOG"), (coverage, "ANSWERS"), (coverage, "DECISIONS"),
                 (coverage, "DISMISSALS")]
        before = [getattr(m, n) for m, n in spots]
        self.run_loop(Scripted([ROUND0, ROUND1]))
        self.assertEqual([getattr(m, n) for m, n in spots], before)
        rows = (self.dir / "run" / "judge.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 2)

    def test_a_failed_call_leaves_an_unfinished_run(self) -> None:
        got = self.run_loop(Scripted([ROUND0, ROUND1], fail_at=2))
        self.assertFalse(got["total"]["완주"])
        self.assertEqual(len(got["rounds"]), 1)


class LockTests(_Base):

    def test_a_live_lock_stops_a_second_run(self) -> None:
        folder = self.dir / "name"
        folder.mkdir()
        (folder / "bench.lock").write_text(str(os.getpid()), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            with bench.locked(folder):
                pass

    def test_the_lock_is_removed_after_the_run(self) -> None:
        with bench.locked(self.dir / "name"):
            self.assertTrue((self.dir / "name" / "bench.lock").is_file())
        self.assertFalse((self.dir / "name" / "bench.lock").exists())


def total(tokens: int, recall: int = 73, errors: int = 0, done: bool = True, **more) -> dict:
    t = {"완주": done, "출력 토큰": tokens, "0회차 회수(2층)": recall, "0회차 회수(짚음)": 120,
         "1층 오류(끝)": errors}
    for k in bench.PREREGISTERED["waste"]:
        t.setdefault(k, more.get(k, 10))
    return t


class CompareTests(unittest.TestCase):

    BASE = [total(60000), total(64000), total(70000)]

    def test_all_candidates_below_the_baseline_is_an_improvement(self) -> None:
        got = bench.compare(self.BASE, [total(40000), total(45000), total(50000)])
        self.assertEqual(got["결론"], "개선")
        self.assertEqual(got["정확도"], "유지")

    def test_overlap_cannot_be_judged(self) -> None:
        got = bench.compare(self.BASE, [total(50000), total(62000), total(55000)])
        self.assertEqual(got["결론"], "판정 불가")

    def test_all_candidates_above_is_worse(self) -> None:
        self.assertEqual(bench.compare(self.BASE, [total(71000)] * 3)["결론"], "악화")

    def test_lost_recall_beats_saved_tokens(self) -> None:
        got = bench.compare(self.BASE, [total(40000), total(40000, recall=70), total(40000)])
        self.assertEqual(got["결론"], "정확도 악화")

    def test_recall_within_the_tolerance_holds(self) -> None:
        got = bench.compare(self.BASE, [total(40000), total(40000, recall=71), total(40000)])
        self.assertEqual(got["결론"], "개선")

    def test_new_layer1_errors_beat_saved_tokens(self) -> None:
        got = bench.compare(self.BASE, [total(40000), total(40000, errors=3), total(40000)])
        self.assertEqual(got["결론"], "정확도 악화")

    def test_too_few_finished_runs_cannot_be_judged(self) -> None:
        cand = [total(40000), total(40000), total(40000, done=False)]
        self.assertEqual(bench.compare(self.BASE, cand)["결론"], "판정 불가")

    def test_more_runs_than_registered_is_exploratory(self) -> None:
        got = bench.compare(self.BASE, [total(40000)] * 4)
        self.assertIn("탐색적", got)


if __name__ == "__main__":
    unittest.main()
