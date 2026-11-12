"""글 단위 일관성 질문(`consistency_pass`)이 지적을 판정 기록에 맞게 남기는지 본다 — 모델은 안 부른다.

(2026-11-12 3단계) 다른 줄을 대조해야 보이는 어긋남(개수 예고와 목록 수, 같은 대상의 다른 이름, 단정과 예외)을 줄마다
내는 판정이 못 짚어, 글 전체를 한 번 더 주고 그것만 묻는다.

**지키는 것**

- 고친 말이 있으면 고칠 지적(확인할 사실에 대조한 줄), 없으면 사람 확인
- 인용이 그 줄에 없거나 줄 번호가 틀린 답, 줄마다 낸 판정과 같은 지적은 버림
- 재판정이면 이번에 고친 줄이 낀 어긋남만 남김
- 이 호출은 줄을 「판정함」으로 남기지 않음
- 인용에 탭 글자가 든 답도 읽음
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402

LINES = ["---", "form: structured", "---", "# 사용 안내", "", "**사용 안내** — 설치와 연결", "",
         "## 기록을 가져오는 세 가지 길", "", "- 말하기", "- 스크립트", "- 커넥터", "- 붙여넣기", "",
         "결과는 모두 내 PC에만 저장됩니다.", "", "일정 연동을 켜면 할일이 그룹웨어 캘린더에 공개로 저장됩니다."]


class TwoCalls:
    """첫 호출(줄마다 판정)과 둘째 호출(일관성 질문)에 다른 답을 준다."""

    def __init__(self, line_reply, whole_reply):
        self.replies = [line_reply, whole_reply]
        self.calls = []

    def call(self, **kw):
        self.calls.append(kw)
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return {"text": text, "model": "claude-opus-5-5", "usage": {"output_tokens": 10}, "cost_usd": 0.01}

    def pair(self):
        return self.call, json.loads


WHOLE = [{"line": 8, "phrase": "세 가지", "other": 10, "other_phrase": "말하기", "kind": "개수",
          "why": "아래 목록은 네 가지", "fix": "네 가지"},
         {"line": 15, "phrase": "내 PC에만 저장됩니다", "other": 17, "other_phrase": "그룹웨어 캘린더에 공개로 저장",
          "kind": "단정과 예외", "why": "일정 연동을 켜면 그룹웨어에도 저장", "fix": ""},
         {"line": 15, "phrase": "문서에 없는 말", "other": 17, "kind": "단정과 예외", "why": "인용 틀림", "fix": "x"},
         {"line": 99, "phrase": "세 가지", "other": 10, "kind": "개수", "why": "줄 번호 틀림", "fix": "x"}]


class ConsistencyTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = (
            self.dir / f for f in ("a.jsonl", "x.jsonl", "d.jsonl"))
        self.doc = self.dir / "guide.md"
        self.doc.write_text("\n".join(LINES) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = self.saved
        self.tmp.cleanup()

    def rows(self) -> list[dict]:
        return [json.loads(l) for l in judge.LOG.read_text(encoding="utf-8").splitlines()]

    def test_findings_are_recorded_as_fix_and_ask(self) -> None:
        fake = TwoCalls([], WHOLE)
        result = judge.judge(self.doc, "opus", 10, fake.pair(), consistency=True)
        self.assertEqual(2, len(fake.calls))
        mine = [f for f in result["findings"] if f["category"] == judge.CONSISTENCY_CATEGORY]
        self.assertEqual([(8, "fix"), (15, "ask")], [(f["line"], f["decide"]) for f in mine])
        self.assertIn("10행", mine[0]["check"])
        row = self.rows()[-1]
        self.assertEqual("consistency", row["context"])
        self.assertEqual([], row["seen"], "이 호출이 줄을 판정함으로 남기면 안 됨")
        self.assertEqual(["세 가지"], [f["phrase"] for f in row["fixes"]])
        self.assertEqual(["내 PC에만 저장됩니다"], [a["phrase"] for a in row["asks"]])
        opened = coverage.open_fixes(coverage.doc_key(self.doc), LINES, judge.LOG)
        self.assertIn((8, "세 가지"), [(n, fx["phrase"]) for n, fx in opened])

    def test_off_by_default_and_duplicates_dropped(self) -> None:
        fake = TwoCalls([], WHOLE)
        judge.judge(self.doc, "opus", 10, fake.pair())
        self.assertEqual(1, len(fake.calls), "기본은 끔 — 명령줄(main)만 켬")
        line = [{"line": 8, "phrase": "세 가지", "category": "소리 내어 읽기", "fix": "네 가지", "why": "", "decide": "fix"}]
        result = judge.judge(self.doc, "opus", 10, TwoCalls(line, WHOLE).pair(), consistency=True)
        self.assertEqual(1, sum(f["line"] == 8 for f in result["findings"]), "같은 줄 같은 표현은 한 번")

    def test_rejudge_keeps_only_findings_touching_edited_lines(self) -> None:
        judge.judge(self.doc, "opus", 10, TwoCalls([], []).pair())
        fake = TwoCalls([], WHOLE)
        result = judge.judge(self.doc, "opus", 10, fake.pair(), targets=[17], consistency=True)
        mine = [f for f in result["findings"] if f["category"] == judge.CONSISTENCY_CATEGORY]
        self.assertEqual([15], [f["line"] for f in mine], "17행이 낀 어긋남만")

    def test_a_tab_inside_a_quote_is_read(self) -> None:
        raw = '[{"line": 8, "phrase": "세 가지", "other": 10, "other_phrase": "말하기\t스크립트", "kind": "개수", "why": "네 가지", "fix": "네 가지"}]'
        result = judge.judge(self.doc, "opus", 10, TwoCalls([], raw).pair(), consistency=True)
        self.assertTrue(any(f["category"] == judge.CONSISTENCY_CATEGORY for f in result["findings"]))


if __name__ == "__main__":
    unittest.main()
