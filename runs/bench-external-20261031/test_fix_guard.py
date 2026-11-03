"""수정안 가리개(`fix_guard.py`)가 사람 확인 없이 넣으면 안 되는 수정안을 막고 조사를 맞추는지 고정한다.

**왜 있나**(2026-11-03) — 다듬은 글에 판정기 수정안을 바로 넣었더니 두 판정자 모두 나빠졌다고 판정했다. 진 까닭이
원문에 없는 말, 지운 내용, 바꾼 제목, 지운 서식, 틀어진 조사였다(`runs/bench-external-20261031/README.md` 「D3」).
아래 예문은 그 꼴을 본떠 지었다.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fix_guard  # noqa: E402

HAS_KIWI = fix_guard._morph() is not None
DOC = ("# 점검 계획\n"
       "**검색 고도화**: 다음 분기에 진행합니다.\n"
       "확대 적용을 중단하고 보완 검증을 진행합니다.\n"
       "SLA 위반이 발생한 고객사에 대한 보상 기준을 검토합니다.\n"
       "관련 문의가 58건 접수되어 개선이 필요하다.\n"
       "서비스 **‘한빛워크’**를 이용해 주셔서 감사합니다.\n"
       "점검은 새벽에 진행합니다.\n")


def line_of(text: str) -> str:
    return next(l for l in DOC.splitlines() if text in l)


class FixGuardTests(unittest.TestCase):
    def test_markup_change_is_blocked(self) -> None:
        why = fix_guard.reasons("**‘한빛워크’**", "‘한빛워크’", line_of("한빛워크"), DOC)
        self.assertTrue(any("서식" in w for w in why), why)

    @unittest.skipUnless(HAS_KIWI, "형태소 분석기 없음")
    def test_new_noun_is_blocked(self) -> None:
        why = fix_guard.reasons("보완 검증을 진행합니다", "원인을 보완한 뒤 다시 검증합니다", line_of("보완 검증"), DOC)
        self.assertTrue(any("원인" in w for w in why), why)
        why = fix_guard.reasons("고객사에 대한 보상 기준", "고객사에 지급할 보상 기준", line_of("보상 기준"), DOC)
        self.assertTrue(any("지급" in w for w in why), why)

    @unittest.skipUnless(HAS_KIWI, "형태소 분석기 없음")
    def test_dropped_content_is_blocked(self) -> None:
        why = fix_guard.reasons("58건 접수되어 개선이 필요하다.", "58건 접수되었다.", line_of("58건"), DOC)
        self.assertTrue(any("빠짐" in w for w in why), why)

    @unittest.skipUnless(HAS_KIWI, "형태소 분석기 없음")
    def test_heading_or_bold_label_change_is_blocked(self) -> None:
        why = fix_guard.reasons("검색 고도화", "검색 조기 출시", line_of("검색 고도화"), DOC)
        self.assertTrue(any("제목" in w for w in why), why)

    @unittest.skipUnless(HAS_KIWI, "형태소 분석기 없음")
    def test_plain_rewording_passes(self) -> None:
        """같은 뜻을 풀어 쓴 것 — 문서에 있는 명사만 쓰고 내용어를 지우지 않음."""
        for phrase, fix, near in (
                ("새벽에 진행합니다", "새벽에 합니다", "새벽에"),
                ("보완 검증을 진행합니다", "보완 검증을 합니다", "보완 검증"),
                ("고객사에 대한 보상 기준", "고객사의 보상 기준", "보상 기준")):
            with self.subTest(fix=fix):
                self.assertEqual(fix_guard.reasons(phrase, fix, line_of(near), DOC), [])

    def test_particle_follows_the_new_word(self) -> None:
        self.assertEqual(fix_guard.fit_particle("대체 이용 경로와 잔여 위험", "경로", "수단"), "대체 이용 수단과 잔여 위험")
        self.assertEqual(fix_guard.fit_particle("이 방안이 좋다", "방안", "방법"), "이 방법이 좋다")
        self.assertEqual(fix_guard.fit_particle("검토를 마침", "검토", "확인"), "확인을 마침")
        self.assertEqual(fix_guard.fit_particle("서울으로 감", "서울", "서울"), "서울로 감")   # ㄹ 받침 뒤 「로」
        self.assertEqual(fix_guard.fit_particle("회의는 끝남", "회의", "회의"), "회의는 끝남")


if __name__ == "__main__":
    unittest.main()
