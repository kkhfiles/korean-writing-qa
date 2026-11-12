"""서식만 바꾼 줄을 다시 판정하지 않고, 닫은 지적을 다시 열지 않는지 본다 — 모델은 안 부른다.

(2026-11-12 다른 세션 인계 B1, B2) 문단을 목록으로 바꾸거나 굵은 머리를 떼는 구조 개편만으로 줄 해시가 바뀌어 판정기가
이미 본 줄을 다시 판정했고(재판정 횟수가 쌓여 사람 확인 13건, 3건, 2건, 1건), 닫은 지적이 다시 열려 같은 근거로
세 번 닫았다.

**지키는 것**

- 줄 앞 목록, 번호, 제목, 인용 표시와 굵게, 빈칸만 다르면 같은 `form_key`
- 글이 바뀌면 다른 `form_key` — 다시 판정하고, 닫은 지적도 다시 염
- 이미 본 줄을 서식만 바꾸면 판정 대상이 아님(`open_lines`)
- 받지 않음으로 닫은 지적은 서식만 바꾼 줄에서 닫힌 채(`open_fixes`)
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import layer2_coverage as coverage  # noqa: E402

LINE = "결과는 F1~F13 항목으로 나눠 라이선스 조건과 함께 정리함"


class FormKeyTests(unittest.TestCase):

    def test_format_only_changes_share_a_key(self) -> None:
        k = coverage.form_key(LINE)
        for v in ("- " + LINE, "  - " + LINE, "1. " + LINE, "> " + LINE, "## " + LINE,
                  "- **결과는** F1~F13 항목으로 나눠 라이선스 조건과 함께 정리함"):
            with self.subTest(v=v):
                self.assertEqual(k, coverage.form_key(v))

    def test_a_wording_change_is_a_new_key(self) -> None:
        self.assertNotEqual(coverage.form_key(LINE), coverage.form_key(LINE.replace("정리함", "적음")))
        self.assertNotEqual(coverage.form_key("- 2건 해결"), coverage.form_key("- 3건 해결"))


class WordsKeptTests(unittest.TestCase):

    OLD = ["- **쓰는 법** — 공식 양식이 없어 팀 의견을 모은 목록. 앞 절에서 다루지 않은 둘만 적음",
           "- 발표 자료는 심사 전날까지 공유함"]

    def test_a_split_piece_keeps_its_words(self) -> None:
        self.assertTrue(coverage.words_kept("- 공식 양식이 없어 팀 의견을 모은 목록.", self.OLD))

    def test_sentences_gathered_from_judged_lines_keep_their_words(self) -> None:
        self.assertTrue(coverage.words_kept("앞 절에서 다루지 않은 둘만 적음. 발표 자료는 심사 전날까지 공유함", self.OLD))

    def test_a_reworded_line_does_not(self) -> None:
        self.assertFalse(coverage.words_kept("- 발표 자료는 심사 이틀 전까지 공유함", self.OLD))
        self.assertFalse(coverage.words_kept("- 공식 양식이 없어 팀 의견을 모은 목록. 새로 넣은 문장도 있음", self.OLD))


class RecordTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log, self.dis = self.dir / "calls.jsonl", self.dir / "x.jsonl"
        self.key = "D:/docs/advice.md"
        self.lines = ["# 의견서", "", LINE, "", "다음 회의에서 다시 봄"]
        row = {"ok": True, "key": self.key, "when": time.time(), "seen": coverage.seen_keys(self.lines),
               "seen_form": coverage.form_keys(self.lines),
               "fixes": [{"line": 3, "line_key": coverage.line_key(LINE), "text": LINE, "phrase": "F1~F13 항목",
                          "fix": "F1~F13 기능 항목", "why": "무엇의 항목인지", "category": "요약하다 맥락이 빠진 명사구"}]}
        self.log.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        close = {"key": self.key, "when": time.time(), "line_key": coverage.line_key(LINE), "text": LINE,
                 "phrase": "F1~F13 항목", "reason": "충족", "note": "3행 표가 기능 목록"}
        self.dis.write_text(json.dumps(close, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def open_fixes(self, lines: list[str]) -> list:
        return coverage.open_fixes(self.key, lines, self.log, self.dis)

    def test_a_reformatted_judged_line_is_not_judged_again(self) -> None:
        moved = ["# 의견서", "", "다음 회의에서 다시 봄", "", "- **결과는** F1~F13 항목으로 나눠 라이선스 조건과 함께 정리함"]
        seen, forms = coverage.judged(self.key, self.log), coverage.judged_forms(self.key, self.log)
        self.assertEqual([], coverage.open_lines(moved, None, seen, forms))
        self.assertEqual([5], coverage.open_lines(moved, None, seen), "서식 무시 해시를 안 주면 예전처럼 다시 판정")

    def test_a_reworded_line_is_judged_again(self) -> None:
        changed = ["# 의견서", "", LINE.replace("정리함", "표로 정리함"), "", "다음 회의에서 다시 봄"]
        self.assertEqual([3], coverage.open_lines(changed, None, coverage.judged(self.key, self.log),
                                                  coverage.judged_forms(self.key, self.log)))

    def test_a_closed_fix_stays_closed_after_reformatting(self) -> None:
        self.assertEqual([], self.open_fixes(self.lines))
        bullets = ["# 의견서", "", "- " + LINE, "", "- 다음 회의에서 다시 봄"]
        self.assertEqual([], self.open_fixes(bullets))

    def test_a_closed_fix_reopens_when_the_wording_changes(self) -> None:
        changed = ["# 의견서", "", LINE.replace("함께 정리함", "함께 표로 정리함"), "", "다음 회의에서 다시 봄"]
        self.assertEqual([3], [n for n, _ in self.open_fixes(changed)])


if __name__ == "__main__":
    unittest.main()
