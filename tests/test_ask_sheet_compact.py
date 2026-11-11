"""사람 확인 표가 사람이 읽을 만한 길이인지 본다 — 바뀐 낱말만 칸에, 판정 이력과 전문은 표 밖에.

(2026-11-11 사용자 「사람 확인 표 이걸 내가 읽고 판단하라고 준건가? 텍스트가 이렇게 많은데? 더 좋은 방안을
만들어야할듯.」 · chungbuk 세션이 전달) 멘토링 문서의 재판정 상한 행이 칸마다 줄 전체 원문, 기준 판 줄 전체, 판정
이력 전부를 담아 세 줄짜리 표가 칸마다 수백 자였다.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ask_sheet  # noqa: E402

BASE = ("| **AI 작업은 오류 없이 일부만 처리하고 끝나기도 함 — 「종료」와 「입력을 끝까지 처리하고 종료」를 따로 기록** | "
        "예약해 둔 자동 작업 두 종류를 한 달 동안 결과물로 세어 보니, 각각 약 30%가 「성공」으로 기록됐지만 실제로는 일을 "
        "다 하지 않은 상태였음 | 블록마다 모델에 전달한 입력의 글자 수를 실행 기록에 저장 |")
CUR = BASE.replace("따로 기록", "구분해 기록").replace("결과물로 세어 보니", "결과물 수를 집계해 보니")
HISTORY = ("[업무에서 쓰는 말로 쓰기] 「세어 보니」 → 「집계해 보니」(반영) / "
           "[실무 행위 밝히기] 「따로 기록」 → 「구분해 기록」(반영) / [군더더기 지우기] 「약」 → 「」(제안과 다르게 고침)")
HELD = {"phrase": CUR, "category": "재판정 상한", "fix": "기준 판으로 되돌림 — " + BASE,
        "why": "같은 줄을 4번째 판정해 자동 수정을 멈춤(상한 3회) · 「그대로」는 지금 문장으로 확정, "
               "「고침」은 기준 판으로 되돌림 · 판정 이력: " + HISTORY}


def visible(cell: str) -> str:
    return re.sub(r"\*\*|\\", "", cell)


class HeldRowTests(unittest.TestCase):

    def test_only_the_changed_words_are_in_the_cells(self) -> None:
        now, fix, why, _, details = ask_sheet.row_parts(CUR, [HELD])
        self.assertIn("**구분해**", now)
        self.assertIn("**결과물 수를 집계해**", now)
        self.assertIn("「따로」", fix)
        self.assertIn("「결과물로 세어」", fix)
        for c in (now, fix, why):
            self.assertLessEqual(len(visible(c)), ask_sheet.CELL_MAX + len(ask_sheet.HELD_PREFIX) + 4, c)
        self.assertNotIn("예약해 둔 자동 작업", now + fix, "바뀌지 않은 글까지 칸에 넣었습니다")

    def test_history_and_full_texts_move_below_the_table(self) -> None:
        _, _, why, _, details = ask_sheet.row_parts(CUR, [HELD])
        self.assertNotIn("판정 이력", why)
        self.assertTrue(any(d.startswith("판정 이력:") and "집계해 보니" in d for d in details))
        self.assertTrue(any(d.startswith("기준 판:") for d in details))

    def test_the_sheet_keeps_one_short_row_and_still_parses(self) -> None:
        text = ask_sheet.render([(Path("d.md"), ["x", CUR], [(2, HELD)])], lambda l: "k")
        row = [l for l in text.splitlines() if l.startswith("| 1 |")][0]
        self.assertLess(len(row), 400, "표 행이 여전히 수백 자입니다")
        self.assertIn("### 자세히", text)
        keys, answers = ask_sheet.parse(text.replace("|  |\n", "| 그대로 |\n", 1))
        self.assertEqual({"Q1": "그대로"}, answers)


class LongCellTests(unittest.TestCase):

    def test_a_long_suggestion_is_clipped_and_kept_in_details(self) -> None:
        long_fix = "가" * 150
        item = {"phrase": "짚은 표현", "category": "업무에서 쓰는 말로 쓰기", "fix": long_fix, "why": "시험"}
        _, fix, _, _, details = ask_sheet.row_parts("앞 글 짚은 표현 뒤 글", [item])
        self.assertLessEqual(len(visible(fix)), ask_sheet.CELL_MAX)
        self.assertTrue(any(long_fix in d for d in details), "잘린 수정안의 전문이 표 밖에 없습니다")


if __name__ == "__main__":
    unittest.main()
