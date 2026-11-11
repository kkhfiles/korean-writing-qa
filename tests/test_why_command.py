"""「왜 고쳤나」 명령(`judge_layer2.py --why`)이 판정 기록에서 줄마다 이유와 처리를 맞게 보이는지 본다 — 모델은 안 부른다.

(2026-11-11 사용자 「이유 표시하는건 기본으로 넣지 않아도 AI한테 요청하면 해줄텐데 구현으로 만들지 말고 명령으로
두는건 쉽지 않나?」) 판정 기록의 줄 번호는 그 회차 판의 번호라, 지금 글에서 줄을 다시 찾아야 한다.
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
from test_judge_layer2 import FakeBackend  # noqa: E402

DOC = ["# 주간 보고", "", "- 실패 원인은 담당자에 의해 분석됨", "- 빌드 에러 3건 발생", "- 회귀 시험이 매일 밤 돌고 있음",
       "- 진척률 72%"]
FINDINGS = [
    {"line": 3, "phrase": "담당자에 의해 분석됨", "category": "번역투 줄이기", "fix": "담당자가 분석함",
     "why": "「~에 의해」 피동", "decide": "fix"},
    {"line": 4, "phrase": "빌드 에러", "category": "불필요한 영어 줄이기", "fix": "빌드 오류", "why": "", "decide": "fix"},
    {"line": 5, "phrase": "돌고 있음", "category": "업무에서 쓰는 말로 쓰기", "fix": "실행함", "why": "입말", "decide": "fix"},
    {"line": 6, "phrase": "진척률 72%", "category": "고치다 뜻이 바뀐 곳", "fix": "진척률 72%", "why": "",
     "decide": "fix", "check": "72%가 맞는지"},
]


class WhyTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS
        judge.LOG, coverage.ANSWERS = d / "calls.jsonl", d / "answers.jsonl"
        coverage.DISMISSALS, coverage.DECISIONS = d / "dismissals.jsonl", d / "decisions.jsonl"
        self.doc = d / "d.md"
        self.doc.write_text("\n".join(DOC) + "\n", encoding="utf-8")
        judge.judge(self.doc, "opus", 10, FakeBackend(FINDINGS).pair())
        # 세션이 고침 — 3행은 제안대로, 4행은 안 고침, 5행은 제안과 다르게, 줄 하나를 앞에 넣어 번호가 밀림
        edited = ["# 주간 보고", "", "- 보고 기간: 11월 첫째 주", "- 실패 원인은 담당자가 분석함", "- 빌드 에러 3건 발생",
                  "- 회귀 시험을 매일 밤 수행함", "- 진척률 72%"]
        self.doc.write_text("\n".join(edited) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = self.saved
        self.tmp.cleanup()

    def test_each_finding_lands_on_its_line_now(self) -> None:
        got = {e["phrase"]: (e["line"], e["status"]) for e in judge.why_changed(self.doc)}
        self.assertEqual((4, "반영"), got["담당자에 의해 분석됨"])
        self.assertEqual((5, "안 고침"), got["빌드 에러"])
        self.assertEqual((6, "다르게 고침"), got["돌고 있음"])
        self.assertEqual(7, got["진척률 72%"][0])
        self.assertTrue(got["진척률 72%"][1].startswith("고칠 것 없음"), "원문과 같은 수정안을 반영으로 셌습니다")

    def test_one_line_only(self) -> None:
        got = judge.why_changed(self.doc, only=4)
        self.assertEqual(["담당자에 의해 분석됨"], [e["phrase"] for e in got])

    def test_the_command_prints_rule_and_reason(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main([str(self.doc), "--why", "--line", "4"])
        self.assertEqual(0, rc)
        self.assertIn("[번역투 줄이기] 「담당자에 의해 분석됨」 → 「담당자가 분석함」 · 반영 — 「~에 의해」 피동", out.getvalue())


if __name__ == "__main__":
    unittest.main()
