"""재현 도구(`scripts/bench_loop.py`)가 고리를 제대로 세는지 본다 — 모델은 안 부른다.

**왜 있나.** 효과를 같은 일감으로 재려고 만든 도구라, 세는 법이 틀리면 개선도 악화도 거짓이 된다
(2026-10-13 하루 동안 다른 일감끼리 견주어 「줄어듦」을 적었다가 실제로는 늘어 있었다).

**지키는 것**

- 0회차는 전체 판정, 그 뒤는 `--since main` 으로 판정 안 한 줄만 보낸다
- 판정기가 바로 앞 회차에 제 수정안으로 쓴 말을 다시 짚으면 「판정기 글 재지적」, 예전 글로 돌아가면 「되돌림」
- 사람 확인은 적용하지 않고, known 정책은 정상 줄을 고치지 않는다
- 판정 · 답 · 결정 · 처리 기록은 실행 폴더에만 쌓이고, 끝나면 원래 경로로 돌아간다
- 환산 비용 · 캐시 쓰기 · 읽기를 호출에서 모으고, 고리가 어떻게 끝났는지 적는다
- 회수를 2층 담당과 1층 담당으로 나누고, 1층이 잡은 줄과 합친 통합 회수를 센다
- 호출이 실패하면 완주하지 않은 실행으로 남고, 비교에서 빠진다
- 비교는 미리 적은 규칙대로 — 실행 수 부족 · 겹침은 판정 불가, 정확도가 떨어지면 낭비가 줄어도 개선이 아님,
  비용이 줄어도 시간이 늘면 악화, 다른 판의 실행(값 없음)과는 견주지 않음
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
# build_doc 이 만드는 줄 번호(머리말 세 줄 뒤)
F1, F2, C1 = 10, 11, 15


def fix(n: int, phrase: str, to: str, decide: str = "fix", check: str = "") -> dict:
    return {"line": n, "phrase": phrase, "fix": to, "decide": decide, "check": check,
            "category": "업무에서 쓰는 말로 쓰기", "why": "시험"}


ROUND0 = [fix(F1, "올립니다", "제출합니다"), fix(C1, "정합니다", "○○를 확정합니다", check="무엇을 확정하는지"),
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
                "usage": {"output_tokens": 100, "cache_creation_input_tokens": 50, "cache_read_input_tokens": 400},
                "cost_usd": 0.25}

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
        self.assertEqual(lines[:3], ["---", "form: prose", "---"], "형식 검사가 줄마다 걸려 1층 회수를 못 셉니다")
        self.assertEqual(lines[F1 - 1], "- 보고서는 매주 금요일에 올립니다.")   # 빈칸 둘은 하나로
        self.assertEqual([meta[n]["id"] for n in sorted(meta)], ["F-1", "F-2", "C-1"])
        self.assertEqual((meta[F1]["owner"], meta[C1]["kind"]), ("2층", "정상"))

    def test_checker_lines_are_read_from_its_output(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("\n".join(bench.HEAD + ["# 제목", "", "본문은 이렇습니다.", "", "우리 팀이 맡습니다."]) + "\n",
                         encoding="utf-8")
            errors, hits = bench.layer1(p)
        self.assertIsInstance(errors, int)
        self.assertIn(8, hits, "검사기가 짚은 줄(우리)을 못 읽었습니다")


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
        self.assertEqual(t["종료"], "수렴")
        self.assertEqual(got["rounds"][0]["사람 확인"], 1)
        self.assertIsInstance(t["걸린 시간"], int)
        self.assertTrue((self.dir / "run" / "summary.json").is_file())

    def test_cost_and_cache_are_summed_from_the_calls(self) -> None:
        t = self.run_loop(Scripted([ROUND0, ROUND1]))["total"]
        self.assertEqual((t["환산 비용"], t["캐시 쓰기"], t["캐시 읽기"]), (0.5, 100, 800))

    def test_recall_is_split_by_owner_and_joined_with_layer1(self) -> None:
        t = self.run_loop(Scripted([ROUND0, ROUND1]))["total"]
        self.assertEqual((t["0회차 회수(짚음)"], t["0회차 회수(2층)"], t["0회차 회수(규칙)"]), (2, 1, 1))
        self.assertEqual(t["0회차 정상 줄 지적"], 1)
        self.assertGreaterEqual(t["통합 회수(짚음)"], t["0회차 회수(짚음)"])

    def test_work_moved_to_the_session_is_counted(self) -> None:
        t = self.run_loop(Scripted([ROUND0, ROUND1]))["total"]
        self.assertEqual((t["자리표시"], t["사실 확인"]), (1, 1))

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
                 (coverage, "DISMISSALS"), (coverage, "INSTRUCTIONS")]
        before = [getattr(m, n) for m, n in spots]
        self.run_loop(Scripted([ROUND0, ROUND1]))
        self.assertEqual([getattr(m, n) for m, n in spots], before)
        rows = (self.dir / "run" / "judge.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 2)

    def test_a_failed_call_leaves_an_unfinished_run(self) -> None:
        got = self.run_loop(Scripted([ROUND0, ROUND1], fail_at=2))
        self.assertFalse(got["total"]["완주"])
        self.assertEqual(got["total"]["종료"], "실패")
        self.assertEqual(len(got["rounds"]), 1)


class LimitWatchTests(unittest.TestCase):

    def test_usage_rates_are_picked_from_the_sdk_events(self) -> None:
        try:
            from llm_playbook.backends import claude_sdk
        except ImportError:
            self.skipTest("llm_playbook 없음")
        import asyncio
        from types import SimpleNamespace

        async def fake(*a, **kw):
            raw = {"unifiedWindows": {"five_hour": {"utilization": 0.11}, "seven_day": {"utilization": 0.86}}}
            yield SimpleNamespace(rate_limit_info=SimpleNamespace(raw=raw))
            yield SimpleNamespace()

        async def drain():
            return [m async for m in claude_sdk.query()]

        saved, claude_sdk.query = claude_sdk.query, fake
        try:
            seen = []
            with bench.watch_limits(seen):
                got = asyncio.run(drain())
            self.assertIs(claude_sdk.query, fake, "엿보기를 끝낸 뒤 원래 함수를 돌려놓지 않았습니다")
        finally:
            claude_sdk.query = saved
        self.assertEqual(len(got), 2, "엿보다가 메시지를 삼켰습니다")
        self.assertEqual(seen, [{"five_hour": 0.11, "seven_day": 0.86}])


EDITS = [{"edit_id": "I-1", "before": "배포 일정은 다음 주 화요일로 정했습니다.",
          "after": "배포 일정은 이번 주 금요일로 정했습니다.", "instruction": "배포를 이번 주 금요일로 당긴다"}]
I1 = 19      # 정상 문장 뒤 「지시로 고칠 문장」 절의 첫 줄


class SessionTests(_Base):

    def session(self, replies, mode="batch") -> tuple[dict, Scripted]:
        fake = Scripted(replies)
        got = bench.run_session(self.dir / "run", FLAGGED, CLEAN, EDITS, mode, max_calls=20, backend=fake.pair())
        return got, fake

    def test_each_kind_of_finding_is_handled_like_a_session(self) -> None:
        round1 = [{"line": I1, "phrase": "이번 주 금요일", "fix": "다음 주 화요일", "decide": "fix",
                   "category": "고치다 뜻이 바뀐 곳", "why": "기준 판과 다름", "check": "일정이 바뀌었는지"}]
        got, fake = self.session([ROUND0, round1, []])
        t = got["total"]
        self.assertEqual(t["종료"], "완료")
        self.assertEqual((t["사람 답"], t["사실 확인 닫기"], t["지시반영 닫기"], t["적용"]), (1, 1, 1, 1))
        doc = (self.dir / "run" / "bench.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(doc[F2 - 1], "- 회의록은 당일 중에 공유합니다.", "사람 확인 답(고침)을 반영하지 않았습니다")
        self.assertEqual(doc[C1 - 1], "- 배포 일정은 다음 주에 정합니다.", "사실 확인 지적의 수정안을 확인 없이 넣었습니다")
        self.assertEqual(doc[I1 - 1], "- 배포 일정은 이번 주 금요일로 정했습니다.", "지시 편집이 안 들어갔거나 되돌려졌습니다")
        # 답대로 고친 줄은 다시 판정하지 않는다 — 1회차 대상은 고친 줄과 지시 편집 줄뿐
        self.assertIn(f"{F1}, {I1}", fake.calls[1]["user"])
        self.assertNotIn(f"{F2},", fake.calls[1]["user"])

    def test_one_at_a_time_makes_small_rejudges(self) -> None:
        two = [fix(F1, "올립니다", "제출합니다"), fix(C1, "정합니다", "확정합니다")]
        batch, _ = self.session([two, [], []], mode="batch")
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        one, _ = self.session([two, [], [], []], mode="one")
        self.assertGreater(one["total"]["호출"], batch["total"]["호출"],
                           "하나씩 처리했는데 재판정 호출이 늘지 않았습니다")
        self.assertGreaterEqual(one["total"]["대상 3줄 이하 재판정"], 1)

    def test_the_context_option_reaches_the_rejudge(self) -> None:
        fake = Scripted([ROUND0, [], []])
        got = bench.run_session(self.dir / "run", FLAGGED, CLEAN, EDITS, "batch", max_calls=20,
                                backend=fake.pair(), context="block")
        self.assertNotIn("줄 생략)…", fake.calls[0]["user"], "첫 전체 판정까지 창으로 보냈습니다")
        self.assertIn("줄 생략)…", fake.calls[1]["user"])
        self.assertEqual("block", got["total"]["문맥"])

    def test_the_call_budget_stops_the_loop(self) -> None:
        endless = [[fix(F1, "올립니다", "제출합니다")]] + [[fix(F1, w, w + "다")] for w in ("제출합니", "제출합니다")]
        fake = Scripted(endless * 5)
        got = bench.run_session(self.dir / "run", FLAGGED, CLEAN, EDITS, "batch", max_calls=2, backend=fake.pair())
        self.assertEqual(got["total"]["종료"], "호출 상한")
        self.assertLessEqual(len(fake.calls), 2)

    def test_work_left_open_is_not_reported_as_done(self) -> None:
        from unittest import mock
        with mock.patch.object(bench, "process", return_value=0):
            fake = Scripted([ROUND0])
            got = bench.run_session(self.dir / "run", FLAGGED, CLEAN, [], "batch", max_calls=5, backend=fake.pair())
        self.assertEqual(got["total"]["종료"], "멈춤", "열린 지적이 남았는데 완료로 적었습니다")

    def test_a_fix_back_to_an_earlier_version_is_closed_not_applied(self) -> None:
        """(2026-10-19) 하나씩 처리에서 한 줄이 두 판을 오가며 판정기 호출 없이 539회차까지 갔다."""
        got, fake = self.session([[fix(F1, "올립니다", "제출합니다")], [fix(F1, "제출합니다", "올립니다")], [], []],
                                 mode="one")
        t = got["total"]
        # 판정기가 0회차 지적을 되살린다고 표시하면(2026-10-20) 그 길로 먼저 닫힌다 — 어느 쪽이든 넣지 않는다
        self.assertEqual(1, t["되돌림 닫기"] + t["되살림 닫기"], "앞선 판으로 되돌리는 수정안을 넣었습니다")
        self.assertEqual(1, t["되살림 닫기"], "지적됐던 표현을 되살리는 수정안을 판정기가 못 알아봤습니다")
        self.assertIn(t["종료"], ("완료", "멈춤"))
        self.assertLess(len(got["rounds"]), 10, "고리가 끝나지 않았습니다")
        doc = (self.dir / "run" / "bench.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(doc[F1 - 1], "- 보고서는 매주 금요일에 제출합니다.")

    def test_reclosing_the_same_finding_is_counted(self) -> None:
        log = self.dir / "d.jsonl"
        rows = [{"phrase": "p", "reason": "확인함", "line_key": k} for k in ("a", "b", "b", "c")]
        log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(bench.reclosed(log), 2)


class ApplyFixTests(unittest.TestCase):

    def test_a_fix_that_repeats_the_surrounding_words_replaces_them(self) -> None:
        line = "- 시나리오 1종이 엔진 실행 파일로 끝까지 실행됨"
        got = bench.apply_fix(line, "엔진 실행 파일로 끝까지 실행", "시나리오 1종이 엔진 실행 파일에서 끝까지 실행됨")
        self.assertEqual("- 시나리오 1종이 엔진 실행 파일에서 끝까지 실행됨", got)

    def test_a_plain_fix_replaces_only_the_phrase(self) -> None:
        self.assertEqual("- 보고서는 매주 금요일에 제출합니다.",
                         bench.apply_fix("- 보고서는 매주 금요일에 올립니다.", "올립니다", "제출합니다"))


class EndStateTests(unittest.TestCase):

    def test_states(self) -> None:
        self.assertEqual(bench.end_state(True, [{"지적": 0}], 6), "수렴")
        self.assertEqual(bench.end_state(True, [{"지적": 3, "적용": 0, "사람 확인": 3}], 6), "사람 이관")
        self.assertEqual(bench.end_state(True, [{"지적": 2, "적용": 1, "사람 확인": 0}] * 7, 6), "회차 상한")
        self.assertEqual(bench.end_state(True, [{"지적": 2, "적용": 0, "사람 확인": 1}], 6), "적용할 것 없음")
        self.assertEqual(bench.end_state(False, [], 6), "실패")


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


def total(cost: float, secs: int = 500, recall: int = 73, joined: int = 140, errors: int = 0,
          done: bool = True) -> dict:
    t = {"완주": done, "종료": "수렴", "환산 비용": cost, "걸린 시간": secs, "0회차 회수(2층)": recall,
         "통합 회수(짚음)": joined, "1층 오류(끝)": errors}
    for k in bench.PREREGISTERED["report"]:
        t.setdefault(k, 1)
    return t


class CompareTests(unittest.TestCase):

    BASE = [total(1.6), total(1.7), total(2.3)]

    def test_lower_cost_without_slower_time_is_an_improvement(self) -> None:
        got = bench.compare(self.BASE, [total(1.0), total(1.2), total(1.4)])
        self.assertEqual(got["결론"], "개선")
        self.assertEqual(got["정확도"], "유지")

    def test_overlap_cannot_be_judged(self) -> None:
        self.assertEqual(bench.compare(self.BASE, [total(1.0), total(1.8), total(1.4)])["결론"], "판정 불가")

    def test_lower_cost_but_slower_is_worse(self) -> None:
        got = bench.compare(self.BASE, [total(1.0, secs=900), total(1.1, secs=950), total(1.2, secs=990)])
        self.assertEqual(got["결론"], "악화", "비용만 보고 시간이 늘어난 것을 놓쳤습니다")

    def test_lost_layer2_recall_beats_saved_cost(self) -> None:
        got = bench.compare(self.BASE, [total(1.0), total(1.0, recall=70), total(1.0)])
        self.assertEqual(got["결론"], "정확도 악화")

    def test_recall_within_the_tolerance_holds(self) -> None:
        self.assertEqual(bench.compare(self.BASE, [total(1.0), total(1.0, recall=71), total(1.0)])["결론"], "개선")

    def test_lost_joined_recall_beats_saved_cost(self) -> None:
        got = bench.compare(self.BASE, [total(1.0), total(1.0, joined=138), total(1.0)])
        self.assertEqual(got["결론"], "정확도 악화")

    def test_new_layer1_errors_beat_saved_cost(self) -> None:
        got = bench.compare(self.BASE, [total(1.0), total(1.0, errors=3), total(1.0)])
        self.assertEqual(got["결론"], "정확도 악화")

    def test_too_few_finished_runs_cannot_be_judged(self) -> None:
        cand = [total(1.0), total(1.0), total(1.0, done=False)]
        self.assertEqual(bench.compare(self.BASE, cand)["결론"], "판정 불가")

    def test_runs_from_the_first_version_are_not_compared(self) -> None:
        old = [{"완주": True, "출력 토큰": 56012, "0회차 회수(2층)": 73}] * 3
        got = bench.compare(old, [total(1.0)] * 3)
        self.assertEqual(got["결론"], "판정 불가")

    def test_more_runs_than_registered_is_exploratory(self) -> None:
        self.assertIn("탐색적", bench.compare(self.BASE, [total(1.0)] * 4))


if __name__ == "__main__":
    unittest.main()
