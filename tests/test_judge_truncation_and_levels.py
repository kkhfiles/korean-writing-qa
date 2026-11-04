"""2층 판정기 — 잘린 답 다시 나누기와 검사 단계 설정(2026-11-04).

- **잘린 답** — 출력 한도에 닿아 끊긴 답은 지적 0건으로 읽혔고, 그 줄들이 「판정기가 본 줄」로 남아 다시
  판정되지 않았다. 묶음을 반으로 나눠 다시 부르고, 못 나누면 실패로 알린다
- **검사 단계** — 최소 · 가성비 · 최대가 첫 판정과 재판정의 모델, 모아서 판정, 문서 비용 한도를 정한다
  (근거 측정은 runs/judge-effort-levels-20261104)
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402

coverage.DECISIONS = Path(tempfile.mkdtemp()) / "decisions.jsonl"
LINES = [f"{i}번째 줄에서 원인을 알 수 없었습니다." for i in range(1, 41)]


class Backend:
    """`cut` 번째까지의 호출은 출력 한도에서 끊긴 답을 돌려준다."""

    def __init__(self, cut: int = 0, reply=None):
        self.calls, self.cut, self.reply = [], cut, reply or []

    def call(self, **kw):
        self.calls.append(kw)
        if len(self.calls) <= self.cut:
            return {"text": '[[3, "알 수", "업무', "model": "claude-opus-5-5", "stop_reason": "max_tokens",
                    "usage": {"input_tokens": 2, "output_tokens": 16000}, "cost_usd": 0.4}
        return {"text": json.dumps(self.reply, ensure_ascii=False), "model": "claude-opus-5-5",
                "usage": {"input_tokens": 2, "output_tokens": 200}, "cost_usd": 0.05}

    @staticmethod
    def parse(text):
        """실제 파서처럼 끊긴 JSON 이면 None."""
        try:
            return json.loads(text)
        except ValueError:
            return None

    def pair(self):
        return self.call, self.parse


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG
        judge.LOG = self.dir / "calls.jsonl"
        self.env = {k: os.environ.pop(k) for k in (judge.LEVEL_ENV, judge.THINKING_ENV, "KOREAN_QA_PUBLISH_REPOS")
                    if k in os.environ}
        os.environ["KOREAN_QA_PUBLISH_REPOS"] = str(self.dir / "no-personal-list.toml")

    def tearDown(self) -> None:
        judge.LOG = self.saved
        for k in (judge.LEVEL_ENV, judge.THINKING_ENV, "KOREAN_QA_PUBLISH_REPOS"):
            os.environ.pop(k, None)
        os.environ.update(self.env)
        self.tmp.cleanup()

    def doc(self, lines=LINES) -> Path:
        p = self.dir / "d.md"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def run_main(self, argv, backend) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main(argv, backend=backend.pair())
        return rc, out.getvalue()

    def rows(self) -> list[dict]:
        return [json.loads(l) for l in judge.LOG.read_text(encoding="utf-8").splitlines()]


class TruncationTests(Base):
    def test_a_cut_answer_is_split_and_judged_again(self) -> None:
        b = Backend(cut=1)
        rc, out = self.run_main([str(self.doc())], b)
        self.assertEqual(0, rc, out)
        self.assertEqual(3, len(b.calls), "잘린 묶음을 반으로 나눠 다시 부르지 않았습니다")
        rows = self.rows()
        self.assertFalse(rows[0]["ok"], "잘린 호출이 성공으로 기록돼 그 줄이 판정된 것으로 잡힙니다")
        self.assertTrue(rows[0].get("truncated"))
        self.assertEqual(["1-20", "21-40"], [r["lines"] for r in rows[1:]])
        seen = coverage.judged(coverage.doc_key(self.doc()), judge.LOG)
        self.assertEqual(len({coverage.line_key(l) for l in LINES}), len(seen))

    def test_a_short_cut_answer_fails_loudly(self) -> None:
        b = Backend(cut=1)
        rc, out = self.run_main([str(self.doc(LINES[:5]))], b)
        self.assertEqual(4, rc, "더 못 나누는 잘린 답을 조용히 넘겼습니다")
        self.assertEqual(set(), coverage.judged(coverage.doc_key(self.doc(LINES[:5])), judge.LOG),
                         "잘린 줄이 판정된 것으로 남았습니다")


class LevelTests(Base):
    def test_balanced_rejudges_with_the_cheaper_model(self) -> None:
        b = Backend()
        rc, _ = self.run_main([str(self.doc(LINES[:5])), "--level", "가성비"], b)
        self.assertEqual(0, rc)
        first = b.calls[-1]
        self.doc(LINES[:5] + ["새로 쓴 줄에서 원인을 알 수 없었습니다."])
        rc, out = self.run_main([str(self.dir / "d.md"), "--level", "balanced", "--since"], b)
        self.assertEqual(0, rc, out)
        self.assertEqual(judge.LEVELS["balanced"]["first"], (first["model"], first.get("effort")))
        self.assertEqual(judge.LEVELS["balanced"]["rejudge"], (b.calls[-1]["model"], b.calls[-1].get("effort")))
        self.assertNotIn(judge.THINKING_ENV, os.environ, "단계가 넣은 사고 깊이가 다음 호출로 새어 나갑니다")

    def test_an_explicit_model_wins_over_the_level(self) -> None:
        b = Backend()
        self.run_main([str(self.doc(LINES[:5])), "--level", "min", "--model", "opus"], b)
        self.assertEqual("opus", b.calls[-1]["model"])

    def test_batching_holds_a_rejudge_while_other_fixes_are_open(self) -> None:
        reply = [{"line": 2, "phrase": "알 수", "category": "업무에서 쓰는 말로 쓰기", "fix": "파악할 수"}]
        rc, _ = self.run_main([str(self.doc(LINES[:5])), "--level", "max"], Backend(reply=reply))
        self.assertEqual(0, rc)
        self.doc(LINES[:5] + ["새로 쓴 줄에서 원인을 알 수 없었습니다."])
        b = Backend()
        rc, out = self.run_main([str(self.dir / "d.md"), "--level", "balanced", "--since"], b)
        self.assertEqual(6, rc, out)
        self.assertEqual([], b.calls, "남은 지적이 있는데 재판정을 불렀습니다")
        rc, out = self.run_main([str(self.dir / "d.md"), "--level", "balanced", "--since", "--now"], b)
        self.assertEqual(0, rc, out)
        self.assertEqual(1, len(b.calls))

    def test_max_only_warns_about_open_fixes(self) -> None:
        reply = [{"line": 2, "phrase": "알 수", "category": "업무에서 쓰는 말로 쓰기", "fix": "파악할 수"}]
        self.run_main([str(self.doc(LINES[:5])), "--level", "max"], Backend(reply=reply))
        self.doc(LINES[:5] + ["새로 쓴 줄에서 원인을 알 수 없었습니다."])
        b = Backend()
        rc, _ = self.run_main([str(self.dir / "d.md"), "--level", "max", "--since"], b)
        self.assertEqual(0, rc)
        self.assertEqual(1, len(b.calls))

    def test_the_budget_stops_and_needs_an_approval_to_go_on(self) -> None:
        p = self.doc(LINES[:5])
        spent = {"at": "x", "when": time.time() - 60, "key": coverage.doc_key(p), "ok": True,
                 "cost_usd": 1.0, "seen": []}
        judge.LOG.write_text(json.dumps(spent) + "\n", encoding="utf-8")
        b = Backend()
        rc, out = self.run_main([str(p), "--level", "balanced"], b)
        self.assertEqual(5, rc, out)
        self.assertIn("검사 미완료", out)
        self.assertEqual([], b.calls)
        rc, _ = self.run_main([str(p), "--level", "balanced", "--over-budget"], b)
        self.assertEqual(2, rc, "승인 원문 없이 한도를 넘겼습니다")
        rc, _ = self.run_main([str(p), "--level", "balanced", "--over-budget", "--note", "사용자 「이번만 넘겨」"], b)
        self.assertEqual(0, rc)
        self.assertEqual("사용자 「이번만 넘겨」", self.rows()[-1].get("over_budget"))

    def test_old_work_does_not_count_toward_the_budget(self) -> None:
        p = self.doc(LINES[:5])
        old = {"at": "x", "when": time.time() - judge.WORK_GAP_S - 60, "key": coverage.doc_key(p), "ok": True,
               "cost_usd": 5.0, "seen": []}
        judge.LOG.write_text(json.dumps(old) + "\n", encoding="utf-8")
        rc, _ = self.run_main([str(p), "--level", "balanced"], Backend())
        self.assertEqual(0, rc)

    def test_where_the_level_comes_from(self) -> None:
        self.assertEqual(judge.DEFAULT_LEVEL, judge.resolve_level(None))
        (self.dir / "no-personal-list.toml").write_text('check_level = "최소"\n', encoding="utf-8")
        self.assertEqual("min", judge.resolve_level(None))
        os.environ[judge.LEVEL_ENV] = "balanced"
        self.assertEqual("balanced", judge.resolve_level(None))
        self.assertEqual("max", judge.resolve_level("최대"))
        with self.assertRaises(ValueError):
            judge.resolve_level("fast")


if __name__ == "__main__":
    unittest.main()
