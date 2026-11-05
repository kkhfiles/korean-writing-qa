"""고친 줄에 앞선 판정이 고치라고 한 표현이 그대로 있으면, 재판정 모델이 짚지 않아도 지적이 붙는지 본다 —
모델은 안 부른다.

(2026-11-04 측정) 가성비 단계(재판정 Sonnet)가 짚힌 표현을 고친 줄에 다시 넣은 함정 둘(「공수 넣기」, 「훑어」와
「펜스」)을 세 번 중 두 번 놓쳤다. 줄을 크게 고치면 발행 게이트도 다른 줄로 보아 놓친다. 줄 이력은 판정기가
이미 알므로 글자로 대조한다.

**지키는 것**

- 모델이 안 짚어도 남은 표현에 고칠 지적이 붙고 기록에도 남나(발행 게이트가 그 기록으로 막는다)
- 모델이 같은 표현을 이미 짚었으면 겹쳐 붙이지 않나
- 표현을 지운 수정에는 안 붙나
- 받지 않음으로 닫은 표현은 일부러 남긴 것이라 안 붙나
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402
from test_rejudge_cap import BASE, _Base  # noqa: E402

ROUND0 = {"line": 5, "phrase": "표시합니다", "category": "업무에서 쓰는 말로 쓰기", "fix": "둡니다",
          "why": "", "decide": "fix"}
# 줄을 크게 고쳤는데 짚힌 표현은 그대로 — 글자 절반 기준으로는 다른 줄이 된다
KEPT = BASE[:4] + ["담당자가 정한 순서대로 오늘 할 일을 표시합니다."]
REMOVED = BASE[:4] + ["담당자가 정한 순서대로 오늘 할 일을 둡니다."]


class KeptPhraseTests(_Base):

    def round0(self) -> None:
        self.write(BASE)
        judge.judge(self.doc, "opus", 10, FakeBackend([ROUND0]).pair())

    def test_a_kept_phrase_is_flagged_even_if_the_model_misses_it(self) -> None:
        self.round0()
        result, _ = self.rejudge(KEPT, [5], [])
        [it] = result["findings"]
        self.assertEqual((5, "표시합니다", "둡니다"), (it["line"], it["phrase"], it["fix"]))
        self.assertTrue(it.get("kept"))
        [rec] = self.last_row()["fixes"]
        self.assertEqual("표시합니다", rec["phrase"], "기록에 안 남으면 발행 게이트가 못 막습니다")
        key = coverage.doc_key(self.doc)
        self.assertEqual([5], [n for n, _ in coverage.open_fixes(key, KEPT, judge.LOG)])

    def test_a_lightly_edited_line_is_flagged_too(self) -> None:
        self.round0()
        result, _ = self.rejudge(BASE[:4] + ["마감이 임박한 업무를 맨 위에 표시합니다."], [5], [])
        self.assertEqual(["표시합니다"], [it["phrase"] for it in result["findings"]])

    def test_no_double_finding_when_the_model_already_flags_it(self) -> None:
        self.round0()
        result, _ = self.rejudge(KEPT, [5], [dict(ROUND0)])
        self.assertEqual(1, len(result["findings"]))
        self.assertFalse(result["findings"][0].get("kept"))

    def test_a_removed_phrase_is_not_flagged(self) -> None:
        self.round0()
        result, _ = self.rejudge(REMOVED, [5], [])
        self.assertEqual([], result["findings"])

    def test_a_dismissed_phrase_is_left_alone(self) -> None:
        self.round0()
        row = {"key": coverage.doc_key(self.doc), "when": time.time(), "line": 5,
               "line_key": coverage.line_key(BASE[4]), "phrase": "표시합니다", "reason": "대상아님",
               "text": BASE[4]}
        coverage.DISMISSALS.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        result, _ = self.rejudge(KEPT, [5], [])
        self.assertEqual([], result["findings"])


class RewordedTests(_Base):
    """짚은 표현을 조금 바꿔 다시 넣은 경우 — 함정 T-12(data/cases/rejudge-traps.jsonl)의 문장."""

    START = ["# 소개", "", "검사가 원문을 그대로 훑어 펜스를 안 본 것입니다."]
    AGAIN = ["# 소개", "", "검사기가 원문을 그대로 훑어서 펜스를 보지 않은 것입니다."]

    def go(self, finding: dict, edited: list[str]) -> dict:
        self.write(self.START)
        judge.judge(self.doc, "opus", 10, FakeBackend([finding]).pair())
        self.write(edited)
        return judge.judge(self.doc, "opus", 10, FakeBackend([]).pair(), [3], self.START)

    def test_a_rare_stem_the_fix_dropped_is_flagged(self) -> None:
        if judge.load_freq() is None:
            self.skipTest("형태소 분석기 없음")
        result = self.go({"line": 3, "phrase": "훑어 펜스를 안 본 것입니다", "category": "업무에서 쓰는 말로 쓰기",
                          "fix": "검사해 코드 펜스를 구분하지 않은 것입니다", "why": "", "decide": "fix"}, self.AGAIN)
        self.assertEqual(["훑어서"], [it["phrase"] for it in result["findings"]])
        self.assertIn("「훑」", result["findings"][0]["why"])

    def test_a_common_stem_is_left_to_the_model(self) -> None:
        if judge.load_freq() is None:
            self.skipTest("형태소 분석기 없음")
        result = self.go({"line": 3, "phrase": "안 본 것입니다", "category": "업무에서 쓰는 말로 쓰기",
                          "fix": "구분하지 않은 것입니다", "why": "", "decide": "fix"}, self.AGAIN)
        self.assertEqual([], result["findings"], "「보다」처럼 흔한 어간까지 보면 상관없는 줄이 걸립니다")

    def test_a_word_the_fix_keeps_is_not_flagged_even_if_tagged_differently(self) -> None:
        """형태소 분석기가 같은 「민감」을 문장마다 다른 품사로 나눠도 수정안에 그대로 있는 말은 뺀 말이 아니다."""
        if judge.load_freq() is None:
            self.skipTest("형태소 분석기 없음")
        start = ["# 소개", "", "- 업무 기록은 회사 안에서 가장 민감한 글에 듭니다"]
        self.write(start)
        judge.judge(self.doc, "opus", 10, FakeBackend([{
            "line": 3, "phrase": "가장 민감한 글에 듭니다", "category": "업무에서 쓰는 말로 쓰기",
            "fix": "가장 민감한 문서에 속합니다", "why": "", "decide": "fix"}]).pair())
        self.write(["# 소개", "", "- 업무 기록은 회사 안에서 가장 민감한 문서에 속합니다"])
        result = judge.judge(self.doc, "opus", 10, FakeBackend([]).pair(), [3], start)
        self.assertEqual([], result["findings"])

    def test_a_word_already_outside_the_flagged_phrase_is_left_alone(self) -> None:
        """원래 줄의 짚지 않은 부분(굵은 라벨 「헛짚음」)에 있던 어절은 그 어간이 지적에 들어 있어도 다시 넣은 말이 아니다."""
        if judge.load_freq() is None:
            self.skipTest("형태소 분석기 없음")
        start = ["# 소개", "", "- **헛짚음 하나를 고침** — 수정안에 그대로 있는 말을 뺀 말로 보고 짚음"]
        self.write(start)
        judge.judge(self.doc, "opus", 10, FakeBackend([{
            "line": 3, "phrase": "수정안에 그대로 있는 말을 뺀 말로 보고 짚음", "category": "사물을 사람처럼 쓴 서술",
            "fix": "판정기가 수정안에 그대로 있는 말을 뺀 말로 판단해 지적함", "why": "", "decide": "fix"}]).pair())
        self.write(["# 소개", "", "- **헛짚음 하나를 고침** — 판정기가 수정안에 그대로 있는 말을 뺀 말로 판단해 지적함"])
        result = judge.judge(self.doc, "opus", 10, FakeBackend([]).pair(), [3], start)
        self.assertEqual([], result["findings"])

    def test_a_fix_that_only_adds_words_keeps_the_phrase(self) -> None:
        result = self.go({"line": 3, "phrase": "펜스를", "category": "맥락이 빠진 명사구",
                          "fix": "코드 펜스를", "why": "", "decide": "fix"},
                         ["# 소개", "", "검사가 원문을 그대로 읽어 코드 블록의 펜스를 무시한 것입니다."])
        self.assertEqual([], result["findings"], "덧붙이기만 한 수정안이면 표현이 남는 것이 맞습니다")


if __name__ == "__main__":
    unittest.main()
