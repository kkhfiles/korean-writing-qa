"""재생 도구(`scripts/replay_rejudge.py`)가 저장된 재판정 입력을 방식마다 같은 입력으로 부르는지 본다 — 모델은 안 부른다.

**지키는 것**

- 판정기가 남긴 입력을 그대로 읽어, 판정 때와 같은 사용자 메시지를 만든다
- 창 방식의 「문맥 부족」은 그 줄만 chunk 로 다시 부르고 지적으로 세지 않는다
- 재생은 판정 기록을 갱신하지 않는다
- 비교 표는 방식 이름을 가리고, 대응은 따로 남긴다 · 일치율을 같은 방식 반복과 방식 사이로 나눠 낸다
"""
from __future__ import annotations

import json
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
from test_rejudge_context import Scripted, doc_lines  # noqa: E402


class ReplayTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = (self.dir / f for f in ("a", "d", "x"))
        self.doc = self.dir / "d.md"
        self.lines = doc_lines()
        self.doc.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        self.live = Scripted([[]])
        judge.judge(self.doc, "opus", 10, self.live.pair(), [5], self.lines)
        self.cases = replay.load_cases(self.dir / "korean-replay")
        self.log_before = judge.LOG.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = self.saved
        self.tmp.cleanup()

    def test_the_replayed_prompt_matches_the_live_one(self) -> None:
        fake = Scripted([[]])
        replay.replay(self.cases[0], self.cases[0]["context"], fake.pair(), "opus")   # 판정 때 방식 그대로
        self.assertEqual(self.live.calls[0]["user"], fake.calls[0]["user"])
        self.assertEqual(self.live.calls[0]["system"], fake.calls[0]["system"])

    def test_context_short_reruns_in_chunk_and_is_not_a_finding(self) -> None:
        short = {"line": 5, "phrase": "배포는", "category": judge.CONTEXT_SHORT, "fix": "", "decide": "fix"}
        real = {"line": 5, "phrase": "매주", "category": "업무에서 쓰는 말로 쓰기", "fix": "주마다", "decide": "fix"}
        got = replay.replay(self.cases[0], "block", Scripted([[short], [real]]).pair(), "opus")
        self.assertEqual((2, [5]), (got["calls"], got["short"]))
        self.assertEqual(["매주"], [f["phrase"] for f in got["findings"]])
        self.assertEqual(["block", "chunk←문맥 부족"], got["modes"])

    def test_bare_drops_the_reason_for_the_base_line(self) -> None:
        case = json.loads(json.dumps(self.cases[0]))
        case["info"] = {int(k): v for k, v in case["info"].items()}
        case["info"][5]["root"] = "배포는 매주 진행합니다."      # 고친 줄로 꾸민다 — 기준 판이 있어야 까닭이 실린다
        case["info"][5]["root_found"] = [{"phrase": "매주", "fix": "주마다", "category": "업무에서 쓰는 말로 쓰기"}]
        with_reason, bare = Scripted([[]]), Scripted([[]])
        replay.replay(case, "chunk", with_reason.pair(), "opus")
        replay.run("t", [case], ["chunk@bare"], 1, bare.pair(), "opus", self.dir / "runs")
        self.assertIn("고친 까닭: 「매주」→「주마다」", with_reason.calls[0]["user"])
        self.assertNotIn("고친 까닭", bare.calls[0]["user"])
        row = json.loads((self.dir / "runs" / "t" / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual("chunk@bare", row["mode"], "결과에서 두 조건을 못 가릅니다")

    def test_replay_leaves_the_judge_log_alone(self) -> None:
        replay.run("t", self.cases, ["chunk", "block"], 1, Scripted([[]] * 4).pair(), "opus", self.dir / "runs")
        self.assertEqual(self.log_before, judge.LOG.read_text(encoding="utf-8"))

    def test_the_sheet_hides_modes_and_the_summary_splits_noise(self) -> None:
        f = {"line": 5, "phrase": "매주", "category": "업무에서 쓰는 말로 쓰기", "fix": "주마다", "decide": "fix"}
        out = self.dir / "runs"
        res = replay.run("t", self.cases, ["chunk", "block"], 2, Scripted([[f], [], [], [f]]).pair(), "opus", out)
        rows = [json.loads(l) for l in res.read_text(encoding="utf-8").splitlines()]
        summary = replay.summarize(rows)
        self.assertEqual({"chunk", "block"}, set(summary["방식별"]))
        self.assertIn("block", summary["chunk 와의 일치"])
        self.assertIsNotNone(summary["같은 방식 반복 일치"])
        text = replay.sheet(rows, out / "t").read_text(encoding="utf-8")
        self.assertNotIn("chunk", text)
        self.assertNotIn("block", text)
        key = json.loads((out / "t" / "key.json").read_text(encoding="utf-8"))
        self.assertEqual({"chunk", "block"}, set(next(iter(key.values())).values()))


if __name__ == "__main__":
    unittest.main()
