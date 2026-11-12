"""판정기가 제안한 문서 안 링크를 문서 제목에 맞추는지 본다 — 모델은 안 부른다.

(2026-11-12 다른 세션 인계 B5) 판정기가 「## 5. 남은 일과 다음 계획」에 `#남은-일과-다음-계획` 을 제안해 번호가
빠졌다. 그대로 넣으면 링크가 깨진다.

**지키는 것**

- 제목의 링크 이름은 GitHub 방식(소문자, 문장 부호 지움, 빈칸은 하이픈)
- 번호만 빠진 이름은 그 제목으로 고치고 알림을 남김 · 맞는 이름은 그대로 · 없는 제목이면 알림만
- 판정 기록에도 고친 이름이 남음 — 검토 화면과 답 처리가 기록의 수정안을 넣음
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
from test_judge_layer2 import FakeBackend  # noqa: E402

LINES = ["---", "form: structured", "---", "# 의견서", "", "**의견서** — 발표 준비", "",
         "## 1. 발표 흐름", "", "- 남은 일은 아래에 정리함", "", "## 5. 남은 일과 다음 계획", "", "- 남은 일 정리"]


class SlugTests(unittest.TestCase):

    def test_heading_slug(self) -> None:
        self.assertEqual("5-남은-일과-다음-계획", judge.heading_slug(" 5. 남은 일과 다음 계획"))
        self.assertEqual("검사-범위와-한계", judge.heading_slug("검사 범위와 한계"))

    def test_a_missing_number_is_restored(self) -> None:
        fix, notes = judge.fit_anchors("[남은 일과 다음 계획](#남은-일과-다음-계획)에 정리함", LINES)
        self.assertIn("(#5-남은-일과-다음-계획)", fix)
        self.assertEqual(1, len(notes))

    def test_a_right_anchor_is_left_alone(self) -> None:
        fix, notes = judge.fit_anchors("[흐름](#1-발표-흐름) 참고", LINES)
        self.assertEqual("[흐름](#1-발표-흐름) 참고", fix)
        self.assertEqual([], notes)

    def test_an_unknown_anchor_is_reported(self) -> None:
        fix, notes = judge.fit_anchors("[부록](#부록) 참고", LINES)
        self.assertEqual("[부록](#부록) 참고", fix)
        self.assertIn("없음", notes[0])


class JudgeRecordTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = (
            self.dir / f for f in ("a.jsonl", "x.jsonl", "d.jsonl"))
        self.doc = self.dir / "advice.md"
        self.doc.write_text("\n".join(LINES) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = self.saved
        self.tmp.cleanup()

    def test_the_logged_fix_carries_the_fitted_anchor(self) -> None:
        reply = [{"line": 10, "phrase": "아래에 정리함", "category": "참조는 링크로 걸기",
                  "fix": "[남은 일과 다음 계획](#남은-일과-다음-계획)에 정리함", "why": "가리키는 절에 링크", "decide": "fix"}]
        result = judge.judge(self.doc, "opus", 10, FakeBackend(reply).pair())
        found = result["findings"][0]
        self.assertIn("(#5-남은-일과-다음-계획)", found["fix"])
        self.assertTrue(any("제목에 맞춤" in n for n in found["fix_notes"]))
        row = json.loads(judge.LOG.read_text(encoding="utf-8").splitlines()[-1])
        self.assertIn("(#5-남은-일과-다음-계획)", row["fixes"][0]["fix"])


if __name__ == "__main__":
    unittest.main()
